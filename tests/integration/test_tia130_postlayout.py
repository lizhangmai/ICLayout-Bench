"""Independent functional calibration of the case-owned two-stage HBT TIA."""

import json
import re
import tomllib
from itertools import pairwise
from pathlib import Path

import pytest
from helpers.case_config import standalone_config
from helpers.scoring import (
    assert_characterization_unscored,
    assert_layout_score,
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
CASE = PUBLIC_ROOT / "tasks/ihp-sg13g2/TO_Apr2025/cases/DC_to_130_GHz_TIA.design_1"


def witness_asset():
    case = tomllib.loads((CASE / "case.toml").read_text())
    declared = next(asset for asset in case["assets"] if asset["role"] == "physical-witness")
    witness = Asset((CASE / declared["path"]).read_bytes(), declared["format"])
    assert witness.sha256 == declared["sha256"]
    return witness


@pytest.fixture(scope="module")
def environment(tmp_path_factory):
    root = tmp_path_factory.mktemp("tia130-functional")
    task = load_task(CASE / "case.toml")
    task.materialize(root / "case")
    config = (CASE / "case.toml").read_text()
    for profile, name in [("klayout", "klayout"), ("magic", "magic"), ("hbt-models", "models")]:
        prepare_support(PUBLIC_ROOT / "third_party/IHP-Open-PDK", f"{PUBLIC_ROOT}/tasks/ihp-sg13g2/pdk.toml#{profile}", root / name)
        config = config.replace(f"build/support/to-design1-{name}", str(root / name))
    path = root / "case/case.toml"
    config = standalone_config(config)
    path.write_text(config)
    return load_task(path), load_toolchain(path)


def check_measurements(report, directory, task):
    biases = []
    for specification in task.evaluation.jobs:
        if specification.stage != "simulate":
            continue
        name = specification.id
        job = report["jobs"][name]
        ac = output_rows(report, directory, name, "ac")
        op = output_rows(report, directory, name, "op")[0]
        deck = declared_testbench(task, name)
        assert_ac_stimuli(deck, specification.parameters.get("values", {}), op, ac)

        current = specification.parameters["values"]["input_current"]
        assert op["i(vsense)"] == pytest.approx(current, abs=1e-12)
        source = command(deck, "IIN")
        ac_amplitude = number(source[source.index("AC") + 1])
        assert all(row["i(vsense)"] == pytest.approx(complex(ac_amplitude), abs=1e-10) for row in ac)
        # Read raw node voltage and actual injected current, not the deck's
        # computed transfer vectors or a copy of its reported measurement.
        transfer = [row["v(output)"] / row["i(vsense)"] for row in ac]

        expected = {
            "input_bias": op["v(input)"], "output_bias": op["v(output)"],
            "supply_power": -op["v(vcc1)"] * op["i(vcc1)"] - op["v(vcc2)"] * op["i(vcc2)"],
            "transimpedance_low": transfer[0].real,
            "transimpedance_high": abs(transfer[-1]),
        }
        for measurement, value in expected.items():
            assert job["measurements"][measurement]["value"] == pytest.approx(value, rel=1e-6, abs=1e-10)
        biases.append((current, op["v(output)"]))
    assert len(biases) >= 2
    biases.sort()
    # Check large-signal DC transfer polarity independently of AC measurements.
    assert all(a[1] < b[1] for a, b in pairwise(biases))


@pytest.mark.acceptance_eda
def test_reference_function_and_pre_post_calibration(environment, tmp_path):
    task, backends = environment
    assert task.evaluation.mode == "post_layout"
    witness = witness_asset()
    post = run_evaluation(task.evaluation, {"candidate": witness, **task.evaluation_inputs()},
                          backends, tmp_path / "post", task_sha256=task.digest, task_witnessed=task.witnessed)
    assert post["physical_valid"] is post["specs_pass"] is post["task_success"] is True, post["jobs"]
    assert_layout_score(post)
    pex = post["jobs"]["parasitics"]
    assert pex["inputs"]["layout"]["sha256"] == witness.sha256
    simulations = [job for job in task.evaluation.description()["jobs"] if job["stage"] == "simulate"]
    for job in simulations:
        assert post["jobs"][job["id"]]["inputs"]["circuit"]["sha256"] == pex["outputs"]["netlist"]["sha256"]
        job["inputs"]["circuit"] = "input:simulation"
    source = task.evaluation.description()
    source.update(mode="characterization", jobs=simulations,
                  metrics=[metric for metric in source["metrics"] if metric["category"] == "performance"])
    unscore_characterization(source)
    pre = run_evaluation(parse_evaluation(json.dumps(source).encode(), file_format="json"),
                         task.evaluation_inputs(), backends, tmp_path / "pre", task_sha256=task.digest)
    assert pre["outcome"] == "passed", pre["jobs"]
    assert_characterization_unscored(pre)
    for job in simulations:
        before, after = pre["jobs"][job["id"]], post["jobs"][job["id"]]
        assert before["inputs"]["deck"] == after["inputs"]["deck"]
        assert before["parameters"] == after["parameters"]
    assert pre["backends"]["circuit.simulate"] == post["backends"]["circuit.simulate"]
    check_measurements(pre, tmp_path / "pre", task)
    check_measurements(post, tmp_path / "post", task)

    # Check compact-device interpretation separately from wire parasitics.
    # A wrong Nx or drawn/effective emitter mapping can produce a converged
    # post-layout circuit while silently simulating different HBT devices.
    native_asset = pex["evidence"]["klayout_native_netlist"]
    native_raw = (tmp_path / "post" / native_asset["path"]).read_bytes()
    ports = next(job.parameters["ports"] for job in task.evaluation.jobs if job.stage == "extract")
    native_circuit = Asset(convert_klayout_netlist(native_raw, ports).encode(), "spice")
    native = run_evaluation(parse_evaluation(json.dumps(source).encode(), file_format="json"),
                            {**task.evaluation_inputs(), "input:simulation": native_circuit},
                            backends, tmp_path / "native", task_sha256=task.digest)
    assert native["outcome"] == "passed", native["jobs"]
    assert_characterization_unscored(native)
    check_measurements(native, tmp_path / "native", task)
    for job in simulations:
        for name, measurement in pre["jobs"][job["id"]]["measurements"].items():
            assert native["jobs"][job["id"]]["measurements"][name]["value"] == pytest.approx(
                measurement["value"], rel=1e-4, abs=1e-9)

    # Floating capacitive islands have no physical DC path. A numerical
    # shunt must stabilize their operating point without determining the
    # amplifier's performance. Test both sides of the declared conditioning.
    deck_role = simulations[0]["inputs"]["deck"]
    deck = task.evaluation_inputs()[deck_role].content.decode()
    nominal_shunt = float(re.search(r"\brshunt=(\S+)", deck).group(1))
    pex_asset = pex["outputs"]["netlist"]
    extracted = Asset((tmp_path / "post" / pex_asset["path"]).read_bytes(), "spice")
    for factor in (0.1, 10):
        varied_deck = Asset(re.sub(r"\brshunt=\S+", f"rshunt={nominal_shunt * factor:g}",
                                   deck, count=1).encode(), "spice")
        for label, baseline, circuit in (
                ("source", pre, task.evaluation_inputs()["input:simulation"]),
                ("post", post, extracted)):
            varied = run_evaluation(
                parse_evaluation(json.dumps(source).encode(), file_format="json"),
                {**task.evaluation_inputs(), deck_role: varied_deck, "input:simulation": circuit},
                backends, tmp_path / f"shunt-{factor:g}-{label}", task_sha256=task.digest)
            assert varied["outcome"] == "passed", varied["jobs"]
            for job in simulations:
                for name, measurement in baseline["jobs"][job["id"]]["measurements"].items():
                    assert varied["jobs"][job["id"]]["measurements"][name]["value"] == pytest.approx(
                        measurement["value"], rel=1e-4, abs=1e-9)


def mutate_witness(backends, operation):
    script = Asset(("from klayout import db\n"
                    "layout = db.Layout()\nlayout.read('witness.gds')\n"
                    "top = layout.top_cell()\n" + operation +
                    "\nlayout.write('mutated.gds')\n").encode(), "python")
    result = backends["layout.artifact"].tool.run(
        ["python", "mutate.py"], {"mutate.py": script,
                                 "witness.gds": witness_asset()},
        {"mutated.gds": "gds"})
    assert result.returncode == 0 and not result.reason, result.evidence
    return result.files["mutated.gds"]


@pytest.mark.acceptance_eda
def test_missing_input_label_cannot_receive_functional_success(environment, tmp_path):
    task, backends = environment
    candidate = mutate_witness(backends, """removed = 0
for cell in layout.each_cell():
    for layer in layout.layer_indexes():
        for shape in list(cell.shapes(layer).each()):
            if shape.is_text() and shape.text.string.upper() == 'INPUT':
                shape.delete()
                removed += 1
assert removed > 0
""")
    report = run_evaluation(task.evaluation, {"candidate": candidate, **task.evaluation_inputs()},
                            backends, tmp_path / "missing-input", task_sha256=task.digest)
    assert report["jobs"]["artifact"]["status"] == report["jobs"]["drc"]["status"] == "passed"
    assert report["task_success"] is not True
    assert report["jobs"]["parasitics"]["status"] in {"blocked", "error", "failed"}
    assert all(report["jobs"][job.id]["status"] == "blocked"
               for job in task.evaluation.jobs if job.stage == "simulate")
    assert_layout_score(report)
    assert report["score"]["value"] == 0


@pytest.mark.acceptance_eda
def test_swapped_supply_labels_fail_lvs_before_simulation(environment, tmp_path):
    task, backends = environment
    candidate = mutate_witness(backends, """changed = 0
for cell in layout.each_cell():
    for layer in layout.layer_indexes():
        for shape in cell.shapes(layer).each():
            if shape.is_text() and shape.text.string in ('VCC2V', 'VCC2V1'):
                label = shape.text
                label.string = {'VCC2V': 'VCC2V1', 'VCC2V1': 'VCC2V'}[label.string]
                shape.text = label
                changed += 1
assert changed == 2
""")
    report = run_evaluation(task.evaluation, {"candidate": candidate, **task.evaluation_inputs()},
                            backends, tmp_path / "swapped-supplies", task_sha256=task.digest)
    assert report["jobs"]["artifact"]["status"] == report["jobs"]["drc"]["status"] == "passed"
    assert report["jobs"]["lvs"]["status"] == "failed"
    assert report["jobs"]["parasitics"]["status"] == "blocked"
    assert report["task_success"] is False
    assert_layout_score(report)
    assert report["score"]["value"] == 0


@pytest.mark.acceptance_eda
def test_repeated_translated_candidate_preserves_decisions(environment, tmp_path):
    task, backends = environment
    original = witness_asset()
    translated = mutate_witness(backends,
                                "top.transform(db.Trans(round(13 / layout.dbu), round(17 / layout.dbu)))\n")
    reports = []
    for index, candidate in enumerate((original, original, translated)):
        report = run_evaluation(task.evaluation, {"candidate": candidate, **task.evaluation_inputs()},
                                backends, tmp_path / f"repeat-{index}", task_sha256=task.digest)
        assert report["task_success"] is True, report["jobs"]
        assert_layout_score(report)
        reports.append(report)
    for name in reports[0]["metrics"]:
        assert all(report["metrics"][name]["status"] == "passed" for report in reports)
        # Independent tool runs and grid-aligned translation retain electrical
        # decisions; allow extraction/simulator numerical rounding.
        for report in reports[1:]:
            assert report["metrics"][name]["value"] == pytest.approx(
                reports[0]["metrics"][name]["value"], rel=1e-3, abs=1e-9)
