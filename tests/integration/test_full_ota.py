"""Real OTA reference, source calibration and minimal rejection checks."""

import cmath
import json
import math
import struct
import subprocess
import sys
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

from benchmarking.engine.evaluate import run_evaluation
from benchmarking.engine.prepare_support import prepare_support
from benchmarking.engine.toolchains import load_toolchain
from benchmarking.evaluation import parse_evaluation
from benchmarking.files import Asset, read_file
from benchmarking.tasks import load_task

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
PUBLIC_ROOT = ROOT
CASE = PUBLIC_ROOT / "tasks/ihp-sg13g2/IHP-AnalogAcademy/cases/full_OTA"


def declared_asset(config, role):
    entry = next(asset for asset in config["assets"] if asset["role"] == role)
    asset = Asset(read_file(CASE, entry["path"]), entry["format"])
    assert asset.sha256 == entry["sha256"], entry["path"]
    return asset


@pytest.fixture(scope="module")
def environment(tmp_path_factory):
    root = tmp_path_factory.mktemp("full-ota-support")
    config = (CASE / "case.toml").read_text()
    # Freeze just the declared inputs and host configuration for this check.
    load_task(CASE / "case.toml").materialize(root / "case")
    for profile, name in [("klayout", "klayout-spice"), ("magic", "magic"), ("analog-models", "models")]:
        prepare_support(None, f"{PUBLIC_ROOT}/tasks/ihp-sg13g2/pdk.toml#{profile}", root / name)
        config = config.replace(f"build/support/full-ota-{name}", str(root / name))
    path = root / "case/case.toml"
    config = standalone_config(config)
    path.write_text(config)
    return path, load_task(path), load_toolchain(path), tomllib.loads(config)


def evaluate(layout, environment, destination):
    config, _, _, _ = environment
    candidate = destination.with_suffix(".gds")
    candidate.write_bytes(layout.content)
    completed = subprocess.run(
        [sys.executable, "-m", "benchmarking.engine.cli", "evaluate", str(config), str(candidate), "--output", str(destination)],
        cwd=ROOT, capture_output=True, text=True, timeout=1200, check=False,
    )
    assert completed.returncode in (0, 1), completed.stdout + completed.stderr
    return completed.returncode, json.loads((destination / "report.json").read_text())


def raw_rows(path):
    """Read the real/complex binary vectors exported by ngspice on Linux x86-64."""
    header, binary = path.read_bytes().split(b"Binary:\n", 1)
    fields, variables = header.decode().split("Variables:\n", 1)
    metadata = dict(line.split(":", 1) for line in fields.splitlines())
    names = [line.split()[1] for line in variables.splitlines() if line.strip()]
    count = int(metadata["No. Points"])
    complex_values = "complex" in metadata["Flags"]
    values = [item[0] for item in struct.iter_unpack("<d", binary)]
    if complex_values:
        values = [complex(real, imaginary) for real, imaginary in zip(values[::2], values[1::2], strict=True)]
    assert len(names) == int(metadata["No. Variables"])
    assert len(values) == count * len(names)
    return [dict(zip(names, values[i:i + len(names)], strict=True)) for i in range(0, len(values), len(names))]


def check_waveform_measurements(report, destination):
    job = report["jobs"]["nominal"]
    ac = raw_rows(destination / job["outputs"]["ac"]["path"])
    op = raw_rows(destination / job["outputs"]["op"]["path"])[0]
    # Derive transfer from node voltages, without using the deck's computed
    # gain/phase vectors or copying the simulator's measurement output.
    transfer = [row["v(vout)"] / (row["v(vp)"] - row["v(vm)"]) for row in ac]
    gain = [20 * math.log10(abs(value)) for value in transfer]
    frequency = [row["frequency"].real for row in ac]
    phase = []
    for value in transfer:
        angle = math.degrees(cmath.phase(value))
        phase.append(angle if not phase else phase[-1] + (angle - phase[-1] + 180) % 360 - 180)
    assert all(math.isfinite(angle) for angle in phase)
    index = next(i for i in range(1, len(gain)) if gain[i - 1] > 0 >= gain[i])
    fraction = gain[index - 1] / (gain[index - 1] - gain[index])
    expected = {
        "low_frequency_gain": gain[0],
        "unity_gain_bandwidth": frequency[index - 1] + fraction * (frequency[index] - frequency[index - 1]),
        "phase_margin": 180 + phase[index - 1] + fraction * (phase[index] - phase[index - 1]),
        "supply_power": -op["v(vdd)"] * op["i(vdd)"],
        "output_bias": op["v(vout)"],
    }
    # Account for ngspice's printed measurement precision and interpolation.
    tolerances = {"low_frequency_gain": 1e-4, "unity_gain_bandwidth": 2,
                  "phase_margin": 1e-3, "supply_power": 1e-12, "output_bias": 1e-10}
    for name, value in expected.items():
        assert job["measurements"][name]["value"] == pytest.approx(value, abs=tolerances[name], rel=0)


