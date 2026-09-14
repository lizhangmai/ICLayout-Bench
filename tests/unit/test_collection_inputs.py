"""Shared source files remain bounded, digest-bound, isolated input snapshots."""

import hashlib
import json
import shutil
import tomllib

import pytest
import tomli_w

from benchmarking.tasks import load_task

pytestmark = pytest.mark.unit


@pytest.fixture
def shared_case(tmp_path, circuit_case):
    collection = tmp_path / "collection"
    case = collection / "cases/first/case.toml"
    case.parent.mkdir(parents=True)
    (collection / "catalog.toml").write_text('schema_version = 3\n')
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
            "license": {"path": "materials/LICENSE", "collection_source": "LICENSE",
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


def test_shared_inputs_are_frozen_and_materialized_without_neighbors(shared_case, tmp_path):
    case, collection = shared_case
    second = collection / "cases/second"
    shutil.copytree(case.parent, second)
    original = (collection / "LICENSE").read_bytes()
    tasks = [load_task(path) for path in [case, second / "case.toml"]]
    (collection / "LICENSE").write_text("Changed after loading")
    for number, task in enumerate(tasks):
        output = tmp_path / f"materialized-{number}"
        task.materialize(output)
        assert (output / "materials/LICENSE").read_bytes() == original
        assert {p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()} == {
            entry.path for entry in task.inputs
        }
        assert "collection_source" not in json.dumps(task.description())
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_task(case)


@pytest.mark.parametrize("source", ["../LICENSE", "/LICENSE", "nested/../../LICENSE", "x\\LICENSE", "./LICENSE", ""])
def test_collection_paths_cannot_escape_or_use_noncanonical_names(shared_case, source):
    case, _ = shared_case
    change_license(case, collection_source=source)
    with pytest.raises(ValueError):
        load_task(case)


@pytest.mark.parametrize("kind", ["file-symlink", "directory-symlink", "directory", "missing", "catalog-symlink"])
def test_collection_inputs_require_regular_files_and_root(shared_case, tmp_path, kind):
    case, collection = shared_case
    external = tmp_path / "external"
    external.mkdir()
    (external / "LICENSE").write_bytes((collection / "LICENSE").read_bytes())
    if kind == "file-symlink":
        (collection / "LICENSE").unlink()
        (collection / "LICENSE").symlink_to(external / "LICENSE")
    elif kind == "directory-symlink":
        (collection / "linked").symlink_to(external, target_is_directory=True)
        change_license(case, collection_source="linked/LICENSE")
    elif kind == "catalog-symlink":
        (collection / "catalog.toml").rename(external / "catalog.toml")
        (collection / "catalog.toml").symlink_to(external / "catalog.toml")
    else:
        (collection / "LICENSE").unlink()
        if kind == "directory":
            (collection / "LICENSE").mkdir()
    with pytest.raises((ValueError, FileNotFoundError)):
        load_task(case)


def test_shared_inputs_reject_ambiguous_source(shared_case):
    case, _ = shared_case
    change_license(case, source="circuit.spice")
    with pytest.raises(ValueError, match="at most one"):
        load_task(case)


def test_shared_inputs_require_collection_layout(shared_case, tmp_path):
    case, _ = shared_case
    destination = tmp_path / "loose"
    shutil.copytree(case.parent, destination)
    with pytest.raises(ValueError, match="requires <collection>"):
        load_task(destination / "case.toml")


def test_standalone_task_cannot_infer_collection_source(shared_case):
    case, _ = shared_case
    data = tomllib.loads(case.read_text())
    standalone = {**data["task"], "schema_version": 1,
                  **{name: data[name] for name in ["id", "title", "status"]}}
    case.write_text(tomli_w.dumps(standalone))
    with pytest.raises(ValueError, match="requires <collection>"):
        load_task(case)
