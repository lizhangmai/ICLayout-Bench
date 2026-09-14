"""Contracts for candidate-derived SG13G2 HBT extraction."""

import pytest

from benchmarking.hbt import convert_klayout_netlist, merge_hbt_netlists


def test_klayout_conversion_keeps_nx_and_requested_port_order():
    native = b"""* native KLayout output
.SUBCKT AMP VEE OUT IN
Q$1 $internal IN VEE VEE npn13G2 we=70n le=900n Nx=5 m=1
Q$2 OUT $internal VEE VEE npn13G2 we=70n le=900n Nx=4 m=1
R$3 OUT VEE VEE rppd w=2u l=3u ps=0u b=0 m=1
.ENDS AMP
"""

    converted = convert_klayout_netlist(native, ["IN", "OUT", "VEE"])

    assert ".SUBCKT AMP IN OUT VEE" in converted
    assert "Nx=5" in converted and "Nx=4" in converted
    assert "$internal" not in converted
    assert "rppd w=2u l=3u ps=0u b=0 m=1" in converted


def test_merge_preserves_magic_series_endpoints_and_rc():
    klayout = b""".SUBCKT AMP OUT IN GND
Q1 OUT IN GND GND npn13G2 we=70n le=900n Nx=5 m=1
.ENDS AMP
"""
    magic = b""".SUBCKT AMP OUT IN GND
Q1 out_local in_local e_local GND npn13g2 le=70n we=0.9u
R1 out_local OUT 1
R2 in_local IN 2
R3 e_local GND 3
.ENDS AMP
"""

    merged, details = merge_hbt_netlists(klayout, magic, ["OUT", "IN", "GND"], magic)

    assert "Q1 out_local in_local e_local GND npn13G2" in merged
    assert "Q1 OUT IN GND GND" not in merged
    assert "R1 out_local OUT 1" in merged
    assert "R2 in_local IN 2" in merged
    assert "R3 e_local GND 3" in merged
    assert details["synthetic_hbt_ties"] == []


def test_merge_rejects_ambiguous_parallel_hbts():
    klayout = b""".SUBCKT AMP OUT IN GND
Q1 OUT IN GND GND npn13G2 we=70n le=900n Nx=5 m=1
Q2 OUT IN GND GND npn13G2 we=70n le=900n Nx=5 m=1
.ENDS AMP
"""
    magic = b""".SUBCKT AMP OUT IN GND
Q1 OUT IN GND GND npn13g2 we=70n le=900n Nx=5 m=1
Q2 OUT IN GND GND npn13g2 we=70n le=900n Nx=5 m=1
.ENDS AMP
"""

    with pytest.raises(ValueError, match="ambiguous"):
        merge_hbt_netlists(klayout, magic, ["OUT", "IN", "GND"], magic)


def test_merge_rejects_passive_geometry_mismatch():
    klayout = b""".SUBCKT AMP OUT IN GND
Q1 OUT IN GND GND npn13G2 we=70n le=900n Nx=5 m=1
R1 OUT GND GND rppd w=2u l=3u ps=0u b=0 m=1
.ENDS AMP
"""
    magic = b""".SUBCKT AMP OUT IN GND
Q1 OUT IN GND GND npn13g2 we=70n le=900n Nx=5 m=1
R1 OUT GND GND rppd w=2u l=4u ps=0u b=0 m=1
.ENDS AMP
"""

    with pytest.raises(ValueError, match="Passive geometry/topology"):
        merge_hbt_netlists(klayout, magic, ["OUT", "IN", "GND"], magic)


def test_mapping_uses_constrained_search_for_twelve_hbts():
    ports = [*(f"OUT{index}" for index in range(12)), "IN", "GND"]
    k_cards = [f"Q{index} OUT{index} IN GND GND npn13G2 we=70n le=900n Nx={index + 1} m=1"
               for index in range(12)]
    m_cards = list(reversed([card.replace("npn13G2", "npn13g2") for card in k_cards]))
    klayout = (f".SUBCKT AMP {' '.join(ports)}\n" + "\n".join(k_cards)
               + "\n.ENDS AMP\n").encode()
    magic = (f".SUBCKT AMP {' '.join(ports)}\n" + "\n".join(m_cards)
             + "\n.ENDS AMP\n").encode()

    merged, details = merge_hbt_netlists(klayout, magic, ports, magic)

    assert details["hbt_count"] == 12
    assert merged.count(" npn13G2 ") == 12


def test_shared_candidate_net_keeps_each_magic_rc_contact():
    """A distributed resistor may split one KLayout net into two contacts."""
    ports = ["OUT", "IN1", "IN2", "GND"]
    klayout = b""".SUBCKT AMP OUT IN1 IN2 GND
Q1 OUT IN1 NINT GND npn13G2 we=70n le=900n Nx=5 m=1
Q2 NINT IN2 GND GND npn13G2 we=70n le=900n Nx=4 m=1
.ENDS AMP
"""
    magic = b""".SUBCKT AMP OUT IN1 IN2 GND
Q1 out_local in1_local n1 GND npn13g2 we=70n le=900n Nx=5 m=1
Q2 n2 in2_local GND GND npn13g2 we=70n le=900n Nx=4 m=1
R1 out_local OUT 1
R2 in1_local IN1 2
R3 in2_local IN2 3
R4 n1 n2 4
.ENDS AMP
"""

    merged, details = merge_hbt_netlists(klayout, magic, ports, magic)

    assert "Q1 out_local in1_local n1 GND npn13G2" in merged
    assert "Q2 n2 in2_local GND GND npn13G2" in merged
    assert "R4 n1 n2 4" in merged
    assert details["internal_net_mapping"]["nint"] == ["n1", "n2"]


def test_fixed_hbt_geometry_does_not_use_absolute_unit_tolerance():
    native = b""".SUBCKT AMP OUT IN GND
Q1 OUT IN GND GND npn13G2 we=71n le=900n Nx=5 m=1
.ENDS AMP
"""

    with pytest.raises(ValueError, match="drawn geometry"):
        convert_klayout_netlist(native, ["OUT", "IN", "GND"])


@pytest.mark.parametrize("model", ["ptap1", "ntap1"])
def test_tap_area_and_perimeter_are_mapped_to_model_resistance(model):
    native = f""".SUBCKT AMP OUT IN GND
Q1 OUT IN GND GND npn13G2 we=70n le=900n Nx=5 m=1
R1 OUT GND {model} A=1p P=4u
.ENDS AMP
""".encode()

    converted = convert_klayout_netlist(native, ["OUT", "IN", "GND"])

    # The model receives an explicit R derived from the PDK symbol expression;
    # the native A/P values must not silently select the model default.
    # The reviewed SG13G2 symbol law gives an area branch of 980 ohm
    # and perimeter branch of 245 ohm for 1 um² / 4 um: parallel R=196 ohm.
    card = next(line for line in converted.splitlines() if f" {model} " in line)
    resistance = float(card.split('R=', 1)[1].split()[0])
    assert resistance == pytest.approx(196)
