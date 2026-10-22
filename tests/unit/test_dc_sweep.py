import copy

import pytest

from benchmarking.evaluation.measurements.sweep import measure_sweep

pytestmark = pytest.mark.unit


@pytest.fixture
def sweep():
    samples = {'temp': [-40, 0, 40, 80, 120], 'out': [1.18, 1.20, 1.22, 1.20, 1.18]}
    settings = {'axis': 'temp', 'axis_unit': 'degC', 'max_step': 40,
                'traces': {'output': {'terms': {'out': 1}, 'unit': 'V'}},
                'measures': {
                    'point': {'operation': 'at', 'trace': 'output', 'at': 20, 'unit': 'V'},
                    'span': {'operation': 'span', 'trace': 'output', 'start': -20, 'stop': 100, 'unit': 'V'},
                    'drift': {'operation': 'ppm_per_axis', 'trace': 'output', 'start': -40, 'stop': 120,
                              'reference_at': 0, 'unit': 'ppm/degC'}}}
    return samples, settings


def test_sweep_interpolation_extrema_and_normalized_span(sweep):
    samples, settings = sweep
    measured = measure_sweep(samples, settings)
    assert measured['point'].value == pytest.approx(1.21)
    assert measured['span'].value == pytest.approx(.03)
    assert measured['drift'].value == pytest.approx(208.33333333333333)
    for operation, expected in [('min', 1.19), ('max', 1.22)]:
        spec = settings['measures']['span'] | {'operation': operation}
        assert measure_sweep(samples, settings | {'measures': {'value': spec}})['value'].value == pytest.approx(expected)


@pytest.mark.parametrize('change', [
    {'temp': [-40, 0, 0, 80, 120]},
    {'temp': [-40, 0, 40, 80, float('nan')]},
    {'temp': [-40, 0, 40, 80, 130]},
    {'out': [1.18, 1.20]},
    {'out': [1.18, 1.20, complex(1.22, 0), 1.20, 1.18]},
    {'out': [1.18, 1.20, float('inf'), 1.20, 1.18]},
    {'out': [0, 0, 0, 0, 0]},
])
def test_sweep_rejects_missing_invalid_or_zero_reference_samples(sweep, change):
    samples, settings = sweep
    with pytest.raises(ValueError):
        measure_sweep(samples | change, settings)


@pytest.mark.parametrize('change', [
    {'start': -41}, {'stop': 121}, {'stop': -40}, {'reference_at': 121},
    {'unit': 'V'}, {'operation': 'unsupported'},
])
def test_sweep_rejects_incomplete_windows_and_invalid_measurements(sweep, change):
    samples, settings = sweep
    settings = copy.deepcopy(settings)
    settings['measures']['drift'].update(change)
    with pytest.raises(ValueError):
        measure_sweep(samples, settings)
