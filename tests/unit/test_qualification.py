"""Qualification retains a passing reference run and checks its input bytes."""

import json
import tomllib
from types import SimpleNamespace

import pytest
from test_evaluate import PLAN

from benchmarking.evaluation import parse_evaluation
from benchmarking.evaluation.qualification import audit, run, verify
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
    monkeypatch.setattr("benchmarking.evaluation.qualification.run_evaluation", lambda *args, **kwargs: raw_report)
    output = tmp_path / "qualification"
    record = run(runtime, output)
    report = record["report"]
    assert set(record) == {"format", "report", "contract_review"}
    assert "engine_sha256" not in report and "backend_sha256" not in report
    path = output / "qualification.json"
    assert verify(runtime, output) == record

    record["report"]["inputs"]["candidate"] = "changed"
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="Qualification input changed: candidate"):
        verify(runtime, output)


def test_explicit_requirements_are_audited_separately_from_weights():
    data = tomllib.loads(PLAN.decode())
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
    with pytest.raises(ValueError, match="metric: .*unknown.*upper"):
        parse_evaluation(json.dumps(data).encode(), file_format='json')


@pytest.mark.parametrize("failure", [None, "drc", "tool"])
def test_retained_evaluation_survives_success_gate_failure_and_tool_error(tmp_path, failure):
    from test_evaluate import Checks, Extractor, Simulator

    data = tomllib.loads(PLAN.decode())
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


def test_qualification_binds_generated_inputs_to_origins_without_clock_freshness(tmp_path, monkeypatch):
    reference = Asset(b"layout", "gds")
    inputs = {"input:netlist": Asset(b"authoritative source", "spice"),
              "input:lvs_source": Asset(b"* Netlisted on: 11:00:00\nsource", "spice")}
    task = SimpleNamespace(
        evaluation=SimpleNamespace(external_inputs=lambda: {"candidate", "input:lvs_source"},
                                   metrics=(), scoring=None),
        evaluation_inputs=lambda: dict(inputs), digest="task", witnessed=True,
        evaluator_inputs=(SimpleNamespace(role="lvs_source", derived_from=("netlist",)),))
    runtime = SimpleNamespace(task=task, witness=lambda: reference, backends={})
    raw = {"outcome": "passed", "physical_valid": True, "specs_pass": True,
           "task_success": True, "score": 1.0,
           "inputs": {"candidate": reference.identity(), "input:lvs_source": inputs["input:lvs_source"].identity()},
           "jobs": {"lvs": {"status": "passed", "measurements": {}}}, "metrics": {}}
    monkeypatch.setattr("benchmarking.evaluation.qualification.run_evaluation", lambda *a, **k: raw)
    output = tmp_path / "qualification"
    record = run(runtime, output)
    assert record["report"]["inputs"] == {"candidate": reference.sha256,
                                          "input:netlist": inputs["input:netlist"].sha256}
    original_evidence = raw["inputs"]["input:lvs_source"]
    inputs["input:lvs_source"] = Asset(b"* Netlisted on: 12:34:56\nsource", "spice")
    assert inputs["input:lvs_source"].identity() != original_evidence
    assert verify(runtime, output) == record
    # Existing records remain evidence of their run, without making a generated
    # file's old bytes a current-source freshness condition.
    record["report"]["inputs"]["input:lvs_source"] = original_evidence["sha256"]
    (output / "qualification.json").write_text(json.dumps(record))
    assert verify(runtime, output) == record
    inputs["input:netlist"] = Asset(b"different authoritative circuit", "spice")
    with pytest.raises(ValueError, match="Qualification input changed: input:netlist"):
        verify(runtime, output)
