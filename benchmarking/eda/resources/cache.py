"""Cache generated PDK views by their preparation recipe."""

import fcntl
import json
import os
import tempfile
from pathlib import Path

from benchmarking.files import Asset


def cache_root():
    """Resolve the shared disposable cache independently of the checkout."""
    override = os.environ.get("ICLAYOUT_BENCH_CACHE_DIR")
    if override:
        return Path(override).expanduser().absolute()
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache").expanduser().absolute() / "iclayout-bench"


def cached_resources(kind, recipe, build):
    """Build a shared resource directory once, then reuse it across cases."""
    raw = json.dumps({"provenance": recipe}, sort_keys=True, indent=2).encode() + b"\n"
    path = cache_root() / "derived" / kind / Asset(raw, "json").sha256
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("w") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        if not path.exists():
            with tempfile.TemporaryDirectory(dir=path.parent) as temporary:
                stage = Path(temporary) / "resources"
                stage.mkdir()
                mounts = build(stage) or {}
                (stage / "resource.json").write_text(json.dumps(
                    {"provenance": recipe, "mounts": mounts}, sort_keys=True, indent=2) + "\n")
                stage.rename(path)
    return path


def bind_resources(source, destination):
    """Store a cache binding; never materialize a tree of source symlinks."""
    destination.mkdir(parents=True)
    (destination / "resource.json").write_text(json.dumps({"root": str(source)}) + "\n")
