"""Metric requirements, frozen baselines and score-envelope validation."""

import math

from benchmarking.files import keys, text

from .contracts import (
    SCORING_DIMENSIONS,
    SCORING_METHOD,
    Metric,
    ScoringSpec,
    identifier,
    number,
)
from .graph import _source_pair_matches


def parse_metrics(data, jobs, pre_layout):
    metrics = []
    seen = set()
    if not isinstance(data["metrics"], list):
        raise TypeError("Metrics must be a list")
    for entry in data["metrics"]:
        keys(entry, {"id", "category", "observations", "unit", "direction", "aggregation"},
             {"lower", "upper", "requirement", "dimension",
              "baseline", "normalization", "scale", "quality_target"}, "metric")
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
        bounds = entry
        rationale = None
        if "requirement" in entry:
            if "lower" in entry or "upper" in entry:
                raise ValueError(f"Mixed legacy bounds and explicit requirement: {name}")
            bounds = entry["requirement"]
            keys(bounds, {"rationale"}, {"lower", "upper"}, "metric.requirement")
            rationale = text(bounds["rationale"], "requirement rationale")
            if not rationale.strip() or not ({"lower", "upper"} & bounds.keys()):
                raise ValueError(f"Requirement needs bounds and a functional rationale: {name}")
        lower = number(bounds["lower"]) if "lower" in bounds else None
        upper = number(bounds["upper"]) if "upper" in bounds else None
        if lower is not None and upper is not None and lower > upper:
            raise ValueError(f"Inverted bounds: {name}")
        if entry["direction"] == "target" and not entry.get("baseline") and (lower is None or upper is None):
            raise ValueError("Target metrics require lower and upper bounds")
        dimension = entry.get("dimension")
        if dimension is not None:
            dimension = text(dimension, "metric dimension")
            if entry["category"] != "performance":
                raise ValueError(f"Only performance metrics may declare a dimension: {name}")
            if dimension not in SCORING_DIMENSIONS:
                raise ValueError(f"Unknown scoring dimension: {dimension}")
            if lower is None and upper is None and not entry.get("baseline"):
                raise ValueError(f"Metric dimension requires a bound or baseline: {name}")
        baseline = entry.get("baseline", [])
        normalization = entry.get("normalization")
        scale = number(entry["scale"]) if "scale" in entry else None
        if not isinstance(baseline, list) or (baseline and len(baseline) != len(refs)):
            raise ValueError(f"Baseline must match observations one to one: {name}")
        if baseline:
            if entry["category"] != "performance" or dimension is None:
                raise ValueError(f"Baseline requires a performance dimension: {name}")
            if normalization not in {"ratio", "saturating_ratio", "db20", "target"}:
                raise ValueError(f"Unknown baseline normalization: {name}")
            if normalization == "saturating_ratio" and (entry["direction"] != "minimize" or scale is None or scale <= 0):
                raise ValueError(f"Saturating ratio needs minimize direction and positive scale: {name}")
            if normalization == "target" and (entry["direction"] != "target" or scale is None or scale <= 0):
                raise ValueError(f"Target normalization needs target direction and positive scale: {name}")
            if normalization != "target" and entry["direction"] == "target":
                raise ValueError(f"Target direction requires target normalization: {name}")
            if normalization == "db20" and entry["unit"] != "dB":
                raise ValueError(f"db20 requires amplitude dB: {name}")
            if scale is not None and (scale <= 0 or normalization == "db20"):
                raise ValueError(f"Invalid normalization scale: {name}")
            for paired_ref, ref in zip(refs, baseline, strict=True):
                parts = text(ref, "baseline observation").split(":")
                if len(parts) != 2 or parts[0] not in pre_layout:
                    raise ValueError(f"Baseline must name a frozen pre-layout observation: {ref}")
                identifier(parts[1])
                source = pre_layout[parts[0]]
                paired = jobs[paired_ref.split(":")[0]]
                if source["operation"] != paired.operation or source["parameters"] != paired.parameters:
                    raise ValueError(f"Baseline and candidate simulation settings differ: {name}")
                if paired_ref.split(":")[1] != parts[1]:
                    raise ValueError(f"Baseline and candidate measurement names differ: {name}")
                measurement = source["measurements"].get(parts[1])
                if measurement is None or measurement["unit"] != entry["unit"]:
                    raise ValueError(f"Missing or incompatible frozen baseline measurement: {ref}")
                if not _source_pair_matches(parts[0], paired.id, pre_layout, jobs):
                    raise ValueError(f"Baseline and candidate non-circuit inputs differ: {name}")
        elif normalization is not None or scale is not None:
            raise ValueError(f"Normalization requires baseline observations: {name}")
        quality_target = None
        quality_target_rationale = None
        if "quality_target" in entry:
            target = entry["quality_target"]
            keys(target, {"value", "rationale"}, set(), "metric.quality_target")
            quality_target = number(target["value"])
            quality_target_rationale = text(target["rationale"], "quality target rationale")
            if not baseline or not quality_target_rationale.strip():
                raise ValueError(f"Quality target needs paired source evidence and a rationale: {name}")
            if normalization in {"ratio", "saturating_ratio"} and quality_target < 0:
                raise ValueError(f"Ratio quality target must be nonnegative: {name}")
            if normalization == "ratio" and quality_target + (scale or 0) <= 0:
                raise ValueError(f"Ratio quality target needs a positive value or scale: {name}")
            if ((lower is not None and quality_target < lower)
                    or (upper is not None and quality_target > upper)):
                raise ValueError(f"Quality target must satisfy functional bounds: {name}")
        metrics.append(Metric(name, entry["category"], tuple(refs), text(entry["unit"], "unit"),
                              entry["direction"], entry["aggregation"], lower, upper,
                              dimension, tuple(baseline), normalization, scale, rationale,
                              quality_target, quality_target_rationale))

    return metrics


