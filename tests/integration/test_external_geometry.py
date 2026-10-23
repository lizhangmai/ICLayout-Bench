"""Independent geometry controls using explicitly supplied commercial runtimes.

These synthetic GDS records establish geometry behavior, not circuit validity.
They need neither a reference layout nor an open EDA package.
"""

import json
import struct

import pytest
from helpers.catalog import CASES, read_case

from benchmarking.eda.environment import ExternalRuntime
from benchmarking.evaluation import Job
from benchmarking.files import Asset
from benchmarking.tasks.dataset import process_manifest

pytestmark = [pytest.mark.integration, pytest.mark.acceptance_eda]


def geometry_cases():
    selected = {}
    for path in CASES:
        backend = read_case(path).get('toolchain', {}).get('backends', {}).get('geometry', {})
        if backend.get('type') in {'virtuoso-geometry-native', 'customcompiler-geometry-native'}:
            selected.setdefault((backend['type'], backend['settings']['runtime']), path)
    return list(selected.values())


def array_gds(*, geometry=True):
    """Six 1 um squares at x=-1,1,3 and y=1,4; ignore a distant text label."""
    def record(kind, datatype, data=b''):
        data += b'\0' * (len(data) % 2)
        return struct.pack('>HBB', len(data) + 4, kind, datatype) + data

    def xy(*values):
        return struct.pack('>' + 'i' * len(values), *values)

    def real8(value):
        exponent = 64
        while value < 1 / 16:
            value *= 16
            exponent -= 1
        while value >= 1:
            value /= 16
            exponent += 1
        return bytes([exponent]) + int(value * 2**56).to_bytes(7, 'big')

    dates = struct.pack('>12h', *([2026, 1, 1, 0, 0, 0] * 2))
    boundary = [record(8, 0), record(13, 2, struct.pack('>h', 17)),
                record(14, 2, struct.pack('>h', 3)),
                record(16, 3, xy(0, 0, 1000, 0, 1000, 1000, 0, 1000, 0, 0)), record(17, 0)]
    return b''.join([
        record(0, 2, struct.pack('>h', 600)), record(1, 2, dates), record(2, 6, b'control'),
        record(3, 5, real8(.001) + real8(1e-9)),
        record(5, 2, dates), record(6, 6, b'child'), *(boundary if geometry else []), record(7, 0),
        record(5, 2, dates), record(6, 6, b'dut'), record(11, 0), record(18, 6, b'child'),
        record(19, 2, struct.pack('>2h', 3, 2)),
        record(16, 3, xy(-1000, 1000, 5000, 1000, -1000, 7000)), record(17, 0),
        record(12, 0), record(13, 2, struct.pack('>h', 17)), record(22, 2, struct.pack('>h', 3)),
        record(16, 3, xy(100000, 100000)), record(25, 6, b'IGNORE_TEXT'), record(17, 0),
        record(7, 0), record(4, 0),
    ])


@pytest.fixture(scope='module', params=geometry_cases(), ids=lambda path: path.parents[3].name)
def geometry_backend(request):
    from benchmarking.eda.backends.customcompiler import CustomCompilerGeometryNative
    from benchmarking.eda.backends.virtuoso import VirtuosoGeometryNative

    spec = read_case(request.param)['toolchain']['backends']['geometry']
    cls = {'virtuoso-geometry-native': VirtuosoGeometryNative,
           'customcompiler-geometry-native': CustomCompilerGeometryNative}[spec['type']]
    return cls(runtime=ExternalRuntime.from_manifest(process_manifest(request.param)), check='geometry')


@pytest.fixture(scope='module')
def artifact_backend(geometry_backend):
    return type(geometry_backend)(runtime=geometry_backend.runtime, check='artifact')


@pytest.mark.parametrize('control', ['valid', 'text_only', 'missing', 'malformed'])
def test_native_artifact_requires_geometry_and_a_readable_declared_top(artifact_backend, control, tmp_path):
    task = {'output': {'top_cell': 'absent' if control == 'missing' else 'dut', 'max_bytes': 1000000}}
    result = artifact_backend.run(Job('artifact', 'check', 'layout.artifact', (), (), (), 'artifact', '{}'), {
        'layout': Asset(b'bad gds' if control == 'malformed' else array_gds(geometry=control != 'text_only'), 'gds'),
        'task': Asset(json.dumps(task).encode(), 'json'),
    })
    for name, asset in result.evidence.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(asset.content)
    assert result.status == ('passed' if control == 'valid' else 'failed'), result.reason


@pytest.mark.parametrize('control', ['valid', 'bounds', 'datatype', 'missing', 'malformed'])
def test_native_geometry_handles_arrays_text_and_invalid_submissions(geometry_backend, control, tmp_path):
    constraints = {'hard': [
        {'id': 'outline', 'type': 'bbox_max', 'functional_layers': [[17, 3]],
         'max_width_um': 5, 'max_height_um': 4},
    ], 'quality': [{'id': 'area', 'type': 'functional_bbox_area', 'layers_from': 'outline'}]}
    if control == 'bounds':
        constraints['hard'][0]['max_width_um'] = 4.99
    if control == 'datatype':
        constraints['hard'][0]['functional_layers'] = [[17, 0]]
    task = {'output': {'top_cell': 'absent' if control == 'missing' else 'dut', 'max_bytes': 1000000}}
    result = geometry_backend.run(Job('geometry', 'check', 'layout.geometry', (), (), (), 'constraint', '{}'), {
        'layout': Asset(b'bad gds' if control == 'malformed' else array_gds(), 'gds'),
        'task': Asset(json.dumps(task).encode(), 'json'),
        'constraints': Asset(json.dumps(constraints).encode(), 'json'),
    })
    for name, asset in result.evidence.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(asset.content)
    assert result.status == ('passed' if control == 'valid' else 'failed'), result.reason
    if control == 'valid':
        # Functional envelope: [-1, 1] to [4, 5], hence 5 * 4 um².
        assert result.measurements['area'].value == 20
        assert result.measurements['area'].unit == 'um2'


def test_native_preview_reads_hierarchy_and_ignores_distant_labels(geometry_backend, tmp_path):
    from benchmarking.results.native_preview import render

    png, metadata = render(Asset(array_gds(), 'gds'), 'dut', geometry_backend.runtime)
    (tmp_path / 'layout.png').write_bytes(png.content)
    assert metadata['bbox_um'] == [-1, 1, 4, 5]
    assert metadata['width'] == 4096
    assert struct.unpack('>II', png.content[16:24]) == (metadata['width'], metadata['height'])
    assert png.content[:8] == b'\x89PNG\r\n\x1a\n'
    assert metadata['renderer']['execution'] == 'operator-native'
