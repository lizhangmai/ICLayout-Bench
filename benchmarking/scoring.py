"""The single task score used by layout evaluations.

The score is intentionally independent of any runner or report writer.  A
sealed evaluation report can be passed to :func:`recompute_score` by a report
consumer and checked against the score written by ``evaluate.py``.

Current ``layout-v2`` quality is ``100 * sqrt(E * Q)`` after physical and
functional gates, with same-condition source simulation defining electrical
quality 1 and a frozen area reference defining Q. Scores are uncapped.
Historical ``layout-v1`` retains its original bounded attainment and bonuses.

The evaluator's metric summaries are display data.  The scoring core derives
observation values and statuses from the raw job measurements so a report
consumer can independently recompute a score from the frozen plan and the
durable job evidence.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from .evaluation import SCORING_METHOD, EvaluationPlan, Metric

MAXIMUM = 100
_FAILED = "failed"
_UNKNOWN = frozenset({"error", "blocked"})


def _clip(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _below_one(value: float) -> float:
    """Keep an outside-bound observation strictly below a perfect score.

    Values immediately outside an acceptance bound can otherwise round to
    ``1.0`` in floating-point arithmetic.  Such a value must remain visibly
    below full attainment, because it makes ``H`` false and must keep the
    electric-only score below 60.
    """

    return min(value, math.nextafter(1.0, 0.0))


def _attainment(metric: Metric, value: float) -> float | None:
    """Return one observation's continuous attainment, or ``None`` if unscored."""

    if not math.isfinite(value) or not metric.is_requirement:
        return None
    lower, upper = metric.lower, metric.upper
    if lower is not None and value < lower:
        boundary = metric.zero_lower
        if boundary is None:
            return None
        if boundary == lower:
            return 0.0
        return _below_one(_clip((value - boundary) / (lower - boundary)))
    if upper is not None and value > upper:
        boundary = metric.zero_upper
        if boundary is None:
            return None
        if boundary == upper:
            return 0.0
        return _below_one(_clip((boundary - value) / (boundary - upper)))
    return 1.0


def _report_status(report: Mapping[str, Any] | None) -> str | None:
    return report.get("status") if isinstance(report, Mapping) else None


def _job_state(plan: EvaluationPlan, jobs: Mapping[str, Any],
               physical_valid: bool | None = None, *, baseline_jobs=frozenset()) -> float | None:
    """Resolve G while preserving known-invalid versus evaluator-error states."""

    gate_jobs = [job for job in plan.jobs if job.gate in {"artifact", "drc", "lvs", "constraint"}]
    gate_statuses = [_report_status(jobs.get(job.id)) for job in gate_jobs]
    # ``physical_valid`` is a derived report summary and is deliberately not
    # authoritative here.  Recompute G from the frozen plan's job identities
    # and their durable statuses so summary tampering cannot change a score.
    del physical_valid
    if _FAILED in gate_statuses:
        return 0.0
    if any(status in _UNKNOWN for status in gate_statuses):
        return None

    # Every declared job belongs to the frozen evaluation contract.  A
    # completed rejection is a known-invalid candidate; an error or a blocked
    # dependent is an evaluator state and cannot be converted into a score.
    statuses = [_report_status(jobs.get(job.id)) for job in plan.jobs]
    if any(_report_status(jobs.get(job.id)) == _FAILED
           for job in plan.jobs if job.id not in baseline_jobs):
        return 0.0
    if any(status in _UNKNOWN or status is None for status in statuses):
        return None
    if any(status != "passed" for status in statuses):
        return None
    return 1.0


def _raw_observation(metric: Metric, jobs: Mapping[str, Any], reference: str) -> tuple[str, float | None]:
    """Read one metric observation from its producing job's raw measurement."""

    job_id, measurement_name = reference.split(":")
    job = jobs.get(job_id)
    if not isinstance(job, Mapping) or job.get("status") != "passed":
        return "blocked", None
    measurements = job.get("measurements")
    measurement = measurements.get(measurement_name) if isinstance(measurements, Mapping) else None
    if not isinstance(measurement, Mapping):
        return "error", None
    value = measurement.get("value")
    unit = measurement.get("unit")
    if type(value) not in {int, float} or not math.isfinite(value):
        return "error", None
    if not isinstance(unit, str) or not unit or unit != metric.unit:
        return "error", None
    return ("passed" if _within(metric, value) else "failed"), value


