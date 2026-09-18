"""One catalog traversal checks ownership, qualification and isolated inputs.

The loader owns plan schema and dependency validation; these checks add the
published case contract and SPICE interface evidence that it cannot infer.
"""

import hashlib
import re
from pathlib import Path

import pytest
import tomli_w
from helpers.case_config import standalone_config
from helpers.catalog import CATALOGS, read_catalog

from benchmarking.benchmark import load_benchmark, task_contract
from benchmarking.engine.prepare_support import load_profile
from benchmarking.tasks import _validate_case, load_task

pytestmark = pytest.mark.unit


def _logical_lines(raw):
    """Join SPICE continuation lines for the small top-level checks below."""
    logical = []
    for raw_line in raw.splitlines():
        line = raw_line.decode("utf-8", "replace").strip()
        if not line or line.startswith("*"):
            continue
        if line.startswith("+") and logical:
            logical[-1] += " " + line[1:].strip()
        else:
            logical.append(line)
    return logical


def _subckt_ports(raw, name):
    for line in _logical_lines(raw):
        fields = line.split()
        if len(fields) >= 2 and fields[0].lower() == ".subckt" and fields[1].lower() == name.lower():
            return fields[2:]
    return None


def _dut_argument_lists(raw, name):
    """Find top-level X instances of the authoritative DUT subcircuit."""
    calls = []
    for line in _logical_lines(raw):
        fields = line.split()
        if not fields or not re.fullmatch(r"x[^\s]*", fields[0], flags=re.IGNORECASE):
            continue
        matches = [index for index, field in enumerate(fields[1:], start=1)
                   if field.lower() == name.lower()]
        if matches:
            calls.append(fields[1:matches[0]])
    return calls


def _check_public_plan(config, data, task):
    assert task.hours == data["task"]["hours"] and task.wall_seconds > 0, config
    description = next(item.content.decode() for item in task.inputs if item.role == "description")
    published_hours = re.findall(r"Solve budget: \*\*([\d.]+) hours\*\*", description)
    assert len(published_hours) == 1 and float(published_hours[0]) == task.hours, config
    assert "coefficient" in data["task"], config
    plan = task.evaluation
    assert plan is not None and plan.mode == "post_layout", config
    assert plan.scoring.method == "layout-v2", config
    netlist = next(item for item in task.inputs if item.role == "netlist")
    ports = _subckt_ports(netlist.content, task.netlist_subcircuit)
    assert ports, config
    inputs = {f"input:{item.role}": item for item in task.inputs}
    for job in plan.jobs:
        if job.stage == "extract":
            assert [port.lower() for port in job.parameters["ports"]] == [port.lower() for port in ports], config
        if job.stage != "simulate":
            continue
        deck = inputs[dict(job.inputs)["deck"]]
        calls = _dut_argument_lists(deck.content, task.netlist_subcircuit)
        assert calls and all(len(call) == len(ports) for call in calls), (config, job.id)
        circuit_roles = [role for role, ref in job.inputs if ref.startswith("job:")]
        if circuit_roles:
            included = {line.split()[1].strip("\"'") for line in _logical_lines(deck.content)
                        if line.lower().startswith(".include ")}
            assert any(f"{role}.spice" in included for role in circuit_roles), (config, job.id)
    for item in task.inputs:
        declared = _subckt_ports(item.content, task.netlist_subcircuit)
        if item.role == "simulation" or declared is not None:
            assert declared == ports, (config, item.role)
    for backend in data["toolchain"]["backends"].values():
        for setting, profile in backend.get("support_profiles", {}).items():
            assert setting in backend["settings"], (config, setting)
            load_profile(f"{config.parents[3]}/pdk.toml#{profile}")


@pytest.mark.parametrize("path", CATALOGS, ids=lambda path: path.parent.name)
def test_catalog_owns_qualified_cases_and_only_declared_solver_inputs(path, tmp_path):
    catalog, configs = read_catalog(path)
    assert set(catalog) == {"schema_version", "cases"} and catalog["schema_version"] == 3
    assert configs and len({item["id"] for item in catalog["cases"]}) == len(configs)
    assert len({config for config, _ in configs}) == len(configs)
    assert set((path.parent / "cases").glob("*/case.toml")) == {config for config, _ in configs}
    assert (path.parent / "README.md").is_file()
    assert (path.parent / "LICENSE").read_bytes()
    for index, (entry, (config, data)) in enumerate(zip(catalog["cases"], configs, strict=True)):
        assert set(entry) == {"id", "config_path"} and entry["id"] == data["id"]
        assert config.name == "case.toml" and config.parent.parent == path.parent / "cases"
        if "task" not in data:
            _validate_case(data)
            assert data["status"] != "qualified", config
            continue
        task = load_task(config)  # Owns schema, digests, physical gates and extracted-DUT dependencies.
        _check_public_plan(config, data, task)
        inputs = data["task"]["inputs"]
        assert not {"license", "notice", "pex_scope"} & inputs.keys(), config
        assert not any(entry["path"].rsplit("/", 1)[-1] in {"LICENSE", "NOTICE"}
                       for entry in inputs.values()), config
        assert set(data["origin"]) == {"url"}
        declared = {"case.toml", "README.md"}
        declared.update(entry["path"] for entry in inputs.values()
                        if not entry.get("collection_source") and not entry.get("source"))
        assets = {entry["path"]: entry for entry in data.get("assets", [])}
        reference = data.get("qualification", {}).get("reference")
        if reference:
            assert task.witnessed and reference in assets, config
            assert assets[reference]["sha256"] not in {item.sha256 for item in task.inputs}, config
        for name, asset in assets.items():
            assert hashlib.sha256((config.parent / name).read_bytes()).hexdigest() == asset["sha256"]
        declared.update(assets)
        actual = {str(p.relative_to(config.parent)) for p in config.parent.rglob("*") if p.is_file()}
        assert actual == declared, (config, actual - declared, declared - actual)
        destination = tmp_path / str(index)
        task.materialize(destination)
        assert {p.relative_to(destination).as_posix() for p in destination.rglob("*") if p.is_file()} == {
            entry.path for entry in task.inputs
        }
        if reference:
            assert not (destination / reference).exists(), config
        copied = destination / "case.toml"
        copied.write_text(standalone_config(tomli_w.dumps(data)))
        standalone = load_task(copied)
        assert standalone.input_assets() == task.input_assets()
        assert task_contract(standalone) == task_contract(task)


def test_benchmark_selects_qualified_catalog_cases_across_processes():
    benchmark = load_benchmark(Path(__file__).resolve().parents[2] / "benchmark.toml")
    registered = {config for catalog in CATALOGS for config, _ in read_catalog(catalog)[1]}
    assert set(benchmark.configs) < registered
    assert len({config.parents[3] for config in benchmark.configs}) > 1
    benchmark.validate_tasks([load_task(config) for config in benchmark.configs])
