"""Calibre/Quantus extraction preserves physical inputs and rejects bad evidence."""

import json
from types import SimpleNamespace

import pytest

from benchmarking.engine.backends.calibre_quantus import CalibreQuantusNative
from benchmarking.engine.external import ExternalRuntime
from benchmarking.engine.netlists.dspf import adapt_dspf
from benchmarking.engine.tools.native import NativeTool
from benchmarking.engine.tools.types import ToolResult
from benchmarking.evaluation import Job
from benchmarking.files import Asset

pytestmark = pytest.mark.unit


def native_probe(self, command, **kwargs):
    output = (b'Version: test\nBuild Ref. No.: 12\nBuild Date: fixed\n'
              if command[0] == 'quantus' else b'Calibre native release\n')
    return SimpleNamespace(returncode=0, stdout=output)


@pytest.mark.parametrize('failure', ['', 'lvs', 'junctions', 'completion', 'exit'])
@pytest.mark.parametrize('within_pdk', [False, True])
def test_cci_rc_requires_complete_physical_evidence(native_tmp_path, monkeypatch, failure, within_pdk):
    pdk = native_tmp_path / 'pdk'
    technology = (pdk if within_pdk else native_tmp_path) / 'technology'
    pdk.mkdir()
    technology.mkdir()
    (pdk / 'lvs.rules').write_text('LAYOUT PRIMARY "old"\nSOURCE PRIMARY "old"\n')
    (technology / 'qrcTechFile').write_text('declared technology identity')
    mounts = [{'source': str(pdk), 'target': str(pdk), 'release': 'test',
               'identity_paths': ['lvs.rules', 'technology'] if within_pdk else ['lvs.rules']}]
    if not within_pdk:
        mounts.append({'source': str(technology), 'target': str(technology), 'release': 'test',
                       'identity_paths': ['qrcTechFile']})
    runtime = ExternalRuntime('licensed-test', {
        'image': 'unused',
        'environment': {'PDK_ROOT': str(pdk),
                        'QRC_ROOT': str(pdk / 'technology') if within_pdk else str(technology)},
        'mounts': mounts})
    monkeypatch.setattr(NativeTool, 'probe', native_probe)
    backend = CalibreQuantusNative(runtime=runtime, deck='lvs.rules', technology_env='QRC_ROOT',
                                  ground='GND', resistor_models={'poly': {'type': 'primitive', 'model': 'poly'}})
    report = '''OVERALL COMPARISON RESULTS
CELL SUMMARY
**********
 CORRECT TOP TOP
**********
 LVS IGNORE PORTS NO
 LVS CHECK PORT NAMES YES
Total Elapsed Time: 3 sec
'''
    circuit = '''.subckt TOP OUT GND IN
Rwire IN OUT 1000 TC1=0.001
Cwire OUT GND 1e-9
Rpoly IN OUT poly L=2e-6 W=1e-6 m=2
M0 OUT IN GND GND nmodel L=2e-6 W=3e-6 AS=1e-12 AD=2e-12 PS=3e-6 PD=4e-6
.ends TOP
'''
    if failure == 'lvs':
        report = report.replace('CORRECT', 'INCORRECT')
    if failure == 'junctions':
        circuit = circuit.replace(' AS=1e-12', '')
    captured = {}

    def execute(command, files, exports, **kwargs):
        captured.update(files)
        evidence = {'lvs.report': Asset(report.encode(), 'text'),
                    'qrc.log': Asset(b'Quantus terminated normally' if failure != 'completion' else b'aborted', 'text'),
                    'extracted.dspf': Asset(circuit.encode(), 'spice')}
        return ToolResult(1 if failure == 'exit' else 0, '', evidence, {})

    monkeypatch.setattr(backend.tool, 'run', execute)
    job = Job('rc', 'extract', 'layout.extract_rc', (), (), (('netlist', 'spice'),), None,
              json.dumps({'ports': ['GND', 'IN', 'OUT'], 'temperature_c': 27}))
    frozen = {'layout': Asset(b'frozen-gds', 'gds'), 'netlist': Asset(b'frozen-source', 'spice'),
              'task': Asset(json.dumps({'output': {'top_cell': 'TOP'}, 'netlist_subcircuit': 'TOP'}).encode(), 'json')}
    result = backend.run(job, frozen)
    assert captured['candidate.gds'] == frozen['layout']
    assert captured['source.spice'] == frozen['netlist']
    assert 'QUERY CCI' in captured['control.svrf'].content.decode()
    assert 'PEX NETLIST' not in captured['control.svrf'].content.decode()
    if failure:
        assert result.status == 'error' and not result.outputs
        assert 'qrc.log' in result.evidence
    else:
        assert result.status == 'passed'
        extracted = result.outputs['netlist'].content.decode()
        assert '.SUBCKT TOP GND IN OUT' in extracted
        for physical in circuit.splitlines()[1:5]:
            assert physical in extracted
        assert backend.identity['execution'] == 'operator-native'


@pytest.mark.parametrize('technology', ['/eda/pdk-sibling/technology', '/eda/pdk/../author'])
def test_quantus_technology_cannot_read_an_undeclared_author_workspace(native_tmp_path, monkeypatch, technology):
    (native_tmp_path / 'identity').write_text('declared PDK')
    monkeypatch.setattr(NativeTool, 'probe', native_probe)
    runtime = ExternalRuntime('licensed-test', {'image': 'unused',
        'environment': {'PDK_ROOT': str(native_tmp_path), 'QRC_ROOT': technology},
        'mounts': [{'source': str(native_tmp_path), 'target': str(native_tmp_path), 'release': 'test',
                    'identity_paths': ['identity']}]})
    with pytest.raises(ValueError, match='declared resource mount'):
        CalibreQuantusNative(runtime=runtime, deck='unused', technology_env='QRC_ROOT', ground='GND')


@pytest.mark.parametrize('card', [
    'Rpoly IN OUT poly L=2e-6',
    'Rpoly IN OUT poly L=0 W=1e-6',
    'Rpoly IN OUT poly L=2e-6 W=nan',
])
def test_native_two_terminal_resistor_requires_physical_dimensions(card):
    circuit = '.subckt TOP IN OUT GND\n'+card+'\nCwire OUT GND 1e-9\n.ends TOP\n'
    with pytest.raises(ValueError, match='primitive resistor lacks valid geometry'):
        adapt_dspf(circuit, 'TOP', ['IN', 'OUT', 'GND'], {},
                   resistor_models={'poly': {'type': 'primitive', 'model': 'poly'}})
