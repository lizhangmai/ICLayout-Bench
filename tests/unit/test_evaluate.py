import hashlib
import json
import sys
import tomllib
from typing import ClassVar

import pytest
from helpers.evaluation import PLAN, Checks, Extractor, Simulator, evaluate

from benchmarking.evaluation import parse_evaluation
from benchmarking.evaluation.contracts import JobResult, Measurement
from benchmarking.evaluation.feedback import feedback_details
from benchmarking.evaluation.runner import run_evaluation
from benchmarking.files import Asset

pytestmark = pytest.mark.unit


def test_direct_native_jobs_share_the_unlimited_eda_default():
    """Preview and operator callers must not need their own timeout opt-out."""
    from benchmarking.eda.environment import ExternalRuntime
    from benchmarking.execution.tools.budget import tool_time_limits
    from benchmarking.execution.tools.native import NativeTool

    runtime = ExternalRuntime('test', {'image': 'unused', 'environment': {}, 'mounts': []})
    tool = NativeTool(runtime, timeout_seconds=.02)
    command = [sys.executable, '-c', 'import time; time.sleep(.1); print("complete")']
    result = tool.run(command, {}, {})
    assert result.returncode == 0 and not result.reason
    assert result.evidence['console'].content.strip() == b'complete'
    with tool_time_limits(True):
        limited = tool.run(command, {}, {})
    assert limited.returncode is None and 'time limit' in limited.reason
    assert tool.run(command, {}, {}).returncode == 0


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
    from benchmarking.execution.tools.budget import tool_time_limits
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
    with tool_time_limits(True):
        if entry == 'qualification':
            with pytest.raises(ValueError, match='Qualification did not pass'):
                evaluate_at('shared-policy')
            inherited = json.loads((tmp_path / 'shared-policy/evaluation/report.json').read_text())
        else:
            inherited = evaluate_at('shared-policy')
    assert inherited['tool_time_limits'] is True
    assert inherited['jobs']['nominal']['status'] == 'error'
    # An explicitly bounded probe must not change later evaluation defaults.
    assert evaluate_at('independent')['task_success'] is True


@pytest.mark.parametrize('phase', ['feedback', 'final'])
@pytest.mark.parametrize('limited', [False, True])
def test_session_evaluation_inherits_shared_tool_policy(tmp_path, inputs, bindings, phase, limited):
    from types import SimpleNamespace

    from benchmarking.eda.environment import ExternalRuntime
    from benchmarking.execution.budgets import PhaseBudgets
    from benchmarking.execution.harness import PROCESS_FEEDBACK_CAPABILITY, HarnessSpec
    from benchmarking.execution.tools.budget import tool_time_limits
    from benchmarking.execution.tools.native import NativeTool
    from benchmarking.execution.workspace import SessionResult
    from benchmarking.execution.workspace.config import RunConfig
    from benchmarking.service.session import run_session

    tool = NativeTool(ExternalRuntime('test', {'image': 'unused', 'environment': {}, 'mounts': []}),
                      timeout_seconds=.02)
    original = bindings['response'].run

    def simulate(job, assets):
        result = tool.run([sys.executable, '-c', 'import time; time.sleep(.1); print("complete")'], {}, {})
        if result.reason:
            return JobResult('error', result.reason, evidence=result.evidence)
        return original(job, assets)

    bindings['response'].run = simulate
    bindings['response'].max_parallel_jobs = 2
    task = SimpleNamespace(hours=None, problem='Synthetic session timeout regression',
                           evaluation=parse_evaluation(PLAN), digest='fixture', witnessed=True,
                           evaluation_inputs=lambda: {**inputs, 'task': Asset(b'{}', 'json')},
                           input_assets=lambda: {'netlist': inputs['input:netlist']})
    config = RunConfig('fixture', 'unused', ('fixture',), 10, None, None, None, 16, {}, {},
                       Asset(b'fixture', 'text'),
                       HarnessSpec(capabilities=(PROCESS_FEEDBACK_CAPABILITY,)),
                       PhaseBudgets(10))
    feedback_reports = []

    class Session:
        def run(self, task, config, resources, message, *, feedback, **kwargs):
            if phase == 'feedback':
                feedback_reports.append(feedback(inputs['candidate'], 1)['report'])
            return SessionResult('completed', '', 0, 0, [],
                                 inputs['candidate'] if phase == 'final' else None,
                                 Asset(b'', 'text'), False, {})

    with tool_time_limits(limited):
        run_session(task, config, {}, bindings, tmp_path / 'session', session=Session())
    report = (feedback_reports[0] if phase == 'feedback' else
              json.loads((tmp_path / 'session/evaluation/report.json').read_text()))
    assert report['tool_time_limits'] is limited
    assert report['task_success'] is (None if limited else True), {
        name: result['reason'] for name, result in report['jobs'].items()
        if result['status'] == 'error'}


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


