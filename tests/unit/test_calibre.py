"""Calibre report acceptance and netlist preservation, without licensed tools."""

import pytest

from benchmarking.engine.backends.calibre import (
    bind_text_variables,
    control_deck,
    drc_summary,
    finfet_netlist,
    junction_properties,
    lvs_summary,
)
from benchmarking.engine.netlists.dspf import adapt_dspf

pytestmark = pytest.mark.unit


def test_drc_reports_require_an_executed_declared_top_and_both_counts():
    report = '''CALIBRE::DRC-H SUMMARY REPORT
Layout Primary Cell: TOP
TOTAL DRC RuleChecks Executed: 17
TOTAL DRC Results Generated: 0 (0)
'''
    assert drc_summary(report, 'TOP') == (17, (0, 0))
    assert drc_summary(report.replace('0 (0)', '0 (3)'), 'TOP')[1] == (0, 3)
    for changed in (report.replace('17', '0'), report.replace('TOP', 'OTHER'),
                    report+report, report.split('TOTAL DRC Results')[0]):
        with pytest.raises(ValueError, match='Incomplete'):
            drc_summary(changed, 'TOP')


def test_lvs_requires_all_compared_cells_named_ports_and_a_finished_report():
    report = '''OVERALL COMPARISON RESULTS
CELL SUMMARY
**********
 Result Layout Source
 CORRECT TOP TOP
 CORRECT CHILD CHILD
**********
 LVS IGNORE PORTS NO
 LVS CHECK PORT NAMES YES
Total Elapsed Time: 3 sec
'''
    assert lvs_summary(report, 'TOP')
    assert not lvs_summary(report.replace('CORRECT CHILD', 'INCORRECT CHILD'), 'TOP')
    for changed in (report.replace('TOP TOP', 'OTHER OTHER'),
                    report.replace('NAMES YES', 'NAMES NO'),
                    report.replace('IGNORE PORTS NO', 'IGNORE PORTS YES'),
                    report.split('Total Elapsed')[0], report+'LVS BOX CHILD\n'):
        with pytest.raises(ValueError):
            lvs_summary(changed, 'TOP')


def test_io_adaptation_retains_rules_and_requires_declared_include():
    vendor = '''INCLUDE "../process.rc"
LAYOUT PRIMARY "example"
LAYOUT PATH "example.gds"
DRC SUMMARY REPORT "example.sum"
minimum_width { INTERNAL M1 < 0.2 }
'''
    text = control_deck(vendor, {'LAYOUT PRIMARY': '"TOP"', 'LAYOUT PATH': '"candidate.gds"'},
                        {'../process.rc': '/pdk/process.rc'})
    assert 'minimum_width { INTERNAL M1 < 0.2 }' in text
    assert 'DRC SUMMARY REPORT "example.sum"' in text
    assert 'LAYOUT PRIMARY "example"' not in text
    assert 'INCLUDE "/pdk/process.rc"' in text
    for original in ('absent', '../process.rc'):
        with pytest.raises(ValueError, match='exactly once'):
            control_deck(vendor+vendor, {}, {original: '/pdk/process.rc'})


def test_extracted_rc_and_junctions_survive_named_port_reordering():
    # Independent series R / shunt C control: pole = 1/(2*pi*1000*1e-9).
    # This verifies adapter preservation; native extraction has a separate
    # geometrical oracle and a representative case in Designs.
    circuit = '''.subckt TOP OUT GND IN
Rlead IN OUT 1000
Cload OUT GND 1e-9
M0 GND GND GND GND nmodel l=2e-6 w=3e-6 as=1e-12 ad=2e-12 ps=3e-6 pd=4e-6
.ends TOP
'''
    adapted = adapt_dspf(circuit, 'TOP', ['GND', 'IN', 'OUT'], {}, True)
    assert '.SUBCKT TOP GND IN OUT' in adapted
    for component in circuit.splitlines()[1:4]:
        assert component in adapted
    continued = circuit.replace(' w=3e-6', '\n* geometry annotation\n  + w=3e-6')
    continued = '\n'.join('  ' + line for line in continued.splitlines()) + '\n'
    assert adapt_dspf(continued, 'TOP', ['GND', 'IN', 'OUT'], {}, True) == adapted.replace(
        '.ends TOP', '* geometry annotation\n.ends TOP')
    wrapped_comment = circuit + '\n* expanding symbol: generated export\n+ of pins=3\n'
    assert adapt_dspf(wrapped_comment, 'TOP', ['GND', 'IN', 'OUT'], {}, True) == (
        adapted + '* expanding symbol: generated export of pins=3\n')
    with pytest.raises(ValueError, match='required geometry'):
        adapt_dspf(circuit.replace(' as=1e-12', ''), 'TOP', ['GND', 'IN', 'OUT'], {}, True)
    with pytest.raises(ValueError, match='ports differ'):
        adapt_dspf(circuit, 'TOP', ['GND', 'IN', 'MISSING'], {}, True)


