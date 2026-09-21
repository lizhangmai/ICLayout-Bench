"""The maintained LN-TIA core: physical gates and independent pre/post checks.

The task netlist follows the published pre-sim topology (case owner decision
2026-09-12); the witness is an independent redraw reusing the upstream device
cells with new routing, not the upstream GDS.
"""

import json
import os
import re
import tomllib
from itertools import pairwise
from pathlib import Path

import pytest
from helpers.case_config import calibration_limits
from helpers.scoring import (
    assert_characterization_unscored,
    assert_layout_score,
    unscore_characterization,
)
from helpers.spice_raw import output_rows
from helpers.stimuli import assert_ac_stimuli, command, number
from helpers.stimuli import testbench as declared_testbench

from benchmarking.engine.docker import DockerTool
from benchmarking.engine.evaluate import run_evaluation
from benchmarking.engine.hbt import convert_klayout_netlist
from benchmarking.engine.ngspice import NgspiceDocker
from benchmarking.engine.prepare_support import prepare_support
from benchmarking.evaluation import parse_evaluation
from benchmarking.files import Asset

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
from helpers.catalog import ROOT as PUBLIC_ROOT

CASE = PUBLIC_ROOT / "tasks/ihp-sg13g2/TO_Apr2025/cases/40_GHZ_LOW_NOISE_TIA"
TOP = "FDM_QNC_00_LN_TIA"
PORTS = ["RFin", "RFout", "VSS", "vcc1", "vcc2", "vcc3"]


@pytest.fixture(scope="module")
def context(tmp_path_factory):
    directory = tmp_path_factory.mktemp("to-40ghz")
    config = tomllib.loads((CASE / "case.toml").read_text())
    image = os.environ.get("ICLAYOUT_BENCH_TEST_IMAGE", "iclayout-bench-tools:local")
    for name in ("klayout", "magic", "hbt-models"):
        prepare_support(None,
                        f"{PUBLIC_ROOT}/tasks/ihp-sg13g2/pdk.toml#{name}",
                        directory / name, compiler_image=image)
    for entry in config["assets"]:
        assert Asset((CASE / entry["path"]).read_bytes(), entry["format"]).sha256 == entry["sha256"]
    return config, image, directory


def task_backends(context, tmp_path):
    """Evaluator backends for the frozen task plan, using fresh support bundles."""
    from benchmarking.engine.toolchains import load_toolchain
    _config, _image, directory = context
    config_text = (CASE / "case.toml").read_text()
    for name in ("klayout", "magic", "hbt-models"):
        config_text = config_text.replace(f"build/support/to-40ghz-{name}", str(directory / name))
    path = tmp_path / "case-toolchain.toml"
    path.write_text(config_text)
    return load_toolchain(path)


def declared_witness(context):
    entry = next(a for a in context[0]["assets"] if a["role"] == "physical-witness")
    asset = Asset((CASE / entry["path"]).read_bytes(), "gds")
    assert asset.sha256 == entry["sha256"]
    return asset


def characterization_plan(task):
    """Build the source-only plan with the post-layout jobs unchanged."""
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
    """Change only the finite source tap to the approved ideal-body rail."""
    lines = []
    for raw in source.content.decode().splitlines():
        if raw.startswith("XSUBTAP "):
            fields = raw.split()
            fields[-1] = "R=1e-6"
            raw = " ".join(fields)
        lines.append(raw)
    return Asset(("\n".join(lines) + "\n").encode(), "spice")


def compare_measurements(reference, candidate, task):
    """Return the largest relative difference over all declared sim values."""
    largest = {"relative_difference": 0.0}
    for specification in task.evaluation.jobs:
        if specification.stage != "simulate":
            continue
        name = specification.id
        before = reference["jobs"][name]["measurements"]
        after = candidate["jobs"][name]["measurements"]
        assert before.keys() == after.keys()
        for metric, measurement in before.items():
            left = measurement["value"]
            right = after[metric]["value"]
            denominator = max(abs(left), 1e-30)
            relative = abs(right - left) / denominator
            if relative > largest["relative_difference"]:
                largest = {"relative_difference": relative,
                           "job": name, "metric": metric,
                           "reference": left, "candidate": right}
    return largest


