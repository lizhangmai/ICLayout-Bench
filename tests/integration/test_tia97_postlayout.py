"""Functional and physical contract for the maintained 97-derived TIA."""

from __future__ import annotations

import json
import math
import os
import tomllib
from itertools import pairwise
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
from helpers.stimuli import assert_ac_stimuli, command, number
from helpers.stimuli import testbench as declared_testbench

from benchmarking.evaluation import parse_evaluation
from benchmarking.files import Asset
from benchmarking.tasks import load_task
from layout_eval.evaluate import run_evaluation
from layout_eval.hbt import convert_klayout_netlist
from layout_eval.prepare_support import prepare_support
from layout_eval.toolchains import load_toolchain

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
PUBLIC_ROOT = ROOT
CASE = PUBLIC_ROOT / "tasks/ihp-sg13g2/TO_Apr2025/cases/97_GHZ_LINEAR_TIA"
TOP = "FMD_QNC_01_LIN_TIA"
PORTS = ["RFIN", "RFOUT", "VCC1", "VCC2", "VCC3", "VSS"]


@pytest.fixture(scope="module")
def environment(tmp_path_factory):
    root = tmp_path_factory.mktemp("tia97-functional")
    task = load_task(CASE / "case.toml")
    task.materialize(root / "case")
    config = (CASE / "case.toml").read_text()
    image = os.environ.get("ICLAYOUT_BENCH_TEST_IMAGE", "iclayout-bench-tools:local")
    for profile, name in [("klayout", "klayout"), ("magic", "magic"),
                          ("hbt-models", "hbt-models")]:
        prepare_support(PUBLIC_ROOT / "third_party/IHP-Open-PDK",
                        f"{PUBLIC_ROOT}/tasks/ihp-sg13g2/pdk.toml#{profile}",
                        root / name, compiler_image=image)
        config = config.replace(f"build/support/tia97-{name}", str(root / name))
    path = root / "case/case.toml"
    config = standalone_config(config)
    path.write_text(config)
    return load_task(path), load_toolchain(path), root


def declared_witness():
    config = tomllib.loads((CASE / "case.toml").read_text())
    entry = next(asset for asset in config["assets"]
                 if asset["role"] == "physical-witness")
    witness = Asset((CASE / entry["path"]).read_bytes(), entry["format"])
    assert witness.sha256 == entry["sha256"]
    return witness


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


def characterization_plan(task):
    jobs = [job for job in task.evaluation.description()["jobs"]
            if job["stage"] == "simulate"]
    for job in jobs:
        job["inputs"]["circuit"] = "input:simulation"
    source = task.evaluation.description()
    source.update(
        mode="characterization",
        jobs=jobs,
        metrics=[metric for metric in source["metrics"]
                 if metric["category"] == "performance"],
    )
    unscore_characterization(source)
    return parse_evaluation(json.dumps(source).encode(), file_format="json")


def ideal_body_netlist(source):
    """Replace only the finite physical tap with the ideal-body boundary."""
    lines = []
    for raw in source.content.decode().splitlines():
        if raw.startswith("XRSUB "):
            fields = raw.split()
            fields[-1] = "R=1e-6"
            raw = " ".join(fields)
        lines.append(raw)
    return Asset(("\n".join(lines) + "\n").encode(), "spice")


def check_dc_linearity(report, directory, task):
    metric = next(metric for metric in task.evaluation.metrics
                  if metric.id == "linearity_error_pct")
    assert metric.unit == "percent"
    limit = metric.upper
    for specification in task.evaluation.jobs:
        if specification.stage != "simulate":
            continue
        rows = output_rows(report, directory, specification.id, "dc")
        sweep = command(declared_testbench(task, specification.id), "dc")
        lower, upper, step = map(number, sweep[-3:])
        expected_points = round((upper - lower) / step) + 1
        assert len(rows) == expected_points
        currents = [float(row["i(vsense)"].real) for row in rows]
        outputs = [float(row["v(rfout)"].real) for row in rows]
        assert currents[0] == pytest.approx(lower, abs=1e-12)
        assert currents[-1] == pytest.approx(upper, abs=1e-12)
        assert all(right > left for left, right in pairwise(currents))
        assert all(math.isfinite(value) for value in currents + outputs)
        span = outputs[-1] - outputs[0]
        assert math.isfinite(span) and abs(span) > 0
        errors = []
        for current, output in zip(currents, outputs):
            fraction = (current - currents[0]) / (currents[-1] - currents[0])
            ideal = outputs[0] + fraction * span
            errors.append(abs(output - ideal))
        normalized = 100 * max(errors) / abs(span)
        reported = report["jobs"][specification.id]["measurements"][metric.id]["value"]
        assert reported == pytest.approx(normalized, rel=1e-5, abs=1e-6)
        assert normalized <= limit, (specification.id, normalized, limit)


