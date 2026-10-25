"""Apply approved HBT substitutions while preserving distributed Magic RC."""

from __future__ import annotations

from benchmarking.eda.backends.hbt.matching import build_merge_plan
from benchmarking.eda.backends.hbt.netlist import netlist_text, parse_spice_netlist
from benchmarking.eda.netlists.dspf import ExtractionRejected


def merge_hbt_netlists(klayout_raw: bytes | str, magic_raw: bytes | str,
                       ports: list[str] | tuple[str, ...],
                       magic_topology_raw: bytes | str | None = None
                       ) -> tuple[str, dict]:
    """Validate native correspondence, then apply its complete replacement plan."""
    klayout = parse_spice_netlist(klayout_raw, strict_devices=True)
    magic = parse_spice_netlist(magic_raw, strict_devices=False)
    if not magic_topology_raw:
        raise ValueError("Magic pre-RC topology evidence is required for HBT mapping")
    topology = parse_spice_netlist(magic_topology_raw, strict_devices=False)
    try:
        plan = build_merge_plan(klayout, magic, ports, topology)
    except ValueError as error:
        raise ExtractionRejected(str(error)) from error
    lines = netlist_text(magic_raw).splitlines()
    for line, replacement in plan.replacements:
        lines[line] = replacement
    return "\n".join(lines).rstrip() + "\n", plan.details


__all__ = ["merge_hbt_netlists"]
