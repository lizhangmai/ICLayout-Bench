"""Prepare reviewed tool support; optionally compile Verilog-A with OpenVAF."""

import argparse
import json
import tomllib
from pathlib import Path

from benchmarking.bundles import publish_bundle
from benchmarking.files import Asset, ReadOnlyMount, keys, read_file

from .docker import DockerTool
from .resource_cache import bind_resources, cached_resources


def load_profile(spec: str) -> Asset:
    """Resolve a manifest#profile reference to its canonical JSON bytes."""
    path, sep, name = spec.partition("#")
    if not sep or not name:
        raise ValueError(f"Support profile must name a manifest profile: {spec}#<name>")
    path = Path(path).absolute()
    manifest = tomllib.loads(read_file(path.parent, path.name).decode())
    keys(manifest, {"source", "profiles"}, {"agent", "notices"}, "support manifest")
    if name not in manifest["profiles"]:
        raise ValueError(f"Unknown support profile: {name}")
    profile = manifest["profiles"][name]
    if not isinstance(profile, dict):
        raise TypeError(f"Support profile must be a table: {name}")
    data = {"source": manifest["source"], **profile}
    return Asset((json.dumps(data, indent=2, sort_keys=True) + "\n").encode(), "json")


def prepare_support(source: Path | None, profile: str, destination: Path, *,
                    compiler_image: str = "iclayout-bench-tools:local") -> str:
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"Support destination exists: {destination}")
    shared = prepare_support_cache(source, profile, compiler_image=compiler_image,
                                   diagnostics=destination.with_name(destination.name + ".failed"))
    bind_resources(shared, destination)
    from benchmarking.bundles import load_bundle

    return load_bundle(shared).manifest.sha256


def prepare_support_cache(source: Path | None, profile: str, *,
                          compiler_image: str = "iclayout-bench-tools:local",
                          diagnostics: Path) -> Path:
    """Return shared runtime resources without creating a per-case binding directory."""
    raw = load_profile(profile)
    data = json.loads(raw.content)
    if data["source"].get("kind") == "ciel":
        from .pdk_installation import prepare_installation

        source = prepare_installation(data["source"])
    else:
        source = source.absolute()
    builds = data.get("compile", [])
    compiler = DockerTool(compiler_image, ["openvaf", "--version"], 180) if builds else None
    recipe = {"profile": data, "source_root": str(source)}
    if compiler:
        recipe["compiler"] = compiler.identity

    def build(stage):
        compile_inputs, mounts = {}, {}
        for name, spec in (data.get("files", {}) | data.get("compile_files", {})).items():
            if not spec.get("replace"):
                if name in data.get("compile_files", {}):
                    compile_inputs[name] = ReadOnlyMount(source / spec["path"], raw)
                else:
                    mounts[name] = str(source / spec["path"])
                continue
            asset = Asset((source / spec["path"]).read_bytes(), spec["format"])
            for edit in spec.get("replace", []):
                old, new = edit["old"].encode(), edit["new"].encode()
                if not old or asset.content.count(old) != 1:
                    raise ValueError(f"Support replacement must match exactly once: {spec['path']}")
                asset = Asset(asset.content.replace(old, new), asset.format)
            if name in data.get("compile_files", {}):
                compile_inputs[name] = asset
                continue
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(asset.content)
        for name, spec in data.get("generated", {}).items():
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(spec["content"])
        for job in builds:
            command = ["openvaf", "--target_cpu", "generic", *[f"-D{x}" for x in job["defines"]],
                       "-o", "compiled.osdi", job["source"]]
            result = compiler.run(command, compile_inputs, {"compiled.osdi": "osdi"})
            if result.reason or result.returncode != 0:
                publish_bundle({"profile.json": raw, **{f"logs/{k}": a for k, a in result.evidence.items()}},
                               {"compiler": compiler.identity, "reason": result.reason}, diagnostics)
                raise ValueError(f"OpenVAF compilation failed; diagnostics: {diagnostics}")
            target = stage / job["output"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(result.files["compiled.osdi"].content)

        return mounts

    return cached_resources("profiles", recipe, build)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, nargs="?", help="Checkout source; omitted for ciel profiles")
    parser.add_argument("profile", help="Manifest profile reference, e.g. tasks/ihp-sg13g2/pdk.toml#klayout")
    parser.add_argument("destination", type=Path)
    parser.add_argument("--compiler-image", default="iclayout-bench-tools:local")
    args = parser.parse_args()
    print(prepare_support(args.source, args.profile, args.destination, compiler_image=args.compiler_image))
