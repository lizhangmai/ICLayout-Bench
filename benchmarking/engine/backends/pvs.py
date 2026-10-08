"""Cadence PVS and Quantus container adapter."""

import json
import re
import shlex
from pathlib import Path

from benchmarking.files import Asset, keys

from ..contracts import JobResult
from ..external import ExternalRuntime
from ..netlists.dspf import adapt_dspf
from ..source import package_source
from ..tools.docker import DockerTool


def _quote(value):
    return shlex.quote(str(value))


def _lvs_passed(text, top):
    verdicts = re.findall(r'Run Result\s*:\s*(\S+)', text)
    return (verdicts == ['MATCH'] and 'END OF REPORT' in text
            and 'Extraction Clean' in text
            and re.search(r'Top Cell\s*:\s*'+re.escape(top)+r'\s+<vs>\s+'+re.escape(top)+r'\s*$', text, re.MULTILINE) is not None
            and re.search(r'Cells matched\s*\|\s*[1-9]\d*', text) is not None
            and all(re.search(re.escape(name)+r'\s*\|\s*0\s*$', text, re.MULTILINE) is not None
                    for name in ('Cells not run', 'Cells which mismatch',
                                 'Cells with parameter mismatches', 'Cells with mismatched instance subtypes',
                                 'Cells that have been blackboxed')))


