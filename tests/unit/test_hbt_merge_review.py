"""Independent fail-closed contracts for candidate-derived HBT merging."""

from textwrap import dedent

import pytest

from layout_eval.hbt import convert_klayout_netlist, merge_hbt_netlists

pytestmark = pytest.mark.unit

PORTS = ["OUT", "IN", "GND"]


def _klayout(*, passive: bool = False, top: str = "AMP", we: str = "70n") -> bytes:
    cards = [f"Q1 OUT IN GND GND npn13G2 we={we} le=900n Nx=5 m=1"]
    if passive:
        cards.append("RDEV OUT GND GND rppd w=2u l=3u ps=0u b=0 m=1")
    body = "\n".join(cards)
    return dedent(f"""\
        .SUBCKT {top} OUT IN GND
        {body}
        .ENDS {top}
    """).encode()


def _magic(*, passive: bool = False, top: str = "AMP", rc: bool = True) -> bytes:
    cards = ["Q1 out_local in_local e_local GND npn13g2 we=70n le=900n Nx=5 m=1"]
    if passive:
        cards.append("RDEV OUT GND GND rppd w=2u l=3u ps=0u b=0 m=1")
    if rc:
        cards.extend([
            "R1 out_local OUT 1",
            "R2 in_local IN 2",
            "R3 e_local GND 3",
        ])
    body = "\n".join(cards)
    return dedent(f"""\
        .SUBCKT {top} OUT IN GND
        {body}
        .ENDS {top}
    """).encode()


def test_final_magic_passive_deletion_is_rejected():
    """The published RC netlist must retain passives present in topology evidence."""
    klayout = _klayout(passive=True)
    topology = _magic(passive=True)
    final_magic = _magic(passive=False)

    with pytest.raises(ValueError):
        merge_hbt_netlists(klayout, final_magic, PORTS, topology)


def test_final_magic_extra_passive_is_rejected():
    """The final RC netlist must not gain unchecked model-card passives."""
    klayout = _klayout(passive=False)
    topology = _magic(passive=False)
    final_magic = _magic(passive=True)

    with pytest.raises(ValueError):
        merge_hbt_netlists(klayout, final_magic, PORTS, topology)


@pytest.mark.parametrize("card", [
    "D1 OUT GND unknown_model",
    "V1 OUT GND 0",
    "R_BAD OUT IN",
    "R_BAD OUT IN unknown_model",
    "R_BAD OUT IN 1e309",
    ".include unreviewed.spice",
])
def test_magic_unknown_cards_are_rejected(card):
    magic = _magic().replace(b".ENDS AMP\n", f"{card}\n.ENDS AMP\n".encode())

    with pytest.raises(ValueError):
        merge_hbt_netlists(_klayout(), magic, PORTS, _magic())


def test_magic_preamble_directive_is_rejected():
    magic = b".include unreviewed.spice\n" + _magic()

    with pytest.raises(ValueError):
        merge_hbt_netlists(_klayout(), magic, PORTS, _magic())


@pytest.mark.parametrize("trailing", [
    ".SUBCKT EXTRA X\n.ENDS EXTRA",
    "R_EXTRA OUT IN 1",
])
def test_content_after_magic_ends_is_rejected(trailing):
    magic = _magic() + f"{trailing}\n".encode()

    with pytest.raises(ValueError):
        merge_hbt_netlists(_klayout(), magic, PORTS, _magic())


def test_extractor_top_cell_mismatch_is_rejected():
    with pytest.raises(ValueError):
        merge_hbt_netlists(_klayout(top="OTHER"), _magic(), PORTS, _magic())


def test_missing_magic_topology_evidence_is_rejected():
    with pytest.raises(ValueError):
        merge_hbt_netlists(_klayout(), _magic(), PORTS)


def test_magic_topology_must_contain_the_hbt_population():
    topology = _magic(passive=True).replace(
        b"        Q1 out_local in_local e_local GND npn13g2 we=70n le=900n Nx=5 m=1\n", b""
    )

    with pytest.raises(ValueError):
        merge_hbt_netlists(_klayout(passive=True), _magic(passive=True), PORTS, topology)


