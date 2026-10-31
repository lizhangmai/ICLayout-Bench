import copy
import json
import struct
import tomllib
from types import SimpleNamespace

import pytest
from helpers.gds import array_gds

from benchmarking.eda.backends.geometry import (
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


def test_native_polygon_boundary_counts_holes_without_their_bridge():
    from benchmarking.eda.oa.virtuoso import polygon_measurements

    # A 4x4 square with a 2x2 hole: area 12 and perimeter 16+8.
    # Native island output represents the hole using a repeated opposite bridge.
    report = ('AREA diffusion 12\n'
              'POLYGON diffusion 0 0 4 0 4 4 0 4 0 0 1 1 1 3 3 3 3 1 1 1 0 0\n')
    assert polygon_measurements(report) == {'diffusion': {'area_um2': 12, 'perimeter_um': 24}}


def test_native_stream_directory_uses_physical_units_and_accepts_zero_padding():
    import struct

    from benchmarking.eda.oa.virtuoso import stream_metadata

    def record(kind, datatype, data=b''):
        return struct.pack('>HBB', 4 + len(data), kind, datatype) + data

    # REAL8 0x40,0x10,... is 16^-1; 0x39,0x10,... is 16^-8.
    # Distinct user units cannot redefine the physical database unit in metres.
    stream = b''.join([record(0, 2, struct.pack('>h', 600)),
                       record(3, 5, bytes([64, 16]) + b'\0' * 6 + bytes([57, 16]) + b'\0' * 6),
                       record(6, 6, b'cell'), record(4, 0)])
    metadata = stream_metadata(stream + b'\0' * 128)
    assert metadata['dbu_um'] == 16**-8 * 1e6
    assert metadata['tops'] == ['cell']
    with pytest.raises(ValueError, match='after GDS library end'):
        stream_metadata(stream + b'unexpected')


@pytest.mark.parametrize('replacement', [
    struct.pack('>HBBh', 6, 14, 2, 3),  # Polygon DATATYPE is not TEXTTYPE.
    struct.pack('>HBBh', 6, 22, 3, 3),  # TEXTTYPE requires an INT2 payload.
    struct.pack('>HBBh', 6, 22, 2, 3) + struct.pack('>HBBh', 6, 21, 2, 5),
])
def test_native_stream_rejects_invalid_text_records(replacement):
    from benchmarking.eda.oa.virtuoso import stream_metadata

    valid = array_gds()
    texttype = struct.pack('>HBBh', 6, 22, 2, 3)
    assert stream_metadata(valid)['tops'] == ['dut']
    with pytest.raises(ValueError, match='GDS TEXT'):
        stream_metadata(valid.replace(texttype, replacement, 1))


@pytest.mark.parametrize('engine', ['virtuoso', 'customcompiler'])
def test_malformed_text_scores_zero_even_when_native_importer_accepts_it(monkeypatch, tmp_path, engine):
    from helpers.evaluation import PLAN, Checks, Extractor, Simulator

    from benchmarking.eda.backends.customcompiler import CustomCompilerGeometryNative
    from benchmarking.eda.backends.virtuoso import VirtuosoGeometryNative
    from benchmarking.eda.environment import ExternalRuntime
    from benchmarking.evaluation import parse_evaluation
    from benchmarking.evaluation.runner import run_evaluation

    class LenientImporter:
        version = 'fixture'

        def __init__(self, *args, **kwargs):
            self.identity = {}

        def probe(self, *args, **kwargs):
            return SimpleNamespace(returncode=0, stdout=b'fixture')

        def run(self, *args, **kwargs):
            return SimpleNamespace(returncode=0, reason='', evidence={}, files={
                'stream.log': Asset(b"Translation completed. '0' error(s)\nMessages: 0 error, 0 warning\n", 'text'),
                'geometry.txt': Asset(b'L17 D3 0 0 1 1\nCOMPLETE\n', 'text'),
            })

    module = f'benchmarking.eda.backends.{engine}'
    monkeypatch.setattr(module + ('.NativeEDATool' if engine == 'virtuoso' else '.NativeTool'), LenientImporter)
    cls = VirtuosoGeometryNative if engine == 'virtuoso' else CustomCompilerGeometryNative
    runtime = ExternalRuntime('fixture', {'image': 'unused', 'environment': {}, 'mounts': []})
    backend = cls(runtime=runtime, check='artifact')
    raw = tomllib.loads(PLAN.decode())
    artifact = next(j for j in raw['jobs'] if j['id'] == 'artifact')
    artifact.update(operation='layout.artifact', inputs={'layout': 'candidate', 'task': 'task'})
    netlist = Asset(b'netlist', 'spice')
    for source in raw['pre_layout']['jobs'].values():
        source['input_sha256']['dut'] = netlist.sha256
    plan = parse_evaluation(json.dumps(raw).encode(), file_format='json')
    malformed = array_gds().replace(struct.pack('>HBBh', 6, 22, 2, 3), struct.pack('>HBBh', 6, 14, 2, 3), 1)
    report = run_evaluation(plan, {
        'candidate': Asset(malformed, 'gds'), 'input:netlist': netlist,
        'task': Asset(json.dumps({'output': {'top_cell': 'dut', 'max_bytes': 1000000}}).encode(), 'json'),
    }, {'layout.artifact': backend, 'check': Checks(), 'extract': Extractor(), 'response': Simulator()}, tmp_path/'evaluation')
    assert report['jobs']['artifact']['status'] == 'failed'
    assert report['jobs']['drc']['status'] == report['jobs']['lvs']['status'] == 'blocked'
    assert report['score']['value'] == 0
    assert report['outcome'] == 'failed'


def test_cadence_geometry_uses_selected_layers_and_enforces_bounds():
    from benchmarking.eda.backends.virtuoso import geometry_result

    constraints = {'hard': [DATA['hard'][0]], 'quality': DATA['quality']}
    # Selected shapes span [-1, 1] to [3, 4]: 4 * 3 square micrometres.
    # An unrelated layer extends far outside the permitted functional outline.
    report = 'L1 D0 -1 1 0 2\nL1 D0 2 3 3 4\nL9 D0 -100 -100 100 100\nCOMPLETE\n'
    result = geometry_result(report, constraints)
    assert result.status == 'passed'
    assert result.measurements['area'].value == 12
    assert result.measurements['area'].unit == 'um2'
    assert geometry_result('L1 D0 0 0 11 1\nCOMPLETE\n', constraints).status == 'failed'
    assert geometry_result('L9 D0 0 0 1 1\nCOMPLETE\n', constraints).status == 'failed'
    assert geometry_result('COMPLETE\n', constraints).status == 'failed'


@pytest.mark.parametrize('report', ['L1 D0 0 0 1 1\n', 'L1 D0 0 0 nan 1\nCOMPLETE\n',
                                   'L1 D0 2 0 1 1\nCOMPLETE\n'])
def test_cadence_geometry_rejects_incomplete_or_invalid_native_evidence(report):
    from benchmarking.eda.backends.virtuoso import geometry_result

    with pytest.raises(ValueError):
        geometry_result(report, {'hard': [], 'quality': []})


@pytest.mark.parametrize(('report', 'expected'), [
    ('ERROR (XSTRM-80048): Not a GDSII file', 'failed'),
    ('ERROR (XSTRM-430): Missing top cell', 'failed'),
    ('License checkout failed', 'error'),
])
def test_cadence_import_distinguishes_candidate_rejection_from_tool_failure(monkeypatch, report, expected):
    from benchmarking.eda.backends.virtuoso import VirtuosoGeometryNative
    from benchmarking.eda.environment import ExternalRuntime

    class Tool:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, command, files, exports):
            return SimpleNamespace(returncode=255, reason='Native exit 255', evidence={},
                                   files={'stream.log': Asset(report.encode(), 'text')})

    monkeypatch.setattr('benchmarking.eda.backends.virtuoso.NativeEDATool', Tool)
    runtime = ExternalRuntime('fixture', {'image': 'unused', 'environment': {}, 'mounts': []})
    backend = VirtuosoGeometryNative(runtime=runtime, check='artifact')
    task = {'output': {'top_cell': 'dut', 'max_bytes': 1024}}
    job = Job('artifact', 'check', 'layout.artifact', (), (), (), 'artifact', '{}')
    result = backend.run(job, {'layout': Asset(array_gds(), 'gds'),
                              'task': Asset(json.dumps(task).encode(), 'json')})
    assert result.status == expected


