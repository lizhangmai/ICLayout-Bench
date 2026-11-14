#!/usr/bin/env bash
set -euo pipefail

if [[ $# -gt 1 || ( $# -eq 1 && "$1" != tools ) ]]; then
    echo 'The toolchain is unified; this check accepts only the tools image.' >&2
    exit 2
fi
image="${ICLAYOUT_BENCH_TEST_IMAGE:-docker.io/lizhangmai/iclayout-bench-tools:latest}"
echo "Checking unified tool image: ${image}"
docker run --rm --network none -i "${image}" bash -es <<'CHECK'
set -euo pipefail
test "$(id -u)" -ne 0
python - <<'PY'
import importlib.util
import subprocess
import gdsfactory as gf
from gdsfactory.generic_tech import get_generic_pdk
import gdstk
import gdspy
import gmsh
import h5py
import matplotlib.pyplot as plt
import networkx
import numpy
import pandas
import PIL.Image
import pya
import psutil
import scipy.optimize
import skrf
import shapely.geometry
import sympy
import tkinter
import yaml
from CSXCAD import ContinuousStructure
from openEMS import openEMS
assert pya.__version__ in subprocess.check_output(['klayout', '-b', '-v'], text=True)
assert pya.Box(0, 0, 10, 20).area() == 200
assert gdstk.rectangle((0, 0), (2, 3)).area() == 6
assert gdspy.Rectangle((0, 0), (2, 3)).area() == 6
gmsh.initialize()
gmsh.option.setNumber('General.Terminal', 0)
volume = gmsh.model.occ.addBox(0, 0, 0, 1, 2, 3)
gmsh.model.occ.synchronize()
assert abs(gmsh.model.occ.getMass(3, volume) - 6) < 1e-12
gmsh.finalize()
fdtd = openEMS(EndCriteria=1e-5)
fdtd.SetCSX(ContinuousStructure())
assert numpy.allclose(skrf.Network(frequency=skrf.Frequency.from_f([1e9], unit='Hz'), s=[[[0]]], z0=50).y, 0.02)
get_generic_pdk().activate()
rectangle = gf.components.rectangle(size=(2, 3), layer=(1, 0))
assert rectangle.area() == 6
array = gf.Component()
array.add_array(rectangle, columns=2, rows=2, spacing=(4, 5))
assert array.area() == 24
cutout = gf.geometry.boolean(
    A=gf.components.rectangle(size=(4, 4), layer=(1, 0)),
    B=gf.components.rectangle(size=(2, 2), layer=(1, 0)),
    operation="A-B", layer=(1, 0))
assert cutout.area() == 12
assert psutil.Process().pid > 0
assert tkinter.Tcl().eval('expr {2 + 3}') == '5'
assert numpy.allclose(numpy.linalg.solve([[2, 0], [0, 4]], [4, 8]), [2, 2])
assert scipy.optimize.brentq(lambda x: x - 2, 0, 4) == 2
assert pandas.Series([1, 2]).sum() == 3
assert shapely.geometry.box(0, 0, 2, 3).area == 6
assert networkx.shortest_path(networkx.path_graph(3), 0, 2) == [0, 1, 2]
x = sympy.Symbol('x')
assert sympy.diff(x**2, x) == 2*x
assert yaml.safe_load('value: 3')['value'] == 3
plt.plot([0, 1], [0, 1])
plt.savefig('/tmp/python-tools.png')
with PIL.Image.open('/tmp/python-tools.png') as picture:
    assert picture.format == 'PNG' and picture.width > 0
for name in ('benchmarking', 'pytest', 'flake8'):
    assert importlib.util.find_spec(name) is None, name
print('Python KLayout', pya.__version__)
PY
printf '%s\n' 'puts "Embedded Ruby #{RUBY_VERSION}"' > /tmp/runtime.rb
klayout -b -r /tmp/runtime.rb
kpex --version
kpex extract --help > /dev/null
netlist --help > /dev/null
xschem --version
ngspice --version
python - <<'PY'
import pathlib
import re
import subprocess
import tempfile

# A stable negative feedback circuit: out=-10*in and 2*in=1+out.
# Both native representations must give out=-5/6 V. A missing xfer DC
# derivative makes the linear circuit diverge despite its unique solution.
with tempfile.TemporaryDirectory(prefix='xfer-dc-') as directory:
    root = pathlib.Path(directory)
    for name, element, model in (
        ('vcvs', 'Eamp out 0 in 0 -10', ''),
        ('xfer', 'Aamp %vd(in 0) %vd(out 0) transfer',
         '.model transfer xfer r_i=true table=[0 -10 0 1e9 -10 0]'),
    ):
        circuit = root / f'{name}.cir'
        circuit.write_text(f'''Negative feedback DC control
Vsource source 0 1
Rsource source in 1000
Rfeedback out in 1000
Rload out 0 1000
{element}
{model}
.control
set num_threads=1
op
let dc_error=abs(v(out)+5/6)
print dc_error
quit
.endc
.end
''')
        run = subprocess.run(['ngspice', '-b', str(circuit)], cwd=root,
                             capture_output=True, text=True, timeout=30, check=True)
        match = re.search(r'^dc_error\s*=\s*(\S+)', run.stdout, re.MULTILINE)
        assert match and float(match[1]) < 1e-10, (name, run.stdout, run.stderr)
print('ngspice xfer and VCVS negative feedback DC controls passed')
PY
magic --version
openvaf --version
QT_QPA_PLATFORM=offscreen qucs-s --version
qucsator --version
qucsator_rf --version
qucsconv --version
palace --help > /dev/null
palace-x86_64.bin --help > /dev/null
CHECK
