"""Unmodified operator-provided Assura checks on frozen GDS and CDL inputs."""

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from benchmarking.files import Asset, keys

from ..contracts import JobResult
from ..external import ExternalRuntime
from ..netlists.dspf import adapt_dspf
from ..source import package_source
from ..tools.docker import DockerTool


def drc_runset(layout, top, deck):
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', top):
        raise ValueError('Assura requires a simple top cell name')
    for path in (str(layout), str(deck)):
        if any(ch in path for ch in '\\"\n\r\x00'):
            raise ValueError('Invalid Assura input path')
    return f'''avParameters(
 ?inputLayout ("GDS2" "{layout}")
 ?cellName "{top}"
 ?rulesFile "{deck}"
 ?runName "result"
 ?workingDirectory "."
 ?flagNon45 t
 ?flagOffGrid .005
 ?userUnits "micron"
 ?textPriOnly nil
 ?joinPins top
 ?modifyHierarchy nil
 ?avrpt t
)
'''


def drc_summary(log, summary, top):
    counts = re.findall(r'^Total\s+errors:\s+(\d+)\s+(\d+)\s*$', log, re.MULTILINE)
    rules = re.findall(r'^Total rules checked\s*=\s*(\d+)\s*$', summary, re.MULTILINE)
    cells = re.findall(r'^Total cells checked\s*=\s*(\d+)\s*$', summary, re.MULTILINE)
    if (len(counts) != 1 or len(rules) != 1 or len(cells) != 1
            or int(rules[0]) <= 0 or int(cells[0]) <= 0
            or log.count('Assura terminated normally') != 1
            or f'Top Cell is \'{top}\'' not in log
            or f'Translating structure "{top}"' not in log
            or 'End of Summary Report' not in summary):
        raise ValueError('Incomplete native Assura DRC report')
    errors = list(map(int, counts[0]))
    return {'status': 'failed' if any(errors) else 'passed', 'errors': errors,
            'execution_steps': int(rules[0]), 'cells_checked': int(cells[0])}


def lvs_runset(layout, netlist, top, extract_deck, compare_deck, binding_deck):
    # Reuse input validation, without adding DRC settings to the LVS run.
    for path in (netlist, extract_deck, compare_deck, binding_deck):
        drc_runset(layout, top, path)
    return f'''avParameters(
 ?inputLayout ("GDS2" "{layout}") ?cellName "{top}"
 ?rulesFile "{extract_deck}" ?runName "result"
 ?workingDirectory "." ?avrpt t
)
load("{compare_deck}")
avCompareRules(
 schematic(netlist(cdl "{netlist}"))
 bindingFile("{binding_deck}")
)
avLVS()
'''


def lvs_summary(log, summary, comparison, cells, top):
    rules = re.findall(r'^Total rules checked\s*=\s*(\d+)\s*$', summary, re.MULTILINE)
    checked = re.findall(r'^Total cells checked\s*=\s*(\d+)\s*$', summary, re.MULTILINE)
    row = re.findall(r'^\s*' + re.escape(top) + r'\s*\|\s*' + re.escape(top)
                     + r'[ \t]*\|[ \t]*([^\n]+?)[ \t]*$', cells, re.MULTILINE)
    if (len(rules) != 1 or len(checked) != 1 or int(rules[0]) <= 0 or int(checked[0]) <= 0
            or log.count('Assura LVS terminated normally.') != 1
            or log.count('Assura terminated normally') != 1
            or f'Top Cell is \'{top}\'' not in log
            or f'Translating structure "{top}"' not in log
            or 'End of Summary Report' not in summary
            or not comparison.strip() or len(row) != 1):
        raise ValueError('Incomplete native Assura LVS report')
    matched = comparison.strip() == 'Schematic and Layout Match'
    if matched and (row[0] != 'matched' or not cells.rstrip().endswith('Schematic and Layout Match')):
        raise ValueError('Contradictory native Assura LVS report')
    return {'status': 'passed' if matched else 'failed', 'match': matched,
            'execution_steps': int(rules[0]), 'cells_checked': int(checked[0])}


