"""Prepare the reviewed PDK view, optionally packaged as generic Agent resources."""

import argparse
import tomllib
from pathlib import Path

from benchmarking.bundles import load_bundle

from .pdk_installation import prepare_installation
from .resource_cache import bind_resources, cached_resources


def prepare_pdk(pdk_manifest: Path, destination: Path) -> str:
    """Bind the complete SG13G2 installation for standalone device checks."""
    config = tomllib.loads(pdk_manifest.read_text())
    source = prepare_installation(config["source"])
    pdk_root = source / "ihp-sg13g2"
    recipe = {"kind": "reviewed-pdk-view", "source": config["source"], "root": str(pdk_root)}

    def build(stage):
        return {"ihp-sg13g2": str(pdk_root)}

    shared = cached_resources("views", recipe, build)
    bind_resources(shared, destination)
    return load_bundle(destination).manifest.sha256


def prepare_pdk_bundle(pdk_manifest: Path, destination: Path):
    prepare_pdk(pdk_manifest, destination)
    return load_bundle(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="SG13G2 pdk.toml selecting the pinned ciel installation")
    parser.add_argument("destination", type=Path, help="New directory for the PDK view")
    parser.add_argument("--bundle", action="store_true", help="Publish generic resources for offline CLI sessions")
    args = parser.parse_args()
    if args.bundle:
        print(prepare_pdk_bundle(args.manifest, args.destination).manifest.sha256)
    else:
        print(prepare_pdk(args.manifest, args.destination))
