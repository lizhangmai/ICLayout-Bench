import copy
import json
import math
import tomllib
from typing import ClassVar

import pytest
from test_evaluate import PLAN, evaluate

from benchmarking.engine.evaluate import run_evaluation
from benchmarking.evaluation import parse_evaluation
from benchmarking.scoring import recompute_score

pytestmark = pytest.mark.unit
pytest_plugins = ["test_evaluate"]


def test_missing_unbounded_metric_measurement_is_not_a_numeric_score(
        tmp_path, inputs, bindings):
    raw = PLAN + b'''
[[metrics]]
id = "diagnostic"
category = "performance"
observations = ["nominal:diagnostic"]
unit = "s"
direction = "minimize"
aggregation = "min"
'''
    report = evaluate(tmp_path, inputs, bindings, raw)
    assert report["metrics"]["diagnostic"]["status"] == "error"
    assert report["outcome"] == "error"
    assert report["score"]["value"] is None


def test_area_metric_must_use_the_candidate_constraint_check():
    data = tomllib.loads(PLAN.decode())
    for job in data["jobs"]:
        if job["id"] == "geometry":
            job["inputs"] = {"layout": "input:netlist"}
    data["jobs"].append({
        "id": "candidate_geometry", "stage": "check", "operation": "check",
        "gate": "constraint", "inputs": {"layout": "candidate"},
        "requires": ["artifact", "drc", "lvs"],
    })
    with pytest.raises(ValueError, match="candidate constraint check"):
        parse_evaluation(json.dumps(data).encode(), file_format="json")


# The existing synthetic circuit owns the DAG and units. These controls protect
# the new public reference-relative arithmetic, uncapped improvements and missing
# baseline semantics; expected values follow the stated ratios, not engine output.
def reference_plan(**metric_changes):
    data = tomllib.loads(PLAN.decode())
    metric = data["metrics"][0]
    metric.pop("upper")
    metric.update(lower=0, baseline=["source_" + ref for ref in metric["observations"]],
                  normalization="ratio", **metric_changes)
    for job in data["pre_layout"]["jobs"].values():
        job["measurements"]["delay"]["value"] = 2 * job["parameters"]["load"]
    return data


class ReferenceSimulator:
    identity: ClassVar[dict] = {"adapter": "synthetic-reference", "version": "1"}

    def run(self, job, inputs):
        from benchmarking.engine.evaluate import JobResult, Measurement
        # Source and extracted circuits traverse the real engine's input resolver.
        source = inputs["dut"].content == b"schematic"
        assert source or inputs["dut"].content == b"derived-from-layout"
        value = job.parameters["load"] * (2 if source else 1)
        return JobResult("passed", measurements={"delay": Measurement(value, "s")},
                         evidence={"log": inputs["dut"]})


def reference_report(tmp_path, inputs, bindings):
    plan = parse_evaluation(json.dumps(reference_plan()).encode(), file_format="json")
    report = run_evaluation(plan, inputs, {**bindings, "response": ReferenceSimulator()}, tmp_path / "reference")
    return plan, report


def test_reference_scores_are_continuous_uncapped_and_recomputable(tmp_path, inputs, bindings):
    plan, report = reference_report(tmp_path, inputs, bindings)
    score = report["score"]
    assert report["outcome"] == "passed"
    assert score["maximum"] is None and score["reference"] == 100
    assert score["value"] == pytest.approx(100 * math.sqrt(2 / 1.5))
    assert score["value"] > 100
    assert score == recompute_score(plan, report)
    # A worse observation remains visible even when the other observation improves.
    report["jobs"]["slow"]["measurements"]["delay"]["value"] = 8
    score = recompute_score(plan, report)
    assert score["components"]["E"] == pytest.approx(0.5)
    assert score["value"] == pytest.approx(100 * math.sqrt(0.5 / 1.5))


@pytest.mark.parametrize("defect", ["missing", "unit", "nonfinite"])
def test_invalid_frozen_source_evidence_is_rejected(defect):
    data = reference_plan()
    source = data["pre_layout"]["jobs"]["source_nominal"]
    if defect == "missing":
        source["measurements"].clear()
    elif defect == "unit":
        source["measurements"]["delay"]["unit"] = "V"
    else:
        source["measurements"]["delay"]["value"] = float("nan")
    with pytest.raises(ValueError):
        parse_evaluation(json.dumps(data).encode(), file_format="json")