def mutate_witness(backends, witness, operation):
    """Apply a deterministic layout-database transform in the artifact tool."""
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
        {"mutate.py": script, "witness.gds": witness},
        {"mutated.gds": "gds"},
    )
    assert result.returncode == 0 and not result.reason, result.evidence
    return result.files["mutated.gds"]


def test_maintained_netlists_declare_the_published_core(context, tmp_path):
    """Maintained netlists declare the topology, independent supplies and ports."""
    _config, _image, _ = context
    for name in ("circuit.cdl", "circuit.spice"):
        frozen = (CASE / f"materials/{name}").read_text()
        assert "FDM_QNC_00_LN_TIA" in frozen
    cdl = (CASE / "materials/circuit.cdl").read_text()
    cards = {}
    for line in cdl.splitlines():
        parts = line.split()
        if parts and parts[0][0] in "QRCX" and not line.startswith("*"):
            cards[parts[0].upper()] = parts[1:]
    assert cards["QQ1"][:4] == ["net1", "RFin", "VSS", "SUBSTRATE"]
    assert cards["QQ2"][:4] == ["vcc2", "net1", "net2", "SUBSTRATE"]
    assert cards["QQ3"][:4] == ["RFout", "net2", "net3", "SUBSTRATE"]
    assert cards["RRC1"][:3] == ["vcc1", "net1", "SUBSTRATE"]
    assert cards["RRF"][:3] == ["RFin", "net2", "SUBSTRATE"]
    assert cards["RRE2"][:3] == ["net2", "VSS", "SUBSTRATE"]
    assert cards["RRE3"][:3] == ["net3", "VSS", "SUBSTRATE"]
    assert cards["RRC3"][:3] == ["vcc3", "RFout", "SUBSTRATE"]
    assert cards["RPTAP"][:5] == ["VSS", "SUBSTRATE", "ptap1", "A=25p", "P=20u"]
    assert cards["CC1"][:3] == ["vcc1", "VSS", "cap_cmim"]
    assert cards["CC2"][:3] == ["vcc2", "VSS", "cap_cmim"]
    assert cards["CC3"][:3] == ["vcc3", "VSS", "cap_cmim"]