def _empty_score(gate: float | None, *, area: dict | None = None) -> dict:
    return {
        "method": "layout-v1",
        "value": 0.0 if gate == 0.0 else None,
        "maximum": MAXIMUM,
        "components": {"G": gate, "E": None, "H": None, "Q": None},
        "dimensions": {},
        "metrics": {},
        "area": area,
    }


def score_layout(plan: EvaluationPlan, jobs: Mapping[str, Any],
                    metrics: Mapping[str, Any], physical_valid: bool | None) -> dict | None:
    """Compute the frozen versioned layout score from an evaluation report.

    ``None`` is returned for plans without a scoring declaration or for
    characterization/physical plans.  For a scored post-layout plan the
    returned object always has the stable score shape.  ``value`` is ``None``
    when the evaluator cannot establish validity, and zero when a completed
    gate rejects the candidate.  ``metrics`` and ``physical_valid`` are
    derived report summaries; raw job statuses and measurements are used for
    the score itself.
    """

    if plan.scoring is not None and plan.scoring.method == SCORING_METHOD:
        return score_layout_v2(plan, jobs)

    spec = plan.scoring
    if spec is None or plan.mode != "post_layout":
        return None

    if not isinstance(jobs, Mapping):
        raise TypeError("Evaluation jobs must be a mapping")
    gate = _job_state(plan, jobs, physical_valid)
    area_metric = next((metric for metric in plan.metrics if metric.id == spec.area_metric), None)
    if area_metric is None:
        # A parsed plan cannot reach this branch, but keeping the helper
        # fail-closed protects independent report consumers from stale plans.
        return _empty_score(gate)

    observations_by_metric = {
        metric.id: [_raw_observation(metric, jobs, reference)
                    for reference in metric.observations]
        for metric in plan.metrics
    }
    area_status, area_value = observations_by_metric[spec.area_metric][0]
    area_details = {
        "metric": spec.area_metric,
        "value": area_value,
        "target": spec.area_target,
        "zero": spec.area_zero,
        "Q": None,
    }
    if area_status == _FAILED:
        gate = 0.0
    elif area_status != "passed" or area_details["value"] is None or area_details["value"] <= 0:
        if gate != 0.0:
            gate = None
    else:
        area_details["Q"] = _clip((spec.area_zero - area_details["value"])
                                   / (spec.area_zero - spec.area_target))

    # A bounded physical requirement is part of candidate validity.  The
    # area metric is checked above because it also supplies Q; other physical
    # requirements must not let an otherwise perfect electrical result claim
    # a full score.
    for metric in plan.metrics:
        if metric.id == spec.area_metric:
            continue
        observations = observations_by_metric[metric.id]
        statuses = [status for status, _ in observations]
        if metric.category == "physical" and _FAILED in statuses:
            gate = 0.0
        elif any(status in _UNKNOWN for status in statuses) and gate != 0.0:
            gate = None
        elif any(status not in {"passed", _FAILED} for status in statuses) and gate != 0.0:
            # Every declared measurement is required to complete.  There is
            # no optional-metric marker in evaluation schema 1.
            gate = None

    if gate == 0.0:
        return _empty_score(0.0, area=area_details)
    if gate is None:
        return _empty_score(None, area=area_details)

    scored = [metric for metric in plan.metrics
              if metric.category == "performance" and metric.is_requirement]
    metric_scores: dict[str, float] = {}
    dimensions: dict[str, float] = {}
    for metric in scored:
        attainments = []
        observations = observations_by_metric[metric.id]
        for status, value in observations:
            if status in _UNKNOWN or status == "blocked" or value is None:
                return _empty_score(None, area=area_details)
            attainment = _attainment(metric, value)
            if attainment is None:
                return _empty_score(None, area=area_details)
            attainments.append(attainment)
        metric_scores[metric.id] = min(attainments)
        if metric.dimension is None:
            return _empty_score(None, area=area_details)
        dimensions[metric.dimension] = min(dimensions.get(metric.dimension, 1.0), metric_scores[metric.id])

    if not dimensions:
        return _empty_score(None, area=area_details)
    electrical = sum(dimensions.values()) / len(dimensions)
    all_requirements_pass = all(
        all(status == "passed" and _within(metric, value)
            for status, value in observations_by_metric[metric.id])
        for metric in scored
    )
    requirement = 1.0 if all_requirements_pass else 0.0
    quality = area_details["Q"]
    value = 60.0 * electrical + 20.0 * requirement + 20.0 * requirement * quality
    if requirement == 0.0 and value >= 60.0:
        value = math.nextafter(60.0, 0.0)
    return {
        "method": "layout-v1",
        "value": value,
        "maximum": MAXIMUM,
        "components": {"G": 1.0, "E": electrical, "H": requirement, "Q": quality},
        "dimensions": dict(sorted(dimensions.items())),
        "metrics": dict(sorted(metric_scores.items())),
        "area": area_details,
    }


