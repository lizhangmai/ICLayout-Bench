"""Native component and port validation for physical-GDS EM co-simulation."""

import json
import math
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from klayout import db


def native_metals(config):
    import importlib

    sys.path.insert(0, str(Path("support", config["workflow"]).resolve().parent))
    workflow = importlib.import_module(Path(config["workflow"]).name)
    return workflow.stackup_reader.read_substrate(
        str(Path("support", config["stackup"]).resolve()))[2]


def reference_metal(config, metals):
    metal = metals.getbylayername(config["reference_layer"])
    if metal is None or not math.isclose(metal.zmin, metal.zmax, abs_tol=1e-9):
        raise ValueError("The declared compact reference must be a native sheet layer")
    return metal


def terminal_region(geometry, device, terminal):
    return sum(geometry.shapes_of_terminal(device.terminal_ref(terminal)).values(), db.Region())


def bulk_terminals(geometry, tech, circuit):
    """Use native layer purposes to identify compact-model well terminals."""
    result = set()
    for device in circuit.each_device():
        for terminal in device.device_class().terminal_definitions():
            purposes = []
            for index in geometry.shapes_of_terminal(device.terminal_ref(terminal.id())):
                layer = tech.computed_layer_info_by_name.get(geometry.layer_name(index))
                if layer is None:
                    purposes.append(None)
                    continue
                value = layer.layer_info
                enum = value.DESCRIPTOR.fields_by_name["purpose"].enum_type
                purposes.append(enum.values_by_number[value.purpose].name)
            if purposes and all(p in {"PURPOSE_PWELL", "PURPOSE_NWELL", "PURPOSE_DNWELL"}
                                for p in purposes):
                result.add((device.id(), terminal.id()))
    return result


def fixtures(config):
    """Consume fixed components already proved by the immutable-macro gate."""
    models = config.get("fixtures", {})
    if not models:
        return {}
    proof = json.loads(Path("derivation.json").read_text())
    actual = {item["cell"]: item for item in proof["macros"] if item["ports"]}
    if set(actual) != set(models) or any(
            not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)
            for name in models.values()):
        raise ValueError("EM fixture models differ from the proved physical macro assembly")
    return actual


