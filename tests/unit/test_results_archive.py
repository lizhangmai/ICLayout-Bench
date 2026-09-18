"""Archive contracts, independent of the evaluator and provider runtimes.

The existing service-analysis tests cover file exports, not SQL transactions, copied
artifacts. This file tests the public ResultStore interface:
hand-authored terminal scores and bytes provide independent expectations. Tests
protect preservation, grouping, recovery and isolation; they make no model-quality
or physical-validity claim. Files belong to tmp_path, never the task catalog.
"""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

pytest.importorskip("sqlalchemy")

from benchmarking.results import ResultStore
from benchmarking.results.presentation import parse_netlist, schematic_svg
from benchmarking.results.store import digest

pytestmark = pytest.mark.unit


def result(
    root,
    sid="run-a",
    *,
    model="model-a",
    score=80,
    outcome="pass",
    task="circuit-a",
    effort="medium",
):
    root.mkdir(parents=True, exist_ok=True)
    raw = {
        "schema_version": 3,
        "state": "finished",
        "identity": {
            "benchmark": {"commit": "a" * 40, "version": "test"},
            "cli_version": "cli 1.0",
            "plan": [
                {"tasks": [task], "model": model, "harness": "codex", "effort": effort}
            ],
        },
        "summary": {"task": task, "repetition": 1},
        "files": ["final.gds", "report.md"],
        "execution": {"elapsed_seconds": 12},
        "top_cell": "TOP",
        "evaluation": {
            "protocol": "layout-http.v1",
            "state": "complete",
            "session_id": sid,
            "task_id": task,
            "task_sha256": digest(task),
            "condition": {"model": model},
            "outcome": outcome,
            "task_success": outcome == "pass",
            "score": {"method": "layout-v1", "value": score, "maximum": 100},
            "metrics": {"power": {"value": 1.2, "unit": "W", "status": "passed"}},
            "limits": {"wall_seconds": 3600},
            "tool_identity": {"image_id": "test-image"},
            "verification_level": "local_development",
            "submission": {
                "candidate_sha256": digest(b"candidate"),
                "submission_id": "1",
            },
        },
    }
    (root / "final.gds").write_bytes(b"candidate")
    (root / "report.md").write_text("Result report")
    (root / "result.json").write_text(json.dumps(raw))
    return root / "result.json"


def change(path, operation):
    raw = json.loads(path.read_text())
    operation(raw)
    path.write_text(json.dumps(raw))


def test_import_is_independent_idempotent_and_preserves_unknowns(tmp_path):
    store = ResultStore(tmp_path / "archive")
    source = result(tmp_path / "source")
    imported = store.import_result(source)
    assert store.import_result(source)["status"] == "existing"
    source.parent.rename(tmp_path / "unavailable-source")
    detail = store.detail(imported["run_id"])
    assert detail["evaluation"]["score"] == 80
    candidate = next(a for a in detail["artifacts"] if a["name"] == "final.gds")
    assert store.artifact(candidate["sha256"]).read_bytes() == b"candidate"
    assert store.list_runs()["total"] == 1
    error = result(tmp_path / "error", "error", score=None, outcome="error")
    store.import_result(error)
    c = store.comparison()["cells"][0]
    assert (c["mean"], c["count"], c["measured"]) == (80, 2, 1)
    assert c["outcomes"]["error"] == 1
    assert store.comparison()["totals"][0]["mean"] is None
    assert not store.verify()["failures"]
    store.close()


def test_conflicts_rollback_and_revisions_remain_accessible(tmp_path):
    store = ResultStore(tmp_path / "archive")
    source = result(tmp_path / "source")
    first = store.import_result(source)
    change(source, lambda d: d["evaluation"]["score"].update(value=90))
    with pytest.raises(ValueError, match="Changed evaluation"):
        store.import_result(source)
    assert store.detail(first["run_id"])["evaluation"]["score"] == 80
    second = store.import_result(source, reevaluation=True)
    assert len(store.detail(first["run_id"])["history"]) == 2
    assert (
        store.detail(first["run_id"], first["evaluation_id"])["evaluation"]["score"]
        == 80
    )
    assert (
        store.detail(first["run_id"], second["evaluation_id"])["evaluation"]["score"]
        == 90
    )
    change(source, lambda d: d["identity"]["plan"][0].update(model="different"))
    with pytest.raises(ValueError, match="Conflicting run"):
        store.import_result(source)
    assert store.list_runs()["total"] == 1
    assert len(store.inventory()["conditions"]) == 1
    store.close()