def score_layout_v2(plan: EvaluationPlan, jobs: Mapping[str, Any]) -> dict:
    """Reference-relative quality; baseline 100, no maximum or acceptance bonus.

    Each scored metric takes its worst paired observation; dimensions and then
    electrical/area quality use geometric means. Functional failure is a zero,
    missing evidence is unknown. Candidate and source use the same testbench.
    """
    baseline_jobs = {ref.split(":")[0] for metric in plan.metrics for ref in metric.baseline}
    gate = _job_state(plan, jobs, baseline_jobs=baseline_jobs)
    score = {"method": SCORING_METHOD, "value": None, "maximum": None,
             "reference": 100, "components": {"G": gate, "E": None, "Q": None},
             "dimensions": {}, "metrics": {}, "area": None}
    if gate == 0:
        score["value"] = 0.0
        return score
    ratios: dict[str, list[float]] = {}
    observed = {metric.id: [_raw_observation(metric, jobs, ref) for ref in metric.observations]
                for metric in plan.metrics}
    if any(status == "failed" for values in observed.values() for status, _ in values):
        score["value"] = 0.0
        score["components"]["G"] = 0.0
        return score
    if gate is None or any(status != "passed" for values in observed.values() for status, _ in values):
        return score
    try:
        for metric in plan.metrics:
            observations = observed[metric.id]
            if metric.id == plan.scoring.area_metric:
                area = observations[0][1]
                if area <= 0:
                    return score
                quality = plan.scoring.area_target / area
                if not math.isfinite(quality) or quality <= 0:
                    return score
                score["area"] = {"metric": metric.id, "value": area,
                                 "target": plan.scoring.area_target, "Q": quality}
                score["components"]["Q"] = quality
            if not metric.baseline:
                continue
            values = []
            for (_, value), ref in zip(observations, metric.baseline, strict=True):
                status, baseline = _raw_observation(metric, jobs, ref)
                if status != "passed":
                    return score
                if metric.normalization == "target":
                    ratio = 1 / (1 + abs(value - baseline) / metric.scale)
                elif metric.normalization == "db20":
                    delta = (value - baseline) / 20
                    ratio = 10 ** (delta if metric.direction == "maximize" else -delta)
                else:
                    offset = metric.scale or 0.0
                    if min(value, baseline) < 0:
                        return score
                    numerator, denominator = ((value + offset, baseline + offset)
                                              if metric.direction == "maximize"
                                              else (baseline + offset, value + offset))
                    if denominator <= 0:
                        return score
                    ratio = numerator / denominator
                if not math.isfinite(ratio) or ratio < 0:
                    return score
                values.append(ratio)
            attainment = min(values)
            score["metrics"][metric.id] = attainment
            ratios.setdefault(metric.dimension, []).append(attainment)
        def geometric(values):
            if any(value == 0 for value in values):
                return 0.0
            return math.exp(sum(math.log(v) for v in values) / len(values))
        score["dimensions"] = {name: geometric(values) for name, values in sorted(ratios.items())}
        electrical = geometric(list(score["dimensions"].values()))
        quality = score["components"]["Q"]
        value = 100 * geometric([electrical, quality])
        if math.isfinite(value):
            score["components"]["E"] = electrical
            score["value"] = value
    except (OverflowError, ZeroDivisionError, TypeError, ValueError):
        # No finite, physically meaningful reference ratio can be established.
        pass
    return score


def _within(metric: Metric, value: Any) -> bool:
    if type(value) not in {int, float} or not math.isfinite(value):
        return False
    return ((metric.lower is None or value >= metric.lower)
            and (metric.upper is None or value <= metric.upper))


def recompute_score(plan: EvaluationPlan, report: Mapping[str, Any]) -> dict | None:
    """Independently recompute a report's task score from raw job evidence."""

    if not isinstance(report, Mapping):
        raise TypeError("Evaluation report must be a mapping")
    jobs = report.get("jobs", {})
    if not isinstance(jobs, Mapping):
        raise TypeError("Evaluation report jobs must be a mapping")
    return score_layout(plan, jobs, {}, None)


# Retain the former public entry point for historical report consumers.
score_layout_v1 = score_layout
