import copy
import json
import math
import tomllib
from typing import ClassVar

import pytest
from test_evaluate import PLAN, evaluate

from benchmarking.engine.evaluate import run_evaluation
from benchmarking.evaluation import parse_evaluation
from benchmarking.evaluation.scoring import recompute_score

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
# the new public target-relative arithmetic, per-metric caps and missing
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


def test_unbounded_scored_reference_can_qualify_at_low_score_but_limits_still_gate(
        tmp_path, inputs, bindings):
    from benchmarking.engine.evaluate import JobResult, Measurement
    from benchmarking.files import Asset

    class DegradedCandidateSimulator(ReferenceSimulator):
        def run(self, job, assets):
            assert assets["dut"].content == b"derived-from-layout"
            return JobResult("passed", measurements={
                "delay": Measurement(1000 * job.parameters["load"], "s")
            }, evidence={"waveform": Asset(b"finite degraded candidate waveform", "text")})

    unbounded = reference_plan()
    unbounded["metrics"][0].pop("lower")
    plan = parse_evaluation(json.dumps(unbounded).encode(), file_format="json")
    from benchmarking.engine.qualification import audit
    assert audit(plan)['minimum_score'] is None
    report = run_evaluation(plan, inputs, {**bindings, "response": DegradedCandidateSimulator()},
                            tmp_path / "unbounded")

    assert report["physical_valid"] is True
    assert report["metrics"]["delay"]["status"] == "passed"
    assert report["specs_pass"] is None
    assert report["outcome"] == "passed"
    assert report["task_success"] is True
    assert report["quality_eligible"] is True
    assert 0 < report["score"]["value"] < 10
    assert report["score"]["value"] == pytest.approx(100 * math.sqrt((2 / 1000) * (1 / 1.5)))
    assert report["score"] == recompute_score(plan, report)
    assert all(report["jobs"][job]["inputs"]["dut"]["sha256"]
               == report["jobs"]["parasitics"]["outputs"]["netlist"]["sha256"]
               for job in ("nominal", "slow"))

    bounded = copy.deepcopy(unbounded)
    bounded["metrics"][0]["requirement"] = {
        "upper": 1000, "rationale": "The synthetic event must occur before the next stimulus cycle."}
    bounded_plan = parse_evaluation(json.dumps(bounded).encode(), file_format="json")
    rejected = run_evaluation(bounded_plan, inputs,
                              {**bindings, "response": DegradedCandidateSimulator()},
                              tmp_path / "bounded")
    assert rejected["physical_valid"] is True
    assert rejected["metrics"]["delay"]["status"] == "failed"
    assert rejected["specs_pass"] is False
    assert rejected["outcome"] == "failed"
    assert rejected["task_success"] is False
    assert rejected["quality_eligible"] is False
    assert rejected["score"]["value"] == 0


def test_reference_scores_cap_improvements_and_remain_recomputable(tmp_path, inputs, bindings):
    plan, report = reference_report(tmp_path, inputs, bindings)
    score = report["score"]
    assert report["outcome"] == "passed"
    assert score["maximum"] == score["reference"] == 100
    assert score["value"] == pytest.approx(100 * math.sqrt(1 / 1.5))
    assert score["metrics"]["delay"] == 2
    assert score["credited_metrics"]["delay"] == 1
    assert score == recompute_score(plan, report)
    # A worse observation remains visible even when the other observation improves.
    report["jobs"]["slow"]["measurements"]["delay"]["value"] = 8
    score = recompute_score(plan, report)
    assert score["components"]["E"] == pytest.approx(0.5)
    assert score["value"] == pytest.approx(100 * math.sqrt(0.5 / 1.5))


@pytest.mark.parametrize("area_quality,delay_quality,expected", [
    (4, 0.5, 100 * math.sqrt(0.5)),
    (0.5, 4, 100 * math.sqrt(0.5)),
    (4, 4, 100),
    (1, 1, 100),
    (0.5, 0.5, 50),
])
def test_caps_prevent_cross_metric_compensation(tmp_path, inputs, bindings, area_quality, delay_quality, expected):
    plan, report = reference_report(tmp_path, inputs, bindings)
    area = next(m for m in plan.metrics if m.id == plan.scoring.area_metric)
    job, name = area.observations[0].split(":")
    report["jobs"][job]["measurements"][name]["value"] = plan.scoring.area_target / area_quality
    for job, source in (("nominal", 2), ("slow", 4)):
        report["jobs"][job]["measurements"]["delay"]["value"] = source / delay_quality

    score = recompute_score(plan, report)
    assert score["value"] == pytest.approx(expected)
    assert 0 <= score["value"] <= 100
    assert score["area"]["Q"] == area_quality
    assert score["area"]["credited_quality"] == min(1, area_quality)
    assert score["components"]["Q"] == min(1, area_quality)
    assert score["credited_metrics"]["delay"] == min(1, delay_quality)


