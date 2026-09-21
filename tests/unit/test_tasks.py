import hashlib
import json
import re
from pathlib import Path

import pytest

from benchmarking.tasks import load_task

pytestmark = pytest.mark.unit


@pytest.fixture
def package(tmp_path):
    files = {
        "input/spec.spice": b".subckt SYNTHETIC A B\n.ends\n",
        "input/constraints.json": b'{"hard": []}\n',
    }
    for path, content in files.items():
        file = tmp_path / path
        file.parent.mkdir(exist_ok=True)
        file.write_bytes(content)
    provenance = tmp_path / "provenance.json"
    provenance.write_text('{"note": "maintainer only"}\n')
    (tmp_path / "unlisted.txt").write_text("must not reach the solver")
    config = '''
id = "synthetic"
title = "Synthetic input preparation test"
kind = "netlist_to_gds"
family = "synthetic"
status = "candidate"
environment = "synthetic-tools"

[inputs.netlist]
path = "input/spec.spice"
sha256 = "NETLIST_HASH"
subcircuit = "SYNTHETIC"

[inputs.constraints]
path = "input/constraints.json"
sha256 = "CONSTRAINTS_HASH"

[provenance]
path = "provenance.json"
sha256 = "PROVENANCE_HASH"

[output]
path = "deliverables/chip.gds"
format = "gds"
top_cell = "SYNTHETIC"
max_bytes = 1048576
'''
    for placeholder, path in (
        ("NETLIST_HASH", "input/spec.spice"),
        ("CONSTRAINTS_HASH", "input/constraints.json"),
        ("PROVENANCE_HASH", "provenance.json"),
    ):
        config = config.replace(placeholder, hashlib.sha256((tmp_path / path).read_bytes()).hexdigest())
    path = tmp_path / "task.toml"
    path.write_text(config)
    return path


def replace(config: Path, before: str, after: str):
    config.write_text(config.read_text().replace(before, after))


def test_task_identity_tracks_published_coefficient_and_output(package):
    coefficient = 10
    original = load_task(package)
    replace(package, 'family = "synthetic"', f'family = "synthetic"\ncoefficient = {coefficient}')
    weighted = load_task(package)
    assert original.coefficient == 1
    assert weighted.coefficient == weighted.description()["coefficient"] == coefficient
    assert original.digest != weighted.digest
    replace(package, "deliverables/chip.gds", "output/final.gds")
    updated = load_task(package)
    assert weighted.digest != updated.digest
    assert updated.description()["output"]["path"] == "/workspace/output/final.gds"


@pytest.fixture
def inline_package(package):
    content = package.read_text()
    start = content.index("[inputs.constraints]")
    end = content.index("[provenance]", start)
    package.write_text(content[:start] + content[end:] + '''
[constraints]
[[constraints.hard]]
id = "outline"
type = "bbox_max"
functional_layers = [[1, 0]]
max_width_um = 7
max_height_um = 9
[[constraints.quality]]
id = "area"
type = "functional_bbox_area"
layers_from = "outline"
''')
    return package


def test_materialization_uses_validated_snapshot_and_configured_io(package, tmp_path):
    task = load_task(package)
    original = (tmp_path / "input/spec.spice").read_bytes()
    (tmp_path / "input/spec.spice").write_text("changed after loading")
    destination = tmp_path / "run-inputs"
    task.materialize(destination)
    assert (destination / "input/spec.spice").read_bytes() == original
    assert sorted(p.relative_to(destination).as_posix() for p in destination.rglob("*") if p.is_file()) == [
        "input/constraints.json", "input/spec.spice",
    ]
    description = task.description()
    assert description["inputs"]["netlist"] == "/task/input/spec.spice"
    assert description["output"]["path"] == "/workspace/deliverables/chip.gds"
    assert description["output"]["top_cell"] == "SYNTHETIC"
    assert description["netlist_subcircuit"] == "SYNTHETIC"
    assert "maintainer only" not in json.dumps(description)
    assert (destination / "input/spec.spice").stat().st_mode & 0o222 == 0
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_task(package)

    before = {p: p.read_bytes() for p in destination.rglob("*") if p.is_file()}
    with pytest.raises(FileExistsError):
        task.materialize(destination)
    assert before == {p: p.read_bytes() for p in destination.rglob("*") if p.is_file()}
    metadata = json.loads(task.evaluation_inputs()["task"].content)
    assert metadata["output"]["top_cell"] == description["output"]["top_cell"]
    assert metadata["netlist_subcircuit"] == description["netlist_subcircuit"]
    assert "provenance" not in metadata


