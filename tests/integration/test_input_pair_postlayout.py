"""Qualification witness and post-layout sensitivity checks for the input pair."""

import copy
import json
import math
import os
import tomllib
from pathlib import Path

import pytest
from helpers.case_config import calibration_limits, standalone_config
from helpers.scoring import (
    assert_characterization_unscored,
    assert_layout_score,
    assert_same_layout_score,
    unscore_characterization,
)
from helpers.spice_raw import output_rows

from benchmarking.engine.evaluate import run_evaluation
from benchmarking.engine.prepare_support import prepare_support
from benchmarking.engine.toolchains import load_toolchain
from benchmarking.evaluation import parse_evaluation
from benchmarking.files import Asset, read_file
from benchmarking.tasks import load_task

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
PUBLIC_ROOT = ROOT
CASE = PUBLIC_ROOT / "tasks/ihp-sg13g2/IHP-AnalogAcademy/cases/input_pair"
IMAGE = os.environ.get("ICLAYOUT_BENCH_TEST_IMAGE", "iclayout-bench-tools:local")


def declared_asset(config, role):
    entry = next(asset for asset in config["assets"] if asset["role"] == role)
    asset = Asset(read_file(CASE, entry["path"]), entry["format"])
    assert asset.sha256 == entry["sha256"], entry["path"]
    return asset


@pytest.fixture(scope="module")
def environment(tmp_path_factory):
    root = tmp_path_factory.mktemp("input-pair-support")
    config_text = (CASE / "case.toml").read_text()
    load_task(CASE / "case.toml").materialize(root / "case")
    for profile, name in (
        ("klayout", "klayout"),
        ("magic", "magic"),
        ("analog-models", "models"),
    ):
        support = root / name
        prepare_support(
            None,
            f"{PUBLIC_ROOT}/tasks/ihp-sg13g2/pdk.toml#{profile}",
            support,
        )
        config_text = config_text.replace(
            f"build/support/input-pair-{name}", str(support)
        )
    config_text = config_text.replace("iclayout-bench-tools:local", IMAGE)
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
    """Replace the finite source tap with the ideal rail PEX boundary."""
    lines = []
    for raw in source.content.decode().splitlines():
        if raw.startswith("XR"):
            continue
        if raw.startswith("XM"):
            fields = raw.split()
            fields[4] = "vdd"
            raw = " ".join(fields)
        lines.append(raw)
    return Asset(("\n".join(lines) + "\n").encode(), "spice")


def at_frequency(rows, frequency):
    row = min(rows, key=lambda item: abs(item["frequency"].real - frequency))
    assert row["frequency"].real == pytest.approx(frequency, rel=1e-10)
    return row


