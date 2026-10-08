"""Declarative measurements of finite, sampled real-valued transient traces.

Windows are closed and interpolated at their endpoints. Event pairing uses
independent ordinal crossings, so an early target is a negative delay rather
than silently being replaced with an edge in the next cycle.
"""

import bisect
import math
from itertools import pairwise

from benchmarking.files import keys

from ..contracts import Measurement


def _absolute_segment_area(duration, left, right):
    a, b = abs(left), abs(right)
    if left < 0 < right or right < 0 < left:
        # Split at the interpolated zero; rectifying only the endpoints would
        # overestimate the area of the two triangles.
        fraction = a/(a+b)
        return duration*(a*fraction+b*(1-fraction))/2
    return duration*(a+b)/2


class _Waveform:
    """Validated affine traces with consistent interpolation and closed windows."""

    def __init__(self, samples, settings):
        time = samples['time']
        step = settings['max_step_s']
        if not isinstance(step, (float, int)) or not math.isfinite(step) or step <= 0:
            raise ValueError('Invalid waveform maximum step')
        if (len(time) < 3 or any(not isinstance(t, (float, int)) or not math.isfinite(t) for t in time)
                or any(b <= a or b-a > step*(1+1e-6) for a, b in pairwise(time))):
            raise ValueError('Waveform time grid is incomplete, nonmonotonic or too sparse')
        traces = {}
        for name, spec in settings['traces'].items():
            keys(spec, {'terms'}, {'offset'}, 'waveform trace')
            offset = spec.get('offset', 0)
            if not spec['terms'] or not math.isfinite(offset):
                raise ValueError('Invalid affine waveform trace')
            values = [offset] * len(time)
            for signal, coefficient in spec['terms'].items():
                raw = samples[signal]
                if (not math.isfinite(coefficient) or len(raw) != len(time)
                        or any(not isinstance(v, (float, int)) or not math.isfinite(v) for v in raw)):
                    raise ValueError('Incomplete or nonfinite waveform signal')
                values = [a+coefficient*b for a, b in zip(values, raw, strict=True)]
            if any(not math.isfinite(v) for v in values):
                raise ValueError('Nonfinite affine waveform trace')
            traces[name] = values

        self.time, self.step, self.traces = time, step, traces

    def interpolate(self, values, x):
        i = bisect.bisect_left(self.time, x)
        if i == 0:
            return values[0]
        return values[i-1]+(values[i]-values[i-1])*(x-self.time[i-1])/(self.time[i]-self.time[i-1])

    def window(self, name, start, stop):
        # Repeated timestep addition accumulates roundoff beyond a single ULP.
        # Bound that accumulation by one ULP per sample, capped at a millionth
        # of the declared maximum step; missing analysis intervals still fail.
        if abs(start-self.time[0]) <= 8*math.ulp(self.time[0]):
            start = self.time[0]
        tolerance = max(8*math.ulp(self.time[-1]), min(len(self.time)*math.ulp(self.time[-1]), self.step*1e-6))
        if abs(stop-self.time[-1]) <= tolerance:
            stop = self.time[-1]
        if not self.time[0] <= start < stop <= self.time[-1]:
            raise ValueError('Waveform window is outside the completed analysis')
        tt = [start, *self.time[bisect.bisect_right(self.time, start):bisect.bisect_left(self.time, stop)], stop]
        return tt, [self.interpolate(self.traces[name], t) for t in tt]

    def crossings(self, event, start, stop):
        keys(event, {'trace', 'direction'}, {'threshold', 'threshold_fraction'}, 'waveform event')
        if ('threshold' in event) == ('threshold_fraction' in event):
            raise ValueError('Waveform event requires exactly one threshold definition')
        tt, yy = self.window(event['trace'], start, stop)
        if 'threshold_fraction' in event:
            fraction = event['threshold_fraction']
            if type(fraction) not in (int, float) or not math.isfinite(fraction) or not 0 < fraction < 1:
                raise ValueError('Waveform threshold fraction must be between zero and one')
            low, high = min(yy), max(yy)
            if low == high:
                raise ValueError('Relative waveform threshold requires nonconstant signal')
            threshold = (1-fraction)*low + fraction*high
        else:
            threshold = event['threshold']
        direction = event['direction']
        if type(threshold) not in (int, float) or not math.isfinite(threshold) or direction not in {'rise', 'fall'}:
            raise ValueError('Invalid waveform event')
        return [a+(b-a)*(threshold-va)/(vb-va)
                for a, b, va, vb in zip(tt[:-1], tt[1:], yy[:-1], yy[1:], strict=True)
                if (va < threshold <= vb if direction == 'rise' else va > threshold >= vb)]

    def mean(self, trace, start, stop):
        tt, yy = self.window(trace, start, stop)
        return sum((b-a)*(va+vb)/2 for a, b, va, vb in
                   zip(tt[:-1], tt[1:], yy[:-1], yy[1:], strict=True))/(stop-start)

    def complete_cycles(self, trace, threshold, start, stop, minimum):
        if type(minimum) is not int or minimum < 1:
            raise ValueError('Minimum complete cycle count must be a positive integer')
        event = {'trace': trace, 'threshold': threshold, 'direction': 'rise'}
        rises = self.crossings(event, start, stop)
        falls = self.crossings(event | {'direction': 'fall'}, start, stop)
        if len(rises)-1 < minimum:
            raise ValueError('Too few complete waveform cycles')
        cycles = []
        for a, b in pairwise(rises):
            inside = falls[bisect.bisect_right(falls, a):bisect.bisect_left(falls, b)]
            if len(inside) != 1:
                raise ValueError('Required cycle falling edge is missing or ambiguous')
            cycles.append((a, inside[0], b))
        return cycles


