"""Native Calibre DRC, LVS and coupled xRC through an external installation."""

import json
import math
import re
import shlex
import tarfile
from pathlib import Path

from benchmarking.eda.backends.calibre_config import CalibreConfiguration
from benchmarking.eda.environment import ExternalRuntime
from benchmarking.eda.netlists.dspf import bind_extracted_netlist
from benchmarking.eda.netlists.spice import logical_lines, number
from benchmarking.evaluation.contracts import JobResult
from benchmarking.evidence.identity import package_source
from benchmarking.execution.tools.docker import DockerTool
from benchmarking.execution.tools.native import NativeTool
from benchmarking.files import Asset, keys


def validate_mos_parameters(text, rules):
    """Validate declared native parameter domains without changing device cards."""
    devices = [row.text for row in logical_lines(text) if re.match(r'(?i)^\s*M\S+\s+', row.text)]
    if not devices:
        raise ValueError('Extraction contains no MOS devices for declared parameter checks')
    for device in devices:
        fields = device.split()
        if len(fields) < 7:
            raise ValueError('Incomplete four-terminal MOS')
        params = {name.lower(): value for name, value in
                  re.findall(r'\b(\w+)\s*=\s*([^\s]+)', ' '.join(fields[6:]))}
        for name, rule in rules.items():
            value = number(params[name.lower()]) if name.lower() in params else None
            if (value is None or not math.isfinite(value) or value < 0
                    or rule != 'nonnegative' and value == 0
                    or rule == 'positive_integer' and not value.is_integer()):
                raise ValueError(f'Extracted MOS violates declared parameter domain: {name}')
    return text


def append_svrf(text, statements):
    """TVF keeps SVRF statements inside a VERBATIM block."""
    if re.match(r'\s*#!\s*tvf\b', text):
        statements = 'tvf::VERBATIM {\n'+statements+'\n}'
    return text.rstrip()+'\n'+statements+'\n'


def control_deck(text, controls, includes):
    """Replace run I/O only; retain the installed process/device rules verbatim.

    Calibre rejects duplicate single-valued statements. Include names resolve
    from the run directory, so declared adaptations bind them to mounted files.
    """
    for original, replacement in includes.items():
        pattern = r'(?im)^\s*include\s+"'+re.escape(original)+r'"\s*$'
        text, count = re.subn(pattern, 'INCLUDE "'+replacement+'"', text)
        if count != 1:
            raise ValueError('Calibre include adaptation must match exactly once')
    names = list(controls)
    if 'PEX NETLIST' in controls:
        names += ['PEX REPORT']
    lines = [line for line in text.splitlines()
             if not any(re.match(r'^\s*'+name+r'\s', line, re.IGNORECASE) for name in names)]
    return append_svrf('\n'.join(lines), '\n'.join(f'{name} {value}' for name, value in controls.items()))


def bind_text_variables(text, variables):
    """Bind declared pin-name lists without adding geometry or LVS ports."""
    for name, values in variables.items():
        if (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name)
                or not isinstance(values, (list, tuple)) or not values
                or any(not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_./:!?*+-]+', value)
                       for value in values)):
            raise ValueError('Invalid Calibre text variable')
        replacement = 'VARIABLE '+name+' '+' '.join('"'+value+'"' for value in values)
        text, count = re.subn(r'(?im)^\s*VARIABLE\s+'+re.escape(name)+r'\s+[^\n]+$',
                              lambda _, replacement=replacement: replacement, text)
        if count != 1:
            raise ValueError('Calibre text variable must match exactly once')
    return text


def drc_summary(text, top):
    rules = re.findall(r'^TOTAL DRC RuleChecks Executed:\s*(\d+)\s*$', text, re.MULTILINE)
    counts = re.findall(r'^TOTAL DRC Results Generated:\s*(\d+)\s*\((\d+)\)\s*$', text, re.MULTILINE)
    cells = re.findall(r'^Layout Primary Cell:\s*(\S+)\s*$', text, re.MULTILINE)
    if (len(rules) != 1 or int(rules[0]) <= 0 or len(counts) != 1 or cells != [top]
            or 'CALIBRE::DRC' not in text):
        raise ValueError('Incomplete native Calibre DRC summary')
    return int(rules[0]), tuple(map(int, counts[0]))


