"""Native component boundaries for a GDS carrying explicit EM setup.

Set ICLAYOUT_BENCH_NATIVE_CELLS_PROFILE to a reviewed native-cells profile.
This checks native geometry and rejects modified components; it does not
qualify an RF circuit or a field partition.
"""

import json
import os

import pytest

from benchmarking.eda.images import DEFAULT_IMAGE
from benchmarking.eda.resources.installation import prepare_installation
from benchmarking.eda.resources.support import load_profile, prepare_support_cache
from benchmarking.evidence.bundles import load_bundle
from benchmarking.evidence.identity import package_source
from benchmarking.execution.tools.docker import DockerTool
from benchmarking.files import Asset

pytestmark = [pytest.mark.integration, pytest.mark.acceptance_eda]



def test_field_gds_serialization_preserves_holes_and_port_sheets(tmp_path):
    """Material holes and zero-area source sheets survive native serialization."""
    db = pytest.importorskip("klayout.db")
    from benchmarking.eda._scripts.openems_prepare import write_field_gds

    layout = db.Layout()
    layout.dbu = .001
    top = layout.create_cell("TOP")
    material = db.Region(db.Box(0, 0, 10000, 10000))
    for x in (1000, 4000, 7000):
        material -= db.Region(db.Box(x, 2000, x + 500, 8000))
    assert sum(p.holes() for p in material.each()) == 3
    index = layout.layer(8, 0)
    top.shapes(index).insert(material)
    port_index = layout.layer(1001, 0)
    port = db.Box(200, 0, 200, 400)
    top.shapes(port_index).insert(port)
    top.shapes(layout.layer(8, 2)).insert(db.Text("terminal", db.Trans(0, 0)))
    encoded = tmp_path / "field.gds"
    write_field_gds(layout, str(encoded))
    frozen = db.Layout()
    frozen.read(str(encoded))
    result = db.Region(frozen.top_cell().begin_shapes_rec(frozen.layer(8, 0)))
    assert (result ^ material).is_empty()
    assert sum(p.holes() for p in result.merged().each()) == 3
    for x in (1000, 4000, 7000):
        assert (result & db.Region(db.Box(x, 2000, x + 500, 8000))).is_empty()
    source_shapes = list(frozen.top_cell().shapes(frozen.layer(1001, 0)).each())
    assert len(source_shapes) == 1
    assert source_shapes[0].bbox() == port
    labels = list(frozen.top_cell().shapes(frozen.layer(8, 2)).each())
    assert [shape.text.string for shape in labels] == ["terminal"]


def test_native_components_are_compared_without_regenerating_the_candidate(tmp_path):
    profile = os.environ.get("ICLAYOUT_BENCH_NATIVE_CELLS_PROFILE")
    if not profile:
        pytest.skip("Set ICLAYOUT_BENCH_NATIVE_CELLS_PROFILE to reviewed IHP native cells")
    image = os.environ.get("ICLAYOUT_BENCH_TEST_IMAGE", DEFAULT_IMAGE)
    source = json.loads(load_profile(profile).content)["source"]
    support = load_bundle(prepare_support_cache(prepare_installation(source), profile,
        compiler_image=image, diagnostics=tmp_path / "resources"))
    control = Asset(rb'''
import json
import subprocess
from pathlib import Path
from klayout import db
from native_cells import metadata, pin_regions, validate_cells

variants = [
    ('npn13G2', {'Nx': 2}),
    ('rsil', {'w': 1e-6, 'l': 2e-6, 'Calculate': 'R'}),
    ('rppd', {'w': 2e-6, 'l': 5e-6, 'b': 0, 'Calculate': 'R'}),
    ('rhigh', {'w': 2e-6, 'l': 6e-6, 'b': 0, 'Calculate': 'R'}),
    ('cmim', {'w': 7e-6, 'l': 9e-6, 'Calculate': 'C'}),
    ('rfcmim', {'w': 7e-6, 'l': 9e-6, 'wfeed': 3e-6, 'Calculate': 'C'}),
]
declaration = {'devices': [{'cell': f'EM_D{i}', 'pcell': name, 'parameters': values}
                           for i, (name, values) in enumerate(variants)],
               'ports': [{'number': 1}]}
config = {'directory': 'support/klayout', 'module': 'sg13g2_pycell_lib',
          'library': 'SG13_dev', 'technology': 'sg13g2', 'dbu': .001}
Path('cells.json').write_text(json.dumps({'declaration': declaration, 'config': config}))
subprocess.run(['python', 'native_cells.py', 'generate'], check=True)
# Importing a library into the candidate process could regenerate saved PCell
# context. The reviewed generator runs separately and emits static geometry.
assert db.Library.library_by_name('SG13_dev', 'sg13g2') is None
names = json.loads(Path('expected.json').read_text())
expected = db.Layout()
expected.read('expected.gds')
layout = db.Layout()
layout.dbu = .001
top = layout.create_cell('TOP')
setup = top.shapes(layout.layer(1000, 0))
setup.insert(db.Text('EM_LAYOUT_V1', db.Trans()))
for i, item in enumerate(declaration['devices']):
    body = layout.create_cell(f'BODY{i}')
    body.copy_tree(expected.cell(names[item['cell']]))
    wrapper = layout.create_cell(item['cell'])
    wrapper.insert(db.CellInstArray(body.cell_index(), db.Trans()))
    top.insert(db.CellInstArray(wrapper.cell_index(), db.Trans(i * 100000, 0)))
    setup.insert(db.Text('EM_DEVICE_V1 ' + json.dumps(item), db.Trans()))
setup.insert(db.Text('EM_PORT_V1 ' + json.dumps(declaration['ports'][0]), db.Trans()))
layout.write('candidate.gds')
frozen = db.Layout()
frozen.read('candidate.gds')
declared = metadata(frozen)
checked = validate_cells(frozen, declared, expected, names)
assert checked.keys() == names.keys()
assert db.Library.library_by_name('SG13_dev', 'sg13g2') is None
# A diode-connected transistor can have B and C on the same extracted net.
# The native terminal labels must still select distinct physical pin planes.
base = sum(pin_regions(checked['EM_D0']['native'], 'B').values(), db.Region())
collector = sum(pin_regions(checked['EM_D0']['native'], 'C').values(), db.Region())
assert not base.is_empty() and not collector.is_empty()
assert (base & collector).is_empty()
# A changed component must not be replaced by freshly generated geometry.
body = checked['EM_D0']['native']
free = db.Region(body.bbox()) - db.Region(body.begin_shapes_rec(frozen.layer(8, 0)))
assert not free.is_empty()
body.shapes(frozen.layer(8, 0)).insert(free)
try:
    validate_cells(frozen, declared, expected, names)
except ValueError as error:
    assert 'differs from its native PCell' in str(error)
else:
    raise AssertionError('Modified native component was accepted')
Path('comparison.json').write_text(json.dumps({'native_variants': len(variants),
    'candidate_library_registered': False, 'modified_component_rejected': True,
    'named_terminal_regions_distinct': True}))
''', "python")
    result = DockerTool(image, ["python", "--version"], 180).run(
        ["python", "control.py"], {"control.py": control,
            "native_cells.py": Asset(package_source("eda/_scripts/openems_layout.py").read_bytes(), "python"),
            **support.mounted_files()},
        {"candidate.gds": "gds", "comparison.json": "json", "expected.gds": "gds"})
    for name, asset in {**result.evidence, **result.files}.items():
        (tmp_path / name.replace(":", "_")).write_bytes(asset.content)
    assert not result.returncode and not result.reason, result.evidence["console"].content.decode()
