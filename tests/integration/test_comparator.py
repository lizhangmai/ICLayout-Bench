"""The approved comparator witness and original DRC failure through one judge."""

import itertools
import json
import re
import struct
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from helpers.case_config import standalone_config
from helpers.scoring import (
    assert_characterization_unscored,
    assert_layout_score,
    assert_same_layout_score,
    unscore_characterization,
)
from helpers.stimuli import command, number

from benchmarking.bundles import publish_bundle
from benchmarking.evaluate import run_evaluation
from benchmarking.evaluation import parse_evaluation
from benchmarking.files import Asset
from benchmarking.klayout import KLayoutDocker
from benchmarking.prepare_support import prepare_support
from benchmarking.tasks import load_task
from benchmarking.toolchains import load_toolchain

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / "tasks/ihp-sg13g2/IHP-AnalogAcademy/cases/comparator"


@pytest.fixture(scope="module")
def case_config(tmp_path_factory):
    root = tmp_path_factory.mktemp("comparator-support")
    directory = root / "case"
    load_task(CASE / "case.toml").materialize(directory)
    path = directory / "case.toml"
    config = (CASE / "case.toml").read_text()
    for profile, name in [("klayout", "klayout"), ("magic", "magic"), ("analog-models", "analog-models")]:
        prepare_support(ROOT / "third_party/IHP-Open-PDK", f"{ROOT}/tasks/ihp-sg13g2/pdk.toml#{profile}", root / name)
        config = config.replace(f"build/support/comparator-{name}", str(root / name))
    config = standalone_config(config)
    path.write_text(config)
    return path


def evaluate(candidate, case_config, destination):
    completed = subprocess.run(
        ["uv", "run", "--locked", "python", "main.py", "evaluate", str(case_config),
         str(candidate), "--output", str(destination)],
        cwd=ROOT, capture_output=True, text=True, timeout=1200, check=False,
    )
    assert (destination / "report.json").is_file(), completed.stdout + completed.stderr
    return completed, json.loads((destination / "report.json").read_text())


