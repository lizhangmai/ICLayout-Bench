"""Native OA transactions over explicitly supplied GDS assets.

This is a trusted author/operator interface, never a participant SKILL endpoint.
Circuit rules and geometry edits belong to the caller. Every transaction uses a
fresh library and the same declared installation/environment as the evaluator.
"""

import json
import re
import shlex
import struct

from benchmarking.execution.tools.native import NativeTool
from benchmarking.files import Asset


def _validate_text_records(records, start):
    # TEXT uses TEXTTYPE, not polygon DATATYPE. Properties follow STRING;
    # optional presentation/path/transform records precede its single XY.
    order = (rb'\x0c\x26?\x2f?\x0d\x16\x17?\x21?\x0f?'
             rb'(?:\x1a\x1b?\x1c?)?\x10\x19(?:\x2b\x2c)*\x11')
    if not re.fullmatch(order, bytes(kind for kind, _, _ in records)):
        raise ValueError(f'Invalid GDS TEXT record sequence at byte {start}; '
                         'expected LAYER, TEXTTYPE, XY, STRING and ENDEL in order')
    fields = {0x0C: (0, 0), 0x26: (1, 2), 0x2F: (3, 4),
              0x0D: (2, 2), 0x16: (2, 2), 0x17: (1, 2), 0x21: (2, 2),
              0x0F: (3, 4), 0x1A: (1, 2), 0x1B: (5, 8), 0x1C: (5, 8),
              0x10: (3, 8), 0x19: (6, None), 0x2B: (2, 2), 0x2C: (6, None), 0x11: (0, 0)}
    if any(datatype != fields[kind][0] or (fields[kind][1] is not None and size != fields[kind][1])
           for kind, datatype, size in records):
        raise ValueError(f'Invalid GDS TEXT record payload at byte {start}')


def stream_metadata(content):
    """Read directory/precision and validate TEXT syntax without repairing records."""
    cells, referenced, layers = set(), set(), set()
    dbu, layer, offset, ended = None, None, 0, False
    text_records, text_start = None, None
    while offset < len(content):
        if offset + 4 > len(content):
            raise ValueError('Truncated GDS record header')
        length, kind, datatype = struct.unpack_from('>HBB', content, offset)
        if length < 4 or length % 2 or offset + length > len(content):
            raise ValueError('Invalid GDS record length')
        data = content[offset + 4:offset + length]
        if kind == 0x0C:
            if text_records is not None:
                raise ValueError(f'Unterminated GDS TEXT element at byte {text_start}')
            text_records, text_start = [], offset
        if text_records is not None:
            text_records.append((kind, datatype, len(data)))
            if kind == 0x11:
                _validate_text_records(text_records, text_start)
                text_records = None
        if kind in (0x06, 0x12):
            name = data.rstrip(b'\0').decode('ascii')
            (cells if kind == 0x06 else referenced).add(name)
        elif kind == 0x03:
            if len(data) != 16:
                raise ValueError('Invalid GDS units record')
            # The second REAL8 is the physical database unit in metres. The
            # first is relative to the stream's user unit, which need not be um.
            value = data[8:]
            dbu = (-1 if value[0] & 128 else 1) * int.from_bytes(value[1:], 'big') / 2**56 * 16**((value[0] & 127) - 64) * 1e6
        elif kind == 0x0D:
            if len(data) != 2:
                raise ValueError('Invalid GDS layer record')
            layer = struct.unpack('>H', data)[0]
        elif kind in (0x0E, 0x16) and layer is not None:
            if len(data) != 2:
                raise ValueError('Invalid GDS layer type record')
            layers.add((layer, struct.unpack('>H', data)[0]))
        offset += length
        if kind == 0x04:
            if any(content[offset:]):
                raise ValueError('Unexpected nonzero data after GDS library end')
            ended = True
            break
    if text_records is not None:
        raise ValueError(f'Unterminated GDS TEXT element at byte {text_start}')
    if not ended or dbu is None or dbu <= 0 or not cells:
        raise ValueError('GDS directory or precision is missing')
    if referenced - cells:
        raise ValueError('GDS contains unresolved cell references')
    return {'cells': sorted(cells), 'tops': sorted(cells - referenced),
            'layers': sorted(layers), 'dbu_um': dbu}


