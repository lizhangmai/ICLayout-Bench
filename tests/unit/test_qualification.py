"""Repeatability limits protect individual observations and ranking precision.

Synthetic report values isolate the publication policy; native extraction
repeatability is verified separately with Dataset witnesses.
"""
import json

import pytest

from benchmarking.engine.qualification import repeatability
from benchmarking.evaluation import EvaluationPlan, Metric

pytestmark = pytest.mark.unit


def fixture_reports():
    metric = Metric('response', 'performance', ('a:value', 'b:value'), 'V',
                    'maximize', 'max', -1, 1)
    plan = EvaluationPlan('characterization', (), (metric,), b'{}', 'json', None, '{}')
    reports = [{'metrics': {'response': {'value': 0.8}}, 'score': {'value': 50.0},
                'jobs': {name: {'measurements': {'value': {'value': value, 'unit': 'V'}}}
                         for name, value in [('a', 0.5), ('b', 0.8)]}} for _ in range(3)]
    return reports, plan


def test_repeatability_checks_each_corner_even_when_aggregate_and_score_are_unchanged():
    reports, plan = fixture_reports()
    initial = repeatability(reports, plan)
    limit = initial['observations']['response/a:value']['limit']
    reports[1]['jobs']['a']['measurements']['value']['value'] += limit / 2
    accepted = repeatability(reports, plan)
    assert accepted['within_limits'] and not accepted['observations_identical']
    reports[1]['jobs']['a']['measurements']['value']['value'] += 2 * limit
    rejected = repeatability(reports, plan)
    assert not rejected['within_limits']
    assert rejected['score_spread'] == 0


def test_repeatability_score_budget_is_absolute_and_rejects_excess_even_with_stable_metrics():
    reports, plan = fixture_reports()
    limit = repeatability(reports, plan)['policy']['score_spread']
    reports[1]['score']['value'] += limit
    assert repeatability(reports, plan)['within_limits']
    reports[1]['score']['value'] += 2 * limit
    assert not repeatability(reports, plan)['within_limits']


def test_repeatability_uses_declared_scale_for_near_zero_measurements():
    from dataclasses import replace
    reports, plan = fixture_reports()
    metric = replace(plan.metrics[0], lower=None, upper=None, scale=1e-6)
    plan = replace(plan, metrics=(metric,))
    for report in reports:
        for job in report['jobs'].values():
            job['measurements']['value']['value'] = 0.0
    limit = repeatability(reports, plan)['observations']['response/a:value']['limit']
    reports[1]['jobs']['a']['measurements']['value']['value'] = -limit / 2
    assert repeatability(reports, plan)['within_limits']
    assert repeatability(reports, plan)['observations']['response/a:value']['limit'] == limit
    # A frozen source observation is also a dimensional reference.
    metric = replace(metric, scale=None, baseline=('source:x', 'source:y'))
    plan = replace(plan, metrics=(metric,), pre_layout_json=json.dumps({
        'source': {'measurements': {'x': {'value': 1e-6}, 'y': {'value': 1e-6}}}}))
    assert repeatability(reports, plan)['observations']['response/a:value']['limit'] == limit


@pytest.mark.parametrize('invalid', [float('nan'), float('inf')])
def test_repeatability_rejects_nonfinite_observations(invalid):
    reports, plan = fixture_reports()
    reports[1]['jobs']['a']['measurements']['value']['value'] = invalid
    with pytest.raises(ValueError, match='finite'):
        repeatability(reports, plan)
