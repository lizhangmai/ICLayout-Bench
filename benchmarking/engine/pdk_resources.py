"""Bind the selected PDK installation and derived support into Agent containers."""

import json
import re
import subprocess
import tomllib
from pathlib import Path

from benchmarking.bundles import load_bundle
from benchmarking.files import Asset, ReadOnlyMount, keys, relative

from .preparation import source_path
from .resource_cache import bind_resources, cached_resources

DESCRIPTOR = "pdk-environment.json"


def agent_spec(manifest):
    data = tomllib.loads(Path(manifest).read_text())
    spec = data.get("agent")
    if spec is None:
        return None
    keys(spec, {"id", "sources", "environment", "checks"},
         {"support_profiles"}, "Agent PDK")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", spec["id"]) or not spec["sources"]:
        raise ValueError("Agent PDK needs an ID and sources")
    for name, source in spec["sources"].items():
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            raise ValueError("Invalid PDK source name")
        keys(source, set(), {"installation", "repository", "commit", "path"}, "Agent PDK root")
        if "path" in source:
            relative(source["path"], "PDK root")
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


def descriptor(resources):
    if DESCRIPTOR not in resources:
        return None
    data = json.loads(resources[DESCRIPTOR].content)
    keys(data, {"id", "environment", "checks", "sources"}, set(), "PDK environment")
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
                if not any(key == local or key.startswith(local + "/")
                           or (isinstance(value, ReadOnlyMount) and value.path.is_dir()
                               and local.startswith(key + "/"))
                           for key, value in resources.items()):
                    raise ValueError(f"Missing PDK environment path: {path}")
    if not isinstance(data["checks"], list) or not data["checks"]:
        raise ValueError("PDK environment requires usage checks")
    for command in data["checks"]:
        if not isinstance(command, list) or not command or any(not isinstance(x, str) or not x or "\0" in x for x in command):
            raise ValueError("PDK checks must be argument lists")
    return data


def prepare_agent_resources(manifest, destination, *, root, image="iclayout-bench-tools:local"):
    """Publish a standalone binding to the Agent resource cache."""
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"Bundle destination exists: {destination}")
    shared = prepare_agent_cache(manifest, root=root, image=image,
                                diagnostics=destination.with_name(destination.name + ".failed"))
    if shared is None:
        return None
    bind_resources(shared, destination)
    return load_bundle(shared)


def prepare_agent_cache(manifest, *, root, profiles=None, image="iclayout-bench-tools:local",
                       diagnostics):
    """Compose Agent mounts from explicitly selected shared profile paths."""
    from .prepare_support import load_profile, prepare_support_cache

    spec = agent_spec(manifest)
    if spec is None:
        return None
    manifest, root = Path(manifest).absolute(), Path(root).absolute()
    selected = profiles
    sources, locations, profiles = {}, {}, {}
    for name, source in spec["sources"].items():
        if source.get("installation"):
            from .pdk_installation import prepare_installation

            declared = tomllib.loads(manifest.read_text())["source"]
            locations[name] = prepare_installation(declared)
            sources[name] = {**source, "source": declared}
        else:
            locations[name] = source_path(root, source)
            commit = subprocess.check_output(["git", "-C", str(locations[name]),
                                              "rev-parse", "HEAD"], text=True).strip()
            sources[name] = {**source, "commit": commit}
        locations[name] = locations[name] / source.get("path", "")
    selected_profiles = spec.get("support_profiles", []) if selected is None else sorted(selected)
    checks = list(spec["checks"])
    for profile in selected_profiles:
        profile_data = json.loads(load_profile(f"{manifest}#{profile}").content)
        if "check" in profile_data:
            checks.append(profile_data["check"])
        output = selected[profile] if selected is not None else prepare_support_cache(
            source_path(root, profile_data["source"]), f"{manifest}#{profile}",
            compiler_image=image, diagnostics=Path(diagnostics) / profile)
        profiles[profile] = load_bundle(Path(output))
    probe = Path(__file__).with_name("pdk_probe.py")
    needs_probe = any("/resources/pdk-check.py" in command for command in checks)
    info = {"id": spec["id"], "environment": spec["environment"], "checks": checks, "sources": sources}
    recipe = {"kind": "pdk-mounts", **info, "roots": {k: str(v) for k, v in locations.items()},
              "profiles": {k: v.manifest.sha256 for k, v in profiles.items()},
              "probe": Asset(probe.read_bytes(), "python").sha256 if needs_probe else None}

    def build(stage):
        mounts = {f"pdks/{name}": str(path) for name, path in locations.items()}
        for profile, bundle in profiles.items():
            generated = json.loads(bundle.manifest.content)["provenance"]["profile"].get("generated", {})
            for name, asset in bundle.files:
                target = stage / "support" / profile / name
                relocated = (asset.content.replace(b"/workspace/support", f"/resources/support/{profile}".encode())
                             if name in generated else None)
                if relocated is not None and relocated != asset.content:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(relocated)
                else:
                    mounts[f"support/{profile}/{name}"] = str(asset.path)
        if needs_probe:
            (stage / "pdk-check.py").write_bytes(probe.read_bytes())
        (stage / DESCRIPTOR).write_text(json.dumps(info, sort_keys=True))
        return mounts

    return cached_resources("agents", recipe, build)
