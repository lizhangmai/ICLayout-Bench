"""Place a trusted external fixture around a translated, unchanged candidate."""

import json
from pathlib import Path

from klayout import db


def prepare(config):
    candidate, fixture = db.Layout(), db.Layout()
    candidate.read("candidate.gds")
    fixture.read("fixture.gds")
    top, external = candidate.cell(config["top_cell"]), fixture.cell(config["fixture_top"])
    if top is None or external is None or candidate.dbu != fixture.dbu:
        raise ValueError("Fixture/candidate top or database unit mismatch")
    if any(cell.cell_index() != top.cell_index()
           and cell.name.casefold() == config["extracted_top"].casefold() for cell in candidate.each_cell()):
        return {"status": "failed", "reason": "Candidate uses a reserved extraction cell name"}
    top.flatten(True)
    constraints = json.loads(Path("constraints.json").read_text())
    outlines = [s for s in constraints["hard"] if s["id"] == config["outline_constraint"] and s["type"] == "bbox_max"]
    if len(outlines) != 1:
        raise ValueError("Fixture alignment requires one declared bounding-box constraint")
    bounds = db.Box()
    for pair in outlines[0]["functional_layers"]:
        region = db.Region(top.begin_shapes_rec(candidate.layer(*pair)))
        if not region.is_empty():
            bounds += region.bbox()
    if bounds.empty():
        raise ValueError("Empty candidate functional geometry")
    for pair in config.get("excluded_layers", []):
        if not db.Region(top.begin_shapes_rec(candidate.layer(*pair))).is_empty():
            return {"status": "failed", "reason": "Candidate uses a layer outside the declared extraction scope"}
    labels = {s.text.string.casefold() for i in candidate.layer_indexes()
              for s in top.shapes(i).each() if s.is_text()}
    if labels & {name.casefold() for name in config["fixture_ports"]}:
        return {"status": "failed", "reason": "Candidate uses a reserved external-fixture label"}
    original = {candidate.get_info(i).to_s(): db.Region(top.begin_shapes_rec(i)).merged()
                for i in candidate.layer_indexes()}
    center = bounds.center()
    shift = db.Trans(-center.x, -center.y)
    top.transform(shift)
    for i in candidate.layer_indexes():
        expected = original[candidate.get_info(i).to_s()].transformed(shift)
        if not (expected ^ db.Region(top.begin_shapes_rec(i)).merged()).is_empty():
            raise ValueError("Fixture alignment changed candidate geometry")
    for info in fixture.layer_infos():
        added = db.Region(external.begin_shapes_rec(fixture.layer(info))).merged()
        existing = db.Region(top.begin_shapes_rec(candidate.layer(info))).merged()
        if not (added & existing).is_empty():
            return {"status": "failed", "reason": "External fixture overlaps candidate geometry"}
    name = "TRUSTED_EXTERNAL_FIXTURE"
    while candidate.cell(name) is not None:
        name += "_"
    imported = candidate.create_cell(name)
    imported.copy_tree(external)
    top.insert(db.CellInstArray(imported.cell_index(), db.Trans()))
    top.flatten(True)
    top.name = config["extracted_top"]
    top.write("combined.gds")
    return {"status": "passed", "reason": "", "candidate_geometry_unchanged": True,
            "translation_dbu": [-center.x, -center.y], "dbu_um": candidate.dbu,
            "functional_bbox_dbu": [bounds.left, bounds.bottom, bounds.right, bounds.top]}


if __name__ == "__main__":
    try:
        result = prepare(json.loads(Path("fixture.json").read_text()))
    except Exception as error:  # noqa: BLE001 -- retain native preparation failures
        result = {"status": "error", "reason": f"{type(error).__name__}: {error}"}
    Path("result.json").write_text(json.dumps(result))
