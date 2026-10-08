"""Native report semantics, independent of licensed tools or process data.

These formats have no prior adapter coverage. Handwritten reports exercise the
fail-closed acceptance boundary; analytical samples exercise differential gain
and log-frequency crossings. They establish parser behavior, not EDA accuracy.
"""
import json
import math
import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest

from benchmarking.engine.backends.pvs import PvsDocker
from benchmarking.engine.backends.spectre import SpectreDocker
from benchmarking.engine.tools.types import ToolResult
from benchmarking.evaluation import Job, parse_evaluation
from benchmarking.files import Asset

pytestmark = pytest.mark.unit


def test_spectre_memory_allocation_is_applied_and_recorded(monkeypatch):
    from benchmarking.engine.tools.docker import DockerTool

    commands = []

    def version(command, **kwargs):
        commands.append(command)
        return 'fixture-version'

    monkeypatch.setattr('benchmarking.engine.tools.docker.subprocess.check_output', version)
    tool = DockerTool('unused', ['spectre', '-W'], 10, memory_mb=8192)
    command = commands[-1]
    assert command[command.index('--memory')+1] == '8192m'
    assert tool.identity['limits']['memory_mb'] == 8192
    for value in [True, 0, -1, 262145]:
        with pytest.raises(ValueError, match='Tool memory'):
            DockerTool('unused', ['spectre', '-W'], 10, memory_mb=value)


def test_native_spectre_keeps_frozen_deck_and_rejects_crash_exit():
    from benchmarking.engine.backends.spectre_native import _NativeSpectreTool
    from benchmarking.engine.external import ExternalRuntime

    runtime = ExternalRuntime('native-test', {'image': 'unused', 'environment': {}, 'mounts': []})
    version = [sys.executable, '-c', 'print("licensed-fixture")']
    tool = _NativeSpectreTool(runtime, 5, version_command=version)
    frozen = Asset(b'simulator lang=spectre\n// /workspace/frozen\n', 'spice')
    result = tool.run(['bash', '-c', 'cat deck.scs > observed.scs; exit 139'],
                      {'deck.scs': frozen}, {'observed.scs': 'spice'})
    assert result.files['observed.scs'] == frozen
    assert result.returncode == 139 and 'Native Spectre' in result.reason
    assert tool.identity['execution'] == 'operator-native'
    assert 'image_id' not in tool.identity and 'limits' not in tool.identity


def test_aps_is_explicit_preserves_inputs_and_propagates_native_failure(monkeypatch):
    # Contract: selecting APS must reach the native command and identity, while
    # retaining Spectre's frozen inputs and error semantics. The I/O double
    # cannot establish numerical equivalence or license availability.
    from benchmarking.engine.backends.spectre_aps import SpectreAPSDocker
    from benchmarking.engine.external import ExternalRuntime
    from benchmarking.engine.tools.docker import DockerTool

    seen = []

    class Tool:
        def __init__(self, *args, **kwargs):
            self.identity = {'tool_version': 'test'}

        def run(self, command, files, exports):
            seen.append((command, files))
            return ToolResult(1, 'Native license unavailable', {},
                              {'console': Asset(b'license failed', 'text')})

    monkeypatch.setattr('benchmarking.engine.backends.spectre.DockerTool', Tool)
    monkeypatch.setattr('benchmarking.engine.external.ExternalRuntime.pdk_file', lambda runtime, name: (None, '/pdk/'+name))
    threads = 2
    runtime = ExternalRuntime('test', {'image': 'test-image', 'environment': {}, 'mounts': []})
    settings = {'runtime': runtime, 'model': 'model', 'section': 'tt',
                'sections': ['tt', 'res_tt', 'mim_tt'], 'model_includes': ['passive.scs']}
    backend = SpectreAPSDocker(threads=threads, **settings)
    classic = SpectreDocker(**settings)
    assert backend.identity['threads'] == threads
    assert backend.identity['adapter'] != classic.identity['adapter']
    assert backend.identity['adapter_sha256'] == classic.identity['adapter_sha256']
    inputs = {'deck': Asset(b'fixture', 'spice'), 'dut': Asset(b'circuit', 'spice')}
    job = Job('probe', 'simulate', 'circuit.simulate', (), (), (), None,
              json.dumps({'measurements': {'value': 'V'}, 'waveform': {}}))
    result = backend.run(job, inputs)
    command, files = seen.pop()
    assert '+aps' in command and f'+mt={threads}' in command
    assert files['deck.scs'] is inputs['deck'] and files['dut.spice'] is inputs['dut']
    assert files['models.scs'].content.decode() == '''simulator lang=spectre
include "/pdk/model" section=tt
include "/pdk/model" section=res_tt
include "/pdk/model" section=mim_tt
include "/pdk/passive.scs"
'''
    assert result.status == 'error' and result.reason == 'Native license unavailable'
    assert result.evidence['console'].content == b'license failed'
    for invalid in (True, 0, DockerTool.CPUS + 1):
        with pytest.raises(ValueError, match='CPU allocation'):
            SpectreAPSDocker(threads=invalid, **settings)

    optimized = SpectreAPSDocker(threads=threads, aps_preset='moderate',
                                  postlayout='hpa', **settings)
    assert optimized.identity['aps_preset'] == 'moderate'
    assert optimized.identity['postlayout'] == 'hpa'
    optimized.run(job, inputs)
    command, _ = seen.pop()
    assert command[:4] == ['spectre', '++aps=moderate', f'+mt={threads}', '+postlayout=hpa']
    optimized.run(replace(job, parameters_json=json.dumps(job.parameters | {'section': 'ff'})), inputs)
    _, files = seen.pop()
    assert files['models.scs'].content.decode() == '''simulator lang=spectre
include "/pdk/model" section=ff
include "/pdk/passive.scs"
'''
    for field, invalid in (('aps_preset', 'fast'), ('postlayout', 'aggressive')):
        with pytest.raises(ValueError, match='(?i)' + field.replace('_', ' ')):
            SpectreAPSDocker(threads=threads, **settings, **{field: invalid})


