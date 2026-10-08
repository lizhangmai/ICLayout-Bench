"""Offline CLI execution with host-enforced resources and explicit GDS snapshots."""

import json
import os
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from benchmarking.engine.container_scripts import benchmark_feedback as opinions
from benchmarking.files import Asset

from ..inference import INFERENCE_SOCKET
from ..source import SESSION_SOURCE_FILES, package_source
from .environment import (
    _agent_environment,
    resource_preflight,
)
from .protocol import SessionProtocol
from .recorder import RecordingError, SessionResult
from .staging import stage_inputs
from .workspace import SessionWorkspace

MAX_CONSOLE_BYTES = 64 * 1024 * 1024
CONSOLE_PREVIEW_BYTES = 64 * 1024


class ConsoleCapture:
    """Drain Docker attach while preserving bounded preview and durable evidence."""

    def __init__(self, recorder, record, limit, preview_limit=CONSOLE_PREVIEW_BYTES):
        self.recorder, self.record = recorder, record
        self.limit, self.preview_limit = limit, preview_limit
        self.preview = bytearray()
        self.bytes_recorded = 0
        self.truncated = False
        self.failed = threading.Event()

    def drain(self, stream):
        try:
            while chunk := stream.read1(8192):
                if self.failed.is_set():
                    continue  # Drain the pipe until container removal closes Docker attach.
                available = max(0, self.preview_limit - len(self.preview))
                self.preview.extend(chunk[:available])
                self.truncated |= len(chunk) > available
                try:
                    if self.bytes_recorded + len(chunk) > self.limit:
                        self.record("console.limit", bytes_recorded=self.bytes_recorded)
                        self.failed.set()
                        continue
                    if self.recorder:
                        self.record("console.chunk", offset=self.bytes_recorded,
                               content=self.recorder.archive(Asset(chunk, "binary")))
                    self.bytes_recorded += len(chunk)
                except OSError:
                    self.failed.set()
        except OSError:
            self.failed.set()