def test_hbt_merge_rejects_an_empty_hbt_population():
    klayout = _klayout(passive=True).replace(
        b"Q1 OUT IN GND GND npn13G2 we=70n le=900n Nx=5 m=1\n", b""
    )
    magic = _magic(passive=True).replace(
        b"Q1 out_local in_local e_local GND npn13g2 we=70n le=900n Nx=5 m=1\n", b""
    )

    with pytest.raises(ValueError):
        merge_hbt_netlists(klayout, magic, PORTS, magic)


def test_topology_hbt_order_can_differ_from_final_magic_order():
    """Per-HBT endpoint checks must follow the mapping, not card position."""
    ports = ["OUT0", "IN0", "OUT1", "IN1", "GND"]
    klayout = dedent("""\
        .SUBCKT AMP OUT0 IN0 OUT1 IN1 GND
        Q1 OUT0 IN0 GND GND npn13G2 we=70n le=900n Nx=5 m=1
        Q2 OUT1 IN1 GND GND npn13G2 we=70n le=900n Nx=6 m=1
        .ENDS AMP
    """).encode()
    magic = dedent("""\
        .SUBCKT AMP OUT0 IN0 OUT1 IN1 GND
        Q1 OUT0 IN0 e0 GND npn13g2 we=70n le=900n Nx=5 m=1
        Q2 OUT1 IN1 e1 GND npn13g2 we=70n le=900n Nx=6 m=1
        .ENDS AMP
    """).encode()
    topology = dedent("""\
        .SUBCKT AMP OUT0 IN0 OUT1 IN1 GND
        Q2 OUT1 IN1 e1 GND npn13g2 we=70n le=900n Nx=6 m=1
        Q1 OUT0 IN0 e0 GND npn13g2 we=70n le=900n Nx=5 m=1
        .ENDS AMP
    """).encode()

    merged, details = merge_hbt_netlists(klayout, magic, ports, topology)

    assert details["hbt_count"] == 2
    assert "Q1 OUT0 IN0 GND GND npn13G2" in merged
    assert "Q2 OUT1 IN1 GND GND npn13G2" in merged


def test_twelve_hbts_share_one_candidate_net_without_collapsing_magic_contacts():
    """A shared KLayout net may remain many Magic contacts joined by wire R."""
    ports = [*(f"OUT{index}" for index in range(12)),
             *(f"IN{index}" for index in range(12)), "GND"]
    klayout_cards = [
        f"Q{index} OUT{index} IN{index} NINT GND npn13G2 we=70n le=900n Nx={index + 1} m=1"
        for index in range(12)
    ]
    magic_cards = list(reversed([
        f"Q{index} OUT{index} IN{index} n{index} GND npn13g2 we=70n le=900n Nx={index + 1} m=1"
        for index in range(12)
    ]))
    wires = [f"R{index} n{index} n{index + 1} 1" for index in range(11)]
    klayout = (f".SUBCKT AMP {' '.join(ports)}\n" + "\n".join(klayout_cards)
               + "\n.ENDS AMP\n").encode()
    magic_body = "\n".join([*magic_cards, *wires])
    magic = (f".SUBCKT AMP {' '.join(ports)}\n" + magic_body
             + "\n.ENDS AMP\n").encode()

    merged, details = merge_hbt_netlists(klayout, magic, ports, magic)

    assert details["hbt_count"] == 12
    assert len(details["internal_net_mapping"]["nint"]) == 12
    for index in range(12):
        assert f"Q{index} OUT{index} IN{index} n{index} GND npn13G2" in merged
    for index in range(11):
        assert f"R{index} n{index} n{index + 1} 1" in merged


