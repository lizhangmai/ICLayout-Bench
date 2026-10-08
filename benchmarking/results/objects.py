"""Content-addressed result artifacts stored independently of SQL metadata."""

import re
from pathlib import Path

from benchmarking.files import atomic_write

from .normalization import digest


class FileObjects:
    """Content-addressed files; storage adapters implement put(bytes) and path(sha)."""

    def __init__(self, root):
        self.objects = Path(root)
        self.objects.mkdir(parents=True, exist_ok=True, mode=0o700)

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