def test_newest_revision_filter_never_resurrects_old_verification(tmp_path):
    store = ResultStore(tmp_path / "archive")
    source = result(tmp_path / "source")
    store.import_result(source)
    change(
        source, lambda d: d["evaluation"].update(verification_level="service_recorded")
    )
    store.import_result(source, reevaluation=True)
    assert store.list_runs(verification="local_development")["total"] == 0
    assert store.list_runs(verification="service_recorded")["total"] == 1


def test_comparison_separates_efforts_contexts_and_planned_coverage(tmp_path):
    store = ResultStore(tmp_path / "archive")
    store.import_result(result(tmp_path / "a"), experiment="planned")
    store.import_result(
        result(tmp_path / "b", "b", model="model-b", score=40), experiment="planned"
    )
    store.import_result(
        result(tmp_path / "c", "c", effort="high"), experiment="planned"
    )
    assert len(store.comparison()["conditions"]) == 3
    assert sorted(c["mean"] for c in store.comparison()["cells"]) == [40, 80, 80]
    xid = store.register_experiment(
        "planned",
        [
            {
                "model": "model-a",
                "harness": "codex",
                "effort": "medium",
                "tasks": ["circuit-a", "not-yet-run"],
                "repetitions": 1,
            }
        ],
    )
    comparison = store.comparison(experiment=xid)
    assert {t["task_id"] for t in comparison["tasks"]} == {"circuit-a", "not-yet-run"}
    assert comparison["totals"][0]["total_tasks"] == 2
    alternate = result(tmp_path / "d", "d")
    change(alternate, lambda d: d["evaluation"]["limits"].update(wall_seconds=7200))
    store.import_result(alternate)
    assert (
        len(store.comparison()["tasks"]) == 3
    )  # two measured contexts and one planned task


def test_candidate_integrity_path_isolation_and_interrupted_transaction(
    tmp_path, monkeypatch
):
    store = ResultStore(tmp_path / "archive")
    source = result(tmp_path / "source")
    (source.parent / "final.gds").write_bytes(b"changed")
    with pytest.raises(ValueError, match="Candidate differs"):
        store.import_result(source)
    (source.parent / "final.gds").write_bytes(b"candidate")
    change(source, lambda d: d["files"].append("../secret"))
    with pytest.raises(ValueError):
        store.import_result(source)
    change(source, lambda d: d.update(files=["final.gds"]))
    from benchmarking.results import store as archive_module
    execute = archive_module.ensure_record

    def interrupt(conn, table, key, values):
        if table.name == "run_artifacts":
            raise OSError("interrupted commit")
        return execute(conn, table, key, values)

    monkeypatch.setattr(archive_module, "ensure_record", interrupt)
    with pytest.raises(OSError):
        store.import_result(source)
    assert store.list_runs()["total"] == 0
    monkeypatch.setattr(archive_module, "ensure_record", execute)
    imported = store.import_result(source)
    attachment = next(
        a
        for a in store.detail(imported["run_id"])["artifacts"]
        if a["name"] == "final.gds"
    )
    store.artifact(attachment["sha256"]).write_bytes(b"corrupt")
    assert store.verify()["failures"]


def test_parallel_import_deduplicates_shared_conditions(tmp_path):
    store = ResultStore(tmp_path / "archive")
    paths = [result(tmp_path / str(i), str(i)) for i in range(8)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(store.import_result, paths + paths))
    assert store.list_runs()["total"] == len(paths)
    assert len(store.inventory()["conditions"]) == 1


def test_outbox_retries_without_reexecuting_model(tmp_path, monkeypatch):
    import benchmarking.results
    from benchmarking.participants.archive import enqueue, retry

    source = result(tmp_path / "source")
    archive = tmp_path / "archive"
    real = benchmarking.results.ResultStore

    def offline(*a, **k):
        raise OSError("database unavailable")

    monkeypatch.setattr(benchmarking.results, "ResultStore", offline)
    assert enqueue(archive, source, experiment="test")["status"] == "pending"
    monkeypatch.setattr(benchmarking.results, "ResultStore", real)
    assert retry(archive)[0]["status"] == "imported"
    assert retry(archive) == []
    assert real(archive).list_runs()["total"] == 1


