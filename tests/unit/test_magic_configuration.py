"""Extraction preprocessing options reject ambiguous configuration before I/O."""

import pytest

from benchmarking.eda.backends.magic import MagicCapacitanceDocker
from benchmarking.eda.backends.magic_checks import netgen_verdict

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
    ('Warning: Orphaned node "internal" arbitrarily attached to "internal.t1"', 'failed'),
    ('Error while reading cell "error_amplifier": Unknown layer/datatype', 'error'),
    ('2 errors found during extraction', 'error'),
    ('Warning: Orphaned node "internal" arbitrarily attached to "internal.t1"\nUnknown layer/datatype', 'error'),
    ('Reading "error_amplifier".\nExtracting error_amplifier into error_amplifier.ext:', 'passed'),
    (('Error while reading cell "dut" (byte position 123): '
      'Warning:  Cell dut boundary was redefined.\n'), 'passed'),
    (('Error while reading cell "dut" (byte position 123): '
      'Warning:  Cell dut boundary was redefined.\nUnknown layer/datatype'), 'error'),
])
def test_extraction_diagnostics_distinguish_cell_names_from_errors(tmp_path, monkeypatch, log, status):
    import json
    from types import SimpleNamespace

    from benchmarking.evaluation import Job
    from benchmarking.evidence.bundles import publish_bundle
    from benchmarking.files import Asset

    class Tool:
        def __init__(self, *args):
            pass

        def run(self, *args, **kwargs):
            return SimpleNamespace(reason='', returncode=0,
                                   files={'extracted.spice': Asset(b'.subckt dut P\n.ends\n', 'spice'),
                                          'interface-check.json': Asset(b'{"status":"passed"}', 'json')},
                                   evidence={'console': Asset(log.encode(), 'text')})

    monkeypatch.setattr('benchmarking.eda.backends.magic.DockerTool', Tool)
    publish_bundle({'tech.tech': Asset(b'', 'text')}, {}, tmp_path / 'support')
    backend = MagicCapacitanceDocker(image='unused', support=str(tmp_path / 'support'),
                                    technology='tech.tech', tech_name='test', style='test')
    job = Job('extract', 'extract', 'extract', (), (('netlist', 'spice'),), (), None,
              json.dumps({'top_cell': 'dut', 'ports': ['P']}))
    result = backend.run(job, {'layout': Asset(b'unused by mock tool', 'gds')})
    assert result.status == status
    assert bool(result.outputs) == (status == 'passed')


@pytest.mark.parametrize('problem,expected', [
    ('rejection', 'failed'), ('missing', 'error'), ('malformed', 'error'),
    ('crash', 'error'), ('cleanup', 'error'), ('exit', 'error'),
])
def test_magic_requires_explicit_rejection_and_successful_execution(tmp_path, monkeypatch, problem, expected):
    import json

    from benchmarking.evaluation import Job
    from benchmarking.evidence.bundles import publish_bundle
    from benchmarking.execution.tools import ToolResult
    from benchmarking.files import Asset

    class Tool:
        def __init__(self, *args):
            pass

        def run(self, *args, **kwargs):
            report = b'{"status":"failed","reason":"Extracted circuit is empty"}'
            files = {'interface-check.json': Asset(b'{broken' if problem == 'malformed' else report, 'json')}
            if problem == 'missing':
                files.clear()
            evidence = {'console': Asset(
                b'Fatal error (signal SIGSEGV) - crash handler invoked\n' if problem == 'crash' else b'', 'text')}
            if problem == 'cleanup':
                evidence['cleanup_error'] = Asset(b'Container cleanup failed', 'text')
            return ToolResult(1 if problem == 'exit' else 0,
                              'Declared tool output is missing: extracted.spice', files, evidence)

    monkeypatch.setattr('benchmarking.eda.backends.magic.DockerTool', Tool)
    publish_bundle({'tech.tech': Asset(b'', 'text')}, {}, tmp_path / 'support')
    backend = MagicCapacitanceDocker(image='unused', support=str(tmp_path / 'support'),
                                    technology='tech.tech', tech_name='test', style='test')
    job = Job('extract', 'extract', 'extract', (), (('netlist', 'spice'),), (), None,
              json.dumps({'top_cell': 'dut', 'ports': ['P']}))
    result = backend.run(job, {'layout': Asset(b'frozen candidate', 'gds')})
    assert result.status == expected
    assert not result.outputs
    assert result.evidence['console'].content == (b'Fatal error (signal SIGSEGV) - crash handler invoked\n'
                                                  if problem == 'crash' else b'')


