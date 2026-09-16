"""Validated, content-addressed files shared by preparation and evaluation."""

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


def keys(value: dict, required: set[str], optional: set[str], name: str) -> None:
    if not isinstance(value, dict):
        raise TypeError(f"{name} must be a table")
    missing, unknown = required - value.keys(), value.keys() - required - optional
    if missing or unknown:
        raise ValueError(f"{name}: missing {sorted(missing)}, unknown {sorted(unknown)}")


def text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError(f"{name} must be a nonempty string without NUL")
    return value


def relative(value: object, name: str) -> str:
    value = text(value, name)
    if (PurePosixPath(value).is_absolute() or "\\" in value
            or any(p in {"", ".", ".."} for p in value.split("/"))):
        raise ValueError(f"{name} must be a normalized relative POSIX file path")
    return value


def read_file(root: Path, name: str) -> bytes:
    # The operator-selected root may be ../my-agent; lexical normalization is
    # distinct from following symlinks. Declared asset names remain confined.
    path = Path(os.path.abspath(root)) / relative(name, "file path")
    if path.resolve(strict=True) != path or not path.is_file():
        raise ValueError(f"Input must be a regular, non-symlink file: {name}")
    return path.read_bytes()


@dataclass(frozen=True)
class Asset:
    """A snapshot, not a pointer back into a mutable solver workspace."""

    content: bytes
    format: str

    def __post_init__(self) -> None:
        if not isinstance(self.content, bytes):
            raise TypeError("Asset content must be an immutable bytes snapshot")
        text(self.format, "asset format")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()

    def identity(self) -> dict:
        return {"sha256": self.sha256, "format": self.format, "bytes": len(self.content)}


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write(path, content, mode=0o600):
    """Publish only a complete file, then persist its directory entry."""
    descriptor, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