def test_challenging_quality_target_keeps_valid_reference_and_source_evidence(tmp_path, inputs, bindings):
    from benchmarking.evaluation.scoring import score_breakdown

    data = reference_plan(quality_target={
        "value": 0.25, "rationale": "Quarter-second response reserves time for downstream work."})
    plan = parse_evaluation(json.dumps(data).encode(), file_format="json")
    report = run_evaluation(plan, inputs, {**bindings, "response": ReferenceSimulator()},
                            tmp_path / "challenging")
    assert report["task_success"] is True
    # Candidate delays are 1 and 2 s, source delays 2 and 4 s. The worst
    # target attainment is 0.25/2, independent of the source values.
    assert report["score"]["value"] == pytest.approx(100 * math.sqrt((0.25 / 2) / 1.5))
    assert report["score"] == recompute_score(plan, report)
    detail = score_breakdown(plan, report["jobs"], report["score"])["metrics"]["delay"]
    assert [pair["source_value"] for pair in detail["observations"]] == [2, 4]
    assert [pair["quality_target"] for pair in detail["observations"]] == [0.25, 0.25]
    assert detail["quality_target_rationale"] == data["metrics"][0]["quality_target"]["rationale"]
    report["jobs"]["slow"]["measurements"]["delay"]["value"] = -1
    assert recompute_score(plan, report)["value"] == 0


@pytest.mark.parametrize("target", [
    {"value": float("nan"), "rationale": "Invalid number"},
    {"value": -1, "rationale": "Invalid ratio"},
    {"value": 0, "rationale": "Unscaled zero ratio"},
    {"value": 0.25, "rationale": " "},
    {"value": 0.25},
])
def test_quality_target_rejects_invalid_declarations(target):
    with pytest.raises((ValueError, TypeError)):
        parse_evaluation(json.dumps(reference_plan(quality_target=target)).encode(), file_format="json")


def test_quality_target_does_not_replace_source_pairing():
    data = reference_plan(quality_target={"value": 0.25, "rationale": "Quarter-second response."})
    data["pre_layout"]["jobs"]["source_nominal"]["parameters"]["load"] = 99
    with pytest.raises(ValueError, match="settings differ"):
        parse_evaluation(json.dumps(data).encode(), file_format="json")


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
    # The bounded error contract: equal, improved, degraded, zero and extreme inputs.
    ("saturating_ratio", "minimize", "V", 1, 0, 0, 1),
    ("saturating_ratio", "minimize", "V", 1, 1, 3, 4 / 3),
    ("saturating_ratio", "minimize", "V", 1, 3, 1, 2 / 3),
    ("saturating_ratio", "minimize", "V", 1e-6, 0, 1e308, 2),
    ("saturating_ratio", "minimize", "V", 1e308, 0, 1e308, 4 / 3),
])
def test_reference_normalization_handles_db_signed_targets_and_zero(
        tmp_path, inputs, bindings, normalization, direction, unit, scale, post, source, expected):
    _, report = reference_report(tmp_path, inputs, bindings)
    data = reference_plan()
    metric = data["metrics"][0]
    metric.update(normalization=normalization, direction=direction, unit=unit)
    if normalization not in {"ratio", "saturating_ratio"}:
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
    score = recompute_score(plan, report)
    assert score["metrics"]["delay"] == pytest.approx(expected)
    assert score["components"]["E"] == pytest.approx(min(1, expected))


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
    assert score['value'] == pytest.approx(100 * 0.5**0.2 * (2/3)**0.2)
    assert score['weights'] == data['scoring']['weights']
    assert score['components']['E'] == pytest.approx(0.5**0.25)
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
    assert score['value'] == pytest.approx(100 * (2/3)**0.2)
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
    from benchmarking.engine.sessions.execution import _zero_attempt_score
    from benchmarking.results.report import report_text

    plan = parse_evaluation(json.dumps(weighted_plan()).encode(), file_format='json')
    report = run_evaluation(plan, inputs, {**bindings, 'response': ReferenceSimulator()}, tmp_path / 'weighted')
    assert report['task_success'] is True
    assert report['score'] == recompute_score(plan, report)
    rendered = report_text({'evaluation': dict(report, evaluation_mode='self_run'),
                            'summary': {'score': report['score']['value']},
                            'identity': {'plan': [{}]}}).decode()
    assert 'product(min(1, q_i) ** w_i)' in rendered and '| delay | 0.6 |' in rendered
    assert 'maximum = 100' in rendered
    assert 'Credited quality' in rendered
    zero = _zero_attempt_score('layout')
    assert zero['method'] == 'layout' and zero['value'] == 0 and zero['maximum'] == 100