def test_twelve_hbts_with_symmetric_shared_terminals_fail_closed():
    """A highly symmetric 12-HBT graph must stop at ambiguity quickly."""
    ports = ["OUT", "IN", "GND"]
    cards_k = [
        f"Q{index} OUT IN NINT GND npn13G2 we=70n le=900n Nx=5 m=1"
        for index in range(12)
    ]
    cards_m = [
        f"Q{index} OUT IN nmagic GND npn13g2 we=70n le=900n Nx=5 m=1"
        for index in range(12)
    ]
    klayout = (".SUBCKT AMP OUT IN GND\n" + "\n".join(cards_k)
               + "\n.ENDS AMP\n").encode()
    magic = (".SUBCKT AMP OUT IN GND\n" + "\n".join(cards_m)
             + "\n.ENDS AMP\n").encode()

    with pytest.raises(ValueError, match="ambiguous|complex"):
        merge_hbt_netlists(klayout, magic, ports, magic)


def test_local_rc_terminals_survive_hbt_replacement():
    """Replacing the HBT card must preserve candidate-local RC endpoints."""
    magic = _magic()[:-len(b".ENDS AMP\n")] + b"CLOCAL out_local c_local 4f\n.ENDS AMP\n"
    merged, _ = merge_hbt_netlists(_klayout(), magic, PORTS, magic)

    assert "Q1 out_local in_local e_local GND npn13G2" in merged
    assert "R1 out_local OUT 1" in merged
    assert "R2 in_local IN 2" in merged
    assert "R3 e_local GND 3" in merged
    assert "CLOCAL out_local c_local 4f" in merged


def test_capacitor_multiplicity_matches_split_magic_model_cards():
    """A native m=2 capacitor may be two Magic m=1 cards after extraction."""
    klayout = _klayout().replace(
        b".ENDS AMP\n",
        b"CDEV OUT GND cap_cmim w=2u l=3u m=2\n.ENDS AMP\n",
    )
    topology = _magic().replace(
        b".ENDS AMP\n",
        b"CDEV0 OUT GND cap_cmim w=2u l=3u\n"
        b"CDEV1 OUT GND cap_cmim w=2u l=3u\n.ENDS AMP\n",
    )
    merged, _ = merge_hbt_netlists(klayout, topology, PORTS, topology)

    assert "CDEV0 OUT GND cap_cmim w=2u l=3u" in merged
    assert "CDEV1 OUT GND cap_cmim w=2u l=3u" in merged


def test_isolated_port_repair_rejects_a_referenced_local_terminal():
    """An attached RC card prevents silently bypassing an unproven wire."""
    magic = _magic(rc=False).replace(
        b"Q1 out_local in_local e_local GND npn13g2 we=70n le=900n Nx=5 m=1\n",
        b"Q1 OUT IN e_local GND npn13g2 we=70n le=900n Nx=5 m=1\n",
    )[:-len(b".ENDS AMP\n")] + (
        b"CLOCAL e_local c_local 4f\n.ENDS AMP\n"
    )

    with pytest.raises(ValueError, match="external references"):
        merge_hbt_netlists(_klayout(), magic, PORTS, magic)


def test_final_rc_must_retain_topology_wire_for_local_port_contact():
    """A pre-RC route cannot justify a contact absent from final Magic RC."""
    topology = _magic(rc=True)
    final_magic = _magic(rc=True).replace(b"R3 e_local GND 3\n", b"")

    # The topology still proves e_local--GND through R3, but the published
    # final RC netlist no longer contains that wire.  Keeping e_local on the
    # merged HBT would leave the emitter floating, so extraction must reject
    # the mismatch rather than trusting topology evidence alone.
    with pytest.raises(ValueError, match="final RC|wire|endpoint|unconnected"):
        merge_hbt_netlists(_klayout(), final_magic, PORTS, topology)


def test_segmented_passive_port_requires_final_rc_wire():
    """A PORT.segment alias is valid only when final RC retains its wire."""
    topology = dedent("""\
        .SUBCKT AMP OUT IN GND
        Q1 OUT IN GND GND npn13g2 we=70n le=900n Nx=5 m=1
        RDEV OUT.t0 GND GND rppd w=2u l=3u ps=0u b=0 m=1
        Rwire OUT.t0 OUT 1
        .ENDS AMP
    """).encode()
    final_magic = dedent("""\
        .SUBCKT AMP OUT IN GND
        Q1 OUT IN GND GND npn13g2 we=70n le=900n Nx=5 m=1
        RDEV OUT.t0 GND GND rppd w=2u l=3u ps=0u b=0 m=1
        .ENDS AMP
    """).encode()

    # The pre-RC topology proves OUT.t0--OUT through Rwire.  The final RC
    # output drops that sole wire while retaining the model card; accepting
    # the spelling prefix alone would leave the passive disconnected.
    with pytest.raises(ValueError, match="final RC|wire|endpoint|connect"):
        merge_hbt_netlists(_klayout(passive=True), final_magic, PORTS, topology)


