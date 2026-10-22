"""Reject incomplete native evidence and retain three-terminal extracted RC."""

import sys
from types import SimpleNamespace

import pytest

from benchmarking.eda.backends.synopsys import (
    HspiceNative,
    _native_version,
    hspice_measures,
    icv_drc_summary,
    icv_lvs_summary,
    starrc_netlist,
)
from benchmarking.eda.environment import ExternalRuntime
from benchmarking.execution.tools.native import NativeTool
from benchmarking.files import Asset

pytestmark = pytest.mark.unit





def test_icv_drc_requires_declared_top_completion_and_rule_coverage():
    report = '''Top cell name: TOP
17 total rules were run.
There are 0 total violations.
R7 v = Not Executed
IC Validator is done.
'''
    assert icv_drc_summary(report, 'TOP', ['R7']) == 0
    assert icv_drc_summary(report.replace('0 total violations', '4 total violations'), 'TOP', ['R7']) == 4
    for bad in (report + report, report.replace('TOP', 'OTHER'), report.replace('17 total', '0 total'),
                report.replace('IC Validator is done.', ''), report.replace('R7', 'R8')):
        with pytest.raises(ValueError):
            icv_drc_summary(bad, 'TOP', ['R7'])


def test_icv_lvs_rejects_unchecked_device_properties():
    report = '''Final comparison result:PASS
TOP equivalence point: [top, TOP]
check_property = 2 device_name
recognize_gate = 0 device_name
'''
    checks = {'check_property': 2, 'recognize_gate': 0}
    assert icv_lvs_summary(report, 'top', checks)
    assert not icv_lvs_summary(report.replace('PASS', 'FAIL'), 'top', checks)
    assert icv_lvs_summary(report.replace('2 device_name', '3 device_names'), 'top',
                           {'check_property': 3, 'recognize_gate': 0})
    for bad in (report + report, report.replace('2 device_name', '0 device_name'),
                report.replace('0 device_name', '2 device_name'), report.replace('[top, TOP]', '[other, TOP]')):
        with pytest.raises(ValueError):
            icv_lvs_summary(bad, 'top', checks)


def test_starrc_preserves_native_models_and_rejects_missing_supply_ports():
    extracted = '''*|DSPF 1.3
.SUBCKT TOP OUT IN VDD! GND!
Rwire IN NGATE 1000
Cwire NGATE GND! 1e-15
Ccouple NGATE OUT 2e-15
M1 OUT NGATE GND! nmos W=21n L=15n nfin=1
+ ADEJ=2e-16 ASEJ=3e-16 PDEJ=62n PSEJ=72n
M2 OUT NGATE VDD! pmos W=21n L=15n nfin=1 ADEJ=4e-16 ASEJ=5e-16 PDEJ=62n PSEJ=72n
.ENDS TOP
'''
    ports = ['IN', 'OUT', 'VDD!', 'GND!']
    bound = starrc_netlist(extracted, 'TOP', ports)
    assert '.SUBCKT TOP IN OUT VDD! GND!' in bound
    assert 'M1 OUT NGATE GND! nmos' in bound
    assert '+ ADEJ=2e-16 ASEJ=3e-16' in bound
    assert 'Ccouple NGATE OUT 2e-15' in bound
    for bad in (extracted.replace('TOP OUT IN VDD! GND!', 'TOP OUT IN'),
                extracted.replace('TOP OUT IN VDD! GND!', 'TOP OUT IN VDD! GND! 7'),
                extracted.replace('1000', '0'), extracted.replace('ASEJ=3e-16', ''),
                extracted.replace('W=21n', 'W=nan'), extracted + extracted):
        with pytest.raises(ValueError):
            starrc_netlist(bad, 'TOP', ports)