def lvs_summary(text, top):
    header = re.search(r'CELL[ \t]+SUMMARY[ \t]*\n(?:[ \t]*\*{5,}[ \t]*\n)?'
                       r'(.*?)\n[ \t]*\*{5,}', text, re.DOTALL)
    if (not header or 'OVERALL COMPARISON RESULTS' not in text
            or not re.search(r'^Total Elapsed Time:\s*\d+\s+sec\s*$', text, re.MULTILINE)
            or not re.search(r'^\s*LVS IGNORE PORTS\s+NO\s*$', text, re.MULTILINE)
            or not re.search(r'^\s*LVS CHECK PORT NAMES\s+YES\s*$', text, re.MULTILINE)):
        raise ValueError('Incomplete native Calibre LVS comparison')
    rows = re.findall(r'^\s*(CORRECT|INCORRECT|NOT COMPARED)\s+(\S+)\s+(\S+)\s*$', header[1], re.MULTILINE)
    if not rows or not any(a == b == top for _, a, b in rows):
        raise ValueError('Calibre LVS did not compare the declared top')
    if re.search(r'^\s*LVS BOX\s+[^/\n]+', text, re.MULTILINE):
        raise ValueError('Blackboxed comparison is not a complete LVS check')
    return all(verdict == 'CORRECT' for verdict, _, _ in rows)