def test_schematic_keeps_ordered_pins_models_and_escapes_labels():
    circuit = parse_netlist(
        ".subckt top a b c d\nM1 a b c d nmos\n+ W=1u L=0.1u\nR1 a b 1k\n.ends\n", "top"
    )
    assert circuit["ports"] == ["a", "b", "c", "d"]
    assert circuit["devices"][0]["nodes"] == ["a", "b", "c", "d"]
    assert circuit["devices"][0]["parameters"] == "W=1u L=0.1u"
    # Maintained CDL includes dollar-bearing identifiers and substrate terminals.
    # Explicit pin expectations protect display binding, not electrical evaluation.
    cdl = parse_netlist(
        ".subckt top c b e bulk\nQ$1 $10 b e $1 npn13G2 m=1\n"
        "R$2 c e $1 rsil w=4u $ comment\nQplain c b e npn 2\n.ends\n", "top"
    )
    assert cdl["devices"][0]["name"] == "Q$1"
    assert cdl["devices"][0]["nodes"] == ["$10", "b", "e", "$1"]
    assert cdl["devices"][0]["model"] == "npn13G2"
    assert cdl["devices"][1]["nodes"] == ["c", "e", "$1"]
    assert cdl["devices"][1]["model"] == "rsil"
    assert cdl["devices"][1]["parameters"] == "w=4u"
    assert cdl["devices"][2]["nodes"] == ["c", "b", "e"]
    assert cdl["devices"][2]["parameters"] == "2"
    circuit["subcircuit"] = "<script>"
    svg = schematic_svg(circuit)
    assert b"<script>" not in svg and b"&lt;script&gt;" in svg
    with pytest.raises(ValueError, match="Unsupported"):
        parse_netlist(".subckt top a b\nZbad a b\n.ends", "top")


def test_drc_overlay_reads_klayout_polygon_and_box_coordinates():
    """KLayout RDB serializes micron-coordinate lists within a single pair of parentheses.

    The independent expected rectangle bounds catch lost vertices and diagonal-only
    box rendering. This tests display coordinates, not rule detection or signoff.
    """
    from benchmarking.results.geometry import drc_markers

    raw = b"""<report-database><items><item><cell>TOP</cell><category>spacing</category>
    <values><value>polygon: (0,0;2,1;2,0)</value><value>box: (1,2;3,4)</value></values>
    </item></items></report-database>"""
    polygon, box = drc_markers(raw)
    assert polygon["points"] == [[0, 0], [2, 1], [2, 0], [0, 0]]
    assert box["points"] == [[1, 2], [3, 2], [3, 4], [1, 4], [1, 2]]
    assert polygon["cell"] == "TOP" and box["category"] == "spacing"


def test_interactive_geometry_applies_hierarchy_and_database_units(tmp_path):
    """A nonphysical 2×1 µm rectangle translated by (5, 7) µm is an analytical display control.

    Its expected extents follow translation alone. It guards the visualization's
    coordinate transform; the fixture carries no circuit or manufacturing claim.
    """
    db = pytest.importorskip("klayout.db")
    from benchmarking.results.geometry import extract

    layout = db.Layout()
    layout.dbu = 0.001
    top, child = layout.create_cell("TOP"), layout.create_cell("CHILD")
    child.shapes(layout.layer(1, 0)).insert(db.Box(0, 0, 2000, 1000))
    top.insert(db.CellInstArray(child.cell_index(), db.Trans(5000, 7000)))
    path = tmp_path / "display.gds"
    layout.write(str(path))
    geometry = extract(path, "TOP")
    assert geometry["bbox"] == [5, 7, 7, 8]
    points = geometry["layers"][0]["polygons"][0][0]
    assert sorted(points) == [[5, 7], [5, 8], [7, 7], [7, 8]]
    with pytest.raises(ValueError, match="shape limit"):
        extract(path, "TOP", max_shapes=0)