def test_hspice_completion_finite_scalars_and_atto_units():
    listing = 'delay= 5.25p targ= 1n trig= 1n\nenergy= 32a\n***** job concluded\n'
    result = hspice_measures(listing, {'delay': 's', 'energy': 'J'})
    assert result['delay'].value == pytest.approx(5.25e-12)
    assert result['energy'].value == pytest.approx(32e-18)
    for bad in (listing.replace('job concluded', ''), listing + listing,
                listing.replace('5.25p', 'nan'), listing + '**error** no convergence\n'):
        with pytest.raises(ValueError):
            hspice_measures(bad, {'delay': 's'})
    with pytest.raises(ValueError, match='required event measurement failed'):
        hspice_measures(listing.replace('5.25p', 'failed'), {'delay': 's'})


@pytest.mark.parametrize('sections,statement', [([], '.include "/models/tt.pm"'),
                                               (['TT'], '.lib "/models/tt.pm" TT')])
def test_hspice_model_cards_and_library_sections(monkeypatch, sections, statement):
    class Tool:
        def __init__(self, *args, **kwargs):
            pass

        def probe(self, command, **kwargs):
            return SimpleNamespace(returncode=0, stdout=b'HSPICE Version test', stderr=None)

        def run(self, command, files, exports, **kwargs):
            deck = files['deck.spice'].content.decode()
            assert statement in deck and '* ICLAYOUT_MODELS' not in deck
            assert files['dut.spice'].content == b'.subckt inv a y\n.ends\n'
            return SimpleNamespace(returncode=0, reason='', evidence={},
                                   files={'result.lis': Asset(b'delay= 5p\n***** job concluded\n', 'text')})

    monkeypatch.setattr('benchmarking.eda.backends.synopsys.NativeTool', Tool)
    runtime = SimpleNamespace(pdk_file=lambda name: (None, '/models/tt.pm'),
                              module_command=lambda module, command: command)
    backend = HspiceNative(runtime=runtime, model='tt.pm', sections=sections)
    job = SimpleNamespace(stage='simulate', outputs={}, parameters={'measurements': {'delay': 's'}})
    result = backend.run(job, {'deck': Asset(b'* ICLAYOUT_MODELS\n.include "dut.spice"\n.end\n', 'spice'),
                               'dut': Asset(b'.subckt inv a y\n.ends\n', 'spice')})
    assert result.status == 'passed'
    assert result.measurements['delay'].value == pytest.approx(5e-12)
    with pytest.raises(ValueError, match='model sections'):
        HspiceNative(runtime=runtime, model='tt.pm', sections=['TT\n.end'])


def test_native_frozen_bytes_license_redaction_and_timeout(monkeypatch):
    monkeypatch.setenv('ICLAYOUT_TEST_LICENSE', 'private-test-setting')
    runtime = ExternalRuntime('test', {'image': 'unused', 'environment': {}, 'mounts': [],
                                      'pass_environment': ['ICLAYOUT_TEST_LICENSE']})
    tool = NativeTool(runtime, timeout_seconds=1, failure_label='test')
    assert len(tool.identity['native_launcher_sha256']) == 64
    frozen = Asset(b'frozen\x00binary', 'gds')
    result = tool.run([sys.executable, '-c',
        ('import os,pathlib; pathlib.Path("out.gds").write_bytes(pathlib.Path("in.gds").read_bytes()); '
         'print(os.environ["ICLAYOUT_TEST_LICENSE"]); raise SystemExit(3)')],
        {'in.gds': frozen}, {'out.gds': 'gds'})
    assert result.returncode == 3 and result.files['out.gds'] == frozen
    assert b'private-test-setting' not in result.evidence['console'].content
    assert b'<operator-license-setting>' in result.evidence['console'].content
    tool.timeout_seconds = .1
    result = tool.run([sys.executable, '-c', 'import time; time.sleep(2)'], {}, {'missing': 'text'})
    assert result.returncode is None and 'time limit' in result.reason and not result.files
    result = tool.run([sys.executable, '-c', 'raise SystemExit(4)'], {}, {'missing': 'text'})
    assert result.returncode == 4 and 'exited with 4' in result.reason
    assert 'missing:missing' in result.evidence