def check_measurements(report, directory, task):
    operating_points = []
    for specification in task.evaluation.jobs:
        if specification.stage != "simulate":
            continue
        name = specification.id
        job = report["jobs"][name]
        assert job["status"] == "passed", job
        op = output_rows(report, directory, name, "op")[0]
        deck = declared_testbench(task, name)
        ac = output_rows(report, directory, name, "ac")
        assert_ac_stimuli(deck, specification.parameters.get("values", {}), op, ac)

        current = specification.parameters["values"]["input_current"]
        assert op["i(vsense)"] == pytest.approx(current, abs=1e-12)
        source = command(deck, "IIN")
        ac_amplitude = number(source[source.index("AC") + 1])
        assert all(row["i(vsense)"].real == pytest.approx(ac_amplitude, abs=1e-8)
                   and abs(row["i(vsense)"].imag) < 1e-8 for row in ac)

        transfer = [row["v(rfout)"] / row["i(vsense)"] for row in ac]
        assert transfer[0].real > 0
        assert transfer[-1].real > 0
        expected = {
            "input_bias": op["v(rfin)"],
            "output_bias": op["v(rfout)"],
            "supply_power": sum(-op[f"v(vcc{index})"] * op[f"i(vcc{index})"]
                                 for index in (1, 2, 3)),
            "supply1_current": -op["i(vcc1)"],
            "supply2_current": -op["i(vcc2)"],
            "supply3_current": -op["i(vcc3)"],
            "transimpedance_low": transfer[0].real,
            "transimpedance_high": abs(transfer[-1]),
        }
        for measurement, value in expected.items():
            assert job["measurements"][measurement]["value"] == pytest.approx(
                value, rel=1e-6, abs=1e-10)
        for measurement in ("input_bias", "output_bias", "supply_power"):
            assert math.isfinite(job["measurements"][measurement]["value"])
        assert all(expected[f"supply{index}_current"] > 0
                   for index in (1, 2, 3))
        operating_points.append((current, expected["output_bias"]))

    assert len(operating_points) >= 2
    operating_points.sort()
    assert all(a[1] < b[1] for a, b in pairwise(operating_points))
    check_dc_linearity(report, directory, task)


@pytest.mark.acceptance_eda
def test_case_owned_witness_pre_post_function_and_calibration(environment, tmp_path):
    """Run the case-owned witness through the complete qualification contract."""
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
    assert task.witnessed is True
    assert post["outcome"] == "passed", post["jobs"]
    assert post["physical_valid"] is True
    assert post["specs_pass"] is True
    assert post["task_success"] is True
    assert_layout_score(post)
    pex = post["jobs"]["parasitics"]
    simulations = [job for job in task.evaluation.description()["jobs"]
                   if job["stage"] == "simulate"]
    for job in simulations:
        assert post["jobs"][job["id"]]["inputs"]["circuit"]["sha256"] == \
            pex["outputs"]["netlist"]["sha256"]
    for job in simulations:
        before, after = pre["jobs"][job["id"]], post["jobs"][job["id"]]
        assert before["inputs"]["deck"] == after["inputs"]["deck"]
        assert before["parameters"] == after["parameters"]
    assert pre["backends"]["circuit.simulate"] == post["backends"]["circuit.simulate"]
    check_measurements(post, tmp_path / "post", task)

    # A compact-device output is only useful when its HBT geometry and Nx are
    # still the native KLayout interpretation.
    native_asset = pex["evidence"]["klayout_native_netlist"]
    native_raw = (tmp_path / "post" / native_asset["path"]).read_bytes()
    native_circuit = Asset(convert_klayout_netlist(native_raw, PORTS).encode(), "spice")
    native_plan = characterization_plan(task)
    native = run_evaluation(
        native_plan,
        {**task.evaluation_inputs(), "input:simulation": native_circuit},
        backends,
        tmp_path / "native",
        task_sha256=task.digest,
    )
    assert native["outcome"] == "passed", native["jobs"]
    assert_characterization_unscored(native)
    check_measurements(native, tmp_path / "native", task)


