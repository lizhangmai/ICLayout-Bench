"""Extraction preprocessing options reject ambiguous configuration before I/O."""

import pytest

from benchmarking.engine.backends.magic import MagicCapacitanceDocker
from benchmarking.engine.backends.magic_checks import netgen_verdict

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('settings,error', [
    ({'grid_subdivision': 0}, ValueError),
    ({'label_layers': [[11, 65536]]}, ValueError),
])
def test_malformed_preprocessing_settings_fail_before_bundle_or_docker_access(settings, error):
    with pytest.raises(error):
        MagicCapacitanceDocker(image='not-used', support='not-used', technology='not-used',
                               tech_name='not-used', style='not-used', **settings)


@pytest.mark.parametrize('log,status', [
    ('Warning: Orphaned node "internal" arbitrarily attached to "internal.t1"', 'error'),
    ('Error while reading cell "error_amplifier": Unknown layer/datatype', 'error'),
    ('2 errors found during extraction', 'error'),
    ('Reading "error_amplifier".\nExtracting error_amplifier into error_amplifier.ext:', 'passed'),
    (('Error while reading cell "dut" (byte position 123): '
      'Warning:  Cell dut boundary was redefined.\n'), 'passed'),
    (('Error while reading cell "dut" (byte position 123): '
      'Warning:  Cell dut boundary was redefined.\nUnknown layer/datatype'), 'error'),
])
def test_extraction_diagnostics_distinguish_cell_names_from_errors(tmp_path, monkeypatch, log, status):
    import json
    from types import SimpleNamespace

    from benchmarking.bundles import publish_bundle
    from benchmarking.evaluation import Job
    from benchmarking.files import Asset

    class Tool:
        def __init__(self, *args):
            pass

        def run(self, *args, **kwargs):
            return SimpleNamespace(reason='', returncode=0,
                                   files={'extracted.spice': Asset(b'.subckt dut P\n.ends\n', 'spice')},
                                   evidence={'console': Asset(log.encode(), 'text')})

    monkeypatch.setattr('benchmarking.engine.backends.magic.DockerTool', Tool)
    publish_bundle({'tech.tech': Asset(b'', 'text')}, {}, tmp_path / 'support')
    backend = MagicCapacitanceDocker(image='unused', support=str(tmp_path / 'support'),
                                    technology='tech.tech', tech_name='test', style='test')
    job = Job('extract', 'extract', 'extract', (), (('netlist', 'spice'),), (), None,
              json.dumps({'top_cell': 'dut', 'ports': ['P']}))
    result = backend.run(job, {'layout': Asset(b'unused by mock tool', 'gds')})
    assert result.status == status
    assert bool(result.outputs) == (status == 'passed')


# Netgen exits successfully for completed mismatches. Its documented JSON
# comparisons (netgen.tcl.in convert_to_json) must establish a nonempty top and
# matching connectivity, properties and pins; the existing extraction tests do
# not cover LVS verdicts. Synthetic reports isolate interpretation from EDA.
@pytest.mark.parametrize('change,expected', [
    ({}, True),
    ({'properties': [[['left', ['W', 1]], ['right', ['W', 2]]]]}, False),
    ({'badnets': [['left', 'right']]}, False),
    ({'badelements': [['left', 'right']]}, False),
    ({'pins': [['IN', 'OUT'], ['OUT', 'IN']]}, False),
    ({'nets': [2, 3]}, False),
    ({'devices': [[['nmos', 2]], [['nmos', 3]]]}, False),
])
def test_netgen_completed_mismatches_do_not_pass(change, expected):
    record = {'name': ['layout', 'source'], 'pins': [['IN', 'OUT'], ['IN', 'OUT']],
              'nets': [2, 2], 'devices': [[['nmos', 2]], [['nmos', 2]]]}
    assert netgen_verdict([record | change], 'layout', 'source') is expected


@pytest.mark.parametrize('records', [[], [{}], [
    {'name': ['layout', 'source'], 'pins': [[], []], 'nets': [0, 0], 'devices': [[], []]},
]])
def test_netgen_absent_or_empty_comparison_is_an_error(records):
    with pytest.raises(ValueError):
        netgen_verdict(records, 'layout', 'source')
