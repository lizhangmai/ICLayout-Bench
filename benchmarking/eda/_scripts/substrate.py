"""Native geometry to a passive, reciprocal projected body multiport.

No vertical silicon transport, depletion network or signal-wire RC is inferred.
All MOS parameters and non-body connectivity come from native extraction.
"""

import json
import math
import re
from itertools import pairwise
from pathlib import Path

import klayout.db as k
import numpy as np
from scipy.sparse import coo_matrix, csc_matrix
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import splu


class CandidateRejected(ValueError):
    """The submitted geometry violates an explicitly supported model boundary."""


def grid_edges(ids, axes, resistance):
    x, y = axes
    dx, dy = np.diff(x).astype(float), np.diff(y).astype(float)
    resistance = np.broadcast_to(resistance, ids.shape)
    a = np.r_[ids[:, :-1].ravel(), ids[:-1].ravel()]
    b = np.r_[ids[:, 1:].ravel(), ids[1:].ravel()]
    gx = dy[:, None] / ((resistance[:, :-1]*dx[:-1] + resistance[:, 1:]*dx[1:])/2)
    gy = dx[None, :] / ((resistance[:-1]*dy[:-1, None] + resistance[1:]*dy[1:, None])/2)
    valid = (a >= 0) & (b >= 0)
    return a[valid], b[valid], np.r_[gx.ravel(), gy.ravel()][valid]


def geometry(config):
    model, fixture = config["model"], config["fixture"]
    layout = k.Layout()
    layout.read("candidate.gds")
    cell = layout.cell(config["top_cell"])
    if cell is None:
        raise ValueError("Missing requested cell")
    cell.flatten(True)
    dbu = layout.dbu
    regions = {name: k.Region(cell.begin_shapes_rec(layout.layer(*pair))).merged()
               for name, pair in model["layers"].items()}
    for metal in model["metals"]:
        regions[metal["name"]] = k.Region(cell.begin_shapes_rec(layout.layer(*metal["layer"]))).merged()
    for via in model["vias"]:
        regions[via["name"]] = k.Region(cell.begin_shapes_rec(layout.layer(*via["layer"]))).merged()
    outline = k.Region()
    for pair in fixture["functional_layers"]:
        outline += k.Region(cell.begin_shapes_rec(layout.layer(*pair)))
    bbox = outline.bbox()
    if bbox.empty() or bbox.width()*dbu > fixture["window_um"][0]+1e-9 or bbox.height()*dbu > fixture["window_um"][1]+1e-9:
        raise CandidateRejected("Functional geometry does not fit the declared integration window")
    # Registration removes translation freedom only. Shape, size and orientation
    # remain submitted choices. Preserve integer coordinates at the native DBU.
    offset = bbox.center()
    move = k.Trans(-offset.x, -offset.y)
    regions = {name: region.transformed(move) for name, region in regions.items()}
    if not ((regions["active"] & regions["pplus"]).sized(1) & regions["active"] & regions["nplus"]).is_empty():
        raise CandidateRejected("Projected body sheets require separated opposite-implant diffusion; butted salicide is outside this model")
    bbox = bbox.transformed(move)
    database = k.LayoutVsSchematic()
    database.read("native.db")
    circuit = database.netlist().top_circuit()
    if circuit is None or any(circuit.each_subcircuit()):
        raise ValueError("Body model requires a flat primitive native circuit")
    layer_map = json.loads(Path("layers.json").read_text())
    power = {}
    rails = set(fixture["domain_rails"].values())
    for metal in model["metals"]:
        index = database.layer_index(database.layer_by_name(layer_map[metal["name"]]))
        power[metal["name"]] = k.Region()
        for net in circuit.each_net():
            if net.name.casefold() in rails:
                power[metal["name"]] += database.polygons_of_net(net, index)
        power[metal["name"]] = power[metal["name"]].merged().transformed(move)
        if not (power[metal["name"]] - regions[metal["name"]]).is_empty():
            raise ValueError("Extracted power metal lies outside the submitted geometry")
    channels = list((regions["active"] & regions["poly"]).merged().each())
    devices, patches = [], []
    for device in circuit.each_device():
        cls = device.device_class()
        if cls.name not in model["body_domains"]:
            raise ValueError(f"Unsupported primitive in projected body model: {cls.name}")
        point = k.Point(round(device.trans.disp.x/dbu)-offset.x, round(device.trans.disp.y/dbu)-offset.y)
        matches = [p for p in channels if p.inside(point)]
        if len(matches) != 1:
            raise ValueError("Primitive MOS centre does not identify one physical channel")
        patch = k.Region(matches[0])
        if not math.isclose(patch.area()*dbu**2, device.parameter("W")*device.parameter("L"), rel_tol=1e-7):
            raise ValueError("Native MOS dimensions disagree with its channel footprint")
        in_well = (patch & regions["well"]).area() == patch.area()
        if in_well != (model["body_domains"][cls.name] == "well"):
            raise ValueError("Native model polarity disagrees with its physical well")
        body = device.net_for_terminal("B").expanded_name()
        if body.casefold() != fixture["domain_rails"][model["body_domains"][cls.name]]:
            raise ValueError("Unsupported body rail or disconnected body")
        patches.append(patch)
        devices.append({"id": device.id(), "model": cls.name, "body": body,
                        "well": in_well, "position_um": [point.x*dbu, point.y*dbu],
                        "parameters": {p.name: device.parameter(p.name) for p in cls.parameter_definitions()}})
    if len(channels) != len(patches) or len({str(p) for p in patches}) != len(channels):
        raise ValueError("Primitive channel coverage is incomplete or ambiguous")
    ground = {m["name"]: k.Region() for m in model["metals"]}
    found = set()
    for metal in model["metals"]:
        for pair in metal["labels"]:
            for shape in cell.shapes(layout.layer(*pair)).each():
                if shape.is_text() and shape.text.string.casefold() in rails:
                    name = shape.text.string.casefold()
                    if name in found:
                        raise CandidateRejected("Each body supply requires exactly one external power-pin label")
                    radius = round(fixture["pin_window_um"]/2/dbu)
                    x, y = shape.text.x-offset.x, shape.text.y-offset.y
                    patch = k.Region(k.Box(x-radius, y-radius, x+radius, y+radius))
                    if (patch & power[metal["name"]]).area() != patch.area():
                        raise CandidateRejected("Power terminal has no declared metal access window")
                    ground[metal["name"]] += patch
                    found.add(name)
    if found != rails:
        raise CandidateRejected("Missing power terminal labels")
    return {"regions": regions, "power": power, "ground": ground, "devices": devices,
            "patches": patches, "bbox": bbox, "dbu": dbu,
            "registration_um": [-offset.x*dbu, -offset.y*dbu]}


