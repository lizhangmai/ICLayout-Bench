"""Declarative, pinned PDK snapshots for the ordinary Agent resource mount."""

import hashlib
import json
import os
import posixpath
import re
import subprocess
import tomllib
from pathlib import Path

from benchmarking.bundles import load_bundle, publish_bundle
from benchmarking.files import Asset, keys, read_file, relative

from .preparation import source_path

DESCRIPTOR = "pdk-environment.json"


def agent_spec(manifest):
    data = tomllib.loads(Path(manifest).read_text())
    spec = data.get("agent")
    if spec is None:
        return None
    keys(spec, {"schema_version", "id", "sources", "environment", "checks"},
         {"support_profiles"}, "Agent PDK")
    if type(spec["schema_version"]) is not int or spec["schema_version"] != 1:
        raise ValueError("Unsupported Agent PDK schema_version")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", spec["id"]) or not spec["sources"]:
        raise ValueError("Agent PDK needs an ID and sources")
    for name, source in spec["sources"].items():
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            raise ValueError("Invalid PDK source name")
        if source.get("installation") is True:
            keys(source, {"installation", "include"}, {"exclude", "path"}, "Agent installed PDK")
            if data["source"].get("kind") != "ciel" or not source["include"]:
                raise ValueError("Agent installation needs a ciel source and explicit includes")
        else:
            keys(source, {"checkout"}, {"include", "exclude", "submodules", "path"}, "Agent PDK source")
            relative(source["checkout"], "PDK checkout")
        if "path" in source:
            relative(source["path"], "PDK root")
        for path in source.get("include", []) + source.get("exclude", []) + source.get("submodules", []):
            relative(path, "PDK source selection")
    return spec


def agent_sources(manifest, root):
    from .prepare_support import load_profile

    spec = agent_spec(manifest)
    if spec is None:
        return []
    sources = [(source_path(root, source), source) for source in spec["sources"].values()
               if not source.get("installation")]
    for profile in spec.get("support_profiles", []):
        data = json.loads(load_profile(f"{manifest}#{profile}").content)
        if data["source"].get("kind") != "ciel":
            sources.append((source_path(root, data["source"]), {}))
    return sources


def _git(checkout, *args):
    return subprocess.check_output(["git", "-C", str(checkout), *args])


def _tree(checkout, commit):
    entries = {}
    for record in _git(checkout, "ls-tree", "-rz", commit).split(b"\0"):
        if record:
            header, name = record.split(b"\t", 1)
            mode, kind, digest = header.decode().split()
            entries[name.decode()] = (mode, kind, digest)
    return entries


def _snapshot(checkout, commit, include=(), submodules=(), exclude=()):
    """Check worktree bytes against Git blobs; omit local extras and Git metadata.

    Internal tracked symlinks are flattened into ordinary frozen files. Missing
    files, escaping links, dirty bytes and missing declared dependencies fail
    explicitly rather than introducing host-dependent mounts.
    """
    if not (checkout / ".git").exists():
        raise ValueError(f"Agent PDK preparation requires a complete Git checkout: {checkout}")
    if _git(checkout, "rev-parse", "HEAD").decode().strip() != commit:
        raise ValueError(f"PDK checkout does not match its pinned commit: {checkout}")
    tree = _tree(checkout, commit)
    for prefix in (*include, *exclude):
        if not any(name == prefix or name.startswith(prefix + "/") for name in tree):
            raise ValueError(f"PDK source selection does not exist at its pin: {prefix}")
    files, links, nested = {}, {}, {}
    for name, (mode, kind, digest) in tree.items():
        relative(name, "tracked PDK path")
        if include and not any(name == p or name.startswith(p + "/") for p in include):
            continue
        if any(name == p or name.startswith(p + "/") for p in exclude):
            continue
        path = checkout / name
        if kind == "commit":
            nested[name] = digest
            continue
        if mode == "120000":
            content = os.readlink(path).encode()
            links[name] = content.decode()
        else:
            if path.is_symlink() or path.resolve() != path.absolute():
                raise ValueError(f"Unexpected symlink in PDK checkout: {path}")
            content = path.read_bytes()
            files[name] = Asset(content, "binary")
        actual = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
        if actual != digest:
            raise ValueError(f"PDK content differs from pinned Git blob: {path}")
    for path in submodules:
        if path not in nested:
            raise ValueError(f"Declared PDK dependency is not a pinned gitlink: {path}")
        for name, asset in _snapshot(checkout / path, nested[path]).items():
            files[f"{path}/{name}"] = asset
    pending = dict(links)
    while pending:
        progressed = False
        for name, target in list(pending.items()):
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
            relative(resolved, "PDK symlink target")
            if name == resolved or name.startswith(resolved + "/"):
                raise ValueError(f"PDK source contains a cyclic directory link: {name}")
            matches = {key: asset for key, asset in files.items()
                       if key == resolved or key.startswith(resolved + "/")}
            if matches:
                for key, asset in matches.items():
                    files[name + key[len(resolved):]] = asset
                del pending[name]
                progressed = True
        if not progressed:
            raise ValueError(f"PDK links have missing, excluded or cyclic targets: {sorted(pending)}")
    if not files:
        raise ValueError("PDK source selection is empty")
    return files


