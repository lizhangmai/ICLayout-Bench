"""Uniform-line geometry controls with independently calculated DC resistance."""

import copy

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.acceptance_eda]


@pytest.fixture
def line_fixture():
    db = pytest.importorskip("pya")
    process = {"kind": "uniform-foster-rlc-line-v1", "width_um": 2,
        "ground_width_um": 10, "ground_extension_um": 5,
        "length_min_um": 10, "length_max_um": 100, "sections": 4,
        "r_dc_ohm_per_um": .1, "l_h_per_um": 1e-12, "c_f_per_um": 1e-15,
        "skin_branches": [{"r_ohm_per_um": .2, "l_h_per_um": 1e-12}], "calibration": {}}
    layout = db.Layout()
    layout.dbu = .001
    top, cell = layout.create_cell("DUT"), layout.create_cell("LINE")
    cell.shapes(layout.layer(134, 0)).insert(db.Box(0, 0, 44000, 2000))
    cell.shapes(layout.layer(8, 0)).insert(db.Box(-3000, -4000, 47000, 6000))
    top.insert(db.CellInstArray(cell.cell_index(), db.Trans(100000, 100000)))
    anchor = layout.create_cell("GROUND")
    anchor.shapes(layout.layer(8, 0)).insert(db.Box(55000, 96000, 65000, 106000))
    top.insert(db.CellInstArray(anchor.cell_index(), db.Trans()))
    top.shapes(layout.layer(8, 0)).insert(db.Box(60000, 100000, 98000, 102000))
    spec = {"cell": "LINE", "subcircuit": "MODELED_LINE", "signal_layer": [134, 0],
        "ground_layer": [8, 0], "landing_um": 2, "guard_um": 1,
        "window_um": [50, 50, 250, 200], "ports": ["A", "B", "REF"],
        "conductor_layers": [[8, 0], [30, 0], [134, 0], [133, 0]]}
    spec["ground_anchor"] = {"cell": "GROUND", "point_um": [60, 101]}
    return db, layout, spec, process


def test_line_cut_preserves_existing_landings_and_ground(line_fixture):
    from benchmarking.eda._scripts.rlc_line_runner import check

    db, candidate, spec, process = line_fixture
    # The earlier fixed-macro abstraction flattens its copy. Geometry must
    # still be read from the original candidate's physical LINE occurrence.
    extraction = db.Layout()
    extraction.dbu = candidate.dbu
    root = extraction.create_cell("DUT")
    root.copy_tree(candidate.top_cell())
    root.flatten(-1)
    cut, netlist, dimensions = check(candidate, spec, process, "DUT", extraction=extraction)
    assert dimensions["length_um"] == 40
    expected = db.Region(db.Box(100000, 100000, 102000, 102000))
    expected += db.Region(db.Box(142000, 100000, 144000, 102000))
    actual = db.Region(cut.top_cell().shapes(cut.layer(134, 0)))
    assert (actual ^ expected).is_empty()
    original_ground = db.Region(candidate.top_cell().begin_shapes_rec(candidate.layer(8, 0)))
    assert (db.Region(cut.top_cell().shapes(cut.layer(8, 0))) ^ original_ground).is_empty()
    # At DC every ideal inductor shorts its parallel skin resistor. The
    # remaining four series resistors must total rho*length/(width*thickness).
    rdc = [float(row.split()[-1]) for row in netlist.splitlines() if row.startswith("Rdc")]
    assert sum(rdc) == pytest.approx(.1 * 40)


@pytest.mark.parametrize("mutation", ["width", "return", "branch", "intermediate", "label", "duplicate"])
def test_unmodeled_line_geometry_is_rejected(line_fixture, mutation):
    from benchmarking.eda._scripts.rlc_line_runner import check

    db, layout, spec, process = line_fixture
    top, cell = layout.top_cell(), layout.cell("LINE")
    if mutation == "width":
        cell.shapes(layout.layer(134, 0)).insert(db.Box(0, 0, 44000, 3000))
    elif mutation == "return":
        cell.shapes(layout.layer(8, 0)).clear()
    elif mutation == "branch":
        top.shapes(layout.layer(134, 0)).insert(db.Box(120000, 101000, 121000, 110000))
    elif mutation == "intermediate":
        top.shapes(layout.layer(30, 0)).insert(db.Box(120000, 100000, 121000, 101000))
    elif mutation == "label":
        cell.shapes(layout.layer(134, 25)).insert(db.Text("GND", db.Trans()))
    else:
        top.insert(db.CellInstArray(cell.cell_index(), db.Trans(180000, 100000)))
    with pytest.raises(ValueError):
        check(layout, spec, process, "DUT")


def test_changed_length_changes_electrical_model_and_remains_bounded(line_fixture):
    from benchmarking.eda._scripts.rlc_line_runner import render_line_netlist

    _, _, _, process = line_fixture
    first = render_line_netlist(process, 20, "LINE")
    second = render_line_netlist(process, 80, "LINE")
    totals = [sum(float(r.split()[-1]) for r in value.splitlines() if r.startswith("Rdc"))
              for value in (first, second)]
    assert totals == pytest.approx([2, 8])
    for length in (0, 101, float("nan")):
        with pytest.raises(ValueError):
            render_line_netlist(process, length, "LINE")
    broken = copy.deepcopy(process)
    broken["skin_branches"][0]["l_h_per_um"] = -1
    with pytest.raises(ValueError, match="passive"):
        render_line_netlist(broken, 20, "LINE")


def test_label_cannot_replace_a_physical_return_path(line_fixture):
    from benchmarking.eda._scripts.rlc_line_runner import check

    db, layout, spec, process = line_fixture
    top = layout.top_cell()
    metal = top.shapes(layout.layer(8, 0))
    remaining = db.Region(metal) - db.Region(db.Box(80000, 99000, 85000, 103000))
    metal.clear()
    metal.insert(remaining)
    top.shapes(layout.layer(8, 25)).insert(db.Text("REF", db.Trans(110000, 101000)))
    with pytest.raises(ValueError, match="physically disconnected"):
        check(layout, spec, process, "DUT")