def test_magic_candidate_rejection_reaches_feedback_and_zero_score_despite_console_error(
        tmp_path, monkeypatch, inputs, bindings):
    import json
    import tomllib

    from helpers.evaluation import PLAN

    from benchmarking.eda.backends.magic import MagicRCDocker
    from benchmarking.evaluation import parse_evaluation
    from benchmarking.evaluation.feedback import feedback_details
    from benchmarking.evaluation.runner import run_evaluation
    from benchmarking.evidence.bundles import publish_bundle
    from benchmarking.execution.tools import ToolResult
    from benchmarking.files import Asset

    reason = 'Magic RC does not support multiple ports on the same conductor'
    console = b'exttospice finished.\nError:  Substrate tile at (0 0) not visited!\n'

    class Tool:
        def __init__(self, *args):
            self.identity = {'tool_version': '8.3.685', 'image': 'synthetic'}

        def run(self, command, files, outputs):
            if command == ['python', 'magic_ports.py']:
                return ToolResult(0, '', {'extraction.gds': files['candidate.gds']}, {})
            return ToolResult(0, '', {
                'interface-check.json': Asset(json.dumps({'status': 'failed', 'reason': reason}).encode(), 'json'),
            }, {'console': Asset(console, 'text')})

    monkeypatch.setattr('benchmarking.eda.backends.magic.DockerTool', Tool)
    publish_bundle({'tech.tech': Asset(b'', 'text')}, {}, tmp_path / 'support')
    bindings['extract'] = MagicRCDocker(image='unused', support=str(tmp_path / 'support'),
                                      technology='tech.tech', tech_name='test', style='test')
    data = tomllib.loads(PLAN.decode())
    next(job for job in data['jobs'] if job['id'] == 'parasitics')['parameters'] = {
        'top_cell': 'dut', 'ports': ['P']}
    plan = parse_evaluation(json.dumps(data).encode(), file_format='json')
    directory = tmp_path / 'evaluation'
    report = run_evaluation(plan, inputs, bindings, directory)

    assert report['jobs']['parasitics']['status'] == 'failed'
    assert report['jobs']['parasitics']['reason'] == reason
    assert report['jobs']['nominal']['status'] == report['jobs']['slow']['status'] == 'blocked'
    assert report['outcome'] == 'failed' and report['score']['value'] == 0
    for bounded in (True, False):
        feedback = feedback_details(report, directory, bounded=bounded)
        assert feedback['jobs']['parasitics']['status'] == 'failed'
        assert feedback['jobs']['parasitics']['reason'] == reason
        assert 'Substrate tile' in feedback['jobs']['parasitics']['evidence']['console']['text']
        assert not {'score', 'plan', 'inputs', 'pre_layout'} & feedback.keys()


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
    {'name': ['other', 'source'], 'pins': [['IN'], ['IN']], 'nets': [1, 1], 'devices': [[['nmos', 1]], [['nmos', 1]]]},
]])
def test_netgen_absent_top_comparison_is_an_error(records):
    with pytest.raises(ValueError):
        netgen_verdict(records, 'layout', 'source')


def test_netgen_completed_empty_comparison_rejects_candidate():
    record = {'name': ['layout', 'source'], 'pins': [[], []], 'nets': [0, 0], 'devices': [[], []]}
    assert netgen_verdict([record], 'layout', 'source') is False


@pytest.mark.parametrize('mismatch', [
    {'badnets': [[['layout_net'], ['source_net']]]},
    {'badelements': [[['layout_device'], ['source_device']]]},
    {'properties': [[['layout_device', ['W', 1]], ['source_device', ['W', 2]]]]},
    {'nets': [2, 3]},
    {'devices': [[['nmos', 1]], [['nmos', 2]]]},
])
def test_netgen_hierarchy_rejection_can_omit_pin_comparison(mismatch):
    child = {'name': ['child', 'child'], 'nets': [2, 2],
             'devices': [[['nmos', 1]], [['nmos', 1]]]}
    top = {'name': ['layout', 'source'], 'pins': [['IN'], ['IN']],
           'nets': [2, 2], 'devices': [[['child', 1]], [['child', 1]]]}
    # Native Netgen can reject a hierarchy before comparing its pins.
    assert netgen_verdict([child | mismatch, top], 'layout', 'source') is False


def test_netgen_missing_pins_without_a_completed_rejection_is_an_error():
    record = {'name': ['layout', 'source'], 'nets': [2, 2],
              'devices': [[['nmos', 1]], [['nmos', 1]]]}
    with pytest.raises(ValueError, match='Malformed Netgen pins'):
        netgen_verdict([record], 'layout', 'source')
