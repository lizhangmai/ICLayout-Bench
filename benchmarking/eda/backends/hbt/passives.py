"""Model-card geometry and passive anchors across native extraction outputs."""

from __future__ import annotations

import math
from collections import Counter
from typing import TYPE_CHECKING

from benchmarking.eda.backends.hbt.connectivity import (
    _port_alias,
    _resistive_components,
)
from benchmarking.eda.backends.hbt.netlist import (
    _HBT_MODELS,
    ParsedNetlist,
    SpiceDevice,
    _canonical_net,
    _parameter_items,
    _spice_number,
)

if TYPE_CHECKING:
    from benchmarking.eda.backends.hbt.matching import _HBTMapping


def _passive_shape(device: SpiceDevice) -> tuple:
    """Compare model-card geometry without making net names part of shape."""
    return _passive_signature(
        device, domain_net=lambda _net: "__shape__",
        defaults={"ps": "0u", "b": "0"}
    )


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
