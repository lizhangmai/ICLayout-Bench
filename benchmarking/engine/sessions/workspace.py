"""Bounded host access to a live isolated solver workspace."""

import json
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
