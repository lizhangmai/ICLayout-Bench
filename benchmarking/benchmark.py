"""Versioned case selection, independent of models and execution resources."""

import json
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .evaluation import identifier
from .files import Asset, keys, read_file, relative, text
from .tasks import load_task


def parse_benchmark(source):
    data = tomllib.loads(source.content.decode())
    keys(data, {"schema_version", "id", "version", "cases"}, set(), "benchmark")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("Unsupported benchmark schema_version")
    identifier(data["id"])
    text(data["version"], "benchmark version")
    if not isinstance(data["cases"], list) or not data["cases"]:
        raise ValueError("Benchmark requires a nonempty case list")
    for name in data["cases"]:
        text(name, "case id")
    if len(set(data["cases"])) != len(data["cases"]):
        raise ValueError("Duplicate benchmark case id")
    return data


def contract_digest(description, inputs):
    """Compare canonical and prepared tasks without host tool paths or references."""
    value = {key: description[key] for key in
             ("id", "title", "family", "coefficient", "environment", "netlist_subcircuit", "output")}
    value["input_paths"] = description["inputs"]
    value["inputs"] = {role: {key: ref[key] for key in ("sha256", "format", "bytes")}
                       for role, ref in inputs.items()}
    return Asset(json.dumps(value, sort_keys=True).encode(), "json").sha256


def task_contract(task):
    return contract_digest(task.description(), {role: asset.identity() for role, asset in task.input_assets().items()})


@dataclass(frozen=True)
class Benchmark:
    id: str
    version: str
    source: Asset
    configs: tuple[Path, ...]
    contracts: dict[str, str]

    def description(self):
        return {"id": self.id, "version": self.version, "sha256": self.source.sha256,
                "cases": list(self.contracts)}

    def validate_tasks(self, tasks):
        if len(tasks) != len(self.contracts) or {task.id for task in tasks} != set(self.contracts):
            raise ValueError("Run tasks must exactly match the benchmark case set")
        for task in tasks:
            if task.status != "qualified" or task_contract(task) != self.contracts[task.id]:
                raise ValueError(f"Run task differs from the qualified benchmark contract: {task.id}")


def load_benchmark(path):
    """Resolve full IDs only through catalogs under the definition's sibling tasks/."""
    path = Path(os.path.abspath(path))
    source = Asset(read_file(path.parent, path.name), "toml")
    data = parse_benchmark(source)
    registry = {}
    for catalog in sorted((path.parent / "tasks").glob("*/*/catalog.toml")):
        entries = tomllib.loads(read_file(catalog.parent, catalog.name).decode())
        keys(entries, {"schema_version", "cases"}, set(), "catalog")
        if type(entries["schema_version"]) is not int or entries["schema_version"] != 3:
            raise ValueError("Unsupported catalog schema_version")
        for entry in entries["cases"]:
            keys(entry, {"id", "config_path"}, set(), "catalog case")
            text(entry["id"], "catalog case id")
            if entry["id"] in registry:
                raise ValueError("Duplicate case id across catalogs")
            registry[entry["id"]] = catalog.parent / relative(entry["config_path"], "case config_path")
    configs, contracts = [], {}
    for name in data["cases"]:
        if name not in registry:
            raise ValueError(f"Unknown benchmark case id: {name}")
        config = registry[name]
        task = load_task(config)
        if task.id != name:
            raise ValueError("Catalog and benchmark case identity disagree")
        if (task.status != "qualified" or task.evaluation is None
                or task.evaluation.mode != "post_layout" or task.evaluation.scoring is None
                or task.evaluation.scoring.method not in {"layout-v1", "layout-v2"}):
            raise ValueError(f"Benchmark case must be qualified with scored post_layout evaluation: {name}")
        configs.append(config)
        contracts[name] = task_contract(task)
    return Benchmark(data["id"], data["version"], source, tuple(configs), contracts)


def score_binding(benchmark):
    """Small definition identity included in the existing score-suite digest."""
    return {"id": benchmark["id"], "version": benchmark["version"],
            "sha256": benchmark["source"]["sha256"]}