def independent_input_checks(report, directory, job_name):
    ac = output_rows(report, directory, job_name, "ac")
    op = output_rows(report, directory, job_name, "op")[0]
    assert all(
        math.isfinite(value.real) and math.isfinite(value.imag)
        for row in ac
        for value in row.values()
    )
    one_megahertz = at_frequency(ac, 1e6)
    one_hundred_megahertz = at_frequency(ac, 1e8)

    def differential_gain(row):
        return abs((row["v(dn3)"] - row["v(dn4)"]) / (row["v(vp)"] - row["v(vm)"]))

    gain = {
        "differential_gain": differential_gain(one_megahertz),
        "differential_gain_high": differential_gain(one_hundred_megahertz),
    }
    assert all(math.isfinite(value) and value > 0 for value in gain.values())
    measurements = report["jobs"][job_name]["measurements"]
    for name, value in gain.items():
        assert measurements[name]["value"] == pytest.approx(value, rel=2e-5, abs=1e-8)

    operating = {
        "tail_voltage": op["v(tail)"],
        "common_drain": (op["v(dn3)"] + op["v(dn4)"]) / 2,
        "drain_balance": op["v(dn3)"] - op["v(dn4)"],
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

    # Source and PEX are calibrated by the same declared deck and values.  The
    # only DUT change is the RC netlist extracted from this candidate GDS.
    assert pre["inputs"]["deck"] == nominal["inputs"]["deck"]
    assert pre["parameters"] == nominal["parameters"]
    assert pre["inputs"]["dut"]["sha256"] == source.sha256
    assert (
        nominal["inputs"]["dut"]["sha256"] == parasitics["outputs"]["netlist"]["sha256"]
    )
    assert parasitics["outputs"]["netlist"]["sha256"] != source.sha256

    source_gain, source_operating = independent_input_checks(
        report, tmp_path / "witness", "pre"
    )
    pex_gain, pex_operating = independent_input_checks(
        report, tmp_path / "witness", "nominal"
    )
    assert source_operating["tail_voltage"] == pytest.approx(
        pex_operating["tail_voltage"], abs=5e-3
    )
    assert source_operating["common_drain"] == pytest.approx(
        pex_operating["common_drain"], abs=5e-3
    )
    assert pex_gain["differential_gain"] == pytest.approx(
        source_gain["differential_gain"], rel=0.03
    )
    # Distributed RC must reach the high-frequency behavior, rather than being
    # silently discarded before the nominal simulation.
    assert pex_gain["differential_gain_high"] != pytest.approx(
        source_gain["differential_gain_high"], rel=1e-2
    )
    assert (
        report["jobs"]["pre"]["outputs"]["ac"]["sha256"]
        != report["jobs"]["nominal"]["outputs"]["ac"]["sha256"]
    )


@pytest.mark.acceptance_eda
def test_finite_tap_is_negligible_at_the_declared_ideal_body_boundary(
    environment, tmp_path
):
    _, task, backends, _ = environment
    source = task.evaluation_inputs()["input:simulation"]
    finite = characterize_source(task, backends, {}, tmp_path / "finite-tap")
    ideal = characterize_source(
        task,
        backends,
        {},
        tmp_path / "ideal-body",
        ideal_body_netlist(source),
    )
    assert finite["outcome"] == ideal["outcome"] == "passed"
    assert finite["task_success"] is ideal["task_success"] is None
    limit = calibration_limits(CASE)["relative"]
    finite_measurements = finite["jobs"]["pre"]["measurements"]
    ideal_measurements = ideal["jobs"]["pre"]["measurements"]
    for name, measurement in finite_measurements.items():
        denominator = max(
            abs(measurement["value"]), abs(ideal_measurements[name]["value"]), 1e-9
        )
        difference = abs(ideal_measurements[name]["value"] - measurement["value"])
        assert difference / denominator <= limit, (
            name,
            measurement,
            ideal_measurements[name],
        )


_MISSING_TAIL = b"""from klayout import db
layout = db.Layout()
layout.read("original.gds")
top = layout.top_cell()
removed = 0
for shape in list(top.shapes(layout.layer(8, 25)).each()):
    if shape.is_text() and shape.text.string == "tail":
        shape.delete()
        removed += 1
assert removed == 1
layout.write("mutated.gds")
"""

_TRANSLATE = b"""from klayout import db
layout = db.Layout()
layout.read("original.gds")
top = next(cell for cell in layout.top_cells() if cell.name == "input_common_centroid")
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
        {"drain_load": values["drain_load"] * 2},
        tmp_path / "sensitivity-load",
    )
    biased = characterize_source(
        task,
        backends,
        {"tail_current": values["tail_current"] * 0.75},
        tmp_path / "sensitivity-bias",
    )
    assert all(report["outcome"] == "passed" for report in (source, loaded, biased))
    source_gain, source_operating = independent_input_checks(
        source, tmp_path / "sensitivity-base", "pre"
    )
    loaded_gain, loaded_operating = independent_input_checks(
        loaded, tmp_path / "sensitivity-load", "pre"
    )
    _, biased_operating = independent_input_checks(
        biased, tmp_path / "sensitivity-bias", "pre"
    )
    assert loaded_operating["common_drain"] != pytest.approx(
        source_operating["common_drain"], rel=1e-3
    )
    assert loaded_gain["differential_gain"] != pytest.approx(
        source_gain["differential_gain"], rel=1e-3
    )
    assert biased_operating["tail_voltage"] != pytest.approx(
        source_operating["tail_voltage"], rel=1e-3
    )


@pytest.mark.acceptance_eda
def test_missing_tail_port_cannot_qualify(environment, tmp_path):
    _, _task, backends, config = environment
    mutation = backends["layout.artifact"].tool.run(
        ["python", "remove_tail.py"],
        {
            "remove_tail.py": Asset(_MISSING_TAIL, "python"),
            "original.gds": declared_asset(config, "physical-witness"),
        },
        {"mutated.gds": "gds"},
    )
    assert mutation.returncode == 0 and not mutation.reason, mutation.evidence
    report = evaluate(
        mutation.files["mutated.gds"], environment, tmp_path / "missing-tail"
    )

    assert report["outcome"] == "failed"
    assert report["physical_valid"] is report["task_success"] is False
    assert report["jobs"]["lvs"]["status"] == "failed"
    assert report["jobs"]["parasitics"]["status"] == "blocked"
    assert report["jobs"]["nominal"]["status"] == "blocked"
    assert_layout_score(report)
    assert report["score"]["value"] == 0