def ideal_body_netlist(source):
    """Replace finite source tap devices with ideal rail-connected bodies.

    Magic's SG13G2 extraction does not emit the source ``ntap1``/``ptap1``
    cards.  This controlled source-only comparison isolates that declared
    extraction boundary while retaining the same MOS models and testbench.
    """
    lines = []
    for raw in source.content.decode().splitlines():
        if raw.startswith("XR"):
            continue
        line = raw
        if raw.startswith("XM"):
            fields = raw.split()
            fields[4] = "vdd" if "pmos" in fields[5].lower() else "vss"
            line = " ".join(fields)
        lines.append(line)
    return Asset(("\n".join(lines) + "\n").encode(), "spice")


def source_characterization_plan(task):
    data = task.evaluation.description()
    jobs = [job for job in data["jobs"] if job["stage"] == "simulate"]
    for job in jobs:
        job["inputs"]["dut"] = "input:simulation"
    data.update(mode="characterization", jobs=jobs,
                metrics=[metric for metric in data["metrics"] if metric["category"] == "performance"])
    unscore_characterization(data)
    return parse_evaluation(json.dumps(data).encode(), file_format="json")


def characterize_source(task, backends, source, destination):
    inputs = task.evaluation_inputs()
    if source is not None:
        inputs["input:simulation"] = source
    report = run_evaluation(source_characterization_plan(task), inputs, backends,
                            destination, task_sha256=task.digest)
    assert_characterization_unscored(report)
    return report


@pytest.mark.acceptance_eda
def test_reference_passes_and_pre_post_calibration_uses_the_same_conditions(environment, tmp_path):
    _, task, backends, config = environment
    reference = declared_asset(config, "physical-witness")
    code, post = evaluate(reference, environment, tmp_path / "post")
    assert code == 0
    assert post["physical_valid"] is post["specs_pass"] is post["task_success"] is True
    assert_layout_score(post)
    assert all(job["status"] == "passed" for job in post["jobs"].values())
    pex = post["jobs"]["parasitics"]
    nominal = post["jobs"]["nominal"]
    assert pex["inputs"]["layout"]["sha256"] == reference.sha256
    assert nominal["inputs"]["dut"]["sha256"] == pex["outputs"]["netlist"]["sha256"]
    assert post["jobs"]["geometry"]["inputs"]["constraints"]["sha256"] == task.inline_constraints.sha256
    pex_text = (tmp_path / "post" / pex["outputs"]["netlist"]["path"]).read_text()
    assert "ntap1" not in pex_text.lower() and "ptap1" not in pex_text.lower()
    mos_lines = [line.split() for line in pex_text.splitlines()
                 if line.startswith("X") and "sg13_lv_" in line]
    assert mos_lines and all(line[4].lower().startswith(("vdd", "vss")) for line in mos_lines)

    # Derive source characterization from the single authoritative case plan.
    # Simulate the matched schematic's separate SPICE export. Model calls
    # retain source ng/m; source-export regression checks its CDL equivalence.
    data = task.evaluation.description()
    simulation = next(job for job in data["jobs"] if job["id"] == "nominal")
    simulation["inputs"]["dut"] = "input:simulation"
    data.update(mode="characterization", jobs=[simulation],
                metrics=[metric for metric in data["metrics"] if metric["category"] == "performance"])
    unscore_characterization(data)
    pre = run_evaluation(parse_evaluation(json.dumps(data).encode(), file_format="json"),
                         task.evaluation_inputs(),
                         backends, tmp_path / "pre", task_sha256=task.digest)
    assert pre["outcome"] == "passed", pre["jobs"]
    assert pre["task_success"] is None
    assert_characterization_unscored(pre)
    assert pre["jobs"]["nominal"]["inputs"]["dut"]["sha256"] == task.evaluation_inputs()["input:simulation"].sha256
    assert pre["jobs"]["nominal"]["inputs"]["deck"] == nominal["inputs"]["deck"]
    assert pre["backends"]["circuit.simulate"] == post["backends"]["circuit.simulate"]
    check_waveform_measurements(pre, tmp_path / "pre")
    check_waveform_measurements(post, tmp_path / "post")