@pytest.mark.acceptance_eda
def test_executable_task_accepts_its_witness(context, tmp_path):
    """The maintained witness passes physical gates and all post-layout checks."""
    from benchmarking.tasks import load_task
    task = load_task(CASE / "case.toml")
    assert task.status == "qualified" and task.witnessed is True
    assert task.evaluation.mode == "post_layout"
    witness = declared_witness(context)
    backends = task_backends(context, tmp_path)
    report = run_evaluation(task.evaluation,
                            {"candidate": witness, **task.evaluation_inputs()},
                            backends, tmp_path / "witness",
                            task_sha256=task.digest, task_witnessed=task.witnessed)
    assert report["outcome"] == "passed" and report["physical_valid"] is True
    assert report["specs_pass"] is True and report["task_success"] is True
    assert_layout_score(report)
    check_measurements(report, tmp_path / "witness", task)

    # Calibrate the maintained schematic against the same testbench and
    # operating points.  The post-layout run must consume the extracted
    # candidate netlist; the characterization run must consume the declared
    # simulation netlist, while all simulation settings remain identical.
    pex = report["jobs"]["parasitics"]
    simulations = [job for job in task.evaluation.description()["jobs"]
                   if job["stage"] == "simulate"]
    for job in simulations:
        assert report["jobs"][job["id"]]["inputs"]["circuit"]["sha256"] == \
            pex["outputs"]["netlist"]["sha256"]
        job["inputs"]["circuit"] = "input:simulation"
    characterization = task.evaluation.description()
    characterization.update(
        mode="characterization",
        jobs=simulations,
        metrics=[metric for metric in characterization["metrics"]
                 if metric["category"] == "performance"],
    )
    unscore_characterization(characterization)
    pre = run_evaluation(
        parse_evaluation(json.dumps(characterization).encode(), file_format="json"),
        task.evaluation_inputs(), backends,
        tmp_path / "pre", task_sha256=task.digest,
    )
    assert pre["outcome"] == "passed", pre["jobs"]
    assert_characterization_unscored(pre)
    for job in simulations:
        before, after = pre["jobs"][job["id"]], report["jobs"][job["id"]]
        assert before["inputs"]["deck"] == after["inputs"]["deck"]
        assert before["parameters"] == after["parameters"]
    assert pre["backends"]["circuit.simulate"] == report["backends"]["circuit.simulate"]
    check_measurements(pre, tmp_path / "pre", task)

    # Check the compact-device interpretation independently from Magic wire
    # parasitics.  The native candidate extraction must preserve all three
    # HBTs, their model, and their Nx multiplicities before the RC merge.
    native_asset = pex["evidence"]["klayout_native_netlist"]
    native_raw = (tmp_path / "witness" / native_asset["path"]).read_bytes()
    native_circuit = Asset(convert_klayout_netlist(native_raw, PORTS).encode(), "spice")
    native_text = native_circuit.content.decode()
    authority = task.input_assets()['netlist'].content.decode()
    def population(text):
        return sorted(re.findall(r'npn13g2 .*?nx=(\d+)', text, flags=re.IGNORECASE))
    assert population(authority)
    assert population(native_text) == population(authority)
    native = run_evaluation(
        characterization_plan(task),
        {**task.evaluation_inputs(), "input:simulation": native_circuit},
        backends, tmp_path / "native", task_sha256=task.digest,
    )
    assert native["outcome"] == "passed", native["jobs"]
    check_measurements(native, tmp_path / "native", task)
    difference = compare_measurements(pre, native, task)
    (tmp_path / "native-source-comparison.json").write_text(
        json.dumps({"source_report": "pre/report.json",
                    "native_report": "native/report.json",
                    "maximum": difference}, indent=2) + "\n"
    )
    assert difference["relative_difference"] <= 1e-3, difference


def test_executable_task_rejects_a_rotated_witness(context, tmp_path):
    """A 90-degree rotation breaks the LVS interface and blocks downstream checks."""
    _config, image, _ = context
    script = Asset(b'''from klayout import db
layout = db.Layout()
layout.read("w.gds")
layout.top_cell().transform(db.Trans(db.Trans.R90))
layout.write("rotated.gds")
''', "python")
    result = DockerTool(image, ["klayout", "-v"], 60).run(
        ["python", "rot.py"], {"rot.py": script, "w.gds": declared_witness(context)},
        {"rotated.gds": "gds"})
    assert result.returncode == 0 and not result.reason, result.evidence
    from benchmarking.tasks import load_task
    task = load_task(CASE / "case.toml")
    report = run_evaluation(task.evaluation,
                            {"candidate": result.files["rotated.gds"], **task.evaluation_inputs()},
                            task_backends(context, tmp_path), tmp_path / "rotated",
                            task_sha256=task.digest, task_witnessed=task.witnessed)
    assert report["outcome"] == "failed"
    assert report["jobs"]["artifact"]["status"] == "passed"
    assert report["jobs"]["lvs"]["status"] == "failed"
    assert report["jobs"]["geometry"]["status"] == "blocked"
    assert report["jobs"]["parasitics"]["status"] == "blocked"
    assert report["task_success"] is False
    assert_layout_score(report)
    assert report["score"]["value"] == 0


