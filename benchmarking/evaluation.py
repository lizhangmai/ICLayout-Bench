"""Tool-independent evaluation plans and per-task metric definitions.

Operation names are resolved by the caller's backend bindings. No executable,
PDK, circuit family, waveform expression or simulator syntax lives here.
"""

import hashlib
import json
import math
import re
import tomllib
from dataclasses import dataclass

from .files import keys, text


def identifier(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", value):
        raise ValueError(f"Invalid identifier: {value!r}")
    return value


def number(value: object) -> float:
    if type(value) not in {int, float} or not math.isfinite(value):
        raise ValueError("Expected a finite numeric value")
    return float(value)


@dataclass(frozen=True)
class Job:
    id: str
    stage: str
    operation: str
    inputs: tuple[tuple[str, str], ...]
    outputs: tuple[tuple[str, str], ...]
    requires: tuple[str, ...]
    gate: str | None
    parameters_json: str

    @property
    def parameters(self) -> dict:
        # Each backend receives its own copy, keeping the frozen plan immutable.
        return json.loads(self.parameters_json)


@dataclass(frozen=True)
class Metric:
    id: str
    category: str
    observations: tuple[str, ...]
    unit: str
    direction: str
    aggregation: str
    lower: float | None
    upper: float | None
    dimension: str | None = None
    zero_lower: float | None = None
    zero_upper: float | None = None

    @property
    def is_requirement(self) -> bool:
        return self.lower is not None or self.upper is not None


@dataclass(frozen=True)
class EvaluationPlan:
    mode: str
    jobs: tuple[Job, ...]
    metrics: tuple[Metric, ...]
    raw: bytes
    format: str = "toml"
    scoring: "ScoringSpec | None" = None

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.raw).hexdigest()

    def description(self) -> dict:
        return _decode_evaluation(self.raw, self.format)

    def external_inputs(self) -> frozenset[str]:
        return frozenset(ref for job in self.jobs for _, ref in job.inputs
                         if ref in {"candidate", "task"} or ref.startswith("input:"))


def _decode_evaluation(raw: bytes, file_format: str) -> dict:
    if file_format == "toml":
        return tomllib.loads(raw.decode("utf-8"))
    if file_format == "json":
        return json.loads(raw)
    raise ValueError("Evaluation plan format must be toml or json")


@dataclass(frozen=True)
class ScoringSpec:
    """Frozen configuration for the single public task score.

    ``area_target`` and ``area_zero`` are absolute functional-area values in
    the unit declared by ``area_metric``.  The latter is deliberately larger:
    reaching the target earns the full area component and reaching the zero
    boundary earns none of it.
    """

    method: str
    area_metric: str
    area_target: float
    area_zero: float


SCORING_METHOD = "layout-v1"
SCORING_DIMENSIONS = frozenset({"response", "bias", "supply"})


