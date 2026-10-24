"""Validate a uniform candidate line and serialize its trusted process RLC."""

import json
import math
import re
from pathlib import Path


def validate_process(process):
    required = {"kind", "width_um", "ground_width_um", "ground_extension_um",
                "length_min_um", "length_max_um", "sections", "r_dc_ohm_per_um",
                "l_h_per_um", "c_f_per_um", "skin_branches", "calibration"}
    if set(process)-{"ground_slots"} != required or process["kind"] != "uniform-foster-rlc-line-v1":
        raise ValueError("Invalid uniform-line process interface")
    for key in required - {"kind", "skin_branches", "calibration"}:
        value = process[key]
        if type(value) not in {int, float} or not math.isfinite(value) or value <= 0:
            raise ValueError("Invalid uniform-line process value: " + key)
    if (type(process["sections"]) is not int or process["sections"] > 128
            or process["length_min_um"] > process["length_max_um"]
            or process["ground_width_um"] <= process["width_um"]):
        raise ValueError("Invalid uniform-line process geometry")
    if not isinstance(process["skin_branches"], list) or not process["skin_branches"]:
        raise ValueError("Missing conductor-loss interface")
    for branch in process["skin_branches"]:
        if set(branch) != {"r_ohm_per_um", "l_h_per_um"} or any(
                type(v) not in {int, float} or not math.isfinite(v) or v <= 0
                for v in branch.values()):
            raise ValueError("Invalid passive skin branch")
    if "ground_slots" in process:
        slots = process["ground_slots"]
        if set(slots) != {"size_um", "pitch_um", "offset_um"} or any(
                type(v) not in {int, float} or not math.isfinite(v) or v <= 0 for v in slots.values()):
            raise ValueError("Invalid process ground slots")


def render_line_netlist(process, length_um, subcircuit):
    """A passive pi ladder; no dimensions or parameters come from source DUTs."""
    validate_process(process)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", subcircuit):
        raise ValueError("Invalid line subcircuit name")
    if not math.isfinite(length_um) or not process["length_min_um"] <= length_um <= process["length_max_um"]:
        raise ValueError("Line length outside calibrated design range")
    count = process["sections"]
    step = length_um / count
    lines = [f".subckt {subcircuit} A B REF"]
    for i in range(count):
        start, end = ("A" if i == 0 else f"n{i}"), ("B" if i == count-1 else f"n{i+1}")
        cap = process["c_f_per_um"] * step / 2
        lines.extend([f"Cleft{i} {start} REF {cap:.17g}", f"Cright{i} {end} REF {cap:.17g}",
            f"Rdc{i} {start} r{i} {process['r_dc_ohm_per_um']*step:.17g}",
            f"Lext{i} r{i} k{i}_0 {process['l_h_per_um']*step:.17g}"])
        branches = process["skin_branches"]
        for j, branch in enumerate(branches):
            other = end if j == len(branches)-1 else f"k{i}_{j+1}"
            lines.extend([f"Rskin{i}_{j} k{i}_{j} {other} {branch['r_ohm_per_um']*step:.17g}",
                f"Lskin{i}_{j} k{i}_{j} {other} {branch['l_h_per_um']*step:.17g}"])
    return "\n".join([*lines, f".ends {subcircuit}", ""])


