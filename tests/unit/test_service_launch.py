"""Installed-service supervision with real process groups and synthetic output."""

import subprocess
import sys

import pytest

from benchmarking.service import launch

pytestmark = pytest.mark.unit


@pytest.fixture
def child(monkeypatch):
    original = subprocess.Popen
    launched = []

    def prepare(code):
        def popen(arguments, **settings):
            process = original([sys.executable, "-I", "-c", code], **settings)
            launched.append((process, arguments, settings))
            return process
        monkeypatch.setattr(launch.subprocess, "Popen", popen)
        return launched

    yield prepare
    for process, _, _ in launched:
        launch.stop(process, timeout=1)


READY = "print('Local development service: http://127.0.0.1:12345', flush=True); import time; time.sleep(60)"


def test_service_passes_declared_settings_and_stops_on_body_failure(tmp_path, child):
    launched = child(READY)
    events = []
    with pytest.raises(ValueError, match="caller failure"), launch.launch_service(
            ["--solver-runtime", "declared"], output=tmp_path,
            environment={"DECLARED_SETTING": "fixture"},
            on_event=lambda kind, **data: events.append((kind, data))) as running:
        assert running.endpoint == "http://127.0.0.1:12345"
        raise ValueError("caller failure")
    process, arguments, settings = launched[0]
    assert arguments[-2:] == ["--solver-runtime", "declared"]
    assert settings["env"] == {"DECLARED_SETTING": "fixture"}
    assert process.poll() is not None
    assert [kind for kind, _ in events] == ["service_spawned", "service_ready", "service_exit"]
    assert events[-1][1]["ready"] is True


def test_ready_service_can_be_retained_for_recovery(tmp_path, child):
    launched = child(READY)
    with launch.launch_service([], output=tmp_path, environment={}) as running:
        running.retain()
    process = launched[0][0]
    assert process.poll() is None
    assert process.stdout.closed


@pytest.mark.parametrize("code,error", [
    ("print('startup failed', flush=True); import time; time.sleep(60)", RuntimeError),
    ("import time; time.sleep(60)", TimeoutError),
])
def test_failed_startup_never_leaves_a_service_alive(tmp_path, child, code, error):
    launched = child(code)
    with pytest.raises(error), launch.launch_service([], output=tmp_path, environment={}, startup_timeout=.2):
        pytest.fail("Failed startup must not yield a service")
    assert launched[0][0].poll() is not None