def parse_scoring(data, metrics):
    scoring = None
    scoring_data = data.get("scoring")
    if scoring_data is not None:
        method = text(scoring_data.get("method"), "scoring method")
        if method != SCORING_METHOD:
            raise ValueError(f"Unsupported scoring method: {method}")
        keys(scoring_data, {"method", "area_metric", "area_target", "weights", "rationale"},
             set(), "evaluation.scoring")
        area_metric = identifier(scoring_data["area_metric"])
        area_target = number(scoring_data["area_target"])
        if area_target <= 0:
            raise ValueError("scoring.area_target must be positive")
        declared = scoring_data["weights"]
        if not isinstance(declared, dict) or not declared:
            raise ValueError("scoring.weights must be a nonempty metric-weight table")
        weights = tuple(sorted((identifier(k), number(v)) for k, v in declared.items()))
        expected = {area_metric} | {metric.id for metric in metrics if metric.baseline}
        if set(declared) != expected:
            raise ValueError("scoring.weights must name exactly the area and baseline metrics")
        if (any(v < 0 or v > 1 for _, v in weights)
                or not math.isclose(math.fsum(v for _, v in weights), 1, rel_tol=0, abs_tol=1e-9)):
            raise ValueError("scoring.weights must be nonnegative and sum to one")
        if not any(k != area_metric and v > 0 for k, v in weights):
            raise ValueError("scoring.weights needs a positive electrical weight")
        rationale = text(scoring_data["rationale"], "scoring rationale")
        scoring = ScoringSpec(method, area_metric, area_target, weights, rationale)

    return scoring


def validate_scoring(mode, scoring, metrics, ordered):
    if scoring is None:
        if any(metric.baseline or metric.dimension is not None for metric in metrics):
            raise ValueError("Scoring metric metadata requires evaluation.scoring")
    else:
        if mode != "post_layout":
            raise ValueError("Layout scoring requires post_layout evaluation")
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
        if not any(metric.baseline for metric in metrics):
            raise ValueError("Layout scoring requires pre-layout baselines")
        for metric in metrics:
            if metric.dimension and not metric.baseline:
                raise ValueError(f"Scored metric needs a baseline: {metric.id}")
