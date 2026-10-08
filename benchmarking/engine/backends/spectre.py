"""Spectre execution, PSF parsing and native measurement profiles."""

import bisect
import json
import math
import re
from dataclasses import replace
from itertools import pairwise
from pathlib import Path

from benchmarking.files import Asset, keys

from ..contracts import JobResult, Measurement
from ..external import ExternalRuntime
from ..measurements.frequency import measure_transfer
from ..measurements.waveform import measure_waveform
from ..source import package_source
from ..tools.docker import DockerTool


def psf_ascii(raw):
    """Read scalar/complex PSF ASCII samples, never evaluate simulator text as code."""
    decoded = raw.decode()
    if not decoded.rstrip().endswith('END') or decoded.count('VALUE\n') != 1:
        raise ValueError('Incomplete PSF ASCII data')
    text = decoded.split('VALUE\n', 1)[1]
    result = {}
    for line in text.splitlines():
        match = re.fullmatch(r'"([^"]+)"\s+(?:"[^"]+"\s+)?(\([^)]*\)|[-+0-9.eE]+)(?:\s+PROP\()?\s*', line)
        if not match:
            continue
        name, value = match.groups()
        if value.startswith('('):
            real, imag = map(float, value[1:-1].split())
            parsed = complex(real, imag)
        else:
            parsed = float(value)
        if not math.isfinite(abs(parsed)):
            raise ValueError('Nonfinite Spectre sample')
        result.setdefault(name, []).append(parsed)
    return result


def ac_measurements(ac, dc, settings):
    freq = ac['freq']
    response = ac[settings['output']]
    positive, negative = ac[settings['positive']], ac[settings['negative']]
    if len(freq) < 2 or not (len(freq) == len(response) == len(positive) == len(negative)):
        raise ValueError('Incomplete differential AC sweep')
    gain = [abs(o/(p-n)) for o, p, n in zip(response, positive, negative, strict=True)]
    if any(f <= 0 for f in freq) or any(b <= a for a, b in pairwise(freq)):
        raise ValueError('Spectre frequency sweep is not strictly increasing')

    def crossing(threshold):
        for i in range(1, len(freq)):
            if gain[i] < threshold <= gain[i-1]:
                alpha = math.log(threshold/gain[i-1])/math.log(gain[i]/gain[i-1])
                return freq[i-1]*(freq[i]/freq[i-1])**alpha
        raise ValueError('Required AC crossing is outside the measured sweep')

    transfer = [o/(p-n) for o, p, n in zip(response, positive, negative, strict=True)]
    phases = [math.atan2(v.imag, v.real) for v in transfer]
    for i in range(1, len(phases)):
        while phases[i]-phases[i-1] > math.pi:
            phases[i] -= 2*math.pi
        while phases[i]-phases[i-1] < -math.pi:
            phases[i] += 2*math.pi
    unity = crossing(1)
    i = bisect.bisect_left(freq, unity)
    alpha = math.log(unity/freq[i-1])/math.log(freq[i]/freq[i-1])
    phase = phases[i-1]+alpha*(phases[i]-phases[i-1])
    return {'gain_db': Measurement(20*math.log10(gain[0]), 'dB'),
            'unity_hz': Measurement(unity, 'Hz'),
            'phase_margin_deg': Measurement(180+math.degrees(phase), 'deg'),
            'bandwidth_hz': Measurement(crossing(gain[0]/math.sqrt(2)), 'Hz'),
            'output_v': Measurement(dc[settings['output']][0], 'V'),
            'power_w': Measurement(abs(dc[settings['supply_current']][0])*settings['supply_v'], 'W')}