@pytest.mark.acceptance_eda
def test_finite_source_taps_are_nominally_negligible_when_bodies_are_ideal(environment, tmp_path):
    _, task, backends, _ = environment
    finite = characterize_source(task, backends, None, tmp_path / "finite-taps")
    ideal = characterize_source(task, backends,
                               ideal_body_netlist(task.evaluation_inputs()["input:simulation"]),
                               tmp_path / "ideal-bodies")
    assert finite["outcome"] == ideal["outcome"] == "passed"
    assert finite["physical_valid"] is ideal["physical_valid"] is None
    assert finite["task_success"] is ideal["task_success"] is None
    finite_measurements = finite["jobs"]["nominal"]["measurements"]
    ideal_measurements = ideal["jobs"]["nominal"]["measurements"]
    limits = {"low_frequency_gain": 1e-5, "unity_gain_bandwidth": 10,
              "phase_margin": 1e-4, "supply_power": 1e-9, "output_bias": 1e-8}
    for name, measurement in finite_measurements.items():
        difference = abs(ideal_measurements[name]["value"] - measurement["value"])
        assert difference <= limits[name], (name, measurement, ideal_measurements[name])


@pytest.mark.acceptance_eda
def test_rotated_reference_exceeds_height_and_blocks_pex(environment, tmp_path):
    _, _, backends, config = environment
    # 90-degree rotation preserves devices and connectivity but places the
    # reference's long axis along Y, exceeding the approved 50 um height.
    script = Asset(b'''from klayout import db
layout = db.Layout()
layout.read("original.gds")
layout.top_cell().transform(db.Trans(db.Trans.R90))
layout.write("rotated.gds")
''', "python")
    result = backends["layout.artifact"].tool.run(
        ["python", "rotate.py"], {"rotate.py": script, "original.gds": declared_asset(config, "physical-witness")},
        {"rotated.gds": "gds"})
    assert result.returncode == 0 and not result.reason, result.evidence
    code, report = evaluate(result.files["rotated.gds"], environment, tmp_path / "rotated")
    assert code == 1
    assert report["physical_valid"] is False, report["jobs"]
    assert report["jobs"]["geometry"]["status"] == "failed"
    assert report["task_success"] is False
    assert report["jobs"]["parasitics"]["status"] == report["jobs"]["nominal"]["status"] == "blocked"
    assert_layout_score(report)
    assert report["score"]["value"] == 0