def test_native_process_controls_are_frozen_and_cannot_shadow_job_inputs():
    control = '// Process interface\ninline subckt native (D G S B)\nends native\n'
    runtime = ExternalRuntime('test', {'image': 'unused', 'environment': {}, 'mounts': [],
        'control_files': {'models.scs': control}})
    tool = NativeTool(runtime, timeout_seconds=10)
    path = runtime.control_path('@models.scs')
    result = tool.run([sys.executable, '-c',
        f'from pathlib import Path; Path("copy.scs").write_bytes(Path({path!r}).read_bytes())'],
        {}, {'copy.scs': 'text'},
        file_rewriter=lambda name, content, root: content.replace(b'Process', b'corrupted'))
    assert result.returncode == 0 and result.files['copy.scs'].content == control.encode()
    with pytest.raises(ValueError, match='collide'):
        tool.run([], {path: Asset(b'candidate override', 'text')}, {})
    with pytest.raises(ValueError, match='Unknown native'):
        runtime.control_path('@missing.scs')
    runtime.control_files['models.scs'] = 'changed process interface'
    with pytest.raises(ValueError, match='changed since preparation'):
        tool.run([], {}, {})
    with pytest.raises(ValueError):
        ExternalRuntime('test', {'image': 'unused', 'environment': {}, 'mounts': [],
            'control_files': {'../outside.scs': control}})


def test_native_version_parser_keeps_backend_module_and_accepted_exit_codes():
    commands = []

    class Probe:
        def probe(self, command):
            commands.append(command)
            return SimpleNamespace(returncode=1, stdout=b'vendor banner\nVersion R-2026.1 for linux64\n')

    runtime = SimpleNamespace(module_command=lambda module, command: ['load', module, *command])
    probe = Probe()
    version = _native_version(probe, runtime, 'icv', ['icv', '-V'],
                              r'Version (\S+) for linux64', returncodes=(0, 1))
    assert version == ['R-2026.1']
    assert commands == [['load', 'icv', 'icv', '-V']]
    with pytest.raises(ValueError, match='release identity'):
        _native_version(probe, runtime, 'icv', ['icv', '-V'], r'Version (\S+) for linux64')

def test_icv_passes_source_and_native_rules_without_process_rewrites(monkeypatch, tmp_path):
    from benchmarking.eda.backends.synopsys import ICVNative

    deck = tmp_path / 'native.rules'
    rules = 'native process comparison and reduction rules\n'
    deck.write_text(rules)
    captured = {}
    class Tool:
        def __init__(self, *_args, **_kwargs):
            pass
        def probe(self, *_args, **_kwargs):
            return SimpleNamespace(returncode=0, stdout=b'Version test for linux64')
        def run(self, command, files, exports, **kwargs):
            captured.update(files)
            report = b'Final comparison result:PASS\nTOP equivalence point: [TOP, TOP]\ncheck_property = 2 device_name\nrecognize_gate = 0 device_name\n'
            return SimpleNamespace(reason='', returncode=0, evidence={},
                                   files={'TOP.LVS_ERRORS': Asset(report, 'text')})
    monkeypatch.setattr('benchmarking.eda.backends.synopsys.NativeTool', Tool)
    runtime = SimpleNamespace(pdk_file=lambda _: (deck, str(deck)),
                              module_command=lambda _module, command: command)
    backend = ICVNative(runtime=runtime, check='lvs', deck='native.rules',
                        lvs_checks={'check_property': 2, 'recognize_gate': 0})
    source = Asset(b'.subckt TOP D G S\nM0 D G S nfet w=21n l=15n nfin=1 m=3\n.ends TOP\n', 'spice')
    job = SimpleNamespace(stage='check', parameters={})
    result = backend.run(job, {'layout': Asset(b'frozen', 'gds'), 'netlist': source,
                              'task': Asset(b'{"output":{"top_cell":"TOP"},"netlist_subcircuit":"TOP"}', 'json')})
    assert result.status == 'passed'
    assert captured['source.spice'] == source
    assert captured['control.rs'].content == rules.encode()
