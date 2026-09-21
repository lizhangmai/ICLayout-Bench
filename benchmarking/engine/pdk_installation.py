"""Use ciel's pinned installation and download lifecycle."""

import fcntl
import hashlib
import os
import subprocess
import tempfile
from pathlib import Path

DATA_SOURCE = "https://fossi-foundation.github.io/ciel-releases"


def cache_root():
    """Resolve the shared disposable cache independently of the checkout."""
    override = os.environ.get("ICLAYOUT_BENCH_CACHE_DIR")
    if override:
        return Path(override).expanduser().absolute()
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache").expanduser().absolute() / "iclayout-bench"


def installation_path(source):
    if source.get("kind") != "ciel":
        repository = source["repository"]
        commit = source["commit"]
        if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
            raise ValueError("Git PDK sources require a full commit hash")
        key = hashlib.sha256(repository.encode()).hexdigest()[:16]
        return cache_root() / "pdks/git" / key / commit
    from ciel.common import Version

    return Path(Version(source["version"], source["family"]).get_dir(str(cache_root() / "pdks")))


def prepare_installation(source):
    """Let ciel reuse/download the requested release; serialize concurrent fetches."""
    if source.get("kind") != "ciel":
        destination = installation_path(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.with_suffix(".lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not destination.exists():
                with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
                    stage = Path(temporary) / "checkout"
                    subprocess.run(["git", "init", "--quiet", str(stage)], check=True)
                    subprocess.run(["git", "-C", str(stage), "fetch", "--depth", "1",
                                    source["repository"], source["commit"]], check=True)
                    subprocess.run(["git", "-C", str(stage), "checkout", "--quiet", "FETCH_HEAD"], check=True)
                    if source.get("submodules"):
                        subprocess.run(["git", "-C", str(stage), "submodule", "update", "--init", "--depth", "1",
                                        "--", *source["submodules"]], check=True)
                    stage.rename(destination)
        return destination
    from ciel.manage import fetch
    from ciel.source import StaticWebDataSource

    destination = installation_path(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.with_suffix(".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if destination.is_dir():
            return destination
        provider = StaticWebDataSource(DATA_SOURCE)
        try:
            fetch(str(cache_root() / "pdks"), source["family"], source["version"], data_source=provider,
                  include_libraries=source["libraries"], build_if_not_found=False)
        finally:
            provider.session.close()
    return destination