def assemble(geometry, tech, config, connections):
    """Keep native devices and bind their declared RF ports through bias tees.

    The DC branch uses native extracted connectivity. All compact models stay
    in the circuit exactly once. The EM branch supplies interconnect behavior;
    no expected schematic is used to add or restore a device or a connection.
    """
    from klayout_pex.klayout.netlist_printer import NetlistHeader, NetlistPrinter

    for name in ("dc_inductance", "dc_block_capacitance"):
        if type(config[name]) not in {float, int} or not math.isfinite(config[name]) or config[name] <= 0:
            raise ValueError("Invalid declared DC/RF bias-tee value")
    circuit = geometry.netlist().circuit_by_name(config["top_cell"])
    if not list(circuit.each_pin()):
        for name in config["ports"]:
            matches = [net for net in circuit.each_net() if net.name == name]
            if len(matches) != 1:
                raise ValueError(f"EM interface has no unique native GDS net {name}")
            circuit.connect_pin(circuit.create_pin(name), matches[0])
    devices = {device.id(): device for device in circuit.each_device()}
    pins = {pin.name(): (pin, circuit.net_for_pin(pin.id())) for pin in circuit.each_pin()}
    if set(pins) != set(config["ports"]) or config["substrate"] not in pins:
        raise ValueError("Native circuit ports differ from the declared interface")
    ground = pins[config["substrate"]][1]
    fixed = fixtures(config)
    public = config.get("external_ports", config["ports"])
    outside = {p["name"] for item in fixed.values() for p in item["ports"] if not p["extract"]}
    if (len(public) != len(set(public)) or config["substrate"] not in public
            or set(public) - set(pins) != outside):
        raise ValueError("Public EM ports must be native circuit or proved fixture terminals")
    bulk = bulk_terminals(geometry, tech, circuit)
    compact = {key: device for key, device in devices.items()
               if device.device_class().name in config["compact_models"]}
    required = {(device.id(), terminal.id()) for device in compact.values()
                for terminal in device.device_class().terminal_definitions()} - bulk
    required_fixed = {(name, port["name"]) for name, item in fixed.items()
                      for port in item["ports"] if port["extract"] and port["name"] != config["substrate"]}
    bound, external, fixed_ports, groups = {}, {}, {}, {}
    if [entry["number"] for entry in connections] != list(range(1, len(connections) + 1)):
        raise ValueError("EM circuit port numbers must be ordered and complete")
    for entry in connections:
        number = entry["number"]
        if "device" in entry:
            key = entry["device"], entry["terminal"]
            if key not in required or key in bound:
                raise ValueError("Invalid or duplicate compact-device EM terminal")
            bound[key] = number
            groups[number] = devices[key[0]].net_for_terminal(key[1]).cluster_id
        elif "fixture" in entry:
            key = entry["fixture"], entry["terminal"]
            if key not in required_fixed or key in fixed_ports or key[1] not in pins:
                raise ValueError("Invalid or duplicate fixed-macro EM terminal")
            fixed_ports[key] = number
            groups[number] = pins[key[1]][1].cluster_id
        else:
            name = entry["external"]
            if name not in set(public) & set(pins) or name == config["substrate"] or name in external:
                raise ValueError("Invalid or duplicate external EM port")
            external[name] = number
            groups[number] = pins[name][1].cluster_id
    if (set(bound) != required or set(external) != set(public) & set(pins) - {config["substrate"]}
            or set(fixed_ports) != required_fixed):
        raise ValueError("EM ports do not cover every physical terminal and external port")
    for device_id, terminal_id in bulk:
        if devices[device_id].net_for_terminal(terminal_id).cluster_id != ground.cluster_id:
            raise ValueError("This EM boundary requires wells tied to the declared substrate port")

    printer = NetlistPrinter(NetlistHeader("0.9.0", "Native device extraction",
        tech.tech.name, datetime.now()), tech.device_models)
    printer.write(geometry.netlist(), "candidate-native.spice")
    # Give the extracted DC wiring a separate namespace. External RF pin names
    # and intrinsic model values remain the native circuit's named interface.
    for net in circuit.each_net():
        net.name = config["substrate"] if net.cluster_id == ground.cluster_id else f"dc_n{net.cluster_id}"
    inserted, rf_nodes = [], {}
    def node(net):
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", net.name):
            raise ValueError("EM assembly requires ordinary SPICE interface names")
        return net.name
    common = node(ground)
    inductance = f"{config['dc_inductance']:.12g}"
    capacitance = f"{config['dc_block_capacitance']:.12g}"
    for pin in sorted(circuit.each_pin(), key=lambda pin: pin.id(), reverse=True):
        circuit.remove_pin(pin.id())
    public_nodes = {}
    for name in public:
        rf_net = ground if name == config["substrate"] else circuit.create_net(name)
        circuit.connect_pin(circuit.create_pin(name), rf_net)
        public_nodes[name] = node(rf_net)
        if name not in external:
            continue
        native_net = pins[name][1]
        number = external[name]
        rf_nodes[number] = node(rf_net)
        inserted.append(f"Lem_dc_{number} {node(rf_net)} {node(native_net)} {inductance}")
    for index, (name, item) in enumerate(fixed.items()):
        terminals = []
        for port in item["ports"]:
            if port["name"] == config["substrate"]:
                terminals.append(common)
                continue
            if not port["extract"]:
                terminals.append(public_nodes[port["name"]])
                continue
            number = fixed_ports[name, port["name"]]
            native_net = pins[port["name"]][1]
            rf_nodes[number] = f"emfixture_{index}_{number}"
            terminals.append(rf_nodes[number])
            inserted.append(f"Lem_dc_{number} {rf_nodes[number]} {node(native_net)} {inductance}")
        inserted.append(f"Xem_fixture_{index} {' '.join(terminals)} {common} {config['fixtures'][name]}")
    for device_id, terminal_id in sorted(required):
        device = devices[device_id]
        native_net = device.net_for_terminal(terminal_id)
        rf_net = circuit.create_net(f"emdev_{device_id}_{terminal_id}")
        device.connect_terminal(terminal_id, rf_net)
        number = bound[device_id, terminal_id]
        rf_nodes[number] = node(rf_net)
        inserted.append(f"Lem_dc_{number} {node(rf_net)} {node(native_net)} {inductance}")
    for number in range(1, len(connections) + 1):
        inserted.append(f"Cem_block_{number} {rf_nodes[number]} em_p{number} {capacitance}")
    inserted.append("Xem_network " + " ".join(f"em_p{i} {common}" for i in
        range(1, len(connections) + 1)) + " EM_NETWORK")
    printer.write(geometry.netlist(), "native-models.spice")
    content = Path("native-models.spice").read_text()
    pattern = re.compile(r"(?im)^\.ENDS\s+" + re.escape(config["top_cell"]) + r"\s*$")
    content, count = pattern.subn(lambda match: "\n".join(inserted) + "\n" + match[0], content)
    if count != 1:
        raise ValueError("Native model output does not contain exactly one DUT boundary")
    if wrapper := config.get("fixture_wrapper"):
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", wrapper) or wrapper == config["top_cell"]:
            raise ValueError("Invalid native fixture-wrapper name")
        interface = " ".join(public)
        content += f"\n.SUBCKT {wrapper} {interface}\nXem_core {interface} {config['top_cell']}\n.ENDS {wrapper}\n"
    Path("circuit.spice").write_text(content)
    return {"ports": len(connections), "devices": len(devices),
            "compact_devices": len(compact),
            "ideal_wire_groups": groups, "substrate_group": ground.cluster_id,
            "dc_scope": "Native models and ideal extracted DC wires. Field-modeled passives remain only on the DC side of the bias tees."}


