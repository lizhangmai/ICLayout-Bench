"""Qualification witness and post-layout sensitivity checks for the output stage."""

import copy
import json
import math
import os
import tomllib
from pathlib import Path

import pytest
from helpers.case_config import standalone_config
from helpers.scoring import (
    assert_characterization_unscored,
    assert_layout_score,
    assert_same_layout_score,
    unscore_characterization,
)
from helpers.spice_raw import output_rows

from benchmarking.evaluate import run_evaluation
from benchmarking.evaluation import parse_evaluation
from benchmarking.files import Asset, read_file
from benchmarking.prepare_support import prepare_support
from benchmarking.tasks import load_task
from benchmarking.toolchains import load_toolchain

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / "tasks/ihp-sg13g2/IHP-AnalogAcademy/cases/output_stage"
IMAGE = os.environ.get("LAYOUT_BENCH_TEST_IMAGE", "layout-bench-tools:local")


def declared_asset(config, role):
    entry = next(asset for asset in config["assets"] if asset["role"] == role)
    asset = Asset(read_file(CASE, entry["path"]), entry["format"])
    assert asset.sha256 == entry["sha256"], entry["path"]
    return asset


@pytest.fixture(scope="module")
def environment(tmp_path_factory):
    root = tmp_path_factory.mktemp("output-stage-support")
    config_text = (CASE / "case.toml").read_text()
    load_task(CASE / "case.toml").materialize(root / "case")
    for profile, name in (
        ("klayout", "klayout"),
        ("magic", "magic"),
        ("analog-models", "models"),
    ):
        support = root / name
        prepare_support(
            ROOT / "third_party/IHP-Open-PDK",
            f"{ROOT}/tasks/ihp-sg13g2/pdk.toml#{profile}",
            support,
        )
        config_text = config_text.replace(
            f"build/support/output-stage-{name}", str(support)
        )
    config_text = config_text.replace("layout-bench-tools:local", IMAGE)
    path = root / "case/case.toml"
    config_text = standalone_config(config_text)
    path.write_text(config_text)
    return path, load_task(path), load_toolchain(path), tomllib.loads(config_text)


def evaluate(candidate, environment, destination, backends=None):
    _, task, configured_backends, _ = environment
    return run_evaluation(
        task.evaluation,
        {"candidate": candidate, **task.evaluation_inputs()},
        configured_backends if backends is None else backends,
        destination,
        task_sha256=task.digest,
        task_witnessed=task.witnessed,
    )


def characterize_source(task, backends, values, destination, source=None):
    """Run one source-netlist point through the declared simulator backend."""
    data = copy.deepcopy(task.evaluation.description())
    job = next(job for job in data["jobs"] if job["id"] == "pre")
    job["parameters"]["values"].update(values)
    data.update(mode="characterization", jobs=[job], metrics=[])
    unscore_characterization(data)
    plan = parse_evaluation(json.dumps(data).encode(), file_format="json")
    inputs = task.evaluation_inputs()
    if source is not None:
        inputs["input:simulation"] = source
    report = run_evaluation(
        plan,
        inputs,
        backends,
        destination,
        task_sha256=task.digest,
        task_witnessed=task.witnessed,
    )
    assert_characterization_unscored(report)
    return report


def assert_same_decision(reference, candidate):
    assert candidate["outcome"] == reference["outcome"] == "passed"
    assert candidate["physical_valid"] is reference["physical_valid"] is True
    assert candidate["specs_pass"] is reference["specs_pass"] is True
    assert candidate["task_success"] is reference["task_success"] is True
    assert_layout_score(reference)
    assert_layout_score(candidate)
    assert_same_layout_score(reference, candidate)
    assert candidate["jobs"].keys() == reference["jobs"].keys()
    assert {name: job["status"] for name, job in candidate["jobs"].items()} == {
        name: job["status"] for name, job in reference["jobs"].items()
    }
    assert candidate["metrics"].keys() == reference["metrics"].keys()
    for name, metric in reference["metrics"].items():
        assert candidate["metrics"][name]["status"] == metric["status"] == "passed"
        assert candidate["metrics"][name]["value"] == pytest.approx(
            metric["value"], rel=1e-4, abs=1e-12
        )


def ideal_body_netlist(source):
    """Replace finite source taps with the ideal rail PEX boundary."""
    lines = []
    for raw in source.content.decode().splitlines():
        if raw.startswith("XR"):
            continue
        if raw.startswith("XM"):
            fields = raw.split()
            fields[4] = "vdd" if "pmos" in fields[5].lower() else "vss"
            raw = " ".join(fields)
        lines.append(raw)
    return Asset(("\n".join(lines) + "\n").encode(), "spice")