def test_runner_storage_configuration_does_not_change_frozen_conditions(
    tmp_path, monkeypatch
):
    """Archive destinations affect delivery only, never whether completed work is rerun."""
    import benchmarking.run as runner
    from benchmarking.participants.config import read_configs

    config = tmp_path / "experiment.toml"
    base = 'harness="codex"\nmodel="model-a"\nefforts=["medium"]\ntasks=["case"]\nconcurrency=1\nrepetitions=1\n'
    config.write_text(base)
    monkeypatch.setattr(runner, "resolve", lambda *args: ({}, {}, {}))
    monkeypatch.setattr(runner, "harness_version", lambda _: ("1.0", "cli 1.0"))
    identities = []

    def capture(args, row, selection, output, identity, blocked):
        identities.append(identity)
        return 0

    monkeypatch.setattr(runner, "execute_condition", capture)
    args = ["--config", str(config), "--endpoint", "https://example.invalid"]
    assert runner.main(args) == 0
    config.write_text('results_data="results/archive"\n' + base)
    assert read_configs([config])[0]["results_data"] == "results/archive"
    assert runner.main(args) == 0
    assert identities[0] == identities[1]
    config.write_text("results_data=false\n" + base)
    with pytest.raises(ValueError, match="results_data"):
        read_configs([config])


def test_legacy_reevaluation_cannot_replace_the_imported_candidate(tmp_path):
    """Missing historical hashes do not authorize replacement of a run's copied GDS."""
    store = ResultStore(tmp_path / "archive")
    source = result(tmp_path / "source")
    change(source, lambda d: d["evaluation"]["submission"].pop("candidate_sha256"))
    imported = store.import_result(source)
    (source.parent / "final.gds").write_bytes(b"another candidate")
    change(source, lambda d: d["evaluation"]["score"].update(value=90))
    with pytest.raises(ValueError, match="Conflicting run"):
        store.import_result(source, reevaluation=True)
    assert store.detail(imported["run_id"])["evaluation"]["score"] == 80


def test_authored_schematic_requires_matching_source_and_artifact_digests(tmp_path):
    """A later drawing may illustrate an old result only for identical source bytes.

    Existing archive tests do not cover authored assets. A tiny independent Git
    catalog protects against silently displaying the wrong circuit or modified SVG.
    """
    import subprocess
    from html import escape

    from benchmarking.results.presentation import GitCatalog

    root = tmp_path / "catalog"
    case = root / "tasks/pdk/library/cases/gate"
    case.mkdir(parents=True)
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    raw = b".subckt gate a z\nR1 a z 1k\n.ends\n"
    metadata = {
        "format": "iclayout-schematic-v1",
        "case_id": "gate",
        "netlist_sha256": digest(raw),
    }
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg"><metadata>'
        + escape(json.dumps(metadata))
        + "</metadata><text>gate</text></svg>"
    ).encode()
    (case / "schematic.svg").write_bytes(svg)
    config = (
        'id = "gate"\n[[assets]]\nrole = "schematic"\nformat = "svg"\n'
        'path = "schematic.svg"\nsha256 = "' + digest(svg) + '"\n'
        '[task.inputs.netlist]\nsha256 = "' + digest(raw) + '"\n'
    )
    (case / "case.toml").write_text(config)

    def snapshot():
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "-m",
                "Catalog",
            ],
            check=True,
            capture_output=True,
        )
        revision = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
        ).strip()
        return GitCatalog(root, revision)

    catalog = snapshot()
    drawing, provenance = catalog.schematic("gate", digest(raw))
    assert drawing == svg
    assert provenance["kind"] == "authored"
    assert provenance["schematic_commit"] == catalog.revision
    assert catalog.schematic("unknown-case", digest(raw)) is None
    with pytest.raises(ValueError, match="different netlist"):
        catalog.schematic("gate", digest(raw + b"* changed source"))
    (case / "schematic.svg").write_bytes(svg + b"<!-- changed -->")
    with pytest.raises(ValueError, match="digest mismatch"):
        snapshot().schematic("gate", digest(raw))
    # Updating the asset hash alone cannot bless a drawing for another circuit.
    wrong = svg.replace(b"gate</text>", b"other</text>").replace(
        b"gate&quot;", b"other&quot;"
    )
    (case / "schematic.svg").write_bytes(wrong)
    (case / "case.toml").write_text(config.replace(digest(svg), digest(wrong)))
    with pytest.raises(ValueError, match="provenance does not match"):
        snapshot().schematic("gate", digest(raw))

