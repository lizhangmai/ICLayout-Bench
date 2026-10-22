"""Calibre/Quantus extraction preserves physical inputs and rejects bad evidence."""

import json
from types import SimpleNamespace

import pytest

from benchmarking.eda.backends.calibre_quantus import CalibreQuantusNative
from benchmarking.eda.environment import ExternalRuntime
from benchmarking.eda.netlists.dspf import bind_extracted_netlist
from benchmarking.evaluation import Job
from benchmarking.execution.tools import ToolResult
from benchmarking.execution.tools.native import NativeTool
from benchmarking.files import Asset

pytestmark = pytest.mark.unit


def native_probe(self, command, **kwargs):
    output = (b'Version: test\nBuild Ref. No.: 12\nBuild Date: fixed\n'
              if command[0] == 'quantus' else b'Calibre native release\n')
    return SimpleNamespace(returncode=0, stdout=output)


@pytest.mark.parametrize('failure', ['', 'lvs', 'junctions', 'completion', 'exit', 'stuck-exit',
                                    'stuck-no-console', 'bad-exit-report', 'missing-exit-report',
                                    'recreated-log-grace'])
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
                                  ground='GND')
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
    native_execute = backend.tool.run
    if failure == 'recreated-log-grace':
        backend.process_exit_grace_seconds = .1

    def execute(command, files, exports, **kwargs):
        captured.update(files)
        if failure == 'recreated-log-grace':
            # Keep the generated waiter's arguments, redirections and exports;
            # substitute only the licensed executable and preceding LVS/CCI.
            script = files['run.sh'].content.decode().split('python3 wait_process_tree.py', 1)[1]
            script = 'python3 wait_process_tree.py' + script.replace('quantus -cmd qrc.cmd', 'python3 fake_quantus.py')
            worker = ('from pathlib import Path\nimport time\n'
                      f'Path("lvs.report").write_text({report!r})\n'
                      f'Path("extracted.dspf").write_text({circuit!r})\n'
                      'Path("qrc.log").unlink(missing_ok=True)\n'
                      'Path("qrc.log").write_text("Quantus terminated normally\\n")\n'
                      'time.sleep(3)\n')
            staged = files | {'run.sh': Asset(script.encode(), 'text'),
                              'fake_quantus.py': Asset(worker.encode(), 'python')}
            return native_execute(command, staged, exports, **kwargs)
        evidence = {'lvs.report': Asset(report.encode(), 'text'),
                    'qrc.log': Asset(b'Quantus terminated normally' if failure != 'completion' else b'aborted', 'text'),
                    'qrc.console.log': Asset(b'native console', 'text'),
                    'extracted.dspf': Asset(circuit.encode(), 'spice')}
        timed_out = failure in {'stuck-exit', 'stuck-no-console'}
        code = 124 if timed_out else 1 if failure == 'exit' else 0
        exit_report = {'schema': 'iclayout-tool-exit-v1', 'returncode': code,
                       'command_returncode': 137 if timed_out else code,
                       'completion_seen': failure != 'completion', 'exit_grace_exceeded': timed_out,
                       'exit_grace_seconds': backend.process_exit_grace_seconds, 'processes': []}
        evidence['qrc.exit.json'] = Asset(json.dumps(exit_report).encode(), 'json')
        if failure == 'stuck-exit':
            evidence['qrc.console.log'] = Asset(
                b'EDA process did not exit after its completion marker: {"processes": []}', 'text')
        elif failure == 'bad-exit-report':
            evidence['qrc.exit.json'] = Asset(b'{broken', 'json')
        elif failure == 'missing-exit-report':
            del evidence['qrc.exit.json']
        return ToolResult(code, f'Native Calibre/Quantus exited with {code}' if code else '', evidence, {})

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
        if failure in {'stuck-exit', 'stuck-no-console', 'recreated-log-grace'}:
            assert 'process tree did not exit' in result.reason
            assert 'execution_error' in result.evidence
            assert b'Quantus terminated normally' in result.evidence['qrc.log'].content
        elif failure in {'exit', 'bad-exit-report', 'missing-exit-report'}:
            assert 'execution_error' in result.evidence
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
    with pytest.raises(ValueError):
        bind_extracted_netlist(circuit, 'TOP', ['IN', 'OUT', 'GND'])
