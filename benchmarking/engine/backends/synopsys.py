"""Native ICV comparison, ICV-based StarRC extraction and HSPICE simulation."""

import json
import math
import re
import shlex
from pathlib import Path

from benchmarking.files import Asset, keys

from ..contracts import JobResult, Measurement
from ..netlists.spice import number
from ..source import package_source
from ..tools.native import NativeTool


def _native_version(tool, runtime, module, command, pattern, returncodes=(0,)):
    argv = runtime.module_command(module, command)
    result = tool.probe(argv)
    output = result.stdout.decode(errors='replace')
    versions = re.findall(pattern, output, re.MULTILINE)
    if result.returncode not in returncodes or not versions:
        raise ValueError('Tool did not report a complete release identity')
    return sorted(set(versions))


def strict_lvs_deck(text):
    """Strengthen the supplied ICV matrix without changing device extraction."""
    replacements = {
        r'recognize_gate\(state = compare_settings, type = ALL\);':
            'recognize_gate_off(state = compare_settings);',
        r'merge_parallel\(state = compare_settings, device_type = (NMOS|PMOS),[^;]+;':
            r'merge_parallel_off(state = compare_settings, device_type = \1);',
        r'short_equivalent_nodes\(state = compare_settings, device_type = (NMOS|PMOS),[^;]+;': '',
    }
    for pattern, replacement in replacements.items():
        text, count = re.subn(pattern, replacement, text)
        if count != (1 if pattern.startswith('recognize') else 2):
            raise ValueError('Unsupported ICV comparison matrix')
    settings = '''
check_property(state = compare_settings, device_type = NMOS,
    property_tolerances = {{"W", [-1e-15, 1e-15], ABSOLUTE},
                           {"L", [-1e-15, 1e-15], ABSOLUTE}, {"nfin", [0, 0], ABSOLUTE}});
check_property(state = compare_settings, device_type = PMOS,
    property_tolerances = {{"W", [-1e-15, 1e-15], ABSOLUTE},
                           {"L", [-1e-15, 1e-15], ABSOLUTE}, {"nfin", [0, 0], ABSOLUTE}});
match(state = compare_settings, detect_permutable_ports = false,
    match_condition = {missing_black_box_cell = ERROR, missing_black_box_port = ERROR,
        matches_must_be_assumed = ERROR, top_ports_matched_with_different_name = ERROR,
        top_schematic_ports_matched_with_different_or_missing_name = ERROR,
        top_schematic_port_net_match_non_port_net = ERROR});
'''
    text, count = re.subn(r'(?m)^compare\(', lambda _: settings + '\ncompare(', text)
    if count != 1:
        raise ValueError('ICV deck must have one comparison')
    text, count = re.subn(r'(schematic_db = schematic\(\s*)', r'\1uppercase = true,\n', text)
    if count != 1:
        raise ValueError('ICV deck must have one comparison')
    return text


def icv_drc_summary(text, top, allowed_unexecuted):
    def scalar(pattern):
        matches = re.findall(pattern, text, re.MULTILINE)
        if len(matches) != 1:
            raise ValueError('Incomplete ICV DRC report')
        return matches[0]
    if scalar(r'^Top cell name:\s*(\S+)\s*$') != top or 'IC Validator is done.' not in text:
        raise ValueError('ICV did not finish the declared layout')
    rules = int(scalar(r'^(\d+) total rules were run\.$'))
    violations = int(scalar(r'^There are (\d+) total violations\.$'))
    unexecuted = re.findall(r'^(\S+)\s+v = Not Executed\s*$', text, re.MULTILINE)
    if rules <= 0 or set(unexecuted) != set(allowed_unexecuted):
        raise ValueError('ICV rule coverage differs from the declared deck')
    return violations


def icv_lvs_summary(text, top):
    verdict = re.findall(r'^Final comparison result:(PASS|FAIL)\s*$', text, re.MULTILINE)
    if (len(verdict) != 1 or not re.search(r'TOP equivalence point:\s*\[' + re.escape(top)
            + r',\s*' + re.escape(top) + r'\]', text, re.IGNORECASE)
            or not re.search(r'check_property\s+= 2 device_name', text)
            or not re.search(r'recognize_gate\s+= 0 device_name', text)):
        raise ValueError('Incomplete or non-strict ICV LVS report')
    return verdict == ['PASS']


