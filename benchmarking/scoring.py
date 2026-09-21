"""The single task score used by layout evaluations.

The score is intentionally independent of any runner or report writer.  A
sealed evaluation report can be passed to :func:`recompute_score` by a report
consumer and checked against the score written by ``evaluate.py``.

Scores use explicit metric and area weights after physical and functional
checks. Source simulation defines electrical quality 1; a fixed area reference
defines area quality 1. Scores are uncapped.

The evaluator's metric summaries are display data.  The scoring core derives
observation values and statuses from the raw job measurements so a report
consumer can independently recompute a score from the frozen plan and the
durable job evidence.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from .evaluation import EvaluationPlan, Metric

_FAILED = "failed"
_UNKNOWN = frozenset({"error", "blocked"})


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


def score_layout(plan: EvaluationPlan, jobs: Mapping[str, Any],
                 metrics: Mapping[str, Any], physical_valid: bool | None) -> dict | None:
    """Compute weighted quality from raw evidence and the frozen task plan.

    Display summaries do not determine the score. Rejection is zero; missing
    evidence is unknown. Unscored and physical-only plans return no score.
    """
    if plan.scoring is None or plan.mode != "post_layout":
        return None
    if not isinstance(jobs, Mapping):
        raise TypeError("Evaluation jobs must be a mapping")
    baseline_jobs = {ref.split(":")[0] for metric in plan.metrics for ref in metric.baseline}
    gate = _job_state(plan, jobs, baseline_jobs=baseline_jobs)
    score = {"method": plan.scoring.method, "value": None, "maximum": None,
             "reference": 100, "components": {"G": gate, "E": None, "Q": None},
             "dimensions": {}, "metrics": {}, "area": None}
    weights = dict(plan.scoring.weights)
    score["weights"] = weights
    if gate == 0:
        score["value"] = 0.0
        return score
    frozen = {name: {"status": "passed", "measurements": source["measurements"]}
              for name, source in plan.pre_layout.items()}
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
                status, baseline = _raw_observation(metric, frozen, ref)
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
        quality = score["components"]["Q"]
        electrical_values = [(score["metrics"][m.id], weights[m.id])
                             for m in plan.metrics if m.baseline]
        electrical = _weighted_geometric(electrical_values)
        score["dimensions"] = {
            name: _weighted_geometric([(score["metrics"][m.id], weights[m.id])
                                       for m in plan.metrics if m.baseline and m.dimension == name])
            for name in sorted(ratios)
        }
        value = 100 * _weighted_geometric(
            [*electrical_values, (quality, weights[plan.scoring.area_metric])])
        if math.isfinite(value):
            score["components"]["E"] = electrical
            score["value"] = value
    except (OverflowError, ZeroDivisionError, TypeError, ValueError):
        # No finite, physically meaningful reference ratio can be established.
        pass
    return score


def _weighted_geometric(values: list[tuple[float, float]]) -> float | None:
    """Normalize positive weights; zero-weight observations contribute no utility."""
    active = [(value, weight) for value, weight in values if weight > 0]
    if not active:
        return None
    if any(value == 0 for value, _ in active):
        return 0.0
    total = math.fsum(weight for _, weight in active)
    return math.exp(math.fsum(math.log(value) * (weight / total) for value, weight in active))


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
