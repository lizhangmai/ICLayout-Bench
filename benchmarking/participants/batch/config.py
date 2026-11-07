"""Resolve experiment conditions without persisting provider credentials."""

import hashlib
import json
import os
import re
import tomllib
from pathlib import Path

from benchmarking.participants.harnesses import registry as adapters
from benchmarking.participants.harnesses.contracts import EFFORTS, HARNESSES
from benchmarking.results.usage import validate_pricing

FIELDS = {"name", "harness", "harness_home", "model", "effort", "tasks", "dataset", "concurrency", "repetitions", "recovery", "results_data", "archive_objects", "scheme", "pricing"}
INPUT_FIELDS = FIELDS | {"pricing_file"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def clean_env():
    return {k: v for k, v in os.environ.items()
            if not k.startswith(("ICLAYOUT_BENCH_", "LAYOUT_BENCH_")) and k != "PYTHONPATH"}


def resolve(harness, model=None, effort=None, *, harness_home=None):
    if harness not in HARNESSES:
        raise ValueError("Unknown harness")
    return adapters.resolve(harness, model, effort, clean_env(),
                            **({"home": Path(harness_home)} if harness_home is not None else {}))


def validate(row):
    if set(row) - FIELDS:
        raise ValueError("Unknown experiment fields: " + ", ".join(sorted(set(row) - FIELDS)))
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", row.get("name", "")):
        raise ValueError("Experiment name must be a short path-safe identifier")
    if row.get("harness") not in HARNESSES:
        raise ValueError("Each experiment needs a supported harness")
    if "harness_home" in row:
        if adapters.get(row["harness"]).METADATA.configuration_file is None:
            raise ValueError("This harness does not have a native configuration home")
        home = row["harness_home"]
        if not isinstance(home, str) or not home.strip() or "\x00" in home:
            raise ValueError("harness_home must be a nonempty directory path")
    tasks = row.get("tasks")
    if (not isinstance(tasks, list) or not tasks
            or any(not isinstance(task, str) or not task.strip() for task in tasks)
            or len(set(tasks)) != len(tasks)):
        raise ValueError("tasks must be an explicit nonempty list of distinct case IDs")
    if not isinstance(row.get("model"), str) or not row["model"].strip():
        raise ValueError("Each experiment must explicitly specify a model")
    if row.get("effort") not in (*EFFORTS, "off"):
        raise ValueError("Each experiment must explicitly specify effort (no default)")
    for key in ("repetitions", "concurrency"):
        if type(row.get(key)) is not int or row[key] <= 0:
            raise ValueError(key + " must be explicitly set to a positive integer")
    if "results_data" in row and (not isinstance(row["results_data"], str) or not row["results_data"].strip()):
        raise ValueError("results_data must be a nonempty archive directory")
    if 'archive_objects' in row and (not isinstance(row['archive_objects'], str)
                                     or not row['archive_objects'].strip() or '\x00' in row['archive_objects']):
        raise ValueError('archive_objects must be a nonempty directory path')
    if "pricing" in row:
        validate_pricing(row["pricing"])
    from benchmarking.participants.attempt.recovery import policy
    settings = policy(row.get("recovery"), harness=row["harness"])
    capabilities = adapters.capabilities(row["harness"])
    if not capabilities["resume_session"] and settings["resume_session"]:
        raise ValueError("This harness does not support resume_session")
    if not capabilities["resume_session"] and settings["network_resumes"]:
        raise ValueError("This harness does not support network_resumes")
    if not capabilities["capacity_resumes"] and settings["capacity_resumes"]:
        raise ValueError("This harness does not support capacity_resumes")
    return row


def _task_selection(row, base, *, dataset=None, revision=None, offline=False):
    if "dataset" not in row and "tasks" not in row:
        raise ValueError("Specify tasks or a dataset")
    if "dataset" in row:
        from benchmarking.tasks.dataset import load_dataset

        spec = row["dataset"]
        if (not isinstance(spec, dict)
                or set(spec) - {"source", "source_env", "revision", "local_files_only", "name", "split"}
                or ("source" in spec) == ("source_env" in spec)):
            raise ValueError("dataset needs exactly one of source/source_env and optional name/split/revision/local_files_only")
        if "source_env" in spec:
            key = spec["source_env"]
            if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                raise ValueError("dataset source_env must name an environment variable")
            source = dataset if dataset is not None else os.environ.get(key)
            if not source or not source.strip():
                raise ValueError("Set the Dataset environment variable: " + key)
        else:
            source = dataset if dataset is not None else spec["source"]
        if not isinstance(source, str) or not source.strip():
            raise ValueError("dataset source must be a nonempty string")
        if dataset is not None and Path(source).is_dir():
            source = str(Path(source).resolve())
        elif dataset is None and (base / source).is_dir():
            source = str((base / source).resolve())
        local_files_only = offline or spec.get("local_files_only", False)
        dataset = load_dataset(source, revision=revision if revision is not None else spec.get("revision"),
                               local_files_only=local_files_only)
        name, split = spec.get("name", "core"), spec.get("split", "test")
        if not isinstance(name, str) or not name or not isinstance(split, str) or not split:
            raise ValueError("dataset name and split must be nonempty strings")
        records, cases = dataset.native_cases(name, split)
        selected = row.get("tasks", list(cases))
        if not isinstance(selected, list) or any(case not in cases for case in selected):
            raise ValueError("Selected tasks must belong to the native Dataset configuration and split")
        row["tasks"] = selected
        row["dataset"] = {**dataset.identity, "name": name, "split": split,
                          "index_sha256": digest(records.to_list()),
                          "local_files_only": local_files_only}
    return row


def _pricing(row, base):
    """Resolve an explicit profile price list into the condition's price snapshot."""
    if "pricing_file" not in row:
        return row
    if "pricing" in row:
        raise ValueError("Use pricing or pricing_file, not both")
    reference = row.pop("pricing_file")
    if not isinstance(reference, str) or not reference.strip():
        raise ValueError("pricing_file must be a nonempty file path")
    catalog = tomllib.loads((base / reference).read_text())
    models = catalog.get("models")
    if set(catalog) != {"models"} or not isinstance(models, dict) or not models:
        raise ValueError("pricing_file needs one or more [models.\"model-id\"] tables")
    model = row.get("model")
    if not isinstance(model, str) or model not in models:
        raise ValueError(f"pricing_file has no price for configured model: {model!r}")
    row["pricing"] = validate_pricing(models[model])
    return row


def frozen_pricing(row, recorded):
    """Reuse a run's price snapshot while retaining all other requested settings."""
    row = {key: value for key, value in row.items() if key != "pricing"}
    if "pricing" in recorded:
        row["pricing"] = recorded["pricing"]
    return row


def read_matrix(path, *, dataset=None, revision=None, offline=False):
    config = tomllib.loads(Path(path).read_text())
    if (set(config) - {"defaults", "runs"} or not isinstance(config.get("defaults", {}), dict)
            or not isinstance(config.get("runs"), list) or not config["runs"]
            or not all(isinstance(row, dict) for row in config["runs"])):
        raise ValueError("Expected [defaults] and one or more [[runs]] tables")
    rows = [validate(_task_selection(_pricing(dict(config.get("defaults", {}), **row), Path(path).resolve().parent),
                                    Path(path).resolve().parent, dataset=dataset, revision=revision, offline=offline))
            for row in config["runs"]]
    if len({row["name"] for row in rows}) != len(rows):
        raise ValueError("Experiment names must be unique")
    return [_scheme(row, Path(path).resolve().parent) for row in rows]


def _scheme(row, base):
    from benchmarking.participants.harnesses.scheme import resolve_scheme
    if "harness_home" in row:
        row["harness_home"] = str((base / row["harness_home"]).resolve())
    if 'archive_objects' in row:
        row['archive_objects'] = str((base / row['archive_objects']).resolve())
    if "scheme" in row or row["harness"] == "command":
        row["scheme"] = resolve_scheme(row.get("scheme", {}), base, row["harness"])
    return row


def read_configs(paths, *, dataset=None, revision=None, offline=False):
    """Expand one harness/model per file into independent effort conditions."""
    rows = []
    for path in paths:
        path = Path(path)
        config = tomllib.loads(path.read_text())
        if set(config) - (INPUT_FIELDS | {"efforts"}):
            raise ValueError("Unknown configuration fields in " + str(path))
        if not isinstance(config.get("model"), str) or not config["model"].strip():
            raise ValueError("Each configuration must specify a model")
        if "effort" in config and "efforts" in config:
            raise ValueError("Use effort or efforts, not both")
        efforts = config.pop("efforts", [config.pop("effort", None)])
        if (not isinstance(efforts, list) or not efforts
                or any(not isinstance(e, str) or e not in (*EFFORTS, "off") for e in efforts)
                or len(set(efforts)) != len(efforts)):
            raise ValueError("efforts must be a nonempty list of distinct effort names")
        name = config.pop("name", path.stem)
        config = _task_selection(_pricing(config, path.resolve().parent), path.resolve().parent,
                                 dataset=dataset, revision=revision, offline=offline)
        for effort in efforts:
            rows.append(_scheme(validate({**config, "name": f"{name}-{effort}",
                                  "effort": effort}), path.resolve().parent))
    if len({row["name"] for row in rows}) != len(rows):
        raise ValueError("Configuration condition names must be unique")
    return rows