class CalibreBackend:
    """Shared Calibre checks and extraction, independent of tool execution."""

    adapter = None
    connectivity = 'xrc'

    def __init__(self, *, runtime, check, deck, timeout_seconds=600, pdk_root_env=None, **settings):
        if not isinstance(runtime, ExternalRuntime):
            raise TypeError('Calibre requires a resolved external runtime')
        self.configuration = CalibreConfiguration.parse(check, deck, settings,
            connectivity=self.connectivity)
        self.runtime = runtime.select_pdk(pdk_root_env)
        self.tool = self._make_tool(timeout_seconds)

    @property
    def check(self):
        return self.configuration.check

    def _make_tool(self, timeout_seconds):
        raise NotImplementedError

    def _run_tool(self, command, files, exports):
        return self.tool.run(command, files, exports)

    @property
    def identity(self):
        return {'adapter': self.adapter, 'check': self.check, 'settings': self.configuration.identity(),
                **self.tool.identity,
                'adapter_sha256': Asset(Path(__file__).read_bytes(), 'python').sha256,
                'configuration_sha256': Asset(package_source('eda/backends/calibre_config.py').read_bytes(), 'python').sha256,
                'spice_number_sha256': Asset(package_source('eda/netlists/spice.py').read_bytes(), 'python').sha256,
                'netlist_adapter_sha256': Asset(package_source('eda/netlists/dspf.py').read_bytes(), 'python').sha256}

    @staticmethod
    def _layout_controls(top):
        return {'LAYOUT PATH': '"/workspace/candidate.gds"', 'LAYOUT PRIMARY': '"'+top+'"',
                'LAYOUT SYSTEM': 'GDSII'}

    def _lvs_controls(self, top, *, execute_erc=True):
        libraries = [self.runtime.pdk_file(path)[1] for path in self.configuration.lvs.source_libraries]
        query = (' CCI' if self.configuration.connectivity == 'cci' else ' XRC') if self.check == 'rc' else ''
        controls = self._layout_controls(top) | {
            'SOURCE PATH': ' '.join('"'+path+'"' for path in ['/workspace/source.spice', *libraries]),
            'SOURCE PRIMARY': '"'+top+'"', 'SOURCE SYSTEM': 'SPICE',
            'LVS REPORT': '"/workspace/lvs.report"', 'LVS IGNORE PORTS': 'NO',
            'LVS CHECK PORT NAMES': 'YES', 'VIRTUAL CONNECT COLON': 'NO',
            'ERC RESULTS DATABASE': '"/workspace/erc.results"',
            'ERC SUMMARY REPORT': '"/workspace/erc.summary"'}
        if execute_erc:
            controls['LVS EXECUTE ERC'] = 'YES'
        controls['MASK SVDB DIRECTORY'] = '"/workspace/svdb" QUERY' + query
        return controls

    def _rule_deck(self, controls):
        path, _ = self.runtime.pdk_file(self.configuration.rules.deck)
        includes = {original: self.runtime.pdk_file(replacement)[1]
                    for original, replacement in self.configuration.rules.includes.items()}
        if self.configuration.rules.rule_control:
            self.runtime.control_path(self.configuration.rules.rule_control)
            raw = self.runtime.control_files[self.configuration.rules.rule_control[1:]]
        elif self.configuration.drc.deck_member:
            with tarfile.open(path) as archive:
                member = archive.getmember(self.configuration.drc.deck_member)
                if not member.isfile():
                    raise ValueError('Archived DRC deck must be a regular file')
                raw = archive.extractfile(member).read().decode(errors='surrogateescape')
        else:
            raw = path.read_text(errors='surrogateescape')
        for original, replacement in self.configuration.rules.inline_includes.items():
            included = self.runtime.pdk_file(replacement)[0].read_text(errors='surrogateescape')
            literal = re.escape(original)
            raw, count = re.subn(r'(?im)^\s*include\s+(?:"'+literal+'"|'+literal+r')\s*$',
                                 lambda _, included=included: included, raw)
            if count != 1:
                raise ValueError('Inline Calibre include must match exactly once')
        text = control_deck(raw, controls, includes)
        text = bind_text_variables(text, self.configuration.rules.text_variables)
        for name, value in self.configuration.rules.defines.items():
            if (not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name)
                    or not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.+-]+', value)):
                raise ValueError('Invalid Calibre define')
            text, count = re.subn(r'(?im)^\s*#DEFINE\s+'+re.escape(name)+r'\s+\S+[^\n]*$',
                                  '#DEFINE '+name+' '+value, text)
            if count != 1:
                raise ValueError('Calibre define must match exactly once')
        for name in self.configuration.rules.rule_includes:
            text = append_svrf(text, 'INCLUDE "'+self.runtime.pdk_file(name)[1]+'"')
        if self.configuration.drc.exclude_checks:
            text = append_svrf(text, 'DRC UNSELECT CHECK '+ ' '.join(self.configuration.drc.exclude_checks))
        return Asset(text.encode(errors='surrogateescape'), 'text')

    def run(self, job, inputs):
        keys(inputs, {'layout', 'task'} | ({'netlist'} if self.check != 'drc' else set()), set(), 'Calibre inputs')
        if inputs['layout'].format != 'gds' or inputs['task'].format != 'json':
            raise ValueError('Calibre requires frozen GDS and task description')
        if job.stage != ('extract' if self.check == 'rc' else 'check'):
            raise ValueError('Calibre job has wrong stage')
        task = json.loads(inputs['task'].content)
        top = task['output']['top_cell']
        if top != task['netlist_subcircuit'] or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', top):
            raise ValueError('Calibre requires identical simple layout/source top names')
        files = {'candidate.gds': inputs['layout']}
        controls = self._layout_controls(top)
        exports = {'calibre.log': 'text'}
        if self.check == 'drc':
            keys(job.parameters, set(), set(), 'Calibre DRC parameters')
            controls.update({'DRC RESULTS DATABASE': '"/workspace/drc.results" ASCII',
                             'DRC SUMMARY REPORT': '"/workspace/drc.summary"',
                             'DRC MAXIMUM RESULTS': '1000'})
            command = f'calibre -drc -hier -turbo {self.configuration.drc.threads} control.svrf > calibre.log 2>&1\n'
            exports.update({'drc.summary': 'text', 'drc.results': 'text'})
        else:
            keys(job.parameters, {'ports'} if self.check == 'rc' else set(), set(), 'Calibre parameters')
            if inputs['netlist'].format != 'spice':
                raise ValueError('Calibre requires a SPICE source')
            files['source.spice'] = inputs['netlist']
            controls = self._lvs_controls(top)
            command = ('calibre -lvs -hier -spice '+shlex.quote('/workspace/svdb/'+top+'.sp')+
                       (' -hcell '+shlex.quote(self.runtime.pdk_file(self.configuration.lvs.hcell_file)[1])
                        if self.configuration.lvs.hcell_file else '')+
                       ' control.svrf > calibre.log 2>&1\n')
            exports.update({'lvs.report': 'text', 'svdb/'+top+'.sp': 'spice'})
            if self.configuration.lvs.require_erc_summary:
                exports['erc.summary'] = 'text'
            if self.check == 'rc':
                controls['PEX NETLIST'] = '"/workspace/extracted.spice" HSPICE SOURCENAMES SINGLEFILE'
                controls['PEX EXTRACT FLOATING NETS'] = 'REDUCED'
                if self.configuration.rc.ground is not None:
                    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', self.configuration.rc.ground):
                        raise ValueError('Invalid Calibre parasitic ground')
                    controls['PEX NETLIST'] += ' GROUND '+self.configuration.rc.ground
                command += ('calibre -xrc -pdb -rcc '+
                            ('-xcell '+shlex.quote(self.runtime.pdk_file(self.configuration.rc.xcell_file)[1])+' '
                             if self.configuration.rc.xcell_file else '')+
                            'control.svrf > pdb.log 2>&1\n'
                            'calibre -xrc -fmt -all control.svrf > fmt.log 2>&1\n')
                exports.update({'pdb.log': 'text', 'fmt.log': 'text', 'extracted.spice': 'spice'})
        files['control.svrf'] = self._rule_deck(controls)
        files['run.sh'] = Asset(('set -eu\n'+self.runtime.module_setup('calibre')+'\n'+command).encode(), 'text')
        result = self._run_tool(['bash', 'run.sh'], files, exports)
        evidence = result.evidence | result.files
        if result.reason or result.returncode:
            return JobResult('error', result.reason or 'Calibre did not complete', evidence=evidence)
        try:
            if self.check == 'drc':
                _, counts = drc_summary(result.files['drc.summary'].content.decode(), top)
                return JobResult('failed' if any(counts) else 'passed',
                                 f'{counts} DRC results' if any(counts) else '', evidence=evidence)
            if not lvs_summary(result.files['lvs.report'].content.decode(), top):
                return JobResult('failed' if self.check == 'lvs' else 'error',
                                 'Calibre LVS mismatch', evidence=evidence)
            if self.check == 'lvs':
                return JobResult('passed', evidence=evidence)
            for name in ('pdb.log', 'fmt.log'):
                counts = re.findall(r'xRC Errors\s*=\s*(\d+)', result.files[name].content.decode())
                if counts != ['0']:
                    raise ValueError('Incomplete or erroneous native xRC '+name)
            raw_netlist = result.files['extracted.spice'].content.decode()
            if self.configuration.rc.mos_parameters:
                validate_mos_parameters(raw_netlist, self.configuration.rc.mos_parameters)
            text = bind_extracted_netlist(raw_netlist, top,
                              job.parameters['ports'], require_junctions=self.configuration.rc.require_junctions,
                              subcircuit_mos_models=self.configuration.rc.subcircuit_mos_models,
                              case_insensitive_ports=self.configuration.rc.case_insensitive_ports)
        except (ValueError, KeyError) as error:
            return JobResult('error', str(error), evidence=evidence)
        return JobResult('passed', outputs={'netlist': Asset(text.encode(), 'spice')}, evidence=evidence)