@pytest.mark.parametrize('termination', ['budget_exhausted', 'agent_error'])
def test_export_preserves_termination_score_and_candidate_quality(tmp_path, inputs, bindings, termination):
    from benchmarking.evidence.archive import RunArchive
    from benchmarking.results.package import (
        ParticipantEvidence,
        TraceEvidence,
        export_run,
    )

    report = evaluate(tmp_path, inputs, bindings)
    run = tmp_path / 'run'
    run.mkdir()
    (tmp_path / 'report').rename(run / 'evaluation')
    raw = (run / 'evaluation/report.json').read_bytes()
    zero = {'method': 'layout', 'value': 0.0, 'maximum': 100, 'reference': 100,
            'components': {'G': 0.0, 'E': None, 'Q': None}}
    (run / 'run.json').write_text(json.dumps({
        'termination': termination, 'outcome': 'passed', 'score': zero,
        'evaluation': dict(Asset(raw, 'json').identity(), path='evaluation/report.json'),
    }))
    service = {'state': 'complete', 'score': zero, 'outcome': 'pass'}
    archive = RunArchive(run)
    final = archive.final_evidence(service)
    result = {'files': []}
    export_run(tmp_path / 'portable', ParticipantEvidence(service, final, TraceEvidence(b'', ''), None, ()), result)

    assert result['evaluation']['score'] == zero
    assert result['evaluation']['termination'] == termination
    exported = json.loads((tmp_path / 'portable/evaluation/report.json').read_text())
    assert exported['score'] == report['score'] and exported['score']['value'] > 0
    assert 'termination' not in service
    with pytest.raises(ValueError, match='Service score differs'):
        archive.final_evidence(dict(service, score=report['score']))


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


def test_last_failure_is_not_reclassified_from_an_earlier_retry_log(tmp_path, inputs, bindings):
    bindings['check'].run = lambda job, assets: JobResult('error', 'Invalid native input', evidence={
        'console': Asset(b'Invalid native input', 'text'),
        'tool-attempts/1/evidence/console': Asset(b'ERROR (ELI-00111) Failed to check out license.\n', 'text')})
    report = evaluate(tmp_path, inputs, bindings)
    assert report['jobs']['artifact'].get('failure') is None
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


@pytest.mark.parametrize('extracted,execution_error,comparison,status', [
    (b'.subckt layout IN OUT\n.ends\n', False, 'missing', 'failed'),
    (b'* Top level circuit layout\n.end\n', False, 'missing', 'failed'),
    (b'.subckt layout IN OUT\nR1 IN OUT 1000\n.ends\n', False, 'missing', 'error'),
    (b'.subckt layout IN OUT\n.ends\n', True, 'missing', 'error'),
    (b'.subckt layout IN OUT\nR1 IN OUT 1000\n.ends\n', False, 'mismatch', 'failed'),
    (b'.subckt layout IN OUT\nR1 IN OUT 1000\n.ends\n', False, 'incomplete', 'error'),
    (b'.subckt layout IN OUT\nR1 IN OUT 1000\n.ends\n', False, 'invalid_json', 'error'),
])
def test_candidate_lvs_rejection_and_tool_failure_have_distinct_scores(
        tmp_path, monkeypatch, inputs, bindings, extracted, execution_error, comparison, status):
    """Completed native rejections score zero; unavailable or invalid reports do not."""
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
            elif comparison == 'missing':
                reason = 'Declared tool output is missing: comparison.json'
            else:
                child = {'name': ['child', 'child'], 'nets': [2, 2],
                         'devices': [[['nmos', 1]], [['nmos', 1]]]}
                if comparison == 'mismatch':
                    child['badnets'] = [[['layout_net'], ['source_net']]]
                top = {'name': ['layout', 'source'], 'pins': [['IN', 'OUT'], ['IN', 'OUT']],
                       'nets': [2, 2], 'devices': [[['child', 1]], [['child', 1]]]}
                raw = b'not JSON' if comparison == 'invalid_json' else json.dumps([child, top]).encode()
                files['comparison.json'] = Asset(raw, 'json')
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


