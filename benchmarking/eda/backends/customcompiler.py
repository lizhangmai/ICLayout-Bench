"""Inspect frozen GDS with Synopsys Custom Compiler's native OA database."""

import json
import re
from pathlib import Path

from benchmarking.eda.backends.geometry import validate_constraints
from benchmarking.eda.backends.virtuoso import geometry_result
from benchmarking.eda.environment import ExternalRuntime
from benchmarking.evaluation.contracts import JobResult
from benchmarking.execution.tools.native import NativeTool
from benchmarking.files import Asset, keys


class CustomCompilerGeometryNative:
    """Check GDS integrity and measure layer-selected non-text bounding boxes."""

    def __init__(self, *, runtime, check, timeout_seconds=180):
        if not isinstance(runtime, ExternalRuntime) or check not in {'artifact', 'geometry'}:
            raise ValueError('Custom Compiler geometry requires an external runtime and a supported check')
        self.runtime, self.check = runtime, check
        self.tool = NativeTool(runtime, timeout_seconds, failure_label='Custom Compiler')
        version = self.tool.probe(runtime.module_command('customcompiler', ['importStream', '-version']))
        if version.returncode:
            raise ValueError('Custom Compiler version probe failed')
        self.version = version.stdout.decode(errors='replace').strip()

    @property
    def identity(self):
        return {'adapter': 'customcompiler-geometry-native', 'check': self.check, **self.tool.identity,
                'tool_version': self.version,
                'adapter_sha256': Asset(Path(__file__).read_bytes(), 'python').sha256,
                'geometry_parser_sha256': Asset(Path(__file__).with_name('virtuoso.py').read_bytes(), 'python').sha256}

    def run(self, job, inputs):
        keys(inputs, {'layout', 'task'} | ({'constraints'} if self.check == 'geometry' else set()), set(),
             'Custom Compiler geometry inputs')
        if job.stage != 'check' or job.outputs or job.parameters:
            raise ValueError('Custom Compiler geometry requires a check without outputs or parameters')
        if inputs['layout'].format != 'gds' or inputs['task'].format != 'json':
            raise ValueError('Custom Compiler geometry requires GDS and JSON task metadata')
        task = json.loads(inputs['task'].content)
        top = task['output']['top_cell']
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', top):
            raise ValueError('Unsupported GDS top cell name')
        if not 0 < len(inputs['layout'].content) <= task['output']['max_bytes']:
            return JobResult('failed', 'Empty or oversized GDS')
        constraints = (json.loads(inputs['constraints'].content) if self.check == 'geometry'
                       else {'hard': [], 'quality': []})
        if self.check == 'geometry':
            validate_constraints(constraints)
            if any(s['type'] != 'bbox_max' for s in constraints['hard']):
                raise ValueError('Custom Compiler geometry supports only bounding-box constraints')
        tcl = f'''set ctx [de::open candidate/{top}/layout -headless true]
set d [db::getAttr editDesign -of $ctx]
set insts [db::getInsts -of $d]
while {{[db::getCount $insts] > 0}} {{
 le::flatten $insts -levels 32 -scalarizeArrayInst true
 set insts [db::getInsts -of $d]
}}
set f [open geometry.txt w]
db::foreach shape [db::getShapes -of $d] {{
 if {{[db::getAttr type -of $shape] ni {{Text TextDisplay AttrDisplay}}}} {{
  set datatype [db::getAttr purposeNum -of $shape]
  # The importer maps stream datatype 0 to OA's built-in drawing purpose (-1).
  if {{$datatype == -1}} {{set datatype 0}}
  puts $f "L[db::getAttr layerNum -of $shape] D$datatype [concat {{*}}[db::getAttr bBox -of $shape]]"
 }}
}}
puts $f COMPLETE
close $f
'''
        # Fresh generic library: stream numbers remain OA layer/purpose numbers.
        # No PDK library or reference layout is used to resolve submitted cells.
        script = ('set -eu\n' + self.runtime.module_setup('customcompiler') + '''
printf 'DEFINE candidate ./candidate\\n' > lib.defs
importStream -lib candidate -libPath ./candidate -libDefFile lib.defs -gds candidate.gds -unmappedLayersUseStrmNums -view layout -logFile stream.log
custom_shell -gui false -batch true -libDefFile lib.defs -log custom -command 'source inspect.tcl'
''')
        files = {'candidate.gds': inputs['layout'], 'inspect.tcl': Asset(tcl.encode(), 'text'),
                 'run.sh': Asset(script.encode(), 'text')}
        result = self.tool.run(['bash', 'run.sh'], files,
                               {'stream.log': 'text', 'geometry.txt': 'text'})
        evidence = {**result.evidence, **result.files, 'script': files['inspect.tcl']}
        report = result.files.get('stream.log', Asset(b'', 'text')).content.decode(errors='replace')
        console = result.evidence.get('console', Asset(b'', 'text')).content.decode(errors='replace')
        if re.search(r'ERROR: \(IMPORT_STREAM-80053\):', report):
            return JobResult('failed', 'Malformed GDS', evidence=evidence)
        if '(DATA_MANAGEMENT-019)' in console:
            return JobResult('failed', 'Missing declared top cell', evidence=evidence)
        if result.reason or result.returncode or 'geometry.txt' not in result.files:
            return JobResult('error', result.reason or 'Native GDS inspection did not complete', evidence=evidence)
        errors = re.findall(r'Messages:\s+(\d+) error,', report)
        if not errors or any(value != '0' for value in errors):
            return JobResult('failed', 'Custom Compiler did not establish an error-free GDS import', evidence=evidence)
        verdict = geometry_result(result.files['geometry.txt'].content.decode(), constraints)
        return JobResult(verdict.status, verdict.reason, measurements=verdict.measurements, evidence=evidence)
