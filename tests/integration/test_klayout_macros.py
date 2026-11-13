"""Native KLayout macros preserve geometry verdicts and completion checks."""

import json
import os
from xml.etree import ElementTree

import pytest

from benchmarking.eda.backends.klayout import KLayoutDocker
from benchmarking.eda.images import DEFAULT_IMAGE
from benchmarking.evaluation import Job
from benchmarking.evidence.bundles import publish_bundle
from benchmarking.files import Asset

pytestmark = [pytest.mark.integration, pytest.mark.acceptance_eda]

RULES = '''require_relative "helper"
raise "Wrong runset directory" unless File.expand_path(__dir__) == File.expand_path(RUNSET_DIRECTORY)
source($input, $topcell)
report("Synthetic width", $report)
input(1, 0).width($minimum.to_f).output("width", "Minimum width")
'''


def support(path, *, body=RULES, ending=''):
    macro = ElementTree.Element('klayout-macro')
    for key, value in {
        'interpreter': 'dsl', 'dsl-interpreter-name': 'drc-dsl-xml',
        'text': body + ending,
    }.items():
        ElementTree.SubElement(macro, key).text = value
    publish_bundle({
        'rules/width.lydrc': Asset(ElementTree.tostring(macro, encoding='utf-8'), 'text'),
        'rules/width.drc': Asset(RULES.encode(), 'text'),
        'rules/helper.rb': Asset(b'RUNSET_DIRECTORY = __dir__\n', 'text'),
        'rules/checks.drc': Asset(
            b'input(1, 0).width($minimum.to_f).output("width", "Minimum width")\n', 'text'),
        'rules/additional.drc': Asset(
            b'source($input, $topcell)\nreport("Additional width", $report)\n'
            b'input(1, 0).width(2 * $minimum.to_f).output("extra_width", "Additional width")\n', 'text'),
    }, {}, path)
    return str(path)


def candidate(tmp_path, width):
    db = pytest.importorskip('klayout.db')
    layout = db.Layout()
    layout.dbu = 0.001
    cell = layout.create_cell('DUT')
    cell.shapes(layout.layer(1, 0)).insert(db.Box(0, 0, round(width / layout.dbu), 1000))
    path = tmp_path / 'candidate.gds'
    layout.write(str(path))
    return Asset(path.read_bytes(), 'gds')


def check(prepared, layout, deck, **settings):
    backend = KLayoutDocker(
        image=os.environ.get('ICLAYOUT_BENCH_TEST_IMAGE', DEFAULT_IMAGE), check='drc',
        support=prepared, deck=deck, variables={'minimum': '0.2'},
        required_categories=['width'], **settings)
    job = Job('drc', 'check', 'layout.drc', (), (), (), 'drc',
              json.dumps({'top_cell': 'DUT', 'max_bytes': 1000000}))
    return backend.run(job, {'layout': layout})


@pytest.mark.parametrize('extension', ['drc', 'lydrc'])
@pytest.mark.parametrize('width,expected', [(1.0, 'passed'), (0.1, 'failed')])
def test_plain_and_xml_runsets_check_candidate_geometry(tmp_path, extension, width, expected):
    result = check(support(tmp_path / 'support'), candidate(tmp_path, width), f'rules/width.{extension}')
    assert result.status == expected, (result.reason, result.evidence['tool.log'].content)
    assert result.evidence['complete.txt'].content == b'complete\n'
    assert result.evidence['report.db'].content


def test_xml_runsets_resolve_native_relative_includes(tmp_path):
    body = 'source($input, $topcell)\nreport("Included width", $report)\n# %include checks.drc\n'
    result = check(support(tmp_path / 'support', body=body), candidate(tmp_path, 1.0), 'rules/width.lydrc')
    assert result.status == 'passed', (result.reason, result.evidence['tool.log'].content)


@pytest.mark.parametrize('failure', ['body', 'early_exit', 'report'])
def test_xml_runset_errors_and_early_exit_cannot_pass(tmp_path, failure):
    ending = {'body': 'raise "Native body failure"', 'early_exit': 'exit(0)'}.get(failure, '')
    body = 'File.write($report, "Invalid report")\n' if failure == 'report' else RULES
    result = check(support(tmp_path / 'support', body=body, ending=ending),
                   candidate(tmp_path, 1.0), 'rules/width.lydrc')
    assert result.status == 'error', (result.reason, result.evidence['tool.log'].content)
    if ending:
        assert result.evidence['complete.txt'].content != b'complete\n'
    else:
        assert result.evidence['complete.txt'].content == b'complete\n'


def test_mixed_xml_and_plain_decks_keep_independent_reports(tmp_path):
    result = check(support(tmp_path / 'support'), candidate(tmp_path, 0.3), 'rules/width.lydrc',
                   additional_decks=[{'deck': 'rules/additional.drc', 'required_categories': ['extra_width']}])
    assert result.status == 'failed', (result.reason, result.evidence['tool.log'].content)
    decks = json.loads(result.evidence['result.json'].content)['details']['decks']
    assert [deck['status'] for deck in decks] == ['passed', 'failed']
    assert result.evidence['complete.txt'].content == result.evidence['complete-1.txt'].content == b'complete\n'


LVS_RULES = '''require_relative "helper"
raise "Wrong runset directory" unless File.expand_path(__dir__) == File.expand_path(RUNSET_DIRECTORY)
source($input, $topcell)
report_lvs($report)
schematic($schematic)
target_netlist($target_netlist)
wire = input(1, 0)
contacts = input(2, 0)
extract_devices(resistor("RES", 1.0), { "R" => wire, "C" => contacts, "tA" => contacts, "tB" => contacts })
connect(contacts, labels(2, 0))
netlist.make_top_level_pins
netlist.simplify
compare
'''