def test_function_failure_is_zero_without_a_degradation_cutoff(tmp_path, inputs, bindings):
    plan, report = reference_report(tmp_path, inputs, bindings)
    report["jobs"]["slow"]["measurements"]["delay"]["value"] = 1000
    assert 0 < recompute_score(plan, report)["value"] < 10
    report["jobs"]["slow"]["measurements"]["delay"]["value"] = -1
    assert recompute_score(plan, report)["value"] == 0


@pytest.mark.parametrize("normalization,direction,unit,scale,post,source,expected", [
    ("db20", "maximize", "dB", None, 26.020599913279625, 20, 2),
    ("target", "target", "V", 1, -0.5, 0, 2 / 3),
    ("ratio", "minimize", "s", 0.001, 0, 0, 1),
    ("ratio", "maximize", "s", None, 0, 1, 0),
])
def test_reference_normalization_handles_db_signed_targets_and_zero(
        tmp_path, inputs, bindings, normalization, direction, unit, scale, post, source, expected):
    _, report = reference_report(tmp_path, inputs, bindings)
    data = reference_plan()
    metric = data["metrics"][0]
    metric.update(normalization=normalization, direction=direction, unit=unit)
    if normalization != "ratio":
        metric.pop("lower")
        # A separate functional measurement keeps the required functional gate.
        function = copy.deepcopy(metric)
        for key in ("dimension", "baseline", "normalization"):
            function.pop(key)
        function.update(id="functional", direction="minimize", upper=100)
        data["metrics"].append(function)
    if scale is not None:
        metric["scale"] = scale
    for job in report["jobs"].values():
        if "delay" in job.get("measurements", {}):
            job["measurements"]["delay"].update(unit=unit, value=post)
    for name in ("source_nominal", "source_slow"):
        data["pre_layout"]["jobs"][name]["measurements"]["delay"].update(value=source, unit=unit)
    plan = parse_evaluation(json.dumps(data).encode(), file_format="json")
    assert recompute_score(plan, report)["components"]["E"] == pytest.approx(expected)


@pytest.mark.parametrize("defect", ["candidate", "parameters", "deck", "unpaired"])
def test_baseline_requires_independent_same_condition_source_simulation(defect):
    data = reference_plan()
    source = data["pre_layout"]["jobs"]["source_nominal"]
    if defect == "candidate":
        source["inputs"]["dut"] = "job:parasitics:netlist"
    elif defect == "parameters":
        source["parameters"]["load"] = 99
    elif defect == "deck":
        source["inputs"]["deck"] = "input:different"
    else:
        data["metrics"][0]["baseline"].pop()
    with pytest.raises(ValueError):
        parse_evaluation(json.dumps(data).encode(), file_format="json")


def test_frozen_baseline_is_not_simulated_and_changed_input_is_rejected(tmp_path, inputs, bindings):
    from benchmarking.files import Asset

    class PostOnly(ReferenceSimulator):
        def run(self, job, inputs):
            assert inputs['dut'].content == b'derived-from-layout'
            return super().run(job, inputs)

    plan = parse_evaluation(json.dumps(reference_plan()).encode(), file_format='json')
    report = run_evaluation(plan, inputs, {**bindings, 'response': PostOnly()}, tmp_path / 'post-only')
    assert report['task_success'] is True
    assert not (plan.pre_layout.keys() & report['jobs'].keys())
    expected = recompute_score(plan, report)
    report['jobs']['source_nominal'] = {
        'status': 'passed', 'measurements': {'delay': {'value': 999999, 'unit': 's'}}}
    assert recompute_score(plan, report) == expected
    inputs['input:netlist'] = Asset(b'changed-source', 'spice')
    with pytest.raises(ValueError, match='Frozen pre-layout input changed'):
        run_evaluation(plan, inputs, bindings, tmp_path / 'stale-reference')
    assert not (tmp_path / 'stale-reference').exists()


def test_extreme_finite_area_does_not_emit_nonfinite_score_evidence(tmp_path, inputs, bindings):
    _, report = reference_report(tmp_path, inputs, bindings)
    data = reference_plan()
    data['scoring']['area_target'] = 1e308
    plan = parse_evaluation(json.dumps(data).encode(), file_format='json')
    report['jobs']['geometry']['measurements']['area']['value'] = 1e-308
    score = recompute_score(plan, report)
    assert score['value'] is None
    json.dumps(score, allow_nan=False)


