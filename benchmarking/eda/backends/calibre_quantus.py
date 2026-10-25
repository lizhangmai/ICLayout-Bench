"""Calibre CCI connectivity and Quantus RC with declared host resources."""

import json
import re
from pathlib import Path

from benchmarking.eda.backends.calibre import CalibreNative, lvs_summary
from benchmarking.eda.netlists.dspf import ExtractionRejected, bind_extracted_netlist
from benchmarking.evaluation.contracts import JobResult
from benchmarking.evidence.identity import package_source
from benchmarking.files import Asset, keys


def query_commands(top):
    """Use the documented CCI annotated geometry and device-template interface."""
    prefix = 'query_output/' + top
    return '\n'.join([
        'gds netprop number 5', 'gds placeprop number 6', 'gds devprop number 7',
        'response file '+prefix+'.gds.map', 'gds seed property device original',
        'gds map', 'response direct', 'gds write '+prefix+'.agf',
        'layout netlist trivial pins YES', 'layout netlist empty cells YES',
        'layout netlist names NONE', 'layout netlist primitive device subckts NO',
        'layout netlist hierarchy AGF',
        'layout nametable write '+prefix+'.lnn EXPAND_CELLS',
        'layout netlist device templates YES',
        'layout netlist write '+prefix+'_pin_xy.spi',
        'source hierarchy write '+prefix+'.sph',
        'layout hierarchy write '+prefix+'.lph',
        'net xref write '+prefix+'.nxf BOX LNXF',
        'instance xref write '+prefix+'.ixf',
        'port table write '+prefix+'.ports',
        'port table cells write '+prefix+'.ports_cells',
        'response file '+prefix+'.devtab', 'device table', 'response direct',
        'lvs settings report write '+prefix+'.lvs_settings', 'terminate', ''
    ])


