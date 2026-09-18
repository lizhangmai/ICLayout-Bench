"""Functional and physical contract for the maintained 160-derived LNA."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

import pytest
from helpers.case_config import calibration_limits, standalone_config
from helpers.scoring import (
    assert_characterization_unscored,
    assert_layout_score,
    unscore_characterization,
)
from helpers.spice_raw import output_rows
from helpers.stimuli import assert_ac_stimuli, command, number
from helpers.stimuli import testbench as declared_testbench

from benchmarking.engine.evaluate import run_evaluation
from benchmarking.engine.hbt import convert_klayout_netlist
from benchmarking.engine.prepare_support import prepare_support
from benchmarking.engine.toolchains import load_toolchain
from benchmarking.evaluation import parse_evaluation
from benchmarking.files import Asset
from benchmarking.tasks import load_task

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
PUBLIC_ROOT = ROOT
CASE = PUBLIC_ROOT / "tasks/ihp-sg13g2/TO_Apr2025/cases/160GHz_LNA"
TOP = "LNA160_FOUR_STAGE"
PORTS = ["IN", "OUT", "VDD", "VSS", "VBIAS"]


@pytest.fixture(scope="module")
def environment(tmp_path_factory):
    root = tmp_path_factory.mktemp("lna160-functional")
    task = load_task(CASE / "case.toml")
    task.materialize(root / "case")
    config = (CASE / "case.toml").read_text()
    image = os.environ.get("ICLAYOUT_BENCH_TEST_IMAGE", "iclayout-bench-tools:local")
    for profile, name in [("klayout", "klayout"), ("magic", "magic"),
                          ("hbt-models", "hbt-models")]:
        prepare_support(None,
                        f"{PUBLIC_ROOT}/tasks/ihp-sg13g2/pdk.toml#{profile}",
                        root / name, compiler_image=image)
        config = config.replace(f"build/support/lna160-{name}", str(root / name))
    path = root / "case/case.toml"
    config = standalone_config(config)
    path.write_text(config)
    return load_task(path), load_toolchain(path), root


def declared_witness() -> Asset:
    return Asset((CASE / "reference/LNA160_FOUR_STAGE.gds").read_bytes(), "gds")


def characterization_plan(task):
    source = task.evaluation.description()
    jobs = [dict(job) for job in source["jobs"] if job["stage"] == "simulate"]
    for job in jobs:
        job["inputs"]["circuit"] = "input:simulation"
    source.update(
        mode="characterization",
        jobs=jobs,
        metrics=[metric for metric in source["metrics"] if metric["category"] == "performance"],
    )
    unscore_characterization(source)
    return parse_evaluation(json.dumps(source).encode(), file_format="json")


def ideal_body_netlist(source: Asset) -> Asset:
    """Build the diagnostic ideal-body variant without changing the source asset."""
    lines = [line for line in source.content.decode().splitlines()
             if not line.startswith("XRSUB ")]
    return Asset(("\n".join(line.replace("SUBSTRATE", "VSS") for line in lines)
                  + "\n").encode(), "spice")


def check_measurements(report, directory, task):
    job = report["jobs"]["nominal"]
    assert job["status"] == "passed", job
    op = output_rows(report, directory, "nominal", "op")[0]
    deck = declared_testbench(task, "nominal")
    ac = output_rows(report, directory, "nominal", "ac")
    assert_ac_stimuli(deck, job["parameters"].get("values", {}), op, ac)

    gain = [row["v(out)"] / row["v(in)"] for row in ac]
    assert abs(gain[0]) > 1
    measurement = command(deck, "meas")
    frequency = number(next(token.split("=", 1)[1] for token in measurement if token.lower().startswith("at=")))
    gain_index = min(range(len(ac)), key=lambda index: abs(ac[index]["frequency"].real - frequency))
    expected = {
        "vin_bias": op["v(in)"],
        "out_bias": op["v(out)"],
        "i_vdd": -op["i(vdd)"],
        "i_vbias": -op["i(vbias)"],
        "gain_db": 20 * math.log10(abs(gain[gain_index])),
    }
    # Compare the deck's .meas point with the nearest raw AC sample at 100 MHz.
    for measurement, value in expected.items():
        assert job["measurements"][measurement]["value"] == pytest.approx(
            value, rel=1e-5, abs=1e-9
        )
    assert expected["i_vdd"] > 0
    assert math.isfinite(expected["i_vbias"])


@pytest.mark.acceptance_eda
def test_case_owned_witness_pre_post_function_and_calibration(environment, tmp_path):
    task, backends, _ = environment
    witness = declared_witness()
    pre = run_evaluation(
        characterization_plan(task),
        task.evaluation_inputs(),
        backends,
        tmp_path / "pre",
        task_sha256=task.digest,
    )
    assert pre["outcome"] == "passed", pre["jobs"]
    assert_characterization_unscored(pre)
    check_measurements(pre, tmp_path / "pre", task)

    post = run_evaluation(
        task.evaluation,
        {"candidate": witness, **task.evaluation_inputs()},
        backends,
        tmp_path / "post",
        task_sha256=task.digest,
        task_witnessed=task.witnessed,
    )
    if task.status != "qualified":
        # Keep this acceptance witness useful while the shared HBT merger is
        # being repaired: the physical gates are already required to pass.
        assert post["jobs"]["artifact"]["status"] == "passed"
        assert post["jobs"]["drc"]["status"] == "passed"
        assert post["jobs"]["lvs"]["status"] == "passed"
        assert post["jobs"]["parasitics"]["status"] in {"error", "failed"}
        assert post["task_success"] is not True
        return

    assert task.witnessed is True
    assert post["outcome"] == "passed", post["jobs"]
    assert post["physical_valid"] is True
    assert post["specs_pass"] is True
    assert post["task_success"] is True
    assert_layout_score(post)
    pex = post["jobs"]["parasitics"]
    assert pex["inputs"]["layout"]["sha256"] == witness.sha256
    assert pex["outputs"]["netlist"]["format"] == "spice"
    assert post["jobs"]["nominal"]["inputs"]["circuit"]["sha256"] == \
        pex["outputs"]["netlist"]["sha256"]
    assert pre["jobs"]["nominal"]["parameters"] == post["jobs"]["nominal"]["parameters"]
    assert pre["jobs"]["nominal"]["inputs"]["deck"] == post["jobs"]["nominal"]["inputs"]["deck"]
    assert pre["backends"]["circuit.simulate"] == post["backends"]["circuit.simulate"]
    check_measurements(post, tmp_path / "post", task)

    # Independently exercise the compact KLayout interpretation.  This guards
    # Nx and HBT terminal identity even if a distributed RC card changes.
    native_asset = pex["evidence"]["klayout_native_netlist"]
    native_raw = (tmp_path / "post" / native_asset["path"]).read_bytes()
    native_circuit = Asset(convert_klayout_netlist(native_raw, PORTS).encode(), "spice")
    native = run_evaluation(
        characterization_plan(task),
        {**task.evaluation_inputs(), "input:simulation": native_circuit},
        backends,
        tmp_path / "native",
        task_sha256=task.digest,
    )
    assert native["outcome"] == "passed", native["jobs"]
    assert_characterization_unscored(native)
    check_measurements(native, tmp_path / "native", task)


@pytest.mark.acceptance_eda
def test_source_finite_and_ideal_body_nominal_calibration(environment, tmp_path):
    task, backends, _ = environment
    inputs = task.evaluation_inputs()
    plan = characterization_plan(task)
    finite = run_evaluation(
        plan,
        inputs,
        backends,
        tmp_path / "finite-body",
        task_sha256=task.digest,
    )
    ideal = run_evaluation(
        plan,
        {**inputs, "input:simulation": ideal_body_netlist(inputs["input:simulation"])},
        backends,
        tmp_path / "ideal-body",
        task_sha256=task.digest,
    )
    assert finite["outcome"] == "passed", finite["jobs"]
    assert ideal["outcome"] == "passed", ideal["jobs"]
    check_measurements(finite, tmp_path / "finite-body", task)
    check_measurements(ideal, tmp_path / "ideal-body", task)

    names = ("vin_bias", "out_bias", "i_vdd", "i_vbias", "gain_db")
    finite_values = {
        name: finite["jobs"]["nominal"]["measurements"][name]["value"]
        for name in names
    }
    ideal_values = {
        name: ideal["jobs"]["nominal"]["measurements"][name]["value"]
        for name in names
    }
    tolerances = calibration_limits(CASE)
    for name, tolerance in tolerances.items():
        assert ideal_values[name] == pytest.approx(
            finite_values[name], abs=tolerance, rel=0
        )


def mutate_witness(backends, operation):
    script = Asset((
        "from klayout import db\n"
        "layout = db.Layout()\n"
        "layout.read('witness.gds')\n"
        "top = layout.top_cell()\n"
        + operation
        + "\nlayout.write('mutated.gds')\n"
    ).encode(), "python")
    result = backends["layout.artifact"].tool.run(
        ["python", "mutate.py"],
        {"mutate.py": script, "witness.gds": declared_witness()},
        {"mutated.gds": "gds"},
    )
    assert result.returncode == 0 and not result.reason, result.evidence
    return result.files["mutated.gds"]


@pytest.mark.acceptance_eda
def test_swapped_supply_labels_fail_strict_lvs_before_pex(environment, tmp_path):
    task, backends, _ = environment
    candidate = mutate_witness(backends, """