def placements(layout, cells):
    """Find every occurrence; a declared compact component is one physical instance."""
    found = {name: [] for name in cells}

    def visit(cell, transform):
        if cell.name in found:
            if transform.mag != 1 or transform.angle % 90:
                raise ValueError("Compact components require orthogonal unit-scale placements")
            found[cell.name].append(transform)
            return
        for instance in cell.each_inst():
            for element in instance.cell_inst.each_cplx_trans():
                visit(layout.cell(instance.cell_index), transform * element)

    visit(layout.top_cell(), db.ICplxTrans())
    if any(len(values) != 1 for values in found.values()):
        raise ValueError("Each compact component wrapper must occur exactly once")
    return {name: values[0] for name, values in found.items()}



def write_field_gds(layout, filename):
    """Serialize multi-hole material without ambiguous bridged GDS contours.

    Native KLayout trapezoids preserve the same planar region. Keep an
    original contour if integer-grid decomposition cannot preserve it exactly.
    Port sheets, paths, labels and all component boundaries remain intact.
    """
    top = layout.top_cell()
    encoded = 0
    for index in layout.layer_indices():
        container = top.shapes(index)
        for shape in list(container.each()):
            if not shape.is_polygon():
                continue
            region = db.Region(shape.polygon).merged()
            if not any(polygon.holes() > 1 for polygon in region.each()):
                continue
            pieces = [piece for polygon in region.each()
                      for piece in polygon.decompose_trapezoids(db.Polygon.TD_simple)]
            if not (region ^ db.Region(pieces)).is_empty():
                continue
            container.erase(shape)
            for piece in pieces:
                container.insert(piece)
            encoded += 1
    layout.write(filename)
    return encoded


def partition(layout, physical, geometry, config, cells):
    """Subtract only verified native compact bodies; retain physical passives and wires."""
    from native_cells import shapes

    poses = placements(layout, cells)
    circuit = geometry.netlist().circuit_by_name(config["top_cell"])
    compact, seen, bodies = {}, set(), {}
    models = {pcell: model for model, pcell in config["model_cells"].items()}
    for name, cell in cells.items():
        pose = poses[name]
        bounds = cell["native"].bbox().transformed(pose)
        model = models.get(cell["pcell"])
        if model is None:
            raise ValueError("A component wrapper uses an undeclared native PCell factory")
        matches = []
        for device in circuit.each_device():
            if device.device_class().name != model:
                continue
            body = sum((terminal_region(geometry, device, terminal.id())
                        for terminal in device.device_class().terminal_definitions()), db.Region())
            if (not body.is_empty()
                    and (db.Region(body.bbox()) - db.Region(bounds)).is_empty()):
                matches.append(device)
        if len(matches) != 1 or matches[0].id() in seen:
            raise ValueError(f"Component wrapper {name} does not contain one unique native device")
        device = matches[0]
        seen.add(device.id())
        if model in config["compact_models"]:
            compact[name] = device
            native, _ = shapes(cell["native"])
            bodies[name] = {pair: region.transformed(pose) for pair, region in native.items()}
    expected = {d.id() for d in circuit.each_device()
                if d.device_class().name in config["model_cells"]}
    if seen != expected:
        raise ValueError("Every model with a declared native cell factory requires its own unchanged wrapper")
    unsupported = {d.device_class().name for d in circuit.each_device()} - set(
        config["compact_models"] + config["field_models"])
    if unsupported:
        raise ValueError(f"Devices outside the declared native EM capability: {sorted(unsupported)}")
    field = db.Layout()
    field.dbu = physical.dbu
    top = field.create_cell(config["top_cell"])
    top.copy_tree(physical.top_cell())
    top.flatten(True)
    for regions in bodies.values():
        for pair, body in regions.items():
            index = field.layer(*pair)
            material = db.Region(top.begin_shapes_rec(index)) - body
            top.shapes(index).clear()
            top.shapes(index).insert(material)
    footprint = sum((db.Region(cells[name]["native"].bbox()).transformed(poses[name])
                     for name in compact), db.Region()).merged()
    reference_layer = int(reference_metal(config, native_metals(config)).layernum)
    reference = db.Region(top.begin_shapes_rec(field.layer(reference_layer, 0)))
    if not (reference ^ footprint).is_empty():
        raise ValueError("The native reference sheet must equal the verified compact-component footprints")
    return field, compact, bodies