def lvs_support(path, *, body=LVS_RULES, ending=''):
    macro = ElementTree.Element('klayout-macro')
    for key, value in {'interpreter': 'dsl', 'dsl-interpreter-name': 'lvs-dsl-xml',
                       'text': body + ending}.items():
        ElementTree.SubElement(macro, key).text = value
    xml = Asset(ElementTree.tostring(macro, encoding='utf-8'), 'text')
    publish_bundle({'compare.lylvs': xml, 'compare.lvs': Asset((body + ending).encode(), 'text'),
        'helper.rb': Asset(b'RUNSET_DIRECTORY = __dir__\n', 'text'),
        'resistor.lvs': Asset(LVS_RULES[LVS_RULES.index('source($input'):].encode(), 'text')}, {}, path)
    return str(path), xml


def resistor_candidate(tmp_path, *, wrapped=False, wrong_label=False):
    db = pytest.importorskip('klayout.db')
    layout = db.Layout()
    layout.dbu = 0.001
    device = layout.create_cell('INNER' if wrapped else 'DUT')
    # An 8 um by 2 um path at 1 ohm/square gives 4 ohms independently
    # of the extractor. Contacts touch its ends and carry electrical labels.
    device.shapes(layout.layer(1, 0)).insert(db.Box(1000, 0, 9000, 2000))
    contacts = device.shapes(layout.layer(2, 0))
    contacts.insert(db.Box(0, 0, 1000, 2000))
    contacts.insert(db.Box(9000, 0, 10000, 2000))
    contacts.insert(db.Text('WRONG' if wrong_label else 'A', db.Trans(500, 1000)))
    contacts.insert(db.Text('B', db.Trans(9500, 1000)))
    if wrapped:
        top = layout.create_cell('DUT')
        top.insert(db.CellInstArray(device.cell_index(), db.Trans(1, False, 3700, 1900)))
    path = tmp_path / 'resistor.gds'
    layout.write(str(path))
    return Asset(path.read_bytes(), 'gds')


def check_lvs(prepared, layout, deck, *, macro=None, resistance=4, flatten=False):
    backend = KLayoutDocker(image=os.environ.get('ICLAYOUT_BENCH_TEST_IMAGE', DEFAULT_IMAGE),
                            check='lvs', support=prepared, deck=deck, flatten=flatten)
    job = Job('lvs', 'check', 'layout.lvs', (), (('database', 'klayout-lvs'), ('binding', 'json')),
              (), 'lvs', json.dumps({'top_cell': 'DUT', 'subcircuit': 'DUT', 'max_bytes': 1000000}))
    inputs = {'layout': layout, 'netlist': Asset(f'.subckt DUT A B\nR0 A B {resistance}\n.ends DUT\n'.encode(), 'spice')}
    if macro is not None:
        inputs['lvs_macro'] = macro
    return backend.run(job, inputs)


@pytest.mark.parametrize('extension', ['lvs', 'lylvs'])
@pytest.mark.parametrize('resistance,expected', [(4, 'passed'), (8, 'failed')])
def test_plain_and_xml_lvs_compare_extracted_physical_devices(tmp_path, extension, resistance, expected):
    prepared, _ = lvs_support(tmp_path / 'support')
    result = check_lvs(prepared, resistor_candidate(tmp_path), f'compare.{extension}', resistance=resistance)
    assert result.status == expected, (result.reason, result.evidence['extracted.spice'].content,
                                      result.evidence['tool.log'].content)
    assert result.evidence['complete.txt'].content == b'complete\n'


@pytest.mark.parametrize('wrong_label,expected', [(False, 'passed'), (True, 'failed')])
def test_task_lvs_macro_and_flatten_preserve_wrapped_labels(tmp_path, wrong_label, expected):
    prepared, macro = lvs_support(tmp_path / 'support')
    original = resistor_candidate(tmp_path, wrapped=True, wrong_label=wrong_label)
    result = check_lvs(prepared, original, None, macro=macro, flatten=True)
    assert result.status == expected, (result.reason, result.evidence['tool.log'].content)
    assert result.evidence['lvs_macro'] == macro
    assert result.evidence['flat-candidate.gds'].content != original.content
    if expected == 'passed':
        assert json.loads(result.outputs['binding'].content)['candidate_sha256'] == original.sha256


def test_native_lvs_macro_resolves_relative_includes(tmp_path):
    prepared, macro = lvs_support(tmp_path / 'support', body='# %include resistor.lvs\n')
    result = check_lvs(prepared, resistor_candidate(tmp_path), None, macro=macro)
    assert result.status == 'passed', (result.reason, result.evidence['tool.log'].content)


@pytest.mark.parametrize('failure', ['body', 'early_exit', 'report'])
def test_native_lvs_macro_errors_cannot_establish_a_pass(tmp_path, failure):
    ending = {'body': 'raise "Native LVS body failure"', 'early_exit': 'exit(0)'}.get(failure, '')
    body = 'File.write($report, "Invalid report")\n' if failure == 'report' else LVS_RULES
    prepared, macro = lvs_support(tmp_path / 'support', body=body, ending=ending)
    result = check_lvs(prepared, resistor_candidate(tmp_path), None, macro=macro)
    assert result.status == 'error', (result.reason, result.evidence['tool.log'].content)
    assert not result.outputs
