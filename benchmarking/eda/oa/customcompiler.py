"""Fresh native Custom Compiler transactions over explicit GDS assets."""

import re
import shlex
from pathlib import Path

from benchmarking.eda.oa.virtuoso import stream_metadata
from benchmarking.execution.tools.native import NativeTool
from benchmarking.files import Asset


def tcl_string(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$').replace('[', '\\[') + '"'


class CustomCompilerGDSNative:
    """Run trusted author/operator Tcl; never expose this as a solver endpoint."""

    def __init__(self, runtime, *, timeout_seconds=180):
        self.runtime = runtime
        self.tool = NativeTool(runtime, timeout_seconds, failure_label='Custom Compiler OA transaction')

    @property
    def identity(self):
        return {'adapter': 'customcompiler-gds-native', **self.tool.identity,
                'adapter_sha256': Asset(Path(__file__).read_bytes(), 'python').sha256}

    def run(self, sources, script, *, exports=None, reports=(), layers=()):
        exports = exports or {}
        if layers or not sources or any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', n) for n in sources):
            raise ValueError('Custom Compiler transactions need named sources and native LPP selection')
        metadata = {n: stream_metadata(a.content) for n, a in sources.items()}
        precision = round(1 / min(m['dbu_um'] for m in metadata.values()))
        files = {n + '.gds': a for n, a in sources.items()}
        files['lib.defs.in'] = Asset(''.join(f'DEFINE {n} ./{n}\n' for n in sources).encode(), 'text')
        files['transaction.tcl'] = Asset(script.encode(), 'text')
        files['driver.tcl'] = Asset(b'if {[catch {source transaction.tcl} error options]} {puts stderr $error; puts stderr [dict get $options -errorinfo]; exit 1}\nset f [open complete.txt w]; puts $f COMPLETE; close $f\n', 'text')
        commands = ['set -eu', self.runtime.module_setup('customcompiler'),
                    'cp lib.defs.in lib.defs', 'chmod u+w lib.defs']
        for name in sources:
            commands.append(shlex.join([
                'importStream', '-lib', name, '-libPath', './' + name, '-libDefFile', 'lib.defs',
                '-gds', name + '.gds', '-unmappedLayersUseStrmNums', '-view', 'layout',
                '-dbuPerUU', str(precision), '-logFile', name + '-in.log']))
        commands.append("custom_shell -gui false -batch true -libDefFile lib.defs -log custom -command 'source driver.tcl'")
        for i, (filename, (library, tops)) in enumerate(exports.items()):
            if library not in sources or not tops:
                raise ValueError('Exports require selected transaction cells')
            commands.append(shlex.join([
                'exportStream', '-lib', library, '-libDefFile', 'lib.defs', '-cell', ','.join(tops),
                '-view', 'layout', '-gds', filename, '-unmappedLayersUseOALayers',
                '-dbuPerUU', str(precision), '-logFile', f'export-{i}.log']))
        files['run.sh'] = Asset(('\n'.join(commands) + '\n').encode(), 'text')
        result = self.tool.run(['bash', 'run.sh'], files,
                               {**{n: 'gds' for n in exports}, **{n: 'text' for n in reports}, 'complete.txt': 'text'},
                               evidence_patterns=('*.log', 'custom*'))
        result.evidence['transaction'] = files['transaction.tcl']
        if not result.reason:
            logs = [a.content.decode(errors='replace') for n, a in result.evidence.items()
                    if n.endswith('-in.log') or n.startswith('export-')]
            counts = [re.findall(r'Messages:\s+(\d+) error,', log) for log in logs]
            if len(logs) != len(sources) + len(exports) or any(not c or any(v != '0' for v in c) for c in counts):
                result.reason = 'Custom Compiler did not complete every stream transaction without errors'
        return result
