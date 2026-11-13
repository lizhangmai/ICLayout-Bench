"""Candidate LVS database to KPEX parasitics with declared native resources."""

import json
import math
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import klayout.db as kdb
import klayout_pex
from klayout_pex.klayout.netlist_printer import NetlistPrinter
from klayout_pex.kpex_cli import KpexCLI


def physical_device_line(writer, device, substrate, process, *, reference=False):
    """Adapt native geometry classes to simulator model calls, without resynthesis.

    KPEX 0.3.12 assumes every DeviceClassCapacitor has a C parameter. The
    physical subclasses can instead have geometry parameters. Emit their
    declared native model interface; generated interconnect C remains farads.
    """
    model = device.device_class().name.lower()
    spec = process["devices"].get(model)
    if spec is None:
        return None
    for name, rule in spec.get("required_values", {}).items():
        if not math.isclose(device.parameter(name), rule["value"], rel_tol=rule.get("relative_tolerance", 0)):
            raise ValueError(f"Unsupported {model} geometry: {name}")
    dc = device.device_class()
    nets = [writer.net_to_string(device.net_for_terminal(dc.terminal_id(t))) for t in spec["terminals"]]
    nets = [substrate if n == process["substrate_node"] else n for n in nets]
    args = []
    parameters = dict(spec["parameters"])
    if reference:
        parameters.update(spec.get("reference_parameters", {}))
    for name, unit in parameters.items():
        value = device.parameter(name)
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"Invalid {model} {name}")
        args.append(f"{name}={value:.12g}{unit}")
    prefix = spec["reference_prefix"] if reference else "X"
    return f'{prefix}physical_{device.id()} {" ".join(nets)} {model} {" ".join(args)}'


def extract(config):
    if config.get("devices_only"):
        geometry, tech = native_geometry(config)
        from klayout_pex.klayout.netlist_printer import NetlistHeader
        from klayout_pex.version import __version__

        header = NetlistHeader(__version__, "KLayout devices", config["process"]["pdk"],
                              datetime.now(UTC))
        NetlistPrinter(header, tech.device_models).write(geometry.netlist(), "extracted.spice")
        return {}
    if config.get("native_resources"):
        return extract_native(config)
    process = config["process"]
    database = kdb.LayoutVsSchematic()
    database.read("candidate.lvsdb")
    circuit = database.netlist().circuit_by_name(config["top_cell"])
    if circuit is None:
        raise ValueError("Missing candidate circuit in LVS database")
    ports = [p.name() for p in circuit.each_pin()]
    if set(ports) != set(config["ports"]):
        raise ValueError("Candidate database ports differ from declared interface")
    if any(n.name == process["substrate_node"] for n in circuit.each_net()):
        raise ValueError("Candidate uses reserved KPEX substrate node")
    counts = {}
    for d in circuit.each_device():
        name = d.device_class().name.lower()
        if name not in process["devices"]:
            raise ValueError(f"Unsupported physical model: {name}")
        counts[name] = counts.get(name, 0) + 1
    if not counts:
        raise ValueError("Empty candidate circuit")
    class CandidateReference(kdb.NetlistSpiceWriterDelegate):
        def write_device(self, device):
            self.emit_line(physical_device_line(self, device, config["substrate"], process, reference=True))

    reference_writer = kdb.NetlistSpiceWriter(CandidateReference())
    reference_writer.use_net_names = True
    reference_writer.with_comments = False
    database.netlist().write("candidate-reference.spice", reference_writer)
    original = NetlistPrinter.write_device

    def write_device(self, device):
        line = physical_device_line(self, device, config["substrate"], process)
        if line is not None:
            self.emit_line(line)
        elif isinstance(device.device_class(), kdb.DeviceClassCapacitor):
            value = device.parameter("C")
            if not math.isfinite(value) or value < 0:
                raise ValueError("Nonfinite or negative extracted capacitance")
            nets = [self.net_to_string(device.net_for_terminal(i)) for i in range(2)]
            self.emit_line(f'Cpar_{device.id()} {" ".join(nets)} {value:.17g}')
        else:
            original(self, device)

    deck = Path(klayout_pex.__file__).parent / process["deck"]
    variables = {
        **process["variables"],
        "input": str(Path("candidate.gds").resolve()), "topcell": config["top_cell"],
        "schematic": str(Path("candidate-reference.spice").resolve()),
        "report": str(Path("geometry.lvsdb").resolve()),
        "target_netlist": str(Path("kpex-native.spice").resolve()),
    }
    command = ["klayout", "-b", "-r", str(deck)]
    command.extend(arg for key, value in variables.items() for arg in ("-rd", f"{key}={value}"))
    with Path("geometry.log").open("w") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    geometry_db = kdb.LayoutVsSchematic()
    geometry_db.read("geometry.lvsdb")
    # The native LVS deck compared this geometry against candidate-reference.spice
    # using the PDK's device and terminal rules. Consume that persisted verdict:
    # a new default comparer after reload does not retain those device semantics.
    pairs = list(geometry_db.xref().each_circuit_pair())
    if not pairs or any(p.status() != kdb.NetlistCrossReference.Match for p in pairs):
        raise ValueError("KPEX geometry extraction differs from native candidate devices")
    NetlistPrinter.write_device = write_device
    try:
        KpexCLI().main(["kpex", "extract", "--pdk", process["pdk"], "--lvsdb", "geometry.lvsdb",
                    "--cell", config["top_cell"], "--2.5D", "--mode", "CC",
                    "--blackbox", "true", "--check", "true", "--threads", "1", "--out-dir", "pex",
                    "--out-netlist", "extracted.spice"])
    finally:
        NetlistPrinter.write_device = original
    bind_interface(config, process["substrate_node"])
    return {"physical_devices": counts, "mode": "CC", "blackbox_devices": True,
            "substrate": config["substrate"]}


