"""Small command-line summaries remain useful without replacing durable reports."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location("layout_bench_main", ROOT / "main.py")
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
_run_summary = _MODULE._run_summary
_inference_preflight = _MODULE._inference_preflight


pytestmark = [pytest.mark.unit, pytest.mark.acceptance, pytest.mark.acceptance_fast]


def test_run_summary_surfaces_failed_gates_and_inference_count(tmp_path):
    output = tmp_path / "run"
    evaluation = output / "evaluation"
    evaluation.mkdir(parents=True)
    (evaluation / "report.json").write_text(json.dumps({
        "jobs": {
            "artifact": {"status": "passed"},
            "lvs": {"status": "failed", "reason": "LVS mismatch"},
        },
        "metrics": {
            "delay": {"status": "failed", "reason": "upper bound exceeded"},
        },
    }))
    summary = _run_summary({
        "termination": "completed", "reason": "", "outcome": "failed", "task_success": False,
        "candidate": {"sha256": "abc"},
        "inference": {"requests": [{"sequence": 1}, {"sequence": 2}]},
    }, output)
    assert summary["inference_requests"] == 2
    assert summary["failures"] == [
        {"kind": "job", "id": "lvs", "status": "failed", "reason": "LVS mismatch"},
        {"kind": "metric", "id": "delay", "status": "failed", "reason": "upper bound exceeded"},
    ]


def test_run_summary_does_not_hide_missing_evaluation(tmp_path):
    summary = _run_summary({
        "termination": "completed", "reason": "", "outcome": "no_submission", "task_success": False,
        "candidate": None,
    }, tmp_path / "run")
    assert summary == {
        "report": str(tmp_path / "run/run.json"),
        "termination": "completed", "reason": "", "outcome": "no_submission",
        "task_success": False, "candidate": None,
    }


def test_inference_preflight_never_reports_a_model_call():
    class Profile:
        base_url = "https://example.invalid/v1"
        model = "test-model"
        wire_api = "responses"
        api_key_env = "LAYOUT_BENCH_TEST_KEY"

    assert _inference_preflight(Profile(), None, False) == {
        "status": "missing_credential",
        "model_call": False,
        "endpoint": "https://example.invalid/v1",
        "model": "test-model",
        "wire_api": "responses",
        "credential_env": "LAYOUT_BENCH_TEST_KEY",
        "credential_present": False,
        "harness": None,
    }


@pytest.mark.parametrize("score", [None, {"method": "layout-v1", "value": 0, "maximum": 100}])
def test_run_summary_preserves_official_attempt_score_without_evaluation(tmp_path, score):
    summary = _run_summary({
        "termination": "budget_exhausted", "reason": "time limit", "outcome": "no_submission",
        "task_success": False, "candidate": None, "score": score,
    }, tmp_path)
    assert "score" in summary
    assert summary["score"] == score


@pytest.mark.parametrize("command", ["run", "evaluate"])
@pytest.mark.parametrize("override", [False, True], ids=["case-default", "explicit-toolchain"])
def test_case_toolchain_default_and_explicit_override(executable_case, tmp_path, monkeypatch, capsys,
                                                     command, override):
    case = executable_case
    output = tmp_path / "result"
    argv = ["main.py", command, str(case), "--output", str(output)]
    selected = []
    invoked = []
    bindings = {}

    def load(path):
        selected.append(path)
        return bindings

    monkeypatch.setattr(_MODULE, "load_toolchain", load)
    if command == "run":
        argv += ["--agent", "agent.toml"]
        monkeypatch.setattr(_MODULE, "load_run_config", lambda path: object())

        def run(task, config, resources, backends, destination, **kwargs):
            assert backends is bindings
            assert task.id == "synthetic-circuit"
            invoked.append(destination)
            return {"termination": "completed", "reason": "", "outcome": "passed",
                    "task_success": True, "candidate": None}

        monkeypatch.setattr(_MODULE, "run_agent", run)
    else:
        candidate = tmp_path / "candidate.gds"
        candidate.write_bytes(b"CLI routing fixture; no EDA invocation")
        argv.append(str(candidate))

        def evaluate(plan, inputs, backends, destination, **kwargs):
            assert backends is bindings
            assert plan.mode == "physical"
            assert inputs["candidate"].content == b"CLI routing fixture; no EDA invocation"
            assert kwargs["task_witnessed"] is False
            invoked.append(destination)
            return {"mode": "physical", "outcome": "passed", "physical_valid": True,
                    "specs_pass": None, "task_success": None, "metrics": {},
                    "task_witnessed": False,
                    "score": {"method": "layout-v1", "value": 90.0, "maximum": 100,
                              "components": {"G": 1, "E": 1, "H": 1, "Q": 0.5}}}

        monkeypatch.setattr(_MODULE, "run_evaluation", evaluate)
    if override:
        argv += ["--toolchain", str(tmp_path / "override.toml")]
    monkeypatch.setattr("sys.argv", argv)
    _MODULE.main()
    assert selected == [tmp_path / "override.toml" if override else case]
    assert invoked == [output]
    if command == "evaluate":
        assert json.loads(capsys.readouterr().out)["score"] == {
            "method": "layout-v1", "value": 90.0, "maximum": 100,
            "components": {"G": 1, "E": 1, "H": 1, "Q": 0.5},
        }
