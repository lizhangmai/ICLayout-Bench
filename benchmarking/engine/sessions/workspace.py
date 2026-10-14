"""Bounded host access to a live isolated solver workspace."""

import hashlib
import json
import os
import re
import selectors
import subprocess
import time

from benchmarking.files import relative


class SessionWorkspace:
    """Host-side access to a running session; lifetime remains owned by DockerSession."""

    def __init__(self, cid, root, reader_env, deadline, *, soft_budget=False):
        self.cid, self.control_socket = cid, root / "protocol/control.sock"
        self.reader_env, self.deadline = reader_env, deadline
        self.active = True
        self.soft_budget = soft_budget

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if not self.active or (remaining <= 0 and not self.soft_budget):
            raise TimeoutError("Session deadline has passed")
        return max(0, remaining)

    def access_timeout(self):
        self.remaining()  # Closed workspaces remain inaccessible.
        return None if self.soft_budget else self.remaining()

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
        if not self.soft_budget:
            timeout = min(timeout, self.remaining())
        # Preserve declared PDK environment only for model commands, not file readers.
        return subprocess.Popen(["docker", "exec", "-i", self.cid, "/usr/bin/python3", "-I",
                                 "/protocol/workspace.py", "exec", execution_id, 'none' if timeout is None else str(timeout)],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def cancel(self, execution_id):
        subprocess.run([*self.reader(), "/protocol/workspace.py", "cancel", execution_id],
                       capture_output=True, timeout=self.access_timeout(), check=True)

    def request(self, action):
        # Rootless socket ownership belongs to the container UID. Use the same
        # bounded helper channel as in-container clients, without weakening modes.
        code = ("import json,socket,sys; s=socket.socket(socket.AF_UNIX); "
                "s.connect('/protocol/control.sock'); s.sendall(sys.stdin.buffer.read()+b'\\n'); "
                "sys.stdout.buffer.write(s.makefile('rb').readline(1048576))")
        response = subprocess.run([*self.reader(), "-c", code], input=json.dumps(action).encode(),
                                  capture_output=True, timeout=self.access_timeout(), check=True)
        return json.loads(response.stdout)

    def checkpoint(self, destination, limit, *, previous=None):
        """Hash the stream once; unchanged workspaces produce no archive write."""
        timeout = self.access_timeout()
        deadline = None if timeout is None else time.monotonic() + timeout
        command = [*self.reader(), '/protocol/workspace.py', 'checkpoint', str(limit)]
        if previous is not None:
            command.append(previous)
        header, errors = bytearray(), bytearray()
        metadata, stream, size = None, None, 0
        digest = hashlib.sha256()
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ, 'output')
                    selector.register(process.stderr, selectors.EVENT_READ, 'error')
                    while selector.get_map():
                        remaining = None if deadline is None else deadline - time.monotonic()
                        if remaining is not None and remaining <= 0:
                            raise subprocess.TimeoutExpired(command, timeout)
                        ready = selector.select(remaining)
                        if not ready:
                            raise subprocess.TimeoutExpired(command, timeout)
                        for key, _ in ready:
                            content = os.read(key.fileobj.fileno(), 1024 * 1024)
                            if not content:
                                selector.unregister(key.fileobj)
                                continue
                            if key.data == 'error':
                                errors.extend(content[:max(0, 65536-len(errors))])
                                continue
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
                    remaining = None if deadline is None else max(0, deadline-time.monotonic())
                    process.wait(timeout=remaining)
                if process.returncode:
                    raise subprocess.CalledProcessError(process.returncode, command, stderr=bytes(errors))
                if metadata is None:
                    raise ValueError('Missing checkpoint header')
                if stream is not None:
                    stream.flush()
                    os.fsync(stream.fileno())
                return metadata | {'sha256': digest.hexdigest() if stream is not None else None}
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
