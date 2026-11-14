"""Validate explicit native component hierarchy before EM partitioning.

The candidate carries port geometry and native PCell parameters. Regeneration
is used only for comparison; field geometry is taken from the frozen candidate.
"""

import importlib
import json
import math
import os
import re
import sys
from collections import Counter
from pathlib import Path

from klayout import db


def metadata(layout):
    """Read short, explicit EM setup records from the physical top cell."""
    if len(layout.top_cells()) != 1:
        raise ValueError("EM setup requires one physical top cell")
    result, headers = {"devices": [], "ports": []}, 0
    for shape in layout.top_cell().shapes(layout.layer(1000, 0)).each():
        if not shape.is_text():
            raise ValueError("GDS 1000/0 is reserved for EM setup texts")
        value = shape.text.string
        if value == "EM_LAYOUT_V1":
            headers += 1
        elif value.startswith("EM_DEVICE_V1 "):
            result["devices"].append(json.loads(value[len("EM_DEVICE_V1 "):]))
        elif value.startswith("EM_PORT_V1 "):
            result["ports"].append(json.loads(value[len("EM_PORT_V1 "):]))
        else:
            raise ValueError("Unknown EM setup text on GDS 1000/0")
    if headers != 1 or not result["devices"] or not result["ports"]:
        raise ValueError("Expected one EM_LAYOUT_V1 header, devices and ports on GDS 1000/0")
    return result


def native_library(directory, module, name, technology):
    """Load the reviewed PDK's own generator and its own technology data."""
    directory = Path(directory).resolve()
    sys.path[:0] = [str(directory / "python"),
                   str(directory / "python/pycell4klayout-api/source/python")]
    os.environ["KLAYOUT"] = "1"
    os.environ["KLAYOUT_PATH"] = str(directory)
    importlib.import_module(module)
    library = db.Library.library_by_name(name, technology)
    if library is None:
        raise ValueError("Native PDK cell library was not registered")
    return library


def shapes(cell):
    """Compare native polygons and texts, independently of cell naming."""
    layout = cell.layout()
    regions, texts = {}, Counter()
    for index in layout.layer_indexes():
        info = layout.get_info(index)
        pair = info.layer, info.datatype
        region = db.Region(cell.begin_shapes_rec(index))
        if not region.is_empty():
            regions[pair] = region
        iterator = cell.begin_shapes_rec(index)
        while not iterator.at_end():
            shape = iterator.shape()
            if shape.is_text():
                texts[pair, str(shape.text.transformed(iterator.trans()))] += 1
            iterator.next()
    return regions, texts


