"""Generate a native Hugging Face table from authoritative Dataset contracts."""

import argparse
import json
import tomllib
from pathlib import Path

import yaml

from .dataset import Dataset, case_location, core_membership, process_manifest
from .files import Asset, atomic_write, read_file, relative


def _input_path(root, config, inputs, role):
    entry = inputs.get(role)
    if entry is None:
        return None
    base = config.parent
    source = entry.get("source", entry["path"])
    source = relative(source, "input source")
    content = read_file(base, source)
    if Asset(content, entry["format"]).sha256 != entry["sha256"]:
        raise ValueError(f"Dataset input digest mismatch: {config}/{role}")
    return (base / source).relative_to(root).as_posix()


def index_files(root):
    """Return the deterministic JSONL view; the evaluation contracts remain in TOML."""
    root = Path(root).resolve()
    rows = {}
    for name, config in sorted(Dataset(root, {}).cases().items()):
        raw = read_file(config.parent, config.name)
        case = tomllib.loads(raw.decode())
        if case["id"] != name:
            raise ValueError(f"Catalog and case identity disagree: {name}")
        path = config.relative_to(root)
        location = case_location(config)
        pdk = process_manifest(config)
        license_path = root / "tasks" / location["process"] / location["collection"] / "LICENSE"
        read_file(license_path.parent, license_path.name)
        task = case.get("task", {})
        inputs = task.get("inputs", {})

        description_path = _input_path(root, config, inputs, "description")
        rows[name] = {
            "id": name, "in_core": core_membership(case), "title": case["title"], "pdk": location["process"],
            "category": case.get("presentation", {}).get("category"),
            "summary": case.get("presentation", {}).get("summary"),
            "source_url": case["origin"]["url"], "status": case["status"],
            "collection": location["collection"], "task_kind": task.get("kind"),
            "problem": read_file(root, description_path).decode(),
            "case_path": path.as_posix(), "case_sha256": Asset(raw, "toml").sha256,
            "pdk_path": pdk.relative_to(root).as_posix(),
            "pdk_sha256": Asset(read_file(pdk.parent, pdk.name), "toml").sha256,
            "description_path": description_path,
            "netlist_path": _input_path(root, config, inputs, "netlist"),
            "netlist_sha256": inputs.get("netlist", {}).get("sha256"),
            "license_path": license_path.relative_to(root).as_posix(),
        }
    return {"data.jsonl": "".join(
        json.dumps(row, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n"
        for row in rows.values()).encode()}


def sync_index(root, *, check=False):
    """Write the generated table, or fail read-only verification when they have drifted."""
    root = Path(root).resolve()
    files = index_files(root)
    card = read_file(root, "README.md").decode().split("---", 2)
    metadata = yaml.safe_load(card[1]) if len(card) == 3 and not card[0].strip() else {}
    expected = [{"config_name": "default",
                 "data_files": [{"split": "test", "path": "data.jsonl"}]}]
    if not isinstance(metadata, dict) or metadata.get("configs") != expected:
        raise ValueError("Dataset Card must declare one default test table at data.jsonl; see the Dataset README")
    stale = [name for name, raw in files.items()
             if not (root / name).is_file() or read_file(root, name) != raw]
    if check and stale:
        raise ValueError("Generated Dataset index is stale: " + ", ".join(stale))
    for name in stale:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(target, files[name], mode=0o644)
    return {name: len(raw.splitlines()) for name, raw in files.items()}


def publication_files(root):
    """List the static release files, excluding maintenance and undeclared assets."""
    root = Path(root).resolve()
    sync_index(root, check=True)
    files = {"README.md", "LICENSE",
             "data.jsonl"}
    for config in Dataset(root, {}).cases().values():
        case = tomllib.loads(read_file(config.parent, config.name).decode())
        base = config.parent.relative_to(root)
        files.add((base / config.name).as_posix())
        for entry in case.get("task", {}).get("inputs", {}).values():
            path = base / relative(entry.get("source", entry["path"]), "input source")
            if Asset(read_file(root, path.as_posix()), entry["format"]).sha256 != entry["sha256"]:
                raise ValueError(f"Publication input digest mismatch: {path}")
            files.add(path.as_posix())
        for asset in case.get("assets", []):
            path = base / relative(asset["path"], "asset path")
            if Asset(read_file(root, path.as_posix()), asset["format"]).sha256 != asset["sha256"]:
                raise ValueError(f"Publication asset digest mismatch: {path}")
            files.add(path.as_posix())
        process = process_manifest(config).parent
        files.add((process / "pdk.toml").relative_to(root).as_posix())
        collection = config.parents[2]
        files.add((collection / "LICENSE").relative_to(root).as_posix())
        for optional in (process / "README.md", collection / "NOTICE"):
            if optional.is_file():
                files.add(optional.relative_to(root).as_posix())
    for name in files:
        read_file(root, name)
    return sorted(files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True, help="Local Dataset working copy")
    parser.add_argument("--check", action="store_true", help="Verify the generated table without changing files")
    parser.add_argument("--publication-files", action="store_true", help="Print a verified JSON allowlist for publication")
    args = parser.parse_args()
    try:
        result = (publication_files(args.dataset) if args.publication_files
                  else sync_index(args.dataset, check=args.check))
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, KeyError) as error:
        parser.exit(2, f"Dataset index failed: {error}\n")


if __name__ == "__main__":
    main()
