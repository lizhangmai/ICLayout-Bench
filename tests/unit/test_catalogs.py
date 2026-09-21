"""One catalog traversal checks ownership, qualification and isolated inputs.

The loader owns plan schema and dependency validation; these checks add the
published case contract and SPICE interface evidence that it cannot infer.
"""

import hashlib
import json
import math
import re

import pytest
import tomli_w
from helpers.case_config import standalone_config
from helpers.catalog import CASES, ROOT, read_case

from benchmarking.dataset import case_location, process_manifest
from benchmarking.engine.prepare_support import load_profile
from benchmarking.evaluation import SCORING_METHOD
from benchmarking.tasks import load_task, task_contract

pytestmark = [pytest.mark.unit, pytest.mark.skipif(not CASES, reason="Set ICLAYOUT_BENCH_DATASET to run dataset checks")]


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
    assert plan.scoring.method == SCORING_METHOD, config
    published_weights = {key: float(value) for key, value in re.findall(
        r"^\| `([^`]+)` \| ([0-9.eE+-]+) \|$", description, re.MULTILINE)}
    assert published_weights == dict(plan.scoring.weights), config
    assert plan.scoring.rationale in description, config
    # The published envelope calculation must reproduce its frozen anchor.
    # Evaluate the documented expression, rather than restating its coefficients;
    # the displayed envelope sum is rounded, so allow one final 0.01 um2 bin.
    envelope = re.search(r"sum of device/contact envelopes ([\d.]+) um2", description)
    if envelope:
        margin = re.search(r"total outer width/height allowance ([\d.]+) um", description)
        formula = re.search(r"Estimate = (.*?)\. Here", description)
        anchor = re.search(r"Area reference: \*\*([\d.]+) um2\*\*", description)
        assert margin and formula and anchor, config
        expression = formula[1]
        assert set(re.findall(r"[A-Za-z_]\w*", expression)) <= {
            "ceil", "sqrt", "envelope_sum", "margin"}, config
        assert re.fullmatch(r"[\w\s.+*/^()-]+", expression), config
        calculated = eval(expression.replace("^", "**"), {"__builtins__": {}}, {
            "ceil": math.ceil, "sqrt": math.sqrt,
            "envelope_sum": float(envelope[1]), "margin": float(margin[1])})
        assert abs(calculated - float(anchor[1])) <= 0.010001, config
        assert float(anchor[1]) == plan.scoring.area_target, config
    # A job/measurement identifier or dimension alone does not define a metric.
    for line in description.splitlines():
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) in {6, 7} and cells[0].startswith("`"):
            assert cells[1].strip("`") not in {"response", "bias", "supply"}, config
            assert not re.fullmatch(r"\w+:\w+(?:, \w+:\w+)*", cells[1]), config
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
            load_profile(f"{process_manifest(config)}#{profile}")


@pytest.mark.parametrize("config", CASES, ids=lambda path: path.parent.name)
def test_published_case_owns_only_declared_solver_inputs(config, tmp_path):
    data = read_case(config)
    location = case_location(config)
    process, collection = location["process"], location["collection"]
    assert config.parents[3].name == process and config.parents[2].name == collection
    assert (ROOT / "tasks" / process / collection / "LICENSE").read_bytes()
    assert data["status"] == "qualified"
    task = load_task(config)  # Owns schema, digests, physical gates and extracted-DUT dependencies.
    _check_public_plan(config, data, task)
    inputs = data["task"]["inputs"]
    assert not {"license", "notice", "pex_scope"} & inputs.keys(), config
    assert not any(entry["path"].rsplit("/", 1)[-1] in {"LICENSE", "NOTICE"}
                   for entry in inputs.values()), config
    assert set(data["origin"]) == {"url"}
    declared = {"case.toml"}
    declared.update(entry["path"] for entry in inputs.values()
                    if not entry.get("source"))
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
        entry.path for entry in task.inputs
    }
    if reference:
        assert not (destination / reference).exists(), config
    copied = destination / "case.toml"
    copied.write_text(standalone_config(tomli_w.dumps(data)))
    standalone = load_task(copied)
    assert standalone.input_assets() == task.input_assets()
    assert task_contract(standalone) == task_contract(task)