def star_spice(text, top, ports, models):
    """Retain extracted three-terminal MOS and RC; expose the declared supplies."""
    # StarRC SPF wraps cards and omits ideal global supply pins from its header.
    text = re.sub(r'\n\s*\+\s*', ' ', text)
    rows = text.splitlines()
    headers = [i for i, row in enumerate(rows) if row.lower().startswith('.subckt ')]
    if len(headers) != 1 or rows[headers[0]].split()[1].lower() != top.lower():
        raise ValueError('StarRC must extract exactly the declared top')
    if len({p.lower() for p in ports}) != len(ports) or any(
            not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_!]*', p) for p in ports):
        raise ValueError('Invalid StarRC interface')
    nodes, resistors, capacitors, mos = set(), 0, 0, 0
    for i, row in enumerate(rows):
        fields = row.split()
        if not fields or fields[0].startswith(('*', '.')):
            continue
        kind = fields[0][0].lower()
        if kind in {'r', 'c'}:
            if len(fields) != 4 or not math.isfinite(number(fields[3])) or number(fields[3]) <= 0:
                raise ValueError('StarRC RC cards must be positive finite scalars')
            nodes.update(p.lower() for p in fields[1:3])
            resistors += kind == 'r'
            capacitors += kind == 'c'
        elif kind == 'm':
            if len(fields) < 8 or fields[4].lower() not in models:
                raise ValueError('Unsupported StarRC three-terminal MOS')
            params = dict(p.lower().split('=', 1) for p in fields[5:])
            if not {'w', 'l', 'nfin', 'adej', 'asej', 'pdej', 'psej'} <= params.keys():
                raise ValueError('StarRC device geometry is incomplete')
            if any(not math.isfinite(number(v)) or number(v) <= 0 for v in params.values()):
                raise ValueError('Invalid extracted device property')
            fields[4] = models[fields[4].lower()]
            rows[i] = ' '.join(fields)
            nodes.update(p.lower() for p in fields[1:4])
            mos += 1
        else:
            raise ValueError('Unexpected StarRC circuit element')
    original = rows[headers[0]].split()[2:]
    extra = {p.lower() for p in original} - {p.lower() for p in ports}
    if (not mos or not resistors or not capacitors
            or any(not re.fullmatch(r'\d+|_generated_\d+', p) for p in extra)
            or not {p.lower() for p in ports} <= nodes):
        raise ValueError('StarRC interface or RC extraction is incomplete')
    rows[headers[0]] = '.subckt ' + top + ' ' + ' '.join(ports)
    return '\n'.join(rows) + '\n'