SKILL_HELPERS = '''
procedure(benchOpen(library cell mode)
 let((cv)
  cv=dbOpenCellViewByType(library cell "layout" "maskLayout" mode)
  unless(cv error("Cannot open transaction cell")) cv))
procedure(benchLPP(layer datatype) list(sprintf(nil "L%d" layer) sprintf(nil "D%d" datatype)))
procedure(benchScratch(library base)
 let((name) name=base
  while(ddGetObj(library name) name=strcat(name "_"))
  benchOpen(library name "w")))
procedure(benchEnsure(cv layer datatype)
 let((tech lpp changed)
  tech=techGetTechFile(cv) lpp=benchLPP(layer datatype)
  when(!techGetLayerNum(tech car(lpp)) || !techGetPurposeNum(tech cadr(lpp))
   techReopenTechFile(tech "a"))
  unless(techGetLayerNum(tech car(lpp))
   unless(techCreateLayer(tech 65536+layer car(lpp)) error("Cannot create transaction layer")) changed=t)
  unless(techGetPurposeNum(tech cadr(lpp))
   unless(techCreatePurpose(tech 65536+datatype cadr(lpp)) error("Cannot create transaction purpose")) changed=t)
  when(changed unless(techSaveTechFile(tech) error("Cannot retain transaction technology")))
  lpp))
procedure(benchShapes(cv layer datatype)
 setof(shape cv~>shapes shape~>lpp == benchLPP(layer datatype) &&
   !member(shape~>objType '("label" "textDisplay"))))
procedure(benchFlatten(cv)
 dbOpenHier(cv 2147483647)
 foreach(inst copy(cv~>instances)
   unless(dbFlattenInst(inst 2147483647 t) error("Cannot flatten transaction instance")))
 when(cv~>instances error("Unresolved transaction hierarchy")) cv)
procedure(benchBounds(shapes)
 let((box b)
  foreach(shape shapes
   b=shape~>bBox
   box=if(box list(min(xCoord(car(box)) xCoord(car(b))):min(yCoord(car(box)) yCoord(car(b)))
                   max(xCoord(cadr(box)) xCoord(cadr(b))):max(yCoord(cadr(box)) yCoord(cadr(b)))) b)) box))
procedure(benchRect(cv layer datatype box)
 dbCreateRect(cv benchEnsure(cv layer datatype) box))
procedure(benchInit(cv)
 benchTech=techGetTechFile(cv) abeInit(cv))
procedure(benchLayer(layer datatype)
 let((lpp)
  lpp=benchLPP(layer datatype)
  if(techGetLayerNum(benchTech car(lpp)) && techGetPurposeNum(benchTech cadr(lpp))
   abeLayerFromCellView(car(lpp) ?purpose cadr(lpp)) abeNewLayer())))
procedure(benchAnd(a b) let((out) out=abeNewLayer() abeLayerAnd(a b out) out))
procedure(benchMinus(a b) let((out) out=abeNewLayer() abeLayerAndNot(a b out) out))
procedure(benchOr(a b) let((out) out=abeNewLayer() abeLayerOr(a out) abeLayerOr(b out) out))
procedure(benchTouch(a b)
 let((out) out=abeNewLayer() abeLayerTouch(a b out ?includeCorners t ?islandBased t) out))
procedure(benchPolygonReport(out name layer)
 let((iterator polygon)
  fprintf(out "AREA %s %.15g\\n" name layer~>area)
  iterator=abeIslandIterator(layer)
  while(polygon=iterator->next
   fprintf(out "POLYGON %s" name)
   foreach(point polygon fprintf(out " %.15g %.15g" xCoord(point) yCoord(point)))
   fprintf(out "\\n"))))
'''


def polygon_measurements(text):
    """Read native union area and sum its boundary, cancelling hole bridges."""
    from collections import defaultdict

    result, edges = {}, defaultdict(lambda: defaultdict(int))
    for line in text.splitlines():
        kind, name, *values = line.split()
        if kind == 'AREA':
            if name in result or len(values) != 1:
                raise ValueError('Duplicate or invalid native area')
            result[name] = {'area_um2': float(values[0])}
        elif kind == 'POLYGON':
            points = list(zip(map(float, values[::2]), map(float, values[1::2]), strict=True))
            if len(points) < 3:
                raise ValueError('Incomplete native polygon boundary')
            for a, b in zip(points, points[1:] + points[:1]):
                if a == b:
                    continue
                key = tuple(sorted((a, b)))
                edges[name][key] += 1 if a < b else -1
        else:
            raise ValueError('Unknown native polygon report record')
    for name, value in result.items():
        value['perimeter_um'] = sum(abs(count) * math_distance(a, b) for (a, b), count in edges[name].items())
    if set(edges) - result.keys():
        raise ValueError('Native polygon boundary lacks area')
    return result


def math_distance(a, b):
    import math

    return math.hypot(a[0] - b[0], a[1] - b[1])


