"""Candidate-derived SG13G2 HBT and distributed-RC extraction.

KLayout's SG13G2 runset is the authority for HBT topology and geometry
parameters.  Magic is used only for its distributed interconnect R/C network.
The two outputs are joined only when every HBT can be mapped uniquely by
terminals and connectivity.  A mapping failure is an extraction error; it is
never repaired by copying a source schematic into the post-layout netlist.
"""

from __future__ import annotations

import json
import math
import re
import shlex
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from benchmarking.evaluation import Job
from benchmarking.files import Asset, keys, text

from .evaluate import JobResult
from .klayout import KLayoutDocker
from .magic import MagicRCDocker

# These are the SG13G2 subcircuits emitted by the pinned KLayout runset and
# accepted by the reviewed ngspice model bundle.  The terminal counts are part
# of the model interface, not inferred from a source netlist.
_MODEL_TERMINALS = {
    "npn13g2": 4,
    "npn13g2l": 4,
    "npn13g2v": 4,
    "pnp13g2": 4,
    "pnp13g2l": 4,
    "rsil": 3,
    "rppd": 3,
    "rhigh": 3,
    "rpoly": 3,
    "cap_cmim": 2,
    "cap_cmomf": 2,
    "cap_cmomi": 2,
    "cap_rfcmim": 2,
    "ptap1": 2,
    "ntap1": 2,
}
_HBT_MODELS = {name for name in _MODEL_TERMINALS if name.startswith(("npn", "pnp"))}
_MODEL_CARD_PREFIXES = {
    **{model: {"Q", "X"} for model in _HBT_MODELS},
    **{model: {"R", "X"} for model in _MODEL_TERMINALS
       if model.startswith(("r", "p", "n")) and model not in _HBT_MODELS},
    **{model: {"C", "X"} for model in _MODEL_TERMINALS if model.startswith("cap_")},
}
_MODEL_DISPLAY = {
    "npn13g2": "npn13G2",
    "npn13g2l": "npn13G2L",
    "npn13g2v": "npn13G2V",
    "pnp13g2": "pnp13G2",
    "pnp13g2l": "pnp13G2L",
}
_PARAMETER_NAMES = {
    "npn13g2": {"we", "le", "nx", "ny", "m", "dtemp"},
    "npn13g2l": {"we", "le", "nx", "ny", "m", "dtemp"},
    "npn13g2v": {"we", "le", "nx", "ny", "m", "dtemp"},
    "pnp13g2": {"we", "le", "nx", "ny", "m", "dtemp"},
    "pnp13g2l": {"we", "le", "nx", "ny", "m", "dtemp"},
    "rsil": {"w", "l", "ps", "b", "m", "mm_ok", "trise", "sw_et"},
    "rppd": {"w", "l", "ps", "b", "m", "mm_ok", "trise", "sw_et"},
    "rhigh": {"w", "l", "ps", "b", "m", "mm_ok", "trise", "sw_et"},
    "rpoly": {"w", "l", "ps", "b", "m", "mm_ok", "trise", "sw_et"},
    "cap_cmim": {"w", "l", "m", "mm_ok", "ic"},
    "cap_cmomf": {"w", "l", "m", "mm_ok", "ic"},
    "cap_cmomi": {"w", "l", "m", "mm_ok", "ic"},
    "cap_rfcmim": {"w", "l", "m", "mm_ok", "ic"},
    # The native extractor reports tap area/perimeter, while the public model
    # deliberately uses its fixed R parameter.  A/P is retained in evidence
    # and omitted from simulator calls because it is not a model parameter.
    "ptap1": set(),
    "ntap1": set(),
}
_HBT_FIXED_GEOMETRY = {
    # The ordinary npn13G2 symbol describes a fixed 70 nm x 900 nm emitter;
    # these values are LVS geometry annotations, not behavioural parameters of
    # the four-terminal simulator subcircuit.  The long/HV variants keep their
    # model-controlled length and have a fixed width in the PDK symbols.
    "npn13g2": {"we": "70n", "le": "900n"},
    "npn13g2l": {"we": "70n"},
    "npn13g2v": {"we": "120n"},
}
_IGNORED_NATIVE_PARAMETERS = {"a", "p"}
_PRIMITIVE_LETTERS = set("QRMCLDIJX")
_SPICE_SUFFIXES = {
    "t": 1e12, "g": 1e9, "meg": 1e6, "k": 1e3, "m": 1e-3,
    "u": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15,
}


def _canonical_net(value: str) -> str:
    """Return a comparison key for KLayout/Magic SPICE net names."""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    # KLayout's writer escapes names such as \$166741.  shlex removes the
    # escape in normal input, but stripping one here also covers unit callers.
    while value.startswith("\\"):
        value = value[1:]
    return value.casefold()


def _spice_number(value: str) -> float:
    """Parse the simple scalar units emitted by the SG13G2 writers."""
    match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)([A-Za-z]*)", value.strip())
    if not match:
        raise ValueError(f"Unsupported non-scalar SPICE value: {value}")
    number = float(match.group(1))
    suffix = match.group(2).casefold()
    if suffix:
        if suffix not in _SPICE_SUFFIXES:
            raise ValueError(f"Unsupported SPICE unit suffix: {suffix}")
        number *= _SPICE_SUFFIXES[suffix]
    return number


def _same_spice_value(actual: str, expected: str) -> bool:
    try:
        left, right = _spice_number(actual), _spice_number(expected)
    except ValueError:
        return actual.casefold() == expected.casefold()
    return (math.isfinite(left) and math.isfinite(right)
            and math.isclose(left, right, rel_tol=1e-6, abs_tol=0.0))


@dataclass(frozen=True)
class _LogicalLine:
    text: str
    physical_lines: tuple[int, ...]


@dataclass(frozen=True)
class SpiceDevice:
    name: str
    nets: tuple[str, ...]
    model: str
    parameters: tuple[tuple[str, str], ...]
    line: _LogicalLine


@dataclass(frozen=True)
class ParsedNetlist:
    name: str
    ports: tuple[str, ...]
    devices: tuple[SpiceDevice, ...]
    lines: tuple[_LogicalLine, ...]

    @property
    def hbt_devices(self) -> tuple[SpiceDevice, ...]:
        return tuple(device for device in self.devices if device.model in _HBT_MODELS)


@dataclass(frozen=True)
class _HBTMapping:
    """A terminal-level association between the two extractor outputs.

    ``k_to_magic`` is intentionally one-to-many.  KLayout's net-only output
    can collapse a candidate conductor to one logical net while Magic keeps
    separate contact nodes on either side of distributed wire resistance.
    Keeping the per-card terminal association prevents the merge from
    accidentally shorting those nodes back together.
    """

    pairs: tuple[tuple[int, int], ...]
    terminal_nets: dict[tuple[int, int], str]
    k_to_magic: dict[str, tuple[str, ...]]
    magic_to_k: dict[str, str]
    # Final-Magic HBT index -> the corresponding pre-RC topology HBT index.
    # Magic normally preserves card names while extresist reorders cards, so
    # terminal safety checks must follow this explicit association.
    topology_pairs: dict[int, int]
    # ``(KLayout net, isolated Magic contact, anchored Magic contact)`` for
    # the bounded compact-terminal repair described in ``merge_hbt_netlists``.
    internal_repairs: tuple[tuple[str, str, str], ...]
def _logical_lines(raw: bytes | str) -> tuple[_LogicalLine, ...]:
    if isinstance(raw, bytes):
        content = raw.decode("utf-8")
    else:
        content = raw
    lines: list[_LogicalLine] = []
    current: _LogicalLine | None = None
    for line_number, physical in enumerate(content.splitlines()):
        stripped = physical.strip()
        if not stripped:
            if current is not None:
                lines.append(current)
                current = None
            continue
        if stripped.startswith("+"):
            if current is None:
                raise ValueError("SPICE continuation appears without a device line")
            current = _LogicalLine(current.text + " " + stripped[1:].strip(),
                                   (*current.physical_lines, line_number))
            continue
        if current is not None:
            lines.append(current)
        current = _LogicalLine(physical.rstrip(), (line_number,))
    if current is not None:
        lines.append(current)
    return tuple(lines)


def _as_text(raw: bytes | str) -> str:
    return raw.decode("utf-8") if isinstance(raw, bytes) else raw


def _tokens(line: _LogicalLine) -> list[str]:
    try:
        # Magic names may legally contain ``#`` (for example
        # ``w_76801_83161#``); enabling shlex's comment mode would silently
        # truncate every such card.  SPICE comments are filtered by their
        # leading token below, so comment mode is unnecessary here.
        tokens = shlex.split(line.text, comments=False, posix=True)
        # A semicolon starts an inline SPICE comment.  We cannot enable
        # shlex's comment mode because Magic wire names legitimately contain
        # ``#``.
        if ";" in tokens:
            tokens = tokens[:tokens.index(";")]
        return tokens
    except ValueError as error:
        raise ValueError(f"Invalid SPICE line at {line.physical_lines[0] + 1}: {error}") from error


def _parse_parameters(tokens: list[str], line: _LogicalLine) -> tuple[tuple[str, str], ...]:
    parameters = []
    for token in tokens:
        if "=" not in token:
            raise ValueError(f"Invalid device parameter at line {line.physical_lines[0] + 1}: {token}")
        key, value = token.split("=", 1)
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", key) or not value:
            raise ValueError(f"Invalid device parameter at line {line.physical_lines[0] + 1}: {token}")
        parameters.append((key, value))
    return tuple(parameters)