@pytest.mark.acceptance_eda
def test_finite_substrate_tap_calibration(environment, tmp_path):
    task, backends, _ = environment
    source = task.evaluation_inputs()["input:simulation"]
    finite = run_evaluation(
        characterization_plan(task),
        task.evaluation_inputs(),
        backends,
        tmp_path / "finite-tap",
        task_sha256=task.digest,
    )
    ideal_inputs = task.evaluation_inputs()
    ideal_inputs["input:simulation"] = ideal_body_netlist(source)
    ideal = run_evaluation(
        characterization_plan(task),
        ideal_inputs,
        backends,
        tmp_path / "ideal-body",
        task_sha256=task.digest,
    )
    assert finite["outcome"] == ideal["outcome"] == "passed"
    assert_characterization_unscored(finite)
    assert_characterization_unscored(ideal)
    limit = calibration_limits(CASE)["relative"]
    for specification in task.evaluation.jobs:
        if specification.stage != "simulate":
            continue
        finite_measurements = finite["jobs"][specification.id]["measurements"]
        ideal_measurements = ideal["jobs"][specification.id]["measurements"]
        assert finite_measurements.keys() == ideal_measurements.keys()
        for name, measurement in finite_measurements.items():
            denominator = max(abs(measurement["value"]), 1e-30)
            difference = abs(ideal_measurements[name]["value"] - measurement["value"])
            assert difference / denominator <= limit, (name, measurement, ideal_measurements[name])


@pytest.mark.acceptance_eda
def test_rejects_missing_input_label(environment, tmp_path):
    task, backends, _ = environment
    candidate = mutate_witness(backends, """
removed = 0
for cell in layout.each_cell():
    for layer in layout.layer_indexes():
        for shape in list(cell.shapes(layer).each()):
            if shape.is_text() and shape.text.string.upper() == 'RFIN':
                shape.delete()
                removed += 1
assert removed > 0
""")
    report = run_evaluation(
        task.evaluation,
        {"candidate": candidate, **task.evaluation_inputs()},
        backends,
        tmp_path / "missing-input",
        task_sha256=task.digest,
        task_witnessed=task.witnessed,
    )
    assert report["jobs"]["artifact"]["status"] == "passed"
    assert report["jobs"]["drc"]["status"] == "passed"
    assert report["task_success"] is not True
    assert report["jobs"]["parasitics"]["status"] in {"blocked", "error", "failed"}
    assert_layout_score(report)
    assert report["score"]["value"] == 0


@pytest.mark.acceptance_eda
def test_swapped_equal_voltage_supply_labels_fail_strict_lvs(environment, tmp_path):
    task, backends, _ = environment
    candidate = mutate_witness(backends, """
changed = 0
for cell in layout.each_cell():
    for layer in layout.layer_indexes():
        for shape in cell.shapes(layer).each():
            if shape.is_text() and shape.text.string in ('VCC2', 'VCC3'):
                label = shape.text
                label.string = {'VCC2': 'VCC3', 'VCC3': 'VCC2'}[label.string]
                shape.text = label
                changed += 1
assert changed >= 2
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


def test_rejects_rotated_witness_before_extraction(environment, tmp_path):
    task, backends, _ = environment
    script = Asset(b"""from klayout import db
layout = db.Layout()
layout.read('witness.gds')
layout.top_cell().transform(db.Trans(db.Trans.R90))
layout.write('rotated.gds')
""", "python")
    result = backends["layout.artifact"].tool.run(
        ["python", "rotate.py"],
        {"rotate.py": script, "witness.gds": declared_witness()},
        {"rotated.gds": "gds"},
    )
    assert result.returncode == 0 and not result.reason, result.evidence
    report = run_evaluation(
        task.evaluation,
        {"candidate": result.files["rotated.gds"], **task.evaluation_inputs()},
        backends,
        tmp_path / "rotated",
        task_sha256=task.digest,
        task_witnessed=task.witnessed,
    )
    assert report["jobs"]["artifact"]["status"] == "passed"
    assert report["jobs"]["lvs"]["status"] == "failed"
    assert report["jobs"]["parasitics"]["status"] == "blocked"
    assert report["task_success"] is False


@pytest.mark.acceptance_eda
def test_repeated_translation_preserves_qualified_decisions(environment, tmp_path):
    task, backends, _ = environment
    assert task.witnessed is True
    translated = mutate_witness(
        backends,
        "top.transform(db.Trans(round(13 / layout.dbu), round(17 / layout.dbu)))\n",
    )
    reports = []
    for index, candidate in enumerate((declared_witness(), declared_witness(), translated)):
        report = run_evaluation(
            task.evaluation,
            {"candidate": candidate, **task.evaluation_inputs()},
            backends,
            tmp_path / f"repeat-{index}",
            task_sha256=task.digest,
            task_witnessed=task.witnessed,
        )
        assert report["task_success"] is True, report["jobs"]
        assert_layout_score(report)
        reports.append(report)
    for report in reports[1:]:
        assert_same_layout_score(reports[0], report)
    for name in reports[0]["metrics"]:
        assert all(report["metrics"][name]["status"] == "passed" for report in reports)
        for report in reports[1:]:
            assert report["metrics"][name]["value"] == pytest.approx(
                reports[0]["metrics"][name]["value"], rel=1e-3, abs=1e-9)
