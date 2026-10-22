"""Resolve experiment conditions and immutable local execution inputs."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from benchmarking.execution.workspace.docker import DockerSession
from benchmarking.files import Asset, relative
from benchmarking.participants.attempt.storage import CaseRecord, case_lease_root
from benchmarking.participants.batch import runner as batch
from benchmarking.participants.batch.config import (
    digest,
    read_configs,
    read_matrix,
    resolve,
    validate,
)
from benchmarking.participants.batch.runner import path_component
from benchmarking.participants.harnesses.contracts import ParticipantSelection
from benchmarking.participants.harnesses.registry import harness_version
from benchmarking.tasks.contract import load_task
from benchmarking.tasks.dataset import dataset_root, load_dataset, process_manifest
from benchmarking.version import package_version

__all__ = ["ExperimentPlan", "ExperimentRequest", "default_output", "harness_version", "plan_conditions", "prepare_batch"]


@dataclass(frozen=True)
class ExperimentRequest:
    config: list[Path] | None
    matrix: Path | None
    case: list[str] | None
    repetitions: int | None
    concurrency: int | None
    dataset: str | None
    revision: str | None
    offline: bool
    image: str
    endpoint: str | None
    token_env: str
    output: Path | None
    results_data: Path | None
    resume: bool
    replace_unfinished: bool


@dataclass(frozen=True)
class PlannedCondition:
    row: dict
    group: str
    selection: ParticipantSelection

    def description(self):
        return {**{k: v for k, v in self.row.items() if k != "results_data"},
                "resolved": self.selection.condition}


@dataclass(frozen=True)
class ExperimentPlan:
    conditions: tuple[PlannedCondition, ...]


@dataclass(frozen=True)
class PreparedCondition:
    planned: PlannedCondition
    output: Path
    identity: dict


def default_output(group):
    return Path("results") / group


def case_outputs(output, tasks, timestamp, *, reuse):
    """Allocate fresh task histories, or reuse the latest recorded run explicitly."""
    paths = {task: str(Path(path_component(task)) / timestamp) for task in tasks}
    if not reuse or not output.exists():
        return paths
    recorded = {}
    invalid = set()
    for record in CaseRecord.discover(output):
        plan = record.read()["identity"]["plan"][0]
        task = plan["tasks"][0]
        if task not in paths:
            continue
        directory = case_lease_root(record.root, plan["repetitions"])
        relative = directory.relative_to(output)
        if len(relative.parts) != 2 or relative.parts[0] != path_component(task):
            invalid.add(task)
            continue
        rank = relative.parts[1]
        try:
            datetime.strptime(rank, "%Y%m%d-%H%M%S-%f").astimezone()
        except ValueError:
            invalid.add(task)
            continue
        previous = recorded.get(task)
        if previous and previous[0] == rank and previous[1] != relative:
            raise ValueError("Ambiguous recorded case directories: " + task)
        if previous is None or rank > previous[0]:
            recorded[task] = (rank, relative)
    for task in tasks:
        latest = recorded.get(task)
        history = output / path_component(task)
        for directory in history.iterdir() if history.is_dir() else ():
            if not directory.is_dir():
                continue
            try:
                datetime.strptime(directory.name, "%Y%m%d-%H%M%S-%f").astimezone()
            except ValueError:
                continue
            candidate = (directory.name, directory.relative_to(output))
            if latest is None or candidate[0] > latest[0]:
                latest = candidate
        if latest is not None:
            paths[task] = str(latest[1])
        elif task in invalid:
            raise ValueError("Recorded cases require --output/<task>/<timestamp>; select the condition output directory: " + task)
    return paths


def plan_conditions(request: ExperimentRequest):
    if not request.config and not request.matrix:
        raise ValueError("Supply --config or --matrix")
    if request.replace_unfinished and (not request.output or not request.case or request.resume):
        raise ValueError("--replace-unfinished requires --output and explicit --case selections, without --resume")
    if request.config:
        groups, rows = [], []
        for config in request.config:
            conditions = read_configs([config], dataset=request.dataset, revision=request.revision, offline=request.offline)
            groups.extend(str(Path(path_component(config.stem)) / r["effort"])
                          if len(conditions) > 1 else path_component(config.stem)
                          for r in conditions)
            rows.extend(conditions)
    else:
        rows = read_matrix(request.matrix, dataset=request.dataset, revision=request.revision, offline=request.offline)
        groups = [str(Path(path_component(request.matrix.stem)) / path_component(r["name"])) for r in rows]
    if len(set(groups)) != len(groups):
        raise ValueError("Configuration output groups must be unique")
    if request.resume and not request.output:
        raise ValueError("--resume requires --output pointing to an existing condition directory")
    for row in rows:
        if request.case:
            selected = []
            for name in request.case:
                matches = ([name] if name in row["tasks"] else
                           [task for task in row["tasks"] if task.rsplit(".", 1)[-1] == name])
                if not matches:
                    raise ValueError(f"Unknown case {name!r} in condition {row['name']}; choose a configured case ID")
                if len(matches) > 1:
                    raise ValueError(f"Ambiguous case {name!r}; use a full ID: {', '.join(matches)}")
                if matches[0] not in selected:
                    selected.append(matches[0])
            row["tasks"] = selected
        for key in ("repetitions", "concurrency"):
            if getattr(request, key) is not None:
                row[key] = getattr(request, key)
        validate(row)
    # Resolve every condition before creating any sessions; no credentials enter the plan.
    return ExperimentPlan(tuple(
        PlannedCondition(row, group, resolve(row["harness"], row.get("model"), row.get("effort"),
            **({"harness_home": row["harness_home"]} if "harness_home" in row else {})))
        for row, group in zip(rows, groups, strict=True)
    ))


def prepare_batch(request: ExperimentRequest, experiment: ExperimentPlan, *, case_paths=None):
    """Bind conditions to recorded histories or explicitly allocated case paths."""
    image = request.image
    conditions = experiment.conditions
    if (request.dataset or request.revision or request.offline) and request.endpoint:
        raise ValueError("Choose a dataset or --endpoint, not both")
    if not request.dataset and not any(c.row.get("dataset") for c in conditions) and not request.endpoint:
        raise ValueError("Supply --dataset or a dataset configuration for local mode, or --endpoint for remote mode")
    if request.output and len(conditions) != 1:
        raise ValueError("--output requires exactly one condition")
    versions = [(r["scheme"]["version"], r["scheme"]["version"]) if r["harness"] == "command"
                else harness_version(r["harness"]) for r in (c.row for c in conditions)]
    outputs = ([request.output.resolve()] if request.output else
               [default_output(c.group).resolve() for c in conditions])
    if len(set(outputs)) != len(outputs):
        raise ValueError("Duplicate harness/model/effort output directories")
    if not request.endpoint:
        images = {c.row.get("scheme", {}).get("solver_image", image) for c in conditions}
        pinned = {image: DockerSession(image).image_id for image in sorted(images)}
        image = pinned.get(image, image)
    identity = {"endpoint": request.endpoint, "image": image if not request.endpoint else None,
                "benchmark": package_version()}
    dataset_paths = {}
    cases = {}
    if not request.endpoint:
        identity["inputs"] = {}
    for condition in conditions:
        row = condition.row
        spec = row.get("dataset", {})
        source = request.dataset or spec.get("source")
        if not source and request.endpoint:
            continue
        revision = request.revision or (spec.get("commit") if source and not Path(source).is_dir() else None)
        dataset = load_dataset(source, revision=revision, local_files_only=request.offline or spec.get("local_files_only", False))
        native = None
        if spec:
            records, native = dataset.native_cases(spec["name"], spec["split"])
            if digest(records.to_list()) != spec["index_sha256"]:
                raise ValueError("Dataset index changed after experiment selection")
        for name in row["tasks"]:
            config = native[name] if native is not None else dataset.case(name)
            location = Path(config).parent.relative_to(dataset_root(config) / "tasks")
            case_path = str(Path(*(path_component(part) for part in location.parts)))
            if name in dataset_paths and dataset_paths[name] != case_path:
                raise ValueError(f"Conflicting Dataset paths for case: {name}")
            dataset_paths[name] = case_path
            if request.endpoint:
                continue
            task = load_task(config)
            selection = {"dataset": dataset.identity["source"],
                         "revision": dataset.identity["commit"] if not Path(source).is_dir() else None,
                         "case": name, "offline": request.offline or spec.get("local_files_only", False)}
            if spec:
                selection.update(dataset_name=spec["name"], dataset_split=spec["split"])
            if name in cases and cases[name] != selection:
                raise ValueError(f"Conflicting datasets for case: {name}")
            cases[name] = selection
            identity["inputs"][name] = {"dataset": dataset.identity, "case_sha256": task.digest,
                "pdk_sha256": Asset((process_manifest(config)).read_bytes(), "toml").sha256,
                "inputs": {key: value.sha256 for key, value in task.input_assets().items()}}
    selected = {task for c in conditions for task in c.row["tasks"]}
    if case_paths is None:
        timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
        case_paths = case_outputs(outputs[0], selected, timestamp, reuse=request.output is not None)
    else:
        if request.output is None or set(case_paths) != selected:
            raise ValueError("Explicit case paths require --output and exactly the selected tasks")
        case_paths = {task: relative(path, "case run directory") for task, path in case_paths.items()}
        if len(set(case_paths.values())) != len(case_paths):
            raise ValueError("Case run directories must be unique")
    options = batch.BatchOptions(
        endpoint=request.endpoint, image=image, token_env=request.token_env,
        results_data=request.results_data, resume=request.resume,
        replace_unfinished=request.replace_unfinished,
        case_paths=case_paths, cases=cases,
    )
    slots = []
    for condition, output, version in zip(conditions, outputs, versions, strict=True):
        current_identity = dict(identity, plan=[condition.description()], cli_version=version[1],
                                image=condition.row.get("scheme", {}).get("solver_image", image) if not request.endpoint else None)
        slots.append(PreparedCondition(condition, output, current_identity))
    return options, slots