def net_materials(geometry, tech, net):
    """Use native extracted connectivity to identify material at a port plane."""
    result = {}
    for index in geometry.layer_indexes():
        pair = tech.gds_pair_for_computed_layer_name.get(geometry.layer_name(index))
        if pair is None or pair[1] != 0:
            continue
        region = geometry.shapes_of_net(net, geometry.layer_by_index(index), True)
        result[pair] = result.get(pair, db.Region()) + region
    return result


def ports_for_circuit(layout, field, geometry, tech, declaration, compact, config):
    """Verify native via/in-plane sources against physical signal and ground faces."""
    from native_cells import pin_regions

    metals = native_metals(config)
    reference_layer = int(reference_metal(config, metals).layernum)
    poses = placements(layout, compact)
    circuit = geometry.netlist().circuit_by_name(config["top_cell"])
    ground = circuit.net_by_name(config["substrate"])
    if ground is None:
        raise ValueError("Missing physical substrate net")
    ground_materials = net_materials(geometry, tech, ground)
    fixed = fixtures(config)
    public = config.get("external_ports", config["ports"])
    field_materials = {int(m.layernum): db.Region(field.top_cell().begin_shapes_rec(
        field.layer(int(m.layernum), 0))) for m in metals.metals}
    native_ports, connections, layers = [], [], set()

    def surface(materials, height):
        return sum((region & field_materials.get(pair[0], db.Region())
                    for pair, region in materials.items()
                    if (metal := metals.getbylayernumber(pair[0])) is not None
                    and (math.isclose(metal.zmin, height, abs_tol=1e-7)
                         or math.isclose(metal.zmax, height, abs_tol=1e-7))), db.Region())

    for port in declaration["ports"]:
        common = {"number", "source_layer", "impedance", "direction", "connection"}
        via = "target_layer" not in port
        required = common | ({"from_layer", "to_layer"} if via else {"target_layer"})
        directions = {"z", "-z"} if via else {"x", "-x", "y", "-y"}
        if not isinstance(port, dict) or set(port) != required or port["direction"] not in directions:
            raise ValueError("Circuit EM ports require explicit native source and reference planes")
        number, layer = port["number"], port["source_layer"]
        if (number != len(native_ports) + 1 or type(layer) is not int or layer in layers
                or not 0 < layer < 65536 or layer == 1000
                or metals.getbylayernumber(layer) is not None):
            raise ValueError("EM ports require consecutive numbers and distinct nonmaterial GDS layers")
        layers.add(layer)
        marker = db.Region(layout.top_cell().begin_shapes_rec(layout.layer(layer, 0))).merged()
        if marker.is_empty():
            raise ValueError("Circuit ports require finite-xy-area native marker polygons")
        # The native workflow uses each polygon's bounding box as the source.
        if any(not polygon.is_box() for polygon in marker.each()):
            raise ValueError("Circuit EM port markers must be rectangular")
        if via:
            low, high = [metals.getbylayername(port[key]) for key in ("from_layer", "to_layer")]
            if low is None or high is None:
                raise ValueError("An EM port refers to a layer absent from the native stackup")
            if low.zmin > high.zmin:
                low, high = high, low
            if low.zmax >= high.zmin:
                raise ValueError("An EM via port requires a finite physical gap")
            positive, negative = ((high.zmin, low.zmax) if port["direction"] == "z"
                                  else (low.zmax, high.zmin))
            positive_face, negative_face = marker, marker
            zlow, zhigh = low.zmax, high.zmin

            def electrode(materials, height):
                return surface(materials, height)

            artificial_reference = int(low.layernum) == reference_layer or int(high.layernum) == reference_layer
        else:
            target = metals.getbylayername(port["target_layer"])
            if target is None or target.is_via or target.zmin >= target.zmax:
                raise ValueError("In-plane EM port requires a native conductor with finite thickness")
            positive = negative = None
            positive_face, negative_face = db.Edges(), db.Edges()
            for polygon in marker.each():
                box = polygon.bbox()
                if port["direction"].endswith("x"):
                    left = db.Edge(box.left, box.bottom, box.left, box.top)
                    right = db.Edge(box.right, box.bottom, box.right, box.top)
                else:
                    left = db.Edge(box.left, box.bottom, box.right, box.bottom)
                    right = db.Edge(box.left, box.top, box.right, box.top)
                p, n = (left, right) if port["direction"].startswith("-") else (right, left)
                positive_face.insert(p)
                negative_face.insert(n)
            zlow, zhigh = target.zmin, target.zmax
            artificial_reference = False

            def electrode(materials, height, target_layer=int(target.layernum)):
                return materials.get((target_layer, 0), db.Region()) & field_materials[target_layer]

        def covered(face, region):
            return (face - (face & region)).is_empty()

        connection = port["connection"]
        if set(connection) == {"device", "terminal"}:
            device = compact.get(connection["device"])
            if device is None:
                raise ValueError("EM port refers to an undeclared compact component")
            terminal = device.device_class().terminal_id(connection["terminal"])
            if terminal is None or terminal < 0:
                raise ValueError("EM port refers to an unknown native device terminal")
            net = device.net_for_terminal(terminal)
            named_pins = {pair: region.transformed(poses[connection["device"]])
                for pair, region in pin_regions(layout.cell(connection["device"]), connection["terminal"]).items()}
            pin = sum((region for pair, region in named_pins.items()
                       if pair[1] == 2 and (metal := metals.getbylayernumber(pair[0])) is not None
                       and ((not via and int(metal.layernum) == int(target.layernum))
                            or (via and (math.isclose(metal.zmin, positive, abs_tol=1e-7)
                                         or math.isclose(metal.zmax, positive, abs_tol=1e-7))))), db.Region())
            if not covered(positive_face, pin):
                raise ValueError("Compact EM port does not lie on its native pin surface")
            reference = field_materials.get(reference_layer, db.Region()) if artificial_reference else electrode(ground_materials, negative)
            connections.append({"number": number, "device": device.id(), "terminal": terminal})
        elif set(connection) == {"fixture", "terminal"}:
            item = fixed.get(connection["fixture"])
            matches = [] if item is None else [p for p in item["ports"]
                if p["name"] == connection["terminal"] and p["extract"]]
            if len(matches) != 1:
                raise ValueError("Unknown proved fixture EM terminal")
            port_spec = matches[0]
            landing = metals.getbylayernumber(port_spec["layer"][0])
            if (landing is None or port_spec["layer"][1] != 0 or
                    (via and not (math.isclose(landing.zmin, positive, abs_tol=1e-7)
                                  or math.isclose(landing.zmax, positive, abs_tol=1e-7))) or
                    (not via and int(target.layernum) != int(landing.layernum))):
                raise ValueError("Fixture EM signal plane differs from its proved native landing layer")
            envelope = db.Region(db.Box(*port_spec["box_dbu"])).transformed(
                db.ICplxTrans.from_s(item["transform"]))
            if not covered(positive_face, envelope):
                raise ValueError("Fixture EM port lies outside its proved native landing")
            net = circuit.net_by_name(port_spec["name"])
            if net is None:
                raise ValueError("Fixed fixture terminal has no native candidate net")
            reference = electrode(ground_materials, negative)
            connections.append({"number": number, "fixture": connection["fixture"],
                                "terminal": connection["terminal"]})
        elif set(connection) == {"external"}:
            name = connection["external"]
            if name not in public or name == config["substrate"]:
                raise ValueError("Unknown external EM interface port")
            net = circuit.net_by_name(name)
            if net is None:
                raise ValueError("External EM port is absent from native physical connectivity")
            reference = electrode(ground_materials, negative)
            connections.append({"number": number, "external": name})
        else:
            raise ValueError("Invalid EM circuit connection declaration")
        if not covered(positive_face, electrode(net_materials(geometry, tech, net), positive)):
            raise ValueError(f"EM port {number} signal face is not on the declared physical net")
        if not covered(negative_face, reference):
            raise ValueError(f"EM port {number} reference face is not on its physical ground")
        for metal in metals.metals:
            if (metal.zmin < zhigh - 1e-7 and metal.zmax > zlow + 1e-7
                    and not (marker & field_materials[int(metal.layernum)]).is_empty()):
                raise ValueError(f"EM port {number} gap intersects physical material {metal.name}")
        native_ports.append({key: value for key, value in port.items() if key != "connection"})
    return native_ports, connections