def test_spectre_x_preserves_inputs_and_rejects_native_failure(monkeypatch):
    from benchmarking.engine.backends.spectre_native import SpectreXNative
    from benchmarking.engine.backends.spectre_x import SpectreXDocker
    from benchmarking.engine.external import ExternalRuntime
    from benchmarking.engine.tools.docker import DockerTool

    seen = []

    class Tool:
        def __init__(self, *args, **kwargs):
            self.identity = {'tool_version': 'test'}

        def run(self, command, files, exports):
            seen.append((command, files))
            return ToolResult(139, 'Tool/container exited with 139', {},
                              {'console': Asset(b'native crash', 'text')})

    monkeypatch.setattr('benchmarking.engine.backends.spectre.DockerTool', Tool)
    monkeypatch.setattr('benchmarking.engine.external.ExternalRuntime.pdk_file', lambda *args: (None, '/pdk/model'))
    runtime = ExternalRuntime('test', {'image': 'test-image', 'environment': {}, 'mounts': []})
    settings = {'runtime': runtime, 'model': 'model', 'section': 'tt'}
    backend = SpectreXDocker(threads=2, preset='ax', preset_override=['maxstep'], memory_mb=8192, **settings)
    assert backend.identity['adapter'] == 'spectre-x-docker'
    assert backend.identity['threads'] == 2 and backend.identity['preset'] == 'ax'
    inputs = {'deck': Asset(b'fixture', 'spice'), 'dut': Asset(b'circuit', 'spice')}
    job = Job('probe', 'simulate', 'circuit.simulate', (), (), (), None,
              json.dumps({'measurements': {'value': 'V'}, 'waveform': {}}))
    result = backend.run(job, inputs)
    command, files = seen.pop()
    assert command[:3] == ['spectre', '+preset=ax', '+mt=2']
    assert '-preset_override=maxstep' in command
    assert backend.identity['preset_override'] == ['maxstep']
    assert files['deck.scs'] is inputs['deck'] and files['dut.spice'] is inputs['dut']
    assert result.status == 'error' and result.reason == 'Tool/container exited with 139'
    assert result.evidence['console'].content == b'native crash'
    for invalid in (True, 0, DockerTool.CPUS + 1):
        with pytest.raises(ValueError, match='CPU allocation'):
            SpectreXDocker(threads=invalid, **settings)
    with pytest.raises(ValueError, match='Spectre X preset'):
        SpectreXDocker(preset='moderate', **settings)
    with pytest.raises(ValueError, match='overridden parameters'):
        SpectreXDocker(preset_override=['unknown'], **settings)
    # Host execution uses the evaluator's affinity, independently of the
    # container allocation. The command and identity must agree on that count.
    monkeypatch.setattr('benchmarking.engine.backends.spectre_native.os.sched_getaffinity',
                        lambda pid: set(range(16)))
    monkeypatch.setattr(SpectreXNative, 'tool_type', Tool)
    native = SpectreXNative(threads=16, preset='mx', **settings)
    result = native.run(job, inputs)
    assert '+mt=16' in seen.pop()[0]
    assert native.identity['adapter'] == 'spectre-x-native'
    assert native.identity['threads'] == 16
    assert result.status == 'error'
    with pytest.raises(ValueError, match='CPU allocation'):
        SpectreXNative(threads=17, **settings)
    with pytest.raises(TypeError, match='memory_mb'):
        SpectreXNative(memory_mb=4096, **settings)


def test_spectre_calibration_selects_eligible_setting_and_reuses_frozen_parameters(monkeypatch):
    # The external tool emits constant analytical traces. The exact-target
    # setting is ineligible; the two legal settings tie, requiring lower ID.
    # This protects selection and downstream propagation, not simulator physics.
    backend = object.__new__(SpectreDocker)
    backend.runtime = SimpleNamespace(pdk_file=lambda name: (None, '/pdk/model'))
    backend.model, backend.section = 'models', 'tt'
    monkeypatch.setattr('benchmarking.engine.external.ExternalRuntime.pdk_file', lambda *args: (None, '/pdk/model'))
    seen, fail = [], False

    class Tool:
        def run(self, command, files, exports):
            assert b'include "selection.scs"' in files['deck.scs'].content
            value = float(files['selection.scs'].content.decode().split('setting=')[1])
            seen.append(value)
            raw = ('VALUE\n' + ''.join(f'"time" {t}\n"x" {value}\n"quality" {2 if value == 1 else 0}\n'
                                      for t in [0, 1, 2]) + 'END\n')
            return ToolResult(1 if fail else 0, '', {
                'spectre.log': Asset(b'spectre completes with 0 errors', 'text'),
                'results/tran.tran.tran': Asset(raw.encode(), 'text')}, {})
    backend.tool = Tool()
    measure = {'trace': 'x', 'operation': 'mean', 'start_s': 0, 'stop_s': 2, 'unit': 'V'}
    parameters = {'measurements': {'mean': 'V', 'quality': '1'},
                  'waveform': {'max_step_s': 1, 'traces': {
                      'x': {'terms': {'x': 1}}, 'quality': {'terms': {'quality': 1}}},
                      'measures': {'mean': measure,
                                   'quality': measure | {'trace': 'quality', 'operation': 'max', 'unit': '1'}}},
                  'calibration': {'candidates': [
                      {'id': 7, 'parameters': {'setting': .5}},
                      {'id': 2, 'parameters': {'setting': 1}},
                      {'id': 3, 'parameters': {'setting': 1.5}}],
                      'target': {'measurement': 'mean', 'unit': 'V', 'value': 1},
                      'eligibility': [{'measurement': 'quality', 'unit': '1', 'upper': 1}]}}
    job = Job('calibration', 'simulate', 'circuit.simulate', (), (('selection', 'json'),),
              (), None, json.dumps(parameters))
    inputs = {key: Asset(b'fixture', 'spice') for key in ('deck', 'dut')}
    inputs['deck'] = Asset(b'title\nsimulator lang=spectre\ninclude "selection.scs"\n', 'spice')
    boolean_target = json.loads(json.dumps(parameters))
    boolean_target['calibration']['target']['value'] = True
    with pytest.raises(ValueError, match='Invalid calibration target'):
        backend.run(replace(job, parameters_json=json.dumps(boolean_target)), inputs)
    boolean_bound = json.loads(json.dumps(parameters))
    boolean_bound['calibration']['eligibility'][0]['upper'] = False
    with pytest.raises(ValueError, match='Invalid calibration eligibility bounds'):
        backend.run(replace(job, parameters_json=json.dumps(boolean_bound)), inputs)
    result = backend.run(job, inputs)
    assert result.status == 'passed'
    assert seen == [.5, 1, 1.5]
    assert json.loads(result.outputs['selection'].content)['id'] == 3
    assert len(json.loads(result.evidence['calibration.json'].content)) == len(seen)
    downstream = parameters.copy()
    del downstream['calibration']
    child = replace(job, outputs=(), parameters_json=json.dumps(downstream))
    reused = backend.run(child, inputs | {'selection': result.outputs['selection']})
    assert reused.measurements['mean'].value == 1.5
    assert job.parameters == parameters  # The frozen plan was not mutated.
    with pytest.raises(ValueError, match='explicit include'):
        backend.run(job, inputs | {'deck': Asset(b'title\n// include "selection.scs"\n', 'spice')})
    # With no validity bounds, quality cannot disqualify the closest setting.
    unbounded = json.loads(json.dumps(parameters))
    unbounded['calibration']['eligibility'] = []
    selected = backend.run(replace(job, parameters_json=json.dumps(unbounded)), inputs)
    assert selected.status == 'passed'
    assert json.loads(selected.outputs['selection'].content)['id'] == 2
    assert all(row['eligible'] for row in json.loads(selected.evidence['calibration.json'].content))
    parameters['calibration']['eligibility'][0]['upper'] = -1
    rejected = backend.run(replace(job, parameters_json=json.dumps(parameters)), inputs)
    assert rejected.status == 'error' and not rejected.outputs
    assert 'No eligible' in rejected.reason
    fail = True
    rejected = backend.run(job, inputs)
    assert rejected.status == 'error' and not rejected.outputs and rejected.evidence
    parameters['calibration']['candidates'][0]['parameters'] = {'bad\ninclude': 1}
    with pytest.raises(ValueError, match='simple names'):
        backend.run(replace(job, parameters_json=json.dumps(parameters)), inputs)