changed = 0
for cell in layout.each_cell():
    for layer in layout.layer_indexes():
        for shape in cell.shapes(layer).each():
            if shape.is_text() and shape.text.string in ('VDD', 'VSS'):
                label = shape.text
                label.string = {'VDD': 'VSS', 'VSS': 'VDD'}[label.string]
                shape.text = label
                changed += 1
assert changed == 2
""")
    report = run_evaluation(
        task.evaluation,
        {"candidate": candidate, **task.evaluation_inputs()},
        backends,
        tmp_path / "swapped-supplies",
        task_sha256=task.digest,
        task_witnessed=task.witnessed,
    )
    assert report["jobs"]["artifact"]["status"] == "passed"
    assert report["jobs"]["drc"]["status"] == "passed"
    assert report["jobs"]["lvs"]["status"] == "failed"
    assert report["jobs"]["parasitics"]["status"] == "blocked"
    assert report["task_success"] is False
    assert_layout_score(report)
    assert report["score"]["value"] == 0




@pytest.mark.acceptance_eda
def test_repeated_grid_translation_preserves_qualified_decisions(environment, tmp_path):
    task, backends, _ = environment
    original = declared_witness()
    translated = mutate_witness(
        backends,
        "top.transform(db.Trans(round(13 / layout.dbu), round(17 / layout.dbu)))\n",
    )
    reports = []
    for index, candidate in enumerate((original, original, translated)):
        directory = tmp_path / f"repeat-{index}"
        report = run_evaluation(
            task.evaluation,
            {"candidate": candidate, **task.evaluation_inputs()},
            backends,
            directory,
            task_sha256=task.digest,
            task_witnessed=task.witnessed,
        )
        assert report["outcome"] == "passed", report["jobs"]
        assert report["physical_valid"] is True
        assert report["specs_pass"] is True
        assert report["task_success"] is True
        assert_layout_score(report)
        check_measurements(report, directory, task)

        pex = report["jobs"]["parasitics"]
        assert pex["status"] == "passed"
        assert pex["inputs"]["layout"]["sha256"] == candidate.sha256
        mapping = json.loads((directory / pex["evidence"]["mapping"]["path"]).read_text())
        assert mapping["ports"] == PORTS
        assert mapping["synthetic_hbt_ties"] == []
        assert mapping["isolated_hbt_port_repairs"] == []
        reports.append(report)

    baseline = reports[0]
    for report in reports[1:]:
        for name, metric in baseline["metrics"].items():
            assert report["metrics"][name]["status"] == "passed"
            assert report["metrics"][name]["value"] == pytest.approx(
                metric["value"], rel=1e-3, abs=1e-9
            )
        for name, measurement in baseline["jobs"]["nominal"]["measurements"].items():
            assert report["jobs"]["nominal"]["measurements"][name]["value"] == pytest.approx(
                measurement["value"], rel=1e-3, abs=1e-9
            )


def test_simulator_bulk_is_an_ordinary_substrate_node():
    simulation = (CASE / "materials/circuit.spice").read_text()
    assert "SUBSTRATE" in simulation
    assert " gnd " not in f" {simulation} "
    taps = [line for line in simulation.splitlines() if not line.lstrip().startswith('*') and ' ptap1 ' in line]
    assert taps
    for card in taps:
        resistance = number(next(token.split('=', 1)[1] for token in card.split() if token.lower().startswith('r=')))
        assert math.isfinite(resistance) and resistance > 0
