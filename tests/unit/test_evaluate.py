import hashlib
import json
import tomllib
from typing import ClassVar

import pytest

from benchmarking.engine.evaluate import JobResult, Measurement, run_evaluation
from benchmarking.evaluation import parse_evaluation
from benchmarking.files import Asset

pytestmark = pytest.mark.unit

PLAN = b'''schema_version = 1
mode = "post_layout"

[scoring]
method = "layout-v1"
area_metric = "functional_area"
area_target = 1.0
area_zero = 2.0

[[jobs]]
id = "slow"
stage = "simulate"
operation = "response"
inputs = { dut = "job:parasitics:netlist" }
[jobs.parameters]
load = 2.0

[[jobs]]
id = "artifact"
stage = "check"
operation = "check"
gate = "artifact"
inputs = { layout = "candidate" }

[[jobs]]
id = "drc"
stage = "check"
operation = "check"
gate = "drc"
inputs = { layout = "candidate" }
requires = ["artifact"]

[[jobs]]
id = "lvs"
stage = "check"
operation = "check"
gate = "lvs"
inputs = { layout = "candidate", schematic = "input:netlist" }
requires = ["artifact"]

[[jobs]]
id = "geometry"
stage = "check"
operation = "check"
gate = "constraint"
inputs = { layout = "candidate" }
requires = ["artifact", "drc", "lvs"]

[[jobs]]
id = "parasitics"
stage = "extract"
operation = "extract"
inputs = { layout = "candidate" }
requires = ["artifact", "drc", "lvs", "geometry"]
outputs = { netlist = "spice" }

[[jobs]]
id = "nominal"
stage = "simulate"
operation = "response"
inputs = { dut = "job:parasitics:netlist" }
[jobs.parameters]
load = 1.0

[[metrics]]
id = "delay"
category = "performance"
observations = ["nominal:delay", "slow:delay"]
unit = "s"
direction = "minimize"
aggregation = "max"
upper = 4.0
zero_upper = 6.0
dimension = "response"

[[metrics]]
id = "functional_area"
category = "physical"
observations = ["geometry:area"]
unit = "um2"
direction = "minimize"
aggregation = "max"
'''


class Checks:
    identity: ClassVar[dict] = {"adapter": "synthetic-checks", "version": "1"}

    def __init__(self, reject=None, crash=None, area=1.5):
        self.area = area
        self.reject = reject
        self.crash = crash
        self.calls = []

    def run(self, job, inputs):
        self.calls.append(job.id)
        if job.id == self.crash:
            raise RuntimeError("Tool failed unexpectedly")
        measurements = {"area": Measurement(self.area, "um2")} if job.id == "geometry" else {}
        return JobResult("failed" if job.id == self.reject else "passed",
                         "Synthetic rejection" if job.id == self.reject else "",
                         measurements=measurements,
                         evidence={"log": Asset(job.id.encode(), "text")})


class Extractor:
    identity: ClassVar[dict] = {"adapter": "synthetic-extractor", "version": "1"}

    def run(self, job, inputs):
        assert inputs["layout"].content == b"synthetic-layout"
        return JobResult("passed", outputs={"netlist": Asset(b"derived-from-layout", "spice")},
                         evidence={"log": Asset(b"extraction evidence", "text")})


class Simulator:
    identity: ClassVar[dict] = {"adapter": "synthetic-simulator", "version": "1"}

    def __init__(self, factor=1.0, unit="s", missing=False):
        self.factor, self.unit, self.missing = factor, unit, missing

    def run(self, job, inputs):
        assert inputs["dut"].content == b"derived-from-layout"
        value = self.factor * (1.0 if job.parameters["load"] == 1.0 else 3.0)
        return JobResult("passed", measurements={} if self.missing else {"delay": Measurement(value, self.unit)},
                         evidence={"waveform": Asset(b"synthetic response", "text")})


@pytest.fixture
def bindings():
    return {"check": Checks(), "extract": Extractor(), "response": Simulator()}


@pytest.fixture
def inputs():
    return {"candidate": Asset(b"synthetic-layout", "gds"), "input:netlist": Asset(b"schematic", "spice"),
            "input:unlisted_reference": Asset(b"reference must not be consumed", "gds")}


def evaluate(tmp_path, inputs, bindings, raw=PLAN):
    return run_evaluation(parse_evaluation(raw), inputs, bindings, tmp_path / "report")