def transient_measurements(samples, settings):
    """Measure last band entry through a declared window using linear interpolation."""
    keys(settings, {'positive', 'negative', 'trigger', 'trigger_threshold', 'edge_index',
                    'reference_start_s', 'reference_stop_s', 'tolerance_v', 'max_step_s'},
         set(), 'Spectre transient response')
    t = samples['time']
    names = [settings[k] for k in ('positive', 'negative', 'trigger')]
    if len(t) < 3 or any(len(samples[name]) != len(t) for name in names):
        raise ValueError('Incomplete transient samples')
    if any(not isinstance(v, (float, int)) or not math.isfinite(v)
           for name in ['time', *names] for v in samples[name]):
        raise ValueError('Invalid transient samples')
    if any(b <= a or b-a > settings['max_step_s']*(1+1e-6) for a, b in pairwise(t)):
        raise ValueError('Transient time grid is nonmonotonic or too sparse')
    start, stop = settings['reference_start_s'], settings['reference_stop_s']
    tolerance = settings['tolerance_v']
    if not t[0] < start < stop <= t[-1] or not math.isfinite(tolerance) or tolerance <= 0:
        raise ValueError('Invalid transient reference window or tolerance')
    y = [p-n for p, n in zip(samples[names[0]], samples[names[1]], strict=True)]
    clock = samples[names[2]]
    threshold = settings['trigger_threshold']
    edges = [a+(b-a)*(threshold-ca)/(cb-ca)
             for a, b, ca, cb in zip(t[:-1], t[1:], clock[:-1], clock[1:], strict=True)
             if ca < threshold <= cb]
    index = settings['edge_index']
    if type(index) is not int or not 1 <= index <= len(edges):
        raise ValueError('Required trigger edge was not observed')
    edge = edges[index-1]
    if edge >= start:
        raise ValueError('Reference window must follow the trigger')

    def interp(x):
        i = bisect.bisect_left(t, x)
        if i == 0:
            return y[0]
        return y[i-1]+(y[i]-y[i-1])*(x-t[i-1])/(t[i]-t[i-1])

    times = [start, *[v for v in t if start < v < stop], stop]
    final = sum((b-a)*(interp(a)+interp(b))/2 for a, b in pairwise(times))/(stop-start)
    times = [edge, *[v for v in t if edge < v < stop], stop]
    values = [interp(v) for v in times]
    last = edge
    for a, b, va, vb in zip(times[:-1], times[1:], values[:-1], values[1:], strict=True):
        if abs(vb-final) > tolerance:
            last = b
        elif abs(va-final) > tolerance:
            boundary = final + math.copysign(tolerance, va-final)
            last = a+(b-a)*(boundary-va)/(vb-va)
    return {'settling_s': Measurement(last-edge, 's'),
            'final_v': Measurement(final, 'V')}


def _selection_parameters(candidate):
    keys(candidate, {'id', 'parameters'}, set(), 'Spectre parameter selection')
    if type(candidate['id']) is not int or candidate['id'] < 0 or not candidate['parameters']:
        raise ValueError('Invalid Spectre parameter selection')
    declarations = []
    for name, value in sorted(candidate['parameters'].items()):
        if (not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name)
                or type(value) not in (int, float) or not math.isfinite(value)):
            raise ValueError('Selection parameters must have simple names and finite numeric values')
        declarations.append(f'{name}={value!r}')
    return 'simulator lang=spectre\nparameters '+ ' '.join(declarations)+'\n'