def parse_spice_netlist(raw: bytes | str, *, strict_devices: bool = False) -> ParsedNetlist:
    """Parse one top-level SPICE subcircuit and its supported device cards.

    ``strict_devices`` is used for KLayout output.  KLayout net-only output is
    expected to contain only supported SG13G2 model calls; silently dropping an
    unknown card would make the simulator netlist incomplete.  Magic output is
    intentionally parsed in permissive mode because its distributed C/R cards
    use primitive SPICE values without a model token.
    """
    lines = _logical_lines(raw)
    subcircuit: _LogicalLine | None = None
    end_index: int | None = None
    for index, line in enumerate(lines):
        tokens = _tokens(line)
        if tokens and tokens[0].casefold() == ".subckt":
            if subcircuit is not None:
                raise ValueError("Netlist contains more than one top-level subcircuit")
            if len(tokens) < 2:
                raise ValueError("SPICE subcircuit has no name")
            subcircuit = line
        elif subcircuit is None and tokens and not tokens[0].startswith(("*", ";")):
            # A top-level include/model/directive would make the result
            # dependent on an unreviewed source rather than this complete
            # extracted circuit.
            raise ValueError(f"SPICE netlist contains content before .SUBCKT: {tokens[0]}")
        elif subcircuit is not None and tokens and tokens[0].casefold() == ".ends":
            end_index = index
            break
    if subcircuit is None or end_index is None:
        raise ValueError("SPICE netlist must contain one complete .SUBCKT/.ENDS pair")
    for line in lines[end_index + 1:]:
        tokens = _tokens(line)
        if tokens and not tokens[0].startswith(("*", ";")):
            raise ValueError("SPICE netlist contains content after .ENDS")
    header = _tokens(subcircuit)
    name, ports = header[1], tuple(header[2:])
    end_tokens = _tokens(lines[end_index])
    if len(end_tokens) > 1 and _canonical_net(end_tokens[1]) != _canonical_net(name):
        raise ValueError(f"SPICE .ENDS name differs from .SUBCKT: {end_tokens[1]} vs {name}")
    if not ports or len({_canonical_net(port) for port in ports}) != len(ports):
        raise ValueError("SPICE subcircuit requires unique top-level ports")

    devices: list[SpiceDevice] = []
    sub_index = lines.index(subcircuit)
    unknown = []
    for line in lines[sub_index + 1:end_index]:
        tokens = _tokens(line)
        if not tokens or tokens[0].startswith("*") or tokens[0].startswith(";"):
            continue
        if tokens[0].startswith("."):
            unknown.append(tokens[0])
            continue
        model_index = next((index for index, token in enumerate(tokens[1:], 1)
                            if token.casefold() in _MODEL_TERMINALS), None)
        if model_index is None:
            # Magic's distributed network legitimately uses primitive C/R
            # cards without a model.  Validate their arity and scalar value;
            # malformed cards must not disappear silently.  Every other
            # device letter must name one of the reviewed subcircuits so an
            # unknown X/Q/M/V card cannot be retained accidentally in a
            # merged simulator netlist.
            letter = tokens[0][:1].upper()
            if letter in {"C", "R"} and not strict_devices:
                if len(tokens) != 4:
                    unknown.append(tokens[0])
                    continue
                try:
                    value = _spice_number(tokens[3])
                    if not math.isfinite(value) or value < 0:
                        raise ValueError("non-finite or negative primitive value")
                except ValueError:
                    unknown.append(tokens[0])
                continue
            if letter not in {"C", "R"} or strict_devices:
                unknown.append(tokens[0])
            continue
        model = tokens[model_index].casefold()
        if tokens[0][:1].upper() not in _MODEL_CARD_PREFIXES[model]:
            unknown.append(tokens[0])
            continue
        terminal_count = _MODEL_TERMINALS[model]
        if model_index - 1 < terminal_count:
            raise ValueError(f"Device {tokens[0]} has too few terminals")
        # SPICE cards place the model after all terminals: name, nets..., model,
        # parameters.  The model index is therefore also the boundary between
        # terminals and parameters.
        nets = tuple(tokens[1:model_index])
        if len(nets) != terminal_count:
            raise ValueError(f"Device {tokens[0]} has an invalid terminal count")
        parameters = _parse_parameters(tokens[model_index + 1:], line)
        devices.append(SpiceDevice(tokens[0], nets, model, parameters, line))
    if strict_devices and unknown:
        raise ValueError("KLayout netlist contains unsupported device cards: " + ", ".join(unknown))
    if not strict_devices and unknown:
        raise ValueError("Magic netlist contains unsupported device cards: " + ", ".join(unknown))
    if not devices:
        raise ValueError("Extracted SPICE subcircuit is empty")
    return ParsedNetlist(name, ports, tuple(devices), lines)


def _parameter_items(device: SpiceDevice) -> tuple[str, ...]:
    if device.model in {"ptap1", "ntap1"}:
        if len({key.casefold() for key, _ in device.parameters}) != len(device.parameters):
            raise ValueError(f"Duplicate {device.model} parameter on {device.name}")
        values = {key.casefold(): value for key, value in device.parameters}
        if set(values) - {"a", "p", "r", "w", "l"}:
            unknown = sorted(set(values) - {"a", "p", "r", "w", "l"})
            raise ValueError(f"Unsupported {device.model} parameters: {unknown}")
        if "r" in values:
            resistance = _spice_number(values["r"])
        elif "a" in values and "p" in values:
            area, perimeter = _spice_number(values["a"]), _spice_number(values["p"])
            if area <= 0 or perimeter <= 0:
                raise ValueError(f"{device.model} requires positive area and perimeter")
            # PDK ptap1/ntap1 symbols use the parallel area/perimeter
            # conductance expression below.  It is the reviewed mapping from
            # KLayout's native A/P annotations to the simulator subcircuit's
            # scalar R parameter.
            resistance = 1.0 / (1.0 / (9.8e-10 / area)
                                + 1.0 / (9.8e-4 / perimeter))
        else:
            raise ValueError(f"{device.model} requires R or both A and P")
        if not math.isfinite(resistance) or resistance <= 0:
            raise ValueError(f"{device.model} requires a finite positive resistance")
        return (f"R={resistance:.12g}",)
    allowed = _PARAMETER_NAMES[device.model]
    output = []
    seen = set()
    for key, value in device.parameters:
        lower = key.casefold()
        if device.model in _HBT_MODELS and lower in _HBT_FIXED_GEOMETRY.get(device.model, {}):
            expected = _HBT_FIXED_GEOMETRY[device.model][lower]
            if not _same_spice_value(value, expected):
                raise ValueError(f"Unsupported {device.model} drawn geometry {key}={value}; expected {expected}")
            # KLayout's native writer includes these values for LVS.  The
            # simulator model's fixed-width/fixed-length symbol contract uses
            # only Nx for npn13G2 and computes El from le for long/HV devices.
            if device.model == "npn13g2" or lower == "we":
                continue
        if lower in _IGNORED_NATIVE_PARAMETERS and lower not in allowed:
            continue
        if lower not in allowed:
            raise ValueError(f"Unsupported {device.model} parameter {key} on {device.name}")
        if lower in seen:
            raise ValueError(f"Duplicate {device.model} parameter {key} on {device.name}")
        seen.add(lower)
        if lower in {"nx", "ny", "m"}:
            numeric = _spice_number(value)
            if not math.isfinite(numeric) or numeric <= 0:
                raise ValueError(f"{device.model} requires a finite positive {key}")
            if lower in {"nx", "ny"} and numeric != int(numeric):
                raise ValueError(f"{device.model} requires an integer {key}")
        canonical = {"nx": "Nx", "ny": "Ny", "dtemp": "dtemp"}.get(lower, lower)
        output.append(f"{canonical}={value}")
    return tuple(output)


def _port_order(parsed: ParsedNetlist, ports: list[str] | tuple[str, ...]) -> dict[str, str]:
    if not isinstance(ports, (list, tuple)) or not ports:
        raise ValueError("Extraction requires an ordered list of unique ports")
    if any(not isinstance(port, str) or not port.strip() for port in ports):
        raise ValueError("Extraction ports must be nonempty strings")
    expected = tuple(ports)
    expected_keys = tuple(_canonical_net(port) for port in expected)
    if len(set(expected_keys)) != len(expected_keys):
        raise ValueError("Extraction ports must be unique case-insensitively")
    actual_keys = tuple(_canonical_net(port) for port in parsed.ports)
    if set(actual_keys) != set(expected_keys):
        raise ValueError(f"Extracted ports differ from the declared interface: {parsed.ports}")
    return dict(zip(expected_keys, expected))


