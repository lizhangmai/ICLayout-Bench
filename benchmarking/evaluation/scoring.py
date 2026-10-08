"""The single task score used by layout evaluations.

The score is intentionally independent of any runner or report writer.  A
sealed evaluation report can be passed to :func:`recompute_score` by a report
consumer and checked against the score written by ``evaluate.py``.

Scores use explicit metric and area weights after physical and functional
checks. Declared quality targets (or source simulation when no target is given)
define electrical quality 1; a fixed area target defines area quality 1.
Each metric is capped at quality 1 before aggregation; scores range from 0 to 100.

The evaluator's metric summaries are display data.  The scoring core derives
observation values and statuses from the raw job measurements so a report
consumer can independently recompute a score from the frozen plan and the
durable job evidence.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from .contracts import EvaluationPlan, Metric

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


def _relative_quality(metric: Metric, value: float, baseline: float) -> float:
    """Normalize one paired condition against its declared quality anchor."""
    if metric.normalization in {"ratio", "saturating_ratio"} and min(value, baseline) < 0:
        raise ValueError("Ratio normalization requires nonnegative observations")
    if metric.quality_target is not None:
        baseline = metric.quality_target
    if metric.normalization == "target":
        ratio = 1 / (1 + abs(value - baseline) / metric.scale)
    elif metric.normalization == "db20":
        delta = (value - baseline) / 20
        ratio = 10 ** (delta if metric.direction == "maximize" else -delta)
    else:
        offset = metric.scale or 0.0
        if min(value, baseline) < 0:
            raise ValueError("Ratio normalization requires nonnegative observations")
        # Scale before adding to keep the bounded rule finite even when finite
        # observations would overflow an ordinary ratio.
        if metric.normalization == "saturating_ratio":
            size = max(value, baseline, offset)
            numerator = baseline / size + offset / size
            denominator = value / size + offset / size
            ratio = 2 * numerator / (numerator + denominator)
        else:
            numerator, denominator = ((value + offset, baseline + offset)
                                      if metric.direction == "maximize"
                                      else (baseline + offset, value + offset))
            if denominator <= 0:
                raise ValueError("Ratio normalization has a nonpositive denominator")
            ratio = numerator / denominator
    if not math.isfinite(ratio) or ratio < 0:
        raise ValueError("Metric normalization did not produce a finite quality factor")
    return ratio


def score_breakdown(plan: EvaluationPlan, jobs: Mapping[str, Any],
                    score: Mapping[str, Any] | None) -> dict | None:
    """Build final per-condition evidence for the reported score.

    The output includes source measurement values used by the scoring formula,
    but never includes the evaluation plan, tool inputs, or reference assets.
    """
    if plan.scoring is None or plan.mode != "post_layout":
        return None
    weights = dict(plan.scoring.weights)
    frozen = {name: {"status": "passed", "measurements": source["measurements"]}
              for name, source in plan.pre_layout.items()}
    score = score if isinstance(score, Mapping) else {}
    breakdown = {
        "maximum": score.get("maximum"),
        "value": score.get("value"),
        "reference": score.get("reference", 100),
        "components": score.get("components", {"G": None, "E": None, "Q": None}),
        "dimensions": score.get("dimensions", {}),
        "weights": weights,
        "metrics": {},
        "omitted_metrics": 0,
        "area": None,
    }
    for metric in plan.metrics:
        if metric.id == plan.scoring.area_metric:
            status, value = _raw_observation(metric, jobs, metric.observations[0])
            quality = (plan.scoring.area_target / value
                       if value is not None and value > 0 else None)
            if quality is not None and not math.isfinite(quality):
                quality = None
            breakdown["area"] = {
                "metric": metric.id,
                "status": status,
                "value": value,
                "target": plan.scoring.area_target,
                "quality_factor": quality,
                "credited_quality": min(1.0, quality) if quality is not None else None,
                "weight": weights[metric.id],
            }
            continue
        if not metric.baseline:
            continue
        pairs = []
        for candidate_ref, source_ref in zip(metric.observations, metric.baseline, strict=True):
            candidate_status, candidate_value = _raw_observation(metric, jobs, candidate_ref)
            source_status, source_value = _raw_observation(metric, frozen, source_ref)
            quality = None
            if candidate_value is not None and source_value is not None:
                try:
                    quality = _relative_quality(metric, candidate_value, source_value)
                except (OverflowError, ZeroDivisionError, TypeError, ValueError):
                    pass
            pairs.append({
                "candidate_observation": candidate_ref,
                "candidate_status": candidate_status,
                "candidate_value": candidate_value,
                "source_observation": source_ref,
                "source_status": source_status,
                "source_value": source_value,
                "quality_target": metric.quality_target if metric.quality_target is not None else source_value,
                "quality_factor": quality,
                "credited_quality": min(1.0, quality) if quality is not None else None,
            })
        reported_quality = (score.get("metrics", {}).get(metric.id)
                            if isinstance(score.get("metrics"), Mapping) else None)
        pair_qualities = [pair["quality_factor"] for pair in pairs]
        if reported_quality is None and pairs and all(value is not None for value in pair_qualities):
            # A failed requirement can gate the official score before it stores
            # metric factors. Keep the paired diagnostic useful while the G
            # component explains why it did not affect the total.
            reported_quality = min(pair_qualities)
        breakdown["metrics"][metric.id] = {
            "dimension": metric.dimension,
            "unit": metric.unit,
            "direction": metric.direction,
            "normalization": metric.normalization,
            "scale": metric.scale,
            "quality_target": metric.quality_target,
            "quality_target_rationale": metric.quality_target_rationale,
            "quality_aggregation": "minimum",
            "aggregate_quality": reported_quality,
            "credited_quality": min(1.0, reported_quality) if reported_quality is not None else None,
            "weight": weights[metric.id],
            "observations": pairs,
            "omitted_observations": 0,
        }
    return breakdown


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
    score = {"method": plan.scoring.method, "value": None, "maximum": 100,
             "reference": 100, "components": {"G": gate, "E": None, "Q": None},
             "dimensions": {}, "metrics": {}, "credited_metrics": {}, "area": None}
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
                                 "target": plan.scoring.area_target, "Q": quality,
                                 "credited_quality": min(1.0, quality)}
                score["components"]["Q"] = min(1.0, quality)
            if not metric.baseline:
                continue
            values = []
            for (_, value), ref in zip(observations, metric.baseline, strict=True):
                status, baseline = _raw_observation(metric, frozen, ref)
                if status != "passed":
                    return score
                values.append(_relative_quality(metric, value, baseline))
            attainment = min(values)
            score["metrics"][metric.id] = attainment
            score["credited_metrics"][metric.id] = min(1.0, attainment)
            ratios.setdefault(metric.dimension, []).append(attainment)
        quality = score["components"]["Q"]
        electrical_values = [(score["credited_metrics"][m.id], weights[m.id])
                             for m in plan.metrics if m.baseline]
        electrical = _weighted_geometric(electrical_values)
        score["dimensions"] = {
            name: _weighted_geometric([(score["credited_metrics"][m.id], weights[m.id])
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