# Native loading previously mistook provenance JSON for samples and failed to cast.
# Exercise the real HF reader against published tables; derive membership and
# hashes independently from the existing catalogs/contracts, never fixed counts.
def test_native_huggingface_views_match_authoritative_cases(tmp_path):
    datasets = pytest.importorskip("datasets")
    from benchmarking.dataset_index import sync_index

    sync_index(ROOT, check=True)
    default = datasets.load_dataset(str(ROOT), cache_dir=str(tmp_path / "cache"))
    assert set(default) == {"test"}
    corpus = default["test"]
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
        assert row["category"] == data["presentation"]["category"]
        assert row["summary"] == data["presentation"]["summary"]
        assert row["source_url"] == data["origin"]["url"]
        assert ROOT / row["case_path"] == config
        assert row["case_sha256"] == hashlib.sha256(config.read_bytes()).hexdigest()
        assert row["problem"] == (ROOT / row["description_path"]).read_text()
        assert row["netlist_sha256"] == hashlib.sha256((ROOT / row["netlist_path"]).read_bytes()).hexdigest()
        assert (ROOT / row["description_path"]).is_file()
        assert (ROOT / row["license_path"]).is_file()
    # Participant selection must traverse the real native reader, including filters.
    from benchmarking.participants.config import read_configs
    config = tmp_path / "participant.toml"
    base = 'harness="codex"\nmodel="fixture"\nefforts=["medium"]\nconcurrency=1\nrepetitions=1\n'
    source = f'\n[dataset]\nsource="{ROOT}"\nname="core"\nsplit="test"\n'
    config.write_text(base + source)
    plan = read_configs([config])[0]
    assert plan["tasks"] == core["id"]
    assert plan["dataset"]["index_sha256"]
    config.write_text(base + f'tasks=["{core[0]["id"]}"]\n' + source)
    assert read_configs([config])[0]["tasks"] == [core[0]["id"]]
    config.write_text(base + 'tasks=["missing-case"]\n' + source)
    with pytest.raises(ValueError, match="must belong"):
        read_configs([config])
    config.write_text(base + source.replace('name="core"', 'name="all"'))
    assert read_configs([config])[0]["tasks"] == corpus["id"]
    streamed = datasets.load_dataset(str(ROOT), split="test", streaming=True,
                                    cache_dir=str(tmp_path / "cache"))
    assert [row["id"] for row in streamed if row["in_core"]] == core["id"]


def test_dataset_index_drift_is_detected_and_regenerated(tmp_path):
    import shutil

    from benchmarking.dataset_index import sync_index

    # Retain static assets to exercise index regeneration and publication together.
    root = tmp_path / "dataset"
    shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(
        ".git", ".agents", "build", ".cache"))
    original = (root / "data.jsonl").read_bytes()
    sync_index(root, check=True)
    config = next(config for config in sorted((root / "tasks").glob("*/*/cases/*/case.toml"))
                  if read_case(config)["in_core"])
    config.write_text(config.read_text().replace('title = "', 'title = "Changed ', 1))
    from benchmarking.dataset import load_dataset
    with pytest.raises(ValueError, match="stale case digest"):
        load_dataset(root).native_cases()
    with pytest.raises(ValueError, match="index is stale"):
        sync_index(root, check=True)
    assert (root / "data.jsonl").read_bytes() == original
    sync_index(root)
    assert (root / "data.jsonl").read_bytes() != original
    sync_index(root, check=True)
    # Loading the same local selection again must observe regenerated table bytes.
    rows, _ = load_dataset(root).native_cases()
    assert next(row for row in rows if row["case_path"] == config.relative_to(root).as_posix())["title"].startswith("Changed ")

    # Browsing text must read the declared source, not a solver destination path.
    import tomllib

    data = tomllib.loads(config.read_text())
    description = data["task"]["inputs"]["description"]
    original_problem = (config.parent / description["path"]).read_text()
    description["source"] = description["path"]
    description["path"] = "solver-problem.md"
    config.write_text(tomli_w.dumps(data))
    sync_index(root)
    row = next(json.loads(line) for line in (root / "data.jsonl").read_text().splitlines()
               if json.loads(line)["id"] == data["id"])
    assert row["problem"] == original_problem
    assert (root / row["description_path"]).read_text() == original_problem

    # Reselecting the benchmark must leave the complete corpus and its assets intact.
    corpus_before = (root / "data.jsonl").read_bytes()
    assets_before = {path.relative_to(root): hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in (root / "tasks").rglob("*") if path.is_file()}
    selected = []
    for path in sorted((root / "tasks").glob("*/*/cases/*/case.toml")):
        case = read_case(path)
        case["in_core"] = not case["in_core"]
        if case["in_core"]:
            selected.append(case["id"])
        path.write_text(tomli_w.dumps(case))
    selected.sort()
    with pytest.raises(ValueError, match="stale core membership"):
        load_dataset(root).native_cases()
    sync_index(root)
    after = [json.loads(line) for line in (root / "data.jsonl").read_text().splitlines()]
    before = [json.loads(line) for line in corpus_before.splitlines()]
    assert [row["id"] for row in after if row["in_core"]] == selected
    assert [{k: v for k, v in row.items() if k not in {"in_core", "case_sha256"}} for row in after] == [
        {k: v for k, v in row.items() if k not in {"in_core", "case_sha256"}} for row in before]
    assert {path.relative_to(root): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (root / "tasks").rglob("*") if path.is_file() and path.name != "case.toml"} == {
                path: sha for path, sha in assets_before.items() if path.name != "case.toml"}
    # Publication exports declared materials, not files merely present in the checkout.
    from benchmarking.dataset_index import publication_files

    (root / "validation.json").write_text("{}")
    (config.parent / "undeclared.txt").write_text("Maintenance-only notes")
    published = set(publication_files(root))
    assert {"README.md", "data.jsonl"} <= published
    assert "validation.json" not in published
    assert not any(path.endswith(("AGENTS.md", "undeclared.txt")) for path in published)
    for row in (json.loads(line) for line in (root / "data.jsonl").read_text().splitlines()):
        assert {row["case_path"], row["pdk_path"], row["license_path"], row["description_path"]} <= published
    asset = next(iter(read_case(config)["assets"]))
    (config.parent / asset["path"]).write_bytes(b"Changed after acceptance")
    with pytest.raises(ValueError, match="Publication asset digest mismatch"):
        publication_files(root)
