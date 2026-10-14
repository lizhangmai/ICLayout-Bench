"""Shared score arithmetic without cohort, evaluator or database policy."""

import math
from dataclasses import dataclass
from statistics import NormalDist, mean, stdev


@dataclass(frozen=True)
class ScoreSummary:
    measured: int
    mean: float | None
    sample_stddev: float | None


def score_summary(values):
    measured = [value for value in values if value is not None]
    return ScoreSummary(len(measured), mean(measured) if measured else None,
                        stdev(measured) if len(measured) > 1 else None)


def wilson(successes, count):
    """Two-sided 95% binomial score interval; an empty sample is unknown."""
    if type(count) is not int or type(successes) is not int or not 0 <= successes <= count:
        raise ValueError("Invalid binomial counts")
    if count == 0:
        return None
    z = NormalDist().inv_cdf(.975)
    rate = successes / count
    denominator = 1 + z*z/count
    center = (rate + z*z/(2*count)) / denominator
    half = z * math.sqrt(rate*(1-rate)/count + z*z/(4*count*count)) / denominator
    return [max(0.0, center-half), min(1.0, center+half)]


def resource_distribution(values):
    """Summarize nonnegative finite usage, retaining missing totals as unknown."""
    values = list(values)
    known = [v for v in values if type(v) in {int, float} and math.isfinite(v) and v >= 0]
    return {"count": len(values), "known": len(known), "missing": len(values)-len(known),
            "sum": sum(known) if known and len(known) == len(values) else None,
            "mean_known": sum(known)/len(known) if known else None,
            "min_known": min(known) if known else None, "max_known": max(known) if known else None}


def usage_summary(reports):
    """Summarize shared run reports; absent attempts retain unknown usage."""
    reports = list(reports)
    result = {field: resource_distribution((r.get("usage") or {}).get(field) if r else None for r in reports)
              for field in ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_output_tokens", "cost")}
    result["wall_seconds"] = resource_distribution(r.get("elapsed_seconds") if r else None for r in reports)
    return result


def inference_summary(reports):
    """Aggregate gateway evidence without treating tokens as compute."""
    failed = {"service_error", "http_error", "protocol_or_transport_error", "incomplete_error", "cancelled"}
    gateways = [r["inference"] for r in reports
                if isinstance(r, dict) and isinstance(r.get("inference"), dict)]
    requests = [event for gateway in gateways for event in gateway.get("requests", [])]
    outcomes = [event.get("outcome") for event in requests]
    usage = {}
    for field in ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_output_tokens", "cost"):
        distribution = resource_distribution((event.get("usage") or {}).get(field) for event in requests)
        usage[field] = {"known": distribution["known"], "missing": distribution["missing"],
                        "total": distribution["sum"]}
    return {"forwarded": len(requests),
            "denied": sum((gateway.get("denied_requests") or 0) for gateway in gateways),
            "failed": sum(outcome in failed for outcome in outcomes),
            "truncated": sum(outcome == "budget_truncated" for outcome in outcomes),
            "content_filtered": sum(outcome == "content_filtered" for outcome in outcomes),
            "cancelled": sum(outcome == "cancelled" for outcome in outcomes),
            "wall_seconds": resource_distribution(gateway.get("wall_seconds") for gateway in gateways),
            "usage": usage}


def planned_score_summary(values, scheduled):
    """Summarize selected observations against an explicit planned sample count.

    A missing observation and an observed unknown score remain distinct. The
    complete-sample mean is unknown until every planned score is known. Callers
    select the observations and verify their task, condition and attempt bindings.
    """
    values = list(values)
    if type(scheduled) is not int or scheduled <= 0 or len(values) > scheduled:
        raise ValueError("Invalid planned sample count")
    if any(value is not None and (type(value) not in {int, float} or not math.isfinite(value))
           for value in values):
        raise ValueError("Scores must be finite numbers or unknown")
    known = score_summary(values)
    missing, unknown = scheduled - len(values), len(values) - known.measured
    complete = missing == 0 and unknown == 0
    return {"scheduled": scheduled, "measured": len(values), "known": known.measured,
            "missing": missing, "unknown": unknown, "complete": complete,
            "value": known.mean if complete else None}


def weighted_score(values):
    """Coefficient-weighted mean; any unknown task keeps the suite score unknown.

    Values are explicit (coefficient, score) pairs. Suite membership, task
    coefficients and comparable conditions are validated by the caller.
    """
    values = list(values)
    if not values:
        return None
    for coefficient, value in values:
        if (type(coefficient) not in {int, float} or not math.isfinite(coefficient) or coefficient <= 0
                or value is not None and (type(value) not in {int, float} or not math.isfinite(value))):
            raise ValueError("Invalid weighted score")
    if any(value is None for _, value in values):
        return None
    return sum(coefficient * value for coefficient, value in values) / sum(coefficient for coefficient, _ in values)