def check_transient_measurements(job, directory, polarity, deck):
    """Recompute delay/margin/power from raw voltages/current, without .meas vectors."""
    path = directory / job["outputs"]["waveform"]["path"]
    header, binary = path.read_bytes().split(b"Binary:\n", 1)
    fields, variables = header.decode().split("Variables:\n", 1)
    metadata = dict(line.split(":", 1) for line in fields.splitlines())
    assert "real" in metadata["Flags"]
    names = [line.split()[1] for line in variables.splitlines() if line.strip()]
    values = [v[0] for v in struct.iter_unpack("<d", binary)]
    assert len(values) == len(names) * int(metadata["No. Points"])
    rows = [dict(zip(names, values[i:i + len(names)], strict=True))
            for i in range(0, len(values), len(names))]
    time = [row["time"] for row in rows]
    output = [polarity * (row["v(outp)"] - row["v(outm)"]) for row in rows]
    clock = [row["v(clk)"] for row in rows]

    def interpolate(x0, y0, x1, y1, x):
        return y0 + (y1 - y0) * (x - x0) / (x1 - x0)

    def window(vector, start, stop):
        samples = [(t, value) for t, value in zip(time, vector, strict=True) if start <= t <= stop]
        for edge in (start, stop):
            if not any(t == edge for t, _ in samples):
                i = next(i for i in range(1, len(time)) if time[i - 1] < edge < time[i])
                samples.append((edge, interpolate(time[i - 1], vector[i - 1], time[i], vector[i], edge)))
        return sorted(samples)

    def crossing(vector, threshold, start, stop, rising):
        points = window(vector, start, stop)
        for (t0, v0), (t1, v1) in itertools.pairwise(points):
            if (v0 < threshold <= v1) if rising else (v0 > threshold >= v1):
                return interpolate(v0, t0, v1, t1, threshold)
        pytest.fail("Missing waveform crossing")

    measurements = job["measurements"]
    stop = number(command(deck, '.tran')[2])
    definitions = [line.split(None, 3) for line in deck.splitlines()
                   if line.lower().startswith('.measure tran ')]
    assert {fields[2] for fields in definitions} <= measurements.keys()
    for _, _, name, definition in definitions:
        if definition.upper().startswith('TRIG '):
            trigger_def, target_def = re.split(r'\s+TARG\s+', definition, flags=re.IGNORECASE)
            def options(text):
                return {key.upper(): number(value) for key, value in
                        re.findall(r'(VAL|TD)=([^\s]+)', text, flags=re.IGNORECASE)}
            trigger_options, target_options = options(trigger_def), options(target_def)
            trigger = crossing(clock, trigger_options['VAL'], trigger_options['TD'], stop, False)
            target = crossing(output, target_options['VAL'], target_options['TD'], stop, True)
            assert measurements[name]['value'] == pytest.approx(target - trigger, abs=2e-14)
        else:
            window_bounds = {key.upper(): number(value) for key, value in
                             re.findall(r'(FROM|TO)=([^\s]+)', definition, flags=re.IGNORECASE)}
            start, end = window_bounds['FROM'], window_bounds['TO']
            if definition.upper().startswith('MIN '):
                margin = min(value for t, value in zip(time, output, strict=True) if start <= t <= end)
                assert measurements[name]['value'] == pytest.approx(margin, abs=2e-6)
            else:
                assert definition.upper().startswith('AVG '), definition
                supply = number(command(deck, 'VDD')[-1])
                points = window([-supply * row['i(vdd)'] for row in rows], start, end)
                energy = sum((t1-t0) * (p0+p1) / 2 for (t0,p0),(t1,p1) in itertools.pairwise(points))
                assert measurements[name]['value'] == pytest.approx(energy / (end-start), rel=1e-4, abs=1e-10)


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
            fields[4] = "vdd" if "pmos" in fields[5].lower() else "gnd"
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
def test_reference_passes_complete_post_layout_evaluation(case_config, tmp_path):
    completed, report = evaluate(CASE / "reference/DIFF_COMPARATOR.gds", case_config, tmp_path / "reference")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert report["physical_valid"] is report["specs_pass"] is report["task_success"] is True
    assert report["outcome"] == "passed"
    assert_layout_score(report)
    task = load_task(case_config)
    assert report["jobs"]["geometry"]["inputs"]["constraints"]["sha256"] == task.evaluation_inputs()["input:constraints"].sha256
    assert set(report["jobs"]) == {job.id for job in task.evaluation.jobs}
    assert all(job["status"] == "passed" for job in report["jobs"].values())
    netlist = report["jobs"]["parasitics"]["outputs"]["netlist"]
    pex_text = (tmp_path / "reference" / netlist["path"]).read_text()
    assert "ntap1" not in pex_text.lower() and "ptap1" not in pex_text.lower()
    mos_lines = [line.split() for line in pex_text.splitlines()
                 if line.startswith("X") and "sg13_lv_" in line]
    assert mos_lines and all(line[4].lower().startswith(("vdd", "gnd")) for line in mos_lines)
    simulations = [job for job in report["jobs"].values() if job["stage"] == "simulate"]
    assert all(job["inputs"]["dut"]["sha256"] == netlist["sha256"] for job in simulations)
    # The approved limits/conditions are checked independently in the case contract
    # test. Here verify that the real run completed every declared observation.
    assert set(report["metrics"]) == {metric.id for metric in task.evaluation.metrics}
    for metric in task.evaluation.metrics:
        observations = report["metrics"][metric.id]["observations"]
        assert set(observations) == set(metric.observations)
        assert all(observation["status"] == "passed" for observation in observations.values())

    # Both analyses use the same stimuli, models and measurement definitions.
    # Pre-layout gets the schematic export; post-layout gets candidate RC.
    data = task.evaluation.description()
    jobs = [job for job in data["jobs"] if job["stage"] == "simulate"]
    for job in jobs:
        job["inputs"]["dut"] = "input:simulation"
    data.update(mode="characterization", jobs=jobs,
                metrics=[metric for metric in data["metrics"] if metric["category"] == "performance"])
    unscore_characterization(data)
    pre = run_evaluation(parse_evaluation(json.dumps(data).encode(), file_format="json"),
                         task.evaluation_inputs(), load_toolchain(case_config), tmp_path / "pre")
    assert pre["outcome"] == "passed", pre["jobs"]
    assert pre["task_success"] is None
    assert_characterization_unscored(pre)
    assert pre["backends"]["circuit.simulate"] == report["backends"]["circuit.simulate"]
    for specification in jobs:
        name = specification["id"]
        before, after = pre["jobs"][name], report["jobs"][name]
        assert before["inputs"]["dut"]["sha256"] == task.evaluation_inputs()["input:simulation"].sha256
        assert before["inputs"]["deck"] == after["inputs"]["deck"]
        polarity = specification["parameters"]["values"]["polarity"]
        check_transient_measurements(before, tmp_path / "pre", polarity, task.input_assets()["performance"].content.decode())
        check_transient_measurements(after, tmp_path / "reference", polarity, task.input_assets()["performance"].content.decode())


