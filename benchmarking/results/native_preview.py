"""Render commercial EDA geometry without loading an open EDA tool image."""

import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from benchmarking.eda.oa.customcompiler import CustomCompilerGDSNative, tcl_string
from benchmarking.eda.oa.virtuoso import VirtuosoGDSNative
from benchmarking.files import Asset
from benchmarking.results.preview_diagnostics import PreviewRenderError


def _cadence(top):
    return f'''procedure(previewLeaf(path)
 if(listp(path) previewLeaf(car(last(path))) path))
procedure(previewPolygon(out shape)
 let((points box)
  cond((shape~>objType == "rect"
    box=shape~>bBox
    points=list(car(box) xCoord(cadr(box)):yCoord(car(box)) cadr(box) xCoord(car(box)):yCoord(cadr(box))))
   (shape~>objType == "polygon" points=shape~>points)
   (t error("Unsupported native preview polygon")))
  fprintf(out "%s %s" shape~>layerName shape~>purpose)
  foreach(point points fprintf(out " %.15g %.15g" xCoord(point) yCoord(point)))
  fprintf(out "\\n")))
let((cv scratch shape copied transform polygons out)
 cv=benchOpen("source" {json.dumps(top)} "r")
 scratch=benchScratch("source" "_preview")
 dbOpenHier(cv 2147483647)
 out=outfile("polygons.txt")
 foreach(path dbGetOverlaps(cv cv~>bBox t 2147483647 t)
  shape=previewLeaf(path)
  unless(member(shape~>objType '("inst" "mosaic" "stdVia" "customVia" "label" "textDisplay"))
   transform=if(listp(path) dbGetHierPathTransform(path) list(0:0 "R0" 1))
   copied=dbCopyFig(shape scratch transform)
   unless(copied error("Cannot transform native preview shape"))
   if(member(copied~>objType '("rect" "polygon")) then
    previewPolygon(out copied)
    else
    polygons=dbLayerOr(scratch copied~>lpp list(copied))
    unless(polygons error("Cannot polygonize native preview path"))
    foreach(polygon polygons previewPolygon(out polygon) dbDeleteObject(polygon)))
   dbDeleteObject(copied)))
 close(out) dbClose(scratch) dbClose(cv))
'''


def _synopsys(top):
    return f'''set ctx [de::open {tcl_string('source/' + top + '/layout')} -headless true]
set d [db::getAttr editDesign -of $ctx]
set insts [db::getInsts -of $d]
while {{[db::getCount $insts] > 0}} {{
 le::flatten $insts -levels 32 -scalarizeArrayInst true
 set insts [db::getInsts -of $d]
}}
set f [open polygons.txt w]
db::foreach shape [db::getShapes -of $d] {{
 if {{[db::getAttr type -of $shape] ni {{Text TextDisplay AttrDisplay}}}} {{
  set datatype [db::getAttr purposeNum -of $shape]
  if {{$datatype == -1}} {{set datatype 0}}
  set polygons [po::createCollection $shape]
  foreach points [db::createList [db::getAttr polygons.pointArray]] {{
   puts $f "L[db::getAttr layerNum -of $shape] D$datatype [concat {{*}}$points]"
  }}
 }}
}}
close $f
'''


