"""Contracts for candidate-derived SG13G2 HBT extraction."""

from textwrap import dedent

import pytest

from benchmarking.engine.hbt import convert_klayout_netlist, merge_hbt_netlists

pytestmark = pytest.mark.unit


def _netlist(cards, ports="OUT IN GND"):
    return (f".SUBCKT AMP {ports}\n" + "\n".join(cards) + "\n.ENDS AMP\n").encode()


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


def test_tap_area_and_perimeter_are_mapped_to_model_resistance():
    model = "ptap1"
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


@pytest.mark.parametrize('variant,expected', [
    ('verified_hbt', 'passed'),
    ('plain_magic', 'error'),
    ('wrong_coordinate', 'error'),
    ('lost_wire', 'error'),
])
def test_hbt_terminal_diagnostics_require_native_provenance_and_complete_mapping(
        tmp_path, monkeypatch, variant, expected):
    """Reproduce the Magic-to-HBT adapter regression at the real call boundary.

    One candidate-derived HBT and three explicit terminal wires suffice. The
    native .ext record uses Magic's msubckt terminal order (bulk, gate, source,
    drain); its diagnostic is from the same device coordinate and gate net.
    Only external EDA execution is replaced. Both adapters and the full graph
    merger run, so accepting the log alone cannot satisfy this regression.
    Real geometry/model coverage belongs to the four published HBT witnesses.
    """
    import json
    from types import SimpleNamespace

    from benchmarking.bundles import publish_bundle
    from benchmarking.engine.hbt import SG13G2HBTRCDocker
    from benchmarking.engine.magic import MagicRCDocker
    from benchmarking.evaluation import Job
    from benchmarking.files import Asset

    native = b'''.SUBCKT AMP OUT IN GND
Q1 OUT IN GND GND npn13G2 we=70n le=900n Nx=5 m=1
.ENDS AMP
'''
    topology = b'''.SUBCKT AMP OUT IN GND
X1 out_local in_local e_local GND npn13g2 le=70n we=0.9u
R1 out_local OUT 1
R2 in_local IN 2
R3 e_local GND 3
.ENDS AMP
'''
    final = topology.replace(b'R2 in_local IN 2\n', b'') if variant == 'lost_wire' else topology
    device = ('device msubckt npn13g2 10 20 11 21 w1=180 l1=14 '
              '"GND" "in_local" 0 0 "e_local" 0 2520,388 "out_local" 0 0\n')
    log = 'Missing gate connection of device at (10 20) on net in_local\n'
    if variant == 'wrong_coordinate':
        log = log.replace('(10 20)', '(11 20)')

    class Tool:
        def __init__(self, image, version_command, timeout):
            self.identity = {'tool_version': '8.3.678'}

        def run(self, command, inputs, outputs):
            if command == ['python', 'run.py']:
                files = {'result.json': Asset(b'{"status":"passed"}', 'json'),
                         'extracted.spice': Asset(native, 'spice')}
                return SimpleNamespace(reason='', returncode=0, files=files, evidence={})
            if command == ['python', 'magic_ports.py']:
                return SimpleNamespace(reason='', returncode=0, evidence={}, files={
                    'extraction.gds': inputs['candidate.gds'],
                    'preparation-check.json': Asset(b'{}', 'json')})
            assert command == ['python', 'magic_netlist.py']
            files = {'extracted.spice': Asset(final, 'spice'),
                     'topology.spice': Asset(topology, 'spice'),
                     'extraction.ext': Asset(device.encode(), 'magic-ext')}
            return SimpleNamespace(reason='', returncode=0,
                                   files=files, evidence={'console': Asset(log.encode(), 'text')})

    monkeypatch.setattr('benchmarking.engine.klayout.DockerTool', Tool)
    monkeypatch.setattr('benchmarking.engine.magic.DockerTool', Tool)
    publish_bundle({'rules.lvs': Asset(b'# test', 'text'),
                    'profile.json': Asset(b'{"deck":"rules.lvs","variables":{},"scope":"test candidate extraction"}', 'json')},
                   {}, tmp_path / 'klayout')
    publish_bundle({'sg13g2.tech': Asset(b'# test', 'text')}, {}, tmp_path / 'magic')
    settings = {'image': 'test', 'technology': 'sg13g2.tech', 'tech_name': 'sg13g2', 'style': 'ngspice()'}
    if variant == 'plain_magic':
        backend = MagicRCDocker(**settings, support=str(tmp_path / 'magic'))
    else:
        backend = SG13G2HBTRCDocker(**settings, magic_support=str(tmp_path / 'magic'),
                                   klayout_support=str(tmp_path / 'klayout'), klayout_profile='profile.json')
    job = Job('pex', 'extract', 'layout.extract', (), (('netlist', 'spice'),), (), None,
              json.dumps({'ports': ['OUT', 'IN', 'GND'], 'top_cell': 'AMP'}))
    result = backend.run(job, {'layout': Asset(b'candidate at external tool boundary', 'gds')})
    assert result.status == expected, result.reason
    if expected == 'passed':
        merged = result.outputs['netlist'].content
        assert b'R2 in_local IN 2' in merged  # Keep the proven base wire, not an ideal shortcut.
        assert b'Nx=5' in merged
        assert result.evidence['magic:console'].content == log.encode()
        assert result.evidence['mapping'].content
        review = json.loads(result.evidence['magic:terminal_diagnostic_review'].content)
        assert review['diagnostics'][0]['diagnostic'] == log.strip()
    else:
        assert not result.outputs
        if variant == 'lost_wire':
            assert 'Unsafe HBT extractor mapping' in result.reason


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
    "R_BAD OUT IN unknown_model",
    ".include unreviewed.spice",
])
def test_magic_unknown_cards_are_rejected(card):
    magic = _magic().replace(b".ENDS AMP\n", f"{card}\n.ENDS AMP\n".encode())

    with pytest.raises(ValueError):
        merge_hbt_netlists(_klayout(), magic, PORTS, _magic())


