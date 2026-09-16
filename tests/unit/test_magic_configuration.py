"""Extraction preprocessing options reject ambiguous configuration before I/O."""

import pytest

from layout_eval.magic import MagicCapacitanceDocker

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('settings,error', [
    ({'grid_subdivision': 0}, ValueError),
    ({'grid_subdivision': True}, ValueError),
    ({'grid_subdivision': 1.5}, ValueError),
    ({'gds_readonly': 'false'}, TypeError),
    ({'case_insensitive_ports': 1}, TypeError),
    ({'label_layers': []}, ValueError),
    ({'label_layers': [[11]]}, ValueError),
    ({'label_layers': [[11, False]]}, ValueError),
    ({'label_layers': [[-1, 0]]}, ValueError),
    ({'label_layers': [[11, 65536]]}, ValueError),
])
def test_malformed_preprocessing_settings_fail_before_bundle_or_docker_access(settings, error):
    with pytest.raises(error):
        MagicCapacitanceDocker(image='not-used', support='not-used', technology='not-used',
                               tech_name='not-used', style='not-used', **settings)


@pytest.mark.parametrize('log', [
    'Missing gate connection of device at (1 2) on net internal',
    'Warning: Orphaned node "internal" arbitrarily attached to "internal.t1"',
    'Extraction style "ngspice" is ambiguous.',
])
def test_unreliable_extraction_is_an_error_even_with_a_netlist(tmp_path, monkeypatch, log):
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

    monkeypatch.setattr('layout_eval.magic.DockerTool', Tool)
    publish_bundle({'tech.tech': Asset(b'', 'text')}, {}, tmp_path / 'support')
    backend = MagicCapacitanceDocker(image='unused', support=str(tmp_path / 'support'),
                                    technology='tech.tech', tech_name='test', style='test')
    job = Job('extract', 'extract', 'extract', (), (('netlist', 'spice'),), (), None,
              json.dumps({'top_cell': 'dut', 'ports': ['P']}))
    result = backend.run(job, {'layout': Asset(b'unused by mock tool', 'gds')})
    assert result.status == 'error'
    assert not result.outputs
