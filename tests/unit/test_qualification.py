"""Qualification retains a passing reference run and checks its input bytes."""

import json
import tomllib
from types import SimpleNamespace

import pytest
from test_evaluate import PLAN

from benchmarking.engine.qualification import audit, run, verify
from benchmarking.evaluation import parse_evaluation
from benchmarking.files import Asset

pytestmark = pytest.mark.unit


def test_qualification_verifies_reference_and_declared_inputs_without_tool_or_contract_bindings(tmp_path, monkeypatch):
    reference, netlist = Asset(b"layout", "gds"), Asset(b"source", "spice")
    task = SimpleNamespace(
        evaluation=SimpleNamespace(external_inputs=lambda: {"candidate", "input:netlist"},
                                   jobs=[SimpleNamespace(id="a-different-plan")],
                                   metrics=(), scoring=None),
        evaluation_inputs=lambda: {"input:netlist": netlist}, digest="task", witnessed=True,
    )
    runtime = SimpleNamespace(task=task, witness=lambda: reference, backends={})
    raw_report = {
        "outcome": "passed", "physical_valid": True, "specs_pass": True,
        "task_success": True, "score": 1.0,
        "engine_sha256": {"evaluate.py": "old"}, "backends": {"check": {"version": "old"}},
        "inputs": {"candidate": {"sha256": reference.sha256},
                   "input:netlist": {"sha256": netlist.sha256}},
        "jobs": {"original-plan": {"status": "passed", "measurements": {}}}, "metrics": {},
    }
    monkeypatch.setattr("benchmarking.engine.qualification.run_evaluation", lambda *args, **kwargs: raw_report)
    output = tmp_path / "qualification"
    record = run(runtime, output)
    report = record["report"]
    assert set(record) == {"format", "report", "contract_review"}
    assert "engine_sha256" not in report and "backend_sha256" not in report
    path = output / "qualification.json"
    assert verify(runtime, output) == record

    # Older retained reports may carry bindings that are no longer freshness checks.
    legacy = {**record, "contract": {"old": "plan"}, "pdk_sha256": "old"}
    legacy["report"] = {**report, "engine_sha256": {"evaluate.py": "old"},
                        "backend_sha256": {"check": "old"}}
    path.write_text(json.dumps(legacy))
    assert verify(runtime, output) == legacy

    legacy["report"]["inputs"]["candidate"] = "changed"
    path.write_text(json.dumps(legacy))
    with pytest.raises(ValueError, match="Qualification input changed: candidate"):
        verify(runtime, output)


# The synthetic plan already owns the observations. These cases protect the
# authoring boundary: ambiguous limits must fail before any reference/tool access,
# while explicit functional requirements and quality are independently visible.
def test_qualification_rejects_implicit_limits_before_accessing_reference(tmp_path):
    plan = parse_evaluation(PLAN)
    runtime = SimpleNamespace(task=SimpleNamespace(evaluation=plan))
    with pytest.raises(ValueError, match="Review the contract before changing the reference"):
        run(runtime, tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()


def test_explicit_requirements_are_audited_separately_from_weights():
    data = tomllib.loads(PLAN.decode())
    for metric in data['metrics']:
        bounds = {key: metric.pop(key) for key in ('lower', 'upper') if key in metric}
        if bounds:
            metric['requirement'] = {**bounds, 'rationale': 'The output event must lie in its input cycle.'}
    plan = parse_evaluation(json.dumps(data).encode(), file_format='json')
    review = audit(plan)
    assert review['minimum_score'] is None
    assert set(review['requirements']) == {m.id for m in plan.metrics if m.is_requirement}
    assert review['quality'] == {key: value for key, value in plan.scoring.weights if value > 0}
    metric = next(m for m in data['metrics'] if 'requirement' in m)
    for invalid in ({'lower': 0}, {'lower': 0, 'rationale': '  '}, {'rationale': 'function'}):
        metric['requirement'] = invalid
        with pytest.raises((ValueError, TypeError)):
            parse_evaluation(json.dumps(data).encode(), file_format='json')
    metric['requirement'] = {'lower': 0, 'rationale': 'function'}
    metric['upper'] = 1
    with pytest.raises(ValueError, match='Mixed legacy'):
        parse_evaluation(json.dumps(data).encode(), file_format='json')


@pytest.mark.parametrize("failure", [None, "drc", "tool"])
def test_retained_evaluation_survives_success_gate_failure_and_tool_error(tmp_path, failure):
    from test_evaluate import Checks, Extractor, Simulator

    data = tomllib.loads(PLAN.decode())
    for metric in data['metrics']:
        bounds = {key: metric.pop(key) for key in ('lower', 'upper') if key in metric}
        if bounds:
            metric['requirement'] = {**bounds, 'rationale': 'Synthetic functional limit.'}
    plan = parse_evaluation(json.dumps(data).encode(), file_format='json')
    task = SimpleNamespace(evaluation=plan, digest='fixture', witnessed=True,
                           evaluation_inputs=lambda: {'input:netlist': Asset(b'schematic', 'spice')})
    runtime = SimpleNamespace(task=task, witness=lambda: Asset(b'synthetic-layout', 'gds'),
                              backends={'check': Checks(reject=failure, crash='drc' if failure == 'tool' else None),
                                        'extract': Extractor(), 'response': Simulator()})
    output = tmp_path / 'qualification'
    if failure:
        with pytest.raises(ValueError, match='did not pass'):
            run(runtime, output, retain_evaluation=True)
    else:
        run(runtime, output, retain_evaluation=True)
        verify(runtime, output)
    raw = output / 'evaluation'
    report = json.loads((raw / 'report.json').read_text())
    assert report['task_success'] is (None if failure == 'tool' else failure is None)
    assert any(p.is_file() and p.read_bytes() == b'artifact' for p in raw.rglob('*'))
    assert (output / 'qualification.json').exists() is (failure is None)
    with pytest.raises(FileExistsError):
        run(runtime, output, retain_evaluation=True)
