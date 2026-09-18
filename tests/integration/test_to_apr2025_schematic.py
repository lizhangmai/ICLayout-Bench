"""The maintained design_1 circuit: maintained netlists, physical checks and function.

Requires the PDK checkout and tools image. The separate functional suite
checks same-condition source/post-layout calibration; no 130 GHz claim is made.
"""

import json
import os
import struct
import tomllib
from pathlib import Path

import pytest
from helpers.stimuli import command, number

from benchmarking.engine.docker import DockerTool
from benchmarking.engine.evaluate import run_evaluation
from benchmarking.engine.klayout import KLayoutDocker
from benchmarking.engine.ngspice import NgspiceDocker
from benchmarking.engine.prepare_support import prepare_support
from benchmarking.evaluation import parse_evaluation
from benchmarking.files import Asset

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
PUBLIC_ROOT = ROOT
CASE = PUBLIC_ROOT / "tasks/ihp-sg13g2/TO_Apr2025/cases/DC_to_130_GHz_TIA.design_1"
TOP = "FMD_QNC_03a_TIA_1"
PORTS = ["INPUT", "OUTPUT", "VCC2V", "VCC2V1", "VEE"]


@pytest.fixture(scope="module")
def context(tmp_path_factory):
    directory = tmp_path_factory.mktemp("to-derived")
    config = tomllib.loads((CASE / "case.toml").read_text())
    image = os.environ.get("ICLAYOUT_BENCH_TEST_IMAGE", "iclayout-bench-tools:local")
    for name in ("klayout", "magic", "hbt-models"):
        prepare_support(None, f"{PUBLIC_ROOT}/tasks/ihp-sg13g2/pdk.toml#{name}",
                        directory / name, compiler_image=image)
    for entry in config["assets"]:
        assert Asset((CASE / entry["path"]).read_bytes(), entry["format"]).sha256 == entry["sha256"]
    return config, image, directory


def test_core_operating_point_uses_real_hbt_resistor_and_capacitor_models(context, tmp_path):
    config, image, directory = context
    plan = parse_evaluation(json.dumps({"schema_version": 1, "mode": "characterization", "metrics": [],
        "jobs": [{"id": "op", "stage": "simulate", "operation": "circuit.simulate",
                  "inputs": {"deck": "input:deck", "circuit": "input:circuit"},
                  "outputs": {"waveform": "ngspice-raw"},
                  "parameters": {"measurements": {"input_bias": "V", "output_bias": "V",
                                 "supply1_current": "A", "supply2_current": "A"},
                                 "exports": {"waveform": "operating_point.raw"}}}],
    }).encode(), file_format="json")
    settings = {**config["toolchain"]["backends"]["simulation"]["settings"],
                "image": image, "support": str(directory / "hbt-models")}
    report = run_evaluation(plan, {
        "input:deck": Asset((CASE / "materials/testbench.spice").read_bytes(), "spice"),
        "input:circuit": Asset((CASE / "materials/circuit.spice").read_bytes(), "spice")},
        {"circuit.simulate": NgspiceDocker(**settings)}, tmp_path / "op")
    assert report["outcome"] == "passed", report["jobs"]["op"]["reason"]
    assert report["task_success"] is None
    job = report["jobs"]["op"]
    raw = (tmp_path / "op" / job["outputs"]["waveform"]["path"]).read_bytes()
    header, binary = raw.split(b"Binary:\n", 1)
    fields, variables = header.decode().split("Variables:\n", 1)
    assert "No. Points: 1" in fields and "Flags: real" in fields
    names = [line.split()[1] for line in variables.splitlines() if line.strip()]
    values = [v[0] for v in struct.iter_unpack("<d", binary)]
    waveform = dict(zip(names, values, strict=True))
    for name, expression in [("input_bias", "v(input)"), ("output_bias", "v(output)"),
                             ("supply1_current", "i(vcc1)"), ("supply2_current", "i(vcc2)")]:
        expected = waveform[expression] * (-1 if name.endswith("current") else 1)
        assert job["measurements"][name]["value"] == pytest.approx(expected, rel=1e-6)
    deck = (CASE / 'materials/testbench.spice').read_text()
    for supply in ['VCC1', 'VCC2']:
        assert waveform[f'v({supply.lower()})'] == pytest.approx(number(command(deck, supply)[-1]))
    # A connected, self-biased core draws current from both independent sources.
    # These are source smoke checks, not benchmark performance limits.
    assert waveform["i(vcc1)"] < 0 and waveform["i(vcc2)"] < 0


