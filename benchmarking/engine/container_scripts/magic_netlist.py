"""Run Magic and verify its exported interface with a native SPICE reader."""

import json
import subprocess
from pathlib import Path

from klayout import db


def resistive_port_connections(circuit):
    """Port pairs joined by native resistor cards, excluding device channels."""
    parents = {}

    def root(net):
        parents.setdefault(net, net)
        while parents[net] != net:
            parents[net] = parents[parents[net]]
            net = parents[net]
        return net

    for device in circuit.each_device():
        cls = device.device_class()
        if isinstance(cls, db.DeviceClassResistor):
            a, b = [root(device.net_for_terminal(cls.terminal_id(t)).expanded_name())
                    for t in ("A", "B")]
            parents[b] = a
    pins = [(pin.name(), root(circuit.net_for_pin(pin.id()).expanded_name()))
            for pin in circuit.each_pin()]
    return {tuple(sorted((a, b))) for i, (a, net_a) in enumerate(pins)
            for b, net_b in pins[i + 1:] if net_a == net_b}


run = subprocess.run(["magic", "-dnull", "-noconsole", "-rcfile", "empty.magicrc", "extract.tcl"], check=False)
if run.returncode:
    raise SystemExit(run.returncode)
config = json.loads(Path("interface.json").read_text())
if config.get("reject_aliased_ports"):
    topology = db.Netlist()
    topology.read("topology.spice", db.NetlistSpiceReader())
    top = topology.circuit_by_name(config["top_cell"].upper())
    if top is None:
        raise ValueError("Missing extraction topology")
    parents = {}

    def root(name):
        parents.setdefault(name, name)
        if parents[name] != name:
            parents[name] = root(parents[name])
        return parents[name]

    # The native topology export represents labels on the same conductor
    # with zero-ohm alias resistors. Magic RC can duplicate or bypass those
    # networks; reject that unsupported interface instead of returning it.
    for device in top.each_device():
        cls = device.device_class()
        if isinstance(cls, db.DeviceClassResistor) and device.parameter(cls.parameter_id("R")) == 0:
            a, b = [root(device.net_for_terminal(t.id()).expanded_name()) for t in cls.terminal_definitions()]
            parents[b] = a
    port_nets = [root(top.net_for_pin(p.id()).expanded_name()) for p in top.each_pin()]
    if len(set(port_nets)) != len(port_nets):
        raise ValueError("Magic RC does not support multiple ports on the same conductor")
netlist = db.Netlist()
netlist.read("extracted.spice", db.NetlistSpiceReader())
circuit = netlist.circuit_by_name(config["top_cell"].upper())
if circuit is None:
    raise ValueError("Extraction did not produce the requested circuit")
ports = [p.name() for p in circuit.each_pin()]
if ports != [p.upper() for p in config["ports"]]:
    raise ValueError(f"Extracted port order/names differ from the declared interface: {ports}")
if not any(circuit.each_device()) and not any(circuit.each_subcircuit()):
    raise ValueError("Extracted circuit is empty")
if config.get("reject_aliased_ports"):
    # extresist can fill implicit substrate across deep-well isolation. A
    # successful tool exit must not turn distinct topology ports into an
    # interconnect resistor network. Preserve intentional native resistors
    # already present before RC; this is not a device-channel comparison.
    introduced = resistive_port_connections(circuit) - resistive_port_connections(top)
    if introduced:
        raise ValueError(f"Magic RC introduced a resistive connection between distinct topology ports: {sorted(introduced)}")
Path("interface-check.json").write_text(json.dumps({"top_cell": circuit.name, "ports": ports}))
