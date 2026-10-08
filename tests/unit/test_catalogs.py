"""One catalog traversal checks ownership, qualification and isolated inputs.

The loader owns plan schema and dependency validation; these checks add the
published case contract and SPICE interface evidence that it cannot infer.
"""

import hashlib
import json
import math
import re

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import tomli_w
from helpers.case_config import standalone_config
from helpers.catalog import CASES, ROOT, read_case

from benchmarking.dataset import Dataset, case_location, process_manifest, select_core
from benchmarking.engine.resources.support import load_profile
from benchmarking.evaluation import SCORING_METHOD
from benchmarking.tasks import load_task, task_contract

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("card_split", [None, "test", "validation"])
@pytest.mark.parametrize("table_format", ["parquet", "jsonl"])
@pytest.mark.parametrize("ordered", [False, True])
def test_native_static_index_with_and_without_dataset_card(tmp_path, card_split, table_format, ordered):
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
    name = f"data.{table_format}"

    def write_index():
        if table_format == "parquet":
            pq.write_table(pa.Table.from_pylist(source_rows), tmp_path / name)
        else:
            (tmp_path / name).write_text("".join(json.dumps(row) + "\n" for row in source_rows))

    write_index()
    if table_format == "parquet":
        # A leftover legacy view must not override the native index without a card.
        (tmp_path / "data.jsonl").write_text(json.dumps({**source_rows[0], "id": "obsolete"}) + "\n")
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


def _check_published_budget(description, hours, context=None):
    patterns = (
        r"\bsolve budget\b\s*(?::|\bis\b)\s*\*{0,2}(\d+(?:\.\d+)?)\s*hours\*{0,2}",
        r"求解(?:预算|时限)\s*[:：]?\s*\*{0,2}(\d+(?:\.\d+)?)\s*小时\*{0,2}",
    )
    published_hours = [float(value) for pattern in patterns
                       for value in re.findall(pattern, description, re.IGNORECASE)]
    assert published_hours == [hours], context


def _markdown_cells(line):
    if "|" not in line:
        return None
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _published_weight_tables(description):
    lines = description.splitlines()
    tables = []
    for index, line in enumerate(lines):
        headers = _markdown_cells(line)
        if headers is None:
            continue
        normalized = [re.sub(r"[^a-z]+", " ", cell.lower()).strip() for cell in headers]
        metric_columns = [column for column, name in enumerate(normalized)
                          if name == "metric" or headers[column] == "指标"]
        weight_columns = [column for column, name in enumerate(normalized)
                          if "weight" in name.split() or headers[column] in {"权重", "评分权重"}]
        if len(metric_columns) != 1 or len(weight_columns) != 1 or index + 1 >= len(lines):
            continue

        separator = _markdown_cells(lines[index + 1])
        if separator is None or len(separator) != len(headers) or not all(
            re.fullmatch(r":?-{3,}:?", cell) for cell in separator
        ):
            continue

        rows = []
        for row_line in lines[index + 2:]:
            cells = _markdown_cells(row_line)
            if cells is None:
                break
            assert len(cells) == len(headers), row_line
            metric = re.search(r"`([^`]+)`", cells[metric_columns[0]])
            weight = re.fullmatch(
                r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(%)?",
                cells[weight_columns[0]],
            )
            assert metric is not None and weight is not None, row_line
            value = float(weight[1]) / 100 if weight[2] else float(weight[1])
            rows.append((metric[1], value))
        tables.append(rows)
    return tables


def _check_published_weights(description, expected, allowed_metrics, context=None):
    tables = _published_weight_tables(description)
    expected_weights = dict(expected)
    allowed_metrics = set(allowed_metrics)
    published_weights = dict(tables[0]) if len(tables) == 1 else {}
    assert (
        len(tables) == 1
        and len(tables[0]) >= len(expected_weights)
        and len(published_weights) == len(tables[0])
        and set(expected_weights) <= set(published_weights)
        and all(published_weights[name] == weight for name, weight in expected_weights.items())
        and all(
            name in allowed_metrics and weight == 0
            for name, weight in published_weights.items()
            if name not in expected_weights
        )
    ), context


def _published_area_targets(description):
    current_targets = re.findall(
        r"Current area target:\s*\*\*([\d.]+) um2\*\*", description
    )
    area_references = re.findall(r"Area reference:\s*\*\*([\d.]+) um2\*\*", description)
    if current_targets:
        anchor_ratios = re.findall(
            r"([\d.]+)%\s+of (?:the )?(?:prior|previous)\s+\*\*([\d.]+) um2\*\*",
            description,
            re.IGNORECASE,
        )
        assert len(current_targets) == 1 and not area_references and len(anchor_ratios) == 1
        ratio, anchor = anchor_ratios[0]
        return float(current_targets[0]), float(anchor), float(ratio) / 100
    assert len(area_references) == 1 and not current_targets
    reference = float(area_references[0])
    return reference, reference, None


def _check_published_area(description, expected_target, context=None):
    # The formula defines the engineering anchor. A later target may be a
    # deliberate percentage of that anchor, so validate both values separately.
    envelope = re.search(r"sum of device/contact envelopes ([\d.]+) um2", description)
    margin = re.search(r"total outer width/height allowance ([\d.]+) um", description)
    formula = re.search(r"Estimate = (.*?)\. Here", description)
    assert envelope and margin and formula, context
    target, anchor, ratio = _published_area_targets(description)
    expression = formula[1]
    assert set(re.findall(r"[A-Za-z_]\w*", expression)) <= {
        "ceil", "sqrt", "envelope_sum", "margin"
    }, context
    assert re.fullmatch(r"[\w\s.+*/^()-]+", expression), context
    calculated = eval(expression.replace("^", "**"), {"__builtins__": {}}, {
        "ceil": math.ceil,
        "sqrt": math.sqrt,
        "envelope_sum": float(envelope[1]),
        "margin": float(margin[1]),
    })
    assert abs(calculated - anchor) <= 0.010001, context
    assert target == expected_target, context
    if ratio is not None:
        assert abs(target - ratio * anchor) <= 0.010001, context


