"""Declarative small-signal transfer measurements on finite AC sweeps."""

import bisect
import math
from itertools import pairwise

from benchmarking.files import keys

from ..contracts import Measurement


def measure_transfer(ac, dc, settings):
    keys(settings, {'input', 'output', 'max_frequency_ratio', 'measures'}, set(), 'AC transfer')
    frequencies = ac['freq']
    ratio = settings['max_frequency_ratio']
    if type(ratio) not in (int, float) or not math.isfinite(ratio) or ratio <= 1:
        raise ValueError('Invalid AC maximum frequency ratio')
    if (len(frequencies) < 2
            or any(type(f) not in (int, float) or not math.isfinite(f) or f <= 0 for f in frequencies)
            or any(b <= a or b/a > ratio*(1+1e-9) for a, b in pairwise(frequencies))):
        raise ValueError('AC frequency grid is incomplete, nonmonotonic or too sparse')

    def linear(samples, spec, count):
        keys(spec, {'terms'}, set(), 'AC/DC linear signal')
        if not spec['terms']:
            raise ValueError('Empty AC/DC linear signal')
        values = [0] * count
        for signal, coefficient in spec['terms'].items():
            raw = samples[signal]
            if (type(coefficient) not in (int, float) or not math.isfinite(coefficient)
                    or len(raw) != count or any(not math.isfinite(abs(v)) for v in raw)):
                raise ValueError('Incomplete or nonfinite AC/DC signal')
            values = [a+coefficient*b for a, b in zip(values, raw, strict=True)]
        if any(not math.isfinite(abs(v)) for v in values):
            raise ValueError('Nonfinite AC/DC linear signal')
        return values

    incoming = linear(ac, settings['input'], len(frequencies))
    outgoing = linear(ac, settings['output'], len(frequencies))
    if any(abs(v) == 0 for v in incoming):
        raise ValueError('Zero AC input excitation')
    gain = [abs(o/i) for o, i in zip(outgoing, incoming, strict=True)]
    if any(not math.isfinite(v) for v in gain):
        raise ValueError('AC gain must be finite')
    gain_db = [20*math.log10(v) if v else None for v in gain]

    def interpolate(f):
        if type(f) not in (int, float) or not math.isfinite(f) or not frequencies[0] <= f <= frequencies[-1]:
            raise ValueError('AC frequency is outside the completed sweep')
        index = bisect.bisect_left(frequencies, f)
        if frequencies[index] == f:
            if gain_db[index] is None:
                raise ValueError('Zero AC gain at a requested logarithmic measurement')
            return gain_db[index]
        if gain_db[index-1] is None or gain_db[index] is None:
            raise ValueError('Zero AC gain prevents requested logarithmic interpolation')
        alpha = math.log(f/frequencies[index-1])/math.log(frequencies[index]/frequencies[index-1])
        return gain_db[index-1]+alpha*(gain_db[index]-gain_db[index-1])

    def window(start, stop):
        left, right = interpolate(start), interpolate(stop)
        if stop <= start:
            raise ValueError('Invalid AC frequency window')
        lo, hi = bisect.bisect_right(frequencies, start), bisect.bisect_left(frequencies, stop)
        if any(v is None for v in gain_db[lo:hi]):
            raise ValueError('Zero AC gain inside a requested logarithmic window')
        return [start, *frequencies[lo:hi], stop], [left, *gain_db[lo:hi], right]

    measured = {}
    for name, spec in settings['measures'].items():
        operation = spec['operation']
        base = {'operation', 'unit'}
        if operation == 'dc':
            keys(spec, base | {'terms'}, set(), 'DC measurement')
            value = linear(dc, {'terms': spec['terms']}, 1)[0]
            if isinstance(value, complex) or spec['unit'] not in {'V', 'A', 'W', '1'}:
                raise ValueError('DC measurement requires a real scalar and declared physical unit')
            unit = spec['unit']
        elif operation == 'gain_db':
            keys(spec, base | {'frequency_hz'}, set(), 'AC point gain')
            value, unit = interpolate(spec['frequency_hz']), 'dB'
        elif operation in {'peak_gain_db', 'peak_frequency_hz', 'peaking_db', 'bandwidth_hz'}:
            required = base | {'start_hz', 'stop_hz'}
            if operation in {'peaking_db', 'bandwidth_hz'}:
                required |= {'reference_hz'}
            if operation == 'bandwidth_hz':
                required |= {'relative_db'}
            keys(spec, required, set(), 'AC window measurement')
            freq, levels = window(spec['start_hz'], spec['stop_hz'])
            peak = max(range(len(levels)), key=levels.__getitem__)
            value, unit = levels[peak], 'dB'
            if operation == 'peak_frequency_hz':
                value, unit = freq[peak], 'Hz'
            elif operation == 'peaking_db':
                value -= interpolate(spec['reference_hz'])
            elif operation == 'bandwidth_hz':
                relative = spec['relative_db']
                if type(relative) not in (int, float) or not math.isfinite(relative) or relative >= 0:
                    raise ValueError('AC relative bandwidth level must be negative')
                threshold = interpolate(spec['reference_hz']) + relative
                for i in range(1, len(freq)):
                    if levels[i] < threshold <= levels[i-1]:
                        alpha = (threshold-levels[i-1])/(levels[i]-levels[i-1])
                        value, unit = freq[i-1]*(freq[i]/freq[i-1])**alpha, 'Hz'
                        break
                else:
                    raise ValueError('Required downward AC crossing is outside the measured window')
        else:
            raise ValueError(f'Unsupported AC transfer operation: {operation}')
        if spec['unit'] != unit:
            raise ValueError('AC transfer measurement unit mismatch')
        measured[name] = Measurement(value, unit)
    if not measured:
        raise ValueError('Empty AC transfer measurements')
    return measured