def _adc_transfer(waveform, spec):
    """Decode settled clocked samples before estimating a stepped transfer."""
    keys(spec, {'input_trace', 'bit_traces', 'logic_low_v', 'logic_high_v',
                'codes', 'windows_s', 'full_scale_low_v', 'full_scale_high_v',
                'max_input_ripple_v'}, {'encoding'}, 'sampled ADC transfer')
    bits, expected = spec['bit_traces'], spec['codes']
    encoding = spec.get('encoding', 'unsigned')
    low, high = spec['logic_low_v'], spec['logic_high_v']
    vlow, vhigh = spec['full_scale_low_v'], spec['full_scale_high_v']
    ripple = spec['max_input_ripple_v']
    if (not isinstance(bits, list) or not bits
            or any(not isinstance(bit, str) for bit in bits)
            or len(set(bits)) != len(bits)
            or not isinstance(expected, list) or len(expected) < 2
            or any(type(code) is not int for code in expected)
            or not isinstance(encoding, str)
            or encoding not in {'unsigned', 'twos_complement'}
            or (expected[0] < (0 if encoding == 'unsigned' else -2**(len(bits)-1)))
            or (expected[-1] >= (2**len(bits) if encoding == 'unsigned'
                                 else 2**(len(bits)-1)))
            or any(b != a+1 for a, b in pairwise(expected))
            or any(type(value) not in (int, float) or not math.isfinite(value)
                   for value in (low, high, vlow, vhigh, ripple))
            or not low < high or not vlow < vhigh or ripple < 0):
        raise ValueError('Invalid sampled ADC transfer definition')
    windows = spec['windows_s']
    if not isinstance(windows, list) or len(windows) < len(expected):
        raise ValueError('Too few sampled ADC windows')
    levels, codes = [], []
    previous_stop = -math.inf
    for bounds in windows:
        if (not isinstance(bounds, list) or len(bounds) != 2
                or any(type(value) not in (int, float) or not math.isfinite(value)
                       for value in bounds)):
            raise ValueError('Invalid sampled ADC window')
        start, stop = bounds
        if start < previous_stop:
            raise ValueError('Sampled ADC windows overlap or are out of order')
        previous_stop = stop
        _, yy = waveform.window(spec['input_trace'], start, stop)
        if max(yy)-min(yy) > ripple:
            raise ValueError('ADC input did not settle in a sample window')
        level = waveform.mean(spec['input_trace'], start, stop)
        if not vlow <= level <= vhigh or (levels and level <= levels[-1]):
            raise ValueError('ADC sample levels are outside full scale or nonmonotonic')
        levels.append(level)
        code = 0
        for index, trace in enumerate(bits):
            _, yy = waveform.window(trace, start, stop)
            if max(yy) <= low:
                continue
            if min(yy) >= high:
                code |= 1 << index
            else:
                raise ValueError('ADC output bit is not stable at a valid rail')
        if encoding == 'twos_complement' and code >= 2**(len(bits)-1):
            code -= 2**len(bits)
        codes.append(code)
    if codes[0] != expected[0] or codes[-1] != expected[-1]:
        raise ValueError('ADC transfer does not cover both endpoint codes')
    transitions, uncertainty = [], []
    for index in range(1, len(codes)):
        delta = codes[index]-codes[index-1]
        if delta not in (0, 1):
            raise ValueError('ADC transfer has a missing or nonmonotonic code')
        if delta:
            transitions.append((levels[index-1]+levels[index])/2)
            uncertainty.append((levels[index]-levels[index-1])/2)
    if len(transitions) != len(expected)-1:
        raise ValueError('ADC transfer does not cover every declared code')
    lsb = (vhigh-vlow)/len(expected)
    if not math.isfinite(lsb) or lsb <= 0:
        raise ValueError('Invalid sampled ADC full-scale interval')
    widths = [b-a for a, b in pairwise([vlow, *transitions, vhigh])]
    if any(width <= 0 for width in widths):
        raise ValueError('ADC transfer has a nonpositive code width')
    return {'code_count': len(expected),
            'thresholds_v': transitions,
            'threshold_uncertainty_v': max(uncertainty),
            'dnl_lsb': [width/lsb-1 for width in widths],
            'inl_lsb': [(value-(vlow+index*lsb))/lsb
                        for index, value in enumerate(transitions, 1)]}