class ICVNative:
    def __init__(self, *, runtime, check, deck, allowed_unexecuted=(), grid=None,
                 mos_models=None, ground='GND!', timeout_seconds=180):
        if check not in {'drc', 'lvs', 'rc'}:
            raise ValueError('Unknown ICV check')
        self.runtime, self.check = runtime, check
        self.deck = runtime.pdk_file(deck)[0]
        self.grid = runtime.pdk_file(grid)[1] if grid else None
        if check == 'rc' and not grid:
            raise ValueError('StarRC needs a declared extraction grid')
        self.models = mos_models or {}
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_!]*', ground):
            raise ValueError('Invalid extraction ground')
        self.ground, self.allowed = ground, tuple(allowed_unexecuted)
        self.settings = {'check': check, 'deck': deck, 'grid': grid, 'mos_models': self.models,
                         'ground': ground, 'allowed_unexecuted': list(allowed_unexecuted)}
        self.tool = NativeTool(runtime, timeout_seconds, failure_label='ICV')
        self.version = _native_version(self.tool, runtime, 'icv', ['icv', '-V'],
                                       r'Version (\S+) for linux64')
        self.star = NativeTool(runtime, timeout_seconds, failure_label='StarRC') if check == 'rc' else None
        self.star_version = (_native_version(self.star, runtime, 'starrc', ['StarXtract', '-v'],
                                              r'^\s*Version\s*:\s*(\S+)', returncodes=(0, 1))
                             if self.star else None)

    @property
    def identity(self):
        return {'adapter': 'icv-native', 'settings': self.settings, **self.tool.identity,
                'module': 'icv', 'tool_version': self.version,
                'starrc': ({**self.star.identity, 'module': 'starrc',
                            'tool_version': self.star_version} if self.star else None),
                'adapter_sha256': Asset(Path(__file__).read_bytes(), 'python').sha256,
                'spice_number_sha256': Asset(package_source('engine/netlists/spice.py').read_bytes(), 'python').sha256}

    def run(self, job, inputs):
        keys(inputs, {'layout', 'task'} | ({'netlist'} if self.check != 'drc' else set()), set(), 'ICV inputs')
        keys(job.parameters, {'ports'} if self.check == 'rc' else set(), set(), 'ICV parameters')
        if (inputs['layout'].format != 'gds' or inputs['task'].format != 'json'
                or job.stage != ('extract' if self.check == 'rc' else 'check')):
            raise ValueError('Invalid ICV job or inputs')
        task = json.loads(inputs['task'].content)
        top = task['output']['top_cell']
        if top != task['netlist_subcircuit'] or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', top):
            raise ValueError('ICV needs identical simple top names')
        raw = self.deck.read_text()
        files = {'candidate.gds': inputs['layout']}
        command = ['icv', '-c', top, '-f', 'GDSII', '-i', 'candidate.gds',
                   '-I', str(self.deck.parent), '-host_init', 'localhost:1']
        exports = {top + '.RESULTS': 'text'}
        if self.check == 'drc':
            raw = ('#include <icv.rh>\nlibrary(cell="' + top
                   + '", format=GDSII, library_name="candidate.gds");\n' + raw)
        else:
            if inputs['netlist'].format != 'spice':
                raise ValueError('ICV requires a SPICE source')
            files['source.spice'] = inputs['netlist']
            raw = strict_lvs_deck(raw)
            command += ['-s', 'source.spice', '-sf', 'SPICE', '-stc', top]
            exports[top + '.LVS_ERRORS'] = 'text'
        command.append('control.rs')
        files['control.rs'] = Asset(raw.encode(), 'text')
        script = 'set -eu\n' + shlex.join(command) + '\n'
        if self.check == 'rc':
            files['star.cmd'] = Asset((f'BLOCK: {top}\nICV_RUNSET_REPORT_FILE: pex_runset_report\n'
                f'SKIP_CELLS: !*\nTCAD_GRD_FILE: {self.grid}\nEXTRACTION: RC\nCOUPLE_TO_GROUND: NO\n'
                'NETS: *\nNETLIST_FORMAT: SPF\nNETLIST_FILE: extracted.dspf\n'
                'NETLIST_INSTANCE_SECTION: YES\nNETLIST_NODE_SECTION: YES\n'
                f'NETLIST_GROUND_NODE_NAME: {self.ground}\nOPERATING_TEMPERATURE: 25\nNUM_CORES: 1\n').encode(), 'text')
            script += self.runtime.module_setup('starrc') + '\nStarXtract star.cmd\n'
            exports['extracted.dspf'] = 'spice'
        files['run.sh'] = Asset(script.encode(), 'text')
        result = self.tool.run(self.runtime.module_command('icv', ['bash', 'run.sh']), files, exports,
                               evidence_patterns=('Star*.log', '*.LAYOUT_ERRORS'))
        evidence = result.evidence | result.files | {'control': files['control.rs']}
        if result.reason or result.returncode:
            return JobResult('error', result.reason or 'ICV/StarRC did not finish', evidence=evidence)
        try:
            if self.check == 'drc':
                count = icv_drc_summary(result.files[top + '.RESULTS'].content.decode(), top, self.allowed)
                return JobResult('failed' if count else 'passed',
                                 f'{count} DRC violations' if count else '', evidence=evidence)
            if not icv_lvs_summary(result.files[top + '.LVS_ERRORS'].content.decode(), top):
                return JobResult('failed' if self.check == 'lvs' else 'error', 'ICV LVS mismatch', evidence=evidence)
            if self.check == 'lvs':
                return JobResult('passed', evidence=evidence)
            console = result.evidence['console'].content
            counts = re.findall(rb'Warnings:\s*(\d+)\s+Errors:\s*(\d+)', console)
            if (not counts or any(errors != b'0' for _, errors in counts)
                    or not re.search(rb'^Done\s+Elp=', console, re.MULTILINE)):
                raise ValueError('StarRC did not report clean completion')
            adapted = star_spice(result.files['extracted.dspf'].content.decode(), top,
                                 job.parameters['ports'], self.models)
        except (ValueError, KeyError) as error:
            return JobResult('error', str(error), evidence=evidence)
        return JobResult('passed', outputs={'netlist': Asset(adapted.encode(), 'spice')}, evidence=evidence)