def check(candidate, specification, process, top_name, *, extraction=None):
    """Accept one rectangular strip over its complete drawn return plane."""
    import pya

    validate_process(process)
    required = {"cell", "subcircuit", "signal_layer", "ground_layer", "landing_um",
                "window_um", "ports", "conductor_layers", "guard_um", "ground_anchor"}
    if set(specification) != required or len(specification["ports"]) != 3:
        raise ValueError("Invalid candidate-line declaration")
    top = candidate.cell(top_name)
    if top is None or list(candidate.top_cells()) != [top]:
        raise ValueError("Candidate line requires the declared single top cell")
    cell = candidate.cell(specification["cell"])
    if cell is None:
        raise ValueError("Missing designed line cell")
    dbu = candidate.dbu

    def units(value):
        integer = round(value / dbu)
        if not math.isclose(integer*dbu, value, abs_tol=1e-9):
            raise ValueError("Line geometry is off the declared grid")
        return integer

    def region(owner, layer):
        return pya.Region(owner.begin_shapes_rec(owner.layout().layer(*layer))).merged()

    signal = region(cell, specification["signal_layer"])
    box = signal.bbox()
    if (signal.count() != 1 or box.left != 0 or box.bottom != 0
            or not (signal ^ pya.Region(box)).is_empty()
            or box.height() != units(process["width_um"])):
        raise ValueError("Designed line must be one uniform calibrated-width rectangle at local origin")
    landing = units(specification["landing_um"])
    if landing <= 0 or 2*landing >= box.width():
        raise ValueError("Invalid line terminal landings")
    length_um = (box.width()-2*landing)*dbu
    netlist = render_line_netlist(process, length_um, specification["subcircuit"])
    extension = units(process["ground_extension_um"])-landing
    half = units((process["ground_width_um"]-process["width_um"])/2)
    ground_box = pya.Box(-extension, -half, box.right+extension, box.top+half)
    expected_ground = pya.Region(ground_box)
    if "ground_slots" in process:
        slots = process["ground_slots"]
        size, pitch, offset = (units(slots[key]) for key in ("size_um", "pitch_um", "offset_um"))
        for x in range(ground_box.left+offset, ground_box.right-size, pitch):
            for y in range(ground_box.bottom+offset, ground_box.top-size, pitch):
                expected_ground -= pya.Region(pya.Box(x, y, x+size, y+size))
    ground = region(cell, specification["ground_layer"])
    if not (ground ^ expected_ground).is_empty():
        raise ValueError("Designed line return-plane geometry differs from calibrated cross-section")
    allowed = {tuple(specification["signal_layer"]), tuple(specification["ground_layer"])}
    for info in candidate.layer_infos():
        iterator = cell.begin_shapes_rec(candidate.layer(info))
        while not iterator.at_end():
            if iterator.shape().is_text():
                raise ValueError("Designed line cell must not supply net labels")
            iterator.next()
        if (info.layer, info.datatype) not in allowed and not region(cell, [info.layer, info.datatype]).is_empty():
            raise ValueError("Unexpected conductor or label inside designed line cell")
    anchor = specification["ground_anchor"]
    if set(anchor) != {"cell", "point_um"} or len(anchor["point_um"]) != 2:
        raise ValueError("Invalid physical return anchor")
    anchor_cell = candidate.cell(anchor["cell"])
    if anchor_cell is None or anchor_cell == cell:
        raise ValueError("Missing separate fixed ground-anchor cell")
    anchor_point = pya.Point(*[units(v) for v in anchor["point_um"]])
    if not any(polygon.inside(anchor_point) for polygon in region(anchor_cell, specification["ground_layer"]).each()):
        raise ValueError("Return anchor is outside existing fixed ground metal")
    occurrences, anchor_occurrences = [], []

    def visit(owner, transform):
        for instance in owner.each_inst():
            for element in instance.cell_inst.each_cplx_trans():
                absolute = transform * element
                child = candidate.cell(instance.cell_index)
                if child.cell_index() == cell.cell_index():
                    occurrences.append(absolute)
                if child.cell_index() == anchor_cell.cell_index():
                    anchor_occurrences.append(absolute)
                visit(child, absolute)

    visit(top, pya.ICplxTrans())
    if len(occurrences) != 1 or len(anchor_occurrences) != 1:
        raise ValueError("Designed line and fixed ground anchor must occur exactly once")
    transform = occurrences[0]
    if transform.mag != 1 or transform.angle % 90:
        raise ValueError("Designed line transform must preserve its grid")
    physical_return = region(top, specification["ground_layer"])
    return_point = transform*ground_box.center()
    fixed_point = anchor_occurrences[0]*anchor_point
    if not any(polygon.inside(return_point) and polygon.inside(fixed_point)
               for polygon in physical_return.each()):
        raise ValueError("Designed return plane is physically disconnected from the fixed ground anchor")
    window = pya.Box(*[units(v) for v in specification["window_um"]])
    world_ground = pya.Region(ground_box).transformed(transform)
    if not (world_ground-pya.Region(window)).is_empty():
        raise ValueError("Designed line lies outside its isolated design window")
    free = pya.Layout()
    free.dbu = dbu
    exterior = free.create_cell("EXTERIOR")

    def collect(owner, absolute):
        for info in candidate.layer_infos():
            for shape in owner.shapes(candidate.layer(info)).each():
                exterior.shapes(free.layer(info)).insert(shape, absolute)
        for instance in owner.each_inst():
            if instance.cell_index != cell.cell_index():
                for element in instance.cell_inst.each_cplx_trans():
                    collect(candidate.cell(instance.cell_index), absolute*element)

    collect(top, pya.ICplxTrans())
    ends = pya.Region(pya.Box(0, 0, landing, box.top)) + pya.Region(
        pya.Box(box.right-landing, 0, box.right, box.top))
    # Signal terminals may have native vias down to the drawn return plane.
    # Additional return wiring attaches only at the ground-plane end faces.
    protected = pya.Region(ground_box).sized(units(specification["guard_um"]))
    if not (protected.transformed(transform)-pya.Region(window)).is_empty():
        raise ValueError("Designed line isolation guard leaves its design window")
    guard_box = protected.bbox()
    access = pya.Region(pya.Box(guard_box.left, 0, landing, box.top)) + pya.Region(
        pya.Box(box.right-landing, 0, guard_box.right, box.top))
    return_access = pya.Region(pya.Box(guard_box.left, ground_box.bottom,
        ground_box.left+landing, ground_box.top)) + pya.Region(pya.Box(
        ground_box.right-landing, ground_box.bottom, guard_box.right, ground_box.top))
    for layer in specification["conductor_layers"]:
        openings = access.dup()
        if layer == specification["ground_layer"]:
            openings += return_access
        overlap = region(exterior, layer) & (protected-openings).transformed(transform)
        if not overlap.is_empty():
            raise ValueError(f"Unmodeled conductor enters designed-line isolation region: {layer}")
    cut = pya.Layout()
    cut.dbu = dbu
    flat = cut.create_cell(top_name)
    if extraction is not None and extraction.dbu != dbu:
        raise ValueError("Extraction copy changes the candidate database unit")
    flat.copy_tree(top if extraction is None else extraction.cell(top_name))
    flat.flatten(-1)
    li = cut.layer(*specification["signal_layer"])
    all_signal = pya.Region(flat.shapes(li))
    if not (signal.transformed(transform)-all_signal).is_empty():
        raise ValueError("Prior abstraction removed the designed conductor")
    flat.shapes(li).clear()
    flat.shapes(li).insert((all_signal-signal.transformed(transform))+ends.transformed(transform))
    # Preserve actual existing landings and ground. Native LVS independently
    # checks their named connections, including separate return islands.
    for label, point, layer in ((specification["ports"][0], pya.Point(landing//2, box.top//2), specification["signal_layer"]),
            (specification["ports"][1], pya.Point(box.right-landing//2, box.top//2), specification["signal_layer"]),
            (specification["ports"][2], ground_box.center(), specification["ground_layer"])):
        for datatype in (2, 25):
            flat.shapes(cut.layer(layer[0], datatype)).insert(pya.Text(label, pya.Trans(transform*point)))
    return cut, netlist, {"cell": cell.name, "transform": str(transform), "length_um": length_um,
        "width_um": process["width_um"], "return_width_um": process["ground_width_um"]}


def main():
    Path("cut.gds").touch()
    Path("line.spice").touch()
    try:
        import pya

        candidate, extraction = pya.Layout(), pya.Layout()
        candidate.read("original.gds")
        extraction.read("candidate.gds")
        config = json.loads(Path("config.json").read_text())
        process = json.loads(Path("process.json").read_text())
        specification = json.loads(Path("specification.json").read_text())
        cut, netlist, details = check(candidate, specification, process, config["top_cell"], extraction=extraction)
        cut.write("cut.gds")
        Path("line.spice").write_text(netlist)
        result = {"status": "passed", "reason": "", "line": details}
    except (ValueError, RuntimeError, TypeError, KeyError) as error:
        result = {"status": "failed", "reason": str(error)}
    Path("result.json").write_text(json.dumps(result))


if __name__ == "__main__":
    main()
