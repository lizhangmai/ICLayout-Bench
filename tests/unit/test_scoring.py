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


# The existing synthetic circuit owns the DAG and units. These controls protect
# the new public reference-relative arithmetic, uncapped improvements and missing
# baseline semantics; expected values follow the stated ratios, not engine output.
def reference_plan(**metric_changes):
    data = tomllib.loads(PLAN.decode())
    data["scoring"].update(method="layout-v2")
    data["scoring"].pop("area_zero")
    for job in list(data["jobs"]):
        if job["stage"] == "simulate":
            source = copy.deepcopy(job)
            source.update(id="source_" + job["id"], inputs={"dut": "input:netlist"})
            data["jobs"].append(source)
    metric = data["metrics"][0]
    metric.pop("zero_upper")
    metric.pop("upper")
    metric.update(lower=0, baseline=["source_" + ref for ref in metric["observations"]],
                  normalization="ratio", **metric_changes)
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
    report = run_evaluation(plan, inputs, {**bindings, "response": ReferenceSimulator()}, tmp_path / "v2")
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


@pytest.mark.parametrize("defect", [
    "missing",
    "unit",
    "failed_job",
])
def test_invalid_source_evidence_never_awards_a_score(tmp_path, inputs, bindings, defect):
    plan, report = reference_report(tmp_path, inputs, bindings)
    if defect == "failed_job":
        report["jobs"]["source_nominal"]["status"] = "failed"
    elif defect == "missing":
        report["jobs"]["source_nominal"]["measurements"].clear()
    else:
        report["jobs"]["source_nominal"]["measurements"]["delay"]["unit"] = "V"
    assert recompute_score(plan, report)["value"] is None


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
        report["jobs"][name]["measurements"]["delay"]["value"] = source
    plan = parse_evaluation(json.dumps(data).encode(), file_format="json")
    assert recompute_score(plan, report)["components"]["E"] == pytest.approx(expected)


@pytest.mark.parametrize("defect", ["candidate", "parameters", "deck", "unpaired"])
def test_baseline_requires_independent_same_condition_source_simulation(defect):
    data = reference_plan()
    source = next(j for j in data["jobs"] if j["id"] == "source_nominal")
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


def test_unusable_baseline_changes_success_to_evaluator_error(tmp_path, inputs, bindings):
    from benchmarking.engine.evaluate import JobResult

    class MissingSource(ReferenceSimulator):
        def run(self, job, inputs):
            if inputs['dut'].content == b'schematic':
                return JobResult('passed', evidence={'log': inputs['dut']})
            return super().run(job, inputs)

    plan = parse_evaluation(json.dumps(reference_plan()).encode(), file_format='json')
    report = run_evaluation(plan, inputs, {**bindings, 'response': MissingSource()}, tmp_path / 'missing-source')
    assert report['physical_valid'] is True and report['specs_pass'] is True
    assert report['outcome'] == 'error'
    assert report['task_success'] is None and report['score']['value'] is None
    # A conclusive functional violation still cannot disappear from statistics.
    report['jobs']['slow']['measurements']['delay']['value'] = -1
    assert recompute_score(plan, report)['value'] == 0


def test_extreme_finite_area_does_not_emit_nonfinite_score_evidence(tmp_path, inputs, bindings):
    _, report = reference_report(tmp_path, inputs, bindings)
    data = reference_plan()
    data['scoring']['area_target'] = 1e308
    plan = parse_evaluation(json.dumps(data).encode(), file_format='json')
    report['jobs']['geometry']['measurements']['area']['value'] = 1e-308
    score = recompute_score(plan, report)
    assert score['value'] is None
    json.dumps(score, allow_nan=False)