class AssuraDocker:
    def __init__(self, *, runtime, drc_deck, timeout_seconds=300):
        if not isinstance(runtime, ExternalRuntime):
            raise TypeError('Assura backend requires a resolved external runtime')
        self.runtime = runtime
        self.drc_deck = drc_deck
        self.tool = DockerTool(self.runtime.image, ['assura', '-h'], timeout_seconds,
                               runtime=self.runtime)
        version = re.findall(r'^sub-version (.+)$', self.tool.version, re.MULTILINE)
        if len(version) != 1:
            raise ValueError('Incomplete Assura version identity')
        self.tool.version = version[0].strip()

    @property
    def identity(self):
        return {'adapter': 'assura-drc-docker', 'drc_deck': self.drc_deck,
                **self.tool.identity,
                'adapter_sha256': Asset(Path(__file__).read_bytes(), 'python').sha256}

    def run(self, job, inputs):
        keys(inputs, {'layout', 'task'}, set(), 'Assura inputs')
        keys(job.parameters, set(), set(), 'Assura DRC parameters')
        if (job.stage != 'check' or inputs['layout'].format != 'gds'
                or inputs['task'].format != 'json'):
            raise ValueError('Assura requires a check with frozen GDS and task')
        top = json.loads(inputs['task'].content)['output']['top_cell']
        _, deck = self.runtime.pdk_file(self.drc_deck)
        files = {'candidate.gds': inputs['layout'],
                 'run.rsf': Asset(drc_runset('candidate.gds', top, deck).encode(), 'text')}
        result = self.tool.run(self.runtime.module_command('assura',
                               ['bash', '-c', 'assura run.rsf > assura.log 2>&1']), files,
                               {'assura.log': 'text', 'result.sum': 'text', 'result.err': 'text'})
        evidence = result.evidence | result.files | {'run.rsf': files['run.rsf']}
        if result.reason or result.returncode:
            return JobResult('error', result.reason or 'Assura did not complete', evidence=evidence)
        try:
            data = drc_summary(result.files['assura.log'].content.decode(errors='replace'),
                               result.files['result.sum'].content.decode(errors='replace'), top)
        except (ValueError, KeyError) as exc:
            return JobResult('error', str(exc), evidence=evidence)
        return JobResult(data['status'], f"{data['errors']} DRC errors" if any(data['errors']) else '',
                         evidence=evidence)


class AssuraLvsDocker:
    def __init__(self, *, runtime, extract_deck, compare_deck, binding_deck, timeout_seconds=300):
        if not isinstance(runtime, ExternalRuntime):
            raise TypeError('Assura backend requires a resolved external runtime')
        self.runtime = runtime
        self.decks = {'extract_deck': extract_deck, 'compare_deck': compare_deck,
                      'binding_deck': binding_deck}
        self.tool = DockerTool(self.runtime.image, ['assura', '-h'], timeout_seconds,
                               runtime=self.runtime)
        version = re.findall(r'^sub-version (.+)$', self.tool.version, re.MULTILINE)
        if len(version) != 1:
            raise ValueError('Incomplete Assura version identity')
        self.tool.version = version[0].strip()

    @property
    def identity(self):
        return {'adapter': 'assura-lvs-docker', **self.decks, **self.tool.identity,
                'adapter_sha256': Asset(Path(__file__).read_bytes(), 'python').sha256}

    def run(self, job, inputs):
        keys(inputs, {'layout', 'task', 'netlist'}, set(), 'Assura LVS inputs')
        keys(job.parameters, set(), set(), 'Assura LVS parameters')
        if (job.stage != 'check' or inputs['layout'].format != 'gds'
                or inputs['task'].format != 'json' or inputs['netlist'].format != 'spice'):
            raise ValueError('Assura LVS requires frozen GDS, CDL and task')
        task = json.loads(inputs['task'].content)
        top = task['output']['top_cell']
        if top != task['netlist_subcircuit']:
            raise ValueError('Assura requires identical layout and source top names')
        decks = {key: self.runtime.pdk_file(value)[1] for key, value in self.decks.items()}
        runset = lvs_runset('candidate.gds', 'source.cdl', top, **decks)
        files = {'candidate.gds': inputs['layout'], 'source.cdl': inputs['netlist'],
                 'run.rsf': Asset(runset.encode(), 'text')}
        exports = {name: 'text' for name in ['assura.log', 'result.sum', 'result.cls',
                                            'result.csm', 'result.erc']}
        result = self.tool.run(self.runtime.module_command('assura',
                               ['bash', '-c', 'assura run.rsf > assura.log 2>&1']), files, exports)
        evidence = result.evidence | result.files | {'run.rsf': files['run.rsf']}
        if result.reason or result.returncode:
            return JobResult('error', result.reason or 'Assura did not complete', evidence=evidence)
        try:
            reports = [result.files[name].content.decode(errors='replace')
                       for name in ['assura.log', 'result.sum', 'result.cls', 'result.csm']]
            data = lvs_summary(*reports, top)
        except (ValueError, KeyError) as exc:
            return JobResult('error', str(exc), evidence=evidence)
        return JobResult(data['status'], '' if data['match'] else 'Assura LVS mismatch', evidence=evidence)