def test_finfet_preserves_physical_fin_count_and_bulk_junction_parameters():
    circuit = '''.subckt TOP D G S B
M0 D G S B nfet l=20n w=48n nfin=2 adej=6.08e-16 asej=6.08e-16 pdej=168n psej=168n
R0 D internal 10
C0 internal S 1f
.ends TOP
'''
    assert finfet_netlist(circuit) == circuit
    adapted = adapt_dspf(finfet_netlist(circuit), 'TOP', ['D', 'G', 'S', 'B'], {})
    assert circuit.splitlines()[1] in adapted
    for changed in (circuit.replace(' nfin=2', ''), circuit.replace('nfin=2', 'nfin=2.5'),
                    circuit.replace('adej=6.08e-16', 'adej=-1'),
                    circuit.replace('psej=168n', 'psej=nan')):
        with pytest.raises(ValueError):
            finfet_netlist(changed)


def test_junction_adaptation_binds_declared_active_geometry():
    deck = '''DEVICE MN(NTEST) gate poly(G) diff(S) diff(D) bulk(B)
[ PROPERTY W, L
W = PERIM_CO(gate,diff)/2
L = AREA(gate)/W ]
'''
    mapping = {'NTEST': {'type': 'MN', 'gate': 'gate', 'active': 'active'}}
    text = junction_properties(deck, mapping)
    assert '<active> [ PROPERTY W, L, AS, AD, PS, PD' in text
    assert 'AS = AREA(S) * W / PERIM_IN(S,active)' in text
    assert 'PD = PERIM(D) * W / PERIM_IN(D,active)' in text
    assert 'W = PERIM_CO(gate,diff)/2' in text
    with pytest.raises(ValueError, match='exactly once'):
        junction_properties(deck+deck, mapping)


def test_explicit_native_execution_preserves_frozen_bytes_and_failure_evidence():
    from benchmarking.engine.backends.calibre import _rewrite_workspace_paths
    from benchmarking.engine.external import ExternalRuntime
    from benchmarking.engine.tools.native import NativeTool
    from benchmarking.files import Asset

    runtime = ExternalRuntime('native-test', {'image': 'unused', 'environment': {}, 'mounts': []})
    tool = NativeTool(runtime, 5, failure_label='Calibre')
    frozen = Asset(b'/workspace/unchanged\x00binary', 'gds')
    files = {'candidate.gds': frozen, 'run.sh': Asset(
        b'cat /workspace/candidate.gds > copied.gds\nprintf "native error"\nexit 3\n', 'text')}
    result = tool.run(['bash', 'run.sh'], files, {'copied.gds': 'gds'},
                      file_rewriter=_rewrite_workspace_paths)
    assert result.files['copied.gds'] == frozen
    assert result.returncode == 3 and result.reason
    assert result.evidence['console'].content == b'native error'
    assert tool.identity['execution'] == 'operator-native'
    assert 'image_id' not in tool.identity


def test_native_timeout_is_an_error_without_fabricated_outputs():
    from benchmarking.engine.external import ExternalRuntime
    from benchmarking.engine.tools.native import NativeTool
    from benchmarking.files import Asset

    runtime = ExternalRuntime('native-test', {'image': 'unused', 'environment': {}, 'mounts': []})
    tool = NativeTool(runtime, .1, failure_label='Calibre')
    result = tool.run(['bash', 'run.sh'], {'run.sh': Asset(b'sleep 3\n', 'text')}, {'result': 'text'})
    assert result.returncode is None and 'time limit' in result.reason
    assert not result.files and 'missing:result' in result.evidence


