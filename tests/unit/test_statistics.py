"""Shared arithmetic preserves planned coverage and unknown resource usage."""

from statistics import NormalDist

import pytest

from benchmarking.results.statistics import (
    inference_summary,
    planned_score_summary,
    resource_distribution,
    usage_summary,
    weighted_score,
    wilson,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("successes,count", [(0, 3), (3, 3), (5, 10), (2, 7)])
def test_wilson_inverts_the_binomial_score_test(successes, count):
    low, high = wilson(successes, count)
    observed = successes / count
    z = NormalDist().inv_cdf(.975)
    assert 0 <= low <= observed <= high <= 1
    for endpoint in (low, high):
        assert (observed - endpoint) ** 2 == pytest.approx(
            z ** 2 * endpoint * (1 - endpoint) / count, abs=1e-12)
    if successes == 0:
        assert low == 0
    if successes == count:
        assert high == 1


def test_wilson_needs_consistent_observations():
    assert wilson(0, 0) is None
    for successes, count in [(4, 3), (-1, 3), (True, 3), (0, -1)]:
        with pytest.raises(ValueError):
            wilson(successes, count)


def test_resource_totals_remain_unknown_with_missing_or_invalid_usage():
    summary = resource_distribution(iter([0, 4, None, -1, True, float("nan")]))
    assert summary == {"count": 6, "known": 2, "missing": 4, "sum": None,
                       "mean_known": 2, "min_known": 0, "max_known": 4}
    assert resource_distribution([])["sum"] is None
    assert resource_distribution([0, 0])["sum"] == 0


def test_usage_summary_keeps_attempts_with_no_report():
    summary = usage_summary([{"elapsed_seconds": 2, "usage": {"input_tokens": 10}}, None])
    assert summary["wall_seconds"]["count"] == 2
    assert summary["wall_seconds"]["missing"] == 1
    assert summary["wall_seconds"]["sum"] is None
    assert summary["input_tokens"]["mean_known"] == 10
    assert summary["output_tokens"]["known"] == 0


def test_gateway_summary_keeps_failed_requests_and_missing_cost():
    reports = [{"inference": {"wall_seconds": 5, "denied_requests": 2, "requests": [
        {"outcome": "completed", "usage": {"input_tokens": 3, "cost": 0}},
        {"outcome": "cancelled", "usage": {"input_tokens": 7}},
        {"outcome": "budget_truncated", "usage": {"input_tokens": 0}},
    ]}}]
    summary = inference_summary(reports)
    assert summary["forwarded"] == 3 and summary["denied"] == 2
    assert summary["failed"] == 1 and summary["cancelled"] == 1 and summary["truncated"] == 1
    assert summary["usage"]["input_tokens"] == {"known": 3, "missing": 0, "total": 10}
    assert summary["usage"]["cost"] == {"known": 1, "missing": 2, "total": None}


@pytest.mark.parametrize("values,missing,unknown,value", [
    ([0, 100], 0, 0, 50), ([100], 1, 0, None), ([100, None], 0, 1, None), ([], 2, 0, None),
])
def test_planned_scores_distinguish_missing_observations_from_unknown_scores(values, missing, unknown, value):
    summary = planned_score_summary(iter(values), 2)
    assert summary["missing"] == missing and summary["unknown"] == unknown
    assert summary["value"] == value
    assert summary["complete"] == (missing == 0 and unknown == 0)


@pytest.mark.parametrize("values,scheduled", [([1, 2], 1), ([], 0), ([True], 1), ([float("inf")], 1)])
def test_planned_scores_reject_extra_observations_and_nonfinite_values(values, scheduled):
    with pytest.raises(ValueError):
        planned_score_summary(values, scheduled)


def test_weighted_scores_use_the_full_task_set():
    assert weighted_score([(1, 100), (6, 50), (10, 0)]) == pytest.approx(400 / 17)
    assert weighted_score([(1, 100), (6, None), (10, 0)]) is None
    assert weighted_score([]) is None
    with pytest.raises(ValueError):
        weighted_score([(0, 100)])
