"""Contracts for candidate-derived SG13G2 HBT extraction."""

from textwrap import dedent

import pytest

from benchmarking.eda.backends.hbt.merge import merge_hbt_netlists

pytestmark = pytest.mark.unit


def _netlist(cards, ports="OUT IN GND"):
    return (f".SUBCKT AMP {ports}\n" + "\n".join(cards) + "\n.ENDS AMP\n").encode()





def test_hbt_reads_escaped_nets_continuations_and_comments():
    from benchmarking.eda.backends.hbt.netlist import parse_spice_netlist

    raw = r'''* the extractor's comment may contain an unmatched quote: "
.SUBCKT AMP OUT IN
* port annotation
  + GND
Q$1 \$10 "IN" GND GND npn13G2
* geometry annotation
  + we=70n le=900n Nx=5 m=1 ; author's comment: "
Rwire \$10 wire# 1
.ENDS AMP

* expanding symbol: generated export
+ of pins=3
'''
    parsed = parse_spice_netlist(raw)
    assert parsed.ports == ('OUT', 'IN', 'GND')
    device = parsed.hbt_devices[0]
    assert device.nets == ('$10', 'IN', 'GND', 'GND')
    assert device.parameters == (('we', '70n'), ('le', '900n'), ('Nx', '5'), ('m', '1'))
    assert device.line.physical_lines == (4, 6)
    with pytest.raises(ValueError, match='Invalid SPICE line at 5'):
        parse_spice_netlist(raw.replace('"IN"', '"IN').replace('author\'s comment: "', 'comment'))


@pytest.mark.parametrize('reader', ['hbt', 'dspf'])
def test_netlist_readers_reject_orphan_continuations(reader):
    from benchmarking.eda.backends.hbt.netlist import parse_spice_netlist
    from benchmarking.eda.netlists.dspf import bind_extracted_netlist

    raw = '+ OUT IN GND\n.SUBCKT AMP OUT IN GND\n.ENDS AMP\n'
    with pytest.raises(ValueError, match='continuation.*line at 1'):
        if reader == 'hbt':
            parse_spice_netlist(raw)
        else:
            bind_extracted_netlist(raw, 'AMP', ['OUT', 'IN', 'GND'])


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


def test_tap_geometry_does_not_synthesize_model_resistance():
    native = _klayout()[:-len(b'.ENDS AMP\n')] + b'Rtap OUT GND ptap1 A=1p P=4u\n.ENDS AMP\n'
    magic = _magic()[:-len(b'.ENDS AMP\n')] + b'Rtap OUT GND ptap1 A=1p P=4u\n.ENDS AMP\n'
    with pytest.raises(ValueError, match='native extracted R'):
        merge_hbt_netlists(native, magic, PORTS, magic)


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

    from benchmarking.eda.backends.hbt.backend import SG13G2HBTRCDocker
    from benchmarking.eda.backends.magic import MagicRCDocker
    from benchmarking.evaluation import Job
    from benchmarking.evidence.bundles import publish_bundle
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

    monkeypatch.setattr('benchmarking.eda.backends.klayout.DockerTool', Tool)
    monkeypatch.setattr('benchmarking.eda.backends.magic.DockerTool', Tool)
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
    merged, _ = merge_hbt_netlists(_klayout(), magic, PORTS, magic)
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

    with pytest.raises(ValueError, match="candidate|topology|connected"):
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
    with pytest.raises(ValueError):
        merge_hbt_netlists(_klayout(we='71n'), _magic(), PORTS, _magic())


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


@pytest.mark.parametrize('has_wire', [False, True])
def test_split_internal_contact_requires_an_extracted_wire(has_wire):
    wire = 'Rnative e_local b_anchor 10' if has_wire else ''
    klayout, magic, topology = _split_internal_contacts(anchor_card=wire, topology_reordered=True)
    ports = ["OUT0", "IN0", "OUT1", "IN1", "GND"]
    if not has_wire:
        with pytest.raises(ValueError, match='topology|mapping|contact'):
            merge_hbt_netlists(klayout, magic, ports, topology)
    else:
        merged, _ = merge_hbt_netlists(klayout, magic, ports, topology)
        assert 'Q0 OUT0 IN0 e_local GND npn13G2' in merged
        assert 'Q1 OUT1 IN1 b_anchor GND npn13G2' in merged
        assert 'Rnative e_local b_anchor 10' in merged


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


