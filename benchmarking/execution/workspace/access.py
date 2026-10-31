"""Bounded host access to a live isolated solver workspace."""

import hashlib
import json
import os
import re
import selectors
import subprocess
import time

from benchmarking.execution.budgets import PhaseBudgets, SessionBudget
from benchmarking.execution.checkpoints import DEFAULT_CHECKPOINT_POLICY
from benchmarking.files import relative


class SessionWorkspace:
    """Host-side access to a running session; lifetime remains owned by DockerSession."""

    def __init__(self, cid, root, reader_env, deadline, *, budgets=None):
        self.cid, self.control_socket = cid, root / "protocol/control.sock"
        self.reader_env, self.deadline = reader_env, deadline
        self.active = True
        self.checkpoint_policy = DEFAULT_CHECKPOINT_POLICY
        self.budget = SessionBudget(budgets or PhaseBudgets(3600, settlement_seconds=0), deadline)

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if not self.active or self.budget.phase == 'expired':
            raise TimeoutError("Session deadline has passed")
        return max(0, remaining)

    def access_timeout(self):
        self.remaining()  # Closed workspaces remain inaccessible.
        return 30  # File/control I/O has its own bounded transport allowance.

    def reader(self):
        return ["docker", "exec", "-i", *self.reader_env,
                "--env", "LD_PRELOAD=", "--env", "LD_LIBRARY_PATH=", "--env", "LD_AUDIT=",
                self.cid, "/usr/bin/python3", "-I"]

    def read(self, path, limit):
        relative(path, "workspace path")
        result = subprocess.run([*self.reader(), "/protocol/snapshot.py", path, str(limit)],
                                capture_output=True, timeout=self.access_timeout(), check=False)
        if result.returncode or len(result.stdout) > limit:
            raise ValueError("Workspace file rejected or unavailable")
        return result.stdout

    def write(self, path, content, limit):
        relative(path, "workspace path")
        if len(content) > limit:
            raise ValueError("Workspace file exceeds limit")
        result = subprocess.run([*self.reader(), "/protocol/workspace.py", "write", path, str(limit)],
                                input=content, capture_output=True, timeout=self.access_timeout(), check=False)
        if result.returncode:
            raise ValueError("Workspace file rejected or unavailable")

    def execute(self, execution_id, command, timeout):
        timeout = self.budget.begin_operation(timeout)
        # Preserve declared PDK environment only for model commands, not file readers.
        try:
            return subprocess.Popen(["docker", "exec", "-i", self.cid, "/usr/bin/python3", "-I",
                                     "/protocol/workspace.py", "exec", execution_id,
                                     str(timeout) if timeout is not None else 'none'],
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        except Exception:
            self.budget.end_operation()
            raise

    def cancel(self, execution_id):
        if not self.active:
            return
        if not execution_id.isalnum():
            raise ValueError("Invalid execution ID")
        # The protocol mount is read-only to the solver. Publishing from the
        # host avoids racing command cleanup with an in-container cancel helper.
        (self.control_socket.parent / ("lb-cancel-" + execution_id)).touch()

    def request(self, action):
        # Rootless socket ownership belongs to the container UID. Use the same
        # bounded helper channel as in-container clients, without weakening modes.
        code = ("import json,socket,sys; s=socket.socket(socket.AF_UNIX); "
                "s.connect('/protocol/control.sock'); s.sendall(sys.stdin.buffer.read()+b'\\n'); "
                "sys.stdout.buffer.write(s.makefile('rb').readline(1048576))")
        response = subprocess.run([*self.reader(), "-c", code], input=json.dumps(action).encode(),
                                  capture_output=True, timeout=30 if action == {'action': 'close'} else self.access_timeout(), check=True)
        return json.loads(response.stdout)

    def checkpoint(self, destination, limit, *, previous=None):
        """Hash the stream once; unchanged workspaces produce no archive write."""
        self.remaining()
        policy = self.checkpoint_policy
        timeout = policy.total_seconds
        started = last_progress = time.monotonic()
        deadline = started + timeout
        command = [*self.reader(), '/protocol/workspace.py', 'checkpoint', str(limit),
                   previous or '', str(policy.compression_level)]
        header, errors, progress_buffer = bytearray(), bytearray(), bytearray()
        metadata, stream, size = None, None, 0
        stage, progress_size = 'scan', -1
        digest = hashlib.sha256()
        def expired():
            error = subprocess.TimeoutExpired(command, timeout)
            error.stage, error.elapsed_seconds, error.archive_bytes = stage, round(time.monotonic()-started, 3), size
            return error
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ, 'output')
                    selector.register(process.stderr, selectors.EVENT_READ, 'error')
                    while selector.get_map():
                        remaining = min(deadline, last_progress+policy.idle_seconds) - time.monotonic()
                        if remaining <= 0:
                            raise expired()
                        ready = selector.select(remaining)
                        if not ready:
                            raise expired()
                        for key, _ in ready:
                            content = os.read(key.fileobj.fileno(), 1024 * 1024)
                            if not content:
                                selector.unregister(key.fileobj)
                                continue
                            if key.data == 'error':
                                progress_buffer.extend(content)
                                if len(progress_buffer) > 65536:
                                    raise ValueError('Checkpoint diagnostic record exceeds limit')
                                while b'\n' in progress_buffer:
                                    line, _, rest = progress_buffer.partition(b'\n')
                                    progress_buffer[:] = rest
                                    try:
                                        update = json.loads(line)
                                    except (ValueError, UnicodeDecodeError):
                                        update = {}
                                    if (update.get('stage') in {'scan', 'archive', 'complete'}
                                            and type(update.get('bytes')) is int and update['bytes'] >= 0):
                                        if update['stage'] != stage or update['bytes'] > progress_size:
                                            last_progress = time.monotonic()
                                            stage, progress_size = update['stage'], update['bytes']
                                    else:
                                        errors.extend(line[:max(0, 65536-len(errors))])
                                continue
                            last_progress = time.monotonic()
                            if metadata is None:
                                header.extend(content)
                                if b'\n' not in header:
                                    if len(header) > 4096:
                                        raise ValueError('Invalid checkpoint header')
                                    continue
                                line, content = bytes(header).split(b'\n', 1)
                                if len(line) > 4096:
                                    raise ValueError('Invalid checkpoint header')
                                metadata = json.loads(line)
                                stage = 'archive'
                                if (not re.fullmatch('[0-9a-f]{64}', metadata.get('workspace_digest', ''))
                                        or type(metadata.get('unchanged')) is not bool
                                        or (metadata['unchanged'] and metadata['workspace_digest'] != previous)):
                                    raise ValueError('Invalid checkpoint identity')
                                header.clear()
                                if not metadata['unchanged']:
                                    stream = destination.open('wb')
                                    os.chmod(destination, 0o600)
                            if content:
                                size += len(content)
                                if stream is None or size > 2 * limit + 16 * 1024 * 1024:
                                    raise ValueError('Workspace checkpoint exceeds allocation')
                                stream.write(content)
                                digest.update(content)
                    remaining = max(0, deadline-time.monotonic())
                    process.wait(timeout=remaining)
                if process.returncode:
                    raise subprocess.CalledProcessError(process.returncode, command, stderr=bytes(errors))
                if metadata is None:
                    raise ValueError('Missing checkpoint header')
                if stream is not None:
                    stream.flush()
                    os.fsync(stream.fileno())
                return metadata | {'sha256': digest.hexdigest() if stream is not None else None,
                                   'archive_bytes': size, 'elapsed_seconds': round(time.monotonic()-started, 3)}
            except BaseException:
                process.kill()
                process.wait()
                raise
            finally:
                if stream is not None:
                    stream.close()

    def restore(self, source, limit):
        with source.open('rb') as stream:
            subprocess.run([*self.reader(), '/protocol/workspace.py', 'restore', str(limit)],
                           stdin=stream, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                           check=True, timeout=self.access_timeout())