def test_missing_magic_topology_evidence_is_rejected():
    with pytest.raises(ValueError):
        merge_hbt_netlists(_klayout(), _magic(), PORTS)


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


def test_local_rc_terminals_survive_hbt_replacement():
    """Replacing the HBT card must preserve candidate-local RC endpoints."""
    magic = _magic().replace(b"we=70n le=900n", b"le=70n we=0.9u")
    magic = magic[:-len(b".ENDS AMP\n")] + b"CLOCAL out_local c_local 4f\n.ENDS AMP\n"
    merged, details = merge_hbt_netlists(_klayout(), magic, PORTS, magic)
    assert details["synthetic_hbt_ties"] == []
    assert "Q1 OUT IN GND GND" not in merged

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


def test_fixed_geometry_rejects_wrong_emitter_width():
    we = "71n"
    with pytest.raises(ValueError):
        convert_klayout_netlist(_klayout(we=we), PORTS)


def _split_internal_contacts(*, local_card="", anchor_card="", topology_reordered=False):
    """Two HBTs share one native node but have separate Magic contacts."""
    ports = "OUT0 IN0 OUT1 IN1 GND"
    native = [
        "Q0 OUT0 IN0 NINT GND npn13G2 we=70n le=900n Nx=5 m=1",
        "Q1 OUT1 IN1 NINT GND npn13G2 we=70n le=900n Nx=6 m=1",
        "RDEV NINT OUT1 GND rppd w=2u l=3u ps=0u b=0 m=1",
    ]
    cards = [
        "Q0 OUT0 IN0 e_local GND npn13g2 we=70n le=900n Nx=5 m=1",
        "Q1 OUT1 IN1 b_anchor GND npn13g2 we=70n le=900n Nx=6 m=1",
        "RDEV b_anchor OUT1 GND rppd w=2u l=3u ps=0u b=0 m=1",
        local_card, anchor_card,
    ]
    magic = _netlist(cards, ports)
    if topology_reordered:
        cards[:2] = reversed(cards[:2])
    return _netlist(native, ports), magic, _netlist(cards, ports)


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


def test_internal_split_contact_requires_exactly_one_isolated_endpoint():
    local_card = "CLOCAL e_local GND 1f"
    anchor_card = ""
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


@pytest.mark.parametrize("anchor", ["retained", "absent", "topology-only"])
def test_isolated_internal_contact_requires_a_passive_anchor_in_both_extractions(anchor):
    native = _klayout(passive=True).replace(b"Q1 OUT IN GND", b"Q1 OUT IN NINT").replace(
        b"RDEV OUT GND", b"RDEV NINT OUT")
    topology = _magic(passive=True, rc=False).replace(
        b"Q1 out_local in_local", b"Q1 OUT IN").replace(b"RDEV OUT GND", b"RDEV b_anchor OUT")
    final = topology
    if anchor != "retained":
        final = final.replace(b"RDEV b_anchor OUT", b"RDEV OUT OUT")
        if anchor == "absent":
            topology = final
        with pytest.raises(ValueError, match="passive|mapping|geometry|anchored"):
            merge_hbt_netlists(native, final, PORTS, topology)
    else:
        merged, details = merge_hbt_netlists(native, final, PORTS, topology)
        assert "Q1 OUT IN b_anchor GND npn13G2" in merged
        assert details["isolated_hbt_internal_repairs"] == [{
            "klayout_net": "nint", "isolated_local": "e_local",
            "anchored_contact": "b_anchor", "external_references": 0,
        }]