@pytest.mark.parametrize('check,diagnostic,interruption,expected', [
    ('artifact', 'stream_80053', None, 0),
    ('artifact', 'stream_80054', None, 0),
    ('drc', 'precision', None, 0),
    ('lvs', 'precision', None, 0),
    ('drc', 'record_offset', None, 0),
    ('lvs', 'record_offset', None, 0),
    ('rc', 'record_offset', None, 0),
    ('artifact', 'stream_80053', 'license', None),
    ('artifact', 'stream_80053', 'crash', None),
    ('artifact', 'stream_80054', 'timeout', None),
    ('artifact', 'stream_80053', 'cleanup', None),
    ('artifact', 'stream_80053', 'execution', None),
    ('artifact', 'stream_80054', 'unexpected_reason', None),
    ('artifact', 'stream_80054', 'unexpected_exit', None),
    ('artifact', 'unknown', None, None),
    ('drc', 'precision', 'license', None),
    ('drc', 'record_offset', 'crash', None),
    ('drc', 'precision', 'timeout', None),
    ('drc', 'precision', 'cleanup', None),
    ('drc', 'precision', 'execution', None),
    ('drc', 'precision', 'unexpected_reason', None),
    ('drc', 'precision', 'unexpected_exit', None),
    ('drc', 'other_input', None, None),
    ('drc', 'unknown', None, None),
])
def test_native_gds_rejections_score_zero_but_execution_faults_remain_unknown(
        tmp_path, native_tmp_path, monkeypatch, inputs, bindings, check, diagnostic, interruption, expected):
    """Replay native input rejection through the actual adapters and score runner."""
    from types import SimpleNamespace

    import tomli_w

    from benchmarking.eda.backends.calibre import CalibreNative
    from benchmarking.eda.backends.customcompiler import CustomCompilerGeometryNative
    from benchmarking.eda.environment import ExternalRuntime
    from benchmarking.execution.tools import ToolResult
    from benchmarking.execution.tools.native import NativeTool

    logs = {
        'stream_80053': 'ERROR: (IMPORT_STREAM-80053): The Stream file is invalid.\n',
        'stream_80054': ('ERROR: (IMPORT_STREAM-80054): The Stream file is invalid. '
                         'An invalid record type "2" was read. The EndLib record type "4" was expected.\n'),
        'precision': ('ERROR: LAYOUT [PATH] precision 1000 is not consistent with database '
                      'precision 134217728000 in input file candidate.gds.\n'),
        'record_offset': 'ERROR: Failure to read input file candidate.gds at record offset 13215926.\n',
        'other_input': 'ERROR: Failure to read input file process.rules at record offset 13215926.\n',
        'unknown': 'ERROR: Unrecognized tool error.\n',
    }
    raw = logs[diagnostic].encode()
    log_name = 'stream.log' if check == 'artifact' else 'calibre.log'
    label = 'Custom Compiler' if check == 'artifact' else 'Calibre'
    code = 1 if check == 'artifact' else 4
    reason = f'Native {label} exited with {code}'
    evidence = {'console': Asset(b'Native console\n', 'text')}
    if interruption in {'execution', 'cleanup'}:
        evidence[interruption + '_error'] = Asset(b'Operator execution failed', 'text')
    elif interruption == 'license':
        evidence['console'] = Asset(b'ERROR (LMF-02002): License call failed. Invalid license file syntax.\n', 'text')
    elif interruption == 'crash':
        evidence['console'] = Asset(b'Fatal error (signal SIGSEGV) - crash handler invoked\n', 'text')
    elif interruption == 'timeout':
        code, reason = None, f'Native {label} exceeded its fixed time limit'
    elif interruption == 'unexpected_reason':
        reason = 'Output collection failed'
    elif interruption == 'unexpected_exit':
        code, reason = -11, f'Native {label} exited with -11'
    result = ToolResult(code, reason, {log_name: Asset(raw, 'text')}, evidence)
    monkeypatch.setattr(NativeTool, 'probe', lambda *args, **kwargs:
                        SimpleNamespace(returncode=0, stdout=b'Synthetic release'))
    monkeypatch.setattr(NativeTool, 'run', lambda *args, **kwargs: result)
    (native_tmp_path / 'process.rules').write_text('width_rule { INTERNAL M1 < 0.2 }\n')
    runtime = ExternalRuntime('test', {'image': 'unused', 'environment': {'PDK_ROOT': str(native_tmp_path)},
        'mounts': [{'source': str(native_tmp_path), 'target': str(native_tmp_path), 'release': 'test',
                    'identity_paths': ['process.rules']}]})
    backend = (CustomCompilerGeometryNative(runtime=runtime, check=check) if check == 'artifact'
               else CalibreNative(runtime=runtime, check=check, deck='process.rules'))
    bindings['native'] = backend
    inputs['task'] = Asset(b'{"output":{"top_cell":"TOP","max_bytes":100000},"netlist_subcircuit":"TOP"}', 'json')
    data = tomllib.loads(PLAN.decode())
    target = 'parasitics' if check == 'rc' else check
    job = next(job for job in data['jobs'] if job['id'] == target)
    job.update(operation='native', inputs={'layout': 'candidate', 'task': 'task'})
    if check in {'lvs', 'rc'}:
        job['inputs']['netlist'] = 'input:netlist'
    if check == 'rc':
        job['parameters'] = {'ports': ['IN', 'OUT']}
    report = evaluate(tmp_path, inputs, bindings, tomli_w.dumps(data).encode())

    status = 'failed' if expected == 0 else 'error'
    assert report['jobs'][target]['status'] == status, report['jobs'][target]['reason']
    assert report['jobs'][target]['evidence'][log_name]['sha256'] == hashlib.sha256(raw).hexdigest()
    assert report['score']['value'] == expected
    assert report['task_success'] is (False if expected == 0 else None)
    assert report['jobs']['nominal']['status'] == 'blocked'


