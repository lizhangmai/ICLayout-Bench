"""Explicit wire components and compact-contact evidence in Magic netlists."""

from __future__ import annotations

from ...netlists.spice import LogicalLine
from ...netlists.spice import tokens as spice_tokens
from .netlist import (
    _HBT_MODELS,
    _MODEL_TERMINALS,
    ParsedNetlist,
    _canonical_net,
    _same_spice_value,
)


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
                 if (spice_tokens(line) and spice_tokens(line)[0].casefold() == ".subckt"))
    end = next(index for index in range(start + 1, len(lines))
               if (spice_tokens(lines[index]) and spice_tokens(lines[index])[0].casefold() == ".ends"))
    for line in lines[start + 1:end]:
        tokens = spice_tokens(line)
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


def _card_net_fields(line: LogicalLine) -> tuple[str, tuple[str, ...]] | None:
    """Return ``(card kind, net fields)`` for a parsed body line.

    This scans primitive Magic C/R cards as well as modelled cards.  Primitive
    cards are deliberately not added to ``ParsedNetlist.devices`` because
    they are distributed parasitics, but their endpoint references still
    matter when deciding whether an HBT contact may be repaired.
    """
    tokens = spice_tokens(line)
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
                 if (spice_tokens(line) and spice_tokens(line)[0].casefold() == ".subckt"))
    end = next(index for index in range(start + 1, len(parsed.lines))
               if (spice_tokens(parsed.lines[index]) and spice_tokens(parsed.lines[index])[0].casefold() == ".ends"))
    for line in parsed.lines[start + 1:end]:
        fields = _card_net_fields(line)
        if fields is None:
            continue
        model, nets = fields
        if model in _HBT_MODELS:
            continue
        if any(_canonical_net(net) == key for net in nets):
            references.append((spice_tokens(line)[0], model))
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
