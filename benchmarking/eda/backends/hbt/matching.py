"""Topology matching and passive correspondence for SG13G2 HBT extraction."""

from __future__ import annotations

from dataclasses import dataclass

from benchmarking.eda.backends.hbt.connectivity import (
    _explicit_component_ports,
    _hbt_topology_pairs,
    _require_final_wire_connectivity,
    _resistive_components,
    _same_resistive_component,
)
from benchmarking.eda.backends.hbt.netlist import (
    _MODEL_DISPLAY,
    ParsedNetlist,
    SpiceDevice,
    _canonical_net,
    _parameter_items,
    _port_order,
)
from benchmarking.eda.backends.hbt.passives import _passive_equivalence, _passive_shape
from benchmarking.eda.netlists.spice import tokens as spice_tokens


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

    def resistor_port_anchors(netlist: ParsedNetlist, net: str) -> set[tuple]:
        """Use native model resistors, never parasitic conductance, as anchors."""
        key = _canonical_net(net)
        anchors = set()
        for device in netlist.devices:
            if not device.model.startswith("r") or len(device.nets) < 2:
                continue
            left, right = map(_canonical_net, device.nets[:2])
            other = right if left == key else left if right == key else None
            if other in port_keys:
                anchors.add((_passive_shape(device), other))
        return anchors

    def pair_score(k_device: SpiceDevice, m_device: SpiceDevice,
                   m_index: int) -> int | None:
        if k_device.model != m_device.model:
            return None
        score = 0
        for position, (k_net, m_net) in enumerate(zip(k_device.nets, m_device.nets)):
            k_key, m_key = _canonical_net(k_net), _canonical_net(m_net)
            if k_key in port_keys:
                if m_key == k_key:
                    score += 100
                elif position in (2, 3):
                    # A local contact is valid only when native wire
                    # evidence proves its path to the named port.
                    reachable = (_explicit_component_ports(components, m_net, port_keys)
                                 or _explicit_component_ports(final_components, m_net, port_keys))
                    if reachable and reachable != {k_key}:
                        return None
                    if reachable != {k_key}:
                        return None
                    score += 10
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
            elif magic_topology is not None:
                topology_device = magic_topology.hbt_devices[topology_pairs[m_index]]
                native_anchors = resistor_port_anchors(klayout, k_net)
                magic_anchors = resistor_port_anchors(magic_topology, topology_device.nets[position])
                # Missing contacts still go through the existing isolated-contact
                # proof. When both extractors retain anchors, named tail ports
                # and physical resistor geometry must agree before graph search.
                if native_anchors and magic_anchors and native_anchors != magic_anchors:
                    return None
        return score

    candidates: dict[int, list[tuple[int, int]]] = {}
    for k_index, k_device in enumerate(k_devices):
        choices = []
        for m_index, m_device in enumerate(m_devices):
            score = pair_score(k_device, m_device, m_index)
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
                        return False, 0
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
    for k_key, m_values in k_to_magic_sets.items():
        if len({_canonical_net(value) for value in m_values}) > 1 and not _same_resistive_component(
                components, list(m_values)) and not _same_resistive_component(
                final_components, list(m_values)):
            raise ValueError(
                f"KLayout internal net {k_key} maps to disconnected Magic contact nets"
            )
    k_to_magic = {
        k_key: tuple(sorted(values, key=_canonical_net))
        for k_key, values in k_to_magic_sets.items()
    }
    return _HBTMapping(mapping, terminal_nets, k_to_magic, magic_to_k,
                       topology_pairs)


@dataclass(frozen=True)
class ValidatedMergePlan:
    """Approved HBT/header replacements after topology and passive checks."""

    replacements: tuple[tuple[int, str], ...]
    details: dict


def build_merge_plan(klayout: ParsedNetlist, magic: ParsedNetlist,
                     ports: list[str] | tuple[str, ...], topology: ParsedNetlist) -> ValidatedMergePlan:
    """Require native connectivity before replacing device model parameters."""
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
    replacements = []
    if any(len(device.line.physical_lines) != 1 for device in magic.hbt_devices):
        raise ValueError("Magic HBT card uses continuation lines; mapping is unsupported")

    port_keys = set(port_names)
    components = _resistive_components(topology, ports) if topology else {}
    final_components = _resistive_components(magic, ports)

    def mapped_terminal(k_index: int, m_index: int, k_net: str, m_net: str,
                        position: int) -> str:
        k_key, m_key = _canonical_net(k_net), _canonical_net(m_net)
        if k_key not in port_keys:
            expected_magic = mapping.terminal_nets.get((k_index, position))
            if expected_magic is None:
                raise ValueError(f"Unmapped internal HBT terminal {k_net} on device {k_index}")
            if _canonical_net(expected_magic) != m_key:
                raise ValueError(f'Extracted internal HBT terminal differs: {m_net}')
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
        raise ValueError(f"Magic HBT endpoint {m_net} is not connected to expected port {expected}")

    mapped_by_magic = {m_index: k_index for k_index, m_index in mapping.pairs}
    for m_index, m_device in enumerate(magic.hbt_devices):
        k_device = klayout.hbt_devices[mapped_by_magic[m_index]]
        k_index = mapped_by_magic[m_index]
        nets = [mapped_terminal(k_index, m_index, k_net, m_net, position)
                for position, (k_net, m_net) in enumerate(zip(k_device.nets, m_device.nets))]
        params = _parameter_items(k_device)
        model = _MODEL_DISPLAY.get(k_device.model, k_device.model)
        replacements.append((m_device.line.physical_lines[0], " ".join(
            [m_device.name, *nets, model, *params]
        )))
    # Make the published interface order explicit even when the extractor
    # emitted a different legal port order.  Device endpoints above retain
    # Magic's spelling for any named/segmented contact.
    header_line = next(line for line in magic.lines
                       if (spice_tokens(line) and spice_tokens(line)[0].casefold() == ".subckt"))
    replacements.append((header_line.physical_lines[0], f".SUBCKT {magic.name} {' '.join(ports)}"))
    for continuation in header_line.physical_lines[1:]:
        replacements.append((continuation, ""))
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
        "passive_equivalence": passive_details,
        "native_parameter_policy": {
            "hbt": "Nx/m (and model-controlled le for long/HV variants); fixed symbol we/le annotations are validated then omitted",
            "passives": "native w/l and model behavior parameters are validated",
            "tap": "requires native extracted R; geometry is not converted",
        },
    }
    return ValidatedMergePlan(tuple(replacements), details)