@pytest.mark.parametrize("status", ["failed", "error"])
def test_extractor_explicitly_distinguishes_rejection_from_evaluator_error(
        tmp_path, inputs, bindings, status):
    reason = "Extracted netlist introduced a resistive connection between distinct ports"

    class RejectedExtractor(Extractor):
        def run(self, job, assets):
            return JobResult(status, reason, evidence={"console": Asset(reason.encode(), "text")})

    bindings["extract"] = RejectedExtractor()
    report = evaluate(tmp_path, inputs, bindings)
    assert report["physical_valid"] is True
    assert report["jobs"]["parasitics"]["status"] == status
    assert report["jobs"]["parasitics"]["reason"] == reason
    assert report["jobs"]["parasitics"]["evidence"]["console"]["sha256"] == hashlib.sha256(reason.encode()).hexdigest()
    assert report["jobs"]["nominal"]["status"] == "blocked"
    assert report["jobs"]["slow"]["status"] == "blocked"
    assert report["outcome"] == status
    assert report["task_success"] is (False if status == "failed" else None)
    assert report["score"]["value"] == (0 if status == "failed" else None)


@pytest.mark.parametrize("problem,expected", [
    ("event", 0), ("mixed", 0), ("missing", None), ("ambiguous", None),
    ("model", None), ("crash", None), ("timeout", None),
])
def test_ngspice_event_rejection_scores_zero_but_execution_and_report_faults_do_not(
        tmp_path, inputs, bindings, monkeypatch, problem, expected):
    """Replay the PTAT missing-crossing pattern through the real adapter and scorer."""
    from benchmarking.eda.backends import ngspice
    from benchmarking.execution.tools import ToolResult

    event_log = (b"No. of Data Rows : 100001\n"
                 b"Error: measure delay when(WHEN): out of interval\n"
                 b" meas tran delay when error=1m fall=last failed!\n")

    class Tool:
        def __init__(self, *args):
            self.identity = {"image_id": "test"}

        def run(self, command, files, exports, **kwargs):
            slow = b"load=2" in files["parameters.spice"].content
            log, console, reason, code = event_log, b"", "", 0
            if slow and problem != "mixed":
                log = b"delay = 3.0\n"
            elif problem in {"missing", "ambiguous"}:
                log = b"No. of Data Rows : 100001\n"
                if problem == "ambiguous":
                    log += b"delay = 1\ndelay = 2\n"
            elif problem == "model":
                log += b"Error: unknown model type\n"
            elif problem == "crash":
                console = b"Fatal error (signal SIGSEGV) - crash handler invoked\n"
            elif problem == "timeout" or slow and problem == "mixed":
                reason, code = "Tool exceeded its fixed time limit", None
            evidence = {"console": Asset(console, "text")}
            if reason:
                evidence["execution_error"] = Asset(reason.encode(), "text")
            return ToolResult(code, reason, {"ngspice.log": Asset(log, "text")}, evidence)

    monkeypatch.setattr(ngspice, "DockerTool", Tool)
    bindings["response"] = ngspice.NgspiceDocker(image="unused")
    data = tomllib.loads(PLAN.decode())
    inputs["input:deck"] = Asset(b"* Required transient event\n", "spice")
    for job in data["jobs"]:
        if job["stage"] == "simulate":
            job["parameters"] = {"measurements": {"delay": "s"}, "values": job["parameters"]}
            job["inputs"]["deck"] = "input:deck"
    for source in data["pre_layout"]["jobs"].values():
        source["parameters"] = {"measurements": {"delay": "s"}, "values": source["parameters"]}
        source["inputs"]["deck"] = "input:deck"
        source["input_sha256"]["deck"] = inputs["input:deck"].sha256
    plan = parse_evaluation(json.dumps(data).encode(), file_format="json")
    report = run_evaluation(plan, inputs, bindings, tmp_path / "report")
    assert report["score"]["value"] == expected
    assert report["outcome"] == ("failed" if expected == 0 else "error")
    assert report["task_success"] is (False if expected == 0 else None)
    assert report["jobs"]["nominal"]["evidence"]["log"]["sha256"]


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