def test_foundry_subcircuit_mos_keeps_measured_junction_geometry():
    circuit = '''.subckt TOP IN OUT VSS
Xmos OUT IN VSS VSS native_n l=1.8e-7 w=1e-6 as=1e-13 ad=2e-13 ps=1e-6 pd=2e-6
Rwire IN OUT 1
Cwire OUT VSS 1e-15
.ends TOP
'''
    adapted = adapt_dspf(circuit, 'TOP', ['IN', 'OUT', 'VSS'], {}, True,
                         subcircuit_mos_models=['native_n'])
    assert circuit.splitlines()[1] in adapted
    with pytest.raises(ValueError, match='required geometry'):
        adapt_dspf(circuit.replace(' ad=2e-13', ''), 'TOP', ['IN', 'OUT', 'VSS'], {}, True,
                   subcircuit_mos_models=['native_n'])
    with pytest.raises(ValueError, match='physical devices'):
        adapt_dspf(circuit, 'TOP', ['IN', 'OUT', 'VSS'], {}, True)


def test_process_variant_is_explicitly_mounted_and_keeps_default(tmp_path):
    from benchmarking.engine.external import ExternalRuntime
    (tmp_path / 'identity').write_text('variant')
    runtime = ExternalRuntime('variants', {'image': 'unused',
        'environment': {'PDK_ROOT': '/default', 'VARIANT_ROOT': str(tmp_path)},
        'mounts': [{'source': str(tmp_path), 'target': '/eda/variant', 'release': '1',
                    'identity_paths': ['identity']}]})
    with pytest.raises(ValueError, match='explicitly mounted'):
        runtime.select_pdk('VARIANT_ROOT')
    runtime.environment['VARIANT_ROOT'] = '/eda/variant'
    selected = runtime.select_pdk('VARIANT_ROOT')
    assert selected.environment['PDK_ROOT'] == '/eda/variant'
    assert runtime.environment['PDK_ROOT'] == '/default'


def test_tvf_io_stays_inside_verbatim_and_preserves_comment_bytes():
    raw = b'#! tvf\ntvf::VERBATIM {\nLAYOUT PATH "old"\n}\n# comment \xb0\n'
    adapted = control_deck(raw.decode(errors='surrogateescape'), {'LAYOUT PATH': '"new"'}, {})
    assert 'tvf::VERBATIM {\nLAYOUT PATH "new"\n}' in adapted
    assert b'# comment \xb0' in adapted.encode(errors='surrogateescape')