def parse_evaluation(raw: bytes, *, file_format: str = "toml") -> EvaluationPlan:
    """Validate a declarative plan; return jobs in dependency order.

    Inputs use candidate, task, input:<role>, or job:<id>:<output>. Metric observations
    use <job>:<measurement>. Separate jobs express corners, loads and seeds;
    metrics retain all observations and check bounds on every one of them.
    TOML files and JSON snapshots of inline plans share the same validation.
    """
    data = _decode_evaluation(raw, file_format)
    keys(data, {"schema_version", "mode", "jobs", "metrics"}, {"scoring"}, "evaluation")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("Unsupported evaluation schema_version")
    if data["mode"] not in {"physical", "post_layout", "characterization"}:
        raise ValueError("Unknown evaluation mode")
    if not isinstance(data["jobs"], list) or not data["jobs"]:
        raise ValueError("Evaluation needs a nonempty jobs list")
    jobs = {}
    for entry in data["jobs"]:
        keys(entry, {"id", "stage", "operation", "inputs"},
             {"outputs", "requires", "gate", "parameters"}, "job")
        name = identifier(entry["id"])
        if name in jobs:
            raise ValueError(f"Duplicate job: {name}")
        if entry["stage"] not in {"check", "extract", "simulate", "measure"}:
            raise ValueError(f"Unknown stage in {name}")
        operation = text(entry["operation"], "operation")
        gate = entry.get("gate")
        if gate is not None and (gate not in {"artifact", "drc", "lvs", "constraint"}
                                 or entry["stage"] != "check"):
            raise ValueError(f"Invalid gate in {name}")
        if not isinstance(entry["inputs"], dict) or not entry["inputs"]:
            raise ValueError(f"Job {name} needs named inputs")
        inputs = tuple((identifier(k), text(v, "input reference"))
                       for k, v in entry["inputs"].items())
        outputs = entry.get("outputs", {})
        if not isinstance(outputs, dict):
            raise TypeError("Job outputs must be a table")
        outputs = tuple((identifier(k), text(v, "output format")) for k, v in outputs.items())
        requires = entry.get("requires", [])
        if not isinstance(requires, list) or len(set(requires)) != len(requires):
            raise ValueError("Job requires must be a list of unique job ids")
        requires = tuple(identifier(x) for x in requires)
        parameters = entry.get("parameters", {})
        if not isinstance(parameters, dict):
            raise TypeError("Job parameters must be a table")
        jobs[name] = Job(name, entry["stage"], operation, inputs, outputs, requires, gate,
                         json.dumps(parameters, allow_nan=False, sort_keys=True))

    # Data dependencies also impose ordering; explicit requires is useful for
    # checks that produce evidence but no downstream circuit artifact.
    ordered = []
    pending = dict(jobs)
    ancestors: dict[str, set[str]] = {}
    data_ancestors: dict[str, set[str]] = {}
    dependencies = {}
    data_dependencies = {}
    for job in jobs.values():
        deps = set(job.requires)
        producers = set()
        for _, ref in job.inputs:
            parts = ref.split(":")
            if ref in {"candidate", "task"}:
                continue
            if len(parts) == 2 and parts[0] == "input":
                identifier(parts[1])
                continue
            if len(parts) != 3 or parts[0] != "job" or parts[1] not in jobs:
                raise ValueError(f"Unknown input reference: {ref}")
            if parts[2] not in dict(jobs[parts[1]].outputs):
                raise ValueError(f"Unknown job output: {ref}")
            producers.add(parts[1])
        deps |= producers
        if not deps <= jobs.keys():
            raise ValueError(f"Unknown job dependency in {job.id}")
        dependencies[job.id], data_dependencies[job.id] = deps, producers
    while pending:
        ready = [job for job in pending.values() if dependencies[job.id] <= ancestors.keys()]
        if not ready:
            raise ValueError("Evaluation dependency cycle")
        for job in ready:
            deps, producers = dependencies[job.id], data_dependencies[job.id]
            ancestors[job.id] = deps | set().union(*(ancestors[x] for x in deps))
            data_ancestors[job.id] = producers | set().union(*(data_ancestors[x] for x in producers))
            ordered.append(Job(job.id, job.stage, job.operation, job.inputs, job.outputs,
                               tuple(sorted(deps)), job.gate, job.parameters_json))
            del pending[job.id]

    metrics = []
    seen = set()
    if not isinstance(data["metrics"], list):
        raise TypeError("Metrics must be a list")
    for entry in data["metrics"]:
        keys(entry, {"id", "category", "observations", "unit", "direction", "aggregation"},
             {"lower", "upper", "dimension", "zero_lower", "zero_upper"}, "metric")
        name = identifier(entry["id"])
        if name in seen:
            raise ValueError(f"Duplicate metric: {name}")
        seen.add(name)
        if entry["category"] not in {"physical", "performance"}:
            raise ValueError(f"Unknown metric category: {name}")
        if entry["direction"] not in {"minimize", "maximize", "target"}:
            raise ValueError(f"Unknown metric direction: {name}")
        if entry["aggregation"] not in {"min", "max"}:
            raise ValueError("Metric aggregation must be min or max")
        refs = entry["observations"]
        if not isinstance(refs, list) or not refs or len(set(refs)) != len(refs):
            raise ValueError(f"Metric {name} needs unique observations")
        for ref in refs:
            parts = text(ref, "observation").split(":")
            if len(parts) != 2 or parts[0] not in jobs:
                raise ValueError(f"Unknown observation: {ref}")
            identifier(parts[1])
            if (jobs[parts[0]].stage not in {"simulate", "measure"}
                    and not (jobs[parts[0]].stage == "check" and entry["category"] == "physical")):
                raise ValueError(f"Observation is not produced by a measurement stage: {ref}")
        lower = number(entry["lower"]) if "lower" in entry else None
        upper = number(entry["upper"]) if "upper" in entry else None
        if lower is not None and upper is not None and lower > upper:
            raise ValueError(f"Inverted bounds: {name}")
        if entry["direction"] == "target" and (lower is None or upper is None):
            raise ValueError("Target metrics require lower and upper bounds")
        dimension = entry.get("dimension")
        if dimension is not None:
            dimension = text(dimension, "metric dimension")
            if entry["category"] != "performance":
                raise ValueError(f"Only performance metrics may declare a dimension: {name}")
            if dimension not in SCORING_DIMENSIONS:
                raise ValueError(f"Unknown scoring dimension: {dimension}")
            if lower is None and upper is None:
                raise ValueError(f"Metric dimension requires an acceptance bound: {name}")
        zero_lower = number(entry["zero_lower"]) if "zero_lower" in entry else None
        zero_upper = number(entry["zero_upper"]) if "zero_upper" in entry else None
        if entry["category"] != "performance" and (zero_lower is not None or zero_upper is not None):
            raise ValueError(f"Only performance metrics may declare scoring boundaries: {name}")
        if zero_lower is not None and lower is None:
            raise ValueError(f"zero_lower requires a lower bound: {name}")
        if zero_upper is not None and upper is None:
            raise ValueError(f"zero_upper requires an upper bound: {name}")
        if lower is not None and zero_lower is not None and zero_lower > lower:
            raise ValueError(f"zero_lower must not exceed the lower bound: {name}")
        if upper is not None and zero_upper is not None and zero_upper < upper:
            raise ValueError(f"zero_upper must not be below the upper bound: {name}")
        metrics.append(Metric(name, entry["category"], tuple(refs), text(entry["unit"], "unit"),
                              entry["direction"], entry["aggregation"], lower, upper,
                              dimension, zero_lower, zero_upper))

    scoring = None
    scoring_data = data.get("scoring")
    if scoring_data is not None:
        keys(scoring_data, {"method", "area_metric", "area_target", "area_zero"}, set(),
             "evaluation.scoring")
        method = text(scoring_data["method"], "scoring method")
        if method != SCORING_METHOD:
            raise ValueError(f"Unsupported scoring method: {method}")
        area_metric = identifier(scoring_data["area_metric"])
        area_target = number(scoring_data["area_target"])
        area_zero = number(scoring_data["area_zero"])
        if area_target <= 0:
            raise ValueError("scoring.area_target must be positive")
        if area_zero <= area_target:
            raise ValueError("scoring.area_zero must exceed area_target")
        scoring = ScoringSpec(method, area_metric, area_target, area_zero)

    if data["mode"] != "characterization":
        for gate in ("artifact", "drc", "lvs"):
            matches = [j for j in ordered if j.gate == gate]
            if len(matches) != 1 or "candidate" not in dict(matches[0].inputs).values():
                raise ValueError(f"Layout evaluation needs one {gate} gate on the candidate")
    if data["mode"] == "post_layout":
        gates = {j.id for j in ordered if j.gate in {"artifact", "drc", "lvs"}}
        for job in ordered:
            if job.stage == "extract" and not gates <= ancestors[job.id]:
                raise ValueError(f"Extraction must depend on physical validity gates: {job.id}")
        performance = [m for m in metrics if m.category == "performance"]
        if not any(m.is_requirement for m in performance):
            raise ValueError("Post-layout evaluation needs a performance requirement")
        for metric in performance:
            for ref in metric.observations:
                job_id = ref.split(":")[0]
                lineage = data_ancestors[job_id] | {job_id}
                simulations = [j for j in ordered if j.id in lineage and j.stage == "simulate"]
                if not simulations:
                    raise ValueError(f"Post-layout metric has no simulation: {metric.id}")
                for simulation in simulations:
                    extractors = [j for j in ordered if j.id in data_ancestors[simulation.id]
                                  and j.stage == "extract"]
                    if not any("candidate" in dict(j.inputs).values() for j in extractors):
                        raise ValueError(f"Simulation must consume candidate extraction: {simulation.id}")

    if scoring is None:
        if any(metric.dimension is not None or metric.zero_lower is not None
               or metric.zero_upper is not None for metric in metrics):
            raise ValueError("Scoring metric metadata requires evaluation.scoring")
    else:
        if data["mode"] != "post_layout":
            raise ValueError("layout-v1 scoring requires post_layout evaluation")
        by_id = {metric.id: metric for metric in metrics}
        area = by_id.get(scoring.area_metric)
        if area is None:
            raise ValueError(f"scoring.area_metric is unknown: {scoring.area_metric}")
        if area.category != "physical":
            raise ValueError("scoring.area_metric must name a physical metric")
        if area.direction != "minimize":
            raise ValueError("scoring.area_metric must minimize functional area")
        if len(area.observations) != 1:
            raise ValueError("scoring.area_metric must have exactly one observation")
        area_job_id, _ = area.observations[0].split(":")
        area_job = next(job for job in ordered if job.id == area_job_id)
        if (area_job.stage != "check" or area_job.gate != "constraint"
                or "candidate" not in dict(area_job.inputs).values()):
            raise ValueError("scoring.area_metric must come from the candidate constraint check")
        constraint_gates = [job for job in ordered
                            if job.stage == "check" and job.gate == "constraint"
                            and "candidate" in dict(job.inputs).values()]
        if len(constraint_gates) != 1:
            raise ValueError("Scored layout evaluation needs one candidate constraint gate")
        required = [metric for metric in metrics
                    if metric.category == "performance" and metric.is_requirement]
        if not required:
            raise ValueError("Scored layout evaluation needs a bounded performance metric")
        for metric in required:
            if metric.dimension not in SCORING_DIMENSIONS:
                raise ValueError(f"Required performance metric needs a scoring dimension: {metric.id}")
            if metric.lower is not None and metric.zero_lower is None:
                raise ValueError(f"Required performance metric needs zero_lower: {metric.id}")
            if metric.upper is not None and metric.zero_upper is None:
                raise ValueError(f"Required performance metric needs zero_upper: {metric.id}")

    return EvaluationPlan(data["mode"], tuple(ordered), tuple(metrics), raw, file_format, scoring)