def convert_klayout_netlist(raw: bytes | str, ports: list[str] | tuple[str, ...]) -> str:
    """Convert native KLayout device cards into simulator subcircuit calls.

    Native KLayout names such as ``\\$166741`` are assigned deterministic local
    names in first-use order.  Top-level ports retain the exact declared
    spelling and order.  Derived writer-only A/P fields are intentionally
    discarded because the reviewed simulator subcircuits do not accept them.
    """
    parsed = parse_spice_netlist(raw, strict_devices=True)
    port_names = _port_order(parsed, ports)
    net_names: dict[str, str] = {}

    def net_name(net: str) -> str:
        key = _canonical_net(net)
        if key in port_names:
            return port_names[key]
        if key == "0":
            return "0"
        if key not in net_names:
            net_names[key] = f"PEX_N{len(net_names)}"
        return net_names[key]

    result = [f"* Candidate-derived KLayout SG13G2 netlist: {parsed.name}",
              f".SUBCKT {parsed.name} {' '.join(ports)}"]
    for index, device in enumerate(parsed.devices, 1):
        parameters = _parameter_items(device)
        model = _MODEL_DISPLAY.get(device.model, device.model)
        items = [f"X{index}", *(net_name(net) for net in device.nets), model, *parameters]
        result.append(" ".join(items))
    result.append(f".ENDS {parsed.name}")
    return "\n".join(result) + "\n"


def _port_alias(value: str, port_keys: set[str]) -> str | None:
    """Return the base port for a Magic ``PORT.segment`` name, if any."""
    key = _canonical_net(value)
    if key in port_keys:
        return key
    for port in port_keys:
        if key.startswith(port + "."):
            return port
    return None


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def add(self, value: str) -> None:
        self.parent.setdefault(value, value)

    def find(self, value: str) -> str:
        self.add(value)
        parent = self.parent[value]
        if parent != value:
            parent = self.find(parent)
            self.parent[value] = parent
        return parent

    def union(self, left: str, right: str) -> None:
        left, right = self.find(left), self.find(right)
        if left != right:
            self.parent[right] = left


def _resistive_components(parsed: ParsedNetlist, ports: list[str] | tuple[str, ...]) -> dict[str, set[str]]:
    """Build Magic's pre-RC conductive components.

    The topology export contains the device geometry cards and any series
    resistor used to connect a device contact to a named port.  A component
    with two named ports is an actual short/ambiguous interface and is kept
    distinct so the mapper can reject it.
    """
    port_keys = {_canonical_net(port) for port in ports}
    union = _UnionFind()
    lines = parsed.lines
    start = next(index for index, line in enumerate(lines)
                 if (_tokens(line) and _tokens(line)[0].casefold() == ".subckt"))
    end = next(index for index in range(start + 1, len(lines))
               if (_tokens(lines[index]) and _tokens(lines[index])[0].casefold() == ".ends"))
    for line in lines[start + 1:end]:
        tokens = _tokens(line)
        if not tokens or tokens[0].startswith(("*", ";", ".")):
            continue
        # Modelled rppd/rsil devices are circuit elements, rather than net
        # aliases.  Only primitive Magic wire resistors represent a contact
        # endpoint's explicit series path in the pre-RC topology.
        model_index = next((index for index, token in enumerate(tokens[1:], 1)
                            if token.casefold() in _MODEL_TERMINALS), None)
        if model_index is not None:
            continue
        # Primitive Magic wire resistors have the form Rname n1 n2 value.
        if tokens[0][:1].casefold() == "r" and len(tokens) >= 4:
            union.union(_canonical_net(tokens[1]), _canonical_net(tokens[2]))
    for key in list(union.parent):
        alias = _port_alias(key, port_keys)
        if alias is not None:
            union.union(key, alias)
    components: dict[str, set[str]] = {}
    for key in union.parent:
        components.setdefault(union.find(key), set()).add(key)
    return components


def _component_ports(components: dict[str, set[str]], value: str,
                     port_keys: set[str]) -> set[str]:
    key = _canonical_net(value)
    for members in components.values():
        if key in members:
            return {port for member in members
                    for port in (_port_alias(member, port_keys),) if port is not None}
    return {_port_alias(value, port_keys)} - {None}


def _explicit_component_ports(components: dict[str, set[str]], value: str,
                              port_keys: set[str]) -> set[str]:
    """Return ports reached through an explicit primitive-R component only."""
    key = _canonical_net(value)
    for members in components.values():
        if key in members:
            return {port for member in members
                    for port in (_port_alias(member, port_keys),) if port is not None}
    return set()


def _same_resistive_component(components: dict[str, set[str]], values: list[str]) -> bool:
    """Whether all values are joined by explicit primitive wire resistors."""
    keys = {_canonical_net(value) for value in values}
    if len(keys) <= 1:
        return True
    roots = {
        root for root, members in components.items()
        if keys.intersection(members)
    }
    # Every endpoint must occur in one component.  A component root can be
    # represented by the canonical name of the first union member, so use a
    # direct membership check rather than assuming root names are stable.
    memberships = [
        next((root for root, members in components.items() if key in members), None)
        for key in keys
    ]
    return bool(roots) and all(root == memberships[0] for root in memberships)


def _require_final_wire_connectivity(topology: ParsedNetlist, magic: ParsedNetlist,
                                     ports: list[str] | tuple[str, ...]) -> None:
    """Require every pre-RC primitive wire path to survive final RC export.

    The topology netlist is the evidence used to associate a Magic contact
    with a candidate terminal.  A final RC netlist may add many segmented
    resistors, but it cannot silently remove the only resistor that proved a
    contact's identity.  Checking the endpoint component relation catches
    that case without requiring Magic to emit the same resistor numbering or
    segmentation.
    """
    topology_components = _resistive_components(topology, ports)
    final_components = _resistive_components(magic, ports)
    for members in topology_components.values():
        if len(members) <= 1:
            continue
        endpoints = sorted(members)
        if not _same_resistive_component(final_components, endpoints):
            raise ValueError(
                "Final RC wire connectivity does not retain a pre-RC endpoint "
                f"component: {endpoints[:6]}"
            )


def _card_net_fields(line: _LogicalLine) -> tuple[str, tuple[str, ...]] | None:
    """Return ``(card kind, net fields)`` for a parsed body line.

    This scans primitive Magic C/R cards as well as modelled cards.  Primitive
    cards are deliberately not added to ``ParsedNetlist.devices`` because
    they are distributed parasitics, but their endpoint references still
    matter when deciding whether an HBT contact may be repaired.
    """
    tokens = _tokens(line)
    if not tokens or tokens[0].startswith(("*", ";", ".")):
        return None
    model_index = next((index for index, token in enumerate(tokens[1:], 1)
                        if token.casefold() in _MODEL_TERMINALS), None)
    if model_index is not None:
        model = tokens[model_index].casefold()
        return model, tuple(tokens[1:model_index])
    letter = tokens[0][:1].upper()
    if letter in {"C", "R"} and len(tokens) >= 4:
        return ("__primitive_c" if letter == "C" else "__primitive_r"), tuple(tokens[1:3])
    return None


def _endpoint_references(parsed: ParsedNetlist, value: str) -> list[tuple[str, str]]:
    """List non-HBT cards that reference an endpoint net."""
    key = _canonical_net(value)
    references: list[tuple[str, str]] = []
    start = next(index for index, line in enumerate(parsed.lines)
                 if (_tokens(line) and _tokens(line)[0].casefold() == ".subckt"))
    end = next(index for index in range(start + 1, len(parsed.lines))
               if (_tokens(parsed.lines[index]) and _tokens(parsed.lines[index])[0].casefold() == ".ends"))
    for line in parsed.lines[start + 1:end]:
        fields = _card_net_fields(line)
        if fields is None:
            continue
        model, nets = fields
        if model in _HBT_MODELS:
            continue
        if any(_canonical_net(net) == key for net in nets):
            references.append((_tokens(line)[0], model))
    return references


def _hbt_endpoint_occurrences(parsed: ParsedNetlist, value: str) -> list[tuple[int, int]]:
    """Return every HBT-card terminal occurrence of ``value``.

    A compact-device terminal is eligible for the bounded internal repair
    only when this list contains exactly its owning card and terminal.  This
    keeps a shared HBT node, or a contact reused by another device, from
    being mistaken for the isolated emitter artifact seen in the reviewed
    layouts.
    """
    key = _canonical_net(value)
    return [
        (device_index, position)
        for device_index, device in enumerate(parsed.hbt_devices)
        for position, net in enumerate(device.nets)
        if _canonical_net(net) == key
    ]


def _hbt_topology_pairs(magic: ParsedNetlist, topology: ParsedNetlist) -> dict[int, int]:
    """Associate final-Magic HBT cards with their pre-RC topology cards.

    ``extresist`` may reorder cards, while Magic keeps the extracted card
    names.  Relying on list position would therefore check an endpoint on a
    different HBT.  Card names are the explicit correspondence exposed by
    the extractor; duplicate, missing, or materially changed identities fail
    closed instead of falling back to an arbitrary order.
    """
    by_name: dict[str, list[int]] = {}
    for index, device in enumerate(topology.hbt_devices):
        by_name.setdefault(_canonical_net(device.name), []).append(index)
    pairs: dict[int, int] = {}
    used: set[int] = set()
    for magic_index, magic_device in enumerate(magic.hbt_devices):
        candidates = by_name.get(_canonical_net(magic_device.name), [])
        if len(candidates) != 1:
            raise ValueError(
                "Magic topology HBT correspondence is missing or ambiguous "
                f"for {magic_device.name}"
            )
        topology_index = candidates[0]
        if topology_index in used:
            raise ValueError(
                "Magic topology HBT correspondence reuses "
                f"{magic_device.name}"
            )
        topology_device = topology.hbt_devices[topology_index]
        if topology_device.model != magic_device.model:
            raise ValueError(
                "Magic topology HBT model differs for "
                f"{magic_device.name}"
            )
        magic_parameters = {key.casefold(): value
                            for key, value in magic_device.parameters}
        topology_parameters = {key.casefold(): value
                               for key, value in topology_device.parameters}
        if (set(magic_parameters) != set(topology_parameters)
                or any(not _same_spice_value(magic_parameters[key], topology_parameters[key])
                       for key in magic_parameters)):
            raise ValueError(
                "Magic topology HBT parameters differ for "
                f"{magic_device.name}"
            )
        pairs[magic_index] = topology_index
        used.add(topology_index)
    if len(used) != len(topology.hbt_devices):
        raise ValueError("Magic topology contains an unmatched HBT card")
    return pairs