def test_relative_edge_thresholds_measure_slew_independently_of_swing():
    # An affine ramp across the interpolated [0.5, 1.5] window takes 0.6 s
    # between 20% and 80%, at any positive swing or DC offset. The outside
    # samples must not set its range. This is a measurement oracle, not a DUT.
    from benchmarking.engine.measurements.waveform import measure_waveform

    event = {'trace': 'out', 'threshold_fraction': .2, 'direction': 'rise'}
    slew = {'operation': 'delay', 'start_s': .5, 'stop_s': 1.5, 'unit': 's',
            'trigger': event, 'target': event | {'threshold_fraction': .8},
            'pairs': [[1, 1]], 'aggregation': 'max'}
    settings = {'max_step_s': 1, 'traces': {'out': {'terms': {'out': 1}}},
                'measures': {'slew': slew}}
    for swing, offset in [(2., 0.), (.01, 1.)]:
        samples = {'time': [0, 1, 2], 'out': [offset, offset+swing, offset+2*swing]}
        assert measure_waveform(samples, settings)['slew'].value == pytest.approx(.6)
        falling = slew | {'trigger': event | {'threshold_fraction': .8, 'direction': 'fall'},
                          'target': event | {'direction': 'fall'}}
        samples['out'].reverse()
        assert measure_waveform(samples, settings | {'measures': {'slew': falling}})['slew'].value == pytest.approx(.6)
    with pytest.raises(ValueError, match='nonconstant'):
        measure_waveform(samples | {'out': [1, 1, 1]}, settings)
    with pytest.raises(ValueError, match='exactly one'):
        measure_waveform(samples, settings | {'measures': {
            'slew': slew | {'trigger': event | {'threshold': 0}}}})


def test_lvs_requires_complete_nonblackboxed_match(monkeypatch):
    report = '''Top Cell : demo <vs> demo
Run Result : MATCH
Extraction Clean
Cells matched | 1
Cells not run | 0
Cells which mismatch | 0
Cells with parameter mismatches | 0
Cells with mismatched instance subtypes | 0
Cells that have been blackboxed | 0
END OF REPORT
'''
    # The trusted deck read is the external I/O boundary.
    class Deck:
        def read_text(self):
            return 'rule deck'
    backend = object.__new__(PvsDocker)
    backend.runtime = SimpleNamespace(pdk_file=lambda name: (Deck(), '/pdk/deck'))
    backend.check = 'lvs'
    backend.settings = {'lvs_deck': 'lvs', 'lvs_includes': {}}
    job = parse_evaluation(b'''mode="characterization"
metrics=[]
[[jobs]]
id="lvs"
stage="check"
operation="layout.lvs"
inputs={layout="input:layout",task="input:task",netlist="input:netlist"}
''').jobs[0]
    inputs = {'layout': Asset(b'not interpreted by fake tool', 'gds'),
              'task': Asset(b'{"output":{"top_cell":"demo"},"netlist_subcircuit":"demo"}', 'json'),
              'netlist': Asset(b'.subckt demo a b\n.ends', 'spice')}
    class Tool:
        def run(self, *args):
            return ToolResult(0, '', {'demo.lvsrpt.cls': Asset(current.encode(), 'text')}, {})
    backend.tool = Tool()
    for current, expected in [(report, 'passed'),
                              (report.replace('blackboxed | 0', 'blackboxed | 1'), 'error'),
                              (report.replace('END OF REPORT', ''), 'error'),
                              (report.replace('Extraction Clean', ''), 'error'),
                              (report + 'Run Result : MISMATCH\n', 'error')]:
        assert backend.run(job, inputs).status == expected


def test_spectre_differential_transfer_uses_complex_input_and_log_crossings(monkeypatch):
    # |H| is 10, sqrt(10), 0.1 at 1, 10, 1000 Hz; interpolate in log space.
    # A 2 V differential stimulus prevents accidentally assuming unit excitation.
    ac = 'VALUE\n' + ''.join(
        f'"freq" {freq}\n"out" (0 {2*gain})\n"inp" (0 1)\n"inn" (0 -1)\n'
        for freq, gain in [(1, 10), (10, math.sqrt(10)), (1000, .1)]) + 'END\n'
    dc = 'VALUE\n"out" "V" 0.5\n"VDD:p" "I" -0.000002\nEND\n'
    backend = object.__new__(SpectreDocker)
    backend.runtime = SimpleNamespace(pdk_file=lambda name: (None, '/pdk/model'))
    backend.model, backend.section = 'models', 'tt'
    monkeypatch.setattr('benchmarking.engine.external.ExternalRuntime.pdk_file', lambda *args: (None, '/pdk/model'))
    class Tool:
        def run(self, *args):
            return ToolResult(0, '', {k: Asset(v.encode(), 'text') for k, v in {
                'spectre.log': 'spectre completes with 0 errors',
                'results/ac.ac': ac, 'results/op.dc': dc}.items()}, {})
    backend.tool = Tool()
    job = parse_evaluation(b'''mode="characterization"
metrics=[]
[[jobs]]
id="ac"
stage="simulate"
operation="circuit.simulate"
inputs={deck="input:deck",dut="input:dut"}
parameters.measurements={gain_db="dB",unity_hz="Hz",power_w="W"}
parameters.response={output="out",positive="inp",negative="inn",supply_current="VDD:p",supply_v=1.0}
''').jobs[0]
    inputs = {k: Asset(b'fixture', 'spice') for k in ('deck', 'dut')}
    result = backend.run(job, inputs)
    assert result.status == 'passed'
    assert result.measurements['gain_db'].value == pytest.approx(20)
    # Segment from sqrt(10) at 10 Hz to .1 at 1000 Hz has slope -0.75.
    assert result.measurements['unity_hz'].value == pytest.approx(10 * 10**(2/3))
    assert result.measurements['power_w'].value == pytest.approx(2e-6)
    profile = {'input': {'terms': {'inp': 1, 'inn': -1}},
               'output': {'terms': {'out': 1}}, 'max_frequency_ratio': 100,
               'measures': {'gain': {'operation': 'gain_db', 'frequency_hz': 1, 'unit': 'dB'},
                            'power': {'operation': 'dc', 'terms': {'VDD:p': -1}, 'unit': 'W'}}}
    transfer_job = replace(job, parameters_json=json.dumps({
        'measurements': {'gain': 'dB', 'power': 'W'}, 'ac_transfer': profile}))
    measured = backend.run(transfer_job, inputs)
    assert measured.status == 'passed'
    assert measured.measurements['gain'].value == pytest.approx(20)
    assert measured.measurements['power'].value == pytest.approx(2e-6)
    ac = ac.removesuffix('END\n')
    failed = backend.run(job, inputs)
    assert failed.status == 'error' and 'Incomplete' in failed.reason
    assert 'results/ac.ac' in failed.evidence


def test_phase_margin_unwraps_lag_across_negative_real_axis():
    # Analytical complex responses place unity one third of a decade above 10 Hz.
    # The next sample wraps to +170 degrees; interpolating wrapped phase would
    # incorrectly report a large positive margin for the later unity crossing.
    import cmath

    from benchmarking.engine.backends.spectre import ac_measurements

    ac = {'freq': [1, 10, 100], 'p': [1, 1, 1], 'n': [0, 0, 0],
          'out': [10*cmath.exp(-1j*math.radians(150)),
                  math.sqrt(10)*cmath.exp(-1j*math.radians(170)),
                  .1*cmath.exp(1j*math.radians(170))]}
    result = ac_measurements(ac, {'out': [0], 'supply': [-1]},
                             {'output': 'out', 'positive': 'p', 'negative': 'n',
                              'supply_current': 'supply', 'supply_v': 1})
    assert result['phase_margin_deg'].value == pytest.approx(10-20/3)