class CalibreDocker(CalibreBackend):
    """Calibre through the explicitly selected external Docker installation."""

    tool_type = DockerTool
    adapter = 'calibre-docker'

    def _make_tool(self, timeout_seconds):
        return self.tool_type(self.runtime.image, ['calibre', '-version'], timeout_seconds,
                              runtime=self.runtime)


def _rewrite_workspace_paths(name, content, root):
    """Adapt trusted generated Calibre controls; leave frozen inputs byte-exact."""
    if name in {'control.svrf', 'run.sh'}:
        return content.replace(b'/workspace/', str(root).encode()+b'/')
    return content


class CalibreNative(CalibreBackend):
    """Explicit host-licensed evaluator; never selected as a Docker fallback."""

    adapter = 'calibre-native'
    tool_failure_label = 'Calibre'

    def _make_tool(self, timeout_seconds):
        tool = NativeTool(self.runtime, timeout_seconds, failure_label=self.tool_failure_label)
        probe = tool.probe(self.runtime.module_command('calibre', ['calibre', '-version']),
                           timeout=timeout_seconds)
        self.tool_version = probe.stdout.decode(errors='replace').strip()
        if probe.returncode or not self.tool_version:
            raise ValueError('Tool did not report a complete release identity')
        return tool

    @property
    def identity(self):
        return super().identity | {'adapter': 'calibre-native',
                                  'tool_version': self.tool_version}

    def _run_tool(self, command, files, exports):
        return self.tool.run(command, files, exports, file_rewriter=_rewrite_workspace_paths,
                             failure_label=self.tool_failure_label)