def _internal_terminal_state(magic: ParsedNetlist, topology: ParsedNetlist,
                             topology_pairs: dict[int, int], magic_index: int,
                             position: int, magic_net: str) -> tuple[str, bool, bool]:
    """Classify one Magic contact in final and pre-RC outputs.

    The returned tuple is ``(spelling, isolated, anchored)``.  ``isolated``
    means the contact occurs only on this HBT terminal and has no non-HBT
    card references in either output.  ``anchored`` means both outputs show a
    non-HBT card attached to the corresponding contact.  Requiring the same
    state in both outputs prevents a topology-only or final-only guess from
    creating a compact-device short.
    """
    topology_index = topology_pairs[magic_index]
    magic_device = magic.hbt_devices[magic_index]
    topology_device = topology.hbt_devices[topology_index]
    topology_net = topology_device.nets[position]
    magic_is_own = _hbt_endpoint_occurrences(magic, magic_net) == [(magic_index, position)]
    topology_is_own = _hbt_endpoint_occurrences(topology, topology_net) == [
        (topology_index, position)
    ]
    magic_external = bool(_endpoint_references(magic, magic_net))
    topology_external = bool(_endpoint_references(topology, topology_net))
    isolated = magic_is_own and topology_is_own and not magic_external and not topology_external
    anchored = magic_external and topology_external
    if isolated and anchored:
        raise ValueError(
            "Magic HBT contact cannot be both isolated and anchored: "
            f"{magic_device.name} {magic_net}"
        )
    return magic_net, isolated, anchored


def _repairable_internal_pair(magic: ParsedNetlist, topology: ParsedNetlist,
                              topology_pairs: dict[int, int], left_index: int,
                              left_position: int, left_net: str, right_index: int,
                              right_position: int, right_net: str) -> bool:
    """Check the only supported split-contact repair during graph search."""
    left = _internal_terminal_state(magic, topology, topology_pairs,
                                    left_index, left_position, left_net)
    right = _internal_terminal_state(magic, topology, topology_pairs,
                                     right_index, right_position, right_net)
    # Exactly one contact is an isolated compact terminal and exactly one is
    # anchored by an explicitly retained passive/wire card.  A pair with two
    # anchors, two isolated contacts, or inconsistent extractor evidence is
    # intentionally rejected.
    return (left[1] and right[2]) or (right[1] and left[2])


def _passive_shape(device: SpiceDevice) -> tuple:
    """Compare model-card geometry without making net names part of shape."""
    return _passive_signature(
        device, domain_net=lambda _net: "__shape__",
        defaults={"ps": "0u", "b": "0"}
    )


def _passive_anchor_mapping(
        klayout: ParsedNetlist, magic: ParsedNetlist, topology: ParsedNetlist,
        mapping: tuple[tuple[int, int], ...], terminal_nets: dict[tuple[int, int], str],
        magic_to_k: dict[str, str], topology_pairs: dict[int, int],
        ports: list[str] | tuple[str, ...]) -> dict[str, tuple[tuple[str, str], ...]]:
    """Find retained Magic passive contacts for isolated internal HBT nodes.

    Magic's topology export can leave a compact-device contact disconnected
    while retaining the corresponding resistor/capacitor model card on a
    nearby contact.  A passive card is a valid anchor only when its model and
    geometry uniquely match a candidate KLayout card and every already-known
    terminal/port agrees.  The result carries both topology and final-RC
    spellings because extresist may add a port segment to the latter.
    """
    port_keys = {_canonical_net(port) for port in ports}
    # ``mapping`` is keyed by KLayout device index throughout this function.
    # Keep that direction explicit; reversing it silently associates a
    # passive with the wrong HBT as soon as Magic emits cards in a different
    # order.
    magic_by_k = {k_index: magic_index for k_index, magic_index in mapping}
    known_magic_by_k: dict[str, set[str]] = {}
    for magic_key, k_key in magic_to_k.items():
        known_magic_by_k.setdefault(k_key, set()).add(magic_key)

    isolated_keys: set[str] = set()
    for (k_index, position), magic_net in terminal_nets.items():
        k_key = _canonical_net(klayout.hbt_devices[k_index].nets[position])
        if k_key in port_keys:
            continue
        magic_index = magic_by_k[k_index]
        _, isolated, _ = _internal_terminal_state(
            magic, topology, topology_pairs, magic_index, position, magic_net
        )
        if isolated:
            isolated_keys.add(k_key)
    if not isolated_keys:
        return {}

    final_by_name: dict[str, list[SpiceDevice]] = {}
    for device in magic.devices:
        if device.model not in _HBT_MODELS:
            final_by_name.setdefault(_canonical_net(device.name), []).append(device)

    def known_compatible(k_net: str, magic_net: str) -> bool:
        k_key = _canonical_net(k_net)
        alias = _port_alias(magic_net, port_keys)
        known_k = magic_to_k.get(_canonical_net(magic_net))
        if k_key in port_keys:
            return alias == k_key
        if alias is not None:
            return False
        if known_k is not None:
            return known_k == k_key
        # An unknown passive endpoint is useful only when the same native net
        # already has a mapped HBT contact.  Otherwise its identity cannot be
        # established from this pair alone.
        return bool(known_magic_by_k.get(k_key))

    def position_orders(device: SpiceDevice) -> tuple[tuple[int, ...], ...]:
        if device.model.startswith(("r", "cap_")) and len(device.nets) >= 2:
            identity = tuple(range(len(device.nets)))
            swapped = (1, 0, *range(2, len(device.nets)))
            return identity, swapped
        return (tuple(range(len(device.nets))),)

    candidates: dict[str, set[tuple[str, str]]] = {
        key: set() for key in isolated_keys
    }
    klayout_passives = [
        device for device in klayout.devices
        if device.model not in _HBT_MODELS
        and device.model.startswith(("r", "cap_"))
    ]
    topology_passives = [
        device for device in topology.devices
        if device.model not in _HBT_MODELS
        and device.model.startswith(("r", "cap_"))
    ]
    for k_device in klayout_passives:
        targets = {
            (position, _canonical_net(net))
            for position, net in enumerate(k_device.nets)
            if _canonical_net(net) in isolated_keys
        }
        if not targets:
            continue
        k_shape = _passive_shape(k_device)
        for topology_device in topology_passives:
            if topology_device.model != k_device.model or _passive_shape(topology_device) != k_shape:
                continue
            final_candidates = final_by_name.get(_canonical_net(topology_device.name), [])
            if len(final_candidates) != 1:
                continue
            final_device = final_candidates[0]
            if (final_device.model != topology_device.model
                    or _passive_shape(final_device) != k_shape):
                continue
            for order in position_orders(k_device):
                # ``order[k_position]`` gives the corresponding topology
                # terminal position for a KLayout terminal.
                if any(not known_compatible(
                        k_device.nets[k_position],
                        topology_device.nets[order[k_position]])
                       for k_position in range(len(k_device.nets))):
                    continue
                for k_position, k_key in targets:
                    topology_net = topology_device.nets[order[k_position]]
                    final_net = final_device.nets[order[k_position]]
                    topology_known = magic_to_k.get(_canonical_net(topology_net))
                    if topology_known is not None or _port_alias(topology_net, port_keys) is not None:
                        continue
                    # The passive endpoint must be present in both Magic
                    # outputs.  A final-only or topology-only contact cannot
                    # establish the compact terminal's identity.
                    if (not _endpoint_references(topology, topology_net)
                            or not _endpoint_references(magic, final_net)):
                        continue
                    candidates[k_key].add((_canonical_net(topology_net), final_net))

    return {
        k_key: tuple(sorted(values))
        for k_key, values in candidates.items()
        if values
    }


