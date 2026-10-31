"""Inspect frozen GDS geometry with Cadence XStream and Virtuoso OA."""

import json
import math
import re
import shlex
from pathlib import Path

from benchmarking.eda.backends.geometry import validate_constraints
from benchmarking.eda.environment import ExternalRuntime
from benchmarking.eda.oa.virtuoso import stream_metadata
from benchmarking.evaluation.contracts import JobResult, Measurement
from benchmarking.execution.tools.native import NativeEDATool
from benchmarking.files import Asset, keys


def geometry_result(text, constraints):
    """Interpret native shape bounding boxes; labels never enter this report."""
    boxes = {}
    lines = text.splitlines()
    if not lines or lines[-1] != 'COMPLETE':
        raise ValueError('Incomplete native geometry report')
    for line in lines[:-1]:
        layer, purpose, *coordinates = line.split()
        box = tuple(map(float, coordinates))
        if len(box) != 4 or not all(map(math.isfinite, box)) or box[2] < box[0] or box[3] < box[1]:
            raise ValueError('Invalid native shape bounding box')
        boxes.setdefault((layer, purpose), []).append(box)
    if not boxes:
        return JobResult('failed', 'GDS contains no geometry')

    def bounds(layers):
        selected = [b for layer, datatype in layers
                    for b in boxes.get((f'L{layer}', f'D{datatype}'), [])]
        if not selected:
            return None
        return (min(b[0] for b in selected), min(b[1] for b in selected),
                max(b[2] for b in selected), max(b[3] for b in selected))

    outlines, measurements = {}, {}
    for spec in constraints['hard']:
        box = bounds(spec['functional_layers'])
        if box is None:
            return JobResult('failed', 'No functional geometry')
        outlines[spec['id']] = box
        if box[2] - box[0] > spec['max_width_um'] + 1e-9 or box[3] - box[1] > spec['max_height_um'] + 1e-9:
            return JobResult('failed', f"Bounding box exceeds {spec['id']}")
    for spec in constraints['quality']:
        box = outlines[spec['layers_from']] if 'layers_from' in spec else bounds(spec['functional_layers'])
        if box is None:
            return JobResult('failed', 'No functional geometry')
        measurements[spec['id']] = Measurement((box[2] - box[0]) * (box[3] - box[1]), 'um2')
    return JobResult('passed', measurements=measurements)