def environment(g, config):
    model, fixture, dbu = config["model"], config["fixture"], g["dbu"]
    unit = lambda value: round(value/dbu)
    regions, power, ground = g["regions"], g["power"], g["ground"]
    radius, width = unit(fixture["return_half_um"]), unit(fixture["return_width_um"])
    outer = k.Region(k.Box(-radius, -radius, radius, radius))
    outer -= k.Region(k.Box(-radius+width, -radius+width, radius-width, radius-width))
    regions["active"] += outer
    regions["pplus"] += outer
    power[model["metals"][0]["name"]] += outer
    ground[model["metals"][0]["name"]] += k.Region(k.Box(-radius, -unit(.5), -radius+width, unit(.5)))
    pitch, cut = unit(fixture["return_pitch_um"]), unit(model["contact_size_um"])
    contacts = k.Region()
    for x in range(-radius+pitch, radius-pitch+1, pitch):
        for y in [-radius+width//2, radius-width//2]:
            contacts.insert(k.Box(x-cut//2, y-cut//2, x+cut//2, y+cut//2))
    for y in range(-radius+pitch, radius-pitch+1, pitch):
        for x in [-radius+width//2, radius-width//2]:
            contacts.insert(k.Box(x-cut//2, y-cut//2, x+cut//2, y+cut//2))
    regions["contact"] += contacts
    half = unit(fixture["domain_half_um"])
    domain = k.Region(k.Box(-half, -half, half, half))
    sources = []
    for box in fixture["psub_boxes_um"]:
        patch = k.Region(k.Box(*(unit(v) for v in box)))
        if not (patch & regions["well"]).is_empty():
            raise ValueError("External substrate excitation intersects a candidate well")
        sources.append(patch)
    bands = [k.Region() for _ in range(4)]
    well_regions = []
    band = unit(fixture["well_band_um"])
    # Every actual connected well containing MOS bodies receives the same four
    # boundary experiments; unused well shapes cannot dilute the injected current.
    for polygon in regions["well"].each():
        well = k.Region(polygon)
        if not any(d["well"] and (p & well).area() == p.area() for d, p in zip(g["devices"], g["patches"], strict=True)):
            continue
        b = polygon.bbox()
        strips = [k.Box(b.left, b.bottom, min(b.right, b.left+band), b.top),
                  k.Box(max(b.left, b.right-band), b.bottom, b.right, b.top),
                  k.Box(b.left, b.bottom, b.right, min(b.top, b.bottom+band)),
                  k.Box(b.left, max(b.bottom, b.top-band), b.right, b.top)]
        for index, strip in enumerate(strips):
            bands[index] += well & k.Region(strip)
        well_regions.append(well)
    if not well_regions or any(b.is_empty() for b in bands):
        raise ValueError("No active well boundary for the declared interference test")
    sources.extend(bands)
    if any(not (source-domain).is_empty() for source in sources):
        raise ValueError("Excitation outside numerical domain")
    return domain, sources


def transport(g, config, step):
    model, fixture, dbu = config["model"], config["fixture"], g["dbu"]
    regions, power, ground = g["regions"], g["power"], g["ground"]
    domain, sources = g["domain"], g["sources"]
    well = regions["well"]
    taps = [(regions["active"] & regions["pplus"])-well, regions["active"] & regions["nplus"] & well]
    contacts = [regions["contact"] & tap & power[model["metals"][0]["name"]] for tap in taps]
    vias = [regions[v["name"]] & power[v["lower"]] & power[v["upper"]] for v in model["vias"]]
    relevant = [domain, well, *taps, *power.values(), *ground.values(), *contacts, *vias, *g["patches"], *sources]
    xs, ys = set(), set()
    for region in relevant:
        for polygon in region.decompose_trapezoids_to_region().each():
            b = polygon.bbox()
            if polygon.area() != b.area():
                raise CandidateRejected("Projected sheet model supports Manhattan boundaries only")
            xs.update([b.left, b.right])
            ys.update([b.bottom, b.top])
    def axis(features, lower, upper, fine_lower, fine_upper):
        features = features | {lower, upper, fine_lower, fine_upper}
        distance = round(4/dbu)
        while fine_upper+distance < upper or fine_lower-distance > lower:
            features.update([max(lower, fine_lower-distance), min(upper, fine_upper+distance)])
            distance *= 2
        anchors = sorted(features | {lower, upper, fine_lower, fine_upper})
        if anchors[0] < lower or anchors[-1] > upper:
            raise ValueError("Conductor geometry lies outside fixed numerical domain")
        points = []
        for a, b in pairwise(anchors):
            distance = max(0, fine_lower-b, a-fine_upper)
            pitch = max(step/dbu, .15*distance)
            points.extend(np.rint(np.linspace(a, b, math.ceil((b-a)/pitch)+1)[:-1]).astype(int))
        return np.unique([*points, upper])
    bounds, fine = domain.bbox(), g["bbox"].enlarged(round(2/dbu))
    ax = axis(xs, bounds.left, bounds.right, fine.left, fine.right)
    ay = axis(ys, bounds.bottom, bounds.top, fine.bottom, fine.top)
    shape = (len(ay)-1, len(ax)-1)
    if np.prod(shape) > fixture["max_grid_cells"]:
        raise ValueError("Declared projected model grid budget exceeded")
    def raster(region):
        mask = np.zeros(shape, dtype=bool)
        for polygon in region.decompose_trapezoids_to_region().each():
            b = polygon.bbox()
            ix, iy = np.searchsorted(ax, [b.left, b.right]), np.searchsorted(ay, [b.bottom, b.top])
            if not np.array_equal(ax[ix], [b.left, b.right]) or not np.array_equal(ay[iy], [b.bottom, b.top]):
                raise ValueError("Material boundaries do not align with grid")
            mask[iy[0]:iy[1], ix[0]:ix[1]] = True
        return mask
    area = np.diff(ay)[:, None]*np.diff(ax)[None, :]
    kinds = raster(well)
    bulk = np.arange(np.prod(shape)).reshape(shape)
    rs = model["resistance_ohm"]
    resistance = np.where(kinds, rs["well"], rs["substrate"])
    for index, tap in enumerate(taps):
        resistance[raster(tap)] = 1/(1/rs["well" if index else "substrate"]+1/rs["nplus" if index else "pplus"])
    a, b, conductance = grid_edges(bulk, (ax, ay), resistance)
    same = kinds.ravel()[a] == kinds.ravel()[b]
    edges, ids = [(a[same], b[same], conductance[same])], {"bulk": bulk}
    count, fixed = bulk.size, []
    for metal in model["metals"]:
        name = metal["name"]
        mask = raster(power[name])
        layer_ids = np.full(shape, -1, dtype=int)
        layer_ids[mask] = count+np.arange(int(mask.sum()))
        ids[name] = layer_ids
        count += int(mask.sum())
        edges.append(grid_edges(layer_ids, (ax, ay), rs[name]))
        fixed.extend(layer_ids[raster(ground[name]) & mask])
    bridges = [(contacts[i], model["contact_size_um"], rs["ncontact" if i else "pcontact"],
                "bulk", model["metals"][0]["name"]) for i in range(2)]
    bridges.extend((r, v["size_um"], rs[v["name"]], v["lower"], v["upper"])
                   for r, v in zip(vias, model["vias"], strict=True))
    for region, size, resistance, lower, upper in bridges:
        cut_area = (size/dbu)**2
        if any(not math.isclose(p.area(), cut_area, rel_tol=1e-9) for p in region.each()):
            raise ValueError("Unsupported contact/via footprint")
        mask = raster(region)
        a, b = ids[lower][mask], ids[upper][mask]
        if np.any(a < 0) or np.any(b < 0):
            raise ValueError("Cut does not bridge two retained conductors")
        edges.append((a, b, area[mask]/(resistance*cut_area)))
    a, b, conductance = (np.concatenate([e[i] for e in edges]) for i in range(3))
    matrix = coo_matrix((np.r_[conductance, conductance, -conductance, -conductance],
                         (np.r_[a, b, a, b], np.r_[a, b, b, a])), shape=(count, count)).tocsc()
    _, components = connected_components(matrix, directed=False)
    fixed = np.unique(fixed)
    grounded = np.isin(components, np.unique(components[fixed]))
    free = grounded.copy()
    free[fixed] = False
    rows, columns, weights = [], [], []
    for index, patch in enumerate(g["patches"]+sources):
        mask = raster(patch)
        kind = g["devices"][index]["well"] if index < len(g["devices"]) else index-len(g["devices"]) >= 4
        if not np.any(mask) or not np.all(kinds[mask] == kind) or not np.all(grounded[bulk[mask]]):
            raise CandidateRejected("Body or excitation has wrong domain or lacks a physical return")
        rows.extend(bulk[mask])
        columns.extend([index]*int(mask.sum()))
        weights.extend(area[mask]/area[mask].sum())
    loads = csc_matrix((weights, (rows, columns)), shape=(count, len(g["devices"])+len(sources)))
    factor = splu(matrix[free][:, free])
    response = factor.solve(loads[free].toarray())
    impedance = np.asarray(loads[free].T @ response)
    reciprocity = float(np.max(abs(impedance-impedance.T))/np.max(abs(impedance)))
    kcl = float(np.max(abs(matrix[free][:, free] @ response-loads[free].toarray())))
    returned = float(np.max(abs(np.asarray(matrix[fixed][:, free] @ response).sum(axis=0)+1)))
    eigenvalue = float(np.linalg.eigvalsh((impedance+impedance.T)/2)[0])
    if reciprocity > 1e-9 or kcl > 1e-6 or returned > 1e-6 or eigenvalue <= 0:
        raise ValueError("Body multiport failed reciprocity, conservation or passivity")
    return impedance, {"unknowns": int(free.sum()), "grid_shape": list(shape),
                       "reciprocity_error": reciprocity, "kcl_error_per_amp": kcl,
                       "return_error_per_amp": returned, "minimum_eigenvalue_ohm": eigenvalue,
                       "contact_counts": [c.count() for c in contacts], "via_counts": [v.count() for v in vias]}


def spice_multiport(original, devices, impedance, ports):
    """Stamp V_body - V_rail = Z I with native SPICE current sensors/CCVS.

    This is an exact multiport realization, including native nonlinear body
    currents. Unlike applying precomputed voltages, it keeps feedback loading.
    Only MOS B nodes change; model names and literal parameters are preserved.
    """
    if "lb_sheet_" in original.casefold():
        raise ValueError("Reserved body-model namespace collision")
    by_id = {d["id"]: i for i, d in enumerate(devices)}
    lines, seen = [], set()
    logical = re.sub(r"\n\+", " ", original)
    for line in logical.splitlines():
        fields = line.split()
        if fields and fields[0].casefold() == ".subckt":
            native = {p.casefold(): p for p in fields[2:]}
            if len(native) != len(ports) or set(native) != {p.casefold() for p in ports}:
                raise ValueError("Native and declared port interfaces differ")
            line = " ".join(fields[:2]+[native[p.casefold()] for p in ports])
        elif fields and fields[0].startswith("M$"):
            index = by_id[int(fields[0][2:])]
            if fields[4].casefold() != devices[index]["body"].casefold() or fields[5] != devices[index]["model"]:
                raise ValueError("Native body binding disagrees with emitted primitive")
            fields[4] = f"lb_sheet_body_{index}"
            line = " ".join(fields)
            seen.add(index)
        elif fields and fields[0].casefold() == ".ends":
            for index, device in enumerate(devices):
                lines.append(f"Vlb_sheet_body_{index} lb_sheet_body_{index} lb_sheet_sum_{index}_0 0")
                for j in range(impedance.shape[1]):
                    ref = device["body"] if j == impedance.shape[1]-1 else f"lb_sheet_sum_{index}_{j+1}"
                    sensor = f"Vlb_sheet_body_{j}" if j < len(devices) else f"Vlb_sheet_inj_{j-len(devices)}"
                    lines.append(f"Hlb_sheet_{index}_{j} lb_sheet_sum_{index}_{j} {ref} {sensor} {impedance[index,j]:.17g}")
            for j in range(impedance.shape[1]-len(devices)):
                lines.extend([f"Vlb_sheet_inj_{j} lb_sheet_source_{j} 0 0",
                              f"Ilb_sheet_inj_{j} 0 lb_sheet_source_{j} DC 0 AC {{lb_sheet_drive_{j}}}"])
        lines.append(line)
    if seen != set(range(len(devices))):
        raise ValueError("Incomplete native primitive body binding")
    return "\n".join(lines)+"\n"


def mesh_comparison(coarse, fine, bodies):
    """Retain column-scaled errors and distinguish the rows used by the circuit."""
    scopes = {"all_ports": (0, len(fine), 0, len(fine)),
              "body_response": (0, bodies, 0, len(fine)),
              "body_loading": (0, bodies, 0, bodies),
              "excitation_to_body": (0, bodies, bodies, len(fine))}
    result = {}
    for name, (r0, r1, c0, c1) in scopes.items():
        old, new = coarse[r0:r1, c0:c1], fine[r0:r1, c0:c1]
        difference = abs(new-old)
        scales = np.max(abs(new), axis=0)
        delta = np.max(difference, axis=0)
        relative = np.divide(delta, scales, out=np.zeros_like(delta), where=scales > 0)
        relative[(scales == 0) & (delta > 0)] = np.inf
        column = int(relative.argmax())
        row = int(difference[:, column].argmax())
        finite = lambda value: float(value) if np.isfinite(value) else None
        result[name] = {"relative_change": finite(relative[column]),
                        "column_relative_changes": [finite(v) for v in relative],
                        "column_start": c0, "row": row+r0, "column": column+c0,
                        "coarse_ohm": float(old[row, column]), "fine_ohm": float(new[row, column]),
                        "column_scale_ohm": float(scales[column]),
                        "max_abs_change_ohm": float(delta[column])}
    return result


def main():
    config = json.loads(Path("config.json").read_text())
    fixture = config["fixture"]
    if (len(fixture["psub_boxes_um"]) != 4 or not 0 < fixture["well_band_um"]
            or not 0 < fixture["return_half_um"] < fixture["domain_half_um"]
            or not 0 < min(fixture["mesh_steps_um"])):
        raise ValueError("Invalid projected-sheet fixture")
    g = geometry(config)
    g["domain"], g["sources"] = environment(g, config)
    runs, meshes, last = [], [], None
    ports = [{"kind": "device_body", "name": f"M${d['id']}:{d['model']}:B",
              "device_id": d["id"], "position_um": d["position_um"]} for d in g["devices"]]
    ports.extend({"kind": "excitation", "name": f"substrate_source_{i}", "box_um": box}
                 for i, box in enumerate(fixture["psub_boxes_um"]))
    ports.extend({"kind": "excitation", "name": f"well_{direction}"}
                 for direction in ("west", "east", "south", "north"))
    evidence = {"model": "projected_ohmic_sheet", "registration_um": g["registration_um"],
                "devices": g["devices"], "ports": ports, "runs": runs,
                "requested_mesh_steps_um": fixture["mesh_steps_um"],
                "mesh_tolerance": fixture["mesh_tolerance"], "mesh_converged": None,
                "source_areas_um2": [s.area()*g["dbu"]**2 for s in g["sources"]],
                "scope": "Native MOS, finite body contacts/power metal; ideal signal wires, no vertical transport."}

    def retain():
        Path("audit.json").write_text(json.dumps(evidence, indent=2, allow_nan=False))
        if meshes:
            np.savez_compressed("impedance.npz", impedance_ohm=meshes[-1], mesh_impedance_ohm=meshes,
                                mesh_steps_um=[r["step_um"] for r in runs])

    for step in fixture["mesh_steps_um"]:
        evidence["current_step_um"] = step
        retain()
        impedance, audit = transport(g, config, step)
        if last is not None:
            audit["mesh_comparison"] = mesh_comparison(last, impedance, len(g["devices"]))
            audit["mesh_column_change"] = audit["mesh_comparison"]["all_ports"]["relative_change"]
        runs.append({"step_um": step, **audit})
        meshes.append(impedance)
        last = impedance
        retain()
    change = runs[-1].get("mesh_column_change")
    evidence["mesh_converged"] = change is not None and change <= fixture["mesh_tolerance"]
    retain()
    if not evidence["mesh_converged"]:
        if len(runs) >= 2 and change is not None:
            comparison = runs[-1]["mesh_comparison"]
            worst = comparison["all_ports"]
            body = comparison["body_response"]["relative_change"]
            reason = (f"Projected body multiport has not converged: mesh change {100*change:.6g}% exceeds "
                      f"{100*fixture['mesh_tolerance']:g}% ({runs[-2]['step_um']:g} -> {step:g} um); "
                      f"row {worst['row']} ({ports[worst['row']]['name']}), "
                      f"column {worst['column']} ({ports[worst['column']]['name']}); "
                      f"body-response change {100*body:.6g}%" if body is not None else
                      "Projected body multiport has an unbounded body-response mesh change")
        else:
            reason = "Projected body multiport requires two finite meshes to establish convergence"
        Path("model-check.json").write_text(json.dumps({"status": "error", "code": "mesh_not_converged",
                                                        "reason": reason, "mesh_tolerance": fixture["mesh_tolerance"]}))
        return
    derived = spice_multiport(Path("native.spice").read_text(), g["devices"], last, config["ports"])
    Path("substrate.spice").write_text(derived)
    Path("model-check.json").write_text(json.dumps({"status": "passed", "reason": ""}))


if __name__ == "__main__":
    try:
        main()
    except CandidateRejected as error:
        Path("model-check.json").write_text(json.dumps({"status": "failed", "reason": str(error)}))
