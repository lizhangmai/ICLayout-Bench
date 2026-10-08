"""Exercise real KLayout geometry measurement without native LVS or Docker."""

import importlib.util
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.acceptance_eda]
LOWER_LAYER = [1, 0]
UPPER_LAYER = [35, 0]
FUNCTIONAL_LAYERS = [LOWER_LAYER, UPPER_LAYER]


@pytest.fixture
def native_geometry_runner(monkeypatch):
    db = pytest.importorskip("klayout.db")
    engine = Path(__file__).parents[2] / "benchmarking" / "engine" / "container_scripts"
    monkeypatch.syspath_prepend(str(engine))
    spec = importlib.util.spec_from_file_location("geometry_runner_under_test", engine / "geometry_runner.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, db


def write_candidate(db, path, *, unrelated=False):
    layout = db.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("DUT")
    if unrelated:
        top.shapes(layout.layer(99, 0)).insert(db.Box(0, 0, 1000, 1000))
    else:
        # Lower-layer core rectangle is 4 x 4 um. The upper-layer route extends
        # its functional union bbox to 12 x 10 um. The expected metric is the
        # bbox area, calculated from those independent rectangle coordinates.
        top.shapes(layout.layer(*LOWER_LAYER)).insert(db.Box(0, 0, 4000, 4000))
        top.shapes(layout.layer(*UPPER_LAYER)).insert(db.Box(10000, 0, 12000, 10000))
    layout.write(str(path))


def runner_config(constraints):
    return {
        "top_cell": "DUT",
        "max_bytes": 1024 * 1024,
        "subcircuit": "DUT",
        "constraints": constraints,
        "layers": {},
        "native_lvs": False,
    }


def test_uncapped_area_uses_all_declared_layers_and_legacy_bbox_still_rejects(
    native_geometry_runner, monkeypatch, tmp_path
):
    runner, db = native_geometry_runner
    candidate = tmp_path / "candidate.gds"
    write_candidate(db, candidate)
    monkeypatch.chdir(tmp_path)
    legacy = {
        "hard": [{"id": "outline", "type": "bbox_max", "functional_layers": FUNCTIONAL_LAYERS,
                  "max_width_um": 8.0, "max_height_um": 8.0}],
        "quality": [{"id": "area", "type": "functional_bbox_area", "layers_from": "outline"}],
    }

    legacy_status, _, legacy_details, legacy_measurements = runner.inspect(runner_config(legacy))

    assert legacy_status == "failed"
    assert legacy_details["outline"]["passed"] is False
    assert legacy_measurements == {}

    quality_only = {
        "hard": [],
        "quality": [{"id": "area", "type": "functional_bbox_area",
                      "functional_layers": FUNCTIONAL_LAYERS}],
    }
    status, _, details, measurements = runner.inspect(runner_config(quality_only))
    cap_area = legacy["hard"][0]["max_width_um"] * legacy["hard"][0]["max_height_um"]

    assert status == "passed"
    assert details["area"] == {"passed": True, "width_um": 12.0, "height_um": 10.0}
    assert measurements["area"] == {"value": 120.0, "unit": "um2"}
    assert measurements["area"]["value"] > cap_area


def test_empty_declared_functional_geometry_fails_without_zero_area(
    native_geometry_runner, monkeypatch, tmp_path
):
    runner, db = native_geometry_runner
    write_candidate(db, tmp_path / "candidate.gds", unrelated=True)
    monkeypatch.chdir(tmp_path)
    constraints = {
        "hard": [],
        "quality": [{"id": "area", "type": "functional_bbox_area",
                     "functional_layers": [LOWER_LAYER]}],
    }

    status, reason, details, measurements = runner.inspect(runner_config(constraints))

    assert status == "failed"
    assert reason
    assert details["area"]["passed"] is False
    assert measurements == {}
