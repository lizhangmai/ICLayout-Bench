"""Read declared native resources from a pinned distribution in the tools image."""

import base64
import importlib.metadata
import json
from pathlib import Path, PurePosixPath


def collect(config):
    distribution = importlib.metadata.distribution(config["distribution"])
    if distribution.version != config["version"]:
        raise ValueError(f"Expected {config['distribution']}=={config['version']}, found {distribution.version}")
    installed = {str(path): path for path in distribution.files or ()}
    selected = {}
    for spec in config["files"].values():
        name = spec["path"]
        path = PurePosixPath(name)
        if path.is_absolute() or str(path) != name or ".." in path.parts:
            raise ValueError(f"Invalid package resource path: {name}")
        matches = [p for p in installed if p == name or
                   spec["format"] == "directory" and p.startswith(name + "/")]
        if not matches:
            raise ValueError(f"Distribution has no declared resource: {name}")
        for member in matches:
            source = Path(distribution.locate_file(installed[member]))
            if source.is_symlink() or not source.is_file():
                raise ValueError(f"Package resource is not a regular file: {member}")
            selected[member] = base64.b64encode(source.read_bytes()).decode("ascii")
    return {"files": selected}


if __name__ == "__main__":
    config = json.loads(Path("package.json").read_text())
    Path("resources.json").write_text(json.dumps(collect(config), sort_keys=True))