def at_frequency(rows, frequency):
    row = min(rows, key=lambda item: abs(item["frequency"].real - frequency))
    assert row["frequency"].real == pytest.approx(frequency, rel=1e-10)
    return row


def independent_output_checks(report, directory, job_name):
    ac = output_rows(report, directory, job_name, "ac")
    op = output_rows(report, directory, job_name, "op")[0]
    assert all(
        math.isfinite(value.real) and math.isfinite(value.imag)
        for row in ac
        for value in row.values()
    )
    one_megahertz = at_frequency(ac, 1e6)
    one_hundred_megahertz = at_frequency(ac, 1e8)

    def output_gain(row):
        return abs(-row["v(vout)"] / row["v(dn4)"])

    gain = {
        "output_gain": output_gain(one_megahertz),
        "output_gain_high": output_gain(one_hundred_megahertz),
    }
    assert all(math.isfinite(value) and value > 0 for value in gain.values())
    measurements = report["jobs"][job_name]["measurements"]
    for name, value in gain.items():
        assert measurements[name]["value"] == pytest.approx(value, rel=2e-5, abs=1e-8)

    operating = {
        "output_bias": op["v(vout)"],
        "supply_power": -op["v(vdd)"] * op["i(vdd)"],
    }
    for name, value in operating.items():
        assert math.isfinite(value)
        assert measurements[name]["value"] == pytest.approx(value, rel=2e-5, abs=1e-12)
    return gain, operating


@pytest.mark.acceptance_eda
def test_qualified_witness_passes_with_same_source_and_pex_conditions(
    environment, tmp_path
):
    _, task, _, config = environment
    reference = declared_asset(config, "physical-witness")
    report = evaluate(reference, environment, tmp_path / "witness")

    assert report["outcome"] == "passed"
    assert (
        report["physical_valid"]
        is report["specs_pass"]
        is report["task_success"]
        is True
    )
    assert_layout_score(report)
    assert all(job["status"] == "passed" for job in report["jobs"].values())
    pre = report["jobs"]["pre"]
    nominal = report["jobs"]["nominal"]
    parasitics = report["jobs"]["parasitics"]
    source = task.evaluation_inputs()["input:simulation"]
    scope = json.loads(task.evaluation_inputs()["input:pex_scope"].content)
    assert scope["body_and_tap_connection"].startswith("ideal")
    assert scope["included"] and scope["excluded"]
    assert scope["calibration"]["declared_metrics_unchanged"] is True
    assert scope["calibration"]["maximum_relative_difference"] > 0
    simulator_cards = source.content.decode().splitlines()
    for instance in ("XR4", "XR5"):
        card = next(line for line in simulator_cards if line.startswith(instance + " "))
        assert any(field.lower().startswith("r=") for field in card.split())

    # Both phases use the same deck and bias values.  Nominal consumes only the
    # RC netlist extracted from this exact physical witness.
    assert pre["inputs"]["deck"] == nominal["inputs"]["deck"]
    assert pre["parameters"] == nominal["parameters"]
    assert pre["inputs"]["dut"]["sha256"] == source.sha256
    assert (
        nominal["inputs"]["dut"]["sha256"] == parasitics["outputs"]["netlist"]["sha256"]
    )
    assert parasitics["outputs"]["netlist"]["sha256"] != source.sha256

    source_gain, source_operating = independent_output_checks(
        report, tmp_path / "witness", "pre"
    )
    pex_gain, pex_operating = independent_output_checks(
        report, tmp_path / "witness", "nominal"
    )
    assert source_operating["output_bias"] == pytest.approx(
        pex_operating["output_bias"], abs=5e-3
    )
    assert pex_gain["output_gain"] == pytest.approx(
        source_gain["output_gain"], rel=0.05
    )
    # The extracted capacitor and distributed wiring affect the high-frequency
    # response, proving that post-layout simulation is reaching the DUT.
    assert pex_gain["output_gain_high"] != pytest.approx(
        source_gain["output_gain_high"], rel=1e-2
    )
    assert pre["outputs"]["ac"]["sha256"] != nominal["outputs"]["ac"]["sha256"]