@pytest.mark.acceptance_eda
def test_finite_source_taps_are_nominally_negligible_when_bodies_are_ideal(context, tmp_path):
    _, backends, task = context
    finite = characterize_source(task, backends, None, tmp_path / "finite-taps")
    ideal = characterize_source(task, backends,
                               ideal_body_netlist(task.evaluation_inputs()["input:simulation"]),
                               tmp_path / "ideal-bodies")
    assert finite["outcome"] == ideal["outcome"] == "passed"
    assert finite["physical_valid"] is ideal["physical_valid"] is None
    assert finite["task_success"] is ideal["task_success"] is None
    for job_id, finite_job in finite["jobs"].items():
        ideal_job = ideal["jobs"][job_id]
        assert ideal_job["status"] == finite_job["status"] == "passed"
        for name, measurement in finite_job["measurements"].items():
            value = measurement["value"]
            difference = abs(ideal_job["measurements"][name]["value"] - value)
            limit = 1e-12 if name.startswith("delay_") else 1e-8
            if name == "supply_power":
                limit = 1e-8
            assert difference <= limit, (job_id, name, value, ideal_job["measurements"][name])


@pytest.fixture(scope="module")
def context(case_config):
    return ({"valid": Asset((CASE / "reference/DIFF_COMPARATOR.gds").read_bytes(), "gds")},
            load_toolchain(case_config), load_task(case_config))


@pytest.mark.acceptance_eda
def test_artifact_rejection_limits_and_configuration_errors(context):
    fixtures, backends, task = context
    backend = backends["layout.artifact"]
    job = next(j for j in task.evaluation.jobs if j.id == "artifact")
    with pytest.raises(ValueError, match="declared gate"):
        backend.run(replace(job, gate="drc"),
                    {"layout": fixtures["valid"], "task": task.evaluation_inputs()["task"]})
    metadata = task.description()
    for layout, change in [(Asset(b"not GDS", "gds"), {}),
                           (Asset(b"\x00\x06\x00\x02\x02\x58", "gds"), {}),
                           (fixtures["valid"], {"top_cell": "ABSENT"}),
                           (fixtures["valid"], {"max_bytes": 6})]:
        changed = {**metadata, "output": {**metadata["output"], **change}}
        result = backend.run(job, {"layout": layout, "task": Asset(json.dumps(changed).encode(), "json")})
        assert result.status == "failed", result.reason
    with pytest.raises(ValueError, match="differs from task"):
        backend.run(replace(job, parameters_json='{"top_cell":"WRONG"}'),
                    {"layout": fixtures["valid"], "task": task.evaluation_inputs()["task"]})


@pytest.mark.acceptance_eda
@pytest.mark.parametrize("fault", ["missing_report", "partial_report", "extract_only", "broken_deck"])
def test_zero_exit_or_incomplete_deck_never_passes(context, tmp_path, fault):
    fixtures, backends, task = context
    mode = "lvs" if fault == "extract_only" else "drc"
    original = backends[f"layout.{mode}"]
    settings = dict(original.settings)
    files = dict(original.support.files)
    if fault == "extract_only":
        settings["variables"] = {**settings["variables"], "net_only": "true"}
    else:
        settings["deck"] = "fixture.drc"
        script = {"missing_report": '# Intentionally produces no report.\n',
                  "partial_report": 'source($input, $topcell)\nreport("incomplete", $report)\ninput(8,0).width(0.1).output("M1.a")\n',
                  "broken_deck": 'raise "intentional tool failure"\n'}[fault]
        files["fixture.drc"] = Asset(script.encode(), "ruby")
    files[f"{mode}.json"] = Asset(json.dumps(settings).encode(), "json")
    publish_bundle(files, {"purpose": "deliberately broken tool configuration"}, tmp_path / "support")
    backend = KLayoutDocker(image="layout-bench-tools:local", check=mode,
                            support=str(tmp_path / "support"), profile=f"{mode}.json")
    report = run_evaluation(task.evaluation, {"candidate": fixtures["valid"], **task.evaluation_inputs()},
                            {**backends, f"layout.{mode}": backend}, tmp_path / "run")
    assert report["jobs"][mode]["status"] == "error", report["jobs"]
    assert report["outcome"] == "error"
    assert report["physical_valid"] is None and report["task_success"] is None
    assert report["jobs"]["parasitics"]["status"] == "blocked"
    assert all(report["jobs"][job.id]["status"] == "blocked"
               for job in task.evaluation.jobs if job.stage == "simulate")
    assert report["jobs"][mode]["evidence"]["result.json"]["bytes"] > 0
    if fault == "partial_report":
        assert report["jobs"][mode]["evidence"]["report.db"]["bytes"] > 0
        assert "required categories" in report["jobs"][mode]["reason"]


