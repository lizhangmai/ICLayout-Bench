"""Runtime supervision for evaluator sessions and their bounded commands.

This module owns live threads, workspaces and subprocess handles. Durable session
and execution state remains with the caller, which supplies callbacks for changes.
"""

import subprocess
import threading
import traceback
from pathlib import Path

from benchmarking.engine.sessions.docker import DockerSession
from benchmarking.engine.sessions.execution import run_session


class AttachedSession(DockerSession):
    """Docker session that reports when its workspace becomes available."""

    def __init__(self, image, ready, *, runtime=None):
        super().__init__(image, runtime=runtime)
        self.ready = ready

    def run(self, *args, **kwargs):
        return super().run(*args, **kwargs, on_ready=self.ready)


class SessionHandle:
    """Volatile handles for one live evaluator run, without lifecycle policy."""

    def __init__(self, sid, event, abandoned, gate):
        self.session_id = sid
        self.ready = event
        self.abandoned = abandoned
        self.gate = gate
        self.workspace = None
        self.session = None
        self.thread = None
        self.startup_exception_type = None
        self.close_sent = False


class _ExecutionHandle:
    def __init__(self, process, should_close, thread=None):
        self.process = process
        self.should_close = should_close
        self.thread = thread


class SessionControl:
    """Start evaluator runs and supervise live workspace commands.

    The controller keeps process-local handles only. Callers retain durable HTTP
    metadata and define how each callback updates that metadata.
    """

    def __init__(self, *, runner=None, session_factory=None, threading_provider=None):
        self._runner = runner or run_session
        self._session_factory = session_factory or AttachedSession
        self._threading_provider = threading_provider or (lambda: threading)
        self._sessions = {}
        self._executions = {}
        self._lock = threading.RLock()

    @staticmethod
    def reap_abandoned(containers):
        """Remove solver containers left by interrupted durable runs."""
        for container in containers:
            subprocess.run(['docker', 'rm', '-f', container],
                           capture_output=True, timeout=30, check=False)

    def start(self, sid, *, task, config, resources, backends, destination,
              image, solver_runtime=None, execution=None, on_ready,
              on_complete, on_error):
        """Start one evaluator thread and return its readiness handle."""
        thread_module = self._threading_provider()
        handle = SessionHandle(sid, thread_module.Event(), thread_module.Event(),
                               thread_module.Lock())
        with self._lock:
            self._sessions[sid] = handle
            self._executions.setdefault(sid, {})

        def attach(workspace, recorder):
            with handle.gate:
                if handle.abandoned.is_set():
                    raise RuntimeError("Session startup abandoned")
                on_ready(workspace, recorder, handle.session)
                handle.workspace = workspace
                handle.ready.set()

        def run():
            try:
                handle.session = self._session_factory(image, attach, runtime=solver_runtime)
                report = self._runner(
                    task, config, resources, backends, Path(destination),
                    session=handle.session, execution=execution,
                )
                if handle.workspace is not None:
                    on_complete(report)
            except Exception as error:  # noqa: BLE001 -- caller persists a sanitized failure state
                traceback.print_exc()
                if handle.workspace is None:
                    handle.startup_exception_type = type(error).__name__
                else:
                    on_error(error)
            finally:
                handle.ready.set()

        handle.thread = thread_module.Thread(target=run, daemon=True)
        handle.thread.start()
        return handle

    @staticmethod
    def await_ready(handle, timeout):
        """Wait for startup and atomically abandon an unattached timed-out run."""
        signaled = handle.ready.wait(timeout)
        with handle.gate:
            attached = handle.workspace is not None
            if not attached:
                handle.abandoned.set()
        return signaled, attached

    def workspace(self, sid):
        with self._lock:
            handle = self._sessions.get(sid)
            return handle.workspace if handle else None

    def execution_is_live(self, sid, eid):
        with self._lock:
            return eid in self._executions.get(sid, {})

    def start_execution(self, sid, eid, command, timeout, log_path, max_log_bytes,
                        *, should_close, on_started, on_progress, on_complete):
        """Run a workspace command and collect a bounded log on a worker thread."""
        workspace = self.workspace(sid)
        if workspace is None:
            raise RuntimeError("Session workspace is unavailable")
        process = workspace.execute(eid, command, timeout)
        path = Path(log_path)
        path.touch(mode=0o600)
        item = _ExecutionHandle(process, should_close)
        with self._lock:
            self._executions.setdefault(sid, {})[eid] = item
        on_started()

        def collect():
            size, truncated = 0, False
            try:
                process.stdin.write(command.encode())
                process.stdin.close()
                with path.open('ab', buffering=0) as log:
                    while chunk := process.stdout.read1(8192):
                        room = max(0, max_log_bytes - size)
                        log.write(chunk[:room])
                        truncated |= len(chunk) > room
                        size += min(len(chunk), room)
                        on_progress(size, truncated)
                code = process.wait()
            except Exception:  # noqa: BLE001 -- match the service's durable error result
                traceback.print_exc()
                code = 126
            try:
                on_complete(code, size, truncated)
            finally:
                with self._lock:
                    self._executions.get(sid, {}).pop(eid, None)
                self._finish_deferred_close(sid, should_close)

        thread_module = self._threading_provider()
        item.thread = thread_module.Thread(target=collect, daemon=True)
        item.thread.start()
        return process

    def cancel_execution(self, sid, eid):
        workspace = self.workspace(sid)
        if workspace is not None and self.execution_is_live(sid, eid):
            workspace.cancel(eid)

    def close_session(self, sid, active_execution_id=None):
        """Close now, or cancel the active command and close when it drains."""
        workspace = self.workspace(sid)
        if workspace is None:
            raise RuntimeError("Session workspace is unavailable")
        if active_execution_id:
            workspace.cancel(active_execution_id)
        else:
            self._send_close_once(sid, workspace)

    def _finish_deferred_close(self, sid, should_close):
        with self._lock:
            handle = self._sessions.get(sid)
            workspace = handle.workspace if handle else None
            running = bool(self._executions.get(sid))
            if (should_close() and workspace is not None and workspace.active
                    and not running and not handle.close_sent):
                handle.close_sent = True
            else:
                return
        try:
            workspace.request({'action': 'close'})
        except Exception:
            with self._lock:
                handle.close_sent = False
            raise

    def _send_close_once(self, sid, workspace):
        with self._lock:
            handle = self._sessions.get(sid)
            if handle is None or handle.close_sent:
                return
            handle.close_sent = True
        try:
            workspace.request({'action': 'close'})
        except Exception:
            with self._lock:
                handle.close_sent = False
            raise

    def active_handles(self):
        with self._lock:
            return tuple(self._sessions.items())

    def join(self, sid, timeout=None):
        with self._lock:
            handle = self._sessions.get(sid)
        if handle and handle.thread:
            handle.thread.join(timeout=timeout)