# Generate all negative witnesses inside the pinned KLayout container.  This
# keeps the qualification evidence tied to the maintained OTA GDS and its
# current case-owned netlist, rather than to an upstream report.
_MUTATION_SCRIPT = r'''import sys
from klayout import db

kind = sys.argv[1]
source = db.Layout()
source.read("original.gds")
source_top_name = source.top_cell().name
if kind == "empty":
    layout = db.Layout()
    top = layout.create_cell(source_top_name)
else:
    layout = source
    top = layout.top_cell()

def layer(number, datatype=0):
    return layout.layer(number, datatype)

def box(x0, y0, x1, y1):
    return db.Box(round(x0 / layout.dbu), round(y0 / layout.dbu),
                  round(x1 / layout.dbu), round(y1 / layout.dbu))

if kind == "empty":
    pass
elif kind == "translate":
    top.transform(db.Trans(500, 700))
elif kind == "missing_pin":
    removed = 0
    for shape in list(top.shapes(layer(67, 25)).each()):
        if shape.is_text() and shape.text.string == "vout":
            shape.delete()
            removed += 1
    assert removed == 1
elif kind == "extra_pin":
    top.shapes(layer(67, 25)).insert(
        db.Text("extra", db.Trans(round(53.29 / layout.dbu), round(-3.13 / layout.dbu))))
elif kind in ("swap_supply", "swap_input", "swap_output"):
    labels = {
        "swap_supply": ("vdd", "vss"),
        "swap_input": ("v+", "v-"),
        "swap_output": ("iout", "vout"),
    }[kind]
    changed = 0
    for index in layout.layer_indexes():
        for shape in top.shapes(index).each():
            if shape.is_text() and shape.text.string in labels:
                label = shape.text
                label.string = {labels[0]: labels[1], labels[1]: labels[0]}[label.string]
                shape.text = label
                changed += 1
    assert changed == 2
elif kind == "short":
    # Bridge the maintained M1 vdd and vss routes.
    top.shapes(layer(8)).insert(box(10.1, -31.0, 19.65, -28.2))
elif kind == "open":
    point = db.Point(round(53.29 / layout.dbu), round(-3.13 / layout.dbu))
    removed = 0
    for shape in list(top.shapes(layer(67)).each()):
        if shape.bbox().contains(point):
            shape.delete()
            removed += 1
    assert removed == 1
elif kind == "wrong":
    shape = next(iter(top.shapes(layer(5)).each()))
    shape.delete()
elif kind == "drc":
    top.shapes(layer(8)).insert(box(90, 90, 90.01, 90.01))
elif kind == "rc_meander":
    # A same-net top-metal extension remains inside the 80 um outline.  It
    # changes extracted vout capacitance while preserving DRC and LVS.
    for index in range(16):
        y = -26.0 + 2.0 * index
        top.shapes(layer(67)).insert(box(70.4, y, 79.5, y + 0.335))
    top.shapes(layer(67)).insert(box(70.4, -26.0, 70.735, 5.435))
    top.shapes(layer(67)).insert(box(79.165, -26.0, 79.5, 5.435))
else:
    raise ValueError(kind)

layout.write("mutated.gds")
'''


def mutate_ota(backends, config, kind):
    script = Asset(_MUTATION_SCRIPT.encode(), "python")
    result = backends["layout.artifact"].tool.run(
        ["python", "mutate.py", kind],
        {"mutate.py": script, "original.gds": declared_asset(config, "physical-witness")},
        {"mutated.gds": "gds"},
    )
    assert result.returncode == 0 and not result.reason, result.evidence
    return result.files["mutated.gds"]


def run_ota(candidate, task, backends, destination):
    return run_evaluation(task.evaluation,
                          {"candidate": candidate, **task.evaluation_inputs()},
                          backends, destination, task_sha256=task.digest)


def assert_same_ota_decision(reference, candidate):
    assert candidate["outcome"] == reference["outcome"] == "passed"
    assert candidate["physical_valid"] is reference["physical_valid"] is True
    assert candidate["specs_pass"] is reference["specs_pass"] is True
    assert candidate["task_success"] is reference["task_success"] is True
    assert_layout_score(reference)
    assert_layout_score(candidate)
    assert_same_layout_score(reference, candidate)
    assert {name: job["status"] for name, job in candidate["jobs"].items()} == {
        name: job["status"] for name, job in reference["jobs"].items()
    }
    for name, metric in reference["metrics"].items():
        assert candidate["metrics"][name]["status"] == metric["status"] == "passed"
        assert candidate["metrics"][name]["value"] == pytest.approx(
            metric["value"], rel=1e-5, abs=2e-4)


@pytest.mark.acceptance_eda
@pytest.mark.parametrize("fault", ["empty", "missing_pin", "extra_pin", "swap_supply", "swap_input", "swap_output",
                                    "short", "open", "wrong", "drc"])