def test_complete_physical_proposal_passes_both_drc_decks_and_lvs(context, tmp_path):
    config, image, directory = context
    entry = next(a for a in config["assets"] if a["role"] == "unqualified-reference-layout")
    candidate = Asset((CASE / entry["path"]).read_bytes(), "gds")
    jobs, backends = [], {}
    for check in ("artifact", "drc", "lvs"):
        operation = "layout." + check
        inputs = {"layout": "candidate"}
        parameters = {"top_cell": TOP, "max_bytes": 67108864}
        if check == "lvs":
            inputs["netlist"] = "input:netlist"
            parameters["subcircuit"] = TOP
        jobs.append({"id": check, "stage": "check", "gate": check, "operation": operation,
                     "inputs": inputs, "parameters": parameters})
        binding = config["toolchain"]["bindings"][operation]
        settings = {**config["toolchain"]["backends"][binding]["settings"], "image": image}
        if check != "artifact":
            settings["support"] = str(directory / "klayout")
        if check == "lvs":
            # This archived physical-only proposal predates distinct supply
            # labels; only the final functional witness uses strict ports.
            settings["profile"] = "lvs-to-apr2025.json"
        backends[operation] = KLayoutDocker(**settings)
    plan = parse_evaluation(json.dumps({"schema_version": 1, "mode": "physical",
                                       "metrics": [], "jobs": jobs}).encode(), file_format="json")
    report = run_evaluation(plan, {"candidate": candidate,
        "input:netlist": Asset((CASE / "materials/circuit.cdl").read_bytes(), "spice")},
        backends, tmp_path / "physical")
    assert {name: job["status"] for name, job in report["jobs"].items()} == {
        "artifact": "passed", "drc": "passed", "lvs": "passed"}
    assert report["physical_valid"] is True and report["task_success"] is None
    # Both maintained decks must complete with empty native report databases.
    import xml.etree.ElementTree as ET
    evidence = report["jobs"]["drc"]["evidence"]
    for name in ("report.db", "report-1.db"):
        native_report = ET.fromstring((tmp_path / "physical" / evidence[name]["path"]).read_bytes())
        assert not native_report.findall("./items/item")
    native = report["jobs"]["lvs"]["evidence"]["report.db"]
    script = """import json, klayout.db as k
n=k.LayoutVsSchematic();n.read('report.lvsdb');x=n.xref()
c=next(x.each_circuit_pair());assert str(c.status())=='Match'
result={p.second().name:str(p.status()) for p in x.each_device_pair(c) if p.second()}
open('pairs.json','w').write(json.dumps(result))
"""
    result = DockerTool(image, ["klayout", "-v"], 60).run(
        ["python", "pairs.py"], {"pairs.py": Asset(script.encode(), "python"),
         "report.lvsdb": Asset((tmp_path / "physical" / native["path"]).read_bytes(), "lvsdb")},
        {"pairs.json": "json"})
    assert result.returncode == 0 and not result.reason
    pairs = json.loads(result.files['pairs.json'].content)
    assert pairs and all(status == 'Match' for status in pairs.values())


def test_executable_task_accepts_its_witness(context, tmp_path):
    """The frozen task passes its own witness with the full scoring plan."""
    from benchmarking.tasks import load_task
    task = load_task(CASE / "case.toml")
    assert task.status == "qualified" and task.witnessed is True
    entry = next(a for a in context[0]["assets"] if a["role"] == "physical-witness")
    witness = Asset((CASE / entry["path"]).read_bytes(), "gds")
    assert witness.sha256 == entry["sha256"]
    report = run_evaluation(task.evaluation,
                            {"candidate": witness, **task.evaluation_inputs()},
                            _task_backends(context, tmp_path), tmp_path / "witness",
                            task_sha256=task.digest, task_witnessed=task.witnessed)
    assert report["outcome"] == "passed" and report["physical_valid"] is True
    assert report["task_success"] is report["specs_pass"] is True
    assert all(job["status"] == "passed" for job in report["jobs"].values())
    # 695.6 x 835.6 um is the evaluator's merged functional bounding box.



def test_executable_task_rejects_a_rotated_witness(context, tmp_path):
    """A 90-degree rotation breaks the LVS interface and blocks downstream checks."""
    config, image, _ = context
    entry = next(a for a in config["assets"] if a["role"] == "physical-witness")
    witness = Asset((CASE / entry["path"]).read_bytes(), "gds")
    script = Asset(b'''from klayout import db
layout = db.Layout()
layout.read("w.gds")
layout.top_cell().transform(db.Trans(db.Trans.R90))
layout.write("rotated.gds")
''', "python")
    result = DockerTool(image, ["klayout", "-v"], 60).run(
        ["python", "rot.py"], {"rot.py": script, "w.gds": witness}, {"rotated.gds": "gds"})
    assert result.returncode == 0 and not result.reason, result.evidence
    from benchmarking.tasks import load_task
    task = load_task(CASE / "case.toml")
    report = run_evaluation(task.evaluation,
                            {"candidate": result.files["rotated.gds"], **task.evaluation_inputs()},
                            _task_backends(context, tmp_path), tmp_path / "rotated",
                            task_sha256=task.digest, task_witnessed=task.witnessed)
    assert report["outcome"] == "failed"
    assert report["jobs"]["artifact"]["status"] == "passed"
    assert report["jobs"]["lvs"]["status"] == "failed"
    assert report["jobs"]["geometry"]["status"] == "blocked"


def _task_backends(context, tmp_path):
    """Evaluator backends for the frozen task plan, using fresh support bundles."""
    from benchmarking.engine.toolchains import load_toolchain
    _, image, directory = context
    task_config = (CASE / "case.toml").read_text()
    for name in ("klayout", "magic"):
        task_config = task_config.replace(f"build/support/to-design1-{name}", str(directory / name))
    task_config = task_config.replace("build/support/to-design1-models", str(directory / "hbt-models"))
    task_config = task_config.replace("iclayout-bench-tools:local", image)
    path = tmp_path / "case-toolchain.toml"
    path.write_text(task_config)
    backends = load_toolchain(path)
    return backends