class CalibreQuantusNative(CalibreNative):
    """Trusted native evaluator, with no solver workspace or source substitution."""

    connectivity = 'cci'
    tool_failure_label = 'Calibre/Quantus'
    process_exit_grace_seconds = 60

    def __init__(self, *, runtime, deck, technology_env, ground, source_libraries=(),
                 includes=None, defines=None,
                 require_junctions=True, case_insensitive_ports=False,
                 subcircuit_mos_models=(), timeout_seconds=600, pdk_root_env=None):
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', ground):
            raise ValueError('Invalid Quantus parasitic reference')
        super().__init__(check='rc', runtime=runtime, deck=deck, ground=ground,
                         source_libraries=source_libraries, includes=includes, defines=defines,
                         require_junctions=require_junctions,
                         case_insensitive_ports=case_insensitive_ports,
                         subcircuit_mos_models=subcircuit_mos_models,
                         timeout_seconds=timeout_seconds, pdk_root_env=pdk_root_env)
        technology = self.runtime.environment.get(technology_env)
        if (not technology or not re.fullmatch(r'[A-Za-z0-9_./-]+', technology)
                or '..' in Path(technology).parts
                or not any((Path(m['target']) == Path(technology)
                            or Path(m['target']) in Path(technology).parents)
                           and not m.get('credential')
                           for m in self.runtime.mounts)):
            raise ValueError('Quantus technology must be inside a declared resource mount')
        self.technology = technology
        self.technology_env = technology_env
        version_result = self.tool.probe(self.runtime.module_command('quantus', ['quantus', '-version']),
                                         timeout=self.tool.timeout_seconds)
        if version_result.returncode:
            raise ValueError('Incomplete Quantus version identity')
        version = version_result.stdout.decode(errors='replace')
        self.quantus_version = {}
        for label in ('Version', 'Build Ref. No.', 'Build Date'):
            values = re.findall(r'^'+re.escape(label)+r'\s*:\s*(.+)$', version, re.MULTILINE)
            if len(values) != 1:
                raise ValueError('Incomplete Quantus version identity')
            self.quantus_version[label] = values[0].strip()

    @property
    def identity(self):
        return super().identity | {
            'adapter': 'calibre-quantus-native', 'quantus_version': self.quantus_version,
            'process_exit_grace_seconds': self.process_exit_grace_seconds,
            'technology_env': self.technology_env,
            'adapter_sha256': Asset(Path(__file__).read_bytes(), 'python').sha256,
            'calibre_adapter_sha256': Asset(package_source('eda/backends/calibre.py').read_bytes(), 'python').sha256,
            'worker_launcher_sha256': Asset(package_source('execution/_scripts/wait_process_tree.py').read_bytes(), 'python').sha256}

    def run(self, job, inputs):
        keys(inputs, {'layout', 'task', 'netlist'}, set(), 'Calibre/Quantus inputs')
        keys(job.parameters, {'ports'}, {'temperature_c'}, 'Quantus parameters')
        if (job.stage != 'extract' or inputs['layout'].format != 'gds'
                or inputs['task'].format != 'json' or inputs['netlist'].format != 'spice'):
            raise ValueError('Calibre/Quantus requires frozen GDS, task and SPICE source')
        task = json.loads(inputs['task'].content)
        top = task['output']['top_cell']
        if top != task['netlist_subcircuit'] or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', top):
            raise ValueError('Calibre/Quantus requires identical simple layout/source top names')
        temperature = job.parameters.get('temperature_c', 27)
        if type(temperature) is not int or not -273 <= temperature <= 300:
            raise ValueError('Quantus temperature must be an integer from -273 to 300 C')
        if self.configuration.rc.ground not in job.parameters['ports']:
            raise ValueError('Quantus parasitic reference must be a declared port')
        text = self._rule_deck(self._lvs_controls(top, execute_erc=False))
        qrc = (f'input_db -type calibre -directory_name query_output -run_name {top} '
               f'-layer_map_file query_output/{top}.gds.map '
               '-net_property_value 5 -instance_property_value 6 -device_property_value 7\n'
               f'process_technology -technology_directory {self.technology} -temperature {temperature}\n'
               f'capacitance -ground_net {self.configuration.rc.ground}\n'
               'extract -type rc_coupled\n'
               'output_db -type dspf -disable_instances false -include_res_model true '
               '-include_parasitic_res_model false -include_parasitic_cap_model false\n'
               'output_setup -directory_name pex -file_name extracted.dspf '
               '-net_name_space schematic -keep_temporary_files true\n')
        script = ('set -eu\n'+self.runtime.module_setup('calibre')+'\n'
                  'calibre -lvs -hier control.svrf > calibre.log 2>&1\n'
                  'mkdir query_output\n'
                  f'calibre -query svdb {top} -query_input query.cmd > query.log 2>&1\n'
                  +self.runtime.module_setup('quantus')+'\n'
                  'python3 wait_process_tree.py --completion-log qrc.log '
                  "--completion-marker 'Quantus terminated normally' "
                  '--exit-report qrc.exit.json '
                  f'--exit-grace-seconds {self.process_exit_grace_seconds} '
                  'quantus -cmd qrc.cmd > qrc.console.log 2>&1\n')
        files = {'candidate.gds': inputs['layout'], 'source.spice': inputs['netlist'],
                 'control.svrf': text,
                 'query.cmd': Asset(query_commands(top).encode(), 'text'),
                 'qrc.cmd': Asset(qrc.encode(), 'text'), 'run.sh': Asset(script.encode(), 'text'),
                 'wait_process_tree.py': Asset(package_source('execution/_scripts/wait_process_tree.py').read_bytes(), 'python')}
        exports = dict.fromkeys(['calibre.log', 'lvs.report', 'erc.summary', 'query.log',
                                'qrc.log', 'qrc.console.log'], 'text')
        exports['qrc.exit.json'] = 'json'
        exports.update({'extracted.dspf': 'spice', 'query_output/'+top+'_pin_xy.spi': 'spice'})
        result = self._run_tool(['bash', 'run.sh'], files, exports)
        evidence = result.evidence | result.files
        evidence.update({n: files[n] for n in ['control.svrf', 'query.cmd', 'qrc.cmd', 'run.sh']})
        lifecycle = evidence.get('qrc.exit.json')
        exit_report = None
        if lifecycle is not None:
            try:
                exit_report = json.loads(lifecycle.content)
                if (exit_report['schema'] != 'iclayout-tool-exit-v1'
                        or type(exit_report['returncode']) is not int
                        or exit_report['returncode'] != result.returncode
                        or type(exit_report['command_returncode']) is not int
                        or result.returncode == 0 and exit_report['command_returncode'] != 0
                        or type(exit_report['completion_seen']) is not bool
                        or type(exit_report['exit_grace_exceeded']) is not bool
                        or exit_report['exit_grace_seconds'] != self.process_exit_grace_seconds
                        or not isinstance(exit_report['processes'], list)
                        or exit_report['exit_grace_exceeded'] and (
                            not exit_report['completion_seen'] or result.returncode != 124)):
                    raise ValueError('Inconsistent process-exit report')
            except (ValueError, KeyError, TypeError):
                return _execution_error('Invalid Quantus process-exit report', evidence)
        elif result.returncode == 0 and not result.reason:
            return _execution_error('Missing Quantus process-exit report', evidence)
        if exit_report is not None and exit_report['exit_grace_exceeded']:
            reason = ('Quantus reported completion but its process tree did not exit within '
                      f'{self.process_exit_grace_seconds} seconds')
            return _execution_error(reason, evidence)
        if result.reason or result.returncode != 0:
            return _execution_error(result.reason or 'Calibre/Quantus did not complete', evidence)
        try:
            if not lvs_summary(result.files['lvs.report'].content.decode(), top):
                return JobResult('failed', 'Calibre LVS mismatch before Quantus extraction', evidence=evidence)
            if 'Quantus terminated normally' not in result.files['qrc.log'].content.decode(errors='replace'):
                raise ValueError('Quantus did not finish normally')
        except (ValueError, KeyError) as error:
            return JobResult('error', str(error), evidence=evidence)
        try:
            adapted = bind_extracted_netlist(result.files['extracted.dspf'].content.decode(), top,
                                 job.parameters['ports'], require_junctions=self.configuration.rc.require_junctions,
                                 subcircuit_mos_models=self.configuration.rc.subcircuit_mos_models,
                                 case_insensitive_ports=self.configuration.rc.case_insensitive_ports)
        except ExtractionRejected as error:
            return JobResult('failed', str(error), evidence=evidence)
        except (ValueError, KeyError) as error:
            return JobResult('error', str(error), evidence=evidence)
        return JobResult('passed', outputs={'netlist': Asset(adapted.encode(), 'spice')}, evidence=evidence)


def _execution_error(reason, evidence):
    """A failed tool lifecycle cannot become a candidate rejection/zero score."""
    evidence['execution_error'] = Asset(reason.encode(), 'text')
    return JobResult('error', reason, evidence=evidence)