def test_archived_drc_reads_only_the_declared_regular_member(native_tmp_path, monkeypatch):
    import io
    import json
    import tarfile
    from types import SimpleNamespace

    from benchmarking.engine.backends.calibre import CalibreNative
    from benchmarking.engine.external import ExternalRuntime
    from benchmarking.engine.tools.types import ToolResult
    from benchmarking.evaluation import Job
    from benchmarking.files import Asset

    raw = b'LAYOUT PRIMARY "old"\nVARIABLE INPUT_NAMES "previous"\nwidth_rule { INTERNAL M1 < 0.2 }\n'
    with tarfile.open(native_tmp_path / 'rules.tar.gz', 'w:gz') as archive:
        member = tarfile.TarInfo('process/ip.drc')
        member.size = len(raw)
        archive.addfile(member, io.BytesIO(raw))
    captured = {}

    from benchmarking.engine.tools.native import NativeTool

    monkeypatch.setattr(NativeTool, 'probe', lambda *args, **kwargs:
                        SimpleNamespace(returncode=0, stdout=b'Calibre native release'))
    runtime = ExternalRuntime('test', {'image': 'unused', 'environment': {'PDK_ROOT': str(native_tmp_path)},
        'mounts': [{'source': str(native_tmp_path), 'target': str(native_tmp_path), 'release': 'test',
                    'identity_paths': ['rules.tar.gz']}]})
    variables = {'INPUT_NAMES': ['IN', 'INB']}
    backend = CalibreNative(runtime=runtime, check='drc', deck='rules.tar.gz', deck_member='process/ip.drc',
                           threads=2, text_variables=variables)
    variables['INPUT_NAMES'].append('CHANGED_AFTER_BINDING')

    def execute(command, files, exports, **kwargs):
        captured.update(files)
        return ToolResult(0, '', {'drc.summary': Asset(b'''CALIBRE::DRC-H SUMMARY REPORT
Layout Primary Cell: TOP
TOTAL DRC RuleChecks Executed: 1
TOTAL DRC Results Generated: 0 (0)
''', 'text')}, {})
    backend.tool.run = execute
    task = Asset(json.dumps({'output': {'top_cell': 'TOP'}, 'netlist_subcircuit': 'TOP'}).encode(), 'json')
    job = Job('drc', 'check', 'layout.drc', (), (), (), 'drc', '{}')
    assert backend.run(job, {'layout': Asset(b'gds', 'gds'), 'task': task}).status == 'passed'
    assert 'width_rule { INTERNAL M1 < 0.2 }' in captured['control.svrf'].content.decode()
    assert 'VARIABLE INPUT_NAMES "IN" "INB"' in captured['control.svrf'].content.decode()
    assert '"previous"' not in captured['control.svrf'].content.decode()
    assert 'calibre -drc -hier -turbo 2' in captured['run.sh'].content.decode()
    for member in ['/absolute.drc', '../author.drc']:
        with pytest.raises(ValueError, match='archived DRC'):
            CalibreNative(runtime=runtime, check='drc', deck='rules.tar.gz', deck_member=member)


def test_text_variables_require_an_existing_unambiguous_safe_name_list():
    vendor = 'VARIABLE INPUT_NAMES "OLD"\nwidth_rule { INTERNAL M1 < 0.2 }\n'
    for deck in [vendor + vendor, vendor.replace('INPUT_NAMES', 'OTHER')]:
        with pytest.raises(ValueError, match='exactly once'):
            bind_text_variables(deck, {'INPUT_NAMES': ['I']})
    for settings in [{'INPUT_NAMES': []}, {'INPUT_NAMES': 'I'}, {'INPUT_NAMES': [1]},
                     {'BAD NAME': ['I']}, {'INPUT_NAMES': ['I"\nDRC UNSELECT CHECK width_rule']},
                     {'INPUT_NAMES': ['I}']}, {'INPUT_NAMES': ['$input']}, {'INPUT_NAMES': ['I\\']}]:
        with pytest.raises(ValueError, match='Invalid'):
            bind_text_variables(vendor, settings)


def test_spice_port_case_matching_is_opt_in_and_rejects_aliases():
    circuit = """.subckt TOP VCM OUT VSS
M1 OUT VCM VSS VSS native_n l=1.8e-7 w=1e-6
Rwire VCM OUT 1
Cwire OUT VSS 1e-15
.ends TOP
"""
    with pytest.raises(ValueError, match='ports differ'):
        adapt_dspf(circuit, 'TOP', ['OUT', 'Vcm', 'VSS'], {})
    adapted = adapt_dspf(circuit, 'TOP', ['OUT', 'Vcm', 'VSS'], {},
                         case_insensitive_ports=True)
    assert adapted.splitlines()[0] == '.SUBCKT TOP OUT Vcm VSS'
    assert adapted.splitlines()[1:] == circuit.splitlines()[1:]
    with pytest.raises(ValueError, match='ports differ'):
        adapt_dspf(circuit, 'TOP', ['VCM', 'Vcm', 'VSS'], {},
                   case_insensitive_ports=True)


def test_tool_module_selection_requires_a_declared_profile():
    from benchmarking.engine.external import ExternalRuntime
    runtime = ExternalRuntime('versions', {'image': 'unused', 'mounts': [],
        'environment': {}, 'modules': {'spectre': ['cadence/current'],
                                      'spectre_previous': ['cadence/previous']}})
    selected = runtime.select_module('spectre', 'spectre_previous')
    assert selected.modules['spectre'] == ['cadence/previous']
    assert runtime.modules['spectre'] == ['cadence/current']
    with pytest.raises(ValueError, match='explicitly declared'):
        runtime.select_module('spectre', 'unknown')