def test_waveform_integrates_interpolated_windows_and_preserves_early_edges():
    # Exact y=t integral on [0.5, 1.5] is 1; RMS is sqrt(13/12).
    # An output crossing before its matching input must retain negative delay.
    # These synthetic traces verify measurement math, not circuit feasibility.
    from benchmarking.engine.measurements.waveform import measure_waveform

    samples = {'time': [0, 1, 2], 'ramp': [0, 1, 2], 'early': [1, 2, 3]}
    common = {'start_s': .5, 'stop_s': 1.5, 'trace': 'ramp', 'unit': 'V'}
    event = {'trace': 'ramp', 'threshold': 1.5, 'direction': 'rise'}
    settings = {'max_step_s': 1, 'traces': {
        'ramp': {'terms': {'ramp': 1}}, 'early': {'terms': {'early': 1}},
        'error': {'terms': {'ramp': 1}, 'offset': -.75},
        'negative_error': {'terms': {'ramp': -1}, 'offset': .75}},
        'measures': {
            'integral': common | {'operation': 'integral', 'unit': 'V*s'},
            'rms': common | {'operation': 'rms'},
            'difference': common | {'operation': 'mean_difference',
                                    'reference_start_s': 0, 'reference_stop_s': .5},
            'delay': {'operation': 'delay', 'start_s': 0, 'stop_s': 2, 'unit': 's',
                      'trigger': event, 'target': event | {'trace': 'early'},
                      'pairs': [[1, 1]], 'aggregation': 'max'}}}
    result = measure_waveform(samples, settings)
    assert result['integral'].value == pytest.approx(1)
    assert result['rms'].value == pytest.approx(math.sqrt(13/12))
    # Ramp means on [.5, 1.5] and [0, .5] are 1 and .25.
    assert result['difference'].value == pytest.approx(.75)
    assert result['delay'].value == pytest.approx(-1)
    # y=+/-(t-.75) on [.25, 1.25] has two triangles of area 1/8
    # each, despite zero signed area. Both the window and zero split samples.
    for trace in ('error', 'negative_error'):
        measures = {operation: {'operation': operation, 'trace': trace,
                               'start_s': .25, 'stop_s': 1.25, 'unit': 'V*s'}
                    for operation in ('integral', 'abs_integral')}
        areas = measure_waveform(samples, settings | {'measures': measures})
        assert areas['integral'].value == pytest.approx(0)
        assert areas['abs_integral'].value == pytest.approx(.25)
    with pytest.raises(ValueError, match='event pair'):
        measure_waveform(samples | {'early': [0, 0, 0]}, settings)
    with pytest.raises(ValueError, match='sparse'):
        measure_waveform(samples, settings | {'max_step_s': .5})
    with pytest.raises(ValueError, match='nonfinite'):
        measure_waveform(samples | {'ramp': [0, math.nan, 2]}, settings)
    with pytest.raises(ValueError, match='outside'):
        measure_waveform(samples, settings | {'measures': {
            'difference': settings['measures']['difference'] | {'reference_start_s': -1}}})


