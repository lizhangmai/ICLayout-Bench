"""Resolve independently published task data through the Hugging Face cache."""

import os
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .files import Asset, read_file, relative


@dataclass(frozen=True)
class Dataset:
    root: Path
    identity: dict

    def cases(self):
        result = {}
        for config in sorted((self.root / "tasks").glob("*/*/cases/*/case.toml")):
            name = tomllib.loads(read_file(config.parent, config.name).decode())["id"]
            dataset_root(config)
            if name in result:
                raise ValueError(f"Duplicate dataset case: {name}")
            result[name] = config
        if not result:
            raise ValueError(f"Dataset has no published cases: {self.root}")
        return result

    def native_cases(self, name="core", split="test"):
        """Load real HF rows and bind their paths to verified evaluation contracts."""
        from datasets import DownloadConfig, load_dataset_builder
        from datasets import load_dataset as hf_load_dataset

        if name not in {"all", "core"}:
            raise ValueError("Dataset selection name must be all or core")
        download = DownloadConfig(local_files_only=True)
        builder = load_dataset_builder(str(self.root), download_config=download)
        # Explicit resolved files bind HF's cache to this snapshot and file metadata;
        # a card's preconfigured name alone can reuse tables from another checkout.
        rows = hf_load_dataset(str(self.root), split=split,
                               data_files=builder.config.data_files, download_config=download)
        cases = {}
        for row in rows:
            case_id = row["id"]
            if case_id in cases:
                raise ValueError(f"Duplicate Dataset row: {case_id}")
            path = relative(row["case_path"], "case path")
            config = self.root / path
            raw = read_file(self.root, path)
            case = tomllib.loads(raw.decode())
            if type(row["in_core"]) is not bool or row["in_core"] != core_membership(case):
                raise ValueError(f"Dataset index has stale core membership: {case_id}")
            if Asset(raw, "toml").sha256 != row["case_sha256"]:
                raise ValueError(f"Dataset index has a stale case digest: {case_id}")
            if tomllib.loads(raw.decode())["id"] != case_id:
                raise ValueError(f"Dataset row and case identity disagree: {case_id}")
            pdk_path = relative(row["pdk_path"], "PDK path")
            if (self.root / pdk_path != process_manifest(config)
                    or Asset(read_file(self.root, pdk_path), "toml").sha256 != row["pdk_sha256"]):
                raise ValueError(f"Dataset index has a stale PDK binding: {case_id}")
            cases[case_id] = config
        if name == "core":
            rows = rows.filter(lambda row: row["in_core"])
            cases = {row["id"]: cases[row["id"]] for row in rows}
        if not cases:
            raise ValueError("Dataset selection is empty")
        return rows, cases

    def case(self, name):
        cases = self.cases()
        if name in cases:
            return cases[name]
        matches = [p for p in cases.values() if p.parent.name == name]
        if len(matches) != 1:
            raise ValueError(f"Unknown or ambiguous dataset case: {name}; use its full ID")
        return matches[0]


def dataset_root(config):
    """Locate the Dataset root from its process/collection/case hierarchy."""
    config = Path(config).absolute()
    if (len(config.parents) < 6 or config.name != "case.toml"
            or config.parents[1].name != "cases" or config.parents[4].name != "tasks"):
        raise ValueError("Expected Dataset tasks/<pdk>/<collection>/cases/<case>/case.toml")
    return config.parents[5]


def case_location(config):
    """Read process and collection from their authoritative directory hierarchy."""
    config = Path(config).absolute()
    dataset_root(config)
    return {"process": config.parents[3].name, "collection": config.parents[2].name}


def process_manifest(config):
    """Resolve the process declaration for a case's PDK directory."""
    config = Path(config).absolute()
    process = case_location(config)["process"]
    return dataset_root(config) / "tasks" / process / "pdk.toml"


def load_dataset(source=None, *, revision=None, local_files_only=False, include_reference=False):
    """Use an HF snapshot or an explicitly supplied local Dataset working copy."""
    source = source or os.environ.get("ICLAYOUT_BENCH_DATASET")
    if not source:
        raise ValueError("Specify a Dataset repo ID or local Dataset directory")
    local = Path(source).expanduser()
    if local.is_dir():
        if revision is not None:
            raise ValueError("Local Dataset directories select their current files; omit revision")
        root = local.resolve()
        result = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                                capture_output=True, text=True, check=False)
        commit = result.stdout.strip() if result.returncode == 0 else None
        return Dataset(root, {"source": str(root), "commit": commit})
    from huggingface_hub import snapshot_download

    root = Path(snapshot_download(
        repo_id=str(source), repo_type="dataset", revision=revision,
        local_files_only=local_files_only,
        ignore_patterns=None if include_reference else ["*/reference/*", "*/validation/*"],
    ))
    return Dataset(root, {"source": str(source), "commit": root.name})


def core_membership(case):
    """Read published selection metadata and validate eligibility against its contract."""
    selected = case.get("in_core")
    if type(selected) is not bool:
        raise ValueError("Published case.in_core must be boolean")
    if selected:
        evaluation = case.get("task", {}).get("evaluation", {})
        if (case.get("status") != "qualified" or evaluation.get("mode") != "post_layout"
                or evaluation.get("scoring", {}).get("method") != "layout"):
            raise ValueError("Core case must be qualified with scored post_layout evaluation")
    return selected