@pytest.mark.acceptance_eda
def test_swapped_supply_labels_fail_lvs_before_simulation(context, tmp_path):
    """Strict named-port LVS rejects an exchange of the equal-voltage rails."""
    script = Asset(b'''from klayout import db
layout = db.Layout()
layout.read("w.gds")
changed = 0
for cell in layout.each_cell():
    for layer in layout.layer_indexes():
        for shape in cell.shapes(layer).each():
            if shape.is_text() and shape.text.string in ("VCC2", "VCC3"):
                label = shape.text
                label.string = {"VCC2": "VCC3", "VCC3": "VCC2"}[label.string]
                shape.text = label
                changed += 1
assert changed > 0
layout.write("swapped.gds")
''', "python")
    backends = task_backends(context, tmp_path)
    result = backends["layout.artifact"].tool.run(
        ["python", "swap.py"], {"swap.py": script, "w.gds": declared_witness(context)},
        {"swapped.gds": "gds"})
    assert result.returncode == 0 and not result.reason, result.evidence
    from benchmarking.tasks import load_task
    task = load_task(CASE / "case.toml")
    report = run_evaluation(task.evaluation,
                            {"candidate": result.files["swapped.gds"], **task.evaluation_inputs()},
                            backends, tmp_path / "swapped-supplies",
                            task_sha256=task.digest, task_witnessed=task.witnessed)
    assert report["jobs"]["artifact"]["status"] == report["jobs"]["drc"]["status"] == "passed"
    assert report["jobs"]["lvs"]["status"] == "failed"
    assert report["jobs"]["parasitics"]["status"] == "blocked"
    assert report["task_success"] is False


@pytest.mark.acceptance_eda
def test_finite_substrate_tap_calibration(context, tmp_path):
    """Finite source tap and ideal-body source runs remain the same case."""
    from benchmarking.tasks import load_task
    task = load_task(CASE / "case.toml")
    backends = task_backends(context, tmp_path)
    source = task.evaluation_inputs()["input:simulation"]
    finite = run_evaluation(
        characterization_plan(task), task.evaluation_inputs(), backends,
        tmp_path / "finite-tap", task_sha256=task.digest,
    )
    ideal_inputs = task.evaluation_inputs()
    ideal_inputs["input:simulation"] = ideal_body_netlist(source)
    ideal = run_evaluation(
        characterization_plan(task), ideal_inputs, backends,
        tmp_path / "ideal-body", task_sha256=task.digest,
    )
    assert finite["outcome"] == ideal["outcome"] == "passed"
    assert_characterization_unscored(finite)
    assert_characterization_unscored(ideal)
    check_measurements(finite, tmp_path / "finite-tap", task)
    check_measurements(ideal, tmp_path / "ideal-body", task)
    difference = compare_measurements(finite, ideal, task)
    (tmp_path / "finite-ideal-comparison.json").write_text(
        json.dumps({"finite_report": "finite-tap/report.json",
                    "ideal_body_report": "ideal-body/report.json",
                    "maximum": difference}, indent=2) + "\n"
    )
    assert difference["relative_difference"] <= calibration_limits(CASE)["relative"], difference


@pytest.mark.acceptance_eda
def test_repeated_translated_candidate_preserves_decisions(context, tmp_path):
    """Repeated and grid-translated witnesses preserve post-layout metrics."""
    from benchmarking.tasks import load_task
    task = load_task(CASE / "case.toml")
    witness = declared_witness(context)
    backends = task_backends(context, tmp_path)
    translated = mutate_witness(
        backends, witness,
        "top.transform(db.Trans(round(13 / layout.dbu), round(17 / layout.dbu)))",
    )
    reports = []
    for index, candidate in enumerate((witness, witness, translated)):
        report = run_evaluation(
            task.evaluation,
            {"candidate": candidate, **task.evaluation_inputs()},
            backends, tmp_path / f"repeat-{index}",
            task_sha256=task.digest, task_witnessed=task.witnessed,
        )
        assert report["outcome"] == "passed", report["jobs"]
        assert report["physical_valid"] is report["specs_pass"] is report["task_success"] is True
        assert_layout_score(report)
        reports.append(report)
    differences = []
    maximum = 0.0
    for name in reports[0]["metrics"]:
        values = [report["metrics"][name]["value"] for report in reports]
        assert all(report["metrics"][name]["status"] == "passed" for report in reports)
        for value in values[1:]:
            relative = abs(value - values[0]) / max(abs(values[0]), 1e-30)
            maximum = max(maximum, relative)
            assert value == pytest.approx(values[0], rel=1e-3, abs=1e-9), (name, values)
        differences.append({"metric": name, "values": values})
    (tmp_path / "repeatability-comparison.json").write_text(
        json.dumps({"reports": [f"repeat-{index}/report.json" for index in range(3)],
                    "maximum_allowed_relative_difference": 1e-3,
                    "maximum_observed_relative_difference": maximum,
                    "metrics": differences}, indent=2) + "\n"
    )