@pytest.mark.acceptance_eda
def test_unresolved_hierarchy_text_only_and_disguised_oasis_are_rejected(context):
    fixtures, backends, task = context
    backend = backends["layout.artifact"]
    script = b'''from klayout import db
l=db.Layout(); t=l.create_cell("DIFF_COMPARATOR"); g=l.create_cell("MISSING")
g.ghost_cell=True
t.insert(db.CellInstArray(g.cell_index(),db.Trans()))
t.shapes(l.layer(8,0)).insert(db.Box(0,0,1000,1000))
l.write("ghost.gds")
l=db.Layout(); t=l.create_cell("DIFF_COMPARATOR")
t.shapes(l.layer(8,25)).insert(db.Text("D",db.Trans()))
l.write("text.gds")
l=db.Layout(); l.read("valid.gds"); l.write("disguised.oas")
'''
    outputs = {"ghost.gds": "gds", "text.gds": "gds", "disguised.oas": "gds"}
    result = backend.tool.run(["python", "generate.py"],
        {"generate.py": Asset(script, "python"), "valid.gds": fixtures["valid"]}, outputs)
    assert not result.reason
    job = next(j for j in task.evaluation.jobs if j.id == "artifact")
    for name, fragment in [("ghost.gds", "Unresolved"), ("text.gds", "no polygon"), ("disguised.oas", "not a GDSII")]:
        checked = backend.run(job, {"layout": result.files[name], "task": task.evaluation_inputs()["task"]})
        assert checked.status == "failed" and fragment in checked.reason, (name, checked.status, checked.reason)


# These mutations are generated inside the pinned KLayout container.  They
# exercise the maintained comparator witness itself, rather than depending on
# an upstream failure whose provenance and tool options may differ.
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
elif kind == "rename":
    for cell in list(layout.each_cell()):
        if cell.cell_index() != top.cell_index():
            layout.rename_cell(cell.cell_index(), "qualified_comparator_%d" % cell.cell_index())
elif kind == "flat":
    top.flatten(-1)
elif kind == "missing_pin":
    removed = 0
    for shape in list(top.shapes(layer(134, 25)).each()):
        if shape.is_text() and shape.text.string == "gnd":
            shape.delete()
            removed += 1
    assert removed == 1
elif kind == "extra_pin":
    top.shapes(layer(126, 25)).insert(
        db.Text("extra", db.Trans(round(1.025 / layout.dbu), round(2.26 / layout.dbu))))
