"""Run a tool with frozen files in a fresh container, retaining failure evidence."""

import io
import subprocess
import tarfile
from pathlib import Path

from benchmarking.evaluation.contracts import number
from benchmarking.files import Asset, ReadOnlyMount, relative

from .budget import tool_timeout
from .types import ToolResult

_LOAD = '''import sys, tarfile
def regular(member, root):
    if not (member.isdir() or member.isfile()):
        raise ValueError('Tool inputs must be regular files or directories')
    member = tarfile.tar_filter(member, root)
    member.mode = 0o777 if member.isdir() else 0o444
    return member
with tarfile.open(fileobj=sys.stdin.buffer, mode='r|') as archive:
    archive.extractall('/workspace', filter=regular)
'''
_DRAIN = '''import os, signal
for name in os.listdir('/proc'):
    if name.isdigit() and int(name) not in (1, os.getpid()):
        try:
            os.kill(int(name), signal.SIGKILL)
        except ProcessLookupError:
            pass
'''
_SNAPSHOT = (Path(__file__).resolve().parents[1] / 'container_scripts/snapshot.py').read_text()


def input_archive(files):
    """Serialize declared inputs in memory, including writable mount parents."""
    stream = io.BytesIO()
    directories = {parent.as_posix() for name in files for parent in Path(name).parents
                   if parent.as_posix() != '.'}
    with tarfile.open(fileobj=stream, mode='w') as archive:
        for name in sorted(directories, key=lambda value: (value.count('/'), value)):
            member = tarfile.TarInfo(name)
            member.type, member.mode = tarfile.DIRTYPE, 0o777
            archive.addfile(member)
        for name, asset in files.items():
            if isinstance(asset, ReadOnlyMount):
                continue
            member = tarfile.TarInfo(name)
            member.size, member.mode = len(asset.content), 0o444
            archive.addfile(member, io.BytesIO(asset.content))
    return stream.getvalue()


def read_only_mount_args(resource: ReadOnlyMount, target: str) -> list[str]:
    """Bind a declared installed resource through Docker's read-only transport."""
    return ["--mount", f"type=bind,src={resource.path},dst={target},readonly"]


