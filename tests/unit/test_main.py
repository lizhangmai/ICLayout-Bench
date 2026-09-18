"""Small command-line summaries remain useful without replacing durable reports."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_ROOT = ROOT
_SPEC = importlib.util.spec_from_file_location("iclayout_bench_main", ROOT / "benchmarking/engine/cli.py")
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
_inference_preflight = _MODULE._inference_preflight


pytestmark = [pytest.mark.unit, pytest.mark.acceptance, pytest.mark.acceptance_fast]


def test_inference_preflight_never_reports_a_model_call():
    class Profile:
        base_url = "https://example.invalid/v1"
        model = "test-model"
        wire_api = "responses"
        api_key_env = "ICLAYOUT_BENCH_TEST_KEY"

    assert _inference_preflight(Profile(), None, False) == {
        "status": "missing_credential",
        "model_call": False,
        "endpoint": "https://example.invalid/v1",
        "model": "test-model",
        "wire_api": "responses",
        "credential_env": "ICLAYOUT_BENCH_TEST_KEY",
        "credential_present": False,
        "harness": None,
    }


@pytest.mark.parametrize("override", [False, True], ids=["case-default", "explicit-toolchain"])
def test_case_toolchain_default_and_explicit_override(executable_case, tmp_path, monkeypatch, capsys,
                                                     override):
    command = "evaluate"
    case = executable_case
    output = tmp_path / "result"
    argv = ["benchmarking.engine.cli", command, str(case), "--output", str(output)]
    selected = []
    invoked = []
    bindings = {}

    def load(path):
        selected.append(path)
        return bindings

    monkeypatch.setattr(_MODULE, "load_toolchain", load)
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
