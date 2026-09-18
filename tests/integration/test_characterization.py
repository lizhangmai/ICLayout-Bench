"""Real simulator qualification with analytical expectations, not layout scores."""

import math
import os
import re
import tomllib
from pathlib import Path

import pytest
import tomli_w
from helpers.spice_raw import read_raw
from helpers.stimuli import command, number

from benchmarking.engine.evaluate import run_evaluation
from benchmarking.engine.ngspice import NgspiceDocker
from benchmarking.engine.toolchains import load_toolchain
from benchmarking.evaluation import parse_evaluation
from benchmarking.files import Asset

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


@pytest.mark.parametrize("formulation", ["conductance", "branch"])
def test_rc_transient_and_ac_match_analytic_values_and_retain_waveforms(tmp_path, formulation):
    config = tomllib.loads((FIXTURES / "rc.toml").read_text())
    inputs = rc_inputs()
    # Branch compilation supports literal extracted resistances. Bind this
    # existing analytical fixture's declared R value separately for each job.
    for job in config["jobs"]:
        role = "dut_" + job["id"]
        resistance = job["parameters"]["values"]["r_series"]
        inputs["input:" + role] = Asset(asset("rc.spice").content.replace(
            b"{r_series}", str(resistance).encode()), "spice")
        job["inputs"]["dut"] = "input:" + role
    del inputs["input:dut"]
    plan = parse_evaluation(tomli_w.dumps(config).encode())
    backend = NgspiceDocker(
        image=os.environ.get("ICLAYOUT_BENCH_TEST_IMAGE", "iclayout-bench-tools:local"),
        resistor_formulation=formulation)
    report = run_evaluation(plan, inputs, {"circuit.simulate": backend}, tmp_path / "rc")
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


@pytest.mark.parametrize("case", ["ia_002_fan_chopper_simple", "ia_003_fan_chopper_pf"])
@pytest.mark.parametrize("limit_multiple,expected", [(0, "passed"), (1, "passed"), (2, "error")])
def test_lock_in_window_validity_is_a_tool_error(tmp_path, case, limit_multiple, expected):
    # Exercise the published validity guard with controlled endpoint errors;
    # the existing divider supplies finite measurements without an expensive PEX run.
    root = FIXTURES.parents[2]
    case_path = root / "tasks/ihp-sg13g2/analog-db/cases" / case
    problem = (case_path / "problem.md").read_text()
    limit_ps = re.search(r"summed endpoint error must not exceed ([\d.]+) ps", problem)
    assert limit_ps, "The solver contract must publish the measurement-validity limit"
    boundary_error = limit_multiple * float(limit_ps[1]) * 1e-12
    deck = (case_path / "materials/testbench.spice").read_text()
    guard = deck.split("let boundary_error_s=", 1)[1].split("\n", 1)[1].split("let dm=", 1)[0]
    control = f"let boundary_error_s={boundary_error}\n{guard}"
    probe = Asset(asset("divider_dc.spice").content.replace(b"print ratio power",
                  control.encode() + b"print ratio power"), "spice")
    backend = NgspiceDocker(image=os.environ.get("ICLAYOUT_BENCH_TEST_IMAGE", "iclayout-bench-tools:local"))
    report = run_evaluation(parse_evaluation((FIXTURES / "divider.toml").read_bytes()),
                            {"input:dut": asset("divider.spice"), "input:dc": probe},
                            {"circuit.simulate": backend}, tmp_path / "window")
    assert report["outcome"] == expected
    if expected == "error":
        assert report["specs_pass"] is None
        assert report["jobs"]["operating_point"]["measurements"] == {}


def test_branch_resistors_preserve_picoampere_kcl(tmp_path):
    """A metal segment must not erase a high-impedance node's conductance.

    TSN RC diagnosis reduced the failure to this matrix stamp: adding 1e-12 S
    to 1/0.1895 S loses significant digits in ordinary resistor nodal equations.
    Independent oracle: KCL gives Vout=I*Rload, regardless of series Rmetal.
    This analytical control verifies numerical formulation, not circuit signoff.
    """
    backend = NgspiceDocker(
        image=os.environ.get("ICLAYOUT_BENCH_TEST_IMAGE", "iclayout-bench-tools:local"),
        resistor_formulation="branch")
    plan = parse_evaluation(b'''schema_version = 1
mode = "characterization"
[[jobs]]
id = "op"
stage = "simulate"
operation = "circuit.simulate"
inputs = {deck = "input:deck", dut = "input:dut"}
parameters = {measurements = {output_v = "V"}}
[[metrics]]
id = "output_v"
category = "performance"
observations = ["op:output_v"]
unit = "V"
direction = "maximize"
aggregation = "min"
''')
    dut = Asset(b'* Linear numerical control\nRmetal a b 0.1895\nRload b 0 1T\n', "spice")
    deck = Asset(b'''* Picoampere conservation control
.include dut.spice
.options gmin=1e-18 reltol=1e-7 abstol=1e-18 vntol=1e-10
IIN 0 a 1p
.control
set numdgt=15
op
let output_v=v(b)
print output_v
quit
.endc
.end
''', "spice")
    report = run_evaluation(plan, {"input:deck": deck, "input:dut": dut},
                            {"circuit.simulate": backend}, tmp_path / "branch")
    assert report["outcome"] == "passed", report["jobs"]
    measured = report["jobs"]["op"]["measurements"]["output_v"]["value"]
    assert measured == pytest.approx(1e-12 * 1e12, rel=1e-8, abs=0)

    assert report["jobs"]["op"]["inputs"]["dut"]["sha256"] == dut.sha256
    assert report["jobs"]["op"]["evidence"]["effective_dut"]["sha256"] != dut.sha256
    noisy = Asset(deck.content.replace(b"op\n", b"noise v(b) IIN dec 10 1 100\n"), "spice")
    rejected = run_evaluation(plan, {"input:deck": noisy, "input:dut": dut},
                              {"circuit.simulate": backend}, tmp_path / "noise")
    assert rejected["outcome"] == "error"
    assert "noise" in rejected["jobs"]["op"]["reason"]