class DockerTool:
    @property
    def limits(self) -> dict:
        return {"cpus": None, "memory_mb": self.memory_mb, "pids": None}

    def _limit_args(self) -> list[str]:
        return [] if self.memory_mb is None else ["--memory", f"{self.memory_mb}m"]

    def __init__(self, image: str, version_command: list[str], timeout_seconds: float, *, runtime=None,
                 memory_mb=None):
        if memory_mb is not None and (type(memory_mb) is not int or not 256 <= memory_mb <= 262144):
            raise ValueError('Tool memory must be between 256 and 262144 MB')
        self.memory_mb = memory_mb
        self.runtime = runtime
        self.network = runtime.network if runtime else 'none'
        self.timeout_seconds = number(timeout_seconds)
        if self.timeout_seconds <= 0:
            raise ValueError("Tool timeout must be positive")
        self.image_id = subprocess.check_output(
            ["docker", "image", "inspect", "--format", "{{.Id}}", image], text=True,
        ).strip()
        self.version = subprocess.check_output(
            ["docker", "run", "--rm", "--network", self.network, "--cap-drop", "ALL",
             "--security-opt", "no-new-privileges", "--read-only", "--log-driver", "none",
             *self._workspace_args(), *self._limit_args(),
             "--user", "1000:1000", *(runtime.docker_args() if runtime else []), self.image_id,
             *(runtime.module_command(version_command[0], version_command) if runtime else version_command)],
            text=True, stderr=subprocess.STDOUT, timeout=self.timeout_seconds,
        ).strip()

    @staticmethod
    def _workspace_args():
        return ['--tmpfs', '/workspace:rw,nosuid,nodev,uid=1000,gid=1000,mode=777',
                '--tmpfs', '/tmp:rw,nosuid,nodev,mode=1777', '--env', 'HOME=/tmp',
                '--env', 'PYTHONDONTWRITEBYTECODE=1']

    @staticmethod
    def _reader(cid, script, *arguments, user='1000:1000'):
        return ['docker', 'exec', '-i', '--user', user,
                '--env', 'LD_PRELOAD=', '--env', 'LD_LIBRARY_PATH=', '--env', 'LD_AUDIT=',
                cid, '/usr/bin/python3', '-I', '-c', script, *arguments]

    @property
    def identity(self) -> dict:
        return {"image_id": self.image_id, "tool_version": self.version,
                "timeout_seconds": self.timeout_seconds, "limits": self.limits,
                "execution_sha256": Asset(Path(__file__).read_bytes() + _SNAPSHOT.encode(), "python").sha256,
                **({'external': self.runtime.identity} if self.runtime else {})}

    def run(self, command: list[str], files: dict[str, Asset | ReadOnlyMount], exports: dict[str, str], *,
            environment: dict[str, str] | None = None) -> ToolResult:
        """Stream inputs and outputs through a fresh, in-memory tool workspace.

        exports maps paths to formats. Collect declared files even on failure;
        never interpret tool output as a successful circuit check here.
        """
        for name in (*files, *exports):
            relative(name, "tool file")
        evidence, produced = {}, {}
        code, reason = None, ""
        mounts = [arg for name, asset in files.items() if isinstance(asset, ReadOnlyMount)
                  for arg in read_only_mount_args(asset, f'/workspace/{name}')]
        env_args = [arg for k, v in (environment or {}).items() for arg in ('--env', f'{k}={v}')]
        cid = subprocess.check_output([
            'docker', 'create', '--network', self.network, '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges', '--read-only', '--log-driver', 'none',
            *self._workspace_args(), *self._limit_args(), '--user', '1000:1000', '--workdir', '/workspace',
            *(self.runtime.docker_args() if self.runtime else []),
            *env_args, *mounts, self.image_id, '/usr/bin/python3', '-I', '-c',
            'import signal; signal.pause()',
        ], text=True).strip()
        try:
            subprocess.run(['docker', 'start', cid], check=True, capture_output=True)
            subprocess.run(self._reader(cid, _LOAD, user='0:0'), input=input_archive(files),
                           check=True, capture_output=True)
            argv = self.runtime.module_command(command[0], command) if self.runtime else command
            try:
                run = subprocess.run(['docker', 'exec', '-i', cid, *argv], capture_output=True,
                                     timeout=tool_timeout(self.timeout_seconds), check=False)
                evidence['console'] = Asset(run.stdout + run.stderr, 'text')
                code = run.returncode
                if code:
                    reason = f'Tool/container exited with {code}'
            except subprocess.TimeoutExpired as error:
                evidence['console'] = Asset((error.stdout or b'') + (error.stderr or b''), 'text')
                reason = 'Tool exceeded its fixed time limit'
            # Keep tmpfs mounted until all declared failure/success outputs have
            # been collected, but freeze them by removing every tool descendant.
            subprocess.run(self._reader(cid, _DRAIN), capture_output=True, check=True)
            for name, file_format in exports.items():
                copied = subprocess.run(self._reader(cid, _SNAPSHOT, name, 'none', 'allow-hardlinks'),
                                        capture_output=True, check=False)
                if copied.returncode:
                    evidence[f'missing:{name}'] = Asset(copied.stderr, 'text')
                    reason = reason or f'Declared tool output is missing: {name}'
                else:
                    produced[name] = Asset(copied.stdout, file_format)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            reason = f'{type(error).__name__}: {error}'
            evidence['execution_error'] = Asset(str(error).encode(), 'text')
        finally:
            cleanup = subprocess.run(['docker', 'rm', '-f', cid], capture_output=True, check=False)
            if cleanup.returncode:
                reason = reason or 'Container cleanup failed'
                evidence['cleanup_error'] = Asset(cleanup.stderr, 'text')
        return ToolResult(code, reason, produced, evidence)
