"""Container-only KLayout rendering of a frozen candidate, without task execution."""

import json
from pathlib import Path

from klayout import db, lay

LONG_EDGE = 4096


def render():
    settings = json.loads(Path("settings.json").read_text())
    view = lay.LayoutView()
    view.set_config("background-color", "#ffffff")
    view.set_config("grid-visible", "false")
    view.set_config("text-visible", "true")
    index = view.load_layout("candidate.gds", False)
    layout = view.cellview(index).layout()
    cell = layout.cell(settings["top_cell"])
    if cell is None or cell.dbbox().empty():
        raise ValueError("Declared top cell is missing or empty")
    view.select_cell(cell.cell_index(), index)
    view.add_missing_layers()
    view.max_hier()
    box = cell.dbbox()
    margin = max(box.width(), box.height()) * 0.04
    target = db.DBox(box.left - margin, box.bottom - margin,
                     box.right + margin, box.top + margin)
    scale = LONG_EDGE / max(target.width(), target.height())
    width, height = max(1, round(target.width() * scale)), max(1, round(target.height() * scale))
    view.save_image_with_options("layout.png", width, height, 0, 2, 0, target, False)
    Path("image.json").write_text(json.dumps({
        "width": width, "height": height, "top_cell": cell.name,
        "bbox_um": [box.left, box.bottom, box.right, box.top],
        "klayout_version": db.__version__, "oversampling": 2,
        "layer_style": "KLayout default colors; all layers visible",
        "layers": [str(layout.get_info(i)) for i in layout.layer_indices()],
    }))


if __name__ == "__main__":
    render()