def _resolve_internal_repairs(
        klayout: ParsedNetlist, magic: ParsedNetlist, topology: ParsedNetlist,
        mapping: tuple[tuple[int, int], ...], terminal_nets: dict[tuple[int, int], str],
        k_to_magic_sets: dict[str, set[str]], topology_pairs: dict[int, int],
        ports: list[str] | tuple[str, ...],
        passive_anchors: dict[str, tuple[tuple[str, str], ...]] | None = None
        ) -> tuple[tuple[str, str, str], ...]:
    """Choose a unique anchored contact for every split KLayout net.

    The KLayout net-only extractor may collapse two compact-device contacts
    to one logical node.  When Magic emits one isolated endpoint and one
    endpoint attached to a real passive/wire network, the isolated contact is
    a bounded intrinsic-device extraction artifact.  Repointing that HBT
    terminal to the anchored Magic contact preserves all existing RC cards;
    no tie element is synthesized.  All other split groups fail closed.
    """
    port_keys = {_canonical_net(port) for port in ports}
    passive_anchors = passive_anchors or {}
    topology_components = _resistive_components(topology, ports)
    final_components = _resistive_components(magic, ports)
    magic_by_k = {k_index: magic_index for k_index, magic_index in mapping}
    repairs: list[tuple[str, str, str]] = []
    for k_key, magic_values in sorted(k_to_magic_sets.items()):
        magic_value_keys = {_canonical_net(value) for value in magic_values}
        has_isolated_hbt = any(
            _internal_terminal_state(
                magic, topology, topology_pairs, magic_by_k[k_index], position, m_net
            )[1]
            for (k_index, position), m_net in terminal_nets.items()
            if _canonical_net(klayout.hbt_devices[k_index].nets[position]) == k_key
        )
        if len(magic_value_keys) <= 1 and not passive_anchors.get(k_key):
            if has_isolated_hbt and k_key not in port_keys:
                raise ValueError(
                    f"KLayout internal net {k_key} has no anchored Magic passive contact"
                )
            continue
        if k_key in port_keys:
            raise ValueError(f"Top-level port maps to multiple Magic HBT contacts: {k_key}")
        # Distinct contacts already joined by an explicit Magic wire
        # resistor are genuine distributed endpoints.  Their relationship is
        # represented by that retained resistor and must not be rewritten as
        # a compact-device repair.
        if (len(magic_value_keys) > 1
                and (_same_resistive_component(topology_components, list(magic_values))
                     or _same_resistive_component(final_components, list(magic_values)))):
            continue
        entries = [
            (k_index, position, m_index, m_net)
            for (k_index, position), m_net in terminal_nets.items()
            if _canonical_net(klayout.hbt_devices[k_index].nets[position]) == k_key
            for m_index in [magic_by_k[k_index]]
        ]
        # ``magic_values`` is assembled from all terminals, while ``entries``
        # also carries the card/terminal needed to validate ownership in both
        # Magic outputs.  Do not accept a value that was not present in an
        # HBT terminal association.
        if {_canonical_net(entry[3]) for entry in entries} != {
                _canonical_net(value) for value in magic_values}:
            raise ValueError(f"Incomplete Magic contact mapping for KLayout net {k_key}")
        states: dict[str, tuple[str, bool, bool]] = {}
        for _, position, m_index, m_net in entries:
            state = _internal_terminal_state(
                magic, topology, topology_pairs, m_index, position, m_net
            )
            previous = states.get(_canonical_net(m_net))
            if previous is not None and previous[1:] != state[1:]:
                raise ValueError(
                    f"Magic contact {m_net} has inconsistent terminal evidence"
                )
            states.setdefault(_canonical_net(m_net), state)
        for topology_net, final_net in passive_anchors.get(k_key, ()):
            if not _endpoint_references(topology, topology_net) or not _endpoint_references(
                    magic, final_net):
                continue
            state = (final_net, False, True)
            prior = states.get(_canonical_net(final_net))
            if prior is not None and prior[1:] != state[1:]:
                raise ValueError(
                    f"Magic passive contact {final_net} has inconsistent terminal evidence"
                )
            states.setdefault(_canonical_net(final_net), state)
        anchored = [state for state in states.values() if state[2]]
        isolated = [state for state in states.values() if state[1]]
        if len(anchored) != 1 or not isolated or len(anchored) + len(isolated) != len(states):
            raise ValueError(
                f"KLayout internal net {k_key} has no unique isolated-to-anchored "
                "Magic contact repair"
            )
        anchor = anchored[0][0]
        isolated_keys = {_canonical_net(state[0]) for state in isolated}
        for k_index, position, _, m_net in entries:
            if _canonical_net(m_net) in isolated_keys:
                terminal_nets[(k_index, position)] = anchor
                repairs.append((k_key, m_net, anchor))
    return tuple(repairs)


def _hbt_mapping(klayout: ParsedNetlist, magic: ParsedNetlist,
                 ports: list[str] | tuple[str, ...],
                 magic_topology: ParsedNetlist | None = None
                 ) -> _HBTMapping:
    """Find a unique KLayout-to-Magic HBT mapping without factorial search.

    Candidate pairs are constrained by model, named C/B ports, and every
    internal equality.  A bounded backtracking search then resolves the small
    remaining graph isomorphism problem.  The bound is deliberate: a highly
    symmetric or malformed netlist is reported as ambiguous instead of
    spending unbounded time or choosing an arbitrary permutation.
    """
    _port_order(klayout, ports)
    _port_order(magic, ports)
    k_devices, m_devices = klayout.hbt_devices, magic.hbt_devices
    if not k_devices or not m_devices:
        raise ValueError("HBT extraction contains no supported HBT devices")
    if len(k_devices) != len(m_devices):
        raise ValueError(f"HBT device count differs between extractors: {len(k_devices)} vs {len(m_devices)}")
    if sorted(device.model for device in k_devices) != sorted(device.model for device in m_devices):
        raise ValueError("HBT model population differs between extractors")
    port_keys = {_canonical_net(port) for port in ports}
    topology_pairs = (_hbt_topology_pairs(magic, magic_topology)
                      if magic_topology is not None else {})
    components = _resistive_components(magic_topology, ports) if magic_topology else {}
    final_components = _resistive_components(magic, ports)

    def pair_score(k_device: SpiceDevice, m_device: SpiceDevice) -> int | None:
        if k_device.model != m_device.model:
            return None
        score = 0
        for position, (k_net, m_net) in enumerate(zip(k_device.nets, m_device.nets)):
            k_key, m_key = _canonical_net(k_net), _canonical_net(m_net)
            if k_key in port_keys:
                if m_key == k_key:
                    score += 100
                elif position in (2, 3):
                    # A port-connected E/S can be represented by a local Magic
                    # contact.  The merge adds an explicit tie unless the
                    # topology already proves a resistor path to the port.
                    reachable = (_explicit_component_ports(components, m_net, port_keys)
                                 or _explicit_component_ports(final_components, m_net, port_keys))
                    if reachable and reachable != {k_key}:
                        return None
                    score += 10 if reachable == {k_key} else 1
                else:
                    # C/B mismatches are valid only when Magic topology proves
                    # the endpoint is on a series-resistor path to this port.
                    # extresist may introduce the segment only in its final
                    # output, so that final graph is accepted as evidence too.
                    reachable = (_explicit_component_ports(components, m_net, port_keys)
                                 or _explicit_component_ports(final_components, m_net, port_keys))
                    if reachable != {k_key}:
                        return None
                    score += 10
            elif m_key in port_keys:
                return None
        return score

    candidates: dict[int, list[tuple[int, int]]] = {}
    for k_index, k_device in enumerate(k_devices):
        choices = []
        for m_index, m_device in enumerate(m_devices):
            score = pair_score(k_device, m_device)
            if score is not None:
                choices.append((m_index, score))
        if not choices:
            raise ValueError(f"No Magic HBT candidate matches {k_device.name}")
        candidates[k_index] = choices

    # Most-constrained-first ordering keeps a 12-emitter graph bounded even
    # when its device cards are emitted in a different order.
    order = tuple(sorted(candidates, key=lambda index: len(candidates[index])))
    solutions: list[tuple[tuple[int, int], ...]] = []
    visits = 0
    visit_limit = 200_000

    def compatible(k_index: int, m_index: int,
                   assigned: dict[int, int]) -> tuple[bool, int]:
        k_device, m_device = k_devices[k_index], m_devices[m_index]
        score = next(value for candidate, value in candidates[k_index] if candidate == m_index)
        for other_k, other_m in assigned.items():
            other_k_device, other_m_device = k_devices[other_k], m_devices[other_m]
            for left_position, left_net in enumerate(k_device.nets):
                for right_position, right_net in enumerate(other_k_device.nets):
                    left_key, right_key = _canonical_net(left_net), _canonical_net(right_net)
                    if left_key in port_keys or right_key in port_keys:
                        continue
                    same_k = left_key == right_key
                    left_magic = m_device.nets[left_position]
                    right_magic = other_m_device.nets[right_position]
                    same_m = (_canonical_net(left_magic)
                              == _canonical_net(right_magic)
                              or (same_k and (
                                  _same_resistive_component(components, [left_magic, right_magic])
                                  or _same_resistive_component(
                                      final_components, [left_magic, right_magic]))))
                    if same_k != same_m:
                        if not (same_k and magic_topology is not None
                                and _repairable_internal_pair(
                                    magic, magic_topology, topology_pairs,
                                    m_index, left_position, left_magic,
                                    other_m, right_position, right_magic)):
                            return False, 0
                        score += 4
                    if same_k:
                        score += 5
        return True, score

    def search(depth: int, assigned: dict[int, int], used: set[int], score: int) -> None:
        nonlocal visits
        if len(solutions) >= 2:
            return
        visits += 1
        if visits > visit_limit:
            raise ValueError("HBT terminal mapping is too complex or ambiguous")
        if depth == len(order):
            mapping = tuple(sorted(assigned.items()))
            if mapping not in solutions:
                solutions.append(mapping)
            return
        k_index = order[depth]
        for m_index, _ in candidates[k_index]:
            if m_index in used:
                continue
            valid, extra = compatible(k_index, m_index, assigned)
            if not valid:
                continue
            assigned[k_index] = m_index
            search(depth + 1, assigned, used | {m_index}, score + extra)
            del assigned[k_index]

    search(0, {}, set(), 0)
    if not solutions:
        raise ValueError("HBT terminal topology cannot be mapped between KLayout and Magic")
    if len(solutions) != 1:
        raise ValueError("HBT terminal mapping is ambiguous between KLayout and Magic")
    mapping = solutions[0]

    terminal_nets: dict[tuple[int, int], str] = {}
    k_to_magic_sets: dict[str, set[str]] = {}
    magic_to_k: dict[str, str] = {}
    for k_index, m_index in mapping:
        for position, (k_net, m_net) in enumerate(
                zip(k_devices[k_index].nets, m_devices[m_index].nets)):
            k_key, m_key = _canonical_net(k_net), _canonical_net(m_net)
            if k_key in port_keys:
                continue
            if m_key in port_keys:
                raise ValueError(f"Internal KLayout HBT net {k_net} maps to Magic port {m_net}")
            terminal_nets[(k_index, position)] = m_net
            k_to_magic_sets.setdefault(k_key, set()).add(m_net)
            prior = magic_to_k.get(m_key)
            if prior is not None and prior != k_key:
                raise ValueError(f"Magic HBT net {m_net} maps to multiple KLayout internal nets")
            magic_to_k[m_key] = k_key
    passive_anchors = (_passive_anchor_mapping(
        klayout, magic, magic_topology, mapping, terminal_nets,
        magic_to_k, topology_pairs, ports
    ) if magic_topology is not None else {})
    for anchor_k, anchor_values in passive_anchors.items():
        for topology_net, final_net in anchor_values:
            # Add both spellings to the logical domain map.  The final RC
            # writer may put a ``PORT.segment`` on the opposite terminal of
            # the same model card, so topology and final keys are kept
            # independently.
            if _port_alias(final_net, port_keys) is not None:
                raise ValueError(
                    f"Internal passive anchor {final_net} aliases a top-level port"
                )
            for anchor_net in (topology_net, final_net):
                anchor_key = _canonical_net(anchor_net)
                prior = magic_to_k.get(anchor_key)
                if prior is not None and prior != anchor_k:
                    raise ValueError(
                        f"Magic passive anchor {anchor_net} maps to multiple "
                        "KLayout internal nets"
                    )
                magic_to_k[anchor_key] = anchor_k
    internal_repairs = _resolve_internal_repairs(
        klayout, magic, magic_topology, mapping, terminal_nets,
        k_to_magic_sets, topology_pairs, ports, passive_anchors
    ) if magic_topology is not None else ()
    for k_key, m_values in k_to_magic_sets.items():
        if len({_canonical_net(value) for value in m_values}) > 1 and not _same_resistive_component(
                components, list(m_values)) and not _same_resistive_component(
                final_components, list(m_values)) and k_key not in {
                    _canonical_net(repair[0]) for repair in internal_repairs
                }:
            raise ValueError(
                f"KLayout internal net {k_key} maps to disconnected Magic contact nets"
            )
    k_to_magic = {
        k_key: tuple(sorted(values, key=_canonical_net))
        for k_key, values in k_to_magic_sets.items()
    }
    return _HBTMapping(mapping, terminal_nets, k_to_magic, magic_to_k,
                       topology_pairs, internal_repairs)


