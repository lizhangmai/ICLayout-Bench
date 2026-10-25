"""Explicit Dataset delivery checks: declared files, interfaces and solver isolation.

Problem prose and engineering estimates are reviewed by Dataset authors. These
checks validate delivery contracts without imposing wording on problem.md.
"""

import hashlib
import re
import shlex

import pytest
import tomli_w
from helpers.case_config import standalone_config
from helpers.catalog import CASES, ROOT, read_case

from benchmarking.eda.resources.support import load_profile
from benchmarking.tasks.contract import load_task, task_contract
from benchmarking.tasks.dataset import case_location, process_manifest

pytestmark = pytest.mark.integration


def _logical_lines(raw):
    """Join SPICE '+' and Spectre backslash continuations for interface checks."""
    logical = []
    content = re.sub(r"\\[ \t]*\r?\n[ \t]*", " ", raw.decode("utf-8", "replace"))
    for raw_line in content.splitlines():
        line = raw_line.strip()
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


def _direct_dut_argument_lists(raw, name):
    """Find direct DUT subcircuit calls in a SPICE or Spectre scope."""
    calls = []
    for line in _logical_lines(raw):
        if line.startswith(("*", ";", "//")):
            continue
        native = re.fullmatch(r"\S+?\s*\(([^()]*)\)\s+" + re.escape(name) + r"(?:\s+.*)?",
                              line, flags=re.IGNORECASE)
        if native:
            calls.append(native[1].split())
            continue
        fields = line.split()
        if not fields or not re.fullmatch(r"x[^\s]*", fields[0], flags=re.IGNORECASE):
            continue
        matches = [index for index, field in enumerate(fields[1:], start=1)
                   if field.lower() == name.lower()]
        if matches:
            calls.append(fields[1:matches[0]])
    return calls


def _dut_argument_lists(raw, name, includes=None):
    """Follow reachable SPICE wrappers in explicitly bound include files."""
    includes = includes or {}
    top, definitions = [], {}

    def read(source, scope, active=()):
        scopes = [scope]
        for line in _logical_lines(source):
            fields = shlex.split(line)
            if not fields:
                continue
            keyword = fields[0].lower()
            if keyword in {'.include', 'include'} and len(fields) > 1:
                path = fields[1]
                if path in includes and path not in active:
                    read(includes[path], scopes[-1], (*active, path))
            elif keyword == '.subckt':
                body = []
                definitions[fields[1].lower()] = (fields[2:], body)
                scopes.append(body)
            elif keyword == '.ends':
                scopes.pop()
            else:
                scopes[-1].append(line)

    def visit(scope, active=()):
        source = '\n'.join(scope).encode()
        calls = _direct_dut_argument_lists(source, name)
        for wrapper, (ports, body) in definitions.items():
            if wrapper == name.lower() or wrapper in active:
                continue
            instances = _direct_dut_argument_lists(source, wrapper)
            if instances:
                assert all(len(args) == len(ports) for args in instances), f'Wrapper {wrapper} port count differs'
                calls.extend(visit(body, (*active, wrapper)))
        return calls

    read(raw, top)
    return visit(top)


@pytest.mark.parametrize("instance", [
    "XDUT a\n+ b example",
    "DUT (a \\\n b) example",
    "I7 (a b) example scale=1",
])
def test_catalog_dut_ports_cover_simulator_dialects(instance):
    raw = ("// I0 (wrong) example\n* XDUT wrong example\n"
           "XOTHER wrong other\n" + instance + "\n").encode()
    assert _dut_argument_lists(raw, "example") == [["a", "b"]]
    assert _dut_argument_lists(raw, "missing") == []


@pytest.mark.parametrize('deck,expected', [
    ('.include models.spice\nXTOP a b outer\n', [['P', 'N']]),
    ('.include models.spice\nXTOP a b unrelated\n', []),
    ('.include unavailable.spice\nXTOP a b outer\n', []),
])
def test_catalog_dut_ports_follow_only_included_reachable_wrappers(deck, expected):
    models = (b'.subckt outer A B\nXINNER A B inner\n.ends outer\n'
              b'.subckt inner P N\nXCORE P N example\n.ends inner\n')
    assert _dut_argument_lists(deck.encode(), 'example', {'models.spice': models}) == expected


