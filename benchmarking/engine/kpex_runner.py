"""Candidate LVS database to SG13G2 2.5D capacitance, retaining native devices."""

import json
import math
import subprocess
from pathlib import Path

import klayout.db as kdb
import klayout_pex
from klayout_pex.klayout.netlist_printer import NetlistPrinter
from klayout_pex.kpex_cli import KpexCLI


def physical_device_line(writer, device, substrate):
    """Adapt native geometry classes to simulator model calls, without resynthesis.

    KPEX 0.3.12 assumes every DeviceClassCapacitor has a C parameter. The
    foundry MIM subclass instead has w/l/m. Emit that native model explicitly.
    Native dimensions are micrometres; generated interconnect C remains farads.
    """
    model = device.device_class().name.lower()
    parameters = {
        "npn13g2": (("Nx", ""), ("m", "")),
        "rsil": (("w", "u"), ("l", "u"), ("m", "")),
        "cap_cmim": (("w", "u"), ("l", "u"), ("m", "")),
    }
    if model not in parameters:
        return None
    if model == "npn13g2":
        for name, value in (("we", 0.07), ("le", 0.9)):
            if not math.isclose(device.parameter(name), value, rel_tol=1e-6):
                raise ValueError(f"Unsupported {model} geometry: {name}")
    if model == "rsil" and any(device.parameter(p) != 0 for p in ("ps", "b")):
        raise ValueError("Serpentine resistor geometry is not supported")
    terminals = {"npn13g2": ("C", "B", "E", "S"),
                 "rsil": ("rsil_1", "rsil_2", "rsil_sub"), "cap_cmim": ("mim_top", "mim_btm")}[model]
    dc = device.device_class()
    nets = [writer.net_to_string(device.net_for_terminal(dc.terminal_id(t))) for t in terminals]
    nets = [substrate if n == "VSUBS" else n for n in nets]
    args = []
    for name, unit in parameters[model]:
        value = device.parameter(name)
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"Invalid {model} {name}")
        args.append(f"{name}={value:.12g}{unit}")
    return f'Xphysical_{device.id()} {" ".join(nets)} {model} {" ".join(args)}'


def extract(config):
    database = kdb.LayoutVsSchematic()
    database.read("candidate.lvsdb")
    circuit = database.netlist().circuit_by_name(config["top_cell"])
    if circuit is None:
        raise ValueError("Missing candidate circuit in LVS database")
    ports = [p.name() for p in circuit.each_pin()]
    if set(ports) != set(config["ports"]):
        raise ValueError("Candidate database ports differ from declared interface")
    if any(n.name == "VSUBS" for n in circuit.each_net()):
        raise ValueError("Candidate uses reserved KPEX substrate node VSUBS")
    counts = {}
    for d in circuit.each_device():
        name = d.device_class().name.lower()
        if name not in {"npn13g2", "rsil", "cap_cmim"}:
            raise ValueError(f"Unsupported physical model: {name}")
        counts[name] = counts.get(name, 0) + 1
    if not counts:
        raise ValueError("Empty candidate circuit")
    class CandidateReference(kdb.NetlistSpiceWriterDelegate):
        def write_device(self, device):
            line = physical_device_line(self, device, config["substrate"])
            model = device.device_class().name.lower()
            kind = {"npn13g2": "Q", "rsil": "R", "cap_cmim": "C"}[model]
            if model == "npn13g2":
                line += " we=70n le=900n"
            self.emit_line(kind + line[1:])

    reference_writer = kdb.NetlistSpiceWriter(CandidateReference())
    reference_writer.use_net_names = True
    reference_writer.with_comments = False
    database.netlist().write("candidate-reference.spice", reference_writer)
    original = NetlistPrinter.write_device

    def write_device(self, device):
        line = physical_device_line(self, device, config["substrate"])
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

    NetlistPrinter.write_device = write_device
    deck = Path(klayout_pex.__file__).parent / "pdk/ihp-sg13g2/libs.tech/kpex/sg13g2.lvs"
    variables = {
        "input": str(Path("candidate.gds").resolve()), "topcell": config["top_cell"],
        "schematic": str(Path("candidate-reference.spice").resolve()),
        "report": str(Path("geometry.lvsdb").resolve()),
        "target_netlist": str(Path("kpex-native.spice").resolve()),
        "run_mode": "deep", "spice_net_names": "true", "spice_comments": "false",
        "net_only": "false", "top_lvl_pins": "true", "combine_devices": "false",
        "purge": "false", "purge_nets": "false", "no_simplify": "true",
        "ignore_top_ports_mismatch": "false",
    }
    command = ["klayout", "-b", "-r", str(deck)]
    command.extend(arg for key, value in variables.items() for arg in ("-rd", f"{key}={value}"))
    with Path("geometry.log").open("w") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    geometry_db = kdb.LayoutVsSchematic()
    geometry_db.read("geometry.lvsdb")
    pairs = list(geometry_db.xref().each_circuit_pair())
    if not pairs or any(p.status() != kdb.NetlistCrossReference.Match for p in pairs):
        raise ValueError("KPEX geometry extraction differs from native candidate devices")
    KpexCLI().main(["kpex", "--pdk", "ihp-sg13g2", "--lvsdb", "geometry.lvsdb",
                    "--cell", config["top_cell"], "--2.5D", "--mode", "CC",
                    "--blackbox", "true", "--threads", "1", "--out_dir", "pex",
                    "--out_spice", "extracted.spice"])
    actual = geometry_db.netlist()
    expected = database.netlist()
    comparer = kdb.NetlistComparer()
    if not comparer.compare(expected, actual):
        raise ValueError("KPEX physical devices/connectivity differ from native candidate LVS")
    path = Path("extracted.spice")
    text = path.read_text()
    # KPEX's process reference plane is the declared ideal substrate boundary.
    import re
    text = re.sub(r"(?<!\S)VSUBS(?!\S)", config["substrate"], text)
    text = re.sub(r"\n\+\s*", " ", text)
    header = re.compile(r"^\.SUBCKT\s+(\S+)\s+.*$", re.MULTILINE | re.IGNORECASE)
    text, count = header.subn(f'.SUBCKT {config["top_cell"]} {" ".join(config["ports"])}', text)
    if count != 1:
        raise ValueError("Expected one flat extracted subcircuit")
    path.write_text(text)
    return {"physical_devices": counts, "mode": "CC", "blackbox_devices": True,
            "substrate": config["substrate"], "mim_policy": "native candidate w/l/m; no layer stripping or schematic reinsertion"}


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
