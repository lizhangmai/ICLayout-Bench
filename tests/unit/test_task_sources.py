"""Case-local source files remain bounded, digest-bound, isolated input snapshots."""

import hashlib
import json
import tomllib

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import tomli_w

from benchmarking.tasks.contract import load_task
from benchmarking.tasks.dataset import Dataset, select_core

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


@pytest.mark.parametrize("card_split", [None, "test", "validation"])
@pytest.mark.parametrize("ordered", [False, True])
def test_native_static_index_with_and_without_dataset_card(tmp_path, card_split, ordered):
    evaluation = tmp_path / "evaluation"
    evaluation.mkdir()
    (evaluation / "source.cdl").write_text(".subckt fixture a b\n.ends\n")
    process = tmp_path / "tasks/fixture"
    process.mkdir(parents=True)
    pdk = process / "pdk.toml"
    pdk.write_text('[source]\nname = "fixture"\n')
    source_rows, source_cases = [], {}
    for position, case_id in enumerate(("example", "zebra")):
        case = process / f"collection/cases/{case_id}/case.toml"
        case.parent.mkdir(parents=True)
        config = {"id": case_id, "in_core": True, "status": "qualified",
                  "task": {"evaluation": {"mode": "post_layout", "scoring": {"method": "layout"}}}}
        row = {"id": case_id, "in_core": True,
               "case_path": case.relative_to(tmp_path).as_posix(),
               "pdk_path": pdk.relative_to(tmp_path).as_posix(),
               "pdk_sha256": hashlib.sha256(pdk.read_bytes()).hexdigest()}
        if ordered:
            config["core_order"] = row["core_order"] = 2 - position
        case.write_text(tomli_w.dumps(config))
        row["case_sha256"] = hashlib.sha256(case.read_bytes()).hexdigest()
        source_rows.append(row)
        source_cases[case_id] = case
    name = "data.parquet"

    def write_index():
        pq.write_table(pa.Table.from_pylist(source_rows), tmp_path / name)

    write_index()
    if card_split:
        (tmp_path / "README.md").write_text(
            "---\nconfigs:\n- config_name: default\n  data_files:\n"
            f"  - split: {card_split}\n    path: {name}\n---\n")
    dataset = Dataset(tmp_path, {})
    for selection in ("all", "core"):
        rows, cases = dataset.native_cases(selection, card_split or "test")
        expected = ["zebra", "example"] if ordered and selection == "core" else ["example", "zebra"]
        assert rows["id"] == expected
        assert list(cases) == expected
        assert cases == source_cases
    if ordered:
        # Matching rows/contracts still cannot declare duplicate dispatch positions.
        case = source_cases["example"]
        import tomllib

        config = tomllib.loads(case.read_text())
        config["core_order"] = source_rows[0]["core_order"] = 1
        case.write_text(tomli_w.dumps(config))
        source_rows[0]["case_sha256"] = hashlib.sha256(case.read_bytes()).hexdigest()
        write_index()
        with pytest.raises(ValueError, match="unique core_order"):
            dataset.native_cases("core", card_split or "test")
    # Loading without a card must retain the normal contract-integrity checks.
    case = source_cases["example"]
    case.write_text(case.read_text() + '\ntitle = "changed"\n')
    with pytest.raises(ValueError, match="stale case digest"):
        dataset.native_cases("all", card_split or "test")


@pytest.mark.parametrize("orders", [(1, 1), (1, None), (0, 2), (True, 2)])
def test_core_order_rejects_ambiguous_or_invalid_positions(orders):
    rows = [{"id": name, "in_core": True, "core_order": order}
            for name, order in zip(("example", "zebra"), orders, strict=True)]
    with pytest.raises(ValueError, match="core_order"):
        select_core(rows)
