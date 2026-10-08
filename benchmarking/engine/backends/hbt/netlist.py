"""SPICE parsing and SG13G2 HBT model conversion."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from ...netlists.spice import LogicalLine, logical_lines
from ...netlists.spice import number as _spice_number
from ...netlists.spice import tokens as spice_tokens

# These are the SG13G2 subcircuits emitted by the pinned KLayout runset and
# accepted by the reviewed ngspice model bundle. Terminal counts are part of
# the model interface, not inferred from a source netlist.
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


def _same_spice_value(actual: str, expected: str) -> bool:
    try:
        left, right = _spice_number(actual), _spice_number(expected)
    except ValueError:
        return actual.casefold() == expected.casefold()
    return (math.isfinite(left) and math.isfinite(right)
            and math.isclose(left, right, rel_tol=1e-6, abs_tol=0.0))


@dataclass(frozen=True)
class SpiceDevice:
    name: str
    nets: tuple[str, ...]
    model: str
    parameters: tuple[tuple[str, str], ...]
    line: LogicalLine


@dataclass(frozen=True)
class ParsedNetlist:
    name: str
    ports: tuple[str, ...]
    devices: tuple[SpiceDevice, ...]
    lines: tuple[LogicalLine, ...]

    @property
    def hbt_devices(self) -> tuple[SpiceDevice, ...]:
        return tuple(device for device in self.devices if device.model in _HBT_MODELS)


def netlist_text(raw: bytes | str) -> str:
    return raw.decode("utf-8") if isinstance(raw, bytes) else raw


def _parse_parameters(tokens: list[str], line: LogicalLine) -> tuple[tuple[str, str], ...]:
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
    lines = logical_lines(raw)
    subcircuit: LogicalLine | None = None
    end_index: int | None = None
    for index, line in enumerate(lines):
        tokens = spice_tokens(line)
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
        tokens = spice_tokens(line)
        if tokens and not tokens[0].startswith(("*", ";")):
            raise ValueError("SPICE netlist contains content after .ENDS")
    header = spice_tokens(subcircuit)
    name, ports = header[1], tuple(header[2:])
    end_tokens = spice_tokens(lines[end_index])
    if len(end_tokens) > 1 and _canonical_net(end_tokens[1]) != _canonical_net(name):
        raise ValueError(f"SPICE .ENDS name differs from .SUBCKT: {end_tokens[1]} vs {name}")
    if not ports or len({_canonical_net(port) for port in ports}) != len(ports):
        raise ValueError("SPICE subcircuit requires unique top-level ports")

    devices: list[SpiceDevice] = []
    sub_index = lines.index(subcircuit)
    unknown = []
    for line in lines[sub_index + 1:end_index]:
        tokens = spice_tokens(line)
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

__all__ = ["ParsedNetlist", "SpiceDevice", "convert_klayout_netlist", "netlist_text", "parse_spice_netlist"]