@pytest.mark.parametrize("file_format", ["toml", "json"])
def test_dependencies_follow_extracted_candidate_and_archive_evidence(tmp_path, inputs, bindings, file_format):
    raw = PLAN if file_format == "toml" else json.dumps(tomllib.loads(PLAN.decode())).encode()
    plan = parse_evaluation(raw, file_format=file_format)
    job = next(j for j in plan.jobs if j.id == "slow")
    job.parameters["load"] = 100
    assert job.parameters["load"] == 2.0
    witnessed = True if file_format == "json" else None
    report = run_evaluation(plan, inputs, bindings, tmp_path / "report", task_witnessed=witnessed)
    assert report["task_witnessed"] is witnessed
    archived = report["plan"]
    restored = parse_evaluation((tmp_path / "report" / archived["path"]).read_bytes(),
                                file_format=archived["format"])
    assert restored.description() == tomllib.loads(PLAN.decode())
    assert report["physical_valid"] is True
    assert report["task_success"] is True
    assert report["quality_eligible"] is True
    assert report["score"]["method"] == "layout-v1"
    assert report["score"]["maximum"] == 100
    assert report["metrics"]["delay"]["value"] == 3.0
    assert list(report["jobs"]).index("parasitics") < list(report["jobs"]).index("slow")
    assert "input:unlisted_reference" not in report["inputs"]
    output = report["jobs"]["parasitics"]["outputs"]["netlist"]
    content = (tmp_path / "report" / output["path"]).read_bytes()
    assert hashlib.sha256(content).hexdigest() == output["sha256"]
    assert report["jobs"]["slow"]["inputs"]["dut"]["sha256"] == output["sha256"]
    assert json.loads((tmp_path / "report/report.json").read_text()) == report
    root = tmp_path / "report"
    for path, mode in ((root, 0o700), (root / "artifacts", 0o700),
                       (root / "report.json", 0o600), (root / output["path"], 0o400)):
        assert path.stat().st_mode & 0o777 == mode
    assert report["score"]["value"] == pytest.approx(90)
    assert report["score"]["components"] == {"G": 1.0, "E": 1.0, "H": 1.0, "Q": 0.5}

def test_drc_lvs_success_is_not_performance_success(tmp_path, inputs, bindings):
    report = evaluate(tmp_path, inputs, bindings, PLAN.replace(b"upper = 4.0", b"upper = 2.0"))
    assert report["physical_valid"] is True
    assert report["specs_pass"] is False
    assert report["task_success"] is False
    assert report["metrics"]["delay"]["observations"]["nominal:delay"]["status"] == "passed"
    assert report["metrics"]["delay"]["observations"]["slow:delay"]["status"] == "failed"
    assert report["score"]["components"]["E"] == pytest.approx(0.75)
    assert report["score"]["components"]["H"] == 0
    assert 0 < report["score"]["value"] < 60


def test_summary_cannot_hide_a_failing_case(tmp_path, inputs, bindings):
    raw = PLAN.replace(b"upper = 4.0", b"lower = 2.0\nzero_lower = 0.0\nupper = 4.0")
    report = evaluate(tmp_path, inputs, bindings, raw)
    assert report["metrics"]["delay"]["value"] == 3.0
    assert report["metrics"]["delay"]["status"] == "failed"


def test_failed_gate_blocks_dependent_work_but_preserves_independent_checks(tmp_path, inputs, bindings):
    bindings["check"] = Checks(reject="drc")
    report = evaluate(tmp_path, inputs, bindings)
    assert report["physical_valid"] is False
    assert report["task_success"] is False
    assert report["jobs"]["lvs"]["status"] == "passed"
    assert report["score"]["value"] == 0
    assert report["jobs"]["parasitics"]["status"] == "blocked"
    assert report["metrics"]["delay"]["value"] is None


def test_unscored_post_layout_plan_has_no_legacy_score(tmp_path, inputs, bindings):
    unscored = PLAN.replace(b'\n[scoring]\nmethod = "layout-v1"\narea_metric = "functional_area"\narea_target = 1.0\narea_zero = 2.0\n', b"")
    unscored = unscored.replace(b'zero_upper = 6.0\n', b"").replace(
        b'dimension = "response"\n', b"")
    report = evaluate(tmp_path, inputs, bindings, unscored)
    assert report["score"] is None
    assert report["task_success"] is True


def test_tool_error_is_not_a_circuit_failure(tmp_path, inputs, bindings):
    bindings["check"] = Checks(crash="drc")
    report = evaluate(tmp_path, inputs, bindings)
    assert report["outcome"] == "error"
    assert report["score"]["value"] is None
    assert report["physical_valid"] is None
    assert report["task_success"] is None
    assert report["jobs"]["lvs"]["status"] == "passed"


def test_known_gate_failure_is_not_hidden_by_unrelated_tool_error(tmp_path, inputs, bindings):
    bindings["check"] = Checks(reject="drc", crash="lvs")
    report = evaluate(tmp_path, inputs, bindings)
    assert report["score"]["value"] == 0
    assert report["score"]["components"]["G"] == 0
    assert report["jobs"]["drc"]["status"] == "failed"
    assert report["jobs"]["lvs"]["status"] == "error"
    assert report["outcome"] == "failed"
    assert report["physical_valid"] is False
    assert report["task_success"] is False