def check_parameters(parameters):
    """Only scalar values; never pass candidate programs to a PDK generator."""
    if not isinstance(parameters, dict) or len(parameters) > 128:
        raise ValueError("Invalid native PCell parameters")
    for key, value in parameters.items():
        if (not isinstance(key, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", key)
                or type(value) not in {str, bool, int, float}):
            raise ValueError("Native PCell parameters must be named scalar values")
        if type(value) in {int, float} and not math.isfinite(value):
            raise ValueError("Nonfinite native PCell parameter")
        if isinstance(value, str) and (len(value) > 128 or "__" in value
                or not re.fullmatch(r"[A-Za-z0-9_.!+&= /-]*", value)):
            raise ValueError("Native PCell parameters cannot contain programs or expressions")


def generate_cells(declaration, config, output):
    """Generate comparison cells without reading or loading a candidate GDS.

    Run this in a separate process. Registering a native library must never
    regenerate or normalize a submitted cell through saved PCell context.
    """
    library = native_library(config["directory"], config["module"], config["library"],
                             config["technology"])
    expected_layout = db.Layout()
    expected_layout.dbu = config["dbu"]
    expected_layout.technology_name = config["technology"]
    names = {}
    for item in declaration["devices"]:
        check_parameters(item["parameters"])
        expected = expected_layout.create_cell(item["pcell"], library.name(), item["parameters"])
        if expected is None or not expected.is_pcell_variant():
            raise ValueError(f"Unknown native PCell {item['pcell']}")
        if not item["parameters"].keys() <= expected.pcell_parameters_by_name().keys():
            raise ValueError("Unknown native PCell parameter")
        names[item["cell"]] = expected.cell_index()
    # Stream owned, static cells under stable names. Native proxy names may
    # change when another variant is created or a library is streamed.
    exported = db.Layout()
    exported.dbu = expected_layout.dbu
    for number, (key, index) in enumerate(names.items()):
        cell = exported.create_cell(f"EM_NATIVE_{number}")
        cell.copy_tree(expected_layout.cell(index))
        cell.flatten(True)
        names[key] = cell.name
    options = db.SaveLayoutOptions()
    options.write_context_info = False
    exported.write(str(output), options)
    return names


def pin_regions(cell, terminal):
    """Read native pin polygons using the PCell's own terminal label."""
    regions, _ = shapes(cell)
    points = []
    for index in cell.layout().layer_indexes():
        iterator = cell.begin_shapes_rec(index)
        while not iterator.at_end():
            shape = iterator.shape()
            if shape.is_text() and shape.text.string == terminal:
                points.append(shape.text.transformed(iterator.itrans()).trans.disp)
            iterator.next()
    selected = {}
    for pair, region in regions.items():
        if pair[1] != 2:
            continue
        pins = db.Region()
        for polygon in region.each():
            if any(polygon.inside(point) for point in points):
                pins.insert(polygon)
        if not pins.is_empty():
            selected[pair] = pins
    if not selected:
        raise ValueError(f"Native PCell has no named pin geometry for {terminal}")
    return selected


def validate_cells(layout, declaration, expected_layout, expected_names):
    """Require each declared wrapper to contain one unchanged native PCell.

    Both layouts are read as frozen geometry, without registering a library.
    """
    if layout.dbu != expected_layout.dbu:
        raise ValueError("Native comparison database units differ from the candidate")
    names, result = set(), {}
    for item in declaration["devices"]:
        if (not isinstance(item, dict) or set(item) != {"cell", "pcell", "parameters"}
                or not isinstance(item["cell"], str) or not isinstance(item["pcell"], str)
                or item["cell"] in names):
            raise ValueError("Invalid or duplicate native component declaration")
        check_parameters(item["parameters"])
        names.add(item["cell"])
        wrapper = layout.cell(item["cell"])
        if wrapper is None:
            raise ValueError(f"Missing native component wrapper {item['cell']}")
        instances = list(wrapper.each_inst())
        if (len(instances) != 1 or instances[0].is_regular_array()
                or not instances[0].cplx_trans.is_unity()):
            raise ValueError("A component wrapper requires one native cell at its local origin")
        for index in layout.layer_indexes():
            if not wrapper.shapes(index).is_empty():
                raise ValueError("Place EM markers and routing outside the native component wrapper")
        expected = expected_layout.cell(expected_names[item["cell"]])
        if expected is None:
            raise ValueError("Native comparison cell is missing")
        actual = layout.cell(instances[0].cell_index)
        actual_regions, actual_texts = shapes(actual)
        expected_regions, expected_texts = shapes(expected)
        if (actual_texts != expected_texts or actual_regions.keys() != expected_regions.keys()
                or any(not (actual_regions[pair] ^ expected_regions[pair]).is_empty()
                       for pair in actual_regions)):
            raise ValueError(f"Component {item['cell']} differs from its native PCell")
        result[item["cell"]] = {"wrapper": wrapper, "instance": instances[0], "native": actual,
                                "pcell": item["pcell"]}
    return result


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] != "generate":
        raise SystemExit("Only the isolated native comparison-cell generator is available")
    values = json.loads(Path("cells.json").read_text())
    names = generate_cells(values["declaration"], values["config"], "expected.gds")
    Path("expected.json").write_text(json.dumps(names))
