"""Catalogs agree with case declarations without freezing today's inventory."""

import pytest
from helpers.catalog import CATALOGS, read_catalog

from benchmarking.tasks import _validate_case, load_task

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("path", CATALOGS, ids=lambda path: path.parent.name)
def test_catalog_and_case_declarations_are_consistent(path):
    catalog, configs = read_catalog(path)
    assert set(catalog) == {"schema_version", "cases"}
    assert catalog["schema_version"] == 3
    assert catalog["cases"], "A published catalog must contain cases"
    assert len({item["id"] for item in catalog["cases"]}) == len(configs)
    assert len({config for config, _ in configs}) == len(configs)
    # One circuit per directory is the public organization convention.
    assert all(config.name == "case.toml" and config.parent.parent == path.parent / "cases"
               for config, _ in configs)
    assert set((path.parent / "cases").glob("*/case.toml")) == {config for config, _ in configs}
    for entry, (config, data) in zip(catalog["cases"], configs, strict=True):
        assert set(entry) == {"id", "config_path"}
        _validate_case(data)
        assert entry["id"] == data["id"]
        if "task" in data:
            load_task(config)  # Checks declared input digests and plan references.


@pytest.mark.parametrize("path", CATALOGS, ids=lambda path: path.parent.name)
def test_public_case_files_have_declared_owners_and_standalone_inputs(path, tmp_path):
    """Catch orphan materials/references and non-standalone solve inputs."""
    import hashlib

    import tomli_w
    from helpers.case_config import standalone_config

    assert (path.parent / "README.md").is_file()
    assert (path.parent / "LICENSE").read_bytes(), "Collection distributions retain their terms"
    for index, (config, data) in enumerate(read_catalog(path)[1]):
        if "task" not in data:
            continue
        inputs = data["task"]["inputs"]
        # Distribution metadata must not enter the isolated solve directory.
        assert not {"license", "notice", "pex_scope"} & inputs.keys(), config
        assert not any(entry["path"].rsplit("/", 1)[-1] in {"LICENSE", "NOTICE"}
                       for entry in inputs.values()), config
        assert set(data["origin"]) == {"url"}
        assert inputs["performance"]["path"] == "materials/testbench.spice"
        assert inputs["netlist"]["path"].startswith("materials/circuit.")
        declared = {"case.toml", "README.md"}
        declared.update(entry["path"] for entry in inputs.values()
                        if not entry.get("collection_source") and not entry.get("source"))
        assets = {entry["path"]: entry for entry in data.get("assets", [])}
        reference = data.get("qualification", {}).get("reference")
        if reference:
            assert reference in assets, config
        for name, entry in assets.items():
            assert hashlib.sha256((config.parent / name).read_bytes()).hexdigest() == entry["sha256"]
        declared.update(assets)
        actual = {str(p.relative_to(config.parent)) for p in config.parent.rglob("*") if p.is_file()}
        assert actual == declared, (config, actual - declared, declared - actual)
        task = load_task(config)
        destination = tmp_path / str(index)
        task.materialize(destination)
        assert {p.relative_to(destination).as_posix() for p in destination.rglob("*") if p.is_file()} == {
            entry.path for entry in task.inputs
        }
        copied = destination / "case.toml"
        copied.write_text(standalone_config(tomli_w.dumps(data)))
        standalone = load_task(copied)
        assert standalone.input_assets() == task.input_assets()
        from benchmarking.benchmark import task_contract
        assert task_contract(standalone) == task_contract(task)


def test_benchmark_selects_qualified_catalog_cases_across_processes():
    from pathlib import Path

    from benchmarking.benchmark import load_benchmark

    benchmark = load_benchmark(Path(__file__).resolve().parents[2] / "benchmark.toml")
    registered = {config for catalog in CATALOGS for config, _ in read_catalog(catalog)[1]}
    assert set(benchmark.configs) < registered
    assert len({config.parents[3] for config in benchmark.configs}) > 1
    benchmark.validate_tasks([load_task(config) for config in benchmark.configs])