@pytest.mark.parametrize(('report', 'console', 'expected'), [
    ('ERROR: (IMPORT_STREAM-80053): Invalid stream record', '', 'failed'),
    ('Messages: 0 error, 0 warning', 'Missing cell (DATA_MANAGEMENT-019)', 'failed'),
    ('', 'License checkout failed', 'error'),
])
def test_customcompiler_import_separates_candidate_failures_from_tool_errors(monkeypatch, report, console, expected):
    from benchmarking.eda.backends.customcompiler import CustomCompilerGeometryNative
    from benchmarking.eda.environment import ExternalRuntime

    class Tool:
        def __init__(self, *args, **kwargs):
            pass

        def probe(self, command):
            return SimpleNamespace(returncode=0, stdout=b'importStream X-2025.06')

        def run(self, command, files, exports):
            return SimpleNamespace(returncode=1, reason='Native Custom Compiler exited with 1',
                                   evidence={'console': Asset(console.encode(), 'text')},
                                   files={'stream.log': Asset(report.encode(), 'text')})

    monkeypatch.setattr('benchmarking.eda.backends.customcompiler.NativeTool', Tool)
    runtime = ExternalRuntime('fixture', {'image': 'unused', 'environment': {}, 'mounts': []})
    backend = CustomCompilerGeometryNative(runtime=runtime, check='artifact')
    task = {'output': {'top_cell': 'dut', 'max_bytes': 1024}}
    job = Job('artifact', 'check', 'layout.artifact', (), (), (), 'artifact', '{}')
    result = backend.run(job, {'layout': Asset(array_gds(), 'gds'),
                              'task': Asset(json.dumps(task).encode(), 'json')})
    assert result.status == expected


