"""Independent analytical checks for the projected sheet and native binding."""

import pytest

pytestmark = pytest.mark.unit

np = pytest.importorskip("numpy")
pytest.importorskip("klayout.db")
pytest.importorskip("scipy")

from benchmarking.eda._scripts.substrate import grid_edges, spice_multiport


def test_rectangular_sheet_faces_use_two_half_cell_resistances():
    # Two cells, widths 2 and 4, height 3, Rs 10 and 40 ohm/square.
    # Their series half-cell resistance is 10*1/3 + 40*2/3 = 30 ohm.
    a, b, conductance = grid_edges(np.array([[0, 1]]),
                                    (np.array([0, 2, 6]), np.array([0, 3])),
                                    np.array([[10, 40]]))
    assert list(zip(a, b, strict=True)) == [(0, 1)]
    assert conductance == pytest.approx([1/30])


def test_uniform_square_sheet_has_analytical_parallel_series_resistance():
    ids = np.arange(6).reshape(2, 3)
    a, b, conductance = grid_edges(ids, (np.arange(4), np.arange(3)), 12.)
    matrix = np.zeros((6, 6))
    for i, j, g in zip(a, b, conductance, strict=True):
        matrix[i, i] += g
        matrix[j, j] += g
        matrix[i, j] -= g
        matrix[j, i] -= g
    # Each horizontal row is two 12-ohm resistors; two rows are parallel.
    voltage = np.array([1., 0., 0., 1., 0., 0.])
    free = [1, 4]
    voltage[free] = np.linalg.solve(matrix[np.ix_(free, free)],
                                    -matrix[np.ix_(free, [0, 3])] @ np.ones(2))
    assert 1/(matrix @ voltage)[[0, 3]].sum() == pytest.approx(12.)
    assert matrix @ np.ones(6) == pytest.approx(np.zeros(6))


def test_native_multiport_preserves_all_nonbody_fields_and_reorders_named_ports():
    native = ".SUBCKT cell g d b s\nM$7 d g s b nfet L=.7U W=2U AS=3P AD=4P PS=5U PD=6U\n.ENDS\n"
    devices = [{"id": 7, "body": "b", "model": "nfet"}]
    # Z from two ports each connected to ground by 10 ohm and each other by
    # 10 ohm: inverse of [[.2,-.1],[-.1,.2]]. Positive and reciprocal.
    impedance = np.linalg.inv(np.array([[.2, -.1], [-.1, .2]]))
    result = spice_multiport(native, devices, impedance, ["d", "g", "s", "b"])
    assert ".SUBCKT cell d g s b" in result
    fields = next(line.split() for line in result.splitlines() if line.startswith("M$"))
    expected = native.splitlines()[1].split()
    assert fields[:4]+fields[5:] == expected[:4]+expected[5:]
    assert fields[4] != expected[4]
    assert "AC {lb_sheet_drive_0}" in result
    with pytest.raises(ValueError, match="body binding"):
        spice_multiport(native, [{**devices[0], "body": "another"}], impedance, ["d", "g", "s", "b"])
    with pytest.raises(ValueError, match="port interfaces"):
        spice_multiport(native, devices, impedance, ["d", "g", "s", "unknown"])


@pytest.mark.parametrize("problem,status", [
    ("passed", "passed"), ("rejected", "failed"), ("crash", "error"),
    ("cleanup", "error"), ("malformed", "error"), ("missing", "error"),
])
def test_sheet_backend_requires_explicit_verdict_and_successful_execution(tmp_path, monkeypatch, problem, status):
    import json

    from benchmarking.eda.backends.substrate import SubstrateSheetDocker
    from benchmarking.evaluation.contracts import Job, JobResult
    from benchmarking.evidence.bundles import publish_bundle
    from benchmarking.execution.tools import ToolResult
    from benchmarking.files import Asset

    class Native:
        def __init__(self, **settings):
            self.settings = {"variables": {}}

        def run(self, job, inputs):
            return JobResult("passed", evidence={n: Asset(b"native", "text")
                                                 for n in ("report.db", "extracted.spice", "layer-map.json")})

    class Tool:
        def __init__(self, *args):
            pass

        def run(self, *args):
            rejected = problem in {"rejected", "crash", "cleanup"}
            verdict = {"status": "failed" if rejected else "passed", "reason": "Invalid power access"}
            files = {"model-check.json": Asset(b"{bad" if problem == "malformed" else json.dumps(verdict).encode(), "json")}
            if problem == "missing":
                files.clear()
            if not rejected:
                files["substrate.spice"] = Asset(b".subckt native\n.ends\n", "spice")
            evidence = {"cleanup_error": Asset(b"cleanup failed", "text")} if problem == "cleanup" else {}
            return ToolResult(1 if problem == "crash" else 0,
                              "Declared tool output is missing: substrate.spice" if rejected else "", files, evidence)

    monkeypatch.setattr("benchmarking.eda.backends.substrate.KLayoutDocker", Native)
    monkeypatch.setattr("benchmarking.eda.backends.substrate.DockerTool", Tool)
    publish_bundle({"body.json": Asset(json.dumps({"extraction_variables": {}, "metals": []}).encode(), "json")}, {}, tmp_path/"support")
    backend = SubstrateSheetDocker(image="unused", support=str(tmp_path/"support"), profile="body.json",
                                   physical_support="unused", physical_profile="unused")
    params = {"top_cell": "cell", "ports": ["p"], "fixture": {"outline_constraint": "bounds"}}
    job = Job("body", "extract", "layout.extract_substrate", (), (("netlist", "spice"),), (), None, json.dumps(params))
    constraints = {"hard": [{"id": "bounds", "type": "bbox_max", "functional_layers": [[1, 0]],
                             "max_width_um": 10, "max_height_um": 10}]}
    result = backend.run(job, {"layout": Asset(b"candidate", "gds"), "netlist": Asset(b"source", "spice"),
                               "constraints": Asset(json.dumps(constraints).encode(), "json")})
    assert result.status == status
    assert bool(result.outputs) == (status == "passed")
