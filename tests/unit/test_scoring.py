import copy
import json
import math
import tomllib

import pytest
from test_evaluate import PLAN, evaluate

from benchmarking.evaluation import parse_evaluation
from benchmarking.scoring import recompute_score
from layout_eval.evaluate import run_evaluation

pytestmark = pytest.mark.unit
pytest_plugins = ["test_evaluate"]


def test_electrical_attainment_uses_the_worst_observation_then_equal_dimensions(
        tmp_path, inputs, bindings):
    raw = PLAN + b'''
[[metrics]]
id = "bias_observation"
category = "performance"
observations = ["nominal:delay", "slow:delay"]
unit = "s"
direction = "maximize"
aggregation = "min"
lower = 2.0
zero_lower = 0.0
dimension = "bias"
'''
    report = evaluate(tmp_path, inputs, bindings, raw)
    assert report["score"]["components"]["E"] == pytest.approx(0.75)
    assert report["score"]["dimensions"] == {"bias": 0.5, "response": 1.0}
    assert report["score"]["components"]["H"] == 0.0
    assert report["score"]["value"] < 60


def test_acceptance_boundary_is_perfect_but_just_outside_is_not(tmp_path, inputs, bindings):
    plan = parse_evaluation(PLAN)
    report = run_evaluation(plan, inputs, bindings, tmp_path / "accepted")
    exact = copy.deepcopy(report)
    exact["jobs"]["slow"]["measurements"]["delay"]["value"] = 4.0
    exact_score = recompute_score(plan, exact)
    assert exact_score["components"]["E"] == 1.0
    assert exact_score["components"]["H"] == 1.0

    outside = copy.deepcopy(exact)
    outside_value = math.nextafter(4.0, math.inf)
    outside["jobs"]["slow"]["measurements"]["delay"]["value"] = outside_value
    outside_score = recompute_score(plan, outside)
    assert outside_score["components"]["E"] < 1.0
    assert outside_score["value"] < 60


def test_equal_zero_boundary_is_a_hard_cliff(tmp_path, inputs, bindings):
    raw = PLAN.replace(b"upper = 4.0", b"upper = 2.0").replace(
        b"zero_upper = 6.0", b"zero_upper = 2.0")
    report = evaluate(tmp_path, inputs, bindings, raw)
    assert report["metrics"]["delay"]["status"] == "failed"
    assert report["score"]["components"]["E"] == 0.0
    assert report["score"]["value"] == 0.0


def test_area_utility_is_clipped_and_report_recomputation_is_identical(
        tmp_path, inputs, bindings):
    plan = parse_evaluation(PLAN)
    report = run_evaluation(plan, inputs, bindings, tmp_path / "report")
    display_tampered = copy.deepcopy(report)
    display_tampered["metrics"]["functional_area"]["value"] = 0.5
    assert recompute_score(plan, display_tampered) == report["score"]

    evidence_changed = copy.deepcopy(report)
    evidence_changed["jobs"]["geometry"]["measurements"]["area"]["value"] = 0.5
    score = recompute_score(plan, evidence_changed)
    assert score["components"]["Q"] == 1.0
    assert score["value"] == pytest.approx(100)
    assert score == recompute_score(plan, {**evidence_changed, "score": score})


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


@pytest.mark.parametrize(("field", "value", "message"), [
    ("area_target", "0", "positive"),
    ("area_zero", "1.0", "exceed"),
    ("area_zero", "nan", "finite numeric"),
])
def test_scoring_area_bounds_are_finite_and_ordered(field, value, message):
    raw = PLAN.replace(f"{field} = 1.0".encode() if field == "area_target"
                       else f"{field} = 2.0".encode(), f"{field} = {value}".encode())
    with pytest.raises(ValueError, match=message):
        parse_evaluation(raw)


@pytest.mark.parametrize(("change", "message"), [
    ((b"zero_upper = 6.0\n", b""), "zero_upper"),
    ((b'dimension = "response"', b'dimension = "unknown"'), "Unknown scoring dimension"),
    ((b'area_metric = "functional_area"', b'area_metric = "delay"'),
     "physical metric"),
    ((b'method = "layout-v1"', b'method = "other"'), "Unsupported scoring method"),
])
def test_scoring_schema_is_strict(change, message):
    before, after = change
    with pytest.raises(ValueError, match=message):
        parse_evaluation(PLAN.replace(before, after))


def test_evaluator_error_is_null_but_completed_invalid_candidate_is_zero(
        tmp_path, inputs, bindings):
    error = evaluate(tmp_path / "error", inputs,
                     {**bindings, "check": type(bindings["check"])(crash="geometry")})
    assert error["outcome"] == "error"
    assert error["score"]["value"] is None

    failed = evaluate(tmp_path / "failed", inputs,
                      {**bindings, "check": type(bindings["check"])(reject="drc")})
    assert failed["outcome"] == "failed"
    assert failed["score"]["value"] == 0


@pytest.mark.parametrize('position,utility,score', [
    ('below', 1, 100), ('target', 1, 100), ('midpoint', 0.5, 90),
    ('zero', 0, 80), ('beyond', 0, 80),
])
def test_area_utility_clips_at_both_anchors_without_changing_acceptance(
        tmp_path, inputs, bindings, position, utility, score):
    # layout-v1 awards 80 electrical points plus 20 times clipped area
    # utility. Expected utilities follow independently stated positions,
    # while the synthetic plan owns the actual dimensional anchors.
    scoring = parse_evaluation(PLAN).scoring
    target, zero = scoring.area_target, scoring.area_zero
    area = {'below': target / 2, 'target': target, 'midpoint': (target + zero) / 2,
            'zero': zero, 'beyond': zero + (zero - target)}[position]
    bindings['check'] = type(bindings['check'])(area=area)
    report = evaluate(tmp_path, inputs, bindings)
    assert report['physical_valid'] is report['task_success'] is True
    assert report['score']['components']['Q'] == pytest.approx(utility)
    assert report['score']['value'] == pytest.approx(score)
