"""Contracts for candidate-derived SG13G2 HBT extraction."""

import pytest

from layout_eval.hbt import convert_klayout_netlist, merge_hbt_netlists

pytestmark = pytest.mark.unit


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


@pytest.mark.parametrize('variant,expected', [
    ('verified_hbt', 'passed'),
    ('plain_magic', 'error'),
    ('wrong_coordinate', 'error'),
    ('wrong_net', 'error'),
    ('mos_device', 'error'),
    ('duplicate_device', 'error'),
    ('missing_device_evidence', 'error'),
    ('lost_wire', 'error'),
    ('orphaned_node', 'error'),
    ('unknown_terminal', 'error'),
    ('other_error', 'error'),
    ('tool_failure', 'error'),
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
    from benchmarking.evaluation import Job
    from benchmarking.files import Asset
    from layout_eval.hbt import SG13G2HBTRCDocker
    from layout_eval.magic import MagicRCDocker

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
    if variant == 'wrong_net':
        log = log.replace('in_local', 'unrelated')
    if variant == 'mos_device':
        device = device.replace('npn13g2', 'sg13_lv_nmos')
    if variant == 'duplicate_device':
        device *= 2
    if variant == 'orphaned_node':
        log += 'Warning: Orphaned node "other" arbitrarily attached to "other.t1"\n'
    if variant == 'unknown_terminal':
        log = log.replace('Missing gate', 'Missing terminal')
    if variant == 'other_error':
        log += 'EXTRACTION_ERROR: failed to complete another network\n'

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
            if variant == 'missing_device_evidence':
                files.pop('extraction.ext')
            return SimpleNamespace(reason='', returncode=1 if variant == 'tool_failure' else 0,
                                   files=files, evidence={'console': Asset(log.encode(), 'text')})

    monkeypatch.setattr('layout_eval.klayout.DockerTool', Tool)
    monkeypatch.setattr('layout_eval.magic.DockerTool', Tool)
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