def test_passive_anchor_does_not_reconnect_an_isolated_hbt():
    native = _klayout(passive=True).replace(b'Q1 OUT IN GND', b'Q1 OUT IN NINT').replace(
        b'RDEV OUT GND', b'RDEV NINT OUT')
    magic = _magic(passive=True, rc=False).replace(
        b'Q1 out_local in_local', b'Q1 OUT IN').replace(b'RDEV OUT GND', b'RDEV b_anchor OUT')
    with pytest.raises(ValueError):
        merge_hbt_netlists(native, magic, PORTS, magic)





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
    from benchmarking.eda.backends.hbt.netlist import parse_spice_netlist
    assert parse_spice_netlist(merged, strict_devices=False).ports == ("IN", "OUT", "GND")


@pytest.mark.parametrize("changed", [None, "candidate_sha256", "database_sha256", "top_cell"])
def test_kpex_rejects_a_database_bound_to_a_different_candidate(changed):
    """An LVS database from a different submission must not drive extraction."""
    from benchmarking.eda.backends.kpex import validate_binding
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


@pytest.mark.parametrize("terminals,width,header,expected", [
    (("A", "B", "SUB"), 0.5, "A B SUB", "passed"),
    (("B", "A", "SUB"), 0.5, "A B SUB", "passed"),
    (("B", "A", "A"), 0.5, "A B SUB", "error"),
    (("A", "A", "SUB"), 0.5, "A B SUB", "error"),
    (("B", "A", "SUB"), 0.6, "A B SUB", "error"),
    (("A", "B", "SUB"), 0.5, "A B", "interface"),
    (("A", "B", "SUB"), 0.5, "A B SUB EXTRA", "interface"),
    (("A", "B", "SUB"), 0.5, "A A B SUB", "interface"),
    (("A", "B", "SUB"), 0.5, "A B SUB SUB", "interface"),
    (("A", "B", "SUB"), 0.5, "A B SUB PLANE", "passed"),
], ids=["unchanged", "swapped-ends", "wrong-substrate", "shorted-ends", "wrong-width",
        "missing-port", "extra-port", "duplicate-port", "duplicate-substrate", "declared-plane"])