# Extend the existing synthetic scoring DAG: calibration consumes the source DUT
# independently, and a downstream baseline consumes its digest-bound selection.
# This checks provenance/fixture equality, not a circuit's calibration accuracy.
def calibrated_reference_plan():
    data = reference_plan()
    source = data['pre_layout']['jobs']['source_nominal']
    calibration = copy.deepcopy(source)
    calibration['parameters'] = {'target': 3, 'candidates': [1, 2]}
    calibration['outputs'] = {'selection': 'json'}
    calibration['output_sha256'] = {'selection': 'a' * 64}
    data['pre_layout']['jobs']['source_calibration'] = calibration
    source['inputs']['selection'] = 'job:source_calibration:selection'
    source['input_sha256']['selection'] = calibration['output_sha256']['selection']
    candidate = next(j for j in data['jobs'] if j['id'] == 'nominal')
    producer = copy.deepcopy(candidate)
    producer.update(id='calibration', parameters=copy.deepcopy(calibration['parameters']),
                    outputs={'selection': 'json'})
    data['jobs'].append(producer)
    candidate['inputs']['selection'] = 'job:calibration:selection'
    return data


def test_frozen_calibration_dag_is_independent_and_not_a_solver_input():
    data = calibrated_reference_plan()
    plan = parse_evaluation(json.dumps(data).encode(), file_format='json')
    assert not any(ref.startswith('job:') for ref in plan.external_inputs())
    assert not (plan.pre_layout.keys() & {job.id for job in plan.jobs})


@pytest.mark.parametrize('defect', ['candidate', 'digest', 'cycle', 'algorithm', 'fixture', 'output', 'circuit_selection'])
def test_frozen_calibration_provenance_and_pairing_are_enforced(defect):
    data = calibrated_reference_plan()
    source = data['pre_layout']['jobs']['source_calibration']
    producer = next(j for j in data['jobs'] if j['id'] == 'calibration')
    if defect == 'candidate':
        source['inputs']['dut'] = 'job:parasitics:netlist'
    elif defect == 'digest':
        source['output_sha256']['selection'] = 'b' * 64
    elif defect == 'cycle':
        source['inputs']['dut'] = 'job:source_calibration:selection'
    elif defect == 'algorithm':
        producer['parameters']['target'] += 1
    elif defect == 'fixture':
        source['inputs']['deck'] = 'input:other_fixture'
        source['input_sha256']['deck'] = 'b' * 64
    elif defect == 'circuit_selection':
        candidate = next(j for j in data['jobs'] if j['id'] == 'nominal')
        candidate['inputs']['dut'] = 'job:calibration:selection'
    else:
        producer['outputs']['selection'] = 'spice'
    with pytest.raises(ValueError):
        parse_evaluation(json.dumps(data).encode(), file_format='json')


def test_candidate_recomputes_calibration_without_source_artifact(tmp_path, inputs, bindings):
    from benchmarking.engine.evaluate import JobResult
    from benchmarking.files import Asset

    class CalibratedSimulator(ReferenceSimulator):
        def run(self, job, assets):
            assert assets['dut'].content == b'derived-from-layout'
            if job.id == 'calibration':
                return JobResult('passed', outputs={'selection': Asset(b'{"code":2}', 'json')},
                                 evidence={'log': Asset(b'independent candidate selection', 'text')})
            if job.id == 'nominal':
                assert assets['selection'].content == b'{"code":2}'
            return super().run(job, assets)

    plan = parse_evaluation(json.dumps(calibrated_reference_plan()).encode(), file_format='json')
    report = run_evaluation(plan, inputs, {**bindings, 'response': CalibratedSimulator()},
                            tmp_path / 'calibrated')
    assert report['task_success'] is True
    assert not (plan.pre_layout.keys() & report['jobs'].keys())
