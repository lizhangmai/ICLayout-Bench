"""External test layouts preserve candidate geometry and native circuit cards."""

import json
import runpy
from types import SimpleNamespace

import pytest

from benchmarking.eda.backends.magic_fixture import MagicFixtureRCDocker
from benchmarking.evaluation.contracts import Job, JobResult
from benchmarking.evidence.identity import package_source
from benchmarking.files import Asset

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("problem", [None, "excluded", "collision", "overlap", "cell"])
def test_external_fixture_translation_and_rejections(tmp_path, monkeypatch, problem):
    db = pytest.importorskip("klayout.db")
    candidate = db.Layout()
    candidate.dbu = .001
    top = candidate.create_cell("core")
    top.shapes(candidate.layer(1, 0)).insert(db.Box(1000, 2000, 5000, 6000))
    if problem == "excluded":
        top.shapes(candidate.layer(12, 0)).insert(db.Box(2000, 3000, 3000, 4000))
    if problem == "collision":
        top.shapes(candidate.layer(1, 10)).insert(db.Text("EXTERNAL", db.Trans(2000, 3000)))
    if problem == "cell":
        candidate.create_cell("extracted")
    candidate.write(str(tmp_path / "candidate.gds"))
    original = (tmp_path / "candidate.gds").read_bytes()
    fixture = db.Layout()
    fixture.dbu = .001
    fixed = fixture.create_cell("fixed")
    box = db.Box(-1000, -1000, 1000, 1000) if problem == "overlap" else db.Box(-10000, -10000, -9000, -9000)
    fixed.shapes(fixture.layer(1, 0)).insert(box)
    fixture.write(str(tmp_path / "fixture.gds"))
    (tmp_path / "constraints.json").write_text(json.dumps({"hard": [{
        "id": "bounds", "type": "bbox_max", "functional_layers": [[1, 0]],
    }]}))
    monkeypatch.chdir(tmp_path)
    prepare = runpy.run_path(str(package_source("eda/_scripts/gds_fixture.py")))["prepare"]
    result = prepare({"top_cell": "core", "fixture_top": "fixed", "extracted_top": "extracted", "outline_constraint": "bounds",
                      "fixture_ports": ["external"], "excluded_layers": [[12, 0]]})
    assert (tmp_path / "candidate.gds").read_bytes() == original
    if problem:
        assert result["status"] == "failed"
        assert not (tmp_path / "combined.gds").exists()
    else:
        assert result["candidate_geometry_unchanged"]
        combined = db.Layout()
        combined.read(str(tmp_path / "combined.gds"))
        expected = db.Region(db.Box(-2000, -2000, 2000, 2000)) | db.Region(box)
        assert (expected ^ db.Region(combined.cell("extracted").begin_shapes_rec(combined.layer(1, 0)))).is_empty()


def test_fixture_adapter_preserves_native_cards_and_external_failure(monkeypatch):
    native = Asset(b".subckt LB_EXTERNAL_EXTRACTED P EXT\nR1 P EXT 2\n.ends\n", "spice")
    candidate, fixture = Asset(b"candidate", "gds"), Asset(b"trusted fixture", "gds")
    verdict = {"status": "passed", "reason": ""}

    class Tool:
        def run(self, command, inputs, outputs):
            assert inputs["candidate.gds"] is candidate
            assert inputs["fixture.gds"] is fixture
            return SimpleNamespace(returncode=0, reason="", evidence={}, files={
                "result.json": Asset(json.dumps(verdict).encode(), "json"),
                **({"combined.gds": Asset(b"combined", "gds")} if verdict["status"] == "passed" else {}),
            })

    def extract(self, job, inputs):
        assert inputs["layout"].content == b"combined"
        assert job.parameters == {"top_cell": "LB_EXTERNAL_EXTRACTED", "ports": ["P", "EXT"]}
        return JobResult("passed", outputs={"netlist": native}, evidence={"extracted_netlist": native})

    monkeypatch.setattr("benchmarking.eda.backends.magic_fixture.MagicRCDocker.run", extract)
    backend = object.__new__(MagicFixtureRCDocker)
    backend.tool = Tool()
    job = Job("fixture", "extract", "layout.extract_rc_fixture", (), (("netlist", "spice"),), (), None,
              json.dumps({"top_cell": "core", "ports": ["P"], "fixture_top": "fixed",
                          "fixture_ports": ["EXT"], "fixture_nets": ["external"], "outline_constraint": "bounds", "fixture_flag": "external_fixture"}))
    inputs = {"layout": candidate, "fixture": fixture, "constraints": Asset(b"{}", "json")}
    result = backend.run(job, inputs)
    assert result.outputs["netlist"].content == native.content + result.evidence["fixture_port_wrapper.spice"].content
    assert b"Xexternal P external LB_EXTERNAL_EXTRACTED" in result.evidence["fixture_port_wrapper.spice"].content
    assert result.evidence["extracted_netlist"] is native
    assert result.evidence["fixture_source.gds"] is fixture
    verdict.update(status="failed", reason="Reserved fixture label")
    result = backend.run(job, inputs)
    assert result.status == "failed" and not result.outputs
    assert result.reason == "Reserved fixture label"