def test_known_metric_failure_is_not_hidden_by_unrelated_tool_error(tmp_path, inputs, bindings):
    class MixedSimulator(Simulator):
        def run(self, job, inputs):
            if job.id == "nominal":
                raise RuntimeError("Synthetic simulator error")
            return super().run(job, inputs)

    raw = PLAN + b'''\n[[metrics]]
id = "slow_limit"
category = "performance"
observations = ["slow:delay"]
unit = "s"
direction = "minimize"
aggregation = "max"
upper = 2.0
zero_upper = 6.0
dimension = "response"
'''
    bindings["response"] = MixedSimulator()
    report = evaluate(tmp_path, inputs, bindings, raw)
    assert report["metrics"]["slow_limit"]["status"] == "failed"
    assert report["metrics"]["delay"]["status"] == "blocked"
    assert report["outcome"] == "failed"
    assert report["task_success"] is False
    assert report["score"]["value"] is None


@pytest.mark.parametrize("simulator", [
    Simulator(unit="ms"),
    Simulator(missing=True),
    Simulator(factor=float("nan")),
])
def test_missing_nonfinite_or_wrong_unit_never_passes(tmp_path, inputs, bindings, simulator):
    bindings["response"] = simulator
    report = evaluate(tmp_path, inputs, bindings)
    assert report["outcome"] == "error"
    assert report["task_success"] is None
    assert report["quality_eligible"] is False


@pytest.mark.parametrize("mode", ["physical", "characterization"])
def test_partial_scope_does_not_claim_full_task_success(tmp_path, inputs, bindings, mode):
    raw = PLAN.replace(b'"post_layout"', f'"{mode}"'.encode())
    raw = raw[:raw.index(b"\n[scoring]")] + raw[raw.index(b"\n[[jobs]]"):]
    raw = raw.replace(b'zero_upper = 6.0\n', b"").replace(
        b'dimension = "response"\n', b"")
    report = evaluate(tmp_path, inputs, bindings, raw)
    assert report["outcome"] == "passed"
    assert report["task_success"] is None
    assert report["quality_eligible"] is False


@pytest.mark.parametrize(("before", "after", "message"), [
    (b"job:parasitics:netlist", b"input:netlist", "consume candidate extraction"),
    (b'requires = ["artifact", "drc", "lvs", "geometry"]', b'requires = ["artifact"]', "physical validity gates"),
    (b'job:parasitics:netlist', b'job:parasitics:absent', "Unknown job output"),
    (b'requires = ["artifact", "drc", "lvs"]', b'requires = ["slow"]', "cycle"),
])
def test_invalid_plans_are_rejected(before, after, message):
    with pytest.raises(ValueError, match=message):
        parse_evaluation(PLAN.replace(before, after))


def test_missing_binding_is_preflight_error(tmp_path, inputs, bindings):
    del bindings["extract"]
    with pytest.raises(ValueError, match="Missing backend"):
        evaluate(tmp_path, inputs, bindings)
    assert not (tmp_path / "report").exists()


def test_untrusted_backend_cannot_claim_success_without_declared_output(tmp_path, inputs, bindings):
    bindings["extract"] = Checks()
    report = evaluate(tmp_path, inputs, bindings)
    assert report["jobs"]["parasitics"]["status"] == "error"
    assert report["task_success"] is None


@pytest.mark.parametrize('lower,upper,value,accepted', [
    (None, 0.0, 0.0, True),
    (-2.0, -1.0, -1.0, True),
    (-2.0, -1.0, -0.99, False),
])
def test_measurement_bounds_are_inclusive_for_signed_and_zero_values(
        tmp_path, lower, upper, value, accepted):
    # Independent interval examples exercise the common evaluator; they make
    # no claim about any real circuit or simulator's physical behavior.
    metric = {'id': 'voltage', 'category': 'performance', 'unit': 'V',
              'direction': 'minimize', 'aggregation': 'max',
              'observations': ['sample:voltage']}
    metric.update({k: v for k, v in [('lower', lower), ('upper', upper)] if v is not None})
    raw = {'schema_version': 1, 'mode': 'characterization',
           'jobs': [{'id': 'sample', 'stage': 'simulate', 'operation': 'measure',
                     'inputs': {'circuit': 'input:source'}}], 'metrics': [metric]}

    class MeasurementTool:
        identity: ClassVar[dict] = {'adapter': 'synthetic-voltage'}

        def run(self, job, inputs):
            return JobResult('passed', measurements={'voltage': Measurement(value, 'V')},
                             evidence={'log': Asset(b'synthetic voltage observation', 'text')})

    report = run_evaluation(parse_evaluation(json.dumps(raw).encode(), file_format='json'),
                            {'input:source': Asset(b'synthetic circuit', 'spice')},
                            {'measure': MeasurementTool()}, tmp_path / 'run')
    assert report['jobs']['sample']['status'] == 'passed'
    assert report['specs_pass'] is accepted
    assert report['metrics']['voltage']['status'] == ('passed' if accepted else 'failed')
    assert report['task_success'] is None
