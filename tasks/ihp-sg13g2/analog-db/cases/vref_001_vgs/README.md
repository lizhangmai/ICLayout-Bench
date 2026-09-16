> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Mixed LV/HV VGS Reference

## Overview

The maintained circuit preserves the fixed-source two-transistor core: an LV
NMOS with gate/source tied to the output above a diode-connected HV NMOS.
It targets an approximately 0.36 V reference for picoampere loads, with
explicit substrate contacts and an independently constructed layout. The
[problem](problem.md) defines the finite supply, temperature and recovery scope.

## Files

- [Configuration](case.toml): frozen inputs, tool bindings and qualification.
- [Physical circuit](materials/circuit.cdl) and [simulator circuit](materials/circuit.spice): equivalent LV/HV devices and same-net tap boundary.
- [Testbench](materials/testbench.spice): DC sensitivity, zero-state ramp and signed load recovery.
- [Reference layout](reference/vref_001_vgs.gds): independent physical implementation.

## Reference Results

The independent witness passes native main/maximal DRC without waivers, strict
named-port LVS, functional geometry, Magic distributed RC and all nine nominal
simulation jobs. Its 50 × 30.43 um footprint is 1521.5 um²; fixed area anchors
are 1600/6400 um², coefficient 5 and score 100. This is a compact self-biased
block with demanding leakage/load conditioning, not an area optimum.

| Metric across the nine jobs | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| Unloaded reference | V | 0.355205–0.364991 | 0.355205–0.364991 |
| Supply current | pA | 8.189–1981 | 8.189–1981 |
| Maximum unloaded power | nW | 2.972 | 2.972 |
| Worst zero-state startup error, 8–9 ms | uV | 0.2042 | 0.5032 |
| Worst +1 pA load error, 18–19 ms | mV | 3.24642 | 3.24584 |
| Worst −1 pA injection error, 38–39 ms | mV | 2.96590 | 2.96661 |
| Worst final return error, 48–49 ms | uV | 0.0515 | 0.5444 |
| Finite +1 pA output resistance | Mohm | 18.645–3246.50 | 18.644–3246.51 |
| Temperature span at fixed supply | mV | 0.3540–1.4907 | 0.3535–1.4904 |

The candidate supply-sweep span is 8.293–9.491 mV over 1.0–1.5 V.
At fixed supply its small temperature span establishes a useful reference
function distinct from the existing supply-sensitive PTAT cores. Replacing the
lower HV device with LV produces only 45.894/64.601 mV at the two extreme
jobs and fails the original acceptance limits. No second topology is admitted
for that device substitution.

Independent binary-waveform inspection recalculates every reported electrical
measurement, checks all DC axes and all transient windows with interpolated
endpoints, and accounts for ngspice's printed precision. Halving the time step,
doubling supply/temperature sweep density and tightening tolerances preserves
acceptance. Reducing gmin from 1e-16 to 1e-17 S changes reference voltage by at
most 0.193 uV at the tested extremes; this distinguishes operating current from
the numerical conductance floor. Trapezoidal integration also passes. Across
these numerical controls, recovery/load-window measurements change by less
than 0.630 uV. These checks characterize the chosen models; they do not establish
silicon leakage, mismatch or all process corners.

A separate zero-volt terminal-current probe covers all nine candidate-RC DC
conditions and checks current conservation without changing device voltages.
The source-terminal conduction exceeds the sum of absolute gate/body currents
by at least 7.486 times. At −20 °C / 1.5 V the upper LV device carries 9.9795 pA
at its source, versus 1.3292 pA gate current and 0.00381 pA body current. Thus
it is above the modeled leakage floor, but a stricter **tenfold** gate/body
headroom probe fails at that condition. Tenfold leakage margin is not a
qualification claim or an original acceptance bound; the native voltage,
current, load and recovery bounds remain unchanged. This explicit leakage
contribution further limits precision and extrapolation claims.

The extracted two-device graph was independently checked after collapsing only
interconnect resistors: model flavors, W/L, all four terminals and nonzero
junction loading agree. Both substrate contacts are physical; the marked tap
uses its explicit native LVS device boundary. Magic idealizes substrate/well
contacts, so distributed substrate resistance/noise is outside scope. The
100 fF external load adds to extracted capacitance. No internal ideal amplifier,
servo, resistor, capacitor or bias source was introduced in the DUT.

The core sizes and ports are unchanged from the fixed raw source. Maintenance
resolves parameters, adds physical body contacts and publishes the native
measurement contract and independent GDS. The new `mixed-mos-models` resource
profile provides pinned LV/HV PSP libraries through the existing preparation
workflow. Validation reused the compatible unified image; no image rebuild,
PDK modification or circuit-specific runner/scorer was needed.

