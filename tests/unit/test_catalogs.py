"""One catalog traversal checks ownership, qualification and isolated inputs.

The loader owns plan schema and dependency validation; these checks add the
catalog case contract and simulator interface evidence that it cannot infer.
"""

import hashlib
import math
import re
import shlex

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import tomli_w
from helpers.case_config import standalone_config
from helpers.catalog import CASES, ROOT, read_case

from benchmarking.eda.resources.support import load_profile
from benchmarking.evaluation import SCORING_METHOD
from benchmarking.tasks.contract import load_task, task_contract
from benchmarking.tasks.dataset import (
    Dataset,
    case_location,
    process_manifest,
    select_core,
)

pytestmark = pytest.mark.unit


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


def _check_published_budget(description, hours, context=None):
    patterns = (
        r"\bsolve budget\b\s*(?::|\bis\b)\s*\*{0,2}(\d+(?:\.\d+)?)\s*hours?\*{0,2}",
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
    scored_metrics = {name for name, weight in expected_weights.items() if weight > 0}
    allowed_metrics = set(allowed_metrics)
    published_weights = dict(tables[0]) if len(tables) == 1 else {}
    assert (
        len(tables) == 1
        and len(published_weights) == len(tables[0])
        and scored_metrics <= set(published_weights)
        and all(weight == expected_weights[name] for name, weight in published_weights.items()
                if name in expected_weights)
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
    quality_targets = re.findall(
        r"The area quality target is\s*\*\*([\d.]+) um2\*\*", description
    )
    area_references = re.findall(r"Area reference:\s*\*\*([\d.]+) um2\*\*", description)
    if current_targets:
        anchor_ratios = re.findall(
            r"([\d.]+)%\s+of (?:the )?(?:prior|previous)\s+\*\*([\d.]+) um2\*\*",
            description,
            re.IGNORECASE,
        )
        assert len(current_targets) == 1 and not area_references and not quality_targets and len(anchor_ratios) == 1
        ratio, anchor = anchor_ratios[0]
        return float(current_targets[0]), float(anchor), float(ratio) / 100
    assert len(area_references) == 1 and not current_targets and len(quality_targets) <= 1
    reference = float(area_references[0])
    target = float(quality_targets[0]) if quality_targets else reference
    return target, reference, None


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


def _check_case_plan(config, data, task):
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
    # Diagnostic bounds remain required; their zero weight need not be repeated in the score table.
    _check_published_weights(scored_only, {**expected, "phase_margin": 0}, allowed_metrics)
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

    reference_text = description.replace(
        "Current area target: **80 um2**, 80% of the prior **100 um2** engineering anchor.",
        "Area reference: **100 um2**.",
    )
    _check_published_area(reference_text, 100.0)
    with pytest.raises(AssertionError):
        _check_published_area(reference_text.replace("reference: **100 um2**", "reference: **101 um2**"), 101.0)

    integration_budget = reference_text + "The area quality target is **80 um2**. It is an integration budget.\n"
    _check_published_area(integration_budget, 80.0)
    with pytest.raises(AssertionError):
        _check_published_area(integration_budget.replace("target is **80 um2**", "target is **81 um2**"), 80.0)
    with pytest.raises(AssertionError):
        _check_published_area(integration_budget.replace("envelopes 98 um2", "envelopes 99 um2"), 80.0)


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
    _check_case_plan(config, data, task)
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