class SpectreBackend:
    """Shared model binding, calibration and acceptance for Spectre transports."""

    def __init__(self, *, runtime, model, section, sections=None, model_includes=(),
                 timeout_seconds=300, max_parallel_jobs=1, pdk_root_env=None, module_profile=None):
        if type(max_parallel_jobs) is not int or max_parallel_jobs < 1:
            raise ValueError('Spectre concurrency must be a positive integer')
        self.max_parallel_jobs = max_parallel_jobs
        if not isinstance(runtime, ExternalRuntime):
            raise TypeError('Cadence backend requires a resolved external runtime')
        self.runtime = runtime.select_pdk(pdk_root_env).select_module("spectre", module_profile)
        self.model, self.section = model, section
        self.sections = list(sections) if sections is not None else [section]
        self.model_includes = list(model_includes)
        if (not self.sections or len(self.sections) != len(set(self.sections))
                or any(not isinstance(s, str) or not re.fullmatch(r'[A-Za-z0-9_]+', s) for s in self.sections)):
            raise ValueError('Invalid Spectre model sections')
        self.tool = self._make_tool(timeout_seconds)

    def _make_tool(self, timeout_seconds):
        raise NotImplementedError

    @property
    def identity(self):
        return {'adapter': self.adapter, 'model': self.model, 'section': self.section,
                'sections': self.sections, 'model_includes': self.model_includes,
                'max_parallel_jobs': self.max_parallel_jobs,
                **self.tool.identity, 'adapter_sha256': Asset(Path(__file__).read_bytes(), 'python').sha256,
                'frequency_sha256': Asset(package_source('engine/measurements/frequency.py').read_bytes(), 'python').sha256,
                'waveform_sha256': Asset(package_source('engine/measurements/waveform.py').read_bytes(), 'python').sha256}

    def run(self, job, inputs):
        if 'calibration' in job.parameters:
            return self._calibrate(job, inputs)
        return self._simulate(job, inputs)

    def _calibrate(self, job, inputs):
        keys(inputs, {'deck', 'dut'}, set(), 'Spectre calibration inputs')
        if dict(job.outputs) != {'selection': 'json'}:
            raise ValueError('Calibration must declare a selection JSON output')
        settings = job.parameters.pop('calibration')
        keys(settings, {'candidates', 'target', 'eligibility'}, set(), 'Spectre calibration')
        target = settings['target']
        keys(target, {'measurement', 'unit', 'value'}, set(), 'calibration target')
        requested = job.parameters['measurements']
        if (requested.get(target['measurement']) != target['unit']
                or type(target['value']) not in (int, float) or not math.isfinite(target['value'])):
            raise ValueError('Invalid calibration target')
        bounds = settings['eligibility']
        if not isinstance(bounds, list):
            raise TypeError('Calibration eligibility must be a list')
        for bound in bounds:
            keys(bound, {'measurement', 'unit'}, {'lower', 'upper'}, 'calibration eligibility')
            limits = [bound[k] for k in ('lower', 'upper') if k in bound]
            if (requested.get(bound['measurement']) != bound['unit'] or not limits
                    or any(type(v) not in (int, float) or not math.isfinite(v) for v in limits)
                    or bound.get('lower', -math.inf) > bound.get('upper', math.inf)):
                raise ValueError('Invalid calibration eligibility bounds')
        candidates = settings['candidates']
        seen, parameter_names = set(), None
        for candidate in candidates:
            _selection_parameters(candidate)
            if candidate['id'] in seen:
                raise ValueError('Duplicate calibration candidate')
            seen.add(candidate['id'])
            names = set(candidate['parameters'])
            if parameter_names is not None and names != parameter_names:
                raise ValueError('Calibration candidates must bind the same parameters')
            parameter_names = names
        if not seen:
            raise ValueError('Calibration requires candidates')
        parameters = job.parameters
        del parameters['calibration']
        child = replace(job, outputs=(), parameters_json=json.dumps(parameters, allow_nan=False))
        evidence, rows, eligible = {}, [], []
        for candidate in candidates:
            selection = Asset(json.dumps(candidate, allow_nan=False).encode(), 'json')
            result = self._simulate(child, inputs | {'selection': selection})
            evidence.update({f"candidate-{candidate['id']}/{k}": v for k, v in result.evidence.items()})
            if result.status != 'passed':
                return JobResult('error', f"Calibration candidate {candidate['id']} failed: {result.reason}",
                                 evidence=evidence)
            valid = all(b.get('lower', -math.inf) <= result.measurements[b['measurement']].value
                        <= b.get('upper', math.inf) for b in bounds)
            distance = abs(result.measurements[target['measurement']].value-target['value'])
            rows.append({'candidate': candidate, 'eligible': valid, 'distance': distance,
                         'measurements': {k: {'value': v.value, 'unit': v.unit}
                                          for k, v in result.measurements.items()}})
            if valid:
                eligible.append((distance, candidate['id'], selection, result))
        evidence['calibration.json'] = Asset(json.dumps(rows, allow_nan=False).encode(), 'json')
        if not eligible:
            return JobResult('error', 'No eligible calibration setting', evidence=evidence)
        _, _, selection, result = min(eligible, key=lambda row: (row[0], row[1]))
        return JobResult('passed', measurements=result.measurements,
                         outputs={'selection': selection}, evidence=evidence)

    def _simulate(self, job, inputs):
        keys(inputs, {'deck', 'dut'}, {'selection'}, 'Spectre inputs')
        keys(job.parameters, {'measurements'}, {'response', 'transient', 'transients', 'waveform', 'ac_transfer', 'section'}, 'Spectre parameters')
        if sum(k in job.parameters for k in ('response', 'transient', 'transients', 'waveform', 'ac_transfer')) != 1:
            raise ValueError('Select exactly one Spectre measurement profile')
        if 'transients' in job.parameters:
            profiles = job.parameters['transients']
            if not isinstance(profiles, dict) or not profiles or any(
                    not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', name)
                    or not isinstance(settings, dict) for name, settings in profiles.items()):
                raise ValueError('Spectre transients requires named transient profiles')
        if job.stage != 'simulate' or any(inputs[k].format != 'spice' for k in ('deck', 'dut')):
            raise ValueError('Spectre requires a simulation deck and a circuit')
        _, model = self.runtime.pdk_file(self.model)
        section = job.parameters.get('section', self.section)
        if not re.fullmatch(r'[A-Za-z0-9_]+', section) or '"' in model or '\n' in model:
            raise ValueError('Invalid Spectre model binding')
        files = {'deck.scs': inputs['deck'], 'dut.spice': inputs['dut']}
        if 'selection' in inputs:
            if len(re.findall(r'^\s*include\s+"selection\.scs"\s*(?://[^\n]*)?$',
                              inputs['deck'].content.decode(), re.MULTILINE)) != 1:
                raise ValueError('Selection requires one explicit include "selection.scs" in the deck')
            if inputs['selection'].format != 'json':
                raise ValueError('Spectre selection must be JSON')
            selected = json.loads(inputs['selection'].content)
            files['selection.scs'] = Asset(_selection_parameters(selected).encode(), 'spice')
        sections = [section] if 'section' in job.parameters else getattr(self, 'sections', [section])
        includes = [self.runtime.pdk_file(name)[1] for name in getattr(self, 'model_includes', [])]
        files['models.scs'] = Asset(('simulator lang=spectre\n'+
            ''.join(f'include "{model}" section={s}\n' for s in sections)+
            ''.join(f'include "{name}"\n' for name in includes)).encode(), 'spice')
        exports = ({'spectre.log': 'text', 'results/tran.tran.tran': 'text'}
                   if any(k in job.parameters for k in ('transient', 'transients', 'waveform')) else
                   {'spectre.log': 'text', 'results/ac.ac': 'text', 'results/op.dc': 'text'})
        result = self.tool.run(['spectre', 'deck.scs', '-format', 'psfascii', '-raw', 'results',
                                '+log', 'spectre.log'], files, exports)
        evidence = result.evidence | result.files
        if result.reason or result.returncode:
            return JobResult('error', result.reason or 'Spectre did not complete', evidence=evidence)
        log = result.files['spectre.log'].content.decode(errors='replace')
        if not re.search(r'spectre completes with 0 errors', log):
            return JobResult('error', 'Spectre has no successful completion marker', evidence=evidence)
        try:
            if 'waveform' in job.parameters:
                measurements = measure_waveform(
                    psf_ascii(result.files['results/tran.tran.tran'].content), job.parameters['waveform'])
            elif 'ac_transfer' in job.parameters:
                measurements = measure_transfer(psf_ascii(result.files['results/ac.ac'].content),
                                                psf_ascii(result.files['results/op.dc'].content),
                                                job.parameters['ac_transfer'])
            elif 'transients' in job.parameters:
                samples = psf_ascii(result.files['results/tran.tran.tran'].content)
                measurements = {
                    f'{name}_{metric}': value
                    for name, settings in profiles.items()
                    for metric, value in transient_measurements(samples, settings).items()}
            elif 'transient' in job.parameters:
                measurements = transient_measurements(
                    psf_ascii(result.files['results/tran.tran.tran'].content), job.parameters['transient'])
            else:
                measurements = ac_measurements(psf_ascii(result.files['results/ac.ac'].content),
                                               psf_ascii(result.files['results/op.dc'].content), job.parameters['response'])
        except (ValueError, KeyError) as error:
            return JobResult("error", str(error), evidence=evidence)
        requested = job.parameters['measurements']
        if not requested or any(name not in measurements or measurements[name].unit != unit for name, unit in requested.items()):
            raise ValueError('Unsupported Spectre measurement or unit')
        return JobResult('passed', measurements={name: measurements[name] for name in requested}, evidence=evidence)


class SpectreDocker(SpectreBackend):
    """Classic Spectre using the reviewed evaluator container."""

    adapter = 'spectre-docker'

    def __init__(self, *, memory_mb=4096, **settings):
        self.memory_mb = memory_mb
        super().__init__(**settings)

    def _make_tool(self, timeout_seconds):
        return DockerTool(self.runtime.image, ['spectre', '-W'], timeout_seconds,
                          runtime=self.runtime, memory_mb=self.memory_mb)