class VirtuosoGeometryNative:
    """Support artifact integrity and layer-selected bounding-box constraints."""

    def __init__(self, *, runtime, check, timeout_seconds=180):
        if not isinstance(runtime, ExternalRuntime) or check not in {'artifact', 'geometry'}:
            raise ValueError('Virtuoso geometry requires an external runtime and a supported check')
        self.runtime, self.check = runtime, check
        self.tool = NativeEDATool(runtime, 'virtuoso', ['virtuoso', '-W'], timeout_seconds)

    @property
    def identity(self):
        return {'adapter': 'virtuoso-geometry-native', 'check': self.check, **self.tool.identity,
                'stream_parser_sha256': Asset(Path(__file__).parents[1].joinpath('oa/virtuoso.py').read_bytes(), 'python').sha256,
                'adapter_sha256': Asset(Path(__file__).read_bytes(), 'python').sha256}

    def run(self, job, inputs):
        keys(inputs, {'layout', 'task'} | ({'constraints'} if self.check == 'geometry' else set()), set(),
             'Virtuoso geometry inputs')
        if job.stage != 'check' or job.outputs or job.parameters:
            raise ValueError('Virtuoso geometry requires a check without outputs or parameters')
        if inputs['layout'].format != 'gds' or inputs['task'].format != 'json':
            raise ValueError('Virtuoso geometry requires GDS and JSON task metadata')
        task = json.loads(inputs['task'].content)
        top = task['output']['top_cell']
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', top):
            raise ValueError('Unsupported GDS top cell name')
        if not 0 < len(inputs['layout'].content) <= task['output']['max_bytes']:
            return JobResult('failed', 'Empty or oversized GDS')
        try:
            stream_metadata(inputs['layout'].content)
        except ValueError as error:
            return JobResult('failed', f'Malformed GDS: {error}',
                             evidence={'format_error': Asset(str(error).encode(), 'text')})
        constraints = json.loads(inputs['constraints'].content) if self.check == 'geometry' else {'hard': [], 'quality': []}
        if self.check == 'geometry':
            validate_constraints(constraints)
            if any(s['type'] != 'bbox_max' for s in constraints['hard']):
                raise ValueError('Virtuoso geometry supports only bounding-box constraints')
        layers = sorted({tuple(pair) for spec in constraints['hard'] + constraints['quality']
                         for pair in spec.get('functional_layers', [])})
        layer_map = ''.join(f'L{layer} D{datatype} {layer} {datatype}\n' for layer, datatype in layers)
        skill = f'''procedure(benchFindShape(view visited)
 prog((found)
   when(visited[view] return(nil))
   visited[view]=t
   foreach(shape view~>shapes
     unless(member(shape~>objType '("label" "textDisplay")) return(shape)))
   dbOpenHier(view 1)
   foreach(master view~>instanceMasters
     found=benchFindShape(master visited)
     when(found return(found)))
   return(nil)))
procedure(benchLeaf(path)
 if(listp(path) benchLeaf(car(last(path))) path))
let((cv out shape transform nativeBox boxes key box previous)
 cv=dbOpenCellViewByType("candidate" {json.dumps(top)} "layout" "maskLayout" "r")
 unless(cv error("Missing submitted top cell"))
 when({'t' if self.check == 'artifact' else 'nil'}
   shape=benchFindShape(cv makeTable("visited" nil))
   out=outfile("geometry.txt")
   when(shape
     fprintf(out "%s %s %.12g %.12g %.12g %.12g\\n"
       shape~>layerName shape~>purpose
       xCoord(car(shape~>bBox)) yCoord(car(shape~>bBox))
       xCoord(cadr(shape~>bBox)) yCoord(cadr(shape~>bBox))))
   fprintf(out "COMPLETE\\n") close(out) dbClose(cv) exit())
 dbOpenHier(cv 2147483647)
 boxes=makeTable("bounds" nil)
 foreach(path dbGetOverlaps(cv cv~>bBox t 2147483647 t)
   shape=benchLeaf(path)
   unless(member(shape~>objType '("inst" "mosaic" "stdVia" "customVia" "label" "textDisplay"))
     transform=if(listp(path) dbGetHierPathTransform(path) list(0:0 "R0" 1.0))
     nativeBox=dbTransformBBox(shape~>bBox transform)
     key=strcat(shape~>layerName " " shape~>purpose)
     box=list(xCoord(car(nativeBox)) yCoord(car(nativeBox))
              xCoord(cadr(nativeBox)) yCoord(cadr(nativeBox)))
     previous=boxes[key]
     when(previous
       box=list(min(nth(0 previous) nth(0 box)) min(nth(1 previous) nth(1 box))
                max(nth(2 previous) nth(2 box)) max(nth(3 previous) nth(3 box))))
     boxes[key]=box))
 out=outfile("geometry.txt")
 foreach(key boxes
   box=boxes[key]
   fprintf(out "%s %.12g %.12g %.12g %.12g\\n" key nth(0 box) nth(1 box) nth(2 box) nth(3 box)))
 fprintf(out "COMPLETE\\n") close(out) dbClose(cv))
exit()
'''
        command = ['strmin', '-library', 'candidate', '-strmFile', 'candidate.gds',
                   '-topCell', top, '-view', 'layout',
                   '-logFile', 'stream.log', '-checkPolygon', '-noDetectVias']
        if layers:
            command += ['-layerMap', 'layers.map']
        script = ('set -eu\n' + self.runtime.module_setup('virtuoso') + '\nmkdir candidate\n' + shlex.join(command)
                  + '\nvirtuoso -nograph -nocdsinit -restore inspect.il -log virtuoso.log\n')
        files = {'candidate.gds': inputs['layout'], 'cds.lib': Asset(b'DEFINE candidate ./candidate\n', 'text'),
                 'layers.map': Asset(layer_map.encode(), 'text'),
                 'inspect.il': Asset(skill.encode(), 'text'), 'run.sh': Asset(script.encode(), 'text')}
        result = self.tool.run(['bash', 'run.sh'], files,
                               {'stream.log': 'text', 'virtuoso.log': 'text', 'geometry.txt': 'text'})
        evidence = {**result.evidence, **result.files, 'script': files['inspect.il'], 'layer_map': files['layers.map']}
        report = result.files.get('stream.log', Asset(b'', 'text')).content.decode(errors='replace')
        # Native parser rejection and missing top are candidate failures, not
        # license/startup failures. Other nonzero tool exits remain errors.
        if re.search(r'ERROR \(XSTRM-(?:80048|430)\):', report):
            return JobResult('failed', 'Malformed GDS or missing declared top cell', evidence=evidence)
        if result.reason or result.returncode or 'geometry.txt' not in result.files:
            return JobResult('error', result.reason or 'Native GDS inspection did not complete', evidence=evidence)
        errors = re.findall(r"Translation completed\. '(\d+)' error\(s\)", report)
        if errors != ['0']:
            return JobResult('failed', 'XStream did not establish an error-free GDS import', evidence=evidence)
        verdict = geometry_result(result.files['geometry.txt'].content.decode(), constraints)
        return JobResult(verdict.status, verdict.reason, measurements=verdict.measurements, evidence=evidence)