class DockerSession:
    """Isolated solver; optional operator-reviewed installation and license mounts."""

    def __init__(self, image, *, runtime=None):
        self.runtime = runtime
        if runtime:
            reserved = tuple(Path(p) for p in ('/task', '/agent', '/resources', '/protocol', '/usr', '/bin', '/lib', '/lib64', '/etc'))
            for mount in runtime.mounts:
                target = Path(mount['target'])
                if any(target == p or target in p.parents or p in target.parents for p in reserved):
                    raise ValueError('External solver mount overlaps trusted session paths')
            names = set(runtime.environment) | set(runtime.profile.get('pass_environment', []))
            if names & {'HOME', 'PATH', 'PYTHONPATH', 'PYTHONHOME', 'LD_PRELOAD', 'LD_LIBRARY_PATH', 'LD_AUDIT'}:
                raise ValueError('External solver environment overrides trusted session settings')
        inspected = json.loads(subprocess.check_output(
            ["docker", "image", "inspect", image], text=True, timeout=30))[0]
        if inspected["Config"].get("Volumes"):
            raise ValueError("Session images must not declare writable volumes outside the bounded workspace")
        self.image_id = inspected["Id"]
        security = json.loads(subprocess.check_output(
            ["docker", "info", "--format", "{{json .SecurityOptions}}"], text=True, timeout=30))
        self.rootless = "name=rootless" in (security or [])

    def _delegate_sockets(self, root, uid, gid, inference):
        """Assign private sockets inside the daemon's user namespace.

        Only socket inodes are writable by this short-lived helper; task files
        and host directories are never mounted into it.
        """
        paths = ["/protocol/control.sock"]
        if inference:
            paths.append(INFERENCE_SOCKET)
        mounts = [arg for path in paths for arg in
                  ("--mount", f"type=bind,src={root / path.lstrip('/')},dst={path}")]
        subprocess.run([
            "docker", "run", "--rm", "--network", "none", "--read-only",
            "--cap-drop", "ALL", "--cap-add", "CHOWN", "--user", "0:0",
            "--security-opt", "no-new-privileges", "--memory", "64m", "--cpus", "1",
            "--pids-limit", "16", *mounts, "--entrypoint", "python", self.image_id,
            "-I", "-c", "import os,sys; [os.chown(p,int(sys.argv[1]),int(sys.argv[2])) for p in sys.argv[3:]]",
            str(uid), str(gid), *paths,
        ], check=True, capture_output=True, timeout=30)

    def run(self, task, config, resources, message, *, inference=None, recorder=None, feedback=None, on_ready=None):
        if inference and recorder:
            inference.recorder = recorder
        console_limit = MAX_CONSOLE_BYTES
        uid, gid = (os.getuid(), os.getgid()) if os.getuid() else (1000, 1000)

        def record(kind, **data):
            if recorder:
                recorder.event(kind, **data)
        console = ConsoleCapture(recorder, record, console_limit)
        submissions, candidate, process_feedback = [], None, []
        benchmark_feedback = []
        termination, reason, code = "infrastructure_error", "", None
        started = None
        elapsed = 0.0
        agent_environment = _agent_environment(config, resources)
        resource_info = resource_preflight(resources, self.runtime)
        identity = {"image_id": self.image_id, "network": "none", "read_only_root": True,
                    "harness": config.harness.identity(),
                    "memory_mb": config.memory_mb, "cpus": config.cpus, "pids": config.pids,
                    "workspace_mb": config.workspace_mb, "tmp_mb": 64, "shm_mb": 16,
                    "user": f"{uid}:{gid}", "wall_seconds": config.wall_seconds,
                    "console_limit_bytes": console_limit,
                    "resource_environment": resource_info["environment"],
                    "source_sha256": Asset(Path(__file__).read_bytes(), "python").sha256,
                    "session_implementation_sha256": {name: Asset(package_source(name).read_bytes(), "python").sha256
                                                       for name in SESSION_SOURCE_FILES}}

        if self.runtime:
            identity["external"] = self.runtime.identity
            identity["network"] = self.runtime.network

        with tempfile.TemporaryDirectory(prefix="lb-session-") as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            resource_mounts = stage_inputs(root, task, config, resources, message, resource_info,
                                           inference=inference, feedback=feedback)
            server = socket.socket(socket.AF_UNIX)
            server.bind(str(root / "protocol/control.sock"))
            if os.getuid() == 0:
                os.chown(root / "protocol/control.sock", uid, -1)
            (root / "protocol/control.sock").chmod(0o600)
            server.listen(4)
            server.settimeout(0.05)
            mounts = [arg for name in ("task", "agent", "resources", "protocol")
                      for arg in ("--mount", f"type=bind,src={root/name},dst=/{name},readonly")]
            mounts.extend(resource_mounts)
            if self.runtime:
                mounts.extend(self.runtime.docker_args())
            env = [arg for k, v in agent_environment.items() for arg in ("--env", f"{k}={v}")]
            # Agent-specific loader/locale settings must not affect the trusted reader.
            reader_env = [arg for k in agent_environment for arg in ("--env", f"{k}=")]
            cid, process, reader, workspace = None, None, None, None
            protocol = None
            try:
                cid = subprocess.check_output([
                    "docker", "create", "--network", self.runtime.network if self.runtime else "none", "--read-only", "--cap-drop", "ALL",
                    "--security-opt", "no-new-privileges", "--user", f"{uid}:{gid}", "--workdir", "/workspace",
                    "--memory", f"{config.memory_mb}m", "--memory-swap", f"{config.memory_mb}m",
                    "--cpus", str(config.cpus), "--pids-limit", str(config.pids), "--shm-size", "16m",
                    "--tmpfs", f"/workspace:rw,nosuid,nodev,size={config.workspace_mb}m,uid={uid},gid={gid},mode=700",
                    "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m,mode=1777", "--log-driver", "none",
                    "--env", "HOME=/tmp", "--env", "PYTHONDONTWRITEBYTECODE=1",
                    *env, *mounts, "--entrypoint", config.command[0], self.image_id, *config.command[1:],
                ], text=True, stderr=subprocess.PIPE, timeout=30).strip()
                record("session.created", container_id=cid, environment=identity)
                started = time.monotonic()
                deadline = started + config.wall_seconds
                if inference:
                    inference.start(root / INFERENCE_SOCKET.lstrip("/"), deadline, uid=uid)
                if self.rootless:
                    self._delegate_sockets(root, uid, gid, inference)
                process = subprocess.Popen(["docker", "start", "-a", cid], stdin=subprocess.DEVNULL,
                                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                reader = threading.Thread(target=console.drain, args=(process.stdout,), daemon=True)
                reader.start()

                workspace = SessionWorkspace(cid, root, reader_env, deadline, soft_budget=config.soft_budget)
                if on_ready is not None:
                    # Docker attach may not have completed the start yet.
                    while process.poll() is None and time.monotonic() < deadline:
                        running = subprocess.check_output([
                            "docker", "inspect", "--format", "{{.State.Running}}", cid], text=True).strip()
                        if running == "true":
                            break
                        time.sleep(.02)
                    on_ready(workspace, recorder)

                protocol = SessionProtocol(task, config, workspace, started, deadline,
                    recorder=recorder, record=record, feedback=feedback, on_ready=on_ready)

                while process.poll() is None:
                    if console.failed.is_set() or (recorder and recorder.error):
                        raise RecordingError("Session evidence is incomplete")
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 and not config.soft_budget:
                        termination = "budget_exhausted"
                        reason = "Wall-clock limit reached"
                        break
                    try:
                        connection, _ = server.accept()
                    except TimeoutError:
                        continue
                    with connection:
                        connection.settimeout(1 if config.soft_budget else max(.001, min(1, deadline - time.monotonic())))
                        receipt = {"accepted": False, "reason": "Invalid submission request"}
                        try:
                            request = connection.makefile("rb").readline(opinions.MAX_BYTES + 257)
                            if len(request) > opinions.MAX_BYTES + 256:
                                raise ValueError("Control request is too large")
                            action = json.loads(request)
                            receipt = protocol.dispatch(action)
                            if protocol.expired:
                                termination, reason = "budget_exhausted", "Wall-clock limit reached"
                        except RecordingError:
                            raise
                        except (OSError, ValueError, subprocess.SubprocessError) as error:
                            receipt = {"accepted": False, "reason": str(error)[:1024],
                                       "elapsed_seconds": time.monotonic() - started}
                            record("submission", receipt=receipt, candidate=None)
                            protocol.submissions.append(receipt)
                        try:
                            connection.sendall(json.dumps(receipt).encode() + b"\n")
                        except OSError:
                            pass  # The host event is authoritative even if the client disconnects.
                    if protocol.remote_closed:
                        termination, reason, code = "completed", "Session closed by client", 0
                        break
                if termination != "budget_exhausted" and not protocol.remote_closed:
                    state = json.loads(subprocess.check_output(
                        ["docker", "inspect", "--format", "{{json .State}}", cid], text=True, timeout=10))
                    code = state["ExitCode"]
                    if state.get("Error") or (process.returncode and code == 0):
                        reason = state.get("Error") or "Docker attach failed"
                    else:
                        termination = "completed" if code == 0 else "agent_error"
                        reason = ("OOM killed" if state.get("OOMKilled") else
                                  f"Agent exited with code {code}" if code else "")
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                termination, reason = "infrastructure_error", str(error)
            finally:
                elapsed = time.monotonic() - started if started else 0.0
                if workspace is not None:
                    workspace.active = False
                server.close()
                if inference:
                    inference.stop()
                if cid:
                    cleanup = subprocess.run(["docker", "rm", "-f", cid], capture_output=True, timeout=30, check=False)
                    if cleanup.returncode:
                        termination, reason = "infrastructure_error", "Session container cleanup failed"
                if process:
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                        termination, reason = "infrastructure_error", "Docker attach cleanup timed out"
                if reader:
                    reader.join(timeout=10)
                    if reader.is_alive():
                        console.failed.set()
                if protocol:
                    protocol.close()
                    submissions, candidate = protocol.submissions, protocol.candidate
                    process_feedback = protocol.process_feedback
                    benchmark_feedback = protocol.benchmark_feedback
                if console.failed.is_set() or (recorder and recorder.error):
                    termination, reason = "infrastructure_error", "Session evidence is incomplete"
                # TemporaryDirectory cleanup must be able to unlink staged files.
                for path in root.rglob("*"):
                    if path.is_dir():
                        path.chmod(0o755)
        record("session.stopped", termination=termination, reason=reason, elapsed_seconds=elapsed,
               exit_code=code, console_bytes=console.bytes_recorded,
               console_complete=not console.failed.is_set())
        return SessionResult(termination, reason, elapsed, code, submissions, candidate,
                             Asset(bytes(console.preview), "text"), console.truncated, identity,
                             process_feedback, benchmark_feedback)