def bind_interface(config, substrate_node):
    """Reorder existing named pins and bind only the declared ideal reference plane."""
    path = Path("extracted.spice")
    text = path.read_text()
    text = re.sub(r"\n\+\s*", " ", text)
    header = re.compile(r"^\.SUBCKT\s+(\S+)\s+.*$", re.MULTILINE | re.IGNORECASE)
    matches = list(header.finditer(text))
    if len(matches) != 1:
        raise ValueError("Expected one flat extracted subcircuit")
    fields = matches[0].group().split()
    native_ports = fields[2:]
    actual = [config["substrate"] if p == substrate_node else p for p in native_ports]
    if (fields[1] != config["top_cell"] or set(actual) != set(config["ports"])
            or len(native_ports) != len(set(native_ports))):
        raise ValueError("KPEX output interface differs from candidate")
    # Only the declared ideal reference-plane alias may collapse two ports.
    text = re.sub(r"(?<!\S)" + re.escape(substrate_node) + r"(?!\S)",
                  lambda _: config["substrate"], text)
    text = header.sub(lambda _: f'.SUBCKT {config["top_cell"]} {" ".join(config["ports"])}', text)
    path.write_text(text)


def native_geometry(config):
    """Run the maintained PEX deck as KPEX does, without a schematic truth input."""
    from klayout_pex.klayout.lvs_runner import LVSRunner
    from klayout_pex.tech_info import TechInfo

    process = config["process"]
    deck = Path("support", process["deck"]).resolve()
    technology = Path("support", process["technology"]).resolve()
    tech = TechInfo.from_json(str(technology), dielectric_filter=None)
    if tech.tech.name != process["pdk"]:
        raise ValueError("KPEX technology differs from declared process")
    LVSRunner.write_dummy_schematic("dummy.spice", config["top_cell"])
    variables = {**process["variables"], "input": str(Path("candidate.gds").resolve()),
                 process["top_cell_variable"]: config["top_cell"],
                 "schematic": str(Path("dummy.spice").resolve()),
                 "report": str(Path("geometry.lvsdb").resolve()),
                 "target_netlist": str(Path("kpex-native.spice").resolve())}
    if process["substrate_variable"] is not None:
        variables[process["substrate_variable"]] = config["substrate"]
    command = ["klayout", "-b", "-r", str(deck)]
    command.extend(arg for key, value in variables.items() for arg in ("-rd", f"{key}={value}"))
    with Path("geometry.log").open("w") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    geometry = kdb.LayoutVsSchematic()
    geometry.read("geometry.lvsdb")
    circuit = geometry.netlist().circuit_by_name(config["top_cell"])
    if circuit is None:
        raise ValueError("Missing candidate circuit in KPEX extraction")
    return geometry, tech