def test_inline_constraints_are_frozen_and_shared_with_solver_and_evaluator(inline_package, tmp_path):
    add_evaluation(inline_package, reference="input:constraints")
    task = load_task(inline_package)
    frozen = task.evaluation_inputs()["input:constraints"]
    assert frozen.format == "json"
    expected = json.loads(frozen.content)
    assert expected["hard"][0]["max_width_um"] == 7
    assert task.description()["constraints"] == expected
    assert json.loads(task.evaluation_inputs()["task"].content)["constraints"] == expected
    assert "constraints" not in task.description()["inputs"]

    replace(inline_package, "max_width_um = 7", "max_width_um = 700")
    task.description()["constraints"]["hard"][0]["max_width_um"] = 900
    (tmp_path / "input/constraints.json").write_text("unused former file")
    assert task.evaluation_inputs()["input:constraints"] == frozen
    assert task.description()["constraints"] == expected
    assert load_task(inline_package).digest != task.digest
    destination = tmp_path / "solver-inputs"
    task.materialize(destination)
    assert {p.relative_to(destination).as_posix() for p in destination.rglob("*") if p.is_file()} == {
        "input/spec.spice", "evaluation/plan.toml", "evaluation/testbench.spice",
    }


def test_constraints_must_have_one_authoritative_source(inline_package):
    content = inline_package.read_text()
    inline_package.write_text(content[:content.index("[constraints]")])
    with pytest.raises(ValueError, match="exactly one"):
        load_task(inline_package)
    inline_package.write_text(content + '\n[inputs.constraints]\npath = "unused.json"\n')
    with pytest.raises(ValueError, match="exactly one"):
        load_task(inline_package)


def test_candidate_circuit_case_without_task_is_not_an_executable_task(circuit_case):
    with pytest.raises(ValueError, match="does not declare an executable task"):
        load_task(circuit_case)


def test_case_metadata_does_not_supply_solver_inputs(executable_case, tmp_path):
    task = load_task(executable_case)
    # Attribution may point to a source that differs from the maintained circuit.
    replace(executable_case, "https://example.invalid/synthetic-circuit",
            "https://example.invalid/another-source")
    executable_case.write_text(executable_case.read_text()
                               + '\n[presentation]\ncategory="Fixture"\nsummary="Browsing only"\n')
    updated = load_task(executable_case)
    assert updated.digest != task.digest
    assert updated.inputs == task.inputs
    assert "origin" not in updated.description()
    assert "presentation" not in updated.description()
    destination = tmp_path / "delivered"
    updated.materialize(destination)
    assert {p.relative_to(destination).as_posix(): p.read_bytes()
            for p in destination.rglob("*") if p.is_file()} == {
        item.path: item.content for item in task.inputs
    }


def test_qualification_reference_cannot_escape_the_case(circuit_case):
    circuit_case.write_text(circuit_case.read_text()
                            + '\n[qualification]\nreference = "../witness.gds"\n')
    with pytest.raises(ValueError, match="relative POSIX"):
        load_task(circuit_case)

def test_witness_flag_follows_the_qualification_reference(executable_case, tmp_path):
    case = executable_case
    assert load_task(case).witnessed is False
    description = load_task(case).description()
    assert description["witnessed"] is False
    case.write_text(case.read_text() + '\n[qualification]\n')
    assert load_task(case).witnessed is False
    case.write_text(case.read_text() + 'reference = "reference.gds"\n')
    assert load_task(case).witnessed is True
    assert load_task(case).description()["witnessed"] is True


@pytest.mark.parametrize("path", [
    "../escape.gds",
    "/absolute.gds",
])
def test_unsafe_output_path_is_rejected(package, path):
    replace(package, '"deliverables/chip.gds"', json.dumps(path))
    with pytest.raises(ValueError, match="relative POSIX"):
        load_task(package)


def test_symlinked_input_is_rejected(package, tmp_path):
    original = tmp_path / "input/spec.spice"
    original.rename(tmp_path / "source.spice")
    original.symlink_to(tmp_path / "source.spice")
    with pytest.raises(ValueError, match="non-symlink"):
        load_task(package)


