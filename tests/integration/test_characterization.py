"""Real simulator qualification with analytical expectations, not layout scores."""

import math
import re
from pathlib import Path

import pytest
from helpers.spice_raw import read_raw
from helpers.stimuli import command, number

from benchmarking.evaluate import run_evaluation
from benchmarking.evaluation import parse_evaluation
from benchmarking.files import Asset
from benchmarking.toolchains import load_toolchain

pytestmark = pytest.mark.integration
FIXTURES = Path(__file__).resolve().parents[2] / "tests/fixtures/characterization"


@pytest.fixture(scope="module")
def backends():
    return load_toolchain(FIXTURES / "toolchain.toml")


def asset(name):
    return Asset((FIXTURES / name).read_bytes(), "spice")


def rc_inputs():
    return {"input:dut": asset("rc.spice"), "input:transient": asset("rc_transient.spice"),
            "input:ac": asset("rc_ac.spice")}


def test_rc_transient_and_ac_match_analytic_values_and_retain_waveforms(tmp_path, backends):
    plan = parse_evaluation((FIXTURES / "rc.toml").read_bytes())
    report = run_evaluation(plan, rc_inputs(), backends, tmp_path / "rc")
    assert report["outcome"] == "passed", report["jobs"]
    assert report["task_success"] is None
    pulse = [number(token) for token in re.search(r'PULSE\(([^)]+)\)',
             asset('rc_transient.spice').content.decode()).group(1).split()]
    for job in plan.jobs:
        values = job.parameters['values']
        tau = values['r_series'] * values['c_load']
        # A short linear input ramp adds half its rise time to the ideal
        # step delay. Bound that approximation independently of ngspice.
        assert pulse[3] / tau < 0.001
        expected = {'t50': pulse[2] + pulse[3] / 2 + math.log(2) * tau,
                    'bandwidth': 1 / (2 * math.pi * tau)}
        for name, measurement in report['jobs'][job.id]['measurements'].items():
            assert measurement['value'] == pytest.approx(expected[name], rel=0.002)
    waveform = report['jobs']['step_nominal']['outputs']['waveform']
    rows = read_raw((tmp_path / 'rc' / waveform['path']).read_bytes())
    assert len(rows) > 1 and rows[0]['time'] < rows[-1]['time']
    assert report["backends"]["circuit.simulate"]["image_id"].startswith("sha256:")


def test_another_circuit_and_metric_set_uses_same_backend_and_core(tmp_path, backends):
    plan = parse_evaluation((FIXTURES / "divider.toml").read_bytes())
    report = run_evaluation(plan, {"input:dut": asset("divider.spice"), "input:dc": asset("divider_dc.spice")},
                            backends, tmp_path / "divider")
    assert report["outcome"] == "passed", report["jobs"]
    circuit = asset('divider.spice').content.decode()
    top = number(command(circuit, 'Rtop')[-1])
    bottom = number(command(circuit, 'Rbottom')[-1])
    voltage = number(command(asset('divider_dc.spice').content.decode(), 'Vdrive')[-1])
    assert report['metrics']['voltage_ratio']['value'] == pytest.approx(bottom / (top + bottom))
    assert report['metrics']['dc_power']['value'] == pytest.approx(voltage ** 2 / (top + bottom))


def test_slower_rc_fails_specs_without_becoming_a_tool_error(tmp_path, backends):
    raw = (FIXTURES / "rc.toml").read_bytes().replace(b"2000.0", b"4000.0")
    report = run_evaluation(parse_evaluation(raw), rc_inputs(), backends, tmp_path / "slow")
    assert all(job["status"] == "passed" for job in report["jobs"].values())
    assert report["outcome"] == "failed"
    assert report["specs_pass"] is False
    assert report["metrics"]["step_time"]["status"] == "failed"
    assert report["metrics"]["bandwidth"]["status"] == "failed"


def test_simulator_exit_success_without_measurement_is_an_error(tmp_path, backends):
    raw = (FIXTURES / "divider.toml").read_bytes().replace(b"ratio =", b"absent_measurement =")
    report = run_evaluation(parse_evaluation(raw),
                            {"input:dut": asset("divider.spice"), "input:dc": asset("divider_dc.spice")},
                            backends, tmp_path / "missing")
    assert report["outcome"] == "error"
    assert report["specs_pass"] is None
    job = report["jobs"]["operating_point"]
    assert job["measurements"] == {}
    assert job["evidence"]["log"]["bytes"] > 0
