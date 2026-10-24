import hashlib
import json
import sys
import tomllib
from typing import ClassVar

import pytest

from benchmarking.evaluation import parse_evaluation
from benchmarking.evaluation.contracts import JobResult, Measurement
from benchmarking.evaluation.feedback import feedback_details
from benchmarking.evaluation.runner import run_evaluation
from benchmarking.files import Asset

pytestmark = pytest.mark.unit

PLAN = b'''
mode = "post_layout"

[scoring]
method = "layout"
area_metric = "functional_area"
area_target = 1.0
rationale = "Delay and area control."
weights = {delay = 0.5, functional_area = 0.5}

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
requirement = { upper = 4.0, rationale = "The synthetic event must occur within its stimulus cycle." }
baseline = ["source_nominal:delay", "source_slow:delay"]
normalization = "ratio"
dimension = "response"

[[metrics]]
id = "functional_area"
category = "physical"
observations = ["geometry:area"]
unit = "um2"
direction = "minimize"
aggregation = "max"

[pre_layout]
source_report_sha256 = "0000000000000000000000000000000000000000000000000000000000000000"

[pre_layout.backends]
response = "synthetic reference"

[pre_layout.jobs.source_nominal]
operation = "response"

[pre_layout.jobs.source_nominal.inputs]
dut = "input:netlist"

[pre_layout.jobs.source_nominal.parameters]
load = 1.0

[pre_layout.jobs.source_nominal.outputs]

[pre_layout.jobs.source_nominal.input_sha256]
dut = "6604afd98a39f581bd04e52a12c75294eccd42bc69f94d8cc4419807bf8a3620"

[pre_layout.jobs.source_nominal.measurements.delay]
value = 1.0
unit = "s"

[pre_layout.jobs.source_slow]
operation = "response"

[pre_layout.jobs.source_slow.inputs]
dut = "input:netlist"

[pre_layout.jobs.source_slow.parameters]
load = 2.0

[pre_layout.jobs.source_slow.outputs]

[pre_layout.jobs.source_slow.input_sha256]
dut = "6604afd98a39f581bd04e52a12c75294eccd42bc69f94d8cc4419807bf8a3620"

[pre_layout.jobs.source_slow.measurements.delay]
value = 3.0
unit = "s"
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
        assert inputs["dut"].content in {b"derived-from-layout", b"schematic", b"netlist"}
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


@pytest.mark.parametrize('crash', [False, True])
def test_independent_simulations_overlap_after_extraction(tmp_path, inputs, bindings, crash):
    """Serial corner execution wastes the explicit backend concurrency allowance.

    A barrier tests overlap without machine-dependent performance thresholds;
    the existing plan independently supplies the expected results and dependency.
    """
    from threading import Barrier

    simulator = bindings['response']
    simulator.max_parallel_jobs = 2
    original = simulator.run
    barrier = Barrier(simulator.max_parallel_jobs, timeout=2)

    def simultaneous(job, assets):
        assert assets['dut'].content == b'derived-from-layout'
        barrier.wait()
        if crash and job.id == 'slow':
            raise RuntimeError('One corner failed')
        return original(job, assets)

    simulator.run = simultaneous
    report = evaluate(tmp_path, inputs, bindings)
    assert report['jobs']['nominal']['status'] == 'passed'
    if crash:
        assert report['jobs']['slow']['status'] == 'error'
        assert report['task_success'] is None
    else:
        assert report['task_success'] is True
        assert report['metrics']['delay']['value'] == 3.0


@pytest.mark.parametrize('entry,parallel_jobs', [('evaluation', 1), ('evaluation', 2), ('qualification', 2)])
def test_evaluation_and_qualification_allow_native_jobs_to_finish_by_default(
        tmp_path, inputs, bindings, entry, parallel_jobs):
    from types import SimpleNamespace

    from benchmarking.eda.environment import ExternalRuntime
    from benchmarking.evaluation.qualification import run as qualify
    from benchmarking.execution.tools.native import NativeTool

    runtime = ExternalRuntime('test', {'image': 'unused', 'environment': {}, 'mounts': []})
    tool = NativeTool(runtime, timeout_seconds=.02)
    simulator = bindings['response']
    simulator.max_parallel_jobs = parallel_jobs
    original = simulator.run

    def simulate(job, assets):
        result = tool.run([sys.executable, '-c', 'import time; time.sleep(.1); print("complete")'], {}, {})
        if result.reason:
            return JobResult('error', result.reason, evidence=result.evidence)
        return original(job, assets)

    simulator.run = simulate
    plan = parse_evaluation(PLAN)
    task = SimpleNamespace(evaluation=plan, digest='fixture', witnessed=True,
                           evaluation_inputs=lambda: inputs)
    qualification_runtime = SimpleNamespace(task=task, witness=lambda: inputs['candidate'], backends=bindings)

    def evaluate_at(name):
        if entry == 'evaluation':
            return run_evaluation(plan, inputs, bindings, tmp_path / name)
        qualify(qualification_runtime, tmp_path / name, retain_evaluation=True)
        return json.loads((tmp_path / name / 'evaluation/report.json').read_text())

    report = evaluate_at('default')
    assert report['task_success'] is True
    assert report['metrics']['delay']['value'] == 3.0
    assert report['tool_time_limits'] is False
    limited = run_evaluation(plan, inputs, bindings, tmp_path / 'limited', limit_tools=True)
    assert limited['jobs']['nominal']['status'] == 'error'
    assert limited['jobs']['slow']['status'] == 'error'
    assert limited['tool_time_limits'] is True
    # An explicitly bounded probe must not change later evaluation defaults.
    assert evaluate_at('independent')['task_success'] is True


def test_check_cancellation_reaches_parallel_native_jobs_and_does_not_leak(tmp_path, inputs, bindings):
    import time
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path
    from threading import Event

    from benchmarking.eda.environment import ExternalRuntime
    from benchmarking.execution.tools.budget import tool_cancellation
    from benchmarking.execution.tools.native import NativeTool

    tool = NativeTool(ExternalRuntime('test', {'image': 'unused', 'environment': {}, 'mounts': []}))
    cancellation = Event()
    simulator = bindings['response']
    simulator.max_parallel_jobs = 2
    original = simulator.run

    def simulate(job, assets):
        marker = tmp_path / job.id
        result = tool.run([sys.executable, '-c', (
            'import os,time; from pathlib import Path; '
            f'Path({str(marker)!r}).write_text(str(os.getpid())); time.sleep(2)')], {}, {})
        if result.reason:
            return JobResult('error', result.reason, evidence=result.evidence)
        return original(job, assets)

    simulator.run = simulate
    plan = parse_evaluation(PLAN)

    def check():
        with tool_cancellation(cancellation):
            return run_evaluation(plan, inputs, bindings, tmp_path / 'cancelled')

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(check)
        deadline = time.monotonic() + 5
        markers = [tmp_path / name for name in ('slow', 'nominal')]
        while not all(marker.exists() for marker in markers) and time.monotonic() < deadline:
            time.sleep(.01)
        assert all(marker.exists() for marker in markers), 'Both independent jobs must be running'
        cancellation.set()
        report = pending.result(timeout=1)
    assert report['outcome'] == 'error'
    for name, marker in zip(('slow', 'nominal'), markers):
        assert 'cancel' in report['jobs'][name]['reason'].lower()
        assert not Path('/proc/' + marker.read_text()).exists()
    # A cancelled check must not contaminate a later check or final evaluation.
    simulator.run = original
    assert run_evaluation(plan, inputs, bindings, tmp_path / 'independent')['task_success'] is True


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
    assert report["score"]["method"] == "layout"
    assert report["score"]["maximum"] == 100 and report["score"]["reference"] == 100
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
    assert report["score"]["value"] == pytest.approx(100 * (2 / 3)**0.5)
    assert report["score"]["components"] == {"G": 1.0, "E": 1.0, "Q": 2/3}
    from benchmarking.evidence.archive import EvaluationArchive
    from benchmarking.results.package import evaluation_export

    files = []
    destination = tmp_path / 'portable'
    evaluation_export(EvaluationArchive(root), destination, files)
    exported = json.loads((destination / 'evaluation/report.json').read_text())
    assert exported['score'] == report['score']
    assert exported['jobs']['parasitics']['outputs']['netlist']['content'] == 'derived-from-layout'
    assert json.loads((root / 'report.json').read_text()) == report

def test_drc_lvs_success_is_not_performance_success(tmp_path, inputs, bindings):
    report = evaluate(tmp_path, inputs, bindings, PLAN.replace(b"upper = 4.0", b"upper = 2.0"))
    assert report["physical_valid"] is True
    assert report["specs_pass"] is False
    assert report["task_success"] is False
    assert report["metrics"]["delay"]["observations"]["nominal:delay"]["status"] == "passed"
    assert report["metrics"]["delay"]["observations"]["slow:delay"]["status"] == "failed"
    assert report["score"]["value"] == 0
    # Successful simulator execution must still expose failing spec measurements.
    details = feedback_details(report, tmp_path)
    assert details["jobs"]["slow"]["status"] == "passed"
    metric = details["metrics"]["delay"]
    assert metric["status"] == "failed"
    assert metric["value"] == report["metrics"]["delay"]["value"]
    assert metric["excess"] == pytest.approx(1.0)
    assert metric["unit"] == report["metrics"]["delay"]["unit"]
    assert "inputs" not in details and "backends" not in details


def test_export_preserves_non_utf8_native_logs_without_changing_score(tmp_path, inputs, bindings):
    from dataclasses import replace

    from benchmarking.evidence.archive import EvaluationArchive
    from benchmarking.results.package import evaluation_export

    original = bindings['check'].run
    raw = b'Calibre native log: temperature 25\xb0C\n'
    bindings['check'].run = lambda job, assets: replace(
        original(job, assets), evidence={'calibre.log': Asset(raw, 'text')})
    report = evaluate(tmp_path, inputs, bindings)
    archive = EvaluationArchive(tmp_path / 'report')
    destination, files = tmp_path / 'portable', []
    evaluation_export(archive, destination, files)
    exported = json.loads((destination / 'evaluation/report.json').read_bytes())
    ref = exported['jobs']['drc']['evidence']['calibre.log']
    assert (destination / 'evaluation' / ref['path']).read_bytes() == raw
    assert 'evaluation/' + ref['path'] in files
    assert exported['score'] == report['score']
    assert archive.report == report


def test_attaching_invalid_evidence_leaves_terminal_result_and_files_unchanged(tmp_path, inputs, bindings, monkeypatch):
    from types import SimpleNamespace

    from benchmarking.evidence.archive import EvaluationArchive
    from benchmarking.participants.attempt.attachments import attach_session_evidence

    report = evaluate(tmp_path, inputs, bindings)
    archive = EvaluationArchive(tmp_path / 'report')
    ref = report['jobs']['drc']['evidence']['log']
    artifact = tmp_path / 'report' / ref['path']
    artifact.chmod(0o600)
    artifact.write_bytes(b'corrupted evidence')
    run = tmp_path / 'participant'
    run.mkdir()
    path = run / 'result.json'
    raw = json.dumps({'format': 'participant-result', 'state': 'finished', 'identity': {},
                      'evaluation': {'session_id': 'session', 'score': report['score']}, 'files': []}).encode()
    path.write_bytes(raw)
    retained = SimpleNamespace(completed_report=lambda: report,
                               final_evidence=lambda _: SimpleNamespace(candidate=b'candidate', top_cell='TOP',
                                                                        evaluation=archive))
    monkeypatch.setattr('benchmarking.participants.attempt.attachments.RunArchive.for_session', lambda *a: retained)
    with pytest.raises(ValueError, match='evidence identity mismatch'):
        attach_session_evidence(path, tmp_path / 'store')
    assert path.read_bytes() == raw
    assert {p.name for p in run.iterdir() if not p.name.startswith('.')} == {'result.json'}


@pytest.mark.parametrize('stage', ['check', 'extract'])
def test_native_license_failure_is_infrastructure_error_not_candidate_rejection(tmp_path, inputs, bindings, stage):
    operation = 'check' if stage == 'check' else 'extract'
    bindings[operation].run = lambda job, assets: JobResult('error', 'Tool/container exited with 129', evidence={
        'console': Asset(b'ERROR (LMF-02002): License call failed for feature CICNG_129.\n'
                         b'ERROR (ELI-00111) Failed to check out license.\n', 'text')})
    report = evaluate(tmp_path, inputs, bindings)
    job = report['jobs']['artifact' if stage == 'check' else 'parasitics']
    assert job['status'] == 'error'
    assert job['failure']['category'] == 'license_unavailable'
    assert report['outcome'] == 'error' and report['score']['value'] is None


def test_post_layout_still_requires_candidate_performance_metrics_without_limits():
    data = tomllib.loads(PLAN.decode())
    data.pop("scoring")
    data["metrics"] = [metric for metric in data["metrics"]
                       if metric["category"] == "physical"]
    with pytest.raises(ValueError, match="needs a performance metric"):
        parse_evaluation(json.dumps(data).encode(), file_format="json")


@pytest.mark.parametrize("bounded", [True, False])
def test_feedback_preserves_candidate_diagnostics_without_scoring(tmp_path, inputs, bindings, bounded):
    report = evaluate(tmp_path, inputs, bindings)
    original = json.dumps(report, sort_keys=True)
    assert report["score"]["value"] > 0

    details = feedback_details(report, tmp_path, bounded=bounded)

    assert set(details) == {"jobs", "metrics", "omitted_jobs", "omitted_metrics"}
    assert details["metrics"]["delay"]["observations"] == report["metrics"]["delay"]["observations"]
    assert details["metrics"]["functional_area"]["value"] == report["metrics"]["functional_area"]["value"]
    assert details["metrics"]["delay"]["unit"] == report["metrics"]["delay"]["unit"]
    assert json.dumps(report, sort_keys=True) == original  # Full judge evidence keeps its score.
    assert json.loads((tmp_path / "report" / "report.json").read_text())["score"] == report["score"]


def test_bounded_feedback_marks_omissions_and_full_report_keeps_diagnostics(tmp_path, inputs, bindings):
    report = evaluate(tmp_path, inputs, bindings)
    report["jobs"].update({f"diagnostic_{i}": {"status": "passed", "reason": "x" * 512}
                           for i in range(100)})
    full = feedback_details(report, tmp_path, bounded=False)
    bounded = feedback_details(report, tmp_path)

    assert len(json.dumps(bounded).encode()) <= 28000
    assert bounded["omitted_jobs"] > 0
    assert len(bounded["jobs"]) + bounded["omitted_jobs"] == len(full["jobs"])
    assert full["omitted_jobs"] == full["omitted_metrics"] == 0
    assert bounded["metrics"] == full["metrics"]


def test_summary_cannot_hide_a_failing_case(tmp_path, inputs, bindings):
    raw = PLAN.replace(b"upper = 4.0", b"lower = 2.0, upper = 4.0")
    report = evaluate(tmp_path, inputs, bindings, raw)
    assert report["metrics"]["delay"]["value"] == 3.0
    assert report["metrics"]["delay"]["status"] == "failed"
    # The aggregate passes, but a lower-valued corner violates the lower bound.
    assert feedback_details(report, tmp_path)["metrics"]["delay"]["shortfall"] == pytest.approx(1.0)


@pytest.mark.parametrize('parallel_jobs', [1, 2])
def test_failed_gate_blocks_dependent_work_but_preserves_independent_checks(tmp_path, inputs, bindings, parallel_jobs):
    bindings['response'].max_parallel_jobs = parallel_jobs
    bindings["check"] = Checks(reject="drc")
    report = evaluate(tmp_path, inputs, bindings)
    assert report["physical_valid"] is False
    assert report["task_success"] is False
    assert report["jobs"]["lvs"]["status"] == "passed"
    assert report["score"]["value"] == 0
    assert report["jobs"]["parasitics"]["status"] == "blocked"
    assert report["metrics"]["delay"]["value"] is None


def test_unscored_post_layout_plan_has_no_score(tmp_path, inputs, bindings):
    import tomli_w

    data = tomllib.loads(PLAN.decode())
    data.pop("scoring")
    for metric in data["metrics"]:
        for key in ("dimension", "baseline", "normalization"):
            metric.pop(key, None)
    report = evaluate(tmp_path, inputs, bindings, tomli_w.dumps(data).encode())
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


@pytest.mark.parametrize('extracted,execution_error,status', [
    (b'.subckt layout IN OUT\n.ends\n', False, 'failed'),
    (b'* Top level circuit layout\n.end\n', False, 'failed'),
    (b'.subckt layout IN OUT\nR1 IN OUT 1000\n.ends\n', False, 'error'),
    (b'.subckt layout IN OUT\n.ends\n', True, 'error'),
])
def test_empty_candidate_lvs_rejection_and_tool_failure_have_distinct_scores(
        tmp_path, monkeypatch, inputs, bindings, extracted, execution_error, status):
    """Device-free extraction is conclusive; unavailable comparison/execution is not."""
    from types import SimpleNamespace

    import tomli_w

    from benchmarking.eda.backends.magic_checks import MagicPhysicalDocker
    from benchmarking.evidence.bundles import publish_bundle

    class Tool:
        identity: ClassVar[dict] = {'tool': 'synthetic native boundary'}

        def __init__(self, image, probe, timeout):
            self.magic = probe[0] == 'magic'

        def run(self, *args, **kwargs):
            files = {'complete.txt': Asset(b'complete\n', 'text')}
            evidence = {'console': Asset(b'Native tool completed\n', 'text')}
            reason = ''
            if self.magic:
                files['extracted.spice'] = Asset(extracted, 'spice')
                if execution_error:
                    reason = 'Container execution unavailable'
                    evidence['execution_error'] = Asset(reason.encode(), 'text')
            else:
                reason = 'Declared tool output is missing: comparison.json'
            return SimpleNamespace(reason=reason, returncode=0, files=files, evidence=evidence)

    monkeypatch.setattr('benchmarking.eda.backends.magic_checks.DockerTool', Tool)
    support = tmp_path / 'support'
    publish_bundle({'tech.tech': Asset(b'', 'text'), 'setup.tcl': Asset(b'', 'tcl')}, {}, support)
    bindings['layout.lvs'] = MagicPhysicalDocker(
        image='unused', check='lvs', support=str(support), technology='tech.tech',
        tech_name='test', style='test', setup='setup.tcl')
    data = tomllib.loads(PLAN.decode())
    lvs = next(job for job in data['jobs'] if job['id'] == 'lvs')
    lvs.update(operation='layout.lvs', inputs={'layout': 'candidate', 'netlist': 'input:netlist'},
               parameters={'top_cell': 'layout', 'subcircuit': 'source'})
    report = evaluate(tmp_path, inputs, bindings, tomli_w.dumps(data).encode())

    assert report['jobs']['lvs']['status'] == status
    assert report['jobs']['lvs']['evidence']['extracted.spice']['sha256'] == hashlib.sha256(extracted).hexdigest()
    assert report['physical_valid'] is (False if status == 'failed' else None)
    assert report['task_success'] is (False if status == 'failed' else None)
    assert report['score']['value'] == (0 if status == 'failed' else None)
    assert report['jobs']['parasitics']['status'] == 'blocked'


@pytest.mark.parametrize("status", ["failed", "error"])
def test_unusable_candidate_extraction_rejects_layout_with_zero_score(
        tmp_path, inputs, bindings, status):
    reason = "Extracted netlist introduced a resistive connection between distinct ports"

    class RejectedExtractor(Extractor):
        def run(self, job, assets):
            return JobResult(status, reason, evidence={"console": Asset(reason.encode(), "text")})

    bindings["extract"] = RejectedExtractor()
    report = evaluate(tmp_path, inputs, bindings)
    assert report["physical_valid"] is True
    assert report["jobs"]["parasitics"]["status"] == "failed"
    assert report["jobs"]["parasitics"]["reason"] == reason
    assert report["jobs"]["parasitics"]["evidence"]["console"]["sha256"] == hashlib.sha256(reason.encode()).hexdigest()
    assert report["jobs"]["nominal"]["status"] == "blocked"
    assert report["jobs"]["slow"]["status"] == "blocked"
    assert report["outcome"] == "failed"
    assert report["task_success"] is False
    assert report["score"]["value"] == 0


@pytest.mark.parametrize("evidence_name", ["execution_error", "cleanup_error", "magic:execution_error"])
def test_extraction_infrastructure_failure_remains_unknown(
        tmp_path, inputs, bindings, evidence_name):
    class UnavailableExtractor(Extractor):
        def run(self, job, assets):
            return JobResult("error", "Container execution unavailable",
                             evidence={evidence_name: Asset(b"infrastructure evidence", "text")})

    bindings["extract"] = UnavailableExtractor()
    report = evaluate(tmp_path, inputs, bindings)
    assert report["jobs"]["parasitics"]["status"] == "error"
    assert report["outcome"] == "error"
    assert report["task_success"] is None
    assert report["score"]["value"] is None


def test_unexpected_extraction_adapter_exception_remains_unknown(tmp_path, inputs, bindings):
    class BrokenExtractor(Extractor):
        def run(self, job, assets):
            raise RuntimeError("Unexpected adapter defect")

    bindings["extract"] = BrokenExtractor()
    report = evaluate(tmp_path, inputs, bindings)
    assert report["jobs"]["parasitics"]["status"] == "error"
    assert report["outcome"] == "error"
    assert report["score"]["value"] is None


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
requirement = { upper = 2.0, rationale = "The synthetic slow event must occur within its stimulus cycle." }
'''
    bindings["response"] = MixedSimulator()
    report = evaluate(tmp_path, inputs, bindings, raw)
    assert report["metrics"]["slow_limit"]["status"] == "failed"
    assert report["metrics"]["delay"]["status"] == "blocked"
    assert report["outcome"] == "failed"
    assert report["task_success"] is False
    assert report["score"]["value"] == 0


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
    raw = raw.replace(b'baseline = ["source_nominal:delay", "source_slow:delay"]\n', b"")
    raw = raw.replace(b'normalization = "ratio"\n', b"").replace(b'dimension = "response"\n', b"")
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
    metric['requirement'] = {**{k: v for k, v in [('lower', lower), ('upper', upper)] if v is not None},
                             'rationale': 'The synthetic voltage must lie in the declared operating interval.'}
    raw = {'mode': 'characterization',
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
