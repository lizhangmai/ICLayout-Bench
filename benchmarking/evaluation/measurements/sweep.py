"""Measurements over completed DC parameter sweeps, with explicit axis units."""

import bisect
import math
from itertools import pairwise

from benchmarking.evaluation.contracts import Measurement
from benchmarking.files import keys


def measure_sweep(samples, settings):
    keys(settings, {'axis', 'axis_unit', 'max_step', 'traces', 'measures'}, set(), 'DC sweep')
    axis = samples[settings['axis']]
    step = settings['max_step']
    if (type(step) not in (int, float) or not math.isfinite(step) or step <= 0
            or settings['axis_unit'] not in {'V', 'degC'}):
        raise ValueError('Invalid DC sweep axis declaration')
    if (len(axis) < 2 or any(type(v) not in (int, float) or not math.isfinite(v) for v in axis)
            or any(b <= a or b-a > step*(1+1e-6) for a, b in pairwise(axis))):
        raise ValueError('DC sweep grid is incomplete, nonmonotonic or too sparse')
    traces = {}
    for name, spec in settings['traces'].items():
        keys(spec, {'terms', 'unit'}, {'offset'}, 'DC sweep trace')
        offset = spec.get('offset', 0)
        if (not spec['terms'] or spec['unit'] not in {'V', 'A', 'W', '1'}
                or type(offset) not in (int, float) or not math.isfinite(offset)):
            raise ValueError('Invalid DC sweep trace')
        values = [offset] * len(axis)
        for signal, coefficient in spec['terms'].items():
            raw = samples[signal]
            if (type(coefficient) not in (int, float) or not math.isfinite(coefficient)
                    or len(raw) != len(axis)
                    or any(type(v) not in (int, float) or not math.isfinite(v) for v in raw)):
                raise ValueError('Incomplete or nonfinite DC sweep signal')
            values = [a+coefficient*b for a, b in zip(values, raw, strict=True)]
        if any(not math.isfinite(v) for v in values):
            raise ValueError('Nonfinite DC sweep trace')
        traces[name] = values

    def point(values, x):
        if type(x) not in (int, float) or not math.isfinite(x):
            raise ValueError('Invalid DC sweep coordinate')
        tolerance = min(step*1e-6, len(axis)*math.ulp(axis[-1]))
        if abs(x-axis[-1]) <= tolerance:
            x = axis[-1]
        if not axis[0] <= x <= axis[-1]:
            raise ValueError('DC measurement is outside the completed sweep')
        i = bisect.bisect_left(axis, x)
        if axis[i] == x:
            return values[i]
        return values[i-1]+(values[i]-values[i-1])*(x-axis[i-1])/(axis[i]-axis[i-1])

    measured = {}
    for name, spec in settings['measures'].items():
        operation = spec['operation']
        base = {'operation', 'trace', 'unit'}
        values = traces[spec['trace']]
        unit = settings['traces'][spec['trace']]['unit']
        if operation == 'at':
            keys(spec, base | {'at'}, set(), 'DC point measurement')
            value = point(values, spec['at'])
        elif operation in {'min', 'max', 'span', 'ppm_per_axis'}:
            extra = {'reference_at'} if operation == 'ppm_per_axis' else set()
            keys(spec, base | {'start', 'stop'} | extra, set(), 'DC window measurement')
            start, stop = spec['start'], spec['stop']
            left, right = point(values, start), point(values, stop)
            if stop <= start:
                raise ValueError('Invalid DC sweep window')
            window = [left, *values[bisect.bisect_right(axis, start):bisect.bisect_left(axis, stop)], right]
            value = min(window) if operation == 'min' else max(window)
            if operation in {'span', 'ppm_per_axis'}:
                value = max(window)-min(window)
            if operation == 'ppm_per_axis':
                reference = point(values, spec['reference_at'])
                if not start <= spec['reference_at'] <= stop or reference <= 0:
                    raise ValueError('Normalized DC span requires a positive in-window reference')
                value = 1e6*value/(reference*(stop-start))
                unit = 'ppm/'+settings['axis_unit']
        else:
            raise ValueError('Unsupported DC sweep measurement: '+operation)
        if spec['unit'] != unit or not math.isfinite(value):
            raise ValueError('Invalid DC sweep measurement unit or value')
        measured[name] = Measurement(value, unit)
    if not measured:
        raise ValueError('Empty DC sweep measurements')
    return measured
