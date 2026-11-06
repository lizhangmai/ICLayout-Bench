"""Bind the selected PDK installation and derived support into Agent containers."""

import json
import re
import subprocess
import tomllib
from pathlib import Path

from benchmarking.eda.images import tool_image
from benchmarking.eda.resources.cache import bind_resources, cached_resources
from benchmarking.eda.resources.installation import installation_path
from benchmarking.eda.resources.support import load_profile, prepare_support_cache
from benchmarking.evidence.bundles import load_bundle
from benchmarking.evidence.identity import package_source
from benchmarking.execution.workspace.environment import DESCRIPTOR
from benchmarking.files import Asset, keys, read_file, relative


def agent_spec(manifest):
    data = tomllib.loads(Path(manifest).read_text())
    spec = data.get("agent")
    if spec is None:
        return None
    keys(spec, {"id", "sources", "environment", "checks"},
         {"support_profiles", "local_files"}, "Agent PDK")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", spec["id"]) or not spec["sources"]:
        raise ValueError("Agent PDK needs an ID and sources")
    for target, local in spec.get('local_files', {}).items():
        relative(target, 'Agent resource target')
        if target.split('/')[0] in {'pdks', 'support', DESCRIPTOR, 'pdk-check.py'}:
            raise ValueError('Agent local files must not replace PDK, support or environment resources')
        keys(local, {'path', 'format'}, set(), 'Agent local file')
        relative(local['path'], 'manifest Agent file')
    for name, source in spec["sources"].items():
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            raise ValueError("Invalid PDK source name")
        keys(source, set(), {"installation", "repository", "commit", "path", "paths"}, "Agent PDK root")
        if "path" in source:
            relative(source["path"], "PDK root")
        if "paths" in source:
            paths = source["paths"]
            if not isinstance(paths, list) or not paths:
                raise ValueError("Agent PDK paths must be a nonempty list")
            for path in paths:
                relative(path, "Agent PDK selected path")
            if len(set(paths)) != len(paths) or any(
                a.startswith(b + "/") for a in paths for b in paths if a != b
            ):
                raise ValueError("Agent PDK paths must not overlap")
    return spec


def prepare_agent_resources(manifest, destination, *, image=None):
    """Publish a standalone binding to the Agent resource cache."""
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"Bundle destination exists: {destination}")
    shared = prepare_agent_cache(manifest, image=image,
                                diagnostics=destination.with_name(destination.name + ".failed"))
    if shared is None:
        return None
    bind_resources(shared, destination)
    return load_bundle(shared)


def prepare_agent_cache(manifest, *, profiles=None, image=None,
                       diagnostics):
    """Compose Agent mounts from explicitly selected shared profile paths."""
    spec = agent_spec(manifest)
    if spec is None:
        return None
    image = tool_image(image)
    manifest = Path(manifest).absolute()
    selected = profiles
    sources, locations, profiles = {}, {}, {}
    for name, source in spec["sources"].items():
        if source.get("installation"):
            from benchmarking.eda.resources.installation import prepare_installation

            declared = tomllib.loads(manifest.read_text())["source"]
            locations[name] = prepare_installation(declared)
            sources[name] = {**source, "source": declared}
        else:
            locations[name] = installation_path(source)
            commit = subprocess.check_output(["git", "-C", str(locations[name]),
                                              "rev-parse", "HEAD"], text=True).strip()
            sources[name] = {**source, "commit": commit}
        locations[name] = locations[name] / source.get("path", "")
    selected_profiles = spec.get("support_profiles", []) if selected is None else sorted(selected)
    checks = list(spec["checks"])
    local_files = {name: read_file(manifest.parent, local['path'])
                   for name, local in spec.get('local_files', {}).items()}
    for profile in selected_profiles:
        profile_data = json.loads(load_profile(f"{manifest}#{profile}").content)
        if "check" in profile_data:
            checks.append(profile_data["check"])
        output = selected[profile] if selected is not None else prepare_support_cache(
            installation_path(profile_data["source"]), f"{manifest}#{profile}",
            compiler_image=image, diagnostics=Path(diagnostics) / profile)
        profiles[profile] = load_bundle(Path(output))
    probe = package_source("eda/_scripts/pdk_probe.py")
    needs_probe = any("/resources/pdk-check.py" in command for command in checks)
    info = {"id": spec["id"], "environment": spec["environment"], "checks": checks, "sources": sources}
    recipe = {"kind": "pdk-mounts", **info, "roots": {k: str(v) for k, v in locations.items()},
              "profiles": {k: v.manifest.sha256 for k, v in profiles.items()},
              "probe": Asset(probe.read_bytes(), "python").sha256 if needs_probe else None}
    if local_files:
        recipe['local_files_sha256'] = {name: Asset(content, 'binary').sha256 for name, content in local_files.items()}

    def build(stage):
        mounts = {}
        for name, root in locations.items():
            for selected_path in spec["sources"][name].get("paths", [""]):
                path = root / selected_path
                if not path.resolve(strict=True).is_relative_to(root.resolve(strict=True)):
                    raise ValueError("Agent PDK selected path escapes its root")
                target = f"pdks/{name}" + (f"/{selected_path}" if selected_path else "")
                mounts[target] = str(path)
        for profile, bundle in profiles.items():
            profile_data = json.loads(bundle.manifest.content)["provenance"]["profile"]
            owned = profile_data.get("generated", {}).keys() | profile_data.get("local_files", {}).keys()
            for name, asset in bundle.files:
                target = stage / "support" / profile / name
                relocated = (asset.content.replace(b"/workspace/support", f"/resources/support/{profile}".encode())
                             if name in owned else None)
                if relocated is not None and relocated != asset.content:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(relocated)
                else:
                    mounts[f"support/{profile}/{name}"] = str(asset.path)
        if needs_probe:
            (stage / "pdk-check.py").write_bytes(probe.read_bytes())
        for name, content in local_files.items():
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        (stage / DESCRIPTOR).write_text(json.dumps(info, sort_keys=True))
        return mounts

    return cached_resources("agents", recipe, build)
