"""Model-card geometry and passive anchors across native extraction outputs."""

from __future__ import annotations

import math
from collections import Counter
from typing import TYPE_CHECKING

from .connectivity import (
    _endpoint_references,
    _internal_terminal_state,
    _port_alias,
    _resistive_components,
)
from .netlist import (
    _HBT_MODELS,
    ParsedNetlist,
    SpiceDevice,
    _canonical_net,
    _parameter_items,
    _spice_number,
)

if TYPE_CHECKING:
    from .matching import _HBTMapping


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
