"""Prepare an isolated GDS for Magic: label aliases and optional flat geometry."""

import json
from pathlib import Path

from klayout import db

config = json.loads(Path("ports.json").read_text())
layout = db.Layout()
layout.read("candidate.gds")
ignored_labels = 0
if "label_layers" in config:
    for index in layout.layer_indexes():
        info = layout.get_info(index)
        if [info.layer, info.datatype] not in config["label_layers"]:
            for cell in layout.each_cell():
                for shape in list(cell.shapes(index).each()):
                    if shape.is_text():
                        shape.delete()
                        ignored_labels += 1
used = {s.text.string for c in layout.each_cell() for i in layout.layer_indexes()
        for s in c.shapes(i).each() if s.is_text()}
for original, alias in config["aliases"].items():
    if alias in used:
        raise ValueError("Generated extraction alias collides with a layout label")
    for cell in layout.each_cell():
        for index in layout.layer_indexes():
            for shape in cell.shapes(index).each():
                if shape.is_text() and (shape.text.string == original or
                        config.get("case_insensitive", False)
                        and shape.text.string.casefold() == original.casefold()):
                    label = shape.text
                    label.string = alias
                    shape.text = label
report = {"aliases": config["aliases"], "flattened": False,
          "label_layers": config.get("label_layers"), "ignored_labels": ignored_labels}
if "flatten_top" in config:
    top = layout.cell(config["flatten_top"])
    if top is None:
        raise ValueError("Missing extraction top cell")
    regions = {i: db.Region(top.begin_shapes_rec(i)).merged() for i in layout.layer_indexes()}
    top.flatten(True)
    for index, region in regions.items():
        if not (region ^ db.Region(top.begin_shapes_rec(index)).merged()).is_empty():
            raise ValueError("Flattening changed extraction geometry")
    top.write("extraction.gds")
    report.update(flattened=True, geometry_unchanged=True, top_cell=top.name)
else:
    layout.write("extraction.gds")
Path("preparation-check.json").write_text(json.dumps(report))
