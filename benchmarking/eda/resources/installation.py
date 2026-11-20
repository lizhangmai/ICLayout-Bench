"""Use ciel's pinned installation and download lifecycle."""

import base64
import fcntl
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

from benchmarking.eda.resources.cache import cache_root, cached_resources

DATA_SOURCE = "https://fossi-foundation.github.io/ciel-releases"


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


def prepare_package_resources(source, files, image):
    """Read selected native resources from an installed tools-image distribution.

    This cache holds native resources, never an importable Python environment.
    Package code and dependencies stay in the selected image.
    """
    from benchmarking.evidence.identity import package_source
    from benchmarking.execution.tools.docker import DockerTool
    from benchmarking.files import Asset, keys, relative

    keys(source, {"kind", "distribution", "version"}, set(), "package resource source")
    if not all(isinstance(source[k], str) and source[k] for k in ("distribution", "version")):
        raise ValueError("Package resources require a distribution and exact version")
    for spec in files.values():
        relative(spec["path"], "package resource")
    tool = DockerTool(image, ["python", "--version"], 180)
    reader = Asset(package_source("eda/_scripts/package_resources.py").read_bytes(), "python")
    config = {**source, "files": files}
    recipe = {"source": source, "files": files, "image": tool.image_id}

    def build(stage):
        result = tool.run(["python", "read.py"], {
            "read.py": reader, "package.json": Asset(json.dumps(config).encode(), "json"),
        }, {"resources.json": "json"})
        if result.reason or result.returncode:
            log = result.evidence.get("console", Asset(b"", "text")).content.decode(errors="replace")
            raise ValueError(f"Package resource preparation failed: {result.reason}\n{log}")
        data = json.loads(result.files["resources.json"].content)
        if not data["files"]:
            raise ValueError("Package resources are empty")
        for name, encoded in data["files"].items():
            name = relative(name, "package resource output")
            if not any(name == spec["path"] or spec["format"] == "directory" and
                       name.startswith(spec["path"] + "/") for spec in files.values()):
                raise ValueError(f"Undeclared package resource: {name}")
            content = base64.b64decode(encoded, validate=True)
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)

    return cached_resources("packages", recipe, build)
