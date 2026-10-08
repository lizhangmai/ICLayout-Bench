"""Independent GDS DRC and extracted-layout LVS using pinned Magic/Netgen rules."""

import json
import re
from pathlib import Path

from benchmarking.bundles import load_bundle
from benchmarking.evaluation.contracts import Job
from benchmarking.files import Asset, keys, relative, text

from ..contracts import JobResult
from ..tools.docker import DockerTool
from .magic import _tcl_word


def netgen_verdict(records, top, subcircuit):
    """Require a nonempty top comparison and no hierarchy/property/pin mismatch."""
    if not isinstance(records, list) or not records:
        raise ValueError("Missing Netgen comparisons")
    tops = [r for r in records if r.get('name') == [top, subcircuit]]
    if len(tops) != 1:
        raise ValueError("Missing or ambiguous Netgen top comparison")
    for record in records:
        # Netgen emits a pin-only record when equating primitive model classes.
        if set(record) == {'pins'}:
            pins = record['pins']
            if not isinstance(pins, list) or len(pins) != 2:
                raise ValueError('Malformed primitive pin comparison')
            if pins[0] != pins[1]:
                return False
            continue
        for field in ('name', 'pins', 'nets', 'devices'):
            if not isinstance(record.get(field), list) or len(record[field]) != 2:
                raise ValueError(f"Malformed Netgen {field}")
        if any(record.get(k) for k in ('badnets', 'badelements', 'properties')):
            return False
        if record['nets'][0] != record['nets'][1]:
            return False
        left, right = record['pins']
        if len(left) != len(right) or any(a.casefold() != b.casefold() or not a
                                        for a, b in zip(left, right, strict=True)):
            return False
        counts = [sum(count for _, count in side) for side in record['devices']]
        if counts[0] != counts[1]:
            return False
    if not all(sum(count for _, count in side) > 0 for side in tops[0]['devices']):
        raise ValueError("Empty or black-box top comparison")
    return True