@pytest.mark.parametrize("distinct_anchors", [True, False], ids=["named-ports", "ambiguous-body"])
def test_passive_anchor_identity_follows_the_hbt_permutation(distinct_anchors):
    """Same-size passives need independent terminal identity, not shape guessing.

    The nontrivial four-HBT emission permutation follows the reviewed LNA.
    Named outer ports prove correspondence; a shared body port cannot.
    """
    anchors = [f"P{i}" for i in range(4)] if distinct_anchors else ["VSS"] * 4
    body = "GND" if distinct_anchors else "VSS"
    ports = " ".join(dict.fromkeys(["IN", "OUT", *anchors, body]))
    native = [
        "Q$1 N1 N0 E1 GND npn13G2 we=70n le=900n Nx=1 m=1",
        "Q$2 N0 IN E0 GND npn13G2 we=70n le=900n Nx=1 m=1",
        "Q$3 N2 N1 E2 GND npn13G2 we=70n le=900n Nx=1 m=1",
        "Q$4 OUT N2 E3 GND npn13G2 we=70n le=900n Nx=1 m=1",
        *(f"R${i} {port} E{i} GND rsil w=4u l=20u" for i, port in enumerate(anchors)),
    ]
    magic = [
        "X2 n1 n0 e1 GND npn13g2 we=70n le=900n",
        "X9 n2 n1 e2 GND npn13g2 we=70n le=900n",
        "X10 OUT n2 e3 GND npn13g2 we=70n le=900n",
        "X13 n0 IN e0 GND npn13g2 we=70n le=900n",
        *(f"X{j} {port} a{i} GND rsil w=4u l=20u" for i, (j, port) in enumerate(zip((0, 1, 3, 4), anchors))),
    ]
    native = _netlist([card.replace("GND", body) for card in native], ports)
    magic = _netlist([card.replace("GND", body) for card in magic], ports)
    if not distinct_anchors:
        with pytest.raises(ValueError, match="unique|ambiguous|anchored|mapping|multiple"):
            merge_hbt_netlists(native, magic, ["IN", "OUT", "VSS"], magic)
    else:
        merged, details = merge_hbt_netlists(native, magic, ports.split(), magic)
        assert details["isolated_hbt_internal_repairs"] == [
            {"klayout_net": f"e{i}", "isolated_local": f"e{i}",
             "anchored_contact": f"a{i}", "external_references": 0} for i in range(4)
        ]
        assert all(f"a{i}" in merged for i in range(4))


def test_named_resistor_tails_disambiguate_identical_hbt_branches():
    """PAM4-style parallel branches differ by physical resistor tail ports."""
    ports = ["OUT", "IN", "TAIL0", "TAIL1", "GND"]
    native = _netlist([
        "Q1 OUT IN E0 GND npn13G2 we=70n le=900n Nx=3 m=1",
        "Q2 OUT IN E1 GND npn13G2 we=70n le=900n Nx=4 m=1",
        "R1 E0 TAIL0 GND rsil w=5u l=0.5u ps=0u b=0 m=1",
        "R2 E1 TAIL1 GND rsil w=5u l=0.5u ps=0u b=0 m=1",
    ], " ".join(ports))
    topology = _netlist([
        "X8 OUT IN b GND npn13g2 we=70n le=0.9u",
        "X3 OUT IN a GND npn13g2 we=70n le=0.9u",
        "X2 TAIL0 a GND rsil l=0.5u w=5u",
        "X1 TAIL1 b GND rsil l=0.5u w=5u",
    ], " ".join(ports))
    merged, _ = merge_hbt_netlists(native, topology, ports, topology)
    assert "X8 OUT IN b GND npn13G2" in merged
    cards = {line.split()[0]: line for line in merged.splitlines() if line.startswith("X")}
    assert "Nx=4" in cards["X8"]
    assert "Nx=3" in cards["X3"]
    wrong = topology.replace(b"TAIL1 b", b"TAIL0 b")
    with pytest.raises(ValueError):
        merge_hbt_netlists(native, wrong, ports, wrong)


def test_merged_interface_consumes_wrapped_subcircuit_header():
    native = b".subckt AMP OUT IN GND\nQ1 OUT IN GND GND npn13G2 Nx=3\n.ends AMP\n"
    magic = b".subckt AMP OUT\n+ IN GND\nX1 OUT IN GND GND npn13g2\n.ends AMP\n"
    merged, _ = merge_hbt_netlists(native, magic, ["IN", "OUT", "GND"], magic)
    from benchmarking.engine.hbt import parse_spice_netlist
    assert parse_spice_netlist(merged, strict_devices=False).ports == ("IN", "OUT", "GND")


@pytest.mark.parametrize("changed", [None, "candidate_sha256", "database_sha256", "top_cell"])
def test_kpex_rejects_a_database_bound_to_a_different_candidate(changed):
    """An LVS database from a different submission must not drive extraction."""
    from benchmarking.engine.kpex import validate_binding
    from benchmarking.files import Asset

    layout = Asset(b"candidate snapshot", "gds")
    database = Asset(b"native LVS snapshot", "klayout-lvs")
    binding = {"candidate_sha256": layout.sha256, "database_sha256": database.sha256,
               "top_cell": "DUT", "layers": {}}
    if changed:
        binding[changed] = "different"
        with pytest.raises(ValueError, match="not bound"):
            validate_binding(layout, database, binding, "DUT")
    else:
        validate_binding(layout, database, binding, "DUT")