class PvsDocker:
    def __init__(self, *, runtime, check, drc_deck=None, lvs_deck=None,
                 lvs_includes=None, qrc_technology=None, mos_models=None,
                 require_junctions=False, resistor_models=None, bipolar_models=None,
                 timeout_seconds=300):
        if check not in {'drc', 'lvs', 'rc'}:
            raise ValueError('Unknown PVS operation')
        if not isinstance(runtime, ExternalRuntime):
            raise TypeError('Cadence backend requires a resolved external runtime')
        self.runtime = runtime
        self.check = check
        self.settings = {'drc_deck': drc_deck, 'lvs_deck': lvs_deck,
                         'lvs_includes': lvs_includes or {}, 'qrc_technology': qrc_technology,
                         'mos_models': mos_models or {}, 'require_junctions': require_junctions,
                         'resistor_models': resistor_models or {},
                         'bipolar_models': bipolar_models or {}}
        self.tool = DockerTool(self.runtime.image, ['pvs', '-version'], timeout_seconds, runtime=self.runtime)
        self.quantus_version = None
        if check == 'rc':
            raw = DockerTool(self.runtime.image, ['quantus', '-version'],
                             timeout_seconds, runtime=self.runtime).version
            self.quantus_version = {}
            # Startup diagnostics can contain the current time. Bind the native
            # release/build fields so a new process can verify the same witness.
            for label in ('Version', 'Build Ref. No.', 'Build Date'):
                values = re.findall(r'^'+re.escape(label)+r'\s*:\s*(.+)$', raw, re.MULTILINE)
                if len(values) != 1:
                    raise ValueError('Incomplete Quantus version identity')
                self.quantus_version[label] = values[0].strip()

    @property
    def identity(self):
        return {'adapter': 'pvs-docker', 'check': self.check, 'settings': self.settings,
                'quantus_version': self.quantus_version, **self.tool.identity,
                'adapter_sha256': Asset(Path(__file__).read_bytes(), 'python').sha256,
                'dspf_adapter_sha256': Asset(package_source('engine/netlists/dspf.py').read_bytes(), 'python').sha256,
                'spice_number_sha256': Asset(package_source('engine/netlists/spice.py').read_bytes(), 'python').sha256,
                'process_waiter_sha256': Asset(package_source('engine/container_scripts/wait_process_tree.py').read_bytes(), 'python').sha256}

    def run(self, job, inputs):
        keys(inputs, {'layout', 'task'} | ({'netlist'} if self.check != 'drc' else set()), set(), 'PVS inputs')
        if inputs['layout'].format != 'gds' or inputs['task'].format != 'json':
            raise ValueError('PVS requires frozen GDS and task description')
        if job.stage != ('extract' if self.check == 'rc' else 'check'):
            raise ValueError('PVS job has wrong stage')
        task = json.loads(inputs['task'].content)
        top = task['output']['top_cell']
        if top != task['netlist_subcircuit'] or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', top):
            raise ValueError('PVS currently requires identical simple top and source names')
        files = {'candidate.gds': inputs['layout']}
        evidence = {}
        if self.check == 'drc':
            keys(job.parameters, set(), set(), 'PVS DRC parameters')
            _, deck = self.runtime.pdk_file(self.settings['drc_deck'])
            command = ['pvs', '-drc', '-gds', 'candidate.gds', '-top_cell', top,
                       '-ascrdb', 'drc.db', '-log', 'pvs.log', deck]
            exports = {'pvs.log': 'text', 'drc.db': 'text', 'result.sum': 'text'}
        else:
            path, _ = self.runtime.pdk_file(self.settings['lvs_deck'])
            deck = path.read_text()
            for original, replacement in self.settings['lvs_includes'].items():
                _, target = self.runtime.pdk_file(replacement)
                pattern = re.compile(r'^include\s+'+re.escape(original)+r'\s*$', re.MULTILINE)
                if len(pattern.findall(deck)) != 1:
                    raise ValueError('LVS include adaptation did not match exactly once')
                deck = pattern.sub('include '+target, deck)
            files['interface.ctl'] = Asset((f'lvs_report_file "{top}.lvsrpt";\n'
                'lvs_compare_port_names yes;\nlvs_ignore_ports no;\n').encode(), 'text')
            files.update({'lvs.rul': Asset(deck.encode(), 'text'), 'source.spice': inputs['netlist']})
            command = ['pvs', '-lvs', '-gds', 'candidate.gds', '-top_cell', top,
                       '-source_cdl', 'source.spice', '-source_top_cell', top,
                       '-rc_data', '-spice', 'connectivity.spice', '-control', 'interface.ctl',
                       '-log', 'pvs.log', 'lvs.rul']
            exports = {'pvs.log': 'text', f'{top}.lvsrpt.cls': 'text',
                       'connectivity.spice': 'spice'}
            if self.check == 'rc':
                keys(job.parameters, {'ports'}, {'temperature_c'}, 'Quantus parameters')
                temperature = job.parameters.get('temperature_c', 25)
                if type(temperature) is not int or not -273 <= temperature <= 300:
                    raise ValueError('Quantus temperature must be an integer from -273 to 300 C')
                _, technology = self.runtime.pdk_file(self.settings['qrc_technology'])
                if not re.fullmatch(r'[A-Za-z0-9_./-]+', technology):
                    raise ValueError('Quantus technology path must be a simple absolute path')
                # Keep reduction intermediates until all orphaned workers exit;
                # the container workspace is discarded after evidence export.
                qrc = (f'input_db -type pvs -directory_name svdb -run_name {top}\n'
                       f'process_technology -technology_directory {technology} -temperature {temperature}\n'
                       'extract -type rc_coupled\n'
                       'output_db -type dspf -disable_instances false '
                       + ('-include_res_model true ' if self.settings['resistor_models'] else '') +
                       '-include_parasitic_res_model false -include_parasitic_cap_model false\n'
                       'output_setup -directory_name pex -file_name extracted.dspf '
                       '-net_name_space schematic -keep_temporary_files true\n')
                files['qrc.cmd'] = Asset(qrc.encode(), 'text')
                files['wait_process_tree.py'] = Asset(package_source('engine/container_scripts/wait_process_tree.py').read_bytes(), 'python')
                script = (self.runtime.module_setup('pvs') + '\n' + shlex.join(command) + '\n' +
                          f"grep -Eq 'Run Result[[:space:]]*:[[:space:]]*MATCH' {_quote(top+'.lvsrpt.cls')}\n" +
                          self.runtime.module_setup('quantus') + '\n' +
                          'python3 wait_process_tree.py quantus -cmd qrc.cmd > qrc.log 2>&1\n')
                files['run.sh'] = Asset(('set -eu\n'+script).encode(), 'text')
                command = ['bash', 'run.sh']
                exports.update({'qrc.log': 'text', 'extracted.dspf': 'spice'})
            else:
                keys(job.parameters, set(), set(), 'PVS LVS parameters')
        result = self.tool.run(command, files, exports)
        evidence.update(result.evidence | result.files)
        if result.reason or result.returncode:
            return JobResult('error', result.reason or 'Cadence tool did not complete', evidence=evidence)
        if self.check == 'drc':
            log = result.files['pvs.log'].content.decode(errors='replace')
            count = re.findall(r'Total DRC Results\s*:\s*(\d+)\s*\(\d+\)', log)
            rules = re.findall(r'Total DRC RuleChecks\s*:\s*(\d+)', log)
            if 'Design Rule Check Finished Normally.' not in log or len(count) != 1 or len(rules) != 1 or int(rules[0]) == 0:
                return JobResult('error', 'Incomplete native PVS DRC report', evidence=evidence)
            return JobResult('failed' if int(count[0]) else 'passed',
                             f'{count[0]} DRC violations' if int(count[0]) else '', evidence=evidence)
        report = result.files[f'{top}.lvsrpt.cls'].content.decode(errors='replace')
        if not _lvs_passed(report, top):
            verdicts = re.findall(r'Run Result\s*:\s*(\S+)', report)
            status = ('failed' if self.check == 'lvs' and verdicts == ['MISMATCH']
                      and 'END OF REPORT' in report else 'error')
            return JobResult(status, 'PVS did not establish a complete non-blackboxed match', evidence=evidence)
        if self.check == 'lvs':
            return JobResult('passed', evidence=evidence)
        if 'Quantus terminated normally' not in result.files['qrc.log'].content.decode(errors='replace'):
            return JobResult('error', 'Quantus did not finish normally', evidence=evidence)
        try:
            text = adapt_dspf(result.files['extracted.dspf'].content.decode(), top,
                              job.parameters['ports'], self.settings['mos_models'],
                              self.settings['require_junctions'], self.settings['resistor_models'],
                              self.settings['bipolar_models'])
        except ValueError as error:
            return JobResult('error', f'DSPF adaptation failed: {error}', evidence=evidence)
        return JobResult('passed', outputs={'netlist': Asset(text.encode(), 'spice')}, evidence=evidence)