elif kind in ("swap_supply", "swap_input", "swap_output"):
    labels = {
        "swap_supply": ("vdd", "gnd"),
        "swap_input": ("V+", "V-"),
        "swap_output": ("out+", "out-"),
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
    # Bridge the two output routes on the maintained M1 layer.
    top.shapes(layer(10)).insert(box(-9.2, 13.4, 30.4, 13.9))
elif kind == "open":
    point = db.Point(round(30.25 / layout.dbu), round(13.605 / layout.dbu))
    removed = 0
    for shape in list(top.shapes(layer(10)).each()):
        if shape.bbox().contains(point):
            shape.delete()
            removed += 1
    assert removed == 1
elif kind == "wrong":
    cell = layout.cell("nmos$1$1")
    assert cell is not None
    shape = next(iter(cell.shapes(layer(5)).each()))
    shape.delete()
elif kind == "drc":
    top.shapes(layer(8)).insert(box(90, 90, 90.01, 90.01))
elif kind == "geometry":
    top.shapes(layer(30)).insert(box(33, 0, 38, 0.3))
elif kind == "area_overflow":
    # The same previously unoccupied Metal5 routing layer now contributes to the
    # functional outline.  This legal island deliberately exceeds its width.
    top.shapes(layer(67)).insert(box(34.8, 30.0, 37.8, 33.0))
else:
    raise ValueError(kind)

layout.write("mutated.gds")
'''


def mutate_comparator(backends, kind):
    script = Asset(_MUTATION_SCRIPT.encode(), "python")
    result = backends["layout.artifact"].tool.run(
        ["python", "mutate.py", kind],
        {"mutate.py": script,
         "original.gds": Asset((CASE / "reference/DIFF_COMPARATOR.gds").read_bytes(), "gds")},
        {"mutated.gds": "gds"},
    )
    assert result.returncode == 0 and not result.reason, result.evidence
    return result.files["mutated.gds"]


def run_comparator(candidate, task, backends, destination):
    return run_evaluation(task.evaluation,
                          {"candidate": candidate, **task.evaluation_inputs()},
                          backends, destination, task_sha256=task.digest)


def assert_same_comparator_decision(reference, candidate):
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
            metric["value"], rel=1e-6, abs=1e-12)


@pytest.mark.acceptance_eda
@pytest.mark.parametrize("fault", ["empty", "missing_pin", "extra_pin", "swap_supply", "swap_input", "swap_output",
                                    "short", "open", "wrong", "drc", "geometry"])
def test_maintained_witness_counterexamples_cannot_qualify(context, tmp_path, fault):
    _, backends, task = context
    candidate = mutate_comparator(backends, fault)
    report = run_comparator(candidate, task, backends, tmp_path / fault)

    if fault == "geometry":
        assert report["physical_valid"] is False
        assert report["jobs"]["geometry"]["status"] == "failed"
        assert report["jobs"]["parasitics"]["status"] == "blocked"
        assert report["task_success"] is False
    elif fault in {"missing_pin", "extra_pin"} or fault.startswith("swap_"):
        assert report["jobs"]["artifact"]["status"] == "passed"
        assert report["jobs"]["drc"]["status"] == "passed"
        assert report["jobs"]["lvs"]["status"] == "failed"
        if fault in {"missing_pin", "extra_pin", "swap_supply"}:
            assert "top-level ports" in report["jobs"]["lvs"]["reason"]
        else:
            # Input/output swaps also alter the device-to-port graph and may
            # therefore be rejected by the earlier LVS mismatch gate.
            assert "LVS" in report["jobs"]["lvs"]["reason"]
        assert report["physical_valid"] is False
        assert report["task_success"] is False
        assert report["jobs"]["parasitics"]["status"] == "blocked"
        assert all(report["jobs"][job.id]["status"] == "blocked"
                   for job in task.evaluation.jobs if job.stage == "simulate")
    else:
        assert report["outcome"] == "failed"
        assert report["physical_valid"] is False
        assert report["task_success"] is False
        assert (report["jobs"]["drc"]["status"] == "failed" or
                report["jobs"]["lvs"]["status"] == "failed" or
                report["jobs"]["artifact"]["status"] == "failed")
        assert report["jobs"]["parasitics"]["status"] == "blocked"
        assert all(report["jobs"][job.id]["status"] == "blocked"
                   for job in task.evaluation.jobs if job.stage == "simulate")
    assert_layout_score(report)
    assert report["score"]["value"] == 0


@pytest.mark.acceptance_eda
def test_equivalent_translation_hierarchy_and_flattening_preserve_the_full_decision(context, tmp_path):
    _, backends, task = context
    original = Asset((CASE / "reference/DIFF_COMPARATOR.gds").read_bytes(), "gds")
    candidates = [original, mutate_comparator(backends, "translate"),
                  mutate_comparator(backends, "rename"), mutate_comparator(backends, "flat")]
    reports = [run_comparator(candidate, task, backends, tmp_path / f"equivalent-{index}")
               for index, candidate in enumerate(candidates)]
    for report in reports[1:]:
        assert_same_comparator_decision(reports[0], report)


@pytest.mark.acceptance_eda
def test_routing_layer_extent_is_a_physical_score_gate(context, tmp_path):
    """An out-of-bounds shape on a routing layer receives score zero."""
    _, backends, task = context
    candidate = mutate_comparator(backends, "area_overflow")
    report = run_comparator(candidate, task, backends, tmp_path / "overflow")

    assert report["jobs"]["artifact"]["status"] == "passed"
    assert report["jobs"]["drc"]["status"] == "passed"
    assert report["jobs"]["lvs"]["status"] == "passed"
    assert report["jobs"]["geometry"]["status"] == "failed"
    assert report["jobs"]["parasitics"]["status"] == "blocked"
    assert report["physical_valid"] is False
    assert report["task_success"] is False
    score = assert_layout_score(report)
    assert score["value"] == 0
    assert score["components"]["G"] == 0.0


@pytest.mark.acceptance_eda
def test_repeated_comparator_evaluation_is_deterministic(context, tmp_path, case_config):
    _, backends, task = context
    original = Asset((CASE / "reference/DIFF_COMPARATOR.gds").read_bytes(), "gds")
    first = run_comparator(original, task, backends, tmp_path / "repeat-first")
    # Recreate the backend bindings and use a fresh output tree.  The decision
    # must not depend on a warm tool process or stale extraction artifacts.
    second = run_comparator(original, task, load_toolchain(case_config), tmp_path / "repeat-second")
    assert_same_comparator_decision(first, second)