def _net_domain(value: str, *, port_keys: set[str], internal: dict[str, str],
                components: dict[str, set[str]] | None = None,
                require_component_for_segment: bool = False) -> str:
    """Project a net into the KLayout logical domain for coarse-device checks."""
    key = _canonical_net(value)
    if key in port_keys:
        return "port:" + key
    if components:
        members = next((members for members in components.values() if key in members), None)
        if members is not None:
            component_ports = {_port_alias(member, port_keys) for member in members}
            component_ports.discard(None)
            if len(component_ports) == 1:
                return "port:" + next(iter(component_ports))
            if len(component_ports) > 1:
                raise ValueError(f"Magic conductive component joins multiple ports: {sorted(component_ports)}")
    # A generated ``PORT.segment`` name is meaningful only when final
    # primitive-R connectivity proves that it reaches PORT.  The topology-side
    # comparison retains the historical spelling alias, while the final-RC
    # side must fail closed when its wire was dropped, including an empty
    # final component map.
    if require_component_for_segment and _port_alias(value, port_keys) is not None:
        k_key = internal.get(key)
        return "internal:" + (k_key if k_key is not None else key)
    alias = _port_alias(value, port_keys)
    if alias is not None:
        return "port:" + alias
    # ``internal`` is indexed by the Magic net key.  Multiple Magic contact
    # nets can therefore point back to one KLayout logical net while retaining
    # their distinct distributed-RC endpoints in the merged circuit.
    k_key = internal.get(key)
    if k_key is not None:
        return "internal:" + k_key
    return "internal:" + key


def _passive_signature(device: SpiceDevice, *, domain_net, defaults: dict[str, str]) -> tuple:
    _parameter_items(device)  # validate unsupported/duplicate native fields
    parameters = {key.casefold(): value for key, value in device.parameters}
    if device.model in {"ptap1", "ntap1"}:
        # A/P and R are alternate representations of the same PDK tap model.
        geometry = (f"R={_parameter_items(device)[0].split('=', 1)[1]}",)
    else:
        if device.model.startswith("cap_"):
            # ``m`` is a parallel multiplicity.  It is compared as an
            # aggregate in ``counter`` so one native ``m=2`` card is
            # equivalent to Magic's two model cards with the default
            # multiplicity of one.
            keys_to_compare = ("w", "l", "mm_ok", "ic")
            model_defaults = {"m": "1", "mm_ok": "0", "ic": "1E10"}
        else:
            keys_to_compare = ("w", "l", "ps", "b", "m", "mm_ok", "trise", "sw_et")
            model_defaults = {"ps": "0u", "b": "0", "m": "1", "mm_ok": "0",
                              "trise": "0", "sw_et": "0"}
        geometry = tuple(_parameter_scalar(parameters.get(key, model_defaults.get(key, defaults.get(key, ""))))
                         for key in keys_to_compare)
    if device.model in {"ptap1", "ntap1"} or device.model.startswith("cap_"):
        nets = tuple(sorted(domain_net(net) for net in device.nets))
    else:
        # SG13G2 resistor models have a symmetric first/second terminal and a
        # separate bulk terminal.  Keep that third terminal ordered.
        nets = (tuple(sorted(domain_net(net) for net in device.nets[:2])),
                domain_net(device.nets[2]))
    return device.model, tuple(geometry), nets


def _parameter_scalar(value: str) -> str:
    if not value:
        return ""
    try:
        return f"{_spice_number(value):.15g}"
    except ValueError:
        return value.casefold()


def _passive_equivalence(klayout: ParsedNetlist, magic: ParsedNetlist,
                         ports: list[str] | tuple[str, ...], mapping: _HBTMapping,
                         magic_topology: ParsedNetlist) -> dict:
    """Require geometry/topology equality for extracted passive devices.

    Magic's distributed R/C cards are intentionally outside this comparison;
    only its coarse model cards are matched to KLayout's device cards.  Taps
    tied to one net are electrically empty in the reviewed SG13G2 model and
    may be absent from Magic's model-card export.  A nontrivial tap mismatch is
    rejected rather than dropped.
    """
    port_keys = {_canonical_net(port) for port in ports}
    topology_components = _resistive_components(magic_topology, ports)

    def domain_for_klayout(net: str) -> str:
        key = _canonical_net(net)
        alias = _port_alias(net, port_keys)
        return "port:" + alias if alias is not None else "internal:" + key

    final_components = _resistive_components(magic, ports)

    def domain_for_topology(net: str) -> str:
        return _net_domain(net, port_keys=port_keys, internal=mapping.magic_to_k,
                           components=topology_components)

    def domain_for_final(net: str) -> str:
        return _net_domain(net, port_keys=port_keys, internal=mapping.magic_to_k,
                           components=final_components,
                           require_component_for_segment=True)

    def counter(parsed: ParsedNetlist, domain_net, *, allow_single_net_taps: bool) -> tuple[Counter, int]:
        values: Counter = Counter()
        ignored_taps = 0
        for device in parsed.devices:
            if device.model in _HBT_MODELS:
                continue
            if (device.model in {"ptap1", "ntap1"}
                    and allow_single_net_taps
                    and domain_net(device.nets[0]) == domain_net(device.nets[1])):
                ignored_taps += 1
                continue
            # Derived A/P fields do not participate in the simulator model,
            # while w/l and all model behavior parameters do.
            signature = _passive_signature(
                device, domain_net=domain_net,
                defaults={"ps": "0u", "b": "0"}
            )
            multiplicity = 1
            if device.model.startswith("cap_"):
                parameters = {key.casefold(): value for key, value in device.parameters}
                multiplicity_value = _spice_number(parameters.get("m", "1"))
                if (not math.isfinite(multiplicity_value)
                        or multiplicity_value <= 0
                        or not multiplicity_value.is_integer()):
                    raise ValueError(
                        f"{device.model} requires a positive integer m on {device.name}"
                    )
                multiplicity = int(multiplicity_value)
            values[signature] += multiplicity
        return values, ignored_taps

    k_counter, ignored_k_taps = counter(klayout, domain_for_klayout,
                                        allow_single_net_taps=True)
    topology_counter, ignored_topology_taps = counter(magic_topology, domain_for_topology,
                                                      allow_single_net_taps=True)
    magic_counter, ignored_magic_taps = counter(magic, domain_for_final,
                                                allow_single_net_taps=True)

    def require_equal(left: Counter, right: Counter, label: str) -> None:
        if left != right:
            missing = list((left - right).elements())
            extra = list((right - left).elements())
            raise ValueError(
                f"Passive geometry/topology differs for {label} "
                f"(missing={missing[:3]}, extra={extra[:3]})"
            )

    require_equal(k_counter, topology_counter, "KLayout vs Magic topology")
    require_equal(topology_counter, magic_counter, "Magic topology vs final RC")
    return {
        "matched_passives": sum(k_counter.values()),
        "ignored_single_net_taps": {
            "klayout": ignored_k_taps,
            "magic_topology": ignored_topology_taps,
            "magic_rc": ignored_magic_taps,
        },
        "reference": "Magic pre-RC topology plus final RC model-card check",
    }