def test_final_only_segmented_passive_port_cannot_rely_on_prefix_alias():
    """A final-only PORT.segment must have an explicit final-RC path."""
    topology = dedent("""\
        .SUBCKT AMP OUT IN GND
        Q1 OUT IN GND GND npn13g2 we=70n le=900n Nx=5 m=1
        RDEV OUT GND GND rppd w=2u l=3u ps=0u b=0 m=1
        .ENDS AMP
    """).encode()
    final_without_wire = dedent("""\
        .SUBCKT AMP OUT IN GND
        Q1 OUT IN GND GND npn13g2 we=70n le=900n Nx=5 m=1
        RDEV OUT.t0 GND GND rppd w=2u l=3u ps=0u b=0 m=1
        .ENDS AMP
    """).encode()
    final_with_wire = final_without_wire.replace(
        b".ENDS AMP\n", b"Rwire OUT.t0 OUT 1\n.ENDS AMP\n"
    )

    # There is deliberately no pre-RC OUT.t0 component.  The segmented
    # contact is introduced by extresist in the final output, so only the
    # final graph can establish whether it still reaches OUT.
    with pytest.raises(ValueError, match="final RC|wire|endpoint|connect"):
        merge_hbt_netlists(_klayout(passive=True), final_without_wire,
                           PORTS, topology)
    merge_hbt_netlists(_klayout(passive=True), final_with_wire, PORTS, topology)


def test_shared_internal_contacts_require_final_rc_wires():
    """Shared KLayout nodes must retain each Magic contact's final wire path."""
    ports = ["OUT0", "IN0", "OUT1", "IN1", "GND"]
    klayout = dedent("""\
        .SUBCKT AMP OUT0 IN0 OUT1 IN1 GND
        Q0 OUT0 IN0 NINT GND npn13G2 we=70n le=900n Nx=5 m=1
        Q1 OUT1 IN1 NINT GND npn13G2 we=70n le=900n Nx=6 m=1
        .ENDS AMP
    """).encode()
    final_magic = dedent("""\
        .SUBCKT AMP OUT0 IN0 OUT1 IN1 GND
        Q0 OUT0 IN0 n0 GND npn13g2 we=70n le=900n Nx=5 m=1
        Q1 OUT1 IN1 n1 GND npn13g2 we=70n le=900n Nx=6 m=1
        .ENDS AMP
    """).encode()
    topology = final_magic.replace(
        b".ENDS AMP\n", b"Rwire n0 n1 1\n.ENDS AMP\n"
    )

    # Mapping is proven by the pre-RC Rwire, but the published Magic RC has
    # removed it.  The merged HBTs would otherwise retain two disconnected
    # contacts for one logical internal node.
    with pytest.raises(ValueError, match="final RC|wire|internal|connect"):
        merge_hbt_netlists(klayout, final_magic, ports, topology)


def _native_hbt(we: str) -> bytes:
    return dedent(f"""\
        .SUBCKT AMP OUT IN GND
        Q1 OUT IN GND GND npn13G2 we={we} le=900n Nx=5 m=1
        .ENDS AMP
    """).encode()


def test_fixed_geometry_accepts_equivalent_spice_units():
    converted = convert_klayout_netlist(_native_hbt("0.07u"), PORTS)

    assert "Nx=5" in converted


@pytest.mark.parametrize("we", ["71n", "1e309"])
def test_fixed_geometry_rejects_materially_wrong_or_nonfinite_values(we):
    with pytest.raises(ValueError):
        convert_klayout_netlist(_native_hbt(we), PORTS)


