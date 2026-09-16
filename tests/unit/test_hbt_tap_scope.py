"""The optional ideal body boundary applies only to candidate extraction."""

import json
from types import SimpleNamespace

import pytest

from benchmarking.bundles import publish_bundle
from benchmarking.evaluation import Job
from benchmarking.files import Asset
from layout_eval.hbt import SG13G2HBTRCDocker
from layout_eval.klayout import KLayoutDocker

pytestmark = pytest.mark.unit


@pytest.fixture
def settings(tmp_path, monkeypatch):
    class Tool:
        def __init__(self, image, version_command, timeout):
            self.identity = {"tool_version": "8.3.678" if version_command[0] == "magic" else "0.30.11"}
            self.inputs = None

        def run(self, command, inputs, outputs):
            self.inputs = inputs
            return SimpleNamespace(reason="tool boundary stop", returncode=1, evidence={}, files={})

    monkeypatch.setattr("layout_eval.klayout.DockerTool", Tool)
    monkeypatch.setattr("layout_eval.magic.DockerTool", Tool)
    profile = {"deck": "rules.lvs", "variables": {"disable_tap_extraction": "false"}, "scope": "strict taps"}
    publish_bundle({"rules.lvs": Asset(b"# fixture", "text"),
                    "profile.json": Asset(json.dumps(profile).encode(), "json")}, {}, tmp_path / "klayout")
    publish_bundle({"sg13g2.tech": Asset(b"# fixture", "text")}, {}, tmp_path / "magic")
    return {"image": "fixture", "klayout_support": str(tmp_path / "klayout"),
            "klayout_profile": "profile.json", "magic_support": str(tmp_path / "magic"),
            "technology": "sg13g2.tech", "tech_name": "sg13g2", "style": "ngspice"}


@pytest.mark.parametrize("disabled", [False, True])
def test_body_boundary_is_explicit_without_changing_physical_lvs(settings, disabled):
    adapter = SG13G2HBTRCDocker(**settings, disable_tap_extraction=disabled)
    physical = KLayoutDocker(image=settings["image"], check="lvs",
                             support=settings["klayout_support"], profile=settings["klayout_profile"])
    candidate = Asset(b"frozen candidate", "gds")
    job = Job("pex", "extract", "layout.extract", (), (("netlist", "spice"),), (), None,
              json.dumps({"ports": ["IN", "OUT", "VSS"], "top_cell": "AMP"}))
    result = adapter.run(job, {"layout": candidate})
    assert result.status == "error"  # Deliberately stop at the external EDA boundary.
    submitted = adapter.klayout.tool.inputs
    config = json.loads(submitted["config.json"].content)
    assert config["variables"]["disable_tap_extraction"] == str(disabled).lower()
    assert adapter.identity["disable_tap_extraction"] is disabled
    assert submitted["candidate.gds"] == candidate
    assert physical.identity["settings"]["variables"]["disable_tap_extraction"] == "false"
    assert result.evidence["klayout_configuration"] == submitted["config.json"]


@pytest.mark.parametrize("invalid", ["false", "true", 0, 1, None])
def test_body_boundary_rejects_non_boolean_configuration(settings, invalid):
    with pytest.raises(TypeError, match="boolean"):
        SG13G2HBTRCDocker(**settings, disable_tap_extraction=invalid)