def test_kpex_uses_completed_native_lvs_after_database_reload(
        native_tmp_path, monkeypatch, terminals, width, header, expected):
    """A persisted native LVS verdict retains the device rules used to compare.

    Independent oracle: a symmetric resistor connects A and B with its bulk at
    SUB; a MIM capacitor from A to SUB distinguishes the two signal nets.
    Reversing the resistor ends preserves that circuit; changing the bulk,
    shorting A/B, or changing its geometry does not. Real KLayout comparison and database I/O
    run here; only the external geometry deck and capacitance tool are replaced.
    No process geometry or extraction-accuracy claim is made by this control.
    """
    db = pytest.importorskip("klayout.db")
    pytest.importorskip("klayout_pex")
    from types import SimpleNamespace

    from benchmarking.eda._scripts import kpex_runner as runner

    def populate(netlist, ends, device_width):
        device_class = db.DeviceClassResistor()
        device_class.name = "film"
        device_class.clear_parameters()
        device_class.clear_terminals()
        device_class.clear_equivalent_terminal_ids()
        for name in ("film_1", "film_2", "film_sub"):
            device_class.add_terminal(db.DeviceTerminalDefinition(name))
        parameters = {"w": device_width, "l": 1.0, "ps": 0.0, "b": 0.0, "m": 1.0}
        for name in parameters:
            device_class.add_parameter(db.DeviceParameterDefinition(name))
        # The fixture declares its device semantics before native LVS, just as
        # a PDK deck does. The runner must consume that completed comparison.
        device_class.equivalent_terminal_id(1, 0)
        netlist.add(device_class)
        circuit = db.Circuit()
        circuit.name = "DUT"
        netlist.add(circuit)
        nets = {name: circuit.create_net(name) for name in ("A", "B", "SUB")}
        for name, net in nets.items():
            circuit.connect_pin(circuit.create_pin(name), net)
        device = circuit.create_device(device_class, "R1")
        for index, name in enumerate(ends):
            device.connect_terminal(index, nets[name])
        for name, value in parameters.items():
            device.set_parameter(name, value)
        anchor_class = db.DeviceClassCapacitor()
        anchor_class.name = "plate"
        anchor_class.clear_parameters()
        anchor_class.clear_terminals()
        anchor_class.clear_equivalent_terminal_ids()
        for name in ("upper", "lower"):
            anchor_class.add_terminal(db.DeviceTerminalDefinition(name))
        for name in ("w", "l", "m"):
            anchor_class.add_parameter(db.DeviceParameterDefinition(name))
        netlist.add(anchor_class)
        anchor = circuit.create_device(anchor_class, "C1")
        anchor.connect_terminal(0, nets["A"])
        anchor.connect_terminal(1, nets["SUB"])
        for name, value in {"w": 2.0, "l": 3.0, "m": 1.0}.items():
            anchor.set_parameter(name, value)

    def write_database(path, ends, device_width):
        report = db.LayoutVsSchematic("DUT", 0.001)
        report.extract_netlist()
        populate(report.netlist(), ends, device_width)
        reference = db.Netlist()
        populate(reference, ("A", "B", "SUB"), 0.5)
        report.reference = reference
        report.compare(db.NetlistComparer())
        report.write(str(path))

    write_database(native_tmp_path / "candidate.lvsdb", ("A", "B", "SUB"), 0.5)
    geometry = native_tmp_path / "geometry-source.lvsdb"
    write_database(geometry, terminals, width)

    def run_geometry(*args, **kwargs):
        (native_tmp_path / "geometry.lvsdb").write_bytes(geometry.read_bytes())

    def run_capacitance(*args, **kwargs):
        (native_tmp_path / "extracted.spice").write_text(
            f".SUBCKT DUT {header}\nXphysical_1 B A SUB film w=0.5u l=1u m=1\n"
            "Xphysical_2 A SUB plate w=2u l=3u m=1\n.ENDS DUT\n")

    monkeypatch.chdir(native_tmp_path)
    monkeypatch.setattr(runner.subprocess, "run", run_geometry)
    monkeypatch.setattr(runner, "KpexCLI", lambda: SimpleNamespace(main=run_capacitance))
    monkeypatch.setattr(runner.NetlistPrinter, "write_device", runner.NetlistPrinter.write_device)
    process = {"pdk": "synthetic", "deck": "synthetic.lvs", "variables": {},
               "substrate_node": "PLANE", "devices": {
                   "film": {"terminals": ["film_1", "film_2", "film_sub"],
                            "parameters": {"w": "u", "l": "u", "m": ""}, "reference_prefix": "R"},
                   "plate": {"terminals": ["upper", "lower"],
                             "parameters": {"w": "u", "l": "u", "m": ""}, "reference_prefix": "C"}}}
    from benchmarking.eda.backends.kpex import validate_process
    validate_process(process)
    config = {"top_cell": "DUT", "ports": ["A", "B", "SUB"], "substrate": "SUB", "process": process}
    if expected in {"error", "interface"}:
        message = "KPEX geometry extraction differs" if expected == "error" else "output interface differs"
        with pytest.raises(ValueError, match=message):
            runner.extract(config)
    else:
        details = runner.extract(config)
        assert details["physical_devices"] == {"film": 1, "plate": 1}
        assert ".SUBCKT DUT A B SUB" in (native_tmp_path / "extracted.spice").read_text()

@pytest.mark.parametrize('terminal', ['e_local', 'out_local', 'in_local'])
def test_isolated_port_contact_is_never_reconnected(terminal):
    magic = _magic()
    wire = {'e_local': b'R3 e_local GND 3\n',
            'out_local': b'R1 out_local OUT 1\n',
            'in_local': b'R2 in_local IN 2\n'}[terminal]
    disconnected = magic.replace(wire, b'')
    with pytest.raises(ValueError):
        merge_hbt_netlists(_klayout(), disconnected, PORTS, disconnected)