def _check_public_plan(config, data, task):
    assert task.hours == data["task"]["hours"] and task.wall_seconds > 0, config
    description = next(item.content.decode() for item in task.inputs if item.role == "description")
    _check_published_budget(description, task.hours, config)
    assert "coefficient" in data["task"], config
    plan = task.evaluation
    assert plan is not None and plan.mode == "post_layout", config
    assert plan.scoring.method == SCORING_METHOD, config
    _check_published_weights(
        description,
        plan.scoring.weights,
        {metric.id for metric in plan.metrics},
        config,
    )
    # Publication review checks whether the scoring explanation is adequate.
    # Equivalent prose need not reproduce scoring.rationale verbatim; these
    # automated checks validate numeric disclosures, not natural-language meaning.
    # The published envelope calculation must reproduce its frozen anchor.
    # Evaluate the documented expression, rather than restating its coefficients;
    # the displayed envelope sum is rounded, so allow one final 0.01 um2 bin.
    envelope = re.search(r"sum of device/contact envelopes ([\d.]+) um2", description)
    if envelope:
        _check_published_area(description, plan.scoring.area_target, config)
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


@pytest.mark.parametrize("description", [
    "Solve budget: **3 hours**.",
    "The solve budget is 3 hours.",
    "求解预算 3 小时。",
    "求解时限 **3 小时**。",
])
def test_published_budget_forms_keep_numeric_contract(description):
    _check_published_budget(description, 3)
    with pytest.raises(AssertionError):
        _check_published_budget(description.replace("3", "4"), 3)


@pytest.mark.parametrize("language", ["en", "zh"])
def test_published_weights_read_the_declared_column_and_reject_drift(language):
    description = """| Metric | Required range | Aggregation | Score weight |
| --- | --- | --- | --- |
| `functional_area` (um2) | -inf to +inf | max | 20% |
| `gain` (dB) | 40 to 100 | min | 80% |
| `phase_margin` (deg) | 45 to 180 | min | 0% |
"""
    if language == "zh":
        description = description.replace("Metric", "指标").replace("Score weight", "评分权重")
    expected = {"functional_area": 0.2, "gain": 0.8}
    allowed_metrics = {*expected, "phase_margin"}
    _check_published_weights(description, expected, allowed_metrics)
    with pytest.raises(AssertionError):
        _check_published_weights(description.replace("80%", "75%"), expected, allowed_metrics)
    with pytest.raises(AssertionError):
        _check_published_weights(description.replace("phase_margin` (deg) | 45 to 180 | min | 0%", "phase_margin` (deg) | 45 to 180 | min | 10%"), expected, allowed_metrics)
    with pytest.raises(AssertionError):
        _check_published_weights(description.replace("| `phase_margin`", "| `unlisted_metric`"), expected, allowed_metrics)
    scored_only = description.replace("| `phase_margin` (deg) | 45 to 180 | min | 0% |\n", "")
    _check_published_weights(scored_only, expected, allowed_metrics)
    with pytest.raises(AssertionError):
        _check_published_weights(description.replace("| `gain` (dB) | 40 to 100 | min | 80% |\n", ""), expected, allowed_metrics)
    for malformed in (
        description.replace("min | 0%", "min | n/a"),
        description.replace("`phase_margin`", "phase_margin"),
        description.replace("45 to 180 | min | 0%", "45 to 180 | 0%"),
    ):
        with pytest.raises(AssertionError):
            _check_published_weights(malformed, expected, allowed_metrics)


def test_published_area_target_and_formula_anchor_are_checked_separately():
    description = """Current area target: **80 um2**, 80% of the prior **100 um2** engineering anchor.
sum of device/contact envelopes 98 um2, total outer width/height allowance 2 um.
Estimate = ceil(envelope_sum + margin). Here margin is the total allowance.
"""
    _check_published_area(description, 80.0)
    with pytest.raises(AssertionError):
        _check_published_area(description.replace("target: **80 um2**", "target: **81 um2**"), 80.0)
    with pytest.raises(AssertionError):
        _check_published_area(description.replace("envelopes 98 um2", "envelopes 99 um2"), 80.0)

    legacy_reference = description.replace(
        "Current area target: **80 um2**, 80% of the prior **100 um2** engineering anchor.",
        "Area reference: **100 um2**.",
    )
    _check_published_area(legacy_reference, 100.0)
    with pytest.raises(AssertionError):
        _check_published_area(legacy_reference.replace("reference: **100 um2**", "reference: **101 um2**"), 101.0)


@pytest.mark.parametrize("config", CASES, ids=lambda path: path.parent.name)
@pytest.mark.skipif(not CASES, reason="Set ICLAYOUT_BENCH_DATASET to run dataset checks")
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
    declared.update(entry.get("source", entry["path"]) for entry in inputs.values())
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
@pytest.mark.skipif(not CASES, reason="Set ICLAYOUT_BENCH_DATASET to run dataset checks")
def test_native_huggingface_views_match_authoritative_cases(tmp_path):
    datasets = pytest.importorskip("datasets")
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
