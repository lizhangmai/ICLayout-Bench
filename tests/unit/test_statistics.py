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


def price_table(**overrides):
    return {"currency": "USD", "source": "https://provider.example/pricing", "as_of": "2026-10-16",
            "input_per_million": 2, "cache_read_per_million": .2,
            "cache_write_per_million": 2.5, "output_per_million": 10, **overrides}


def test_model_cost_distinguishes_cache_reads_writes_and_reasoning_without_double_counting():
    from benchmarking.results.usage import (
        UsageEvidence,
        request_record,
        summarize_usage,
    )

    call = request_record("a", "model", input_tokens=1000, cached=700, written=100,
                          output=50, reasoning=30, seconds=2)
    report = summarize_usage(UsageEvidence([call, call]), model="model", pricing=price_table(), wall_seconds=20)
    assert report["tokens"] == {"input_tokens": 1000, "uncached_input_tokens": 200,
        "cached_input_tokens": 700, "cache_write_input_tokens": 100, "output_tokens": 50, "reasoning_output_tokens": 30}
    assert report["cost"] == pytest.approx(.00129)
    assert report["cost_source"] == "api_token_pricing"
    assert report["api_seconds"] == 2
    assert report["wall_seconds"] == 20
    assert report["request_count"] == 1


def test_native_cost_including_zero_is_used_without_repricing():
    from benchmarking.results.usage import (
        UsageEvidence,
        request_record,
        summarize_usage,
    )

    call = request_record("a", "model", input_tokens=1000, cached=0, written=0, output=100, cost=0)
    report = summarize_usage(UsageEvidence([call]), model="model", pricing=price_table())
    assert report["cost"] == 0 and report["cost_source"] == "provider"
    report = summarize_usage(UsageEvidence([call], reported_cost=.7), model="model", pricing=price_table())
    assert report["cost"] == .7 and report["cost_source"] == "harness_reported"
    assert report["api_seconds"] is None


def test_model_pricing_uses_each_requests_context_length_and_keeps_unpriced_models_unknown():
    from benchmarking.results.usage import (
        UsageEvidence,
        request_record,
        summarize_usage,
        validate_pricing,
    )

    rates = price_table(long_context_threshold=1000, long_context={
        "input_per_million": 4, "cache_read_per_million": .4,
        "cache_write_per_million": 5, "output_per_million": 15})
    validate_pricing(rates)
    call = request_record("a", "model", input_tokens=2000, cached=1000, written=0, output=100)
    report = summarize_usage(UsageEvidence([call]), model="model", pricing=rates)
    assert report["cost"] == pytest.approx(.0059)
    unknown = request_record("b", "other-model", input_tokens=100, cached=0, written=0, output=10)
    partial = summarize_usage(UsageEvidence([call, unknown]), model="model", pricing=rates)
    assert partial["cost"] is None and partial["coverage"]["cost"] == {"known": 1, "missing": 1}
    invalid = request_record("c", "model", input_tokens=100, cached=101, written=0, output=10)
    assert summarize_usage(UsageEvidence([invalid]), model="model", pricing=rates)["cost"] is None
    rates['models'] = {'other-model': {'input_per_million': 1, 'cache_read_per_million': .1,
                                     'cache_write_per_million': 0, 'output_per_million': 5}}
    validate_pricing(rates)
    other = summarize_usage(UsageEvidence([unknown]), model='model', pricing=rates)
    assert other['cost'] == pytest.approx(.00015)


@pytest.mark.parametrize("started,expected", [
    ("2026-10-16T01:00:00Z", .003), ("2026-10-16T04:00:00Z", .0015),
    ("2026-10-17T01:00:00Z", .0015), ("2026-10-01T01:00:00Z", .0015), (None, None),
])
def test_peak_and_off_peak_prices_respect_utc_boundaries_weekends_and_explicit_holidays(started, expected):
    from benchmarking.results.usage import (
        UsageEvidence,
        request_record,
        summarize_usage,
    )

    rates = price_table(input_per_million=2, output_per_million=10,
        peak_utc_hours=["01:00-04:00", "06:00-10:00"], off_peak_dates=["2026-10-01"],
        off_peak={"input_per_million": 1, "cache_read_per_million": .1,
                  "cache_write_per_million": 1.25, "output_per_million": 5})
    call = request_record("a", "model", input_tokens=1000, cached=0, written=0, output=100, started_at=started)
    report = summarize_usage(UsageEvidence([call]), model="model", pricing=rates)
    assert report["cost"] == pytest.approx(expected) if expected is not None else report["cost"] is None


def test_task_usage_aggregation_preserves_missing_tasks_and_currencies():
    from benchmarking.results.statistics import model_usage_summary

    a = {"tokens": {"output_tokens": 100}, "api_seconds": 2, "cost": 1, "currency": "USD"}
    b = {"tokens": {"output_tokens": 300}, "api_seconds": 6, "cost": 3, "currency": "USD"}
    report = model_usage_summary([a, b])
    assert report["cost_per_task"] == 2
    assert report["tokens"]["output_tokens"]["sum"] == 400
    assert report["api_seconds"]["sum"] == 8
    assert model_usage_summary([a, None])["cost_per_task"] is None
    assert model_usage_summary([a, {**b, "currency": "CNY"}])["cost_per_task"] is None
    assert model_usage_summary([a, {**b, "api_seconds": None}])["api_seconds"]["sum"] is None


def test_replaced_attempt_costs_use_their_own_snapshots_and_missing_attempts_stay_unknown():
    from benchmarking.results.usage import (
        UsageEvidence,
        combine_usage,
        request_record,
        summarize_usage,
    )

    call = request_record('r1', 'model', input_tokens=1000, cached=0, written=0, output=100, seconds=2)
    first = summarize_usage(UsageEvidence([call]), model='model', pricing=price_table(), wall_seconds=10)
    second = summarize_usage(UsageEvidence([call], reported_cost=1), model='model', wall_seconds=20)
    combined = combine_usage([first, second])
    assert combined['cost'] == pytest.approx(1.003)
    assert combined['api_seconds'] == 4
    assert combined['wall_seconds'] == 30
    assert len({r['id'] for r in combined['requests']}) == 2
    assert combined['cost_source'] == 'mixed'
    assert combine_usage([None, second])['cost'] is None


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