@pytest.mark.acceptance_eda
def test_finite_taps_are_negligible_at_the_declared_ideal_body_boundary(
    environment, tmp_path
):
    _, task, backends, _ = environment
    source = task.evaluation_inputs()["input:simulation"]
    finite = characterize_source(task, backends, {}, tmp_path / "finite-taps")
    ideal = characterize_source(
        task,
        backends,
        {},
        tmp_path / "ideal-bodies",
        ideal_body_netlist(source),
    )
    assert finite["outcome"] == ideal["outcome"] == "passed"
    assert finite["task_success"] is ideal["task_success"] is None
    scope = json.loads(task.evaluation_inputs()["input:pex_scope"].content)
    limit = scope["calibration"]["maximum_relative_difference"]
    finite_measurements = finite["jobs"]["pre"]["measurements"]
    ideal_measurements = ideal["jobs"]["pre"]["measurements"]
    for name, measurement in finite_measurements.items():
        denominator = max(abs(measurement["value"]), 1e-30)
        difference = abs(ideal_measurements[name]["value"] - measurement["value"])
        assert difference / denominator <= limit, (
            name,
            measurement,
            ideal_measurements[name],
        )


_MISSING_DN4 = b"""from klayout import db
layout = db.Layout()
layout.read("original.gds")
top = next(cell for cell in layout.top_cells() if cell.name == "output_stage")
removed = 0
for shape in list(top.shapes(layout.layer(10, 25)).each()):
    if shape.is_text() and shape.text.string == "dn4":
        shape.delete()
        removed += 1
assert removed == 1
layout.write("mutated.gds")
"""

_TRANSLATE = b"""from klayout import db
layout = db.Layout()
layout.read("original.gds")
top = next(cell for cell in layout.top_cells() if cell.name == "output_stage")
top.transform(db.Trans(500, 700))
layout.write("translated.gds")
"""


def translated_witness(backends, config):
    mutation = backends["layout.artifact"].tool.run(
        ["python", "translate.py"],
        {
            "translate.py": Asset(_TRANSLATE, "python"),
            "original.gds": declared_asset(config, "physical-witness"),
        },
        {"translated.gds": "gds"},
    )
    assert mutation.returncode == 0 and not mutation.reason, mutation.evidence
    return mutation.files["translated.gds"]


@pytest.mark.acceptance_eda
def test_repeat_translation_and_source_sensitivity_are_exercised(environment, tmp_path):
    case_path, task, backends, config = environment
    reference = declared_asset(config, "physical-witness")
    first = evaluate(reference, environment, tmp_path / "repeat-first")
    second = evaluate(
        reference,
        environment,
        tmp_path / "repeat-second",
        load_toolchain(case_path),
    )
    translated = evaluate(
        translated_witness(backends, config), environment, tmp_path / "translated"
    )
    assert_same_decision(first, second)
    assert_same_decision(first, translated)

    pre = next(
        job for job in task.evaluation.description()["jobs"] if job["id"] == "pre"
    )
    values = pre["parameters"]["values"]
    source = characterize_source(task, backends, {}, tmp_path / "sensitivity-base")
    loaded = characterize_source(
        task,
        backends,
        {"rload": values["rload"] * 2},
        tmp_path / "sensitivity-load",
    )
    biased = characterize_source(
        task,
        backends,
        {"gate_dc": values["gate_dc"] * 0.8},
        tmp_path / "sensitivity-bias",
    )
    assert all(report["outcome"] == "passed" for report in (source, loaded, biased))
    source_gain, source_operating = independent_output_checks(
        source, tmp_path / "sensitivity-base", "pre"
    )
    loaded_gain, loaded_operating = independent_output_checks(
        loaded, tmp_path / "sensitivity-load", "pre"
    )
    _, biased_operating = independent_output_checks(
        biased, tmp_path / "sensitivity-bias", "pre"
    )
    assert loaded_operating["output_bias"] != pytest.approx(
        source_operating["output_bias"], rel=1e-3
    )
    assert loaded_gain["output_gain"] != pytest.approx(
        source_gain["output_gain"], rel=1e-3
    )
    assert biased_operating["output_bias"] != pytest.approx(
        source_operating["output_bias"], rel=1e-3
    )


@pytest.mark.acceptance_eda
def test_missing_dn4_port_cannot_qualify(environment, tmp_path):
    _, _task, backends, config = environment
    mutation = backends["layout.artifact"].tool.run(
        ["python", "remove_dn4.py"],
        {
            "remove_dn4.py": Asset(_MISSING_DN4, "python"),
            "original.gds": declared_asset(config, "physical-witness"),
        },
        {"mutated.gds": "gds"},
    )
    assert mutation.returncode == 0 and not mutation.reason, mutation.evidence
    report = evaluate(
        mutation.files["mutated.gds"], environment, tmp_path / "missing-dn4"
    )

    assert report["outcome"] == "failed"
    assert report["physical_valid"] is report["task_success"] is False
    assert report["jobs"]["lvs"]["status"] == "failed"
    assert report["jobs"]["parasitics"]["status"] == "blocked"
    assert report["jobs"]["nominal"]["status"] == "blocked"
    assert_layout_score(report)
    assert report["score"]["value"] == 0