def add_evaluation(package, *, reference="input:netlist", inline=False):
    root = package.parent
    plan = f'''
mode = "characterization"
[[jobs]]
id = "dc"
stage = "simulate"
operation = "circuit.measure"
inputs = {{ dut = "{reference}", deck = "input:testbench" }}
[[metrics]]
id = "gain"
category = "performance"
observations = ["dc:gain"]
unit = "1"
direction = "maximize"
aggregation = "min"
lower = 1.0
'''
    files = {"evaluation": ("evaluation/plan.toml", plan, "toml"),
             "testbench": ("evaluation/testbench.spice", "* generic testbench", "spice")}
    if inline:
        del files["evaluation"]
    additions = ""
    for role, (relative, contents, file_format) in files.items():
        path = root / relative
        path.parent.mkdir(exist_ok=True)
        path.write_text(contents)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        additions += f'\n[inputs.{role}]\npath = "{relative}"\nsha256 = "{digest}"\nformat = "{file_format}"\n'
    if inline:
        additions += '\n[evaluation]\n' + re.sub(r'^(\[+)(?=[A-Za-z])', r'\1evaluation.', plan, flags=re.MULTILINE)
    package.write_text(package.read_text() + additions)


def test_evaluation_and_arbitrary_named_testbenches_are_frozen_inputs(package, tmp_path):
    add_evaluation(package)
    task = load_task(package)
    assert task.evaluation.jobs[0].operation == "circuit.measure"
    assert task.evaluation_inputs()["input:testbench"].format == "spice"
    before = task.evaluation.sha256
    (tmp_path / "evaluation/plan.toml").write_text("changed after loading")
    destination = tmp_path / "prepared"
    task.materialize(destination)
    assert hashlib.sha256((destination / "evaluation/plan.toml").read_bytes()).hexdigest() == before
    assert task.description()["evaluation"]["metrics"][0]["id"] == "gain"
    assert not (destination / "provenance.json").exists()


def test_evaluation_cannot_reference_an_undeclared_input(package):
    inline = True
    add_evaluation(package, reference="input:private_reference", inline=inline)
    with pytest.raises(ValueError, match="undeclared task input"):
        load_task(package)


def test_inline_evaluation_freezes_public_rules_without_an_extra_solver_file(package, tmp_path):
    add_evaluation(package, inline=True)
    task = load_task(package)
    frozen = task.input_assets()["evaluation"]
    assert frozen.format == "json"
    assert task.evaluation.metrics[0].lower == 1.0
    assert json.loads(frozen.content) == task.description()["evaluation"]
    assert task.evaluation_inputs()["input:evaluation"] == frozen
    assert "evaluation" not in task.description()["inputs"]

    replace(package, "lower = 1.0", "lower = 700.0")
    task.description()["evaluation"]["metrics"][0]["lower"] = 900.0
    assert task.description()["evaluation"]["metrics"][0]["lower"] == 1.0
    assert task.input_assets()["evaluation"] == frozen
    assert load_task(package).digest != task.digest
    destination = tmp_path / "solver-inputs"
    task.materialize(destination)
    assert {p.relative_to(destination).as_posix() for p in destination.rglob("*") if p.is_file()} == {
        "input/spec.spice", "input/constraints.json", "evaluation/testbench.spice",
    }
    assert "maintainer only" not in json.dumps(task.description())

    package.write_text(package.read_text() + '\n[inputs.evaluation]\npath = "unused.toml"\n')
    with pytest.raises(ValueError, match="at most one"):
        load_task(package)


def test_task_budget_is_published_frozen_and_service_owned(package):
    hours = 0.5
    from benchmarking.service.server import session_limits
    original = load_task(package)
    with pytest.raises(ValueError, match='hours'):
        session_limits(original)
    replace(package, 'family = "synthetic"', f'family = "synthetic"\nhours = {hours}')
    task = load_task(package)
    assert task.digest != original.digest
    assert task.description()['hours'] == hours
    assert session_limits(task)['wall_seconds'] == hours * 3600
    with pytest.raises(ValueError, match='override'):
        session_limits(task, task.wall_seconds + 1)

    replace(package, f"hours = {hours}", "hours = 0")
    with pytest.raises(ValueError, match="hours"):
        load_task(package)