Only the problem and three material files enter a solve. Standalone preparation,
input digests and exact solver materialization were checked independently.
The shared empty-layout regression rejects the empty witness. No precision,
bandgap, buffered-load, AC PSRR, noise, arbitrary startup, continuous PVT,
mismatch or fabrication-signoff claim is made. This two-MOS self-biased core has
no separate amplifier/CMFB injection boundary; DC sensitivity and the stated
startup/load recovery are its observable feedback checks, not an internal-pole
proof. Native standalone DRC excludes density/antenna signoff.

## Reproduce

These operator commands require the installed `ICLayout-Bench-Private` package.
Run preparation from the Public checkout; run any `tests/integration/` commands
from the Private checkout using that environment.

Follow the shared [tool setup](../../../../../docs/tools.md#manual-tools).
From the repository root, the following commands generate fresh resource and
evaluation directories; these directories are created by the reader's run.

```bash
python -m layout_eval.preview prepare --case vref_001_vgs \
  --output build/runs/vref-qualification-03/prepared --image iclayout-bench-tools:local
python -m layout_eval.preview run \
  --prepared build/runs/vref-qualification-03/prepared \
  --output build/runs/vref-qualification-03/run
```

### Independent audit and failure probe

Run this after the preview above. It generates pre-layout and candidate-RC
calibration reports from the frozen evaluation plan, using the same declared
resources. Existing calibration reports in this fresh run directory can be
re-read; use a new directory after changing any inputs. The wrong-flavor control
must execute successfully and fail electrical acceptance. The assertions also
check model/terminal correspondence and exact solver input isolation.

```bash
uv run --locked python - <<'PY'
from pathlib import Path
import json,sys,math,bisect,re
from benchmarking.tasks import load_task
from layout_eval.toolchains import load_toolchain
from layout_eval.evaluate import run_evaluation
from benchmarking.evaluation import parse_evaluation
from benchmarking.files import Asset
sys.path.insert(0,'tests')
from helpers.spice_raw import output_rows
from helpers.scoring import unscore_characterization
root=Path('build/runs/vref-qualification-03')
prepared=root/'prepared/case/case.toml'
task=load_task(prepared);backends=load_toolchain(prepared)
postdir=root/'run/reference';post=json.loads((postdir/'report.json').read_text())
assert post['task_success'],post['jobs']
def interp(xs,ys,x):
 j=bisect.bisect_left(xs,x)
 if j==0:return ys[0]
 if j==len(xs):return ys[-1]
 a,b=xs[j-1],xs[j]
 return ys[j-1]+(ys[j]-ys[j-1])*(x-a)/(b-a)
def window(xs,ys,a,b):
 assert xs[0]<=a<b<=xs[-1]
 return [interp(xs,ys,a),*[y for x,y in zip(xs,ys) if a<x<b],interp(xs,ys,b)]
def audit(report,directory,step=1e-6,line_step=.01,temp_step=5):
 summary={}
 for name,job in report['jobs'].items():
  if 'op' not in job.get('outputs',{}):continue
  op=output_rows(report,directory,name,'op')[0];tr=output_rows(report,directory,name,'transient')
  x=[r['time'] for r in tr];v=[r['v(vref)'] for r in tr]
  assert all(b>a for a,b in zip(x,x[1:])) and math.isclose(x[-1],.05,abs_tol=1e-12)
  assert max(b-a for a,b in zip(x,x[1:]))<=step*1.001
  expected={'reference_v':op['v(vref)'],'supply_a':-op['i(vdd)'],'power_w':-op['v(vdd)']*op['i(vdd)'],'minimum_v':min(v),'maximum_v':max(v)}
  for measurement,a in [('startup_error_v',.008),('load_error_v',.018),('release_error_v',.028),('injection_error_v',.038),('return_error_v',.048)]:
   ys=window(x,v,a,a+.001);assert len(ys)>=.001/step-1
   expected[measurement]=max(abs(y-op['v(vref)']) for y in ys)
  for label,a,b,delta in [('line',1.,1.5,line_step),('temperature',-20,85,temp_step),('load',-1.,1.,.1)]:
   rows=output_rows(report,directory,name,label);axis=next(iter(rows[0]));xs=[r[axis] for r in rows];ys=[r['v(vref)'] for r in rows]
   assert len(xs)==round((b-a)/delta)+1,(label,len(xs),axis)
   assert math.isclose(xs[0],a,rel_tol=1e-10,abs_tol=1e-22) and math.isclose(xs[-1],b,rel_tol=1e-10,abs_tol=1e-22),(label,xs[0],xs[-1])
   assert all(math.isclose(y-z,delta,rel_tol=1e-9,abs_tol=1e-22) for z,y in zip(xs,xs[1:]))
   if label=='load':
    expected['loaded_reference_v']=ys[-1];expected['output_resistance_ohm']=(op['v(vref)']-ys[-1])/1e-12
   else:
    expected[label+'_min_v']=min(ys);expected[label+'_max_v']=max(ys);expected[label+'_span_v']=max(ys)-min(ys)
  for key,value in expected.items():
   measured=job['measurements'][key]['value']
   assert math.isclose(measured,value,rel_tol=2e-6,abs_tol=1e-12 if key not in ['supply_a','power_w'] else 1e-22),(name,key,measured,value)
  summary[name]=expected
 return summary
# Load and materialize the prepared package away from the collection.
import tempfile,shutil,hashlib
original=load_task(Path('tasks/ihp-sg13g2/analog-db/cases/vref_001_vgs/case.toml'))
assert [(i.role,i.path,i.content) for i in original.inputs]==[(i.role,i.path,i.content) for i in task.inputs]
assert original.evaluation.description()==task.evaluation.description()
with tempfile.TemporaryDirectory(dir=root) as tmp:
 tmp=Path(tmp);shutil.copytree(prepared.parent,tmp/'standalone')
 standalone=load_task(tmp/'standalone/case.toml')
 standalone.materialize(tmp/'solver')
 assert {p.relative_to(tmp/'solver').as_posix() for p in (tmp/'solver').rglob('*') if p.is_file()}=={i.path for i in task.inputs}
 assert all((tmp/'solver'/i.path).read_bytes()==i.content for i in task.inputs)
summary={'post':audit(post,postdir)}
source=task.evaluation.description();source.update(mode='characterization',jobs=[j for j in source['jobs'] if j['stage']=='simulate'],metrics=[m for m in source['metrics'] if m['category']=='performance']);unscore_characterization(source)
for j in source['jobs']:j['inputs']['dut']='input:simulation'
plan=parse_evaluation(json.dumps(source).encode(),file_format='json')
pre_dir=root/'calibration-pre'
if (pre_dir/'report.json').exists():pre=json.loads((pre_dir/'report.json').read_text())
else:pre=run_evaluation(plan,task.evaluation_inputs(),backends,pre_dir,task_sha256=task.digest)
assert pre['outcome']=='passed',pre['jobs'];summary['pre']=audit(pre,pre_dir)
pex=post['jobs'][next(j.id for j in task.evaluation.jobs if j.stage=='extract')]['outputs']['netlist']
extracted=Asset((postdir/pex['path']).read_bytes(),'spice')
assert len(re.findall(r'\bsg13_lv_nmos\b',extracted.content.decode()))==1
assert len(re.findall(r'\bsg13_hv_nmos\b',extracted.content.decode()))==1
# Independently collapse extracted interconnect and check both model boundaries.
lines=extracted.content.decode().splitlines();parent={}
def find(x):
 parent.setdefault(x,x)
 if parent[x]!=x:parent[x]=find(parent[x])
 return parent[x]
for line in lines:
 t=line.split()
 if t and t[0].startswith('R'):parent[find(t[1])]=find(t[2])
expected_devices={'sg13_lv_nmos':(['vdd','vref','vref','vss'],2.5,2.),'sg13_hv_nmos':(['vref','vref','vss','vss'],1.,2.)}
for line in lines:
 t=line.split()
 if not t or not t[0].startswith('X'):continue
 nodes,w,l=expected_devices[t[5]];params=dict(x.split('=') for x in t[6:])
 assert all(find(a)==find(b) for a,b in zip(t[1:5],nodes))
 assert float(params['w'].removesuffix('u'))==w and float(params['l'].removesuffix('u'))==l
 assert all(float(params[k].removesuffix('p').removesuffix('u'))>0 for k in ['ad','as','pd','ps'])
for variant in ['dense','floor','trapezoidal','wrong-flavor']:
 p=json.loads(json.dumps(source));p['jobs']=[p['jobs'][0],p['jobs'][-1]]
 selected={j['id'] for j in p['jobs']}
 for metric in p['metrics']:metric['observations']=[v for v in metric['observations'] if v.split(':')[0] in selected]
 assets=task.evaluation_inputs();deck=assets['input:performance'].content.decode();assets['input:simulation']=extracted
 if variant=='dense':deck=deck.replace('tran 1u 50m 0 1u','tran .5u 50m 0 .5u').replace('1.5 .01','1.5 .005').replace('85 5','85 2.5').replace('reltol=1e-6 abstol=1e-18 vntol=1e-10','reltol=1e-7 abstol=1e-19 vntol=1e-11')
 if variant=='floor':deck=deck.replace('gmin=1e-16','gmin=1e-17')
 if variant=='trapezoidal':deck=deck.replace('method=gear maxord=2','method=trap')
 if variant=='wrong-flavor':assets['input:simulation']=Asset(task.evaluation_inputs()['input:simulation'].content.replace(b'sg13_hv_nmos',b'sg13_lv_nmos'),'spice')
 assets['input:performance']=Asset(deck.encode(),'spice')
 directory=root/f'calibration-{variant}'
 if (directory/'report.json').exists():report=json.loads((directory/'report.json').read_text())
 else:report=run_evaluation(parse_evaluation(json.dumps(p).encode(),file_format='json'),assets,backends,directory,task_sha256=task.digest)
 if variant=='wrong-flavor':
  assert report['outcome']=='failed' and all(j['status']=='passed' for j in report['jobs'].values()),report['jobs']
  assert all(j['measurements']['reference_v']['value']<.1 for j in report['jobs'].values())
  summary[variant]={k:v['measurements']['reference_v']['value'] for k,v in report['jobs'].items()}
 else:
  assert report['outcome']=='passed',report['jobs'];summary[variant]=audit(report,directory,step=.5e-6 if variant=='dense' else 1e-6,line_step=.005 if variant=='dense' else .01,temp_step=2.5 if variant=='dense' else 5)
 print(variant,'audited',flush=True)
for variant in ['dense','floor','trapezoidal']:
 for job,values in summary[variant].items():
  assert abs(values['reference_v']-summary['post'][job]['reference_v'])<1e-6
  for metric in ['startup_error_v','load_error_v','release_error_v','injection_error_v','return_error_v']:
   assert abs(values[metric]-summary['post'][job][metric])<2e-6
(root/'independent-audit.json').write_text(json.dumps(summary,indent=2))
print('All waveform, boundary, numerical and wrong-flavor checks passed.',flush=True)
PY
```

### Terminal currents and stricter leakage-headroom probe

The following independent calibration inserts ideal zero-volt measurement
sources at every terminal of the two extracted MOS devices. It retains device
models, junction dimensions and interconnects, performs all nine unloaded DC
jobs, checks Kirchhoff current conservation and compares output voltage with
the uninstrumented candidate. It reports the stricter tenfold-headroom failure
separately; that diagnostic does not silently change the native acceptance
limits. As above, use a fresh run directory after any input change.

```bash
uv run --locked python - <<'PY'
from pathlib import Path
import json,re,sys
from benchmarking.tasks import load_task
from layout_eval.toolchains import load_toolchain
from benchmarking.evaluation import parse_evaluation
from layout_eval.evaluate import run_evaluation
from benchmarking.files import Asset
sys.path.insert(0,'tests')
from helpers.scoring import unscore_characterization
from helpers.spice_raw import output_rows
root=Path('build/runs/vref-qualification-03');prepared=root/'prepared/case/case.toml';task=load_task(prepared)
p=root/'run/reference';report=json.loads((p/'report.json').read_text());circuit=(p/report['jobs']['parasitics']['outputs']['netlist']['path']).read_text();lines=[];probes=[]
for line in circuit.splitlines():
 t=line.split()
 if t and t[0].startswith('X'):
  name=t[0].lower()
  for i,term in enumerate('dgsb',1):
   probes.append(f'V{name}{term} {t[i]} {name}{term} 0');t[i]=name+term
  line=' '.join(t)
 if line.startswith('.ends'):lines.extend(probes)
 lines.append(line)
assets=task.evaluation_inputs();assets['input:simulation']=Asset(('\n'.join(lines)+'\n').encode(),'spice');deck=assets['input:performance'].content.decode();deck=deck[:deck.index('tran 1u')]+ 'quit\n.endc\n.end\n';assets['input:performance']=Asset(deck.encode(),'spice')
p=task.evaluation.description();jobs=[j for j in p['jobs'] if j['stage']=='simulate'];p.update(mode='characterization',jobs=jobs,metrics=[m for m in p['metrics'] if m['id'] in ['reference_v','supply_a','power_w']]);selected={j['id'] for j in p['jobs']};unscore_characterization(p)
for m in p['metrics']:m['observations']=[v for v in m['observations'] if v.split(':')[0] in selected]
for j in p['jobs']:
 j['inputs']['dut']='input:simulation';j['outputs']={'op':'ngspice-raw'};j['parameters']['exports']={'op':'op.raw'};j['parameters']['measurements']={k:v for k,v in j['parameters']['measurements'].items() if k in ['reference_v','supply_a','power_w']}
out=root/'calibration-terminal-current-grid'
if (out/'report.json').exists():r=json.loads((out/'report.json').read_text())
else:r=run_evaluation(parse_evaluation(json.dumps(p).encode(),file_format='json'),assets,load_toolchain(prepared),out,task_sha256=task.digest)
import hashlib
assert r['task_sha256']==task.digest
for j in r['jobs'].values():
 for role,asset in [('deck',assets['input:performance']),('dut',assets['input:simulation'])]:
  assert j['inputs'][role]['sha256']==hashlib.sha256(asset.content).hexdigest()

assert r['outcome']=='passed'
summary={}
for name,j in r['jobs'].items():
 row=output_rows(r,out,name,'op')[0]
 assert abs(row['v(vref)']-report['jobs'][name]['measurements']['reference_v']['value'])<1e-6
 ratios=[]
 for device in ['x0','x1']:
  currents={t:row[f'i(v.xdut.v{device}{t})'] for t in 'dgsb'}
  assert abs(sum(currents.values()))<max(1e-18,abs(currents['d'])*1e-5)
  ratio=abs(currents['s'])/(abs(currents['g'])+abs(currents['b']))
  assert ratio>1,(name,device,currents,ratio)  # Source conduction must dominate gate/body leakage.
  ratios.append(ratio)
 summary[name]=dict(source_to_gate_body_ratio=ratios,terminal_currents={k:v for k,v in row.items() if 'vx' in k})
# A stricter tenfold-headroom diagnostic is deliberately not claimed to pass.
under_ten=[(name,device,ratio) for name,values in summary.items() for device,ratio in zip(['upper_lv','lower_hv'],values['source_to_gate_body_ratio']) if ratio<10]
assert under_ten, 'Recheck the published tenfold-headroom counterexample.'
print('Tenfold-headroom diagnostic failures:',under_ten)
(out/'independent-currents.json').write_text(json.dumps(summary,indent=2))
print('All nine jobs pass terminal-current conservation and leakage-floor checks.')
print('Minimum source-to-gate/body ratio:',min(min(v['source_to_gate_body_ratio']) for v in summary.values()))
PY
```

The DC-load stimulus uses a dimensionless −1–+1 control and 1 pA/V gain.
A direct tiny-current DC sweep was rejected during calibration because ngspice
included samples beyond +1 pA. The terminal value is read from the last saved
sample; the independent axis checks above establish that it is the declared
+1 pA endpoint. Acceptance limits and actual loads were not widened.

```bash
python -m pytest tests/integration/test_public_references.py \
  -k 'vref_001_vgs and empty'
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local python -m pytest \
  tests/integration/test_session.py -k 'declared_pdks and ihp'
python -m pytest tests/unit/test_catalogs.py tests/unit/test_tasks.py
uv run --locked python scripts/check_docs.py
```

## Source and License

Derived from [analog-db VREF001 at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/blob/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/raw/vref_001_vgs/ihp-sg13g2/_dut.spice), under the collection [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE), including PolyForm Noncommercial and applicable component terms.

The upstream manifest identifies this worked example as `analog-circuit-design`
and labels the component Apache-2.0. Its four advertised analyses are provenance,
not imported qualification or PSRR evidence. The normalized source remains
subject to the collection's PolyForm Noncommercial terms and Required Notice;
the manifest label does not relicense the derivative as a whole.

| Fixed-snapshot file reviewed | SHA-256 |
| --- | --- |
| `raw/vref_001_vgs/ihp-sg13g2/_dut.spice` | `0f1570819e2437286917ef9370cb20b7266e3ca7449e861f30074a4caaad61a5` |
| `circuits/vref_001_vgs/circuit.yaml` | `de50462486c2f5e9f5c199de5b3f671366206d9d63b9069b091f648d4f8112af` |
| `LICENSE` | `160dfa809ed429d74457e192fd8b53505d053b7de0651e89d21c507ebe0aa3d3` |
| `NOTICE` | `e4644906a59d8dc2c378bfcecb375c9e513c6a2a38e8045be8f7e4e3e7c3a425` |

All paths in the audit table are relative to `analog-db/` in the pinned
snapshot. No external reference pointer was followed. Native testbench authoring
is identified separately as MIT; retain the collection LICENSE and NOTICE with
all circuit-material distributions.