def _split_internal_contacts(*, local_card: str = "", anchor_card: str = "",
                             topology_reordered: bool = False) -> tuple[bytes, bytes, bytes]:
    """Build a two-HBT witness for the bounded internal-contact repair."""
    ports = "OUT0 IN0 OUT1 IN1 GND"
    klayout = dedent(f"""\
        .SUBCKT AMP {ports}
        Q0 OUT0 IN0 NINT GND npn13G2 we=70n le=900n Nx=5 m=1
        Q1 OUT1 IN1 NINT GND npn13G2 we=70n le=900n Nx=6 m=1
        RDEV NINT OUT1 GND rppd w=2u l=3u ps=0u b=0 m=1
        .ENDS AMP
    """).encode()
    cards = f"""\
        Q0 OUT0 IN0 e_local GND npn13g2 we=70n le=900n Nx=5 m=1
        Q1 OUT1 IN1 b_anchor GND npn13g2 we=70n le=900n Nx=6 m=1
        RDEV b_anchor OUT1 GND rppd w=2u l=3u ps=0u b=0 m=1
        {local_card}
        {anchor_card}
    """
    magic = dedent(f"""\
        .SUBCKT AMP {ports}
        {cards}
        .ENDS AMP
    """).encode()
    topology_cards = "\n".join([
        "Q1 OUT1 IN1 b_anchor GND npn13g2 we=70n le=900n Nx=6 m=1",
        "Q0 OUT0 IN0 e_local GND npn13g2 we=70n le=900n Nx=5 m=1",
        "RDEV b_anchor OUT1 GND rppd w=2u l=3u ps=0u b=0 m=1",
        local_card,
        anchor_card,
    ] if topology_reordered else [
        "Q0 OUT0 IN0 e_local GND npn13g2 we=70n le=900n Nx=5 m=1",
        "Q1 OUT1 IN1 b_anchor GND npn13g2 we=70n le=900n Nx=6 m=1",
        "RDEV b_anchor OUT1 GND rppd w=2u l=3u ps=0u b=0 m=1",
        local_card,
        anchor_card,
    ])
    topology = dedent(f"""\
        .SUBCKT AMP {ports}
        {topology_cards}
        .ENDS AMP
    """).encode()
    return klayout, magic, topology


def test_internal_split_contact_repairs_to_unique_anchored_magic_endpoint():
    klayout, magic, topology = _split_internal_contacts(topology_reordered=True)

    merged, details = merge_hbt_netlists(
        klayout, magic, ["OUT0", "IN0", "OUT1", "IN1", "GND"], topology
    )

    assert "Q0 OUT0 IN0 b_anchor GND npn13G2" in merged
    assert "Q1 OUT1 IN1 b_anchor GND npn13G2" in merged
    assert "RDEV b_anchor OUT1 GND rppd" in merged
    assert details["isolated_hbt_internal_repairs"] == [{
        "klayout_net": "nint",
        "isolated_local": "e_local",
        "anchored_contact": "b_anchor",
        "external_references": 0,
    }]
    assert details["synthetic_hbt_ties"] == []


@pytest.mark.parametrize("local_card, anchor_card", [
    ("CLOCAL e_local GND 1f", ""),
    ("CLOCAL e_local GND 1f", "COTHER b_anchor GND 1f"),
])
def test_internal_split_contact_requires_exactly_one_isolated_endpoint(
        local_card, anchor_card):
    klayout, magic, topology = _split_internal_contacts(
        local_card=local_card, anchor_card=anchor_card
    )

    with pytest.raises(ValueError, match="isolated|anchored|topology|mapping"):
        merge_hbt_netlists(
            klayout, magic, ["OUT0", "IN0", "OUT1", "IN1", "GND"], topology
        )


def test_internal_split_contact_rejects_topology_only_isolation():
    klayout, magic, topology = _split_internal_contacts(
        local_card="CLOCAL e_local GND 1f"
    )
    # The final output's local contact is referenced, while topology claims it
    # is isolated.  A topology-only repair would bypass that final RC card.
    final_magic = magic.replace(b"CLOCAL e_local GND 1f\n", b"")

    with pytest.raises(ValueError, match="isolated|anchored|mapping|external|terminal"):
        merge_hbt_netlists(
            klayout, final_magic, ["OUT0", "IN0", "OUT1", "IN1", "GND"], topology
        )