def render(candidate, top, runtime):
    """Return a PNG and separately identified renderer metadata."""
    if 'virtuoso' in runtime.modules:
        backend, script = VirtuosoGDSNative(runtime), _cadence(top)
    elif 'customcompiler' in runtime.modules:
        backend, script = CustomCompilerGDSNative(runtime), _synopsys(top)
    else:
        raise ValueError('Declare a supported commercial EDA renderer module')
    rendered = backend.run({'source': candidate}, script, reports=('polygons.txt',))
    if rendered.reason or rendered.returncode:
        raise PreviewRenderError('Native EDA geometry rendering failed', stage='native_geometry',
                                 renderer={'adapter': backend.identity['adapter']}, result=rendered)
    polygons = []
    for line in rendered.files['polygons.txt'].content.decode().splitlines():
        layer, datatype, *values = line.split()
        if not layer.startswith('L') or not datatype.startswith('D') or len(values) < 6 or len(values) % 2:
            raise ValueError('Invalid native preview polygon')
        coordinates = tuple(map(float, values))
        if not all(map(math.isfinite, coordinates)):
            raise ValueError('Nonfinite native preview geometry')
        polygons.append((int(layer[1:]), int(datatype[1:]), coordinates))
    if not polygons:
        raise ValueError('Native preview contains no geometry')
    xs = [v for _, _, p in polygons for v in p[::2]]
    ys = [v for _, _, p in polygons for v in p[1::2]]
    box = [min(xs), min(ys), max(xs), max(ys)]
    extent = max(box[2] - box[0], box[3] - box[1])
    if extent <= 0:
        raise ValueError('Native preview has no positive extent')
    margin = extent * .04
    scale = 4096 / (extent + 2 * margin)
    width = max(1, round((box[2] - box[0] + 2 * margin) * scale))
    height = max(1, round((box[3] - box[1] + 2 * margin) * scale))
    # Outline drawing keeps underlying diffusion, gate and metal visible through
    # large wells and upper-metal shapes, without a PDK-specific display recipe.
    palette = ((.15, .35, .75), (.7, .18, .2), (.1, .55, .3), (.6, .3, .65), (.7, .48, .1), (.15, .55, .65))
    postscript = [f'%!PS-Adobe-3.0\n<< /PageSize [{width} {height}] >> setpagedevice',
                  f'{scale:.15g} {scale:.15g} scale {-box[0] + margin:.15g} {-box[1] + margin:.15g} translate',
                  f'{.7 / scale:.15g} setlinewidth 1 setlinejoin']
    for layer, datatype, coordinates in sorted(polygons):
        red, green, blue = palette[(layer + datatype) % len(palette)]
        postscript += [f'{red} {green} {blue} setrgbcolor', 'newpath',
                       f'{coordinates[0]:.15g} {coordinates[1]:.15g} moveto']
        postscript.extend(f'{x:.15g} {y:.15g} lineto' for x, y in zip(coordinates[2::2], coordinates[3::2]))
        postscript.append('closepath stroke')
    postscript.append('showpage')
    gs = shutil.which('gs')
    if not gs:
        raise ValueError('Native layout previews require the installed Ghostscript rasterizer')
    environment = {'PATH': os.defpath, 'LANG': 'C'}
    version = subprocess.run([gs, '--version'], capture_output=True, check=True, env=environment, timeout=10).stdout.decode().strip()
    with tempfile.TemporaryDirectory(prefix='iclayout-native-preview-') as temporary:
        root = Path(temporary)
        (root / 'layout.ps').write_text('\n'.join(postscript) + '\n')
        subprocess.run([gs, '-q', '-dSAFER', '-dBATCH', '-dNOPAUSE', '-sDEVICE=png16m',
                        '-r72', '-dTextAlphaBits=4', '-dGraphicsAlphaBits=4',
                        '-sOutputFile=layout.png', 'layout.ps'], cwd=root, env=environment,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True, timeout=120)
        png = Asset((root / 'layout.png').read_bytes(), 'png')
    info = {'width': width, 'height': height, 'top_cell': top, 'bbox_um': box,
            'layer_style': 'Native geometry outlines; stream-layer colors; labels omitted',
            'layers': [f'{l}/{d}' for l, d in sorted({(l, d) for l, d, _ in polygons})],
            'renderer': {'backend': backend.identity['adapter'], 'execution': 'operator-native',
                         'identity_sha256': hashlib.sha256(json.dumps(backend.identity, sort_keys=True).encode()).hexdigest(),
                         'rasterizer': 'Ghostscript', 'rasterizer_version': version,
                         'adapter_sha256': Asset(Path(__file__).read_bytes(), 'python').sha256}}
    return png, info
