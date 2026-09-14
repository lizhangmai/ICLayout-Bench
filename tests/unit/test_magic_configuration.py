"""Extraction preprocessing options reject ambiguous configuration before I/O."""

import pytest

from benchmarking.magic import MagicCapacitanceDocker

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('settings,error', [
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
