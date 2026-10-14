"""Trusted helpers for operating an existing session container (not a new runtime)."""
import hashlib
import json
import os
import signal
import stat
import subprocess
import sys
import tarfile
import time
import uuid
from pathlib import Path


def workspace_archive(output, mode, limit):
    """Traverse the same bounded tree for its identity and its recovery archive."""
    total = 0

    def regular(member):
        nonlocal total
        if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
            raise ValueError('Workspace contains a special file')
        total += member.size
        if total > limit:
            raise ValueError('Workspace checkpoint exceeds allocation')
        return member

    with tarfile.open(fileobj=output, mode=mode, dereference=False) as archive:
        for entry in sorted(Path('/workspace').iterdir()):
            archive.add(entry, arcname=entry.name, filter=regular)


def checkpoint(limit, previous=None):
    """Reuse unchanged content while committing fresh HTTP completion metadata."""
    digest = hashlib.sha256()

    class Sink:
        def write(self, content):
            digest.update(content)
            return len(content)

    workspace_archive(Sink(), 'w|', limit)
    identity = digest.hexdigest()
    unchanged = identity == previous
    sys.stdout.buffer.write((json.dumps({'workspace_digest': identity, 'unchanged': unchanged}) + '\n').encode())
    sys.stdout.buffer.flush()
    if not unchanged:
        workspace_archive(sys.stdout.buffer, 'w|gz', limit)


def restore(limit):
    """Extract only inside the empty, isolated workspace, under its tmpfs cap."""
    total, links = 0, []
    with tarfile.open(fileobj=sys.stdin.buffer, mode='r|gz') as archive:
        for member in archive:
            total += member.size
            if total > limit or not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
                raise ValueError('Invalid workspace checkpoint')
            if member.issym() or member.islnk():
                links.append(member)
            else:
                archive.extract(member, '/workspace', filter='data')
        # External symlinks may point at declared read-only resources. Restore
        # them last so no archive data can be written through such a link.
        for member in sorted(links, key=lambda entry: entry.issym()):
            archive.extract(member, '/workspace', filter='tar' if member.issym() else 'data')


def write_file(path, content):
    parts = path.split('/')
    if any(part in {'', '.', '..'} for part in parts) or '\x00' in path:
        raise ValueError('Invalid relative path')
    parent = os.open('/workspace', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = '.write-' + uuid.uuid4().hex
    try:
        for part in parts[:-1]:
            try:
                os.mkdir(part, 0o700, dir_fd=parent)
            except FileExistsError:
                pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
        try:
            old = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISREG(old.st_mode) or old.st_nlink != 1:
                raise ValueError('Target is not a regular unlinked file')
        except FileNotFoundError:
            pass
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, parts[-1], src_dir_fd=parent, dst_dir_fd=parent)
    finally:
        try:
            os.unlink(temporary, dir_fd=parent)
        except FileNotFoundError:
            pass
        os.close(parent)


def execute(execution_id, seconds):
    """Foreground command with bounded lifetime and removal of leftover children.

    Used only with the idle session PID 1 and one external execution at a time.
    All model processes share the session UID; the helper has no extra capability.
    """
    command = sys.stdin.buffer.read(128*1024+1).decode()
    if len(command.encode()) > 128*1024:
        raise ValueError('Command too large')
    child = subprocess.Popen(['/bin/sh', '-lc', command], start_new_session=True,
                             stdin=subprocess.DEVNULL)
    deadline = None if seconds is None else time.monotonic()+seconds
    marker = Path('/tmp') / ('lb-cancel-'+execution_id)
    reason = None
    try:
        while child.poll() is None:
            if marker.exists() or (deadline is not None and time.monotonic() >= deadline):
                reason = 124 if not marker.exists() else 125
                break
            time.sleep(.05)
    finally:
        # A new PID namespace per session: PID 1 is the idle keeper, this helper
        # is the only trusted process while an API execution is active.
        for entry in Path('/proc').iterdir():
            if entry.name.isdigit() and int(entry.name) not in {1, os.getpid()}:
                try:
                    os.kill(int(entry.name), signal.SIGKILL)
                except ProcessLookupError:
                    pass
        child.wait()
        marker.unlink(missing_ok=True)
    return reason if reason is not None else child.returncode


if __name__ == '__main__':
    try:
        action, path = sys.argv[1:3]
        if action == 'write':
            limit = int(sys.argv[3])
            content = sys.stdin.buffer.read(limit+1)
            if len(content) > limit:
                raise ValueError('File too large')
            write_file(path, content)
        elif action == 'exec':
            raise SystemExit(execute(path, None if sys.argv[3] == 'none' else float(sys.argv[3])))
        elif action == 'cancel':
            if not path.isalnum():
                raise ValueError('Invalid execution ID')
            (Path('/tmp')/('lb-cancel-'+path)).touch()
        elif action == 'checkpoint':
            checkpoint(int(path), sys.argv[3] if len(sys.argv) > 3 else None)
        elif action == 'restore':
            restore(int(path))
        else:
            raise ValueError('Unknown operation')
    except (OSError, ValueError) as error:
        print(json.dumps({'error': type(error).__name__}), file=sys.stderr)
        raise SystemExit(126) from None