def merge_hbt_netlists(klayout_raw: bytes | str, magic_raw: bytes | str,
                       ports: list[str] | tuple[str, ...],
                       magic_topology_raw: bytes | str | None = None
                       ) -> tuple[str, dict]:
    """Replace Magic HBT cards with uniquely mapped KLayout cards.

    Every passive and distributed primitive from Magic remains in the merged
    output.  HBT terminal names and all HBT geometry parameters come from the
    candidate-derived KLayout netlist, including ``Nx``.
    """
    klayout = parse_spice_netlist(klayout_raw, strict_devices=True)
    magic = parse_spice_netlist(magic_raw, strict_devices=False)
    if not magic_topology_raw:
        raise ValueError("Magic pre-RC topology evidence is required for HBT mapping")
    topology = parse_spice_netlist(magic_topology_raw, strict_devices=False)
    if _canonical_net(klayout.name) != _canonical_net(magic.name):
        raise ValueError(f"Extractor top-cell names differ: {klayout.name} vs {magic.name}")
    if _canonical_net(topology.name) != _canonical_net(magic.name):
        raise ValueError(f"Magic topology top-cell differs: {topology.name} vs {magic.name}")
    if (len(topology.hbt_devices) != len(magic.hbt_devices)
            or sorted(device.model for device in topology.hbt_devices)
            != sorted(device.model for device in magic.hbt_devices)):
        raise ValueError("Magic topology HBT population differs from final RC extraction")
    mapping = _hbt_mapping(klayout, magic, ports, topology)
    _require_final_wire_connectivity(topology, magic, ports)
    passive_details = _passive_equivalence(klayout, magic, ports, mapping, topology)
    port_names = _port_order(klayout, ports)
    lines = _as_text(magic_raw).splitlines()
    if any(len(device.line.physical_lines) != 1 for device in magic.hbt_devices):
        raise ValueError("Magic HBT card uses continuation lines; mapping is unsupported")

    port_keys = set(port_names)
    components = _resistive_components(topology, ports) if topology else {}
    final_components = _resistive_components(magic, ports)
    isolated_port_repairs: dict[tuple[str, str], None] = {}

    def mapped_terminal(k_index: int, m_index: int, k_net: str, m_net: str,
                        position: int) -> str:
        k_key, m_key = _canonical_net(k_net), _canonical_net(m_net)
        if k_key not in port_keys:
            expected_magic = mapping.terminal_nets.get((k_index, position))
            if expected_magic is None:
                raise ValueError(f"Unmapped internal HBT terminal {k_net} on device {k_index}")
            if _canonical_net(expected_magic) != m_key:
                if not any(
                        _canonical_net(repair_k) == k_key
                        and _canonical_net(repair_local) == m_key
                        and _canonical_net(repair_anchor) == _canonical_net(expected_magic)
                        for repair_k, repair_local, repair_anchor in mapping.internal_repairs):
                    raise ValueError(
                        f"Unproven internal HBT repair for {k_net} on device {k_index}"
                    )
                # The local endpoint is an isolated compact-device contact;
                # use the unique anchored contact while retaining every
                # candidate-derived passive card attached to that anchor.
                return expected_magic
            # Keep the per-device Magic contact.  If two contacts implement
            # one KLayout logical net, their explicit wire resistors remain in
            # the merged RC network rather than being collapsed here.
            return m_net
        expected = port_names[k_key]
        if m_key == k_key:
            return m_net
        topology_reachable = _explicit_component_ports(components, m_net, port_keys)
        final_reachable = _explicit_component_ports(final_components, m_net, port_keys)
        if topology_reachable == {k_key}:
            if final_reachable != {k_key}:
                raise ValueError(
                    f"Final RC endpoint {m_net} lost its wire path to {expected}"
                )
            # Keep the Magic contact endpoint so its series RC remains in the
            # merged circuit; changing it to the global port would short that
            # candidate-derived segment.
            return m_net
        if final_reachable == {k_key}:
            # extresist may introduce a PORT.segment contact only in the final
            # output.  Preserve that endpoint after the final graph proves its
            # path to the candidate port.
            return m_net
        reachable = topology_reachable or final_reachable
        if reachable:
            raise ValueError(
                f"Magic HBT endpoint {m_net} reaches ports {sorted(reachable)}, expected {expected}"
            )
        if position in (2, 3) and not reachable:
            # A missing Magic contact route is repairable only when the local
            # node is otherwise unused in both Magic outputs.  In that case
            # there is no extracted external RC endpoint to preserve; mapping
            # the compact-device terminal directly to the candidate-proven
            # port restores the intrinsic HBT connection without inventing a
            # wire or bypassing a parasitic.  Any referenced local node fails
            # closed because its physical route cannot be inferred here.
            if _port_alias(m_net, port_keys) is not None:
                raise ValueError(
                    f"Final RC endpoint {m_net} has no explicit wire path to {expected}"
                )
            refs = [*_endpoint_references(magic, m_net),
                    *_endpoint_references(topology, m_net)]
            if refs:
                raise ValueError(
                    f"Magic HBT endpoint {m_net} has unproven external references {refs[:3]}"
                )
            isolated_port_repairs[(m_net, expected)] = None
            return expected
        raise ValueError(f"Magic HBT endpoint {m_net} is not connected to expected port {expected}")

    mapped_by_magic = {m_index: k_index for k_index, m_index in mapping.pairs}
    for m_index, m_device in enumerate(magic.hbt_devices):
        k_device = klayout.hbt_devices[mapped_by_magic[m_index]]
        k_index = mapped_by_magic[m_index]
        nets = [mapped_terminal(k_index, m_index, k_net, m_net, position)
                for position, (k_net, m_net) in enumerate(zip(k_device.nets, m_device.nets))]
        params = _parameter_items(k_device)
        model = _MODEL_DISPLAY.get(k_device.model, k_device.model)
        lines[m_device.line.physical_lines[0]] = " ".join(
            [m_device.name, *nets, model, *params]
        )
    # Make the published interface order explicit even when the extractor
    # emitted a different legal port order.  Device endpoints above retain
    # Magic's spelling for any named/segmented contact.
    header_line = next(line for line in magic.lines
                       if (_tokens(line) and _tokens(line)[0].casefold() == ".subckt"))
    lines[header_line.physical_lines[0]] = f".SUBCKT {magic.name} {' '.join(ports)}"
    merged = "\n".join(lines).rstrip() + "\n"
    details = {
        "top_cell": klayout.name,
        "ports": list(ports),
        "hbt_count": len(mapping.pairs),
        "device_source": "KLayout SG13G2 net_only extraction",
        "distributed_rc_source": "Magic extresist extraction",
        "mapping": [
            {"klayout_device": klayout.hbt_devices[k_index].name,
             "magic_device": magic.hbt_devices[m_index].name,
             "klayout_model": klayout.hbt_devices[k_index].model,
             "magic_model": magic.hbt_devices[m_index].model}
            for k_index, m_index in mapping.pairs
        ],
        "internal_net_mapping": {
            k_key: list(magic_nets) if len(magic_nets) > 1 else magic_nets[0]
            for k_key, magic_nets in mapping.k_to_magic.items()
        },
        "terminal_net_mapping": [
            {"klayout_device": klayout.hbt_devices[k_index].name,
             "terminal_index": position,
             "magic_net": magic_net}
            for (k_index, position), magic_net in sorted(mapping.terminal_nets.items())
        ],
        "magic_topology_hbt_mapping": [
            {"magic_device": magic.hbt_devices[m_index].name,
             "topology_device": topology.hbt_devices[t_index].name}
            for m_index, t_index in sorted(mapping.topology_pairs.items())
        ],
        "native_parameter_policy": {
            "hbt": "Nx/m (and model-controlled le for long/HV variants); fixed symbol we/le annotations are validated then omitted",
            "passives": "w/l plus model behavior parameters; native A/P is omitted only after tap R conversion",
            "tap": "A/P converted with the reviewed SG13G2 xschem parallel conductance expression",
        },
        "synthetic_hbt_ties": [],
        "isolated_hbt_port_repairs": [{"local": local, "port": port,
                                       "external_references": 0}
                                      for local, port in sorted(isolated_port_repairs)],
        "isolated_hbt_internal_repairs": [
            {"klayout_net": k_net, "isolated_local": local,
             "anchored_contact": anchor, "external_references": 0}
            for k_net, local, anchor in mapping.internal_repairs
        ],
        "passive_equivalence": passive_details,
    }
    return merged, details