class VirtuosoGDSNative:
    """Import named assets, execute caller SKILL, and export selected OA cells."""

    def __init__(self, runtime, *, timeout_seconds=180):
        self.runtime = runtime
        self.tool = NativeTool(runtime, timeout_seconds, failure_label='Virtuoso OA transaction')

    @property
    def identity(self):
        from pathlib import Path

        return {'adapter': 'virtuoso-gds-native', **self.tool.identity,
                'adapter_sha256': Asset(Path(__file__).read_bytes(), 'python').sha256}

    def run(self, sources, skill, *, exports=None, reports=(), layers=()):
        """Return ToolResult, retaining scripts and native translator diagnostics.

        ``sources`` maps fresh OA library names to frozen GDS Assets. ``exports``
        maps output filenames to (library, top-cell names). ``reports`` lists
        caller-written text outputs. The caller must check the returned reason.
        """
        exports = exports or {}
        if not sources or any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', n) for n in sources):
            raise ValueError('Native OA sources need simple, distinct library names')
        metadata = {n: stream_metadata(a.content) for n, a in sources.items()}
        all_layers = set(layers) | {pair for m in metadata.values() for pair in m['layers']}
        precision = round(1 / min(m['dbu_um'] for m in metadata.values()))
        if precision <= 0 or any(abs(precision * m['dbu_um'] - round(precision * m['dbu_um'])) > 1e-6 for m in metadata.values()):
            raise ValueError('GDS inputs need compatible integer OA database precision')
        files = {n + '.gds': a for n, a in sources.items()}
        files['layers.map'] = Asset(''.join(f'L{l} D{d} {l} {d}\n' for l, d in sorted(all_layers)).encode(), 'text')
        files['cds.lib'] = Asset(''.join(f'DEFINE {n} @ROOT@/{n}\n' for n in sources).encode(), 'text')
        files['transaction.il'] = Asset((SKILL_HELPERS + '\n' + skill + '\n'
                                        'let((out) out=outfile("complete.txt") fprintf(out "COMPLETE\\n") close(out))\n').encode(), 'text')
        files['driver.il'] = Asset(b'if(errset(load("transaction.il") t) exit(0) exit(1))\n', 'text')
        commands = ['set -eu', self.runtime.module_setup('virtuoso')]
        for name in sources:
            commands += ['mkdir ' + shlex.quote(name), shlex.join([
                'strmin', '-library', name, '-strmFile', name + '.gds', '-view', 'layout',
                '-layerMap', 'layers.map', '-case', 'preserve', '-labelCase', 'preserve',
                '-dbuPerUU', str(precision), '-noDetectVias', '-logFile', name + '-in.log'])]
        commands.append('virtuoso -nograph -nocdsinit -restore driver.il -log virtuoso.log')
        for index, (filename, (library, tops)) in enumerate(exports.items()):
            if library not in sources or not tops:
                raise ValueError('Exports need a transaction library and explicit selected cells')
            commands.append(shlex.join([
                'strmout', '-library', library, '-topCell', ' '.join(tops), '-view', 'layout',
                '-strmFile', filename, '-layerMap', 'layers.map', '-case', 'preserve',
                '-labelCase', 'preserve', '-dbuPerUU', str(precision), '-logFile', f'export-{index}.log']))
        files['run.sh'] = Asset(('\n'.join(commands) + '\n').encode(), 'text')
        outputs = {**{p: 'gds' for p in exports}, **{p: 'text' for p in reports}, 'complete.txt': 'text'}
        result = self.tool.run(['bash', 'run.sh'], files, outputs, evidence_patterns=('*.log',),
                               file_rewriter=lambda name, content, root: content.replace(b'@ROOT@', str(root).encode()) if name == 'cds.lib' else content)
        result.evidence.update({'transaction': files['transaction.il'], 'layer_map': files['layers.map']})
        if not result.reason:
            logs = [a.content.decode(errors='replace') for n, a in result.evidence.items() if n.endswith(('-in.log', '.log')) and n != 'virtuoso.log']
            counts = [re.findall(r"Translation completed\. '(\d+)' error\(s\)", log) for log in logs]
            if len(logs) != len(sources) + len(exports) or any(c != ['0'] for c in counts):
                from dataclasses import replace

                result = replace(result, reason='XStream did not complete every transaction without errors')
        return result

    def compare(self, original, streamed):
        """Prove equal per-layer unions and exact native label placement."""
        a, b = stream_metadata(original.content), stream_metadata(streamed.content)
        if a['tops'] != b['tops'] or abs(a['dbu_um'] - b['dbu_um']) > 1e-12:
            raise ValueError('Streamed GDS changed selected roots or database precision')
        script = ['let((left right scratch aa bb differences la lb)',
                  'scratch=benchScratch("original" "_compare")']
        for top in a['tops']:
            script += [f'left=benchFlatten(benchOpen("original" {json.dumps(top)} "a"))',
                       f'right=benchFlatten(benchOpen("streamed" {json.dumps(top)} "a"))']
            for layer, datatype in sorted(set(a['layers']) | set(b['layers'])):
                script += [f'aa=benchShapes(left {layer} {datatype}) bb=benchShapes(right {layer} {datatype})',
                           f'differences=dbLayerXor(scratch benchLPP({layer} {datatype}) aa bb)',
                           'when(differences error("Native stream changed polygon geometry"))',
                           f'la=setof(s left~>shapes s~>objType == "label" && s~>lpp == benchLPP({layer} {datatype}))',
                           f'lb=setof(s right~>shapes s~>objType == "label" && s~>lpp == benchLPP({layer} {datatype}))',
                           'la=sort(foreach(mapcar s la sprintf(nil "%L" list(s~>theLabel s~>xy s~>orient))) \'alphalessp)',
                           'lb=sort(foreach(mapcar s lb sprintf(nil "%L" list(s~>theLabel s~>xy s~>orient))) \'alphalessp)',
                           'unless(la == lb error("Native stream changed interface labels"))']
            script += ['dbClose(left) dbClose(right)']
        script += ['dbClose(scratch))']
        return self.run({'original': original, 'streamed': streamed}, '\n'.join(script))