class AssuraRCDocker(AssuraLvsDocker):
    """Quantus extraction from a freshly checked Assura GDS/CDL database."""

    def __init__(self, *, runtime, extract_deck, compare_deck, binding_deck,
                 qrc_technology, mos_models, resistor_models=None, bipolar_models=None,
                 require_junctions=True, junctionless_models=(), timeout_seconds=300):
        super().__init__(runtime=runtime, extract_deck=extract_deck,
                         compare_deck=compare_deck, binding_deck=binding_deck,
                         timeout_seconds=timeout_seconds)
        if (not isinstance(junctionless_models, (list, tuple))
                or any(not isinstance(m, str) or m not in mos_models for m in junctionless_models)):
            raise ValueError('Junctionless devices must name explicitly mapped process models')
        self.settings = {'qrc_technology': qrc_technology, 'mos_models': mos_models,
                         'resistor_models': resistor_models or {}, 'bipolar_models': bipolar_models or {},
                         'require_junctions': require_junctions,
                         'junctionless_models': list(junctionless_models)}
        raw = DockerTool(self.runtime.image, ['quantus', '-version'], timeout_seconds,
                         runtime=self.runtime).version
        self.quantus_version = {}
        for label in ('Version', 'Build Ref. No.', 'Build Date'):
            values = re.findall(r'^'+re.escape(label)+r'\s*:\s*(.+)$', raw, re.MULTILINE)
            if len(values) != 1:
                raise ValueError('Incomplete Quantus version identity')
            self.quantus_version[label] = values[0].strip()

    @property
    def identity(self):
        return {**super().identity, 'adapter': 'assura-rc-docker', 'settings': self.settings,
                'quantus_version': self.quantus_version,
                'spice_number_sha256': Asset(package_source('engine/netlists/spice.py').read_bytes(), 'python').sha256,
                'dspf_adapter_sha256': Asset(package_source('engine/netlists/dspf.py').read_bytes(), 'python').sha256}

    def run(self, job, inputs):
        keys(inputs, {'layout', 'task', 'netlist'}, set(), 'Assura RC inputs')
        keys(job.parameters, {'ports'}, {'temperature_c'}, 'Assura RC parameters')
        if (job.stage != 'extract' or inputs['layout'].format != 'gds'
                or inputs['task'].format != 'json' or inputs['netlist'].format != 'spice'):
            raise ValueError('Assura RC requires frozen GDS, CDL and task')
        task = json.loads(inputs['task'].content)
        top = task['output']['top_cell']
        if top != task['netlist_subcircuit']:
            raise ValueError('Assura requires identical layout and source top names')
        temperature = job.parameters.get('temperature_c', 25)
        if type(temperature) is not int or not -273 <= temperature <= 300:
            raise ValueError('Quantus temperature must be an integer from -273 to 300 C')
        decks = {key: self.runtime.pdk_file(value)[1] for key, value in self.decks.items()}
        _, technology = self.runtime.pdk_file(self.settings['qrc_technology'])
        if not re.fullmatch(r'[A-Za-z0-9_./-]+', technology):
            raise ValueError('Quantus technology path must be a simple absolute path')
        runset = lvs_runset('candidate.gds', 'source.cdl', top, **decks)
        # Assura requires coincident input/output directories and explicit GDS
        # design binding. No author OA library is consulted.
        qrc = (f'input_db -type assura -directory_name . -run_name result '
               f'-format GDS -design_file candidate.gds -design_cell_name {top} layout unused\n'
               f'process_technology -technology_directory {technology} -temperature {temperature}\n'
               'extract -type rc_coupled\n'
               'output_db -type dspf -disable_instances false -include_res_model true '
               '-include_parasitic_res_model false -include_parasitic_cap_model false\n'
               'output_setup -directory_name . -file_name extracted.dspf '
               '-net_name_space schematic -keep_temporary_files true\n')
        script = ('set -eu\n' + self.runtime.module_setup('assura') + '\n'
                  'assura run.rsf > assura.log 2>&1\n'
                  'grep -q "Schematic and Layout Match" result.cls\n'
                  + self.runtime.module_setup('quantus') + '\n'
                  'python3 wait_process_tree.py quantus -cmd qrc.cmd > qrc.log 2>&1\n')
        files = {'candidate.gds': inputs['layout'], 'source.cdl': inputs['netlist'],
                 'run.rsf': Asset(runset.encode(), 'text'), 'qrc.cmd': Asset(qrc.encode(), 'text'),
                 'run.sh': Asset(script.encode(), 'text'),
                 'wait_process_tree.py': Asset(package_source('engine/container_scripts/wait_process_tree.py').read_bytes(), 'python')}
        exports = {name: 'text' for name in ['assura.log', 'result.sum', 'result.cls',
                                            'result.csm', 'result.erc', 'qrc.log']}
        exports['extracted.dspf'] = 'spice'
        result = self.tool.run(['bash', 'run.sh'], files, exports)
        evidence = result.evidence | result.files | {k: files[k] for k in ('run.rsf', 'qrc.cmd', 'run.sh')}
        if result.reason or result.returncode:
            return JobResult('error', result.reason or 'Assura/Quantus did not complete', evidence=evidence)
        try:
            reports = [result.files[name].content.decode(errors='replace')
                       for name in ['assura.log', 'result.sum', 'result.cls', 'result.csm']]
            if not lvs_summary(*reports, top)['match']:
                raise ValueError('Assura LVS mismatch before RC extraction')
            if 'Quantus terminated normally' not in result.files['qrc.log'].content.decode(errors='replace'):
                raise ValueError('Quantus did not finish normally')
            settings = {k: v for k, v in self.settings.items() if k != 'qrc_technology'}
            text = adapt_dspf(result.files['extracted.dspf'].content.decode(), top,
                              job.parameters['ports'], **settings)
        except (ValueError, KeyError) as exc:
            return JobResult('error', str(exc), evidence=evidence)
        return JobResult('passed', outputs={'netlist': Asset(text.encode(), 'spice')}, evidence=evidence)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', choices=['drc', 'lvs'], default='drc')
    parser.add_argument('--layout', type=Path, required=True)
    parser.add_argument('--top', required=True)
    parser.add_argument('--deck', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=300)
    parser.add_argument('--pdk', type=Path,
                        help='Process manifest for Docker checks; deck paths are relative to PDK_ROOT')
    parser.add_argument('--netlist', type=Path)
    parser.add_argument('--compare-deck', type=Path)
    parser.add_argument('--binding-deck', type=Path)
    args = parser.parse_args()
    if args.pdk:
        from benchmarking.evaluation.contracts import Job

        runtime = ExternalRuntime.from_manifest(args.pdk)
        layout = Asset(args.layout.read_bytes(), 'gds')
        inputs = {'layout': layout, 'task': Asset(json.dumps({
            'output': {'top_cell': args.top}, 'netlist_subcircuit': args.top}).encode(), 'json')}
        if args.check == 'lvs':
            if not all([args.netlist, args.compare_deck, args.binding_deck]):
                parser.error('LVS requires --netlist, --compare-deck and --binding-deck')
            inputs['netlist'] = Asset(args.netlist.read_bytes(), 'spice')
            backend = AssuraLvsDocker(runtime=runtime, extract_deck=str(args.deck),
                                      compare_deck=str(args.compare_deck),
                                      binding_deck=str(args.binding_deck), timeout_seconds=args.timeout)
        else:
            if any([args.netlist, args.compare_deck, args.binding_deck]):
                parser.error('CDL and comparison decks belong to LVS')
            backend = AssuraDocker(runtime=runtime, drc_deck=str(args.deck),
                                   timeout_seconds=args.timeout)
        args.output.mkdir(parents=True, exist_ok=False)
        result = backend.run(Job(args.check, 'check', 'layout.' + args.check,
                                 (), (), (), None, '{}'), inputs)
        for name, asset in result.evidence.items():
            path = args.output / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(asset.content)
        report = {'check': args.check, 'top': args.top, 'status': result.status,
                  'reason': result.reason, 'identity': backend.identity,
                  'input_sha256': {name: asset.sha256 for name, asset in inputs.items()}}
        (args.output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'check': args.check, 'status': result.status, 'reason': result.reason}))
        return 0 if result.status == 'passed' else 1
    layout, deck = args.layout.resolve(strict=True), args.deck.resolve(strict=True)
    sources = {'layout': layout, 'deck': deck}
    if args.check == 'lvs':
        if not all([args.netlist, args.compare_deck, args.binding_deck]):
            parser.error('LVS requires --netlist, --compare-deck and --binding-deck')
        sources.update({name: getattr(args, name).resolve(strict=True)
                        for name in ['netlist', 'compare_deck', 'binding_deck']})
        runset = lvs_runset(layout, sources['netlist'], args.top, deck,
                            sources['compare_deck'], sources['binding_deck'])
    else:
        if any([args.netlist, args.compare_deck, args.binding_deck]):
            parser.error('CDL and comparison decks belong to LVS')
        runset = drc_runset(layout, args.top, deck)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'run.rsf').write_text(runset)
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    report = {'check': args.check, 'top': args.top, 'command': ['assura', 'run.rsf']}
    for name, path in sources.items():
        report.update({name: str(path), name + '_sha256': sha(path)})
    environment = {key: value for key, value in os.environ.items()
                   if key not in {'OA_HOME', 'OA_PLUGIN_PATH', 'LD_LIBRARY_PATH'}}
    try:
        with (args.output / 'assura.log').open('w') as log:
            proc = subprocess.run(['assura', 'run.rsf'], cwd=args.output, stdout=log,
                                  stderr=subprocess.STDOUT, timeout=args.timeout, check=False,
                                  env=environment)
        report['returncode'] = proc.returncode
        if proc.returncode:
            raise ValueError('Assura did not complete')
        reports = [(args.output / name).read_text(errors='replace')
                   for name in ['assura.log', 'result.sum']]
        if args.check == 'lvs':
            reports.extend((args.output / name).read_text(errors='replace')
                           for name in ['result.cls', 'result.csm'])
            report.update(lvs_summary(*reports, args.top))
        else:
            report.update(drc_summary(*reports, args.top))
        if any(sha(path) != report[name + '_sha256'] for name, path in sources.items()):
            raise ValueError('Assura inputs changed during the run')
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        report.update(status='error', reason=str(exc))
    (args.output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
