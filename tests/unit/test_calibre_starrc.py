"""StarRC acceptance uses native evidence and preserves frozen physical inputs."""

import json
from types import SimpleNamespace

import pytest

from benchmarking.engine.backends.calibre_starrc import (
    CalibreStarRCNative,
    command_setting,
)
from benchmarking.engine.external import ExternalRuntime
from benchmarking.engine.tools.native import NativeTool
from benchmarking.engine.tools.types import ToolResult
from benchmarking.evaluation import Job
from benchmarking.files import Asset

pytestmark = pytest.mark.unit


def native_probe(self, command, **kwargs):
    if command[0] == 'StarXtract':
        return SimpleNamespace(returncode=1, stdout=b'notice\nVersion: test\nBuilt on: fixed\n')
    return SimpleNamespace(returncode=0, stdout=b'Calibre native release\n')


@pytest.mark.parametrize('failure', ['', 'lvs', 'junctions', 'ports', 'completion', 'summary', 'exit'])
def test_starrc_requires_complete_candidate_extraction(native_tmp_path, monkeypatch, failure):
    pdk = native_tmp_path / 'pdk'
    technology = pdk / 'technology'
    technology.mkdir(parents=True)
    (pdk / 'lvs.rules').write_text('LAYOUT PRIMARY "old"\nSOURCE PRIMARY "old"\n')
    for name in ['grid', 'mapping', 'hcell', 'pins']:
        (technology / name).write_text('declared '+name)
    (technology / 'command').write_text('BLOCK: OLD\nTCAD_GRD_FILE: old\nMAPPING_FILE: old\n'
                                       'NETLIST_FILE: old\nCALIBRE_QUERY_FILE: old\nCOUPLE_TO_GROUND: NO\n'
                                       'EXTRACTION: \nCALIBRE_OPTIONAL_DEVICE_PIN_FILE: placeholder\n'
                                       'CALIBRE_RUNSET: old\n')
    (technology / 'query').write_text('layout netlist write TOP_CELL.spi\n')
    runtime = ExternalRuntime('licensed-test', {'image': 'unused',
        'environment': {'PDK_ROOT': str(pdk), 'STAR_ROOT': str(technology)},
        'mounts': [{'source': str(pdk), 'target': str(pdk), 'release': 'test',
                    'identity_paths': ['lvs.rules', 'technology']}]})
    monkeypatch.setattr(NativeTool, 'probe', native_probe)
    backend = CalibreStarRCNative(runtime=runtime, deck='lvs.rules', technology_env='STAR_ROOT',
        grid='grid', mapping='mapping', hcell_file='hcell', command_template='command', query_template='query',
        extraction_mode='RC', device_pin_file='pins')
    assert backend.version == [('test', 'fixed')]
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
Rwire IN OUT 1000
Cwire OUT GND 1e-9
M0 OUT IN GND GND nmodel L=2e-6 W=3e-6 AS=1e-12 AD=2e-12 PS=3e-6 PD=4e-6
.ends TOP
'''
    if failure == 'lvs':
        report = report.replace('CORRECT', 'INCORRECT')
    if failure == 'junctions':
        circuit = circuit.replace(' AS=1e-12', '')
    if failure == 'ports':
        circuit = circuit.replace('TOP OUT GND IN', 'TOP OTHER GND IN')
    log = 'Warnings: 0    Errors: 0\nDone          Elp=00:00:01 Cpu=00:00:01\n'
    if failure == 'completion':
        log = log.split('Done')[0]
    if failure == 'summary':
        log = log.replace('Errors: 0', 'Errors: 1')
    captured = {}

    def execute(command, files, exports, **kwargs):
        captured.update(files)
        return ToolResult(1 if failure == 'exit' else 0, '', {
            'lvs.report': Asset(report.encode(), 'text'), 'starrc.log': Asset(log.encode(), 'text'),
            'extracted.dspf': Asset(circuit.encode(), 'spice')}, {})

    backend.tool.run = execute
    job = Job('rc', 'extract', 'layout.extract_rc', (), (), (('netlist', 'spice'),), None,
              json.dumps({'ports': ['GND', 'IN', 'OUT'], 'temperature_c': 27}))
    frozen = {'layout': Asset(b'frozen-gds', 'gds'), 'netlist': Asset(b'frozen-cdl', 'spice'),
              'task': Asset(json.dumps({'output': {'top_cell': 'TOP'}, 'netlist_subcircuit': 'TOP'}).encode(), 'json')}
    result = backend.run(job, frozen)
    assert captured['candidate.gds'] == frozen['layout']
    assert captured['source.spice'] == frozen['netlist']
    assert 'QUERY CCI' in captured['control.svrf'].content.decode()
    assert 'PEX NETLIST' not in captured['control.svrf'].content.decode()
    assert 'COUPLE_TO_GROUND: NO' in captured['star.cmd'].content.decode()
    assert 'EXTRACTION: RC' in captured['star.cmd'].content.decode()
    assert 'CALIBRE_RUNSET: control.svrf' in captured['star.cmd'].content.decode()
    assert f'CALIBRE_OPTIONAL_DEVICE_PIN_FILE: {technology}/pins' in captured['star.cmd'].content.decode()
    assert backend.identity['execution'] == 'operator-native'
    if failure:
        assert result.status == 'error' and not result.outputs
        assert result.evidence['extracted.dspf'].content.decode() == circuit
    else:
        assert result.status == 'passed'
        extracted = result.outputs['netlist'].content.decode()
        assert '.SUBCKT TOP GND IN OUT' in extracted
        for component in circuit.splitlines()[1:4]:
            assert component in extracted


def test_starrc_template_cannot_silently_add_or_duplicate_settings():
    assert command_setting('BLOCK: old\nKEEP: policy\n', 'BLOCK', 'TOP') == 'BLOCK: TOP\nKEEP: policy\n'
    for template in ['KEEP: policy\n', 'BLOCK: a\nBLOCK: b\n']:
        with pytest.raises(ValueError, match='exactly once'):
            command_setting(template, 'BLOCK', 'TOP')

    for mode in ['C', 'R', 'arbitrary']:
        with pytest.raises(ValueError, match='mode must be RC'):
            CalibreStarRCNative(runtime=None, deck='unused', technology_env='unused',
                grid='grid', mapping='map', command_template='command', query_template='query',
                hcell_file='hcell', extraction_mode=mode)


@pytest.mark.parametrize('technology', ['/eda/pdk-sibling/technology', '/eda/pdk/../author'])
def test_starrc_technology_requires_a_declared_resource(native_tmp_path, monkeypatch, technology):
    (native_tmp_path / 'identity').write_text('resource')
    monkeypatch.setattr(NativeTool, 'probe', native_probe)
    runtime = ExternalRuntime('licensed-test', {'image': 'unused',
        'environment': {'PDK_ROOT': str(native_tmp_path), 'STAR_ROOT': technology},
        'mounts': [{'source': str(native_tmp_path), 'target': str(native_tmp_path), 'release': 'test',
                    'identity_paths': ['identity']}]})
    with pytest.raises(ValueError, match='declared resource mount'):
        CalibreStarRCNative(runtime=runtime, deck='unused', technology_env='STAR_ROOT',
            grid='grid', mapping='map', command_template='command', query_template='query', hcell_file='hcell')