def test_isolated_internal_contact_can_use_a_retained_passive_anchor():
    """A unique emitter may be repaired to the matching passive endpoint."""
    klayout = dedent("""\
        .SUBCKT AMP OUT IN GND
        Q1 OUT IN NINT GND npn13G2 we=70n le=900n Nx=5 m=1
        RDEV NINT OUT GND rppd w=2u l=3u ps=0u b=0 m=1
        .ENDS AMP
    """).encode()
    magic = dedent("""\
        .SUBCKT AMP OUT IN GND
        Q1 OUT IN e_local GND npn13g2 we=70n le=900n Nx=5 m=1
        RDEV b_anchor OUT GND rppd w=2u l=3u ps=0u b=0 m=1
        .ENDS AMP
    """).encode()

    merged, details = merge_hbt_netlists(klayout, magic, PORTS, magic)

    assert "Q1 OUT IN b_anchor GND npn13G2" in merged
    assert details["isolated_hbt_internal_repairs"] == [{
        "klayout_net": "nint",
        "isolated_local": "e_local",
        "anchored_contact": "b_anchor",
        "external_references": 0,
    }]


def test_isolated_internal_contact_without_a_unique_passive_anchor_fails():
    """A floating Magic emitter cannot be repaired by net-name guessing."""
    klayout = dedent("""\
        .SUBCKT AMP OUT IN GND
        Q1 OUT IN NINT GND npn13G2 we=70n le=900n Nx=5 m=1
        RDEV NINT OUT GND rppd w=2u l=3u ps=0u b=0 m=1
        .ENDS AMP
    """).encode()
    magic = dedent("""\
        .SUBCKT AMP OUT IN GND
        Q1 OUT IN e_local GND npn13g2 we=70n le=900n Nx=5 m=1
        RDEV OUT OUT GND rppd w=2u l=3u ps=0u b=0 m=1
        .ENDS AMP
    """).encode()

    with pytest.raises(ValueError, match="anchored|passive|mapping|geometry"):
        merge_hbt_netlists(klayout, magic, PORTS, magic)


def test_internal_passive_anchor_must_exist_in_final_rc_and_topology():
    klayout = dedent("""\
        .SUBCKT AMP OUT IN GND
        Q1 OUT IN NINT GND npn13G2 we=70n le=900n Nx=5 m=1
        RDEV NINT OUT GND rppd w=2u l=3u ps=0u b=0 m=1
        .ENDS AMP
    """).encode()
    topology = dedent("""\
        .SUBCKT AMP OUT IN GND
        Q1 OUT IN e_local GND npn13g2 we=70n le=900n Nx=5 m=1
        RDEV b_anchor OUT GND rppd w=2u l=3u ps=0u b=0 m=1
        .ENDS AMP
    """).encode()
    final_magic = topology.replace(
        b"RDEV b_anchor OUT GND rppd w=2u l=3u ps=0u b=0 m=1\n",
        b"RDEV OUT OUT GND rppd w=2u l=3u ps=0u b=0 m=1\n",
    )

    with pytest.raises(ValueError, match="passive|mapping|geometry|anchored"):
        merge_hbt_netlists(klayout, final_magic, PORTS, topology)