def descriptor(resources):
    if DESCRIPTOR not in resources:
        return None
    data = json.loads(resources[DESCRIPTOR].content)
    keys(data, {"schema_version", "id", "environment", "checks", "sources"}, set(), "PDK environment")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("Unsupported PDK environment schema_version")
    for name, value in data["environment"].items():
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name) or not isinstance(value, str) or "\0" in value:
            raise ValueError("Invalid PDK environment setting")
        if name in {"HOME", "PATH", "LD_PRELOAD", "LD_LIBRARY_PATH", "PYTHONHOME"}:
            raise ValueError(f"Reserved PDK environment setting: {name}")
        if name.endswith(("PATH", "ROOT")):
            for path in value.split(":"):
                if not path.startswith("/resources/"):
                    raise ValueError("PDK paths must be inside /resources")
                local = relative(path.removeprefix("/resources/"), "PDK environment path")
                if not any(key == local or key.startswith(local + "/") for key in resources):
                    raise ValueError(f"Missing PDK environment path: {path}")
    if not isinstance(data["checks"], list) or not data["checks"]:
        raise ValueError("PDK environment requires usage checks")
    for command in data["checks"]:
        if not isinstance(command, list) or not command or any(not isinstance(x, str) or not x or "\0" in x for x in command):
            raise ValueError("PDK checks must be argument lists")
    return data


def prepare_agent_resources(manifest, destination, *, root, prepared=None, image="iclayout-bench-tools:local"):
    """Publish one process's sources and derived support via the normal bundle interface."""
    from .prepare_support import load_profile, prepare_support

    spec = agent_spec(manifest)
    if spec is None:
        return None
    manifest, destination, root = Path(manifest).absolute(), Path(destination).absolute(), Path(root).absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"Bundle destination exists: {destination}")
    files, sources = {}, {}
    for name, source in spec["sources"].items():
        if source.get("installation"):
            from .pdk_installation import prepare_installation

            declared = tomllib.loads(manifest.read_text())["source"]
            installed = prepare_installation(declared)
            paths = [path.relative_to(installed).as_posix() for path in installed.rglob("*") if path.is_file()]
            for prefix in source["include"] + source.get("exclude", []):
                if not any(path == prefix or path.startswith(prefix + "/") for path in paths):
                    raise ValueError(f"PDK installation selection does not exist: {prefix}")
            snapshot = {path: Asset(read_file(installed, path), "binary") for path in paths
                        if any(path == p or path.startswith(p + "/") for p in source["include"])
                        and not any(path == p or path.startswith(p + "/") for p in source.get("exclude", []))}
            sources[name] = {**source, "source": declared}
        else:
            checkout = source_path(root, source)
            entry = _tree(root, "HEAD").get(source["checkout"])
            if entry is None or entry[1] != "commit":
                raise ValueError("Agent PDK sources must be pinned repository submodules")
            snapshot = _snapshot(checkout, entry[2], source.get("include", ()),
                                 source.get("submodules", ()), source.get("exclude", ()))
            sources[name] = {**source, "commit": entry[2]}
        for path, asset in snapshot.items():
            if "path" in source:
                path = str(Path(path).relative_to(source["path"]))
            files[f"pdks/{name}/{path}"] = asset
    for profile in spec.get("support_profiles", []):
        relative(profile, "Agent support profile")
        output = (prepared or destination.parent) / profile
        if not output.exists():
            prepare_support(source_path(root, json.loads(load_profile(f"{manifest}#{profile}").content)["source"]),
                f"{manifest}#{profile}", output, compiler_image=image)
        bundle = load_bundle(output)
        expected = load_profile(f"{manifest}#{profile}")
        if dict(bundle.files).get("preparation.json") != expected:
            raise ValueError(f"Prepared Agent support does not match its declared profile: {profile}")
        files[f"metadata/{profile}-preparation.json"] = bundle.manifest
        generated = json.loads(expected.content).get("generated", {})
        for name, asset in bundle.files:
            if name in generated:
                asset = Asset(asset.content.replace(b"/workspace/support", f"/resources/support/{profile}".encode()), asset.format)
            files[f"support/{profile}/{name}"] = asset
    files["pdk-check.py"] = Asset(Path(__file__).with_name("pdk_probe.py").read_bytes(), "python")
    info = {"schema_version": 1, "id": spec["id"], "environment": spec["environment"],
            "checks": spec["checks"], "sources": sources}
    files[DESCRIPTOR] = Asset(json.dumps(info, sort_keys=True).encode(), "json")
    descriptor(files)
    return publish_bundle(files, {"kind": "pdk-sources", "id": spec["id"], "sources": sources,
                                  "generated_path_relocation": "/workspace/support -> /resources/support/<profile>"}, destination)