class MagicPhysicalDocker:
    """Validate the submitted GDS; rules and styles are frozen host settings.

    LVS extracts the GDS independently and compares it with the source netlist.
    Neither a candidate-supplied extraction nor a generator's check is accepted.
    """

    def __init__(self, *, image, check, support, technology, tech_name,
                 style, setup=None, grid_subdivision=1, timeout_seconds=180):
        if check not in {'drc', 'lvs'}:
            raise ValueError("Magic physical check must be drc or lvs")
        if type(grid_subdivision) is not int or grid_subdivision < 1:
            raise ValueError("Grid subdivision must be a positive integer")
        if (check == 'lvs') != (setup is not None):
            raise ValueError("Only LVS requires a Netgen setup")
        self.check, self.grid_subdivision = check, grid_subdivision
        self.support = load_bundle(Path(support))
        self.technology = relative(technology, 'Magic technology')
        self.setup = relative(setup, 'Netgen setup') if setup is not None else None
        for path in (self.technology, self.setup):
            if path is not None and path not in dict(self.support.files):
                raise ValueError(f"Missing physical-check resource: {path}")
        self.tech_name, self.style = text(tech_name, 'technology name'), text(style, 'check style')
        self.tool = DockerTool(image, ['magic', '--version'], timeout_seconds)
        self.netgen = DockerTool(image, ['netgen', '-batch', 'quit'], timeout_seconds) if check == 'lvs' else None

    @property
    def identity(self):
        return {'adapter': 'magic-physical-docker', 'check': self.check,
                **self.tool.identity, 'netgen': self.netgen.identity if self.netgen else None,
                'adapter_sha256': Asset(Path(__file__).read_bytes(), 'python').sha256,
                'support_sha256': self.support.manifest.sha256, 'technology': self.technology,
                'tech_name': self.tech_name, 'style': self.style, 'setup': self.setup,
                'grid_subdivision': self.grid_subdivision}

    def run(self, job: Job, inputs):
        keys(inputs, {'layout', 'netlist'} if self.check == 'lvs' else {'layout'}, {'task'}, 'Magic check inputs')
        if (job.stage != 'check' or job.gate not in {None, self.check} or job.outputs
                or inputs['layout'].format != 'gds'):
            raise ValueError("Magic physical checks require a GDS check job without outputs")
        keys(job.parameters, set(), {'top_cell', 'subcircuit'} if self.check == 'lvs' else {'top_cell'}, 'Magic parameters')
        params = dict(job.parameters)
        if 'task' in inputs:
            task = json.loads(inputs['task'].content)
            configured = {'top_cell': task['output']['top_cell']}
            if self.check == 'lvs':
                configured['subcircuit'] = task['netlist_subcircuit']
            for key, value in configured.items():
                if key in params and params[key] != value:
                    raise ValueError(f"Magic {key} differs from task configuration")
                params[key] = value
        top = text(params.get('top_cell'), 'top cell')
        script = ['if {[catch {', 'drc off',
                  f'tech load {_tcl_word("/workspace/support/" + self.technology)}',
                  f'if {{[tech name] ne {_tcl_word(self.tech_name)}}} {{error "Wrong technology"}}',
                  f'scalegrid 1 {self.grid_subdivision}', 'gds read candidate.gds',
                  f'if {{[cellname list exists {_tcl_word(top)}] eq "0"}} {{error "Missing top cell"}}',
                  f'load {_tcl_word(top)}', 'select top cell', 'expand']
        if self.check == 'drc':
            script += [f'drc style {_tcl_word(self.style)}',
                       f'if {{[drc list style] ne {_tcl_word(self.style)}}} {{error "Wrong DRC style"}}',
                       'drc euclidean on', 'drc check', 'drc catchup',
                       'set f [open drc-markers.txt w]', 'puts $f [drc listall why]', 'close $f',
                       'set f [open drc-count.txt w]', 'puts $f [drc list count total]', 'close $f']
            exports = {'drc-markers.txt': 'text', 'drc-count.txt': 'text'}
        else:
            if inputs['netlist'].format != 'spice':
                raise ValueError("LVS source must be a SPICE netlist")
            text(params.get('subcircuit'), 'source subcircuit')
            script += [f'extract style {_tcl_word(self.style)}', 'extract all', 'ext2spice lvs',
                       'ext2spice scale off', 'ext2spice -o extracted.spice']
            exports = {'extracted.spice': 'spice'}
        script += ['set f [open complete.txt w]', 'puts $f complete', 'close $f',
                   '} message]} {puts stderr $message; exit 2}', 'quit -noprompt']
        files = {'candidate.gds': inputs['layout'], 'empty.magicrc': Asset(b'', 'text'),
                 'check.tcl': Asset(('\n'.join(script) + '\n').encode(), 'tcl'), **self.support.mounted_files()}
        result = self.tool.run(['magic', '-dnull', '-noconsole', '-rcfile', 'empty.magicrc', 'check.tcl'],
                               files, {**exports, 'complete.txt': 'text'})
        evidence = {**self.support.evidence(), **result.evidence, **result.files, 'script': files['check.tcl']}
        if result.reason or result.returncode:
            return JobResult('error', result.reason or 'Magic did not complete', evidence=evidence)
        console = result.evidence.get('console', Asset(b'', 'text')).content.decode(errors='replace')
        if re.search(r'unknown layer|unrecognized|unmapped|not found|couldn.t|cannot|missing gate connection|orphaned node', console, re.IGNORECASE):
            return JobResult('error', 'Magic reported an input or extraction error', evidence=evidence)
        try:
            if result.files['complete.txt'].content.strip() != b'complete':
                raise ValueError('Incomplete Magic check')
            if self.check == 'drc':
                count = int(result.files['drc-count.txt'].content)
                if count < 0:
                    raise ValueError('Invalid DRC count')
                return JobResult('passed' if count == 0 else 'failed',
                                 '' if count == 0 else f'Magic reported {count} DRC violations', evidence=evidence)
            subcircuit = params['subcircuit']
            netgen_script = ('if {[catch {\n'
                             f'lvs [list extracted.spice {_tcl_word(top)}] '
                             f'[list source.spice {_tcl_word(subcircuit)}] '
                             f'{_tcl_word("/workspace/support/" + self.setup)} comparison.out -json\n'
                             'set f [open complete.txt w]; puts $f complete; close $f\n'
                             '} message]} {puts stderr $message; exit 2}\nquit\n')
            netgen = self.netgen.run(['netgen', '-batch', 'source', 'compare.tcl'],
                                    {'extracted.spice': result.files['extracted.spice'],
                                     'source.spice': inputs['netlist'],
                                     'compare.tcl': Asset(netgen_script.encode(), 'tcl'),
                                     **self.support.mounted_files()},
                                    {'comparison.json': 'json', 'comparison.out': 'text', 'complete.txt': 'text'})
            evidence.update({f'netgen:{k}': v for k, v in (netgen.evidence | netgen.files).items()})
            evidence['netgen_script'] = Asset(netgen_script.encode(), 'tcl')
            if netgen.reason or netgen.returncode:
                return JobResult('error', netgen.reason or 'Netgen did not complete', evidence=evidence)
            if netgen.files['complete.txt'].content.strip() != b'complete':
                raise ValueError('Incomplete Netgen check')
            passed = netgen_verdict(json.loads(netgen.files['comparison.json'].content), top, subcircuit)
            return JobResult('passed' if passed else 'failed', '' if passed else 'Netgen LVS mismatch', evidence=evidence)
        except (KeyError, ValueError, TypeError) as error:
            return JobResult('error', f'Invalid physical-check result: {error}', evidence=evidence)
