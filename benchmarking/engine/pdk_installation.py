"""Fetch a pinned prebuilt PDK with ciel and verify its cached contents."""

import fcntl
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from benchmarking.files import keys

DATA_SOURCE = "https://fossi-foundation.github.io/ciel-releases"


def cache_root():
    """Resolve the shared disposable cache independently of the checkout."""
    override = os.environ.get("ICLAYOUT_BENCH_CACHE_DIR")
    if override:
        return Path(override).expanduser().absolute()
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache").expanduser().absolute() / "iclayout-bench"


def installation_path(source):
    """Resolve a fixed ciel version without downloading or enabling it."""
    from ciel.common import Version
    from ciel.families import Family

    keys(source, {"kind", "family", "version", "libraries", "sha256"}, {"license"}, "ciel source")
    if source["kind"] != "ciel" or source["family"] not in Family.by_name:
        raise ValueError("Unsupported ciel PDK family")
    if not re.fullmatch(r"[0-9a-f]{40}", source["version"]):
        raise ValueError("ciel source requires a full version commit")
    if not re.fullmatch(r"[0-9a-f]{64}", source["sha256"]):
        raise ValueError("ciel source requires a reviewed installation sha256")
    libraries = source["libraries"]
    if (not isinstance(libraries, list) or not libraries
            or any(name not in Family.by_name[source["family"]].all_libraries for name in libraries)
            or len(set(libraries)) != len(libraries)):
        raise ValueError("ciel source requires explicit library names")
    return Path(Version(source["version"], source["family"]).get_dir(str(cache_root() / "pdks")))


def installation_digest(root):
    """Hash the complete installed file set, including paths; reject symlinks."""
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Symlink in cached PDK: {path}")
        if path.is_file():
            with path.open("rb") as stream:
                files[path.relative_to(root).as_posix()] = hashlib.file_digest(stream, "sha256").hexdigest()
        elif not path.is_dir():
            raise ValueError(f"Unexpected cached PDK entry: {path}")
    if not files:
        raise ValueError(f"Empty PDK installation: {root}")
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def prepare_installation(source):
    """Download once, publish atomically, and verify on every offline reuse."""
    destination = installation_path(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.with_suffix(".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if destination.exists() or destination.is_symlink():
            if destination.is_symlink() or installation_digest(destination) != source["sha256"]:
                raise ValueError(f"Cached PDK checksum mismatch: {destination}; remove this version and fetch again")
            return destination
        from ciel.manage import fetch
        from ciel.source import StaticWebDataSource
        from httpx import HTTPError

        # Keep interrupted downloads outside the published cache. fetch never
        # enables a version and never falls back to a local open-pdks build.
        with tempfile.TemporaryDirectory(prefix=".download-", dir=destination.parent) as staging:
            provider = StaticWebDataSource(DATA_SOURCE)
            try:
                version = fetch(staging, source["family"], source["version"], data_source=provider,
                                include_libraries=source["libraries"], build_if_not_found=False)
            except HTTPError as error:
                raise RuntimeError("PDK download interrupted; rerun fetch to retry") from error
            finally:
                provider.session.close()
            installed = Path(version.get_dir(staging))
            if installation_digest(installed) != source["sha256"]:
                raise ValueError("Downloaded PDK checksum mismatch; review the pinned release before using it")
            installed.rename(destination)
    return destination