class _HBTMagicRCDocker(MagicRCDocker):
    """Defer proven HBT contact diagnostics to the composite graph validator.

    SG13G2 describes HBTs as Magic msubckt devices. ResFixUpConnections still uses
    MOS terminal names for their compact contacts, which may not have a
    separate resistance mesh node. This is not a general warning waiver:
    native device identity and the named terminal must agree, and the caller
    must subsequently validate both Magic graphs against native KLayout HBTs.
    """

    @property
    def identity(self) -> dict:
        return {**super().identity,
                "diagnostic_review_sha256": Asset(Path(__file__).read_bytes(), "python").sha256,
                "diagnostic_policy": "native HBT contacts require subsequent composite graph validation"}

    def _check_diagnostics(self, log: str, files: dict[str, Asset]) -> tuple[str, dict[str, Asset]]:
        pattern = re.compile(
            r"Missing (gate|source|drain|substrate) connection of device at "
            r"\((-?\d+) (-?\d+)\) on net (.+)", re.IGNORECASE)
        diagnostics = []
        for line in log.splitlines():
            if re.search(r"missing\s+\w+\s+connection", line, re.IGNORECASE):
                match = pattern.fullmatch(line)
                if match is None:
                    return "Unrecognized Magic HBT terminal diagnostic", {}
                diagnostics.append(match)
        if not diagnostics:
            return super()._check_diagnostics(log, files)
        reviewed = []
        try:
            devices: dict[tuple[int, int], list[list[str]]] = {}
            for line in files["extraction.ext"].content.decode().splitlines():
                if not line.startswith("device "):
                    continue
                fields = shlex.split(line)
                coordinate = (int(fields[3]), int(fields[4]))
                devices.setdefault(coordinate, []).append(fields)
            # Magic msubckt records: parameters, bulk, then gate/source/drain
            # triples (net, length, attributes). Keep its native terminal order.
            positions = {"substrate": 0, "gate": 1, "source": 4, "drain": 7}
            for match in diagnostics:
                terminal, x, y, net = match.groups()
                coordinate = (int(x), int(y))
                matches = devices.get(coordinate, [])
                if len(matches) != 1:
                    raise ValueError(f"Missing or ambiguous native device at {coordinate}")
                fields = matches[0]
                if fields[1] != "msubckt" or fields[2].casefold() not in _HBT_MODELS:
                    raise ValueError(f"Diagnostic does not identify a supported HBT at {coordinate}")
                terminals = fields[7:]
                while terminals and "=" in terminals[0]:
                    terminals = terminals[1:]
                if len(terminals) != 10 or terminals[positions[terminal.casefold()]] != net:
                    raise ValueError(f"Diagnostic terminal differs from the native HBT at {coordinate}")
                reviewed.append({"diagnostic": match.group(), "model": fields[2],
                                 "coordinate": list(coordinate), "terminal": terminal, "net": net})
        except (KeyError, IndexError, ValueError, UnicodeError) as error:
            return f"Unverified Magic HBT terminal diagnostic: {error}", {}
        remaining = "\n".join(line for line in log.splitlines() if not pattern.fullmatch(line))
        error, evidence = super()._check_diagnostics(remaining, files)
        evidence["terminal_diagnostic_review"] = Asset(json.dumps({
            "status": "requires_composite_mapping", "diagnostics": reviewed,
        }, indent=2).encode(), "json")
        return error, evidence


class SG13G2HBTRCDocker:
    """Extract candidate-derived HBT geometry plus Magic distributed RC."""

    wire_resistance = True

    def __init__(self, *, image: str, klayout_support: str, klayout_profile: str,
                 magic_support: str, technology: str, tech_name: str, style: str,
                 timeout_seconds: float = 180, disable_tap_extraction: bool = False):
        if type(disable_tap_extraction) is not bool:
            raise TypeError("disable_tap_extraction must be a boolean")
        self.disable_tap_extraction = disable_tap_extraction
        self.klayout = KLayoutDocker(image=image, check="lvs", support=klayout_support,
                                     profile=klayout_profile, timeout_seconds=timeout_seconds)
        self.magic = _HBTMagicRCDocker(image=image, support=magic_support, technology=technology,
                                     tech_name=tech_name, style=style,
                                     timeout_seconds=timeout_seconds)
        self.runner = Asset(Path(__file__).with_name("hbt_runner.py").read_bytes(), "python")
        self.timeout_seconds = timeout_seconds

    @property
    def identity(self) -> dict:
        return {
            "adapter": "sg13g2-hbt-rc-docker",
            "adapter_sha256": Asset(Path(__file__).read_bytes(), "python").sha256,
            "runner_sha256": self.runner.sha256,
            "klayout": self.klayout.identity,
            "magic": self.magic.identity,
            "parasitics": "candidate_hbt_geometry_plus_distributed_rc",
            "disable_tap_extraction": self.disable_tap_extraction,
            "mapping_policy": (
                "unique terminal mapping; explicit primitive-wire connectivity may "
                "split one logical internal net; an isolated compact terminal may "
                "use one retained passive/HBT anchor; ambiguous or unproven mappings rejected"
            ),
            "isolated_terminal_policy": (
                "restore a candidate-proven port, or a unique retained Magic passive/HBT "
                "anchor for an internal net, only when the local contact has zero "
                "external R/C references in both Magic outputs; no synthetic ties"
            ),
        }

    def run(self, job: Job, inputs: dict[str, Asset]) -> JobResult:
        if job.stage != "extract" or set(inputs) - {"layout", "task"} or "layout" not in inputs:
            raise ValueError("SG13G2 HBT extraction requires layout and optional task inputs")
        if inputs["layout"].format != "gds" or dict(job.outputs) != {"netlist": "spice"}:
            raise ValueError("SG13G2 HBT extraction requires GDS and a SPICE netlist output")
        keys(job.parameters, {"ports"}, {"top_cell"}, "SG13G2 HBT extraction parameters")
        params = job.parameters
        ports = params["ports"]
        if not isinstance(ports, list) or not ports or any(not isinstance(port, str) for port in ports):
            raise ValueError("Extraction requires an ordered list of unique ports")
        if len({_canonical_net(port) for port in ports}) != len(ports):
            raise ValueError("Extraction ports must be unique case-insensitively")
        top = params.get("top_cell")
        if "task" in inputs:
            if inputs["task"].format != "json":
                raise ValueError("Task description must be JSON")
            task = json.loads(inputs["task"].content)
            configured = task["output"]["top_cell"]
            if top is not None and top != configured:
                raise ValueError("Extraction top cell differs from task configuration")
            top = configured
        top = text(top, "top cell")

        # This standard PDK mode affects candidate extraction only. The
        # separate physical LVS gate still checks the task's explicit taps.
        # Recording it in both identity and config makes the body boundary
        # reproducible; cases must disclose and calibrate its idealization.
        variables = {**self.klayout.settings["variables"],
                     "disable_tap_extraction": "true" if self.disable_tap_extraction else "false"}
        config = Asset(json.dumps({"deck": self.klayout.settings["deck"],
                                   "variables": variables,
                                   "top_cell": top}, sort_keys=True).encode(), "json")
        files = {"candidate.gds": inputs["layout"], "run.py": self.runner,
                 "config.json": config, **self.klayout.support.mounted_files()}
        extraction = self.klayout.tool.run(
            ["python", "run.py"], files,
            {"result.json": "json", "tool.log": "text", "complete.txt": "text",
             "extracted.spice": "spice"},
        )
        evidence = {**self.klayout.support.evidence(), **extraction.evidence,
                    **{f"klayout:{name}": asset for name, asset in extraction.files.items()},
                    "klayout_runner": self.runner, "klayout_configuration": config}
        if extraction.reason or extraction.returncode != 0:
            return JobResult("error", extraction.reason or "KLayout extraction failed", evidence=evidence)
        try:
            verdict = json.loads(extraction.files["result.json"].content)
        except (KeyError, ValueError, TypeError) as error:
            return JobResult("error", f"Invalid KLayout extraction result: {error}", evidence=evidence)
        if verdict.get("status") != "passed":
            return JobResult("error", verdict.get("reason") or "KLayout extraction did not pass", evidence=evidence)

        magic_result = self.magic.run(job, inputs)
        evidence.update({f"magic:{name}": asset for name, asset in magic_result.evidence.items()})
        if magic_result.status != "passed":
            return JobResult("error", magic_result.reason or "Magic extraction failed", evidence=evidence)
        try:
            klayout_raw = extraction.files["extracted.spice"].content
            magic_raw = magic_result.outputs["netlist"].content
            topology_asset = magic_result.evidence.get("topology.spice")
            topology_raw = topology_asset.content if topology_asset else None
            merged, details = merge_hbt_netlists(klayout_raw, magic_raw, ports, topology_raw)
        except (KeyError, ValueError, UnicodeError) as error:
            evidence["klayout_native_netlist"] = Asset(klayout_raw, "spice") if "klayout_raw" in locals() else Asset(b"", "spice")
            if "magic_raw" in locals():
                evidence["magic_rc_netlist"] = Asset(magic_raw, "spice")
            return JobResult("error", f"Unsafe HBT extractor mapping: {error}", evidence=evidence)
        merged_asset = Asset(merged.encode(), "spice")
        evidence.update({"klayout_native_netlist": Asset(klayout_raw, "spice"),
                         "magic_rc_netlist": Asset(magic_raw, "spice"),
                         "mapping": Asset(json.dumps(details, indent=2, sort_keys=True).encode(), "json"),
                         "merged_netlist": merged_asset})
        return JobResult("passed", outputs={"netlist": merged_asset}, evidence=evidence)


__all__ = ["SG13G2HBTRCDocker", "convert_klayout_netlist", "merge_hbt_netlists",
           "parse_spice_netlist"]
