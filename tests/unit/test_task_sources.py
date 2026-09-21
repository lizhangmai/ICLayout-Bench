"""Case-local source files remain bounded, digest-bound, isolated input snapshots."""

import hashlib
import json
import tomllib

import pytest
import tomli_w

from benchmarking.tasks import load_task

pytestmark = pytest.mark.unit


@pytest.fixture
def shared_case(tmp_path, circuit_case):
    collection = tmp_path / "tasks/fixture.public.first"
    case = collection / "case.toml"
    case.parent.mkdir(parents=True)
    (collection / "LICENSE").write_bytes(b"Synthetic shared terms\n")
    (collection / "private.txt").write_text("Undeclared collection neighbor")
    netlist = b".subckt TEST A B\n.ends\n"
    (case.parent / "circuit.spice").write_bytes(netlist)
    data = tomllib.loads(circuit_case.read_text())
    data["task"] = {
        "kind": "netlist_to_gds", "family": "synthetic", "environment": "no-tools",
        "inputs": {
            "netlist": {"path": "circuit.spice", "sha256": hashlib.sha256(netlist).hexdigest(),
                        "subcircuit": "TEST"},
            "license": {"path": "materials/LICENSE", "source": "LICENSE",
                        "sha256": hashlib.sha256((collection / "LICENSE").read_bytes()).hexdigest()},
        },
        "constraints": {"hard": []},
        "output": {"path": "output/final.gds", "format": "gds", "top_cell": "TEST", "max_bytes": 1024},
    }
    case.write_text(tomli_w.dumps(data))
    return case, collection


def change_license(case, **updates):
    data = tomllib.loads(case.read_text())
    data["task"]["inputs"]["license"].update(updates)
    case.write_text(tomli_w.dumps(data))


def test_case_inputs_are_frozen_and_materialized_without_neighbors(shared_case, tmp_path):
    case, collection = shared_case
    original = (collection / "LICENSE").read_bytes()
    tasks = [load_task(case)]
    (collection / "LICENSE").write_text("Changed after loading")
    for number, task in enumerate(tasks):
        output = tmp_path / f"materialized-{number}"
        task.materialize(output)
        assert (output / "materials/LICENSE").read_bytes() == original
        assert {p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()} == {
            entry.path for entry in task.inputs
        }
        assert "LICENSE" not in json.dumps(task.description().get("provenance"))
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_task(case)


def test_source_cannot_escape_the_case(shared_case):
    source = "../LICENSE"
    case, _ = shared_case
    change_license(case, source=source)
    with pytest.raises(ValueError):
        load_task(case)


def test_case_inputs_reject_source_symlinks(shared_case, tmp_path):
    case, directory = shared_case
    original = directory / "LICENSE"
    original.rename(tmp_path / "LICENSE")
    original.symlink_to(tmp_path / "LICENSE")
    with pytest.raises(ValueError):
        load_task(case)
