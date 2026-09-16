"""New HTTP harness contract: independent simulator and scripted provider outputs.

Legacy in-container fixtures do not cover this public loop. Check automatic
submission, bounded operation policy and preserved unknown/error outcomes;
these deterministic checks never count as model or EDA performance.
"""

import json

import pytest
from helpers.service import Simulator

from benchmarking.client import Client
from benchmarking.official import Config, run

pytestmark = pytest.mark.unit


class Provider:
    version = "fixture"

    def __init__(self, actions):
        self.actions = iter(actions)
        self.prompts = []

    def __call__(self, prompt, timeout):
        self.prompts.append(prompt)
        return next(self.actions), {"usage": []}


def action(name, **kwargs):
    return {
        "action": name,
        "command": None,
        "seconds": None,
        "path": None,
        "content": None,
    } | kwargs


@pytest.fixture
def service():
    simulator = Simulator()
    yield simulator
    simulator.stop()


def test_official_loop_submits_model_action_output_and_keeps_simulator_error(
    service, tmp_path
):
    model = Provider(
        [
            action("write", path="generate.py", content="model-owned source"),
            action("exec", command="python generate.py", seconds=10),
            action("finish"),
        ]
    )
    result = run(
        Client(service.endpoint, "operator"),
        "synthetic",
        Config("fixture-model"),
        tmp_path / "run",
        provider=model,
    )
    assert service.files["generate.py"] == b"model-owned source"
    assert service.executions == 1
    assert service.receipt is not None and service.closed
    assert "model-owned source" in model.prompts[-1]
    assert all("session-token" not in prompt for prompt in model.prompts)
    assert result["outcome"] == "error" and result["score"] is None
    assert all(value is None for value in result["usage"].values())
    assert result["condition"]["harness_kind"] == "official"
    recorded = json.loads((tmp_path / "run/harness.json").read_text())
    assert recorded["receipts"] and recorded["error"] is None
    assert "session-token" not in (tmp_path / "run/session.json").read_text()


def test_malformed_action_closes_without_inventing_a_submission(service, tmp_path):
    result = run(
        Client(service.endpoint, "operator"),
        "synthetic",
        Config("fixture-model"),
        tmp_path / "run",
        provider=Provider([{"action": "pretend-success"}]),
    )
    assert service.closed and service.receipt is None
    assert result["score"] is None
    assert (
        json.loads((tmp_path / "run/harness.json").read_text())["error"] == "ValueError"
    )


def test_reserve_time_prevents_another_model_call(service, tmp_path):
    service.remaining = 1
    provider = Provider([])
    run(
        Client(service.endpoint, "operator"),
        "synthetic",
        Config("fixture-model"),
        tmp_path / "run",
        provider=provider,
    )
    assert not provider.prompts and service.closed
