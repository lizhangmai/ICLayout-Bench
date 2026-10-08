"""Parse declarative evaluations in dependency order without executing tools."""

import json
import re

from benchmarking.files import keys, text

from .contracts import EvaluationPlan, Job, _decode_evaluation, identifier, number
from .graph import _order_jobs, _validate_source_graph
from .metrics import parse_metrics, parse_scoring, validate_scoring


def _parse_jobs(data):
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

    return jobs


def _parse_pre_layout(data, jobs):
    pre_layout = data.get("pre_layout", {})
    if pre_layout:
        keys(pre_layout, {"jobs", "source_report_sha256", "backends"}, set(), "pre_layout")
        if not re.fullmatch(r"[0-9a-f]{64}", pre_layout["source_report_sha256"]):
            raise ValueError("Pre-layout evidence needs a report digest")
        if not isinstance(pre_layout["backends"], dict) or not pre_layout["backends"]:
            raise ValueError("Pre-layout evidence needs backend identities")
    pre_layout = pre_layout.get("jobs", {})
    if not isinstance(pre_layout, dict):
        raise TypeError("Pre-layout observations must be a table")
    for name, source in pre_layout.items():
        identifier(name)
        if name in jobs:
            raise ValueError("Pre-layout observations are not executable evaluation jobs")
        keys(source, {"operation", "inputs", "outputs", "input_sha256", "parameters", "measurements"}, {"output_sha256"}, "pre_layout job")
        text(source["operation"], "pre-layout operation")
        if not isinstance(source["parameters"], dict) or not isinstance(source["measurements"], dict):
            raise TypeError("Pre-layout parameters and measurements must be tables")
        if any(not isinstance(source[field], dict) for field in ("inputs", "input_sha256", "outputs")):
            raise TypeError("Pre-layout input and output declarations must be tables")
        if not source["inputs"] or set(source["inputs"]) != set(source["input_sha256"]):
            raise ValueError("Pre-layout input identities are incomplete")
        for role, ref in source["inputs"].items():
            identifier(role)
            if not isinstance(ref, str):
                raise TypeError("Invalid pre-layout input reference")
            if ref.startswith("input:"):
                identifier(ref[6:])
            elif not (len(ref.split(":")) == 3 and ref.startswith("job:")):
                raise ValueError("Pre-layout must be independent of the candidate")
            if not re.fullmatch(r"[0-9a-f]{64}", source["input_sha256"][role]):
                raise ValueError("Invalid pre-layout input digest")
        for name, measurement in source["measurements"].items():
            identifier(name)
            keys(measurement, {"value", "unit"}, set(), "pre-layout measurement")
            number(measurement["value"])
            text(measurement["unit"], "pre-layout measurement unit")

    _validate_source_graph(pre_layout)

    return pre_layout


def _validate_mode(mode, ordered, metrics, ancestors, data_ancestors):
    if mode != "characterization":
        for gate in ("artifact", "drc", "lvs"):
            matches = [j for j in ordered if j.gate == gate]
            if len(matches) != 1 or "candidate" not in dict(matches[0].inputs).values():
                raise ValueError(f"Layout evaluation needs one {gate} gate on the candidate")
    if mode == "post_layout":
        gates = {j.id for j in ordered if j.gate in {"artifact", "drc", "lvs"}}
        for job in ordered:
            if job.stage == "simulate" and not any(ref.startswith("job:") for _, ref in job.inputs):
                raise ValueError("Post-layout simulations must consume candidate extraction; pre-layout is frozen")
            if job.stage == "extract" and not gates <= ancestors[job.id]:
                raise ValueError(f"Extraction must depend on physical validity gates: {job.id}")
        performance = [m for m in metrics if m.category == "performance"]
        if not performance:
            raise ValueError("Post-layout evaluation needs a performance metric")
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



def parse_evaluation(raw: bytes, *, file_format: str = "toml") -> EvaluationPlan:
    """Validate a TOML declaration or JSON snapshot and order its jobs."""
    data = _decode_evaluation(raw, file_format)
    keys(data, {"mode", "jobs", "metrics"}, {"scoring", "pre_layout"}, "evaluation")
    if data["mode"] not in {"physical", "post_layout", "characterization"}:
        raise ValueError("Unknown evaluation mode")
    jobs = _parse_jobs(data)
    ordered, ancestors, data_ancestors = _order_jobs(jobs)
    pre_layout = _parse_pre_layout(data, jobs)
    metrics = parse_metrics(data, jobs, pre_layout)
    scoring = parse_scoring(data, metrics)
    _validate_mode(data["mode"], ordered, metrics, ancestors, data_ancestors)
    validate_scoring(data["mode"], scoring, metrics, ordered)
    return EvaluationPlan(data["mode"], tuple(ordered), tuple(metrics), raw, file_format, scoring,
                          json.dumps(pre_layout, sort_keys=True, allow_nan=False))