def hspice_measures(listing, requested):
    if 'job concluded' not in listing.lower() or re.search(r'\*\*error\*\*', listing, re.IGNORECASE):
        raise ValueError('HSPICE did not complete all measurements')
    result = {}
    for name, unit in requested.items():
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
            raise ValueError('Invalid HSPICE measurement name')
        values = re.findall(r'^\s*' + re.escape(name) + r'\s*=\s*(\S+)', listing, re.MULTILINE | re.IGNORECASE)
        if values and any(value.lower() == 'failed' for value in values):
            raise ValueError('HSPICE required event measurement failed: ' + name)
        if len(values) != 1 or not math.isfinite(number(values[0])):
            raise ValueError('Missing or nonfinite HSPICE measurement: ' + name)
        result[name] = Measurement(number(values[0]), unit)
    if not result:
        raise ValueError('HSPICE needs explicit measurements')
    return result


class HspiceNative:
    def __init__(self, *, runtime, model, sections, timeout_seconds=180):
        self.runtime = runtime
        self.model = runtime.pdk_file(model)[1]
        if (not isinstance(sections, list)
                or any(not isinstance(s, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', s)
                       for s in sections)):
            raise ValueError('Invalid HSPICE model sections')
        self.sections = list(sections)
        self.tool = NativeTool(runtime, timeout_seconds, failure_label='HSPICE')
        self.version = _native_version(self.tool, runtime, 'hspice', ['hspice', '-v'],
                                       r'(?:Version|HSPICE Version)\s*[:=]?\s*(\S+)')

    @property
    def identity(self):
        return {'adapter': 'hspice-native', 'model': self.model, 'sections': self.sections,
                **self.tool.identity, 'module': 'hspice', 'tool_version': self.version,
                'adapter_sha256': Asset(Path(__file__).read_bytes(), 'python').sha256,
                'spice_number_sha256': Asset(package_source('engine/netlists/spice.py').read_bytes(), 'python').sha256}

    def run(self, job, inputs):
        keys(inputs, {'deck', 'dut'}, set(), 'HSPICE inputs')
        keys(job.parameters, {'measurements'}, set(), 'HSPICE parameters')
        if job.stage != 'simulate' or job.outputs or any(a.format != 'spice' for a in inputs.values()):
            raise ValueError('HSPICE requires a simulation deck and DUT without outputs')
        deck = inputs['deck'].content.decode()
        if deck.count('* ICLAYOUT_MODELS') != 1:
            raise ValueError('HSPICE deck needs one model binding marker')
        libraries = ('\n'.join(f'.lib "{self.model}" {s}' for s in self.sections)
                     if self.sections else f'.include "{self.model}"')
        deck = deck.replace('* ICLAYOUT_MODELS', libraries)
        files = {'deck.spice': Asset(deck.encode(), 'spice'), 'dut.spice': inputs['dut']}
        command = self.runtime.module_command('hspice', ['hspice', '-i', 'deck.spice', '-o', 'result'])
        result = self.tool.run(command, files,
                               {'result.lis': 'text'}, evidence_patterns=('result.mt*', 'result.st*'))
        evidence = result.evidence | result.files | {'bound-deck': files['deck.spice']}
        if result.reason or result.returncode:
            return JobResult('error', result.reason or 'HSPICE did not finish', evidence=evidence)
        try:
            measures = hspice_measures(result.files['result.lis'].content.decode(), job.parameters['measurements'])
        except ValueError as error:
            return JobResult('error', str(error), evidence=evidence)
        return JobResult('passed', measurements=measures, evidence=evidence)
