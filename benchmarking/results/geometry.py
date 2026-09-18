"""Optional, offline geometry extraction; viewing the stored output needs no EDA runtime."""

import json
import re
import xml.etree.ElementTree as ET


def extract(path, top_cell, *, max_shapes=200_000):
    from klayout import db

    layout = db.Layout()
    layout.read(str(path))
    cell = layout.cell(top_cell) if top_cell else layout.top_cell()
    if cell is None:
        raise ValueError("Layout top cell is missing")
    box = cell.dbbox()
    layers, count = [], 0
    for index in layout.layer_indices():
        polygons, texts = [], []
        iterator = cell.begin_shapes_rec(index)
        while not iterator.at_end():
            shape, transform = iterator.shape(), iterator.trans()
            if shape.is_text():
                text = shape.text.transformed(transform)
                texts.append(
                    {
                        "x": text.x * layout.dbu,
                        "y": text.y * layout.dbu,
                        "text": text.string,
                    }
                )
            elif shape.is_polygon() or shape.is_box() or shape.is_path():
                polygon = (
                    shape.path.polygon() if shape.is_path() else shape.polygon
                ).transformed(transform)
                rings = [
                    [
                        [p.x * layout.dbu, p.y * layout.dbu]
                        for p in polygon.each_point_hull()
                    ]
                ]
                rings += [
                    [
                        [p.x * layout.dbu, p.y * layout.dbu]
                        for p in polygon.each_point_hole(i)
                    ]
                    for i in range(polygon.holes())
                ]
                polygons.append(rings)
                count += 1
                if count > max_shapes:
                    raise ValueError(
                        "Geometry exceeds interactive shape limit; use PNG or download GDS"
                    )
            iterator.next()
        if polygons or texts:
            layers.append(
                {
                    "name": str(layout.get_info(index)),
                    "polygons": polygons,
                    "texts": texts,
                }
            )
    return {
        "bbox": [box.left, box.bottom, box.right, box.top],
        "unit": "um",
        "top_cell": cell.name,
        "layers": layers,
        "shapes": count,
    }


def drc_markers(raw):
    root = ET.fromstring(raw)
    markers = []
    for item in root.findall(".//items/item"):
        for value in item.findall("./values/value"):
            text = value.text or ""
            if not text.startswith(("polygon:", "box:", "edge:", "edge-pair:")):
                continue
            coords = re.findall(r"([-+\d.eE]+)\s*,\s*([-+\d.eE]+)", text)
            if coords:
                points = [[float(x), float(y)] for x, y in coords]
                if text.startswith("box:") and len(points) == 2:
                    (x0, y0), (x1, y1) = points
                    points = [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]
                elif text.startswith("polygon:"):
                    points.append(points[0])
                markers.append(
                    {
                        "category": item.findtext("category"),
                        "cell": item.findtext("cell"),
                        "points": points,
                    }
                )
    return markers


def attach_geometry(store, *, run_id=None):
    rows = [{"id": run_id}] if run_id else store.list_runs(limit=1_000_000)["items"]
    results = []
    for row in rows:
        detail = store.detail(row["id"])
        files = {a["name"]: a for a in detail["artifacts"]}
        try:
            candidate = files["final.gds"]
            geometry = extract(
                store.artifact(candidate["sha256"]), detail["data"].get("top_cell")
            )
            geometry["candidate_sha256"] = candidate["sha256"]
            store.attach(
                detail["evaluation"]["id"],
                "layout.geometry.json",
                json.dumps(geometry).encode(),
            )
            markers = []
            for name, artifact in files.items():
                if name.startswith("evaluation/drc-") and name.endswith(".db"):
                    try:
                        markers.extend(
                            drc_markers(store.artifact(artifact["sha256"]).read_bytes())
                        )
                    except (ValueError, ET.ParseError):
                        continue
            store.attach(
                detail["evaluation"]["id"],
                "layout.drc.json",
                json.dumps(markers).encode(),
            )
            results.append(
                {
                    "run_id": row["id"],
                    "status": "complete",
                    "shapes": geometry["shapes"],
                    "markers": len(markers),
                }
            )
        except (ValueError, KeyError, RuntimeError) as error:
            results.append(
                {"run_id": row["id"], "status": "unavailable", "reason": str(error)}
            )
    return results
