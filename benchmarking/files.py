"""Validated, content-addressed files shared by preparation and evaluation."""

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path, PurePosixPath

import zstandard


class EvidenceError(ValueError):
    """Retained evidence is malformed or differs from its recorded identity."""


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


def is_hub_file(path: Path) -> bool:
    """Accept HF snapshot links through repository blobs, including shared Xet storage."""
    if not path.is_symlink() or not path.is_file():
        return False
    for snapshot in path.parents:
        if snapshot.parent.name == "snapshots" and snapshot.parent.parent.name.startswith("datasets--"):
            blobs = snapshot.parent.parent / "blobs"
            if path.parent.resolve() != path.parent:
                return False
            blob = Path(os.path.abspath(path.parent / os.readlink(path)))
            if blob.parent != blobs or blobs.resolve() != blobs:
                return False
            if not blob.is_symlink():
                return blob.is_file()
            # HF Xet deduplicates repository blobs into cache-wide regular files.
            shared = Path(os.path.abspath(blob.parent / os.readlink(blob)))
            return (shared.resolve() == shared and shared.is_file()
                    and shared.parent.parent == snapshot.parent.parent.parent / "blobs"
                    and re.fullmatch(r"[0-9a-f]{64}", shared.name) is not None
                    and shared.parent.name == shared.name[:2])
    return False


def read_file(root: Path, name: str) -> bytes:
    # The operator-selected root may be ../my-agent; lexical normalization is
    # distinct from following symlinks. Declared asset names remain confined.
    path = Path(os.path.abspath(root)) / relative(name, "file path")
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError:
        return read_retained_file(path)
    if not path.is_file() or (resolved != path and not is_hub_file(path)):
        raise ValueError(f"Input must be a regular, non-symlink file: {name}")
    return path.read_bytes()


def checked(root, reference):
    """Read a declared file and verify the content identity of its snapshot."""
    try:
        raw = read_file(Path(root), reference['path'])
        valid = (hashlib.sha256(raw).hexdigest() == reference['sha256']
                 and ('bytes' not in reference or len(raw) == reference['bytes']))
    except (ValueError, TypeError, KeyError, FileNotFoundError) as error:
        raise EvidenceError('Invalid result evidence reference') from error
    if not valid:
        raise EvidenceError('Result evidence identity mismatch: ' + reference['path'])
    return raw


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


@dataclass(frozen=True)
class ReadOnlyMount:
    """An installed resource, identified by its preparation recipe, not a copy."""

    path: Path
    provenance: Asset

    @property
    def content(self) -> bytes:
        return self.path.read_bytes()

    @property
    def sha256(self) -> str:
        return self.provenance.sha256


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


def write_json(path, value):
    """Atomically persist a participant record without changing its JSON encoding."""
    path = Path(path)
    atomic_write(path, (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode())


def append_event(path, event, *, durable=False, **fields):
    """Append one caller-sanitized runtime event without replacing history."""
    value = {"timestamp": datetime.now(UTC).isoformat(), "event": event, **fields}
    raw = (json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n').encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    try:
        if os.write(descriptor, raw) != len(raw):
            raise OSError('Incomplete runtime journal write')
        if durable:
            os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return value


RETAINED_SCHEMA = "retained-evidence-v1"
RETAINED_MANIFEST = ".retained/manifest.json"


class EvidenceUnavailable(EvidenceError):
    """A recorded attachment was explicitly omitted by the retention policy."""


@lru_cache(maxsize=64)
def _retained_manifest(path, modified, size):
    value = json.loads(Path(path).read_bytes())
    if value.get('schema') != RETAINED_SCHEMA:
        raise EvidenceError('Unsupported retained evidence manifest')
    return value


def retained_manifest(root):
    path = root / RETAINED_MANIFEST
    if path.resolve() != path or not path.is_file():
        raise EvidenceError('Invalid retained evidence manifest')
    info = path.stat()
    return _retained_manifest(str(path), info.st_mtime_ns, info.st_size)


def retained_object(root, record):
    sha, size = record.get('sha256'), record.get('bytes')
    if (not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha)
            or type(size) is not int or size < 0 or record.get('codec') != 'zstd'):
        raise EvidenceError('Invalid retained object reference')
    return root / '.retained/objects' / sha[:2] / (sha + '.zst')


def read_retained_file(path):
    """Resolve a missing logical file only through an explicit local manifest."""
    path = Path(path).absolute()
    for parent in path.parents:
        marker = parent / RETAINED_MANIFEST
        if not marker.exists():
            continue
        manifest = retained_manifest(parent)
        name = relative(path.relative_to(parent).as_posix(), 'retained file')
        if name in manifest.get('omitted', {}):
            reason = manifest['omitted'][name]['reason']
            raise EvidenceUnavailable(f'{name}: {reason}')
        record = manifest.get('files', {}).get(name)
        if record is not None:
            try:
                return verify_compressed(retained_object(parent, record), record['sha256'], record['bytes'], collect=True)
            except (OSError, ValueError, zstandard.ZstdError) as error:
                raise EvidenceError('Invalid compressed result evidence: ' + name) from error
    raise FileNotFoundError(path)


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