def prepare(config):
    from native_cells import metadata, validate_cells
    from native_kpex import native_geometry

    if config["process"]["variables"].get("no_simplify") != "true":
        raise ValueError("EM partitioning requires native extraction without device merging")
    physical, original = db.Layout(), db.Layout()
    physical.read("candidate.gds")
    original.read("original.gds" if Path("original.gds").exists() else "candidate.gds")
    if (len(physical.top_cells()) != 1 or len(original.top_cells()) != 1
            or original.top_cell().name != config["top_cell"] or physical.dbu != original.dbu):
        raise ValueError("EM input layouts differ from the declared physical interface")
    declaration = metadata(original)
    Path("cells.json").write_text(json.dumps({"declaration": declaration,
        "config": {**config["generator"], "dbu": original.dbu}}))
    subprocess.run([sys.executable, "native_cells.py", "generate"], check=True)
    expected = db.Layout()
    expected.read("expected.gds")
    cells = validate_cells(original, declaration, expected,
                           json.loads(Path("expected.json").read_text()))
    # First check the maintained extractor against the independent successful
    # LVS database using its ordinary native simplification. Then extract the
    # same frozen geometry without merging physical components for partitioning.
    comparison_config = {**config, "process": {**config["process"], "variables": {
        **config["process"]["variables"], "no_simplify": "false"}}}
    comparison, _ = native_geometry(comparison_config)
    database = db.LayoutVsSchematic()
    database.read("candidate.lvsdb")
    comparison.reference = database.netlist().dup()
    comparison.compare(db.NetlistComparer())
    pairs = list(comparison.xref().each_circuit_pair())
    if not pairs or any(pair.status() != db.NetlistCrossReference.Match for pair in pairs):
        raise ValueError("Native EM geometry extraction differs from the independent candidate LVS")
    geometry, tech = native_geometry(config)
    field, compact, _bodies = partition(original, physical, geometry, config, cells)
    ports, connections = ports_for_circuit(original, field, geometry, tech, declaration,
                                           compact, config)
    details = assemble(geometry, tech, config, connections)
    if config.get("fixture_wrapper"):
        wrapper = re.escape(config["fixture_wrapper"])
        # Replace only the supplied fixture harness. Device definitions and
        # every native table/model outside that harness remain byte-for-byte.
        models = Path("models.spice").read_text()
        pattern = re.compile(r"(?ims)^\.subckt[ \t]+" + wrapper +
            r"[ \t]+[^\n]*\n.*?^\.ends(?:[ \t]+" + wrapper + r")?[ \t]*$")
        models, count = pattern.subn("", models)
        if count != 1 or any(not re.search(r"(?im)^\.subckt[ \t]+" + re.escape(name) + r"[ \t]+", models)
                             for name in config.get("fixtures", {}).values()):
            raise ValueError("Native RF fixture definitions or their declared wrapper are missing")
        Path("fixture-models.spice").write_text(models)
    field.top_cell().shapes(field.layer(1000, 0)).clear()
    details["gds_multi_hole_polygons_encoded"] = write_field_gds(field, "em.gds")
    Path("ports.json").write_text(json.dumps(ports, indent=2))
    details["field_models"] = config["field_models"]
    details["rf_scope"] = "Native EM of physical passives and interconnect, with native compact devices at verified GDS pin planes."
    return details


if __name__ == "__main__":
    Path("fixture-models.spice").touch()
    try:
        details = prepare(json.loads(Path("config.json").read_text()))
        result = {"status": "passed", "details": details}
    except (Exception, SystemExit) as error:  # noqa: BLE001 -- preserve native failures.
        result = {"status": "error", "reason": f"{type(error).__name__}: {error}"}
    Path("result.json").write_text(json.dumps(result, indent=2, allow_nan=False))