def _adc_spectra(waveform, specifications):
    spectra = {}
    for name, spec in specifications.items():
        keys(spec, {'bits_lsb_first', 'threshold_v', 'sample_start_s', 'sample_period_s',
                    'sample_count', 'fundamental_bin'}, set(), 'coherent ADC spectrum')
        bits = spec['bits_lsb_first']
        count, fundamental = spec['sample_count'], spec['fundamental_bin']
        start, period, threshold = (spec[k] for k in ('sample_start_s', 'sample_period_s', 'threshold_v'))
        if (not isinstance(bits, list) or not bits or len(bits) != len(set(bits))
                or any(b not in waveform.traces for b in bits)
                or type(count) is not int or count < 8 or count > 4096 or count % 2
                or type(fundamental) is not int or not 0 < fundamental < count//2
                or not all(type(v) in (int, float) and math.isfinite(v) for v in (start, period, threshold))
                or period <= 0 or not waveform.time[0] <= start < start+(count-1)*period <= waveform.time[-1]):
            raise ValueError('Invalid coherent ADC sampling definition')
        codes, margins = [], []
        for i in range(count):
            levels = [waveform.interpolate(waveform.traces[b], start+i*period) for b in bits]
            codes.append(sum(1 << j for j, v in enumerate(levels) if v > threshold))
            margins.extend(abs(v-threshold) for v in levels)
        dc = sum(codes)/count
        centered = [v-dc for v in codes]
        powers = []
        for k in range(1, count//2+1):
            real = sum(v*math.cos(2*math.pi*k*i/count) for i, v in enumerate(centered))
            imag = sum(v*math.sin(2*math.pi*k*i/count) for i, v in enumerate(centered))
            powers.append((real*real+imag*imag)*(1 if k == count//2 else 2)/count**2)
        signal = powers[fundamental-1]
        other = powers[:fundamental-1]+powers[fundamental:]
        if signal <= 0 or sum(other) <= 0 or max(other) <= 0:
            raise ValueError('ADC spectrum lacks finite signal or distortion power')
        sndr = 10*math.log10(signal/sum(other))
        spectra[name] = {'sndr': (sndr, 'dB'), 'sfdr': (10*math.log10(signal/max(other)), 'dB'),
                         'enob': ((sndr-1.76)/6.02, '1'),
                         'code_span': (max(codes)-min(codes), '1'),
                         'logic_margin': (min(margins), 'V')}

    return spectra


def measure_waveform(samples, settings):
    keys(settings, {'max_step_s', 'traces', 'measures'}, {'adc_transfers', 'adc_spectra'}, 'waveform settings')
    waveform = _Waveform(samples, settings)
    transfers = {name: _adc_transfer(waveform, spec)
                 for name, spec in settings.get('adc_transfers', {}).items()}
    spectra = _adc_spectra(waveform, settings.get('adc_spectra', {}))
    results = {}
    for name, spec in settings['measures'].items():
        common = {'operation', 'start_s', 'stop_s', 'unit'}
        operation = spec['operation']
        if operation == 'adc_spectrum':
            keys(spec, {'operation', 'spectrum', 'statistic', 'unit'}, set(), 'ADC spectrum measurement')
            value, unit = spectra[spec['spectrum']][spec['statistic']]
            if unit != spec['unit'] or not math.isfinite(value):
                raise ValueError('Invalid ADC spectrum unit or nonfinite measurement')
            results[name] = Measurement(value, unit)
            continue
        if operation == 'adc_transfer':
            keys(spec, {'operation', 'transfer', 'statistic', 'unit'}, {'index'},
                 'sampled ADC measurement')
            transfer = transfers[spec['transfer']]
            statistic = spec['statistic']
            scalar = {'code_count': ('1', transfer['code_count']),
                      'threshold_uncertainty_v': ('V', transfer['threshold_uncertainty_v']),
                      'max_abs_dnl_lsb': ('1', max(map(abs, transfer['dnl_lsb']))),
                      'max_abs_inl_lsb': ('1', max(map(abs, transfer['inl_lsb'])))}
            indexed = {'threshold_v': ('V', transfer['thresholds_v']),
                       'dnl_lsb': ('1', transfer['dnl_lsb']),
                       'inl_lsb': ('1', transfer['inl_lsb'])}
            if statistic in scalar and 'index' not in spec:
                unit, value = scalar[statistic]
            elif statistic in indexed:
                unit, values = indexed[statistic]
                index = spec.get('index')
                if type(index) is not int or not 1 <= index <= len(values):
                    raise ValueError('Invalid sampled ADC measurement index')
                value = values[index-1]
            else:
                raise ValueError('Invalid sampled ADC measurement statistic')
            if spec['unit'] != unit:
                raise ValueError('Sampled ADC measurement unit mismatch')
            if not math.isfinite(value):
                raise ValueError('Nonfinite sampled ADC measurement')
            results[name] = Measurement(value, unit)
            continue
        start, stop = spec['start_s'], spec['stop_s']
        if operation in {'mean', 'min', 'max', 'rms', 'integral', 'abs_integral', 'span', 'absmax'}:
            keys(spec, common | {'trace'}, set(), 'waveform statistic')
            tt, yy = waveform.window(spec['trace'], start, stop)
            integral = sum((b-a)*(va+vb)/2 for a, b, va, vb in
                           zip(tt[:-1], tt[1:], yy[:-1], yy[1:], strict=True))
            # Exact integral of the square of each linearly interpolated segment.
            square = sum((b-a)*(va*va+va*vb+vb*vb)/3 for a, b, va, vb in
                         zip(tt[:-1], tt[1:], yy[:-1], yy[1:], strict=True))
            absolute = (sum(_absolute_segment_area(b-a, va, vb) for a, b, va, vb in
                            zip(tt[:-1], tt[1:], yy[:-1], yy[1:], strict=True))
                        if operation == 'abs_integral' else None)
            value = {'mean': integral/(stop-start), 'min': min(yy), 'max': max(yy),
                     'rms': math.sqrt(square/(stop-start)), 'integral': integral,
                     'abs_integral': absolute,
                     'span': max(yy)-min(yy), 'absmax': max(map(abs, yy))}[operation]
        elif operation == 'mean_difference':
            keys(spec, common | {'trace', 'reference_start_s', 'reference_stop_s'}, set(),
                 'waveform mean difference')

            value = (waveform.mean(spec['trace'], start, stop)
                     - waveform.mean(spec['trace'], spec['reference_start_s'], spec['reference_stop_s']))
        elif operation == 'phase_difference':
            keys(spec, common | {'event', 'reference_event', 'min_edges', 'statistic'}, set(),
                 'clock phase measurement')
            if (spec['unit'] != 's' or type(spec['min_edges']) is not int or spec['min_edges'] < 2
                    or spec['statistic'] not in {'std', 'span'}):
                raise ValueError('Invalid clock phase measurement')
            edges = waveform.crossings(spec['event'], start, stop)
            references = waveform.crossings(spec['reference_event'], start, stop)
            if min(len(edges), len(references)) < spec['min_edges']:
                raise ValueError('Too few clock phase edges')
            # Align once at the beginning. Keeping ordinal pairs preserves
            # accumulated phase drift and cycle slips instead of wrapping them.
            if edges[0] >= references[0]:
                offset = min(range(len(references)), key=lambda i: abs(references[i]-edges[0]))
                references = references[offset:]
            else:
                offset = min(range(len(edges)), key=lambda i: abs(edges[i]-references[0]))
                edges = edges[offset:]
            size = min(len(edges), len(references))
            if size < spec['min_edges']:
                raise ValueError('Too few aligned clock phase edges')
            phases = [a-b for a, b in zip(edges[:size], references[:size], strict=True)]
            average = sum(phases)/size
            value = (max(phases)-min(phases) if spec['statistic'] == 'span' else
                     math.sqrt(sum((p-average)**2 for p in phases)/size))
        elif operation == 'count':
            keys(spec, common | {'event'}, set(), 'waveform crossing count')
            if spec['unit'] != '1':
                raise ValueError('Crossing count requires dimensionless unit')
            value = len(waveform.crossings(spec['event'], start, stop))
        elif operation == 'delay':
            keys(spec, common | {'trigger', 'target', 'pairs', 'aggregation'}, set(), 'waveform delay')
            if spec['unit'] != 's' or spec['aggregation'] not in {'min', 'max'} or not spec['pairs']:
                raise ValueError('Invalid waveform delay definition')
            triggers = waveform.crossings(spec['trigger'], start, stop)
            targets = waveform.crossings(spec['target'], start, stop)
            values = []
            for pair in spec['pairs']:
                if (len(pair) != 2 or any(type(i) is not int or i < 1 for i in pair)
                        or pair[0] > len(triggers) or pair[1] > len(targets)):
                    raise ValueError('Required waveform event pair was not observed')
                values.append(targets[pair[1]-1]-triggers[pair[0]-1])
            value = (min if spec['aggregation'] == 'min' else max)(values)
        elif operation in {'duty_cycle', 'frequency', 'cycle_extrema'}:
            required = common | {'trace', 'threshold', 'aggregation', 'min_cycles'}
            if operation == 'cycle_extrema':
                required.add('statistic')
            keys(spec, required, set(), 'waveform cycle statistic')
            unit = {'duty_cycle': '1', 'frequency': 'Hz'}.get(operation)
            if ((unit is not None and spec['unit'] != unit)
                    or spec['aggregation'] not in {'min', 'max', 'mean'}):
                raise ValueError('Invalid waveform cycle statistic definition')
            cycles = waveform.complete_cycles(spec['trace'], spec['threshold'], start, stop, spec['min_cycles'])
            if operation == 'cycle_extrema':
                if spec['statistic'] not in {'min', 'max'}:
                    raise ValueError('Cycle extrema require min or max statistic')
                statistic = min if spec['statistic'] == 'min' else max
                values = [statistic(waveform.window(spec['trace'], a, b)[1]) for a, _, b in cycles]
            elif operation == 'frequency':
                values = [1/(b-a) for a, _, b in cycles]
            else:
                values = [(fall-a)/(b-a) for a, fall, b in cycles]
            value = {'min': min(values), 'max': max(values),
                     'mean': sum(values)/len(values)}[spec['aggregation']]
        elif operation in {'frequency_ratio', 'frequency_relative_difference'}:
            keys(spec, common | {'trace', 'threshold', 'min_cycles',
                                'reference_start_s', 'reference_stop_s'}, set(),
                 'waveform frequency comparison')
            if spec['unit'] != '1':
                raise ValueError('Frequency comparison requires dimensionless unit')
            frequencies = []
            for left, right in ((start, stop), (spec['reference_start_s'], spec['reference_stop_s'])):
                cycles = waveform.complete_cycles(spec['trace'], spec['threshold'], left, right, spec['min_cycles'])
                frequencies.append(sum(1/(b-a) for a, _, b in cycles)/len(cycles))
            a, b = frequencies
            value = a/b if operation == 'frequency_ratio' else abs(a-b)/((a+b)/2)
        else:
            raise ValueError('Unsupported waveform operation')
        if not math.isfinite(value):
            raise ValueError('Nonfinite waveform measurement')
        results[name] = Measurement(value, spec['unit'])
    if not results:
        raise ValueError('No waveform measurements declared')
    return results
