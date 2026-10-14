"""Explicit native configuration homes and concurrent file credential retention."""

import fcntl
import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path

from benchmarking.files import atomic_write, write_json


def select_home(metadata, env, home):
    home = Path(home).resolve()
    filename = metadata.configuration_file
    if filename is None:
        raise ValueError("This harness does not have a native configuration home")
    if not home.is_dir():
        raise ValueError("Native configuration directory is missing: " + str(home))
    path = home / filename
    if not path.is_file() or path.is_symlink():
        raise ValueError("Native configuration must be a regular file: " + str(path))
    env[metadata.home_environment] = str(home)
    return home


@contextmanager
def _credential_lock(source):
    descriptor = os.open(source.parent / ".credentials.lock",
                         os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _sources(private):
    path = private / "credential-sources.json"
    return json.loads(path.read_text()) if path.exists() else {}


def stage_file(source, target, private):
    """Bind one credential file to its selected source, preserving native refreshes."""
    if not source.is_file() or source.is_symlink():
        raise ValueError("Native credential must be a regular file: " + str(source))
    with _credential_lock(source):
        sources = _sources(private)
        key = target.relative_to(private).as_posix()
        recorded = sources.get(key)
        if recorded and recorded["source"] != str(source):
            raise ValueError("Native credential source changed during continuation")
        raw = source.read_bytes()
        if not recorded and target.exists():
            raise ValueError("Existing native credentials have no bound source")
        if not target.exists():
            # A prior process may have stopped after recording the source but before
            # publishing its snapshot. Bind the bytes actually staged on this retry.
            sources[key] = {"source": str(source), "sha256": _digest(raw), "status": "seeded"}
            write_json(private / "credential-sources.json", sources)
            atomic_write(target, raw)
        elif target.is_symlink():
            raise ValueError("Private native credential must not be a symlink")
    return raw


def sync_files(private):
    """Write native refreshes back only while their source still matches the seed."""
    # The record contains paths and private digests only, never credential bytes.
    for key, recorded in _sources(private).items():
        source, target = Path(recorded["source"]), private / key
        if not target.is_file() or target.is_symlink():
            continue
        with _credential_lock(source):
            sources = _sources(private)
            state = sources[key]
            if not source.is_file() or source.is_symlink():
                state["status"] = "source_removed"
            else:
                current, refreshed = source.read_bytes(), target.read_bytes()
                if current == refreshed:
                    state.update(sha256=_digest(current), status="unchanged")
                elif _digest(refreshed) == state["sha256"]:
                    state["status"] = "source_changed"
                elif _digest(current) == state["sha256"]:
                    atomic_write(source, refreshed)
                    state.update(sha256=_digest(refreshed), status="refreshed")
                else:
                    # A different process/login owns the new source. Never replace it
                    # with a competing refresh from this attempt's private snapshot.
                    state["status"] = "refresh_conflict"
            write_json(private / "credential-sources.json", sources)