def test_maintained_witness_counterexamples_cannot_qualify(environment, tmp_path, fault):
    _, task, backends, config = environment
    candidate = mutate_ota(backends, config, fault)
    report = run_ota(candidate, task, backends, tmp_path / fault)

    assert report["outcome"] == "failed"
    assert report["physical_valid"] is False
    assert report["task_success"] is False
    if fault in {"missing_pin", "extra_pin"} or fault.startswith("swap_"):
        assert report["jobs"]["artifact"]["status"] == "passed"
        assert report["jobs"]["drc"]["status"] == "passed"
        assert report["jobs"]["lvs"]["status"] == "failed"
        if fault in {"missing_pin", "extra_pin", "swap_supply"}:
            assert "top-level ports" in report["jobs"]["lvs"]["reason"]
        else:
            assert "LVS" in report["jobs"]["lvs"]["reason"]
    assert (report["jobs"]["drc"]["status"] == "failed" or
            report["jobs"]["lvs"]["status"] == "failed" or
            report["jobs"]["artifact"]["status"] == "failed")
    assert report["jobs"]["parasitics"]["status"] == "blocked"
    assert report["jobs"]["nominal"]["status"] == "blocked"
    assert_layout_score(report)
    assert report["score"]["value"] == 0


@pytest.mark.acceptance_eda
def test_equivalent_translation_preserves_the_full_ota_decision(environment, tmp_path):
    _, task, backends, config = environment
    original = declared_asset(config, "physical-witness")
    translated = mutate_ota(backends, config, "translate")
    reference = run_ota(original, task, backends, tmp_path / "equivalent-reference")
    candidate = run_ota(translated, task, backends, tmp_path / "equivalent-translated")
    assert_same_ota_decision(reference, candidate)


@pytest.mark.acceptance_eda
def test_repeated_ota_evaluation_is_deterministic(environment, tmp_path):
    _, task, backends, config = environment
    original = declared_asset(config, "physical-witness")
    first = run_ota(original, task, backends, tmp_path / "repeat-first")
    # Fresh run directory and backend objects rule out stale extraction output
    # or a warm tool process as the source of the observed decision.
    second = run_ota(original, task, load_toolchain(environment[0]), tmp_path / "repeat-second")
    assert_same_ota_decision(first, second)


@pytest.mark.acceptance_eda
def test_legal_output_parasitic_change_reaches_post_layout_performance(environment, tmp_path):
    _, task, backends, config = environment
    original = declared_asset(config, "physical-witness")
    meander = mutate_ota(backends, config, "rc_meander")
    reference = run_ota(original, task, backends, tmp_path / "rc-reference")
    variant = run_ota(meander, task, backends, tmp_path / "rc-meander")
    assert variant["outcome"] == reference["outcome"] == "passed"
    assert variant["physical_valid"] is reference["physical_valid"] is True
    assert variant["specs_pass"] is reference["specs_pass"] is True
    assert variant["task_success"] is reference["task_success"] is True
    assert_layout_score(reference)
    assert_layout_score(variant)
    assert {name: job["status"] for name, job in variant["jobs"].items()} == {
        name: job["status"] for name, job in reference["jobs"].items()
    }
    assert all(metric["status"] == "passed" for metric in variant["metrics"].values())

    # The extension is electrically legal and still passes all declared
    # limits, but it must not disappear between layout and simulation.  The
    # PEX netlist digest and two transfer metrics provide independent evidence.
    ref_pex = reference["jobs"]["parasitics"]["outputs"]["netlist"]
    variant_pex = variant["jobs"]["parasitics"]["outputs"]["netlist"]
    assert ref_pex["sha256"] != variant_pex["sha256"]
    assert variant["metrics"]["unity_gain_bandwidth"]["value"] != pytest.approx(
        reference["metrics"]["unity_gain_bandwidth"]["value"], rel=1e-8, abs=1e-6)
    assert variant["metrics"]["phase_margin"]["value"] != pytest.approx(
        reference["metrics"]["phase_margin"]["value"], rel=1e-8, abs=1e-8)