# Explicit weights protect task priorities from dimension size and from diagnostics.
# The existing source/candidate control supplies ratios of 2 (delay), 1/2 (power)
# and 2/3 (area); expectations below follow the product of declared exponents.
def weighted_plan():
    data = reference_plan()
    data['scoring'].update(method='layout', rationale='Delay first, then power and area.',
                           weights={'delay': 0.6, 'power': 0.2, 'functional_area': 0.2})
    power = copy.deepcopy(data['metrics'][0])
    power.update(id='power', dimension='supply', direction='maximize')
    data['metrics'].append(power)
    return data


def test_explicit_weights_control_tradeoffs_and_ignore_dimension_grouping(tmp_path, inputs, bindings):
    _, report = reference_report(tmp_path, inputs, bindings)
    data = weighted_plan()
    plan = parse_evaluation(json.dumps(data).encode(), file_format='json')
    score = recompute_score(plan, report)
    assert score['value'] == pytest.approx(100 * 2**0.6 * 0.5**0.2 * (2/3)**0.2)
    assert score['weights'] == data['scoring']['weights']
    assert score['components']['E'] == pytest.approx(2**0.75 * 0.5**0.25)
    # Display edits cannot rewrite the frozen policy or the raw observations.
    report['score'] = {'weights': {'power': 1}, 'value': 0}
    report['metrics']['delay']['value'] = 10000
    assert recompute_score(plan, report) == score
    data['metrics'][-1]['dimension'] = 'response'
    regrouped = parse_evaluation(json.dumps(data).encode(), file_format='json')
    assert recompute_score(regrouped, report)['value'] == pytest.approx(score['value'])
    data['scoring']['weights'].update(delay=0.2, power=0.6)
    power_first = parse_evaluation(json.dumps(data).encode(), file_format='json')
    assert recompute_score(power_first, report)['value'] < score['value']


def test_zero_weight_excludes_quality_but_not_measurement_or_function_checks(tmp_path, inputs, bindings):
    _, report = reference_report(tmp_path, inputs, bindings)
    data = weighted_plan()
    data['scoring']['weights'].update(delay=0.8, power=0)
    plan = parse_evaluation(json.dumps(data).encode(), file_format='json')
    # A valid zero utility on an excluded observation does not erase the score.
    data['metrics'][-1].update(observations=['nominal:power'], baseline=['source_nominal:power'])
    report['jobs']['nominal']['measurements']['power'] = {'value': 0, 'unit': 's'}
    data['pre_layout']['jobs']['source_nominal']['measurements']['power'] = {'value': 1, 'unit': 's'}
    plan = parse_evaluation(json.dumps(data).encode(), file_format='json')
    score = recompute_score(plan, report)
    assert score['value'] == pytest.approx(100 * 2**0.8 * (2/3)**0.2)
    assert score['dimensions']['supply'] is None
    report['jobs']['nominal']['measurements']['power']['value'] = -1
    assert recompute_score(plan, report)['value'] == 0
    report['jobs']['nominal']['measurements']['power'].pop('value')
    assert recompute_score(plan, report)['value'] is None


@pytest.mark.parametrize('weights', [
    {'delay': 1},  # area omitted
    {'delay': 0.5, 'power': 0.3, 'functional_area': 0.2, 'typo': 0},
    {'delay': -0.1, 'power': 0.9, 'functional_area': 0.2},
    {'delay': 0.6, 'power': 0.3, 'functional_area': 0.2},
    {'delay': True, 'power': 0, 'functional_area': 0},
    {'delay': 0, 'power': 0, 'functional_area': 1},
])
def test_weight_schema_rejects_incomplete_or_ambiguous_policies(weights):
    data = weighted_plan()
    data['scoring']['weights'] = weights
    with pytest.raises((TypeError, ValueError)):
        parse_evaluation(json.dumps(data).encode(), file_format='json')


def test_weighted_evaluation_and_report_rendering(tmp_path, inputs, bindings):
    from benchmarking.engine.execution import _zero_attempt_score
    from benchmarking.participants.results import report_text

    plan = parse_evaluation(json.dumps(weighted_plan()).encode(), file_format='json')
    report = run_evaluation(plan, inputs, {**bindings, 'response': ReferenceSimulator()}, tmp_path / 'weighted')
    assert report['task_success'] is True
    assert report['score'] == recompute_score(plan, report)
    rendered = report_text({'evaluation': report, 'summary': {'score': report['score']['value']},
                            'identity': {'plan': [{}]}}).decode()
    assert 'product(q_i ** w_i)' in rendered and '| delay | 0.6 |' in rendered
    assert 'maximum = 100' not in rendered
    zero = _zero_attempt_score('layout')
    assert zero['method'] == 'layout' and zero['value'] == 0 and zero['maximum'] is None