def extract_native(config):
    """Use KPEX's maintained device mappings and physical tables unchanged."""
    from klayout_pex.pdk_config import PDK

    process = config["process"]
    deck = Path("support", process["deck"]).resolve()
    technology = Path("support", process["technology"]).resolve()
    geometry, tech = native_geometry(config)
    models = tech.device_models.mapping_by_lvs_device_class_name
    database = kdb.LayoutVsSchematic()
    database.read("candidate.lvsdb")
    circuit = database.netlist().circuit_by_name(config["top_cell"])
    if circuit is None:
        raise ValueError("Missing candidate circuit in LVS database")
    if {p.name() for p in circuit.each_pin()} != set(config["ports"]):
        raise ValueError("Candidate database ports differ from declared interface")
    if any(n.name == process["substrate_node"] and n.name != config["substrate"]
           for n in circuit.each_net()):
        raise ValueError("Candidate uses reserved KPEX substrate node")
    counts, interfaces = {}, {}
    for device in circuit.each_device():
        name = device.device_class().name
        if name not in models:
            raise ValueError(f"Unsupported physical model: {name}")
        mapping = models[name]
        if mapping.spice_prefix != "X":
            raise ValueError(f"Unsupported KPEX model prefix: {mapping.spice_prefix}")
        model = (mapping.model_name or name).lower()
        counts[model] = counts.get(model, 0) + 1
        interfaces[model] = {"terminals": list(mapping.terminal_names)}
    # Compare native databases directly. Re-reading a SPICE serialization would
    # require the PEX deck's schematic reader to support every geometric class.
    writer = kdb.NetlistSpiceWriter()
    writer.use_net_names = True
    writer.with_comments = False
    database.netlist().write("candidate-reference.spice", writer)
    geometry.reference = database.netlist().dup()
    geometry.compare(kdb.NetlistComparer())
    pairs = list(geometry.xref().each_circuit_pair())
    if not pairs or any(p.status() != kdb.NetlistCrossReference.Match for p in pairs):
        raise ValueError("KPEX geometry extraction differs from native candidate devices")
    # KPEX 0.9 selects these paths through its PDKConfig API. Bind that selection
    # to reviewed support resources instead of silently loading package defaults.
    selected = PDK.from_string(process["pdk"]).config
    original = selected.pex_lvs_script_path, selected.tech_pb_json_path
    selected.pex_lvs_script_path, selected.tech_pb_json_path = str(deck), str(technology)
    try:
        KpexCLI().main(["kpex", "extract", "--pdk", process["pdk"],
            "--lvsdb", "geometry.lvsdb", "--gds", "candidate.gds", "--port-labels", "top",
            "--cell", config["top_cell"], "--2.5D", "--mode", config["mode"],
            "--blackbox", "true", "--check", "true", "--reduce", "none", "--threads", "1",
            "--out-dir", "pex", "--out-netlist", "extracted.spice"])
    finally:
        selected.pex_lvs_script_path, selected.tech_pb_json_path = original
    bind_interface(config, process["substrate_node"])
    return {"physical_devices": counts, "model_interfaces": interfaces,
            "mode": config["mode"], "blackbox_devices": True, "substrate": config["substrate"]}


if __name__ == "__main__":
    for name in ("extracted.spice", "geometry.lvsdb", "geometry.log",
                 "candidate-reference.spice", "kpex-native.spice"):
        Path(name).touch()
    try:
        details = extract(json.loads(Path("config.json").read_text()))
        result = {"status": "passed", "details": details}
    except (Exception, SystemExit) as error:  # noqa: BLE001 -- tool failure is evidence, not a pass.
        result = {"status": "error", "reason": f"{type(error).__name__}: {error}"}
    Path("result.json").write_text(json.dumps(result, indent=2))
