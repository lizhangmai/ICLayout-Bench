"""Check exact fixed-cell geometry and expose only existing terminal landings."""

import json
from pathlib import Path

import pya


def region(cell, info):
    return pya.Region(cell.begin_shapes_rec(cell.layout().layer(info))).merged()


def texts(cell, info):
    result = []
    iterator = cell.begin_shapes_rec(cell.layout().layer(info))
    while not iterator.at_end():
        shape = iterator.shape()
        if shape.is_text():
            text = shape.text.transformed(iterator.trans())
            result.append((text.string, str(text.trans)))
        iterator.next()
    return sorted(result)


def check(candidate, library, specification, top_name):
    if candidate.dbu != library.dbu:
        raise ValueError("Macro library and candidate database units differ")
    top = candidate.cell(top_name)
    if top is None or list(candidate.top_cells()) != [top]:
        raise ValueError("Fixed macros require the declared single top cell")
    if set(specification) != {"macros"} or not specification["macros"]:
        raise ValueError("Fixed macro specification requires a nonempty macro list")
    # Flat copies prevent hierarchical aliasing when a candidate reuses a
    # protected cell as an ancestor of another protected cell.
    flat = pya.Layout()
    flat.dbu = candidate.dbu
    cut = flat.create_cell(top_name)
    cut.copy_tree(top)
    cut.flatten(-1)
    all_layers = set(candidate.layer_infos()) | set(library.layer_infos())
    bound = []
    names = set()
    protected_names = {spec["cell"] for spec in specification["macros"]}
    free = pya.Layout()
    free.dbu = candidate.dbu
    free_top = free.create_cell("FREE")

    def collect(cell, transform):
        for info in candidate.layer_infos():
            for shape in cell.shapes(candidate.layer(info)).each():
                free_top.shapes(free.layer(info)).insert(shape, transform)
        for instance in cell.each_inst():
            child = candidate.cell(instance.cell_index)
            if child.name not in protected_names:
                for element in instance.cell_inst.each_cplx_trans():
                    collect(child, transform * element)

    collect(top, pya.ICplxTrans())
    pose = None
    for spec in specification["macros"]:
        if set(spec) != {"cell", "ports", "translation_dbu", "clearance_dbu", "abstract", "contact_layers"}:
            raise ValueError("Invalid fixed macro declaration")
        name = spec["cell"]
        if name in names:
            raise ValueError("Duplicate fixed macro cell")
        names.add(name)
        source, actual = library.cell(name), candidate.cell(name)
        if source is None or actual is None:
            raise ValueError(f"Missing fixed macro {name}")
        for info in all_layers:
            if not (region(source, info) ^ region(actual, info)).is_empty():
                raise ValueError(f"Changed fixed macro geometry: {name} layer {info}")
            if texts(source, info) != texts(actual, info):
                raise ValueError(f"Changed fixed macro text: {name} layer {info}")
        # Count physical occurrences, including arrays and nested references.
        occurrences = []

        def visit(cell, transform, target_index, found):
            for instance in cell.each_inst():
                for element in instance.cell_inst.each_cplx_trans():
                    absolute = transform * element
                    child = candidate.cell(instance.cell_index)
                    if child.cell_index() == target_index:
                        found.append(absolute)
                    visit(child, absolute, target_index, found)

        visit(top, pya.ICplxTrans(), actual.cell_index(), occurrences)
        if len(occurrences) != 1:
            raise ValueError(f"Fixed macro must occur exactly once: {name}")
        transform = occurrences[0]
        if transform.mag != 1 or transform.angle % 90:
            raise ValueError(f"Fixed macro transform must preserve its manufacturing grid: {name}")
        # Preserve the shared RF ground environment and relative macro poses.
        origin = pya.ICplxTrans(1, 0, False, *spec["translation_dbu"])
        assembly_pose = transform * origin.inverted()
        if pose is None:
            pose = assembly_pose
        elif pose != assembly_pose:
            raise ValueError("Fixed RF assembly relative placement changed")
        if type(spec["abstract"]) is not bool:
            raise ValueError("Fixed macro abstract flag must be boolean")
        if not spec["abstract"]:
            if spec["ports"]:
                raise ValueError("A retained context macro cannot expose abstract terminals")
            bound.append({"cell": name, "transform": str(transform), "ports": []})
            continue
        port_regions = {}
        for port in spec["ports"]:
            if set(port) != {"name", "layer", "text_layers", "box_dbu", "extract"}:
                raise ValueError("Invalid macro port")
            info = pya.LayerInfo(*port["layer"])
            box = pya.Region(pya.Box(*port["box_dbu"]))
            landing = region(source, info) & box
            if landing.is_empty() or landing.count() != 1:
                raise ValueError(f"Macro port needs one connected, existing landing: {name}/{port['name']}")
            if type(port["extract"]) is not bool:
                raise ValueError("Macro terminal extract flag must be boolean")
            if port["extract"]:
                key = tuple(port["layer"])
                port_regions[key] = port_regions.get(key, pya.Region()) + landing
        for info in all_layers:
            body = region(source, info)
            if body.is_empty():
                continue
            keep = port_regions.get((info.layer, info.datatype), pya.Region())
            # Candidate geometry may overlap a terminal landing, but must not
            # duplicate, bridge, or attach to the protected macro body elsewhere.
            entire = region(cut, info)
            world = body.transformed(transform)
            protected = (body - keep).transformed(transform)
            clearance = spec["clearance_dbu"]
            for contact in spec["contact_layers"]:
                if contact["body"] == [info.layer, info.datatype]:
                    for contacting in contact["contacts"]:
                        exterior = region(free_top, pya.LayerInfo(*contacting))
                        if not (exterior & protected.sized(clearance)).is_empty():
                            raise ValueError(f"Candidate conductor enters fixed macro keepout: {name} layer {contacting}")
            cut.shapes(flat.layer(info)).clear()
            cut.shapes(flat.layer(info)).insert((entire - world) + keep.transformed(transform))
        for port in spec["ports"]:
            if not port["extract"]:
                # External fixture-only ports are supplied by the model; the
                # native free circuit must have no attachment to that body.
                for text_layer in port["text_layers"]:
                    for shape in list(cut.shapes(flat.layer(pya.LayerInfo(*text_layer))).each()):
                        if shape.is_text() and shape.text.string == port["name"]:
                            shape.delete()
                continue
            layer = pya.LayerInfo(*port["layer"])
            landing = region(source, layer) & pya.Region(pya.Box(*port["box_dbu"]))
            point = transform * landing.bbox().center()
            if not any(polygon.inside(point) for polygon in landing.transformed(transform).each()):
                raise ValueError(f"Macro port label lies outside its metal: {name}/{port['name']}")
            # The label identifies candidate-proven metal already present in
            # the immutable macro. It never supplies a connection or a device.
            for text_layer in port["text_layers"]:
                cut.shapes(flat.layer(pya.LayerInfo(*text_layer))).insert(
                    pya.Text(port["name"], pya.Trans(point)))
        bound.append({"cell": name, "transform": str(transform), "ports": spec["ports"]})
    # Non-port labels inside fixed cells are forbidden by library authoring;
    # their text is checked above and public terminal labels are retained.
    return flat, bound


def main():
    Path("cut.gds").touch()
    try:
        candidate, library = pya.Layout(), pya.Layout()
        candidate.read("candidate.gds")
        library.read("library.gds")
        specification = json.loads(Path("specification.json").read_text())
        top_name = json.loads(Path("config.json").read_text())["top_cell"]
        cut, macros = check(candidate, library, specification, top_name)
        cut.write("cut.gds")
        result = {"status": "passed", "reason": "", "macros": macros}
    except (ValueError, RuntimeError, KeyError, TypeError) as error:
        result = {"status": "failed", "reason": str(error)}
    Path("result.json").write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
