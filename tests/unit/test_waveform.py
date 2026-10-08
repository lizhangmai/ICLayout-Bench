import pytest

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('period', [1.0, 1.1])
def test_continuous_clock_phase_retains_drift_and_rejects_missing_edges(period):
    import math

    from benchmarking.engine.measurements.waveform import measure_waveform
    time = [i/100 for i in range(1101)]
    samples = {'time': time, 'reference': [math.sin(2*math.pi*(t-.1)) for t in time],
               'clock': [math.sin(2*math.pi*(t-.3)/period) for t in time]}
    settings = {'max_step_s': .010001,
        'traces': {name: {'terms': {name: 1}} for name in ['reference', 'clock']},
        'measures': {name: {'operation': 'phase_difference', 'start_s': 0, 'stop_s': 11,
            'event': {'trace': 'clock', 'threshold': 0, 'direction': 'rise'},
            'reference_event': {'trace': 'reference', 'threshold': 0, 'direction': 'rise'},
            'min_edges': 8, 'statistic': name, 'unit': 's'} for name in ['std', 'span']}}
    result = measure_waveform(samples, settings)
    # Equal clocks have a constant 0.2 s phase. Slower clocks accumulate
    # 0.1 s each cycle, including phase excursions beyond half a period.
    assert result['span'].value == pytest.approx(0 if period == 1 else .9, abs=1e-8)
    assert result['std'].value == pytest.approx(0 if period == 1 else math.sqrt(.0825), abs=1e-8)
    samples['clock'] = [0]*len(time)
    with pytest.raises(ValueError, match='Too few clock phase edges'):
        measure_waveform(samples, settings)


def test_coherent_binary_adc_spectrum_includes_harmonics_and_bit_order():
    import math

    from benchmarking.engine.measurements.waveform import measure_waveform
    codes = [8, 11, 12, 11, 8, 5, 4, 5] * 4
    samples = {'time': list(range(33))}
    traces = {}
    for bit in range(4):
        name = f'b{bit}'
        samples[name] = [1.8 if code & (1 << bit) else 0 for code in codes+[codes[0]]]
        traces[name] = {'terms': {name: 1}}
    settings = {'max_step_s': 1, 'traces': traces, 'adc_spectra': {'adc': {
        'bits_lsb_first': list(traces), 'threshold_v': .9, 'sample_start_s': 0,
        'sample_period_s': 1, 'sample_count': 32, 'fundamental_bin': 4}},
        'measures': {'sndr': {'operation': 'adc_spectrum', 'spectrum': 'adc',
                              'statistic': 'sndr', 'unit': 'dB'}}}
    # The eight-sample sequence has only fundamental and third harmonic.
    expected = 20*math.log10((4+3*math.sqrt(2))/(3*math.sqrt(2)-4))
    assert math.isclose(measure_waveform(samples, settings)['sndr'].value, expected, abs_tol=1e-10)
    settings['adc_spectra']['adc']['sample_start_s'] = 2
    with pytest.raises(ValueError, match='sampling'):
        measure_waveform(samples, settings)
