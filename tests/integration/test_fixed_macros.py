"""Independent rectangle controls for immutable-macro abstraction."""

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.acceptance_eda]


@pytest.fixture
def fixture():
    db = pytest.importorskip("pya")
    from benchmarking.eda._scripts.fixed_macros_runner import check

    library, candidate = db.Layout(), db.Layout()
    library.dbu = candidate.dbu = 0.001
    macro = library.create_cell("PASSIVE")
    macro.shapes(library.layer(134, 0)).insert(db.Box(0, 0, 10000, 2000))
    top = candidate.create_cell("DUT")
    actual = candidate.create_cell("PASSIVE")
    actual.copy_tree(macro)
    top.insert(db.CellInstArray(actual.cell_index(), db.Trans()))
    top.shapes(candidate.layer(134, 0)).insert(db.Box(-2000, 500, 500, 1500))
    spec = {"macros": [{"cell": "PASSIVE", "translation_dbu": [0, 0],
        "abstract": True, "clearance_dbu": 0,
        "contact_layers": [{"body": [134, 0], "contacts": [[134, 0], [133, 0]]}],
        "ports": [{"name": "P1", "layer": [134, 0], "text_layers": [[134, 2], [134, 25]],
                   "box_dbu": [0, 0, 1000, 2000], "extract": True},
                  {"name": "P2", "layer": [134, 0], "text_layers": [[134, 2], [134, 25]],
                   "box_dbu": [9000, 0, 10000, 2000], "extract": True}]}]}
    return db, check, candidate, library, spec


def test_abstraction_removes_only_macro_interior_and_preserves_candidate_wire(fixture):
    db, check, candidate, library, spec = fixture
    cut, _ = check(candidate, library, spec, "DUT")
    actual = db.Region(cut.top_cell().shapes(cut.layer(134, 0)))
    expected = db.Region(db.Box(-2000, 500, 500, 1500))
    expected += db.Region(db.Box(0, 0, 1000, 2000))
    expected += db.Region(db.Box(9000, 0, 10000, 2000))
    assert (actual ^ expected).is_empty()
    assert actual.merged().count() == 2  # The model terminals are not shorted.
    assert db.Region(candidate.top_cell().begin_shapes_rec(candidate.layer(134, 0))).merged().count() == 1


@pytest.mark.parametrize("mutation", ["changed", "duplicate", "overlap", "bridge", "body_via"])
def test_bad_macro_or_unmodelled_body_attachment_is_rejected(fixture, mutation):
    db, check, candidate, library, spec = fixture
    top = candidate.top_cell()
    if mutation == "changed":
        candidate.cell("PASSIVE").shapes(candidate.layer(134, 0)).insert(db.Box(4000, 0, 6000, 3000))
    elif mutation == "duplicate":
        top.insert(db.CellInstArray(candidate.cell("PASSIVE").cell_index(), db.Trans(0, 5000)))
    elif mutation == "overlap":
        # A flattened duplicate must not disappear when the macro is cut.
        top.shapes(candidate.layer(134, 0)).insert(db.Box(0, 0, 10000, 2000))
    elif mutation == "bridge":
        top.shapes(candidate.layer(134, 0)).insert(db.Box(-1000, 500, 11000, 1500))
    else:
        top.shapes(candidate.layer(133, 0)).insert(db.Box(4500, 500, 5500, 1500))
    with pytest.raises(ValueError, match="Changed fixed macro|exactly once|keepout"):
        check(candidate, library, spec, "DUT")


def test_pose_preserves_the_model_ground_context(fixture):
    db, check, candidate, library, spec = fixture
    ground = library.create_cell("GROUND")
    ground.shapes(library.layer(8, 0)).insert(db.Box(-1000, -1000, 11000, 3000))
    actual = candidate.create_cell("GROUND")
    actual.copy_tree(ground)
    candidate.cell("DUT").insert(db.CellInstArray(actual.cell_index(), db.Trans(1, 0)))
    spec["macros"].append({"cell": "GROUND", "translation_dbu": [0, 0],
        "abstract": False, "ports": [], "clearance_dbu": 0, "contact_layers": []})
    with pytest.raises(ValueError, match="relative placement"):
        check(candidate, library, spec, "DUT")