def test_customcompiler_geometry_preserves_selected_datatype_and_measurement_unit(monkeypatch):
    from benchmarking.eda.backends.customcompiler import CustomCompilerGeometryNative
    from benchmarking.eda.environment import ExternalRuntime

    class Tool:
        def __init__(self, *args, **kwargs):
            pass

        def probe(self, command):
            return SimpleNamespace(returncode=0, stdout=b'importStream X-2025.06')

        def run(self, command, files, exports):
            return SimpleNamespace(returncode=0, reason='', evidence={}, files={
                'stream.log': Asset(b'Messages: 0 error, 0 warning\n', 'text'),
                'geometry.txt': Asset(b'L17 D3 -1 1 4 5\nL17 D0 -100 -100 100 100\nCOMPLETE\n', 'text'),
            })

    monkeypatch.setattr('benchmarking.eda.backends.customcompiler.NativeTool', Tool)
    runtime = ExternalRuntime('fixture', {'image': 'unused', 'environment': {}, 'mounts': []})
    backend = CustomCompilerGeometryNative(runtime=runtime, check='geometry')
    task = {'output': {'top_cell': 'dut', 'max_bytes': 1024}}
    constraints = {'hard': [], 'quality': [
        {'id': 'area', 'type': 'functional_bbox_area', 'functional_layers': [[17, 3]]},
    ]}
    job = Job('geometry', 'check', 'layout.geometry', (), (), (), 'constraint', '{}')
    result = backend.run(job, {'layout': Asset(array_gds(), 'gds'),
                              'task': Asset(json.dumps(task).encode(), 'json'),
                              'constraints': Asset(json.dumps(constraints).encode(), 'json')})
    assert result.status == 'passed'
    assert result.measurements['area'].value == 20
    assert result.measurements['area'].unit == 'um2'


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

    monkeypatch.setattr('benchmarking.eda.backends.geometry.DockerTool', Tool)
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
    inputs = {'layout': Asset(array_gds(), 'gds'),
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
