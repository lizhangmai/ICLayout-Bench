"""Calibre CCI and StarRC coupled extraction from declared vendor resources."""

import json
import re
from pathlib import Path

from benchmarking.files import Asset, keys, relative

from ..contracts import JobResult
from ..netlists.dspf import adapt_dspf
from ..source import package_source
from .calibre import CalibreNative, lvs_summary


def command_setting(text, name, value):
    """Replace one declared command while preserving vendor extraction policy."""
    pattern = r'(?m)^' + re.escape(name) + r':[^\n]*$'
    text, count = re.subn(pattern, lambda _: name + ': ' + str(value), text)
    if count != 1:
        raise ValueError('StarRC command must occur exactly once: ' + name)
    return text


class CalibreStarRCNative(CalibreNative):
    """Operator host evaluator using frozen GDS/CDL and vendor CCI templates."""

    connectivity = 'cci'

    def __init__(self, *, runtime, deck, technology_env, grid, mapping,
                 command_template, query_template, hcell_file, cores=1,
                 source_libraries=(), includes=None, defines=None,
                 subcircuit_mos_models=(), require_junctions=True,
                 case_insensitive_ports=False, timeout_seconds=7200, pdk_root_env=None,
                 extraction_mode=None, device_pin_file=None):
        if type(cores) is not int or not 1 <= cores <= 8:
            raise ValueError('StarRC cores must be from 1 to 8')
        if extraction_mode not in (None, 'RC'):
            raise ValueError('StarRC extraction mode must be RC')
        super().__init__(runtime=runtime, check='rc', deck=deck,
                         source_libraries=source_libraries, includes=includes, defines=defines,
                         subcircuit_mos_models=subcircuit_mos_models,
                         require_junctions=require_junctions,
                         case_insensitive_ports=case_insensitive_ports,
                         timeout_seconds=timeout_seconds, pdk_root_env=pdk_root_env)
        technology = self.runtime.environment.get(technology_env)
        if not technology or '..' in Path(technology).parts:
            raise ValueError('StarRC technology must be inside a declared resource mount')
        mounts = [m for m in self.runtime.mounts if not m.get('credential')
                  and (Path(m['target']) == Path(technology)
                       or Path(m['target']) in Path(technology).parents)]
        if len(mounts) != 1:
            raise ValueError('StarRC technology must be inside a declared resource mount')
        mount = mounts[0]
        host = Path(mount['source']) / Path(technology).relative_to(mount['target'])
        bindings = {
            'grid': grid, 'mapping': mapping, 'command_template': command_template,
            'query_template': query_template, 'hcell_file': hcell_file}
        if device_pin_file is not None:
            bindings['device_pin_file'] = device_pin_file
        self.resources = {key: (host / relative(value, 'StarRC resource'),
                               str(Path(technology) / relative(value, 'StarRC resource')))
                          for key, value in bindings.items()}
        self.star_options = dict(technology_env=technology_env, **bindings, cores=cores,
                                 extraction_mode=extraction_mode)
        version = self.tool.probe(self.runtime.module_command('starrc', ['StarXtract', '-v']))
        text = version.stdout.decode(errors='replace')
        releases = re.findall(r'^Version:\s*(\S+)\s*$', text, re.MULTILINE)
        builds = re.findall(r'^Built on:\s*(.+)$', text, re.MULTILINE)
        if version.returncode not in (0, 1) or not releases or len(releases) != len(builds):
            raise ValueError('Incomplete StarRC version identity')
        self.version = sorted(set(zip(releases, builds, strict=True)))

    @property
    def identity(self):
        return super().identity | {'adapter': 'calibre-starrc-native',
                                  'starrc_settings': dict(self.star_options),
                                  'starrc_version': self.version,
                                  'calibre_adapter_sha256': Asset(package_source('engine/backends/calibre.py').read_bytes(), 'python').sha256,
                                  'adapter_sha256': Asset(Path(__file__).read_bytes(), 'python').sha256}

    def run(self, job, inputs):
        keys(inputs, {'layout', 'task', 'netlist'}, set(), 'Calibre/StarRC inputs')
        keys(job.parameters, {'ports'}, {'temperature_c'}, 'StarRC parameters')
        if (job.stage != 'extract' or inputs['layout'].format != 'gds'
                or inputs['netlist'].format != 'spice' or inputs['task'].format != 'json'):
            raise ValueError('StarRC requires frozen GDS, CDL and task')
        task = json.loads(inputs['task'].content)
        top = task['output']['top_cell']
        if top != task['netlist_subcircuit'] or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', top):
            raise ValueError('StarRC requires identical simple layout/source top names')
        temperature = job.parameters.get('temperature_c', 27)
        if type(temperature) is not int or not -273 <= temperature <= 300:
            raise ValueError('Invalid StarRC temperature')
        deck = self._rule_deck(self._lvs_controls(top, execute_erc=False))
        command = self.resources['command_template'][0].read_text()
        for name, value in {'BLOCK': top, 'TCAD_GRD_FILE': self.resources['grid'][1],
                            'MAPPING_FILE': self.resources['mapping'][1],
                            'NETLIST_FILE': 'extracted.dspf', 'CALIBRE_QUERY_FILE': 'query.cmd'}.items():
            command = command_setting(command, name, value)
        if self.star_options.get('extraction_mode'):
            command = command_setting(command, 'EXTRACTION', self.star_options['extraction_mode'])
        if 'device_pin_file' in self.resources:
            command = command_setting(command, 'CALIBRE_OPTIONAL_DEVICE_PIN_FILE',
                                      self.resources['device_pin_file'][1])
        if re.search(r'(?m)^CALIBRE_RUNSET:', command):
            command = command_setting(command, 'CALIBRE_RUNSET', 'control.svrf')
        command += f'\nOPERATING_TEMPERATURE: {temperature}\nNETLIST_NODE_SECTION: YES\nNUM_CORES: {self.star_options["cores"]}\n'
        query = self.resources['query_template'][0].read_text().replace('TOP_CELL', top)
        script = ('set -eu\n'+self.runtime.module_setup('calibre')+'\n'
                  f'calibre -lvs -hier -hcell hcell.list -spice svdb/{top}.sp control.svrf > calibre.log 2>&1\n'
                  f'calibre -query_input query.cmd -query svdb {top} > query.log 2>&1\n'
                  +self.runtime.module_setup('starrc')+'\n'
                  'pids=""\n'
                  f'for i in $(seq 1 {self.star_options["cores"]}); do StarXtract star.cmd > "star-worker$i.log" 2>&1 & pids="$pids $!"; done\n'
                  'status=0\nfor p in $pids; do wait "$p" || status=1; done\n'
                  'cat star-worker*.log > starrc.log\nexit "$status"\n')
        files = {'candidate.gds': inputs['layout'], 'source.spice': inputs['netlist'],
                 'control.svrf': deck,
                 'query.cmd': Asset(query.encode(), 'text'), 'star.cmd': Asset(command.encode(), 'text'),
                 'hcell.list': Asset(self.resources['hcell_file'][0].read_bytes(), 'text'),
                 'run.sh': Asset(script.encode(), 'text')}
        exports = dict.fromkeys(['calibre.log', 'lvs.report', 'query.log', 'starrc.log'], 'text')
        exports['extracted.dspf'] = 'spice'
        result = self._run_tool(['bash', 'run.sh'], files, exports)
        evidence = result.evidence | result.files
        evidence.update({key: files[key] for key in ('control.svrf', 'query.cmd', 'star.cmd', 'run.sh')})
        if result.returncode or result.reason:
            return JobResult('error', result.reason or 'StarRC did not complete', evidence=evidence)
        try:
            if not lvs_summary(result.files['lvs.report'].content.decode(), top):
                raise ValueError('Calibre LVS mismatch before StarRC')
            log = result.files['starrc.log'].content.decode(errors='replace')
            counts = re.findall(r'Warnings:\s*\d+\s+Errors:\s*(\d+)', log)
            if (not counts or any(int(count) for count in counts)
                    or len(re.findall(r'^Done\s+Elp=', log, re.MULTILINE)) != self.star_options['cores']):
                raise ValueError('StarRC error summary is missing or reports errors')
            adapted = adapt_dspf(result.files['extracted.dspf'].content.decode(), top,
                                 job.parameters['ports'], {}, self.configuration.rc.require_junctions,
                                 subcircuit_mos_models=self.configuration.rc.subcircuit_mos_models,
                                 case_insensitive_ports=self.configuration.rc.case_insensitive_ports)
        except (ValueError, KeyError) as error:
            return JobResult('error', str(error), evidence=evidence)
        return JobResult('passed', outputs={'netlist': Asset(adapted.encode(), 'spice')}, evidence=evidence)