def test_catalog_dut_ports_reject_wrong_wrapper_interface():
    models = b'.subckt outer A B\nXCORE A B example\n.ends outer\n'
    with pytest.raises(AssertionError, match='outer'):
        _dut_argument_lists(b'.include models.spice\nXTOP a outer\n', 'example',
                            {'models.spice': models})


def _check_case_interfaces(config, data, task):
    plan = task.evaluation
    assert plan is not None, config
    netlist = next(item for item in task.inputs if item.role == "netlist")
    ports = _subckt_ports(netlist.content, task.netlist_subcircuit)
    assert ports, config
    inputs = {f"input:{item.role}": item for item in (*task.inputs, *task.evaluator_inputs)}
    for job in plan.jobs:
        if job.stage == "extract":
            assert [port.lower() for port in job.parameters["ports"]] == [port.lower() for port in ports], config
        if job.stage != "simulate":
            continue
        deck = inputs[dict(job.inputs)["deck"]]
        includes = {f'{role}.spice': inputs[ref].content for role, ref in job.inputs
                    if ref.startswith('input:') and inputs[ref].format == 'spice'}
        calls = _dut_argument_lists(deck.content, task.netlist_subcircuit, includes)
        assert calls and all(len(call) == len(ports) for call in calls), (config, job.id)
        circuit_roles = [role for role, ref in job.inputs if ref.startswith("job:")]
        if circuit_roles:
            included = {shlex.split(line)[1] for line in _logical_lines(deck.content)
                        if re.match(r"\.?include\s+", line, flags=re.IGNORECASE)}
            assert any(f"{role}.spice" in included for role in circuit_roles), (config, job.id)
    for item in task.inputs:
        declared = _subckt_ports(item.content, task.netlist_subcircuit)
        if item.role == "simulation":
            # SPICE formal port names are local to the model. The simulator
            # representation is called positionally. Physical LVS checks the
            # named interface; author validation covers source/PEX equivalence.
            assert declared is not None and len(declared) == len(ports), (config, item.role)
        elif declared is not None:
            assert declared == ports, (config, item.role)
    for backend in data["toolchain"]["backends"].values():
        for setting, profile in backend.get("support_profiles", {}).items():
            assert setting in backend["settings"], (config, setting)
            load_profile(f"{process_manifest(config)}#{profile}")


@pytest.mark.parametrize("config", CASES, ids=lambda path: read_case(path)["id"])
@pytest.mark.skipif(not CASES, reason="Set ICLAYOUT_BENCH_DATASET to run dataset checks")
def test_catalog_case_owns_only_declared_solver_inputs(config, tmp_path):
    data = read_case(config)
    location = case_location(config)
    process, collection = location["process"], location["collection"]
    assert config.parents[3].name == process and config.parents[2].name == collection
    assert (ROOT / "tasks" / process / collection / "LICENSE").read_bytes()
    task = load_task(config)  # Owns schema, digests, physical gates and extracted-DUT dependencies.
    assert task.status == data["status"], config
    _check_case_interfaces(config, data, task)
    inputs = data["task"]["inputs"]
    assert not {"license", "notice", "pex_scope"} & inputs.keys(), config
    assert not any(entry["path"].rsplit("/", 1)[-1] in {"LICENSE", "NOTICE"}
                   for entry in inputs.values()), config
    assert set(data["origin"]) == {"url"}
    declared = {"case.toml"}
    declared.update(entry.get("source", entry["path"]) for entry in inputs.values())
    declared.update(item.path for item in task.evaluator_inputs)
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
    destination = tmp_path / "solver"
    task.materialize(destination)
    assert {p.relative_to(destination).as_posix() for p in destination.rglob("*") if p.is_file()} == {
        entry.path for entry in task.solver_inputs
    }
    assert all(not (destination / item.path).exists() for item in task.evaluator_inputs), config
    if reference:
        assert not (destination / reference).exists(), config
    standalone_directory = tmp_path / "standalone"
    standalone_directory.mkdir()
    for item in (*task.inputs, *task.evaluator_inputs):
        path = standalone_directory / item.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(item.content)
    copied = standalone_directory / "case.toml"
    copied.write_text(standalone_config(tomli_w.dumps(data)))
    standalone = load_task(copied)
    assert standalone.input_assets() == task.input_assets()
    assert task_contract(standalone) == task_contract(task)


