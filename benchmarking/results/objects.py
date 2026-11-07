"""Content-addressed result artifacts stored independently of SQL metadata."""

import hashlib
import os
import re
import tempfile
from pathlib import Path

import zstandard

from benchmarking.files import atomic_write, sync_directory
from benchmarking.results.normalization import digest


class FileObjects:
    """Content-addressed files; storage adapters implement put(bytes) and path(sha)."""

    def __init__(self, root):
        self.objects = Path(os.path.abspath(root))
        self.objects.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.objects.resolve() != self.objects:
            raise ValueError('Object directories must not contain symlinks')

    def path(self, sha):
        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise ValueError("Invalid artifact identity")
        return self.objects / sha[:2] / sha

    def put(self, raw):
        sha = digest(raw)
        path = self.path(sha)
        path.parent.mkdir(exist_ok=True, mode=0o700)
        if path.exists():
            if digest(path.read_bytes()) != sha:
                raise ValueError("Stored artifact is corrupt: " + sha)
        else:
            atomic_write(path, raw)
        return sha, len(raw)

    def compress_file(self, source):
        """Stream exact bytes into a shared, immutable Zstandard object."""
        source = Path(source).absolute()
        if source.resolve() != source or not source.is_file():
            raise ValueError('Object source must be a regular non-symlink file')
        before = source.stat()
        descriptor, temporary = tempfile.mkstemp(prefix='.pending-', dir=self.objects)
        digest, size = hashlib.sha256(), 0
        try:
            with os.fdopen(descriptor, 'wb') as output, source.open('rb') as stream:
                with zstandard.ZstdCompressor(level=3).stream_writer(output, closefd=False) as encoder:
                    while chunk := stream.read(1024 * 1024):
                        digest.update(chunk)
                        size += len(chunk)
                        encoder.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            after = source.stat()
            if (before.st_ino, before.st_size, before.st_mtime_ns) != (
                    after.st_ino, after.st_size, after.st_mtime_ns):
                raise ValueError('Object source changed during archival')
            sha = digest.hexdigest()
            destination = self.path(sha).with_suffix('.zst')
            destination.parent.mkdir(exist_ok=True, mode=0o700)
            if destination.exists():
                verify_compressed(destination, sha, size)
            else:
                os.chmod(temporary, 0o400)
                os.replace(temporary, destination)
                sync_directory(destination.parent)
                sync_directory(self.objects)
            return sha, size, destination
        finally:
            Path(temporary).unlink(missing_ok=True)


def verify_compressed(path, sha, size, *, collect=False):
    """Validate the uncompressed identity, optionally returning its original bytes."""
    path = Path(path).absolute()
    if path.resolve() != path or not path.is_file():
        raise ValueError('Compressed object must be a regular non-symlink file')
    digest, count, chunks = hashlib.sha256(), 0, []
    with path.open('rb') as stream, zstandard.ZstdDecompressor().stream_reader(stream) as decoder:
        while chunk := decoder.read(min(1024 * 1024, max(1, size + 1 - count))):
            count += len(chunk)
            if count > size:
                raise ValueError('Compressed object exceeds recorded size')
            digest.update(chunk)
            if collect:
                chunks.append(chunk)
    if count != size or digest.hexdigest() != sha:
        raise ValueError('Compressed object identity mismatch')
    return b''.join(chunks) if collect else None