@pytest.mark.acceptance_eda
def test_core_operating_point_uses_real_hbt_resistor_and_capacitor_models(context, tmp_path):
    """The case-owned nominal point uses the corrected DUT port order."""
    _config, image, directory = context
    plan = parse_evaluation(json.dumps({"mode": "characterization", "metrics": [],
        "jobs": [{"id": "op", "stage": "simulate", "operation": "circuit.simulate",
                  "inputs": {"deck": "input:deck", "circuit": "input:circuit"},
                  "outputs": {"waveform": "ngspice-raw"},
                  "parameters": {"values": {"input_current": 0},
                                  "measurements": {"input_bias": "V", "output_bias": "V",
                                 "supply1_current": "A", "supply2_current": "A",
                                 "supply3_current": "A"},
                                 "exports": {"waveform": "operating_point.raw"}}}],
    }).encode(), file_format="json")
    settings = {"image": image, "support": str(directory / "hbt-models")}
    report = run_evaluation(plan, {
        "input:deck": Asset((CASE / "materials/testbench.spice").read_bytes(), "spice"),
        "input:circuit": Asset((CASE / "materials/circuit.spice").read_bytes(), "spice")},
        {"circuit.simulate": NgspiceDocker(**settings)}, tmp_path / "op")
    values = {name: m["value"] for name, m in report["jobs"]["op"]["measurements"].items()}
    # Values are from ngspice 42 with hbt_typ/res_typ/cap_typ in the reviewed
    # support bundle, after correcting the testbench instance order.
    assert values == pytest.approx({"input_bias": 0.7969694832621,
                                    "output_bias": 2.070945101961,
                                    "supply1_current": 6.605785410982e-04,
                                    "supply2_current": 1.462121157998e-03,
                                    "supply3_current": 1.054659780059e-03}, rel=1e-4)


def check_measurements(report, directory, task):
    """Recompute transfer and power from candidate waveform samples."""
    outputs = []
    for specification in task.evaluation.jobs:
        if specification.stage != "simulate":
            continue
        name = specification.id
        job = report["jobs"][name]
        assert job["status"] == "passed", job
        ac = output_rows(report, directory, name, "ac")
        op = output_rows(report, directory, name, "op")[0]
        deck = declared_testbench(task, name)
        assert_ac_stimuli(deck, specification.parameters.get("values", {}), op, ac)

        current = specification.parameters["values"]["input_current"]
        assert op["i(vsense)"] == pytest.approx(current, abs=1e-12)
        # The ideal 1 A AC sense current has a sub-nanamp numerical residual
        # in ngspice's complex linear solve; this check remains far tighter
        # than any declared circuit metric.
        source = command(deck, "IIN")
        ac_amplitude = number(source[source.index("AC") + 1])
        assert all(row["i(vsense)"] == pytest.approx(complex(ac_amplitude), abs=1e-9) for row in ac)

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
        assert all(expected[f"supply{index}_current"] > 0 for index in (1, 2, 3))
        outputs.append((current, op["v(rfout)"], expected))
    assert len(outputs) >= 2
    outputs.sort()
    assert all(a[1] < b[1] for a, b in pairwise(outputs))