# Native loading previously mistook provenance JSON for samples and failed to cast.
# Exercise the real HF reader against published tables; derive membership and
# hashes independently from the existing catalogs/contracts, never fixed counts.
@pytest.mark.skipif(not CASES, reason="Set ICLAYOUT_BENCH_DATASET to run dataset checks")
def test_native_huggingface_views_match_authoritative_cases(tmp_path):
    datasets = pytest.importorskip("datasets")
    files = {"test": str(ROOT / "data.parquet")}
    default = datasets.load_dataset(str(ROOT), data_files=files, cache_dir=str(tmp_path / "cache"))
    assert set(default) == {"test"}
    corpus = default["test"]
    if (ROOT / "README.md").is_file():
        # A supplied publication card also supports default HF discovery.
        inferred = datasets.load_dataset(str(ROOT), cache_dir=str(tmp_path / "cache"))
        assert set(inferred) == {"test"}
        assert inferred["test"].to_list() == corpus.to_list()
    core = corpus.filter(lambda row: row["in_core"])
    selected = {read_case(config)["id"] for config in CASES if read_case(config)["in_core"]}
    assert set(core["id"]) == selected
    declared = {data["id"]: (config, data)
                for config in CASES for data in [read_case(config)]}
    assert set(corpus["id"]) == set(declared)
    assert set(core["id"]) <= set(corpus["id"])
    for row in corpus:
        config, data = declared[row["id"]]
        assert type(row["in_core"]) is bool
        assert row["in_core"] == (row["id"] in selected)
        assert row["title"] == data["title"]
        presentation = data.get("presentation", {})
        assert row["category"] == presentation.get("category")
        assert row["summary"] == presentation.get("summary")
        assert row["source_url"] == data["origin"]["url"]
        assert ROOT / row["case_path"] == config
        assert row["case_sha256"] == hashlib.sha256(config.read_bytes()).hexdigest()
        assert row["problem"] == (ROOT / row["description_path"]).read_text()
        assert row["netlist_sha256"] == hashlib.sha256((ROOT / row["netlist_path"]).read_bytes()).hexdigest()
        assert (ROOT / row["description_path"]).is_file()
        assert (ROOT / row["license_path"]).is_file()
    # Participant selection must traverse the real native reader, including filters.
    from benchmarking.participants.batch.config import read_configs
    config = tmp_path / "participant.toml"
    base = 'harness="codex"\nmodel="fixture"\nefforts=["medium"]\nconcurrency=1\nrepetitions=1\n'
    source = f'\n[dataset]\nsource="{ROOT}"\nname="core"\nsplit="test"\n'
    config.write_text(base + source)
    plan = read_configs([config])[0]
    assert plan["tasks"] == [row["id"] for row in sorted(core, key=lambda row: row["core_order"])]
    assert plan["dataset"]["index_sha256"]
    config.write_text(base + f'tasks=["{core[0]["id"]}"]\n' + source)
    assert read_configs([config])[0]["tasks"] == [core[0]["id"]]
    config.write_text(base + 'tasks=["missing-case"]\n' + source)
    with pytest.raises(ValueError, match="must belong"):
        read_configs([config])
    config.write_text(base + source.replace('name="core"', 'name="all"'))
    assert read_configs([config])[0]["tasks"] == corpus["id"]
    streamed = datasets.load_dataset(str(ROOT), data_files=files, split="test", streaming=True,
                                    cache_dir=str(tmp_path / "cache"))
    assert [row["id"] for row in streamed if row["in_core"]] == core["id"]