def test_sampled_adc_transfer_requires_complete_ordered_stable_codes():
    # A seven-code staircase has six transition midpoints. The expected DNL
    # and INL follow from declared full-scale endpoints, independently of the
    # measurement implementation or a simulator waveform.
    from benchmarking.engine.measurements.waveform import measure_waveform

    levels = [-.3, -.2, -.1, .02, .1, .2, .3]
    codes = list(range(1, 8))
    times = list(range(21))
    samples = {'time': times, 'vin': [levels[t//3] for t in times]}
    for bit in range(3):
        samples[f'b{bit}'] = [float((codes[t//3] >> bit) & 1) for t in times]
    transfer = {'input_trace': 'vin', 'bit_traces': ['b0', 'b1', 'b2'],
                'logic_low_v': .2, 'logic_high_v': .8,
                'codes': codes, 'windows_s': [[3*i+.2, 3*i+1.8] for i in range(7)],
                'full_scale_low_v': -.35, 'full_scale_high_v': .35,
                'max_input_ripple_v': .001}
    def measure(statistic, unit):
        return {'operation': 'adc_transfer', 'transfer': 'flash',
                'statistic': statistic, 'unit': unit}
    settings = {'max_step_s': 1, 'traces': {name: {'terms': {name: 1}}
                                           for name in ('vin', 'b0', 'b1', 'b2')},
                'adc_transfers': {'flash': transfer},
                'measures': {'count': measure('code_count', '1'),
                             'dnl': measure('max_abs_dnl_lsb', '1'),
                             'inl': measure('max_abs_inl_lsb', '1'),
                             'threshold': measure('threshold_v', 'V') | {'index': 3},
                             'uncertainty': measure('threshold_uncertainty_v', 'V')}}
    observed = measure_waveform(samples, settings)
    assert observed['count'].value == len(codes)
    assert observed['threshold'].value == pytest.approx(-.04)
    assert observed['dnl'].value == pytest.approx(.1)
    assert observed['inl'].value == pytest.approx(.1)
    assert observed['uncertainty'].value == pytest.approx(.06)

    skipped = {key: values.copy() for key, values in samples.items()}
    for bit in range(3):
        skipped[f'b{bit}'][6:9] = [float((4 >> bit) & 1)]*3
    with pytest.raises(ValueError, match='missing or nonmonotonic code'):
        measure_waveform(skipped, settings)
    unstable = {key: values.copy() for key, values in samples.items()}
    unstable['b0'][10] = .5
    with pytest.raises(ValueError, match='not stable'):
        measure_waveform(unstable, settings)
    with pytest.raises(ValueError, match='unit mismatch'):
        measure_waveform(samples, settings | {'measures': {'dnl': measure('max_abs_dnl_lsb', 'V')}})

    # The original Ethernet flash decoder uses signed three-bit output:
    # raw 101, 110, 111, 000, 001, 010, 011 means -3 through +3.
    signed_codes = list(range(-3, 4))
    signed_samples = {key: values.copy() for key, values in samples.items()}
    for bit in range(3):
        signed_samples[f'b{bit}'] = [float(((signed_codes[t//3] & 7) >> bit) & 1)
                                       for t in times]
    signed_transfer = transfer | {'encoding': 'twos_complement',
                                  'codes': signed_codes}
    signed_settings = settings | {'adc_transfers': {'flash': signed_transfer}}
    signed_observed = measure_waveform(signed_samples, signed_settings)
    assert signed_observed['count'].value == 7
    assert signed_observed['threshold'].value == pytest.approx(-.04)
    assert signed_observed['dnl'].value == pytest.approx(.1)
    assert signed_observed['inl'].value == pytest.approx(.1)
    with pytest.raises(ValueError, match='endpoint codes'):
        measure_waveform(signed_samples, settings)
    with pytest.raises(ValueError, match='Invalid sampled ADC transfer'):
        measure_waveform(signed_samples, signed_settings | {'adc_transfers': {
            'flash': signed_transfer | {'codes': list(range(-3, 5))}}})
    with pytest.raises(ValueError, match='Invalid sampled ADC transfer'):
        measure_waveform(signed_samples, signed_settings | {'adc_transfers': {
            'flash': signed_transfer | {'encoding': []}}})


@pytest.mark.parametrize('worker_exit', [0, 7])
def test_batch_launcher_waits_for_orphaned_worker_and_propagates_failure(tmp_path, worker_exit):
    # Reproduce a batch tool that exits before its extraction worker. Completion
    # is independently observed through the worker's file and exit status.
    import subprocess
    import sys
    from pathlib import Path

    import benchmarking.engine.container_scripts.wait_process_tree as waiter

    marker = tmp_path / 'worker-finished'
    worker = (f'import time,pathlib,sys; time.sleep(0.05); '
              f'pathlib.Path({str(marker)!r}).write_text("finished"); sys.exit({worker_exit})')
    launcher = f'import subprocess,sys; subprocess.Popen([sys.executable, "-c", {worker!r}])'
    result = subprocess.run([sys.executable, str(Path(waiter.__file__)), sys.executable,
                             '-c', launcher], timeout=10, check=False)
    assert marker.read_text() == 'finished'
    assert result.returncode == worker_exit


def test_quantus_identity_survives_timestamped_startup_diagnostics(monkeypatch):
    from types import SimpleNamespace

    from benchmarking.engine.external import ExternalRuntime

    runtime = ExternalRuntime('operator', {'image': 'operator', 'environment': {}, 'mounts': []})
    serial = iter(range(4))

    def tool(image, command, timeout, runtime):
        version = (f'Runtime warning at time {next(serial)}\nVersion : release\n'
                   'Build Ref. No. : build\nBuild Date : fixed-build-date\n')
        return SimpleNamespace(version=version, identity={'tool_version': 'PVS release'})

    monkeypatch.setattr('benchmarking.engine.backends.pvs.DockerTool', tool)
    first = PvsDocker(runtime=runtime, check='rc').identity
    second = PvsDocker(runtime=runtime, check='rc').identity
    assert first == second


def test_dspf_interface_continuations_and_junctions_preserve_rc():
    # Synthetic DSPF tests ordered pin binding and model-call adaptation only.
    # A continued port was previously dropped; missing junctions must not default.
    from benchmarking.engine.netlists.dspf import adapt_dspf

    raw = '.SUBCKT demo b\n+ a\nM1 d g s b mos L=1e-6 W=2e-6\n+ AS=1e-12 AD=2e-12 PS=3e-6 PD=4e-6 fw=2e-6\nR1 a d 12\nC1 b g 1e-15\n.ENDS\n'
    adapted = adapt_dspf(raw, 'demo', ['a', 'b'], {'mos': 'wrapped'}, True)
    assert adapted.startswith('.SUBCKT demo a b\n')
    assert 'XM1 d g s b wrapped L=1e-6 W=2e-6 AS=1e-12 AD=2e-12 PS=3e-6 PD=4e-6' in adapted
    assert 'R1 a d 12\nC1 b g 1e-15' in adapted
    with pytest.raises(ValueError, match='geometry'):
        adapt_dspf(raw.replace('AS=1e-12 ', ''), 'demo', ['a', 'b'], {'mos': 'wrapped'}, True)
    with pytest.raises(ValueError, match='interface'):
        adapt_dspf(raw, 'demo', ['a', 'wrong'], {'mos': 'wrapped'}, True)
    cap = '\nMcap b g b b moscap L=1e-6 W=2e-6\n'
    mapped = {'mos': 'wrapped', 'moscap': 'cap_wrapper'}
    with pytest.raises(ValueError, match='geometry'):
        adapt_dspf(raw + cap, 'demo', ['a', 'b'], mapped, True)
    assert 'XMcap b g b b cap_wrapper' in adapt_dspf(
        raw + cap, 'demo', ['a', 'b'], mapped, True, junctionless_models=['moscap'])
    with pytest.raises(ValueError, match='geometry'):
        adapt_dspf(raw.replace('AS=1e-12 ', '') + cap, 'demo', ['a', 'b'], mapped,
                   True, junctionless_models=['moscap'])


def test_dspf_engineering_units_preserve_native_physical_parameters():
    from benchmarking.engine.netlists.dspf import adapt_dspf

    raw = ('.SUBCKT demo a b\n'
           'X1 d g s b mos L=30n W=0.8u AS=0.1125p AD=0 PS=1.05u PD=0\n'
           'R1 a d 1.2k\nC1 b g 0.5f\n.ENDS demo\n')
    assert adapt_dspf(raw, 'demo', ['a', 'b'], {}, True,
                      subcircuit_mos_models=['mos']) == raw
    for invalid in ('-0.1p', '1e999p', '0.1bogus', '{area}'):
        with pytest.raises(ValueError):
            adapt_dspf(raw.replace('0.1125p', invalid), 'demo', ['a', 'b'], {}, True,
                       subcircuit_mos_models=['mos'])
    for invalid in ('0u', '-30n', '1e999n'):
        with pytest.raises(ValueError, match='geometry'):
            adapt_dspf(raw.replace('30n', invalid), 'demo', ['a', 'b'], {}, True,
                       subcircuit_mos_models=['mos'])


def test_rejected_dspf_retains_native_diagnostic_evidence(monkeypatch):
    # Missing junctions are rejected after native extraction succeeds. Previously
    # the adapter exception discarded the DSPF and logs needed to audit that
    # rejection. Synthetic tool output tests evidence retention, not extraction.
    from types import SimpleNamespace

    report = ('Top Cell : demo <vs> demo\nRun Result : MATCH\nExtraction Clean\n'
              'Cells matched | 1\nCells not run | 0\nCells which mismatch | 0\n'
              'Cells with parameter mismatches | 0\n'
              'Cells with mismatched instance subtypes | 0\n'
              'Cells that have been blackboxed | 0\nEND OF REPORT\n')
    raw = ('.SUBCKT demo a b\nM1 a a b b mos L=1e-6 W=2e-6\n'
           'R1 a x 12\nC1 x b 1e-15\n.ENDS\n')
    evidence = {'demo.lvsrpt.cls': Asset(report.encode(), 'text'),
                'qrc.log': Asset(b'Quantus terminated normally', 'text'),
                'extracted.dspf': Asset(raw.encode(), 'spice')}
    deck = SimpleNamespace(read_text=lambda: 'rule deck')
    backend = object.__new__(PvsDocker)
    backend.runtime = SimpleNamespace(module_setup=lambda _: '', pdk_file=lambda name: (deck, '/pdk/deck'))
    backend.check = 'rc'
    backend.settings = {'lvs_deck': 'lvs', 'lvs_includes': {}, 'qrc_technology': 'rcx',
                        'mos_models': {'mos': 'wrapped'}, 'require_junctions': True,
                        'resistor_models': {}, 'bipolar_models': {}}
    backend.tool = SimpleNamespace(run=lambda *args: ToolResult(0, '', evidence, {}))
    job = parse_evaluation(b'''mode="characterization"
metrics=[]
[[jobs]]
id="rc"
stage="extract"
operation="layout.extract_rc"
inputs={layout="input:layout",task="input:task",netlist="input:netlist"}
outputs={netlist="spice"}
parameters.ports=["a","b"]
''').jobs[0]
    result = backend.run(job, {
        'layout': Asset(b'not interpreted by fake tool', 'gds'),
        'task': Asset(b'{"output":{"top_cell":"demo"},"netlist_subcircuit":"demo"}', 'json'),
        'netlist': Asset(b'.subckt demo a b\n.ends', 'spice')})
    assert result.status == 'error'
    assert 'missing required geometry' in result.reason
    assert not result.outputs
    assert result.evidence == evidence


def test_transient_settling_uses_last_band_entry_and_frozen_reference_window():
    # Piecewise-linear analytical trace: first entry at 1.9 s, later excursion,
    # final band entry at 3.5 s. Trigger crosses 0.5 V at 0.5 s, so delay is 3 s.
    # This catches a first-crossing measurement falsely accepting ringing.
    from benchmarking.engine.backends.spectre import transient_measurements

    settings = {'positive': 'p', 'negative': 'n', 'trigger': 'clk',
                'trigger_threshold': .5, 'edge_index': 1,
                'reference_start_s': 4., 'reference_stop_s': 5.,
                'tolerance_v': .1, 'max_step_s': 1.}
    samples = {'time': [0., 1., 2., 3., 4., 5.], 'p': [0., 0., 1., 1.2, 1., 1.],
               'n': [0.]*6, 'clk': [0., 1., 1., 1., 1., 1.]}
    result = transient_measurements(samples, settings)
    assert result['settling_s'].value == pytest.approx(3.)
    assert result['final_v'].value == pytest.approx(1.)
    with pytest.raises(ValueError, match='sparse'):
        transient_measurements(samples, settings | {'max_step_s': .5})
    with pytest.raises(ValueError, match='edge'):
        transient_measurements(samples, settings | {'edge_index': 2})


def test_spectre_named_transients_share_run_and_reject_missing_edge():
    # Two analytical ramps settle at 1.9 and 4.9 s; trigger crossings are
    # at .5 and 3.5 s, hence both settling times are 1.4 s.
    samples = {'time': list(range(7)), 'p': [0, 0, 1, 1, 1, 0, 0],
               'n': [0]*7, 'rise': [0, 1, 1, 1, 1, 1, 1],
               'fall': [0, 0, 0, 0, 1, 1, 1]}
    psf = 'VALUE\n' + ''.join(
        ''.join(f'"{name}" {values[i]}\n' for name, values in samples.items())
        for i in range(7)) + 'END\n'
    backend = object.__new__(SpectreDocker)
    backend.runtime = SimpleNamespace(pdk_file=lambda name: (None, '/pdk/model'))
    backend.model, backend.section = 'models', 'tt'
    runs = []

    def run(command, files, exports):
        runs.append(command)
        return ToolResult(0, '', {name: Asset(content.encode(), 'text')
                                 for name, content in {
            'spectre.log': 'spectre completes with 0 errors',
            'results/tran.tran.tran': psf}.items()}, {})

    backend.tool = SimpleNamespace(run=run)
    job = parse_evaluation(b'''mode="characterization"
metrics=[]
[[jobs]]
id="step"
stage="simulate"
operation="circuit.simulate"
inputs={deck="input:deck",dut="input:dut"}
parameters.measurements={rise_settling_s="s",fall_settling_s="s",fall_final_v="V"}
''').jobs[0]
    profile = {'positive': 'p', 'negative': 'n', 'trigger': 'rise',
               'trigger_threshold': .5, 'edge_index': 1,
               'reference_start_s': 2., 'reference_stop_s': 3.,
               'tolerance_v': .1, 'max_step_s': 1.}
    profiles = {'rise': profile, 'fall': profile | {
        'trigger': 'fall', 'reference_start_s': 5., 'reference_stop_s': 6.}}
    parameters = job.parameters | {'transients': profiles}
    inputs = {name: Asset(b'fixture', 'spice') for name in ('deck', 'dut')}
    result = backend.run(replace(job, parameters_json=json.dumps(parameters)), inputs)
    assert result.status == 'passed'
    assert len(runs) == 1  # Named events explicitly share a simulator execution.
    assert result.measurements['rise_settling_s'].value == pytest.approx(1.4)
    assert result.measurements['fall_settling_s'].value == pytest.approx(1.4)
    assert result.measurements['fall_final_v'].value == pytest.approx(0.)
    profiles['fall']['edge_index'] = 2
    parameters['measurements'] = {'rise_settling_s': 's'}
    failed = backend.run(replace(job, parameters_json=json.dumps(parameters)), inputs)
    assert failed.status == 'error' and 'edge' in failed.reason
    assert 'results/tran.tran.tran' in failed.evidence
    for invalid in ({}, {'bad:name': profile}, {'rise': []}):
        with pytest.raises(ValueError, match='named transient'):
            backend.run(replace(job, parameters_json=json.dumps(
                parameters | {'transients': invalid})), inputs)


@pytest.mark.parametrize('with_mos', [True, False])
def test_modeled_resistor_retains_geometry_and_substrate(with_mos):
    # A physical process resistor must not become a temperature-independent
    # number. Interconnect resistance remains a numeric extracted element.
    from benchmarking.engine.netlists.dspf import adapt_dspf

    raw = ('.SUBCKT demo a b\nM1 a a b b mos L=1e-6 W=2e-6\n'
           'Rdev a b poly 1997 L=9.985e-6 W=2e-6 $SUB=b\n'
           'Rwire a x 12\nC1 x b 1e-15\n.ENDS\n')
    # A passive DUT has no MOS. Model-bound geometry still identifies its
    # physical devices; a parasitic-only RC fragment must not qualify instead.
    if not with_mos:
        raw = raw.replace('M1 a a b b mos L=1e-6 W=2e-6\n', '')
    args = ('demo', ['a', 'b'], {'mos': 'wrapped'}, False, {'poly': 'poly_wrapper'})
    result = adapt_dspf(raw, *args)
    assert 'XRdev a b b poly_wrapper l=9.985e-6 w=2e-6' in result
    assert 'Rwire a x 12' in result
    assert '1997' not in result
    with pytest.raises(ValueError, match='substrate'):
        adapt_dspf(raw.replace(' $SUB=b', ''), *args)
    with pytest.raises(ValueError, match='Unmapped'):
        adapt_dspf(raw.replace('poly 1997', 'other 1997'), *args)
    with pytest.raises(ValueError, match='geometry'):
        adapt_dspf(raw.replace('W=2e-6 $SUB', 'W=0 $SUB'), *args)
    # A missing operator map must fail even when another physical MOS exists.
    # Numeric device-segment annotations indicate model-flattening; accepting
    # them lets the simulator ignore geometry and silently lose process PVT.
    with pytest.raises(ValueError, match='Unmapped'):
        adapt_dspf(raw, *args[:-1])
    flattened = raw.replace('poly 1997 L=9.985e-6 W=2e-6',
                            '1997 segr=1997 segl=9.985e-6 segw=2e-6 effw=2e-6')
    for mapping in ({}, args[-1]):
        with pytest.raises(ValueError, match='lost its model'):
            adapt_dspf(flattened, *args[:-1], mapping)
    if not with_mos:
        with pytest.raises(ValueError, match='physical devices'):
            adapt_dspf(raw.replace('Rdev a b poly 1997 L=9.985e-6 W=2e-6 $SUB=b\n', ''), *args)


def test_waveform_endpoint_roundoff_does_not_hide_truncation():
    from benchmarking.engine.measurements.waveform import measure_waveform

    settings = {'max_step_s': .5, 'traces': {'x': {'terms': {'x': 1}}},
                'measures': {'peak': {'operation': 'max', 'trace': 'x',
                            'start_s': 0, 'stop_s': math.nextafter(1., math.inf), 'unit': 'V'}}}
    samples = {'time': [0., .5, 1.], 'x': [0., .5, 1.]}
    assert measure_waveform(samples, settings)['peak'].value == 1.
    with pytest.raises(ValueError, match='outside'):
        measure_waveform(samples | {'time': [0., .5, .999]}, settings)
    # A simulator accumulates timesteps; its last decimal timestamp can be
    # thousands of ULPs short even though every requested step completed.
    step, count = 1e-10, 40000
    times = [0.]
    for _ in range(count):
        times.append(times[-1] + step)
    end = count * step
    settings['max_step_s'] = step
    settings['measures']['peak']['stop_s'] = end
    samples = {'time': times, 'x': [1.] * len(times)}
    assert measure_waveform(samples, settings)['peak'].value == 1.
    with pytest.raises(ValueError, match='outside'):
        measure_waveform({k: v[:-1] for k, v in samples.items()}, settings)


def test_duty_cycle_uses_complete_periods_and_bounds_each_cycle():
    # Piecewise-linear crossings: rises at 1,5,9 s; falls at 2,8 s.
    # Independent high-time/period ratios are 1/4 and 3/4. A mean of 1/2
    # must not hide either extreme, and a threshold-touching glitch must fail.
    from benchmarking.engine.measurements.waveform import measure_waveform

    signal = [-1, -1, 0, 1, 0, -1, -1, -1, -1, -1, 0, 1, 1, 1, 1, 1, 0, -1, 0, 1, 1]
    samples = {'time': [i/2 for i in range(len(signal))], 'x': signal}
    spec = {'operation': 'duty_cycle', 'start_s': 0, 'stop_s': 10, 'unit': '1',
            'trace': 'x', 'threshold': 0, 'min_cycles': 2}
    settings = {'max_step_s': .5, 'traces': {'x': {'terms': {'x': 1}}},
                'measures': {key: spec | {'aggregation': key} for key in ['min', 'max', 'mean']}}
    result = measure_waveform(samples, settings)
    assert result['min'].value == pytest.approx(1/4)
    assert result['max'].value == pytest.approx(3/4)
    assert result['mean'].value == pytest.approx(1/2)
    glitch = signal.copy()
    glitch[12] = 0
    with pytest.raises(ValueError, match='missing or ambiguous'):
        measure_waveform(samples | {'x': glitch}, settings)
    with pytest.raises(ValueError, match='Too few complete'):
        measure_waveform(samples | {'x': [1]*len(signal)}, settings)
    with pytest.raises(ValueError, match='Too few complete'):
        measure_waveform(samples, settings | {'measures': {
            'duty': spec | {'aggregation': 'min', 'min_cycles': 3}}})


def test_periodic_measurements_bound_cycles_and_compare_windows():
    # Analytical rising crossings at 1,3,7,11 s give 1/2,1/4,1/4 Hz.
    # Unequal peaks/troughs expose averaging that conceals a weak cycle.
    from benchmarking.engine.measurements.waveform import measure_waveform

    samples = {'time': [0, 1, 1.5, 2, 2.5, 3, 4, 5, 6, 7, 8, 9, 10, 11],
               'x': [-1, 0, 2, 0, -1, 0, 1, 0, -1, 0, 3, 0, -2, 0]}
    spec = {'operation': 'frequency', 'start_s': 0, 'stop_s': 11, 'unit': 'Hz',
            'trace': 'x', 'threshold': 0, 'min_cycles': 3, 'aggregation': 'mean'}
    settings = {'max_step_s': 1, 'traces': {'x': {'terms': {'x': 1}}},
                'measures': {'frequency': spec}}
    assert measure_waveform(samples, settings)['frequency'].value == pytest.approx(1/3)
    for aggregation, expected in [('min', 1/4), ('max', 1/2)]:
        settings['measures'] = {'f': spec | {'aggregation': aggregation}}
        assert measure_waveform(samples, settings)['f'].value == pytest.approx(expected)
    for statistic, aggregation, expected in [('max', 'min', 1), ('min', 'max', -1)]:
        settings['measures'] = {'rail': spec | {'operation': 'cycle_extrema', 'unit': 'V',
                                'statistic': statistic, 'aggregation': aggregation}}
        assert measure_waveform(samples, settings)['rail'].value == expected
    compare = {key: value for key, value in spec.items() if key != 'aggregation'}
    compare |= {'start_s': 2.5, 'min_cycles': 2, 'unit': '1',
                'reference_start_s': 0, 'reference_stop_s': 7}
    for operation, expected in [('frequency_ratio', 2/3), ('frequency_relative_difference', .4)]:
        settings['measures'] = {'comparison': compare | {'operation': operation}}
        assert measure_waveform(samples, settings)['comparison'].value == pytest.approx(expected)
    settings['measures']['comparison']['reference_stop_s'] = 3
    with pytest.raises(ValueError, match='Too few complete'):
        measure_waveform(samples, settings)


def test_bipolar_wrapper_converts_area_units_without_changing_terminals_or_rc():
    # A six-square-micrometre emitter is represented in native square metres.
    # The explicit wrapper mapping converts units; device count/multiplicity,
    # ordered C/B/E terminals and all numeric parasitics must remain unchanged.
    from benchmarking.engine.netlists.dspf import adapt_dspf

    emitter_um2 = 6
    raw = (f'.SUBCKT demo c b e\nQ1 c b e pnp AREA={emitter_um2*1e-12} M=3\n'
           'R1 c x 12\nC1 x b 1e-15\n.ENDS\n')
    mapping = {'pnp': {'model': 'bjt_wrapper', 'area_scale': 1e12}}
    args = ('demo', ['c', 'b', 'e'], {}, False, None)
    result = adapt_dspf(raw, *args, mapping)
    assert f'XQ1 c b e bjt_wrapper area={emitter_um2} M=3' in result
    assert 'R1 c x 12\nC1 x b 1e-15' in result
    with pytest.raises(ValueError, match='Unmapped'):
        adapt_dspf(raw, *args)
    for area in ['0', '-1', 'nan', 'inf']:
        invalid = raw.replace(f'AREA={emitter_um2*1e-12}', f'AREA={area}')
        with pytest.raises(ValueError, match='bipolar area'):
            adapt_dspf(invalid, *args, mapping)
    with pytest.raises(ValueError, match='one explicit area'):
        adapt_dspf(raw.replace(' M=3', ' AREA=1 M=3'), *args, mapping)
    with pytest.raises(ValueError, match='Invalid bipolar model mapping'):
        adapt_dspf(raw, *args, {'pnp': mapping['pnp'] | {'area_scale': 0}})


def test_ac_transfer_measures_attenuation_and_rejects_incomplete_sweeps():
    # H(f)=0.5*f**(-log10(2)); it never crosses unity. Opposite output
    # phases plus a common component require subtraction before magnitude.
    # This analytical oracle protects the new differential AC profile, which
    # the existing single-output/unity-crossing test cannot exercise.
    from benchmarking.engine.measurements.frequency import measure_transfer

    freq = [1, 10, 100]
    gain = [.5, .25, .125]
    ac = {'freq': freq, 'ip': [1j]*3, 'im': [-1j]*3,
          'op': [3+g*1j for g in gain], 'om': [3-g*1j for g in gain]}
    dc = {'op': [.8], 'om': [.6], 'ia': [-.002], 'id': [-.001]}
    settings = {'input': {'terms': {'ip': 1, 'im': -1}},
                'output': {'terms': {'op': 1, 'om': -1}}, 'max_frequency_ratio': 10,
                'measures': {
                    'point': {'operation': 'gain_db', 'frequency_hz': math.sqrt(10), 'unit': 'dB'},
                    'peak': {'operation': 'peak_gain_db', 'start_hz': 1, 'stop_hz': 100, 'unit': 'dB'},
                    'peak_f': {'operation': 'peak_frequency_hz', 'start_hz': 1, 'stop_hz': 100, 'unit': 'Hz'},
                    'boost': {'operation': 'peaking_db', 'start_hz': 1, 'stop_hz': 100,
                              'reference_hz': 1, 'unit': 'dB'},
                    'bw': {'operation': 'bandwidth_hz', 'start_hz': 1, 'stop_hz': 100,
                           'reference_hz': 1, 'relative_db': 20*math.log10(.5), 'unit': 'Hz'},
                    'cm': {'operation': 'dc', 'terms': {'op': .5, 'om': .5}, 'unit': 'V'},
                    'power': {'operation': 'dc', 'terms': {'ia': -2, 'id': -1}, 'unit': 'W'}}}
    measured = measure_transfer(ac, dc, settings)
    assert measured['point'].value == pytest.approx(20*math.log10(math.sqrt(.5*.25)))
    assert measured['peak'].value == pytest.approx(20*math.log10(.5))
    assert measured['peak_f'].value == 1
    assert measured['boost'].value == 0
    assert measured['bw'].value == pytest.approx(10)
    assert measured['cm'].value == pytest.approx(.7)
    assert measured['power'].value == pytest.approx(.005)
    with pytest.raises(ValueError, match='too sparse'):
        measure_transfer(ac, dc, settings | {'max_frequency_ratio': 9})
    with pytest.raises(ValueError, match='Zero AC input'):
        measure_transfer(ac | {'im': ac['ip']}, dc, settings)
    with pytest.raises(ValueError, match='Incomplete'):
        measure_transfer(ac | {'op': ac['op'][:-1]}, dc, settings)
    for changed, message in [({'frequency_hz': 101}, 'outside'), ({'unit': 'Hz'}, 'unit mismatch')]:
        with pytest.raises(ValueError, match=message):
            measure_transfer(ac, dc, settings | {'measures': {'point': settings['measures']['point'] | changed}})
    with pytest.raises(ValueError, match='crossing'):
        measure_transfer(ac, dc, settings | {'measures': {'bw': settings['measures']['bw'] | {'relative_db': -60}}})

    null_ac = ac | {'op': [*ac['op'][:2], 3], 'om': [*ac['om'][:2], 3]}
    point_only = settings | {'measures': {'point': settings['measures']['point']}}
    assert measure_transfer(null_ac, dc, point_only)['point'] == measured['point']
    with pytest.raises(ValueError, match='Zero AC gain'):
        measure_transfer(null_ac, dc, settings)


def test_assura_native_drc_requires_complete_nonempty_run():
    from benchmarking.engine.backends.assura import drc_runset, drc_summary

    # Native Assura summary/avrpt fields; no licensed data or process deck.
    log = ('Translating structure "dut"\nTop Cell is \'dut\'\n'
           'Total  errors: 0 0\n*****  Assura terminated normally  *****\n')
    summary = 'Total cells checked = 1\nTotal rules checked = 42\nEnd of Summary Report\n'
    assert drc_summary(log, summary, 'dut')['status'] == 'passed'
    assert drc_summary(log.replace('errors: 0 0', 'errors: 0 3'), summary, 'dut')['status'] == 'failed'
    for bad_log, bad_summary in [(log.replace('Assura terminated normally', ''), summary),
                                 (log, summary.replace('checked = 42', 'checked = 0')),
                                 (log + 'Total errors: 0 0\n', summary),
                                 (log.replace('Top Cell is \'dut\'', ''), summary)]:
        with pytest.raises(ValueError, match='Incomplete'):
            drc_summary(bad_log, bad_summary, 'dut')
    rsf = drc_runset('candidate.gds', 'dut', '/pdk/assura/drc.rul')
    assert '?inputLayout ("GDS2" "candidate.gds")' in rsf
    assert 'blackBox' not in rsf and '?set' not in rsf
    with pytest.raises(ValueError):
        drc_runset('candidate.gds', 'dut', '/pdk/"bad')


def test_assura_lvs_reports_require_agreement_and_complete_run():
    from benchmarking.engine.backends.assura import lvs_runset, lvs_summary

    log = ('Translating structure "dut"\nTop Cell is \'dut\'\n'
           'Assura LVS terminated normally.\nAssura terminated normally\n')
    summary = 'Total cells checked = 1\nTotal rules checked = 42\nEnd of Summary Report\n'
    match = 'Schematic and Layout Match'
    cells = 'dut | dut | matched\n' + match
    assert lvs_summary(log, summary, match, cells, 'dut')['match']
    mismatch = 'Mismatch between Schematic and Layout'
    failed = 'dut | dut | parameter errors      *\n' + mismatch
    assert lvs_summary(log, summary, mismatch, failed, 'dut')['status'] == 'failed'
    for reports in [(log, summary, match, failed),
                    (log.replace('Assura LVS terminated normally.', ''), summary, match, cells),
                    (log, summary.replace('checked = 1', 'checked = 0'), match, cells),
                    (log, summary, '', cells),
                    (log, summary, match, cells.replace('dut', 'other'))]:
        with pytest.raises(ValueError):
            lvs_summary(*reports, 'dut')
    rsf = lvs_runset('candidate.gds', 'source.cdl', 'dut', '/pdk/extract.rul',
                     '/pdk/compare.rul', '/pdk/bind.rul')
    assert 'schematic(netlist(cdl "source.cdl"))' in rsf
    assert 'avLVS()' in rsf
    for path in ['bad"path', 'bad\npath']:
        with pytest.raises(ValueError):
            lvs_runset('candidate.gds', path, 'dut', '/pdk/extract.rul',
                        '/pdk/compare.rul', '/pdk/bind.rul')


def test_assura_rc_keeps_frozen_inputs_and_requires_native_match(monkeypatch):
    # Extend native-report coverage to the new Assura/Quantus boundary. These
    # synthetic reports and DSPF establish fail-closed adaptation, not physics.
    from types import SimpleNamespace

    from benchmarking.engine.backends.assura import AssuraRCDocker

    backend = object.__new__(AssuraRCDocker)
    backend.runtime = SimpleNamespace(module_setup=lambda _: '', pdk_file=lambda name: (None, '/pdk/'+name))
    backend.decks = {'extract_deck': 'extract', 'compare_deck': 'compare', 'binding_deck': 'bind'}
    backend.settings = {'qrc_technology': 'rcx', 'mos_models': {'mos': 'wrapper'},
                        'resistor_models': {}, 'bipolar_models': {}, 'require_junctions': True,
                        'junctionless_models': []}
    native = {
        'assura.log': 'Translating structure "dut"\nTop Cell is \'dut\'\n'
                      'Assura LVS terminated normally.\nAssura terminated normally\n',
        'result.sum': 'Total cells checked = 1\nTotal rules checked = 42\nEnd of Summary Report\n',
        'result.cls': 'Schematic and Layout Match',
        'result.csm': 'dut | dut | matched\nSchematic and Layout Match',
        'qrc.log': 'Quantus terminated normally',
        'extracted.dspf': '.SUBCKT dut b a\nM1 a a b b mos L=1e-6 W=2e-6 '
                          'AS=1e-12 AD=1e-12 PS=1e-6 PD=1e-6\nR1 a b 10\nC1 a b 1e-15\n.ENDS\n',
    }
    inputs = {'layout': Asset(b'frozen layout', 'gds'), 'netlist': Asset(b'frozen circuit', 'spice'),
              'task': Asset(json.dumps({'output': {'top_cell': 'dut'}, 'netlist_subcircuit': 'dut'}).encode(), 'json')}

    class Tool:
        def run(self, command, files, exports):
            assert files['candidate.gds'] == inputs['layout']
            assert files['source.cdl'] == inputs['netlist']
            return ToolResult(0, '', {k: Asset(v.encode(), exports[k]) for k, v in native.items()}, {})

    backend.tool = Tool()
    job = Job('rc', 'extract', 'layout.extract_rc', (), (), (), None,
              json.dumps({'ports': ['a', 'b'], 'temperature_c': 27}))
    passed = backend.run(job, inputs)
    assert passed.status == 'passed'
    assert '.SUBCKT dut a b' in passed.outputs['netlist'].content.decode()
    for evidence in ('result.csm', 'qrc.log'):
        original = native[evidence]
        native[evidence] = 'Incomplete or mismatched run'
        failed = backend.run(job, inputs)
        assert failed.status == 'error' and not failed.outputs
        assert 'extracted.dspf' in failed.evidence
        native[evidence] = original
