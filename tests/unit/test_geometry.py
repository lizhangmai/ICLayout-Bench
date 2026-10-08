import copy
import json
from types import SimpleNamespace

import pytest

from benchmarking.engine.backends.geometry import (
    KLayoutGeometryDocker,
    validate_constraints,
)
from benchmarking.evaluation import Job
from benchmarking.files import Asset

pytestmark = pytest.mark.unit
DATA = {
    'hard': [
        {'id': 'outline', 'type': 'bbox_max', 'functional_layers': [[1, 0]],
         'max_width_um': 10.0, 'max_height_um': 10.0},
        {'id': 'ports', 'type': 'named_metal_ports', 'names': ['VIN'],
         'drawing_layer': [8, 0], 'pin_layer': [8, 0], 'text_layer': [8, 0],
         'connectivity_layer': 'metal1', 'min_access_square_um': 0.1},
    ],
    'quality': [{'id': 'area', 'type': 'functional_bbox_area', 'layers_from': 'outline'}],
}


@pytest.mark.parametrize('change', [
    'unknown',
    'negative',
    'unbound_area',
    'ambiguous_area',
    'empty_area_layers',
    'missing_area_source',
])
def test_geometry_requirements_reject_unsupported_or_ambiguous_semantics(change):
    data = copy.deepcopy(DATA)
    if change == "unknown":
        data["hard"][0]["type"] = "looks_symmetric"
    elif change == "negative":
        data["hard"][1]["min_access_square_um"] = -1
    elif change == "unbound_area":
        data["quality"][0]["layers_from"] = "missing"
    elif change == "ambiguous_area":
        data["quality"][0]["functional_layers"] = [[1, 0]]
    elif change == "empty_area_layers":
        data["quality"][0].pop("layers_from")
        data["quality"][0]["functional_layers"] = []
    else:
        data["quality"][0].pop("layers_from")
    with pytest.raises(ValueError):
        validate_constraints(data)


def test_geometry_requires_a_hard_check_or_quality_measurement():
    with pytest.raises(ValueError, match="at least one"):
        validate_constraints({'hard': [], 'quality': []})


def test_functional_layer_area_allows_quality_only_constraints():
    validate_constraints({'hard': [], 'quality': [
        {'id': 'area', 'type': 'functional_bbox_area', 'functional_layers': [[1, 0], [35, 0]]},
    ]})


@pytest.mark.parametrize(('connectivity', 'quality_only'), [
    (False, False),
    (True, False),
    (False, True),
])
def test_database_free_geometry_allows_only_measurement_or_bbox(monkeypatch, connectivity, quality_only):
    calls = []

    class Tool:
        def __init__(self, *args):
            pass

        def run(self, command, files, outputs):
            calls.append(files)
            verdict = {'status': 'passed', 'reason': '',
                       'measurements': {'area': {'value': 6.0, 'unit': 'um2'}}}
            return SimpleNamespace(returncode=0, reason='', evidence={},
                                   files={'result.json': Asset(json.dumps(verdict).encode(), 'json')})

    monkeypatch.setattr('benchmarking.engine.backends.geometry.DockerTool', Tool)
    backend = KLayoutGeometryDocker(image='unused')
    if quality_only:
        constraints = {'hard': [], 'quality': [
            {'id': 'area', 'type': 'functional_bbox_area', 'functional_layers': [[1, 0], [35, 0]]},
        ]}
    else:
        constraints = copy.deepcopy(DATA)
    if not connectivity and not quality_only:
        constraints['hard'] = constraints['hard'][:1]
    task = {'output': {'top_cell': 'dut', 'max_bytes': 1024}, 'netlist_subcircuit': 'dut'}
    inputs = {'layout': Asset(b'candidate', 'gds'),
              'task': Asset(json.dumps(task).encode(), 'json'),
              'constraints': Asset(json.dumps(constraints).encode(), 'json')}
    job = Job('geometry', 'check', 'layout.geometry', (), (), (), 'constraint', '{}')
    if connectivity:
        with pytest.raises(ValueError, match='Connectivity constraints require'):
            backend.run(job, inputs)
        assert not calls
    else:
        result = backend.run(job, inputs)
        assert result.status == 'passed'
        assert result.measurements['area'].value == 6.0
        assert 'lvs.db' not in calls[0]
        config = json.loads(calls[0]['config.json'].content)
        assert config['native_lvs'] is False
        if quality_only:
            assert config['constraints'] == constraints
