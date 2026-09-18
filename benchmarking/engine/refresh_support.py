"""Refresh support file digests from a pinned checkout or verified ciel cache."""

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path

import tomli_w

from benchmarking.files import Asset, keys, read_file


def _git(source: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(source), *args], text=True).strip()


def refresh(source: Path | None, manifest: Path, profile: str | None = None) -> dict:
    """Rewrite the manifest's commit and file digests from the checkout; return the changes."""
    manifest = manifest.absolute()
    data = tomllib.loads(manifest.read_bytes().decode())
    keys(data, {"schema_version", "source", "profiles"}, {"agent", "notices"}, "support manifest")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("Unsupported support manifest schema_version")
    if profile is not None and profile not in data["profiles"]:
        raise ValueError(f"Unknown support profile: {profile}")
    if data["source"].get("kind") == "ciel":
        from .pdk_installation import prepare_installation

        source = prepare_installation(data["source"])
        previous = commit = data["source"]["version"]
    else:
        if source is None:
            raise ValueError("A checkout source is required for this manifest")
        source = source.absolute()
        commit = _git(source, "rev-parse", "HEAD")
        dirty = _git(source, "status", "--porcelain", "--untracked-files=no")
        if dirty:
            raise ValueError(f"Upstream checkout has uncommitted changes:\n{dirty}")
        previous = data["source"].get("commit")
        data["source"]["commit"] = commit
    updated = []
    names = [profile] if profile else list(data["profiles"])
    for name in names:
        for file, spec in data["profiles"][name]["files"].items():
            keys(spec, {"path", "sha256", "format"}, {"replace"}, "support source")
            asset = Asset(read_file(source, spec["path"]), spec["format"])
            if asset.sha256 != spec["sha256"]:
                spec["sha256"] = asset.sha256
                updated.append(f"{name}:{file}")
    manifest.write_text(tomli_w.dumps(data, multiline_strings=True))
    return {"commit": (previous, commit), "digests": updated}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, nargs="?", help="Pinned checkout; omitted for a ciel manifest")
    parser.add_argument("manifests", type=str, nargs="+",
                        help="Manifest path, optionally with #profile to refresh one profile")
    args = parser.parse_args()
    try:
        for spec in args.manifests:
            path, _, name = spec.partition("#")
            changes = refresh(args.source, Path(path), name or None)
            old, new = (value[:12] if value else "none" for value in changes["commit"])
            print(f"{spec}: commit {old} -> {new}, {len(changes['digests'])} digests refreshed")
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
        print(f"Support refresh error: {error}", file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