def test_internal_passive_anchors_follow_a_nontrivial_hbt_permutation():
    """Per-device passive anchors must follow the HBT mapping permutation.

    The four HBT cards use a chain whose Magic emission order is the same
    nontrivial cycle as the reviewed LNA.  All four rsil cards have identical
    geometry, so the distinct named ports are the only contract-level anchor
    identity.  An inverted KLayout-to-Magic index map classifies the wrong
    emitter as isolated and either rejects the merge or attaches several
    passives to one logical net.
    """
    ports = ["IN", "OUT", "P0", "P1", "P2", "P3", "GND"]
    klayout = dedent("""\
        .SUBCKT AMP IN OUT P0 P1 P2 P3 GND
        Q$1 N1 N0 E1 GND npn13G2 we=70n le=900n Nx=1 m=1
        Q$2 N0 IN E0 GND npn13G2 we=70n le=900n Nx=1 m=1
        Q$3 N2 N1 E2 GND npn13G2 we=70n le=900n Nx=1 m=1
        Q$4 OUT N2 E3 GND npn13G2 we=70n le=900n Nx=1 m=1
        R$0 P0 E0 GND rsil w=4u l=20u
        R$1 P1 E1 GND rsil w=4u l=20u
        R$2 P2 E2 GND rsil w=4u l=20u
        R$3 P3 E3 GND rsil w=4u l=20u
        .ENDS AMP
    """).encode()
    magic = dedent("""\
        .SUBCKT AMP IN OUT P0 P1 P2 P3 GND
        X2 n1 n0 e1 GND npn13g2 we=70n le=900n
        X9 n2 n1 e2 GND npn13g2 we=70n le=900n
        X10 OUT n2 e3 GND npn13g2 we=70n le=900n
        X13 n0 IN e0 GND npn13g2 we=70n le=900n
        X0 P0 a0 GND rsil w=4u l=20u
        X1 P1 a1 GND rsil w=4u l=20u
        X3 P2 a2 GND rsil w=4u l=20u
        X4 P3 a3 GND rsil w=4u l=20u
        .ENDS AMP
    """).encode()

    merged, details = merge_hbt_netlists(klayout, magic, ports, magic)

    assert details["isolated_hbt_internal_repairs"] == [
        {"klayout_net": f"e{index}", "isolated_local": f"e{index}",
         "anchored_contact": f"a{index}", "external_references": 0}
        for index in range(4)
    ]
    for index in range(4):
        assert f"a{index}" in merged


def test_identical_common_body_passive_anchors_fail_without_physical_identity():
    """Repeated body-ended passives must not be assigned by shape alone.

    This mirrors the maintained LNA boundary: every ``rsil`` has the same
    geometry and its outer terminals are all VSS, while each HBT emitter has a
    distinct isolated contact.  The native netlist therefore cannot identify
    which Magic ``rsil`` contact belongs to which emitter.  A merge may pass
    only after the extractor supplies per-instance physical correspondence;
    the logical net and model/shape evidence below must remain ambiguous.
    """
    ports = ["IN", "OUT", "VSS"]
    klayout = dedent("""\
        .SUBCKT AMP IN OUT VSS
        Q$1 N1 N0 E1 VSS npn13G2 we=70n le=900n Nx=1 m=1
        Q$2 N0 IN E0 VSS npn13G2 we=70n le=900n Nx=1 m=1
        Q$3 N2 N1 E2 VSS npn13G2 we=70n le=900n Nx=1 m=1
        Q$4 OUT N2 E3 VSS npn13G2 we=70n le=900n Nx=1 m=1
        R$0 VSS E0 VSS rsil w=4u l=20u
        R$1 VSS E1 VSS rsil w=4u l=20u
        R$2 VSS E2 VSS rsil w=4u l=20u
        R$3 VSS E3 VSS rsil w=4u l=20u
        .ENDS AMP
    """).encode()
    magic = dedent("""\
        .SUBCKT AMP IN OUT VSS
        X2 n1 n0 e1 VSS npn13g2 we=70n le=900n
        X9 n2 n1 e2 VSS npn13g2 we=70n le=900n
        X10 OUT n2 e3 VSS npn13g2 we=70n le=900n
        X13 n0 IN e0 VSS npn13g2 we=70n le=900n
        X0 VSS a0 VSS rsil w=4u l=20u
        X1 VSS a1 VSS rsil w=4u l=20u
        X3 VSS a2 VSS rsil w=4u l=20u
        X4 VSS a3 VSS rsil w=4u l=20u
        .ENDS AMP
    """).encode()

    with pytest.raises(ValueError, match="unique|ambiguous|anchored|mapping|multiple"):
        merge_hbt_netlists(klayout, magic, ports, magic)