# Delivery is a separate public contract: packages must preserve terminal bytes,
# exclude live credentials and reject attacker-controlled archive paths. Existing
# SQL tests do not exercise that transport boundary; all artifacts use tmp_path.
def test_portable_package_preserves_results_without_runtime(tmp_path):
    from benchmarking.transfer import pack, unpack
    source = result(tmp_path / "source")
    (source.parent / ".runtime").mkdir()
    (source.parent / ".runtime" / "credentials").write_text("never packaged")
    package = tmp_path / "results.zip"
    pack(source.parent, package)
    target = tmp_path / "received"
    unpack(package, target)
    copied = next(target.rglob("result.json"))
    assert copied.read_bytes() == source.read_bytes()
    assert (copied.parent / "final.gds").read_bytes() == b"candidate"
    assert not list(target.rglob("credentials"))
    store = ResultStore(tmp_path / "received-db")
    record = store.import_result(copied)
    assert store.detail(record["run_id"])["evaluation"]["score"] == 80
    store.close()


def test_package_rejects_symlinks_traversal_and_digest_tampering(tmp_path):
    import zipfile

    from benchmarking.transfer import pack, unpack
    source = result(tmp_path / "source")
    package = tmp_path / "results.zip"
    pack(source, package)
    with zipfile.ZipFile(package) as z:
        content = {n: z.read(n) for n in z.namelist()}
    for label, addition in [("escape", {"../escape": b"bad"}), ("tamper", {"runs/000000/final.gds": b"changed"})]:
        altered = tmp_path / (label + ".zip")
        with zipfile.ZipFile(altered, "w") as z:
            for name, data in {**content, **addition}.items():
                z.writestr(name, data)
        with pytest.raises(ValueError):
            unpack(altered, tmp_path / label)
        assert not (tmp_path / label).exists()
    (source.parent / "final.gds").unlink()
    (source.parent / "final.gds").symlink_to(source.parent / "report.md")
    with pytest.raises((ValueError, OSError)):
        pack(source, tmp_path / "symlink.zip")


def test_upload_client_never_sends_credentials_over_remote_http():
    from benchmarking.transfer import request
    with pytest.raises(ValueError, match="HTTPS"):
        request("http://example.org", "test-only", "/api/uploads")


def test_tool_schemes_share_evaluator_context_without_merging_conditions(tmp_path):
    """Solver tooling is a participant variable; the trusted judge is the context.

    Extend existing comparison coverage with two hand-authored scheme identities.
    Historical unsplit identities stay separate rather than acquiring new claims.
    """
    store = ResultStore(tmp_path / 'archive')
    for label, score in [('baseline', 40), ('with-a', 80)]:
        path = result(tmp_path / label, sid=label, score=score)
        def configure(raw, label=label):
            raw['identity']['plan'][0].update(name=label, scheme={'instructions': label, 'mcp': {}})
            raw['evaluation']['tool_identity'] = {'image_id': label, 'evaluator': {'backends': {'drc': 'same-judge'}}}
        change(path, configure)
        store.import_result(path)
    compared = store.comparison()
    assert len(compared['conditions']) == 2
    assert len(compared['tasks']) == 1
    assert sorted(c['mean'] for c in compared['cells']) == [40, 80]
    store.import_result(result(tmp_path / 'historical', sid='historical'))
    assert len(store.comparison()['tasks']) == 2


def test_import_preserves_reference_scores_above_100_and_separates_versions(tmp_path):
    store = ResultStore(tmp_path / 'archive')
    source = result(tmp_path / 'relative', score=144)
    change(source, lambda raw: raw['evaluation']['score'].update(
        method='layout-v2', maximum=None, reference=100))
    imported = store.import_result(source)
    assert store.detail(imported['run_id'])['evaluation']['score'] == 144
    store.import_result(result(tmp_path / 'legacy', sid='legacy', score=100))
    cells = store.comparison()['cells']
    assert sorted(cell['mean'] for cell in cells) == [100, 144]
    assert not store.verify()['failures']
    store.close()
