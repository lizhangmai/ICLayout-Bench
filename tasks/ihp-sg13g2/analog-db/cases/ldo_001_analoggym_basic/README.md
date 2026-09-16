> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Multistage Error-Amplifier PMOS Regulator

## Overview

The PMOS-input folded error amplifier, cascoded bias branches and mirrored
loads drive a separate intermediate PMOS/NMOS branch and the pass-gate node
`net1`. The auxiliary PMOS source/body is tied to `net1`; the input pair has
a separate source-tied `net20` well. The physical 300/100 kohm divider returns
one quarter of output through the declared VFB/SENSE measurement interface.
This complete internal drive network adds coverage beyond the simpler LDO004,
LDO008 and LDO009 error-amplifier paths.

| Related maintained case | Distinction of this case |
| --- | --- |
| [LDO004](../../../../gf180mcuD/analog-db/cases/ldo_004_basic_pmos/README.md) | Its four-transistor error amplifier uses an external 1 uF load capacitor; this folded/cascoded core retains internal compensation and qualifies its own bilateral loop and specified zero-state startup. LDO004 retains its own GF180 supply/load and rejection contract. |
| [LDO008](../ldo_008_fer_mirror_ota/README.md) | Its mirror OTA uses divider/series compensation; this core has separate source-tied input and auxiliary wells, a pass-gate-coupled auxiliary branch, and net106/net10 output-connected compensation. Neither case proves all internal poles. |
| [LDO009](../ldo_009_fer_5t_pass/README.md) | Its NMOS-input five-transistor amplifier uses unity feedback and internal COUT; this PMOS-input multistage core has a physical 3:1 divider and two internal compensation paths, without added output-to-ground storage. |

All 24 original MOS groups remain. Equivalent parallel regrouping converts
1,168 raw fingers into 831 physical MOS, preserving each group's total W and L;
individual W/m and diffusion perimeter change. The pass PMOS retains its 464
fingers. All original bias and feedback devices remain. The 8 uA external sink
is unchanged; the reference is explicitly calibrated from 0.4 to 0.225 V,
setting an ideal 0.9 V output target within the 1.2/1.3 V LV supply range.

All internal passives are physical: three 42.685 um square MIM units retain
approximately 8.2 pF `net106–output` compensation; an additional 51.64 um square
MIM provides approximately 4 pF `net10–output` local compensation. Twelve/four
series high-poly segments (W=1 um, L=17.465 um) implement the complete divider.
No extra output-to-ground capacitor, ideal servo or diagnostic clamp is added.
There is real output-connected capacitance in both compensation branches.

Qualification covers typical models at 27 C, two supplies, 0.2/0.5 mA loads
doubled with 200 ns edges, line/load/headroom sweeps and synchronized 10/20 us
zero-state startup into 900/4500 ohm loads. The [problem](problem.md) owns the
complete circuit, body, interface, physical and electrical contract.

## Files

- [Problem](problem.md): complete solver-facing requirements.
- [Configuration](case.toml): inputs, checks, limits, scoring and witness.
- [Native circuit](materials/circuit.cdl) and [simulation circuit](materials/circuit.spice): matching device graphs.
- [Loop/load deck](materials/testbench.spice): bilateral return ratio and sustained current-load recovery.
- [Startup deck](materials/startup.spice): zero-state supply/reference/bias ramps with resistive loading.
- [Sweep deck](materials/sweeps.spice): line/load and downward regulation-floor measurements.
- [Reference GDS](reference/ldo_001_analoggym_basic.gds): independent physical witness.

Only the problem and five declared materials enter solver inputs. Collection
license/notice accompany distributions separately; source checkouts, reference,
configuration and qualification results remain outside solver inputs.

## Reference Results

Native main/maximal DRC without waivers, strict named-interface LVS and the
complete functional geometry pass. Functional area is 1,906,376.7360 um²; the
fixed absolute target/zero anchors are 2,000,000/8,000,000 um². They budget the
831 MOS, four MIM, sixteen poly segments, body contacts and complete routing;
the 5500 × 360 um envelope includes the extra physical compensation. Coefficient
9 reflects multistage regulation, physical feedback, coupled internal dynamics
and loaded recovery. The long feasibility witness is not an area optimum. The published
reference evaluation passes with score 100; the catalog-driven empty-layout
regression rejects the empty candidate.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `output_v` | V | 0.88468938–0.889839703 | 0.887975954–0.892727012 |
| `bias_v` | V | 0.704715141–0.804715088 | 0.696712076–0.797777465 |
| `quiescent_a` | A | 8.50537548e-05–8.56283475e-05 | 8.75562927e-05–8.82044975e-05 |
| `power_w` | W | 0.000342126811–0.000761264106 | 0.000345067551–0.000764665847 |
| `dc_gain_db` | dB | 50.32356–52.69066 | 50.84444–53.46268 |
| `unity_hz` | Hz | 401330.1–406136.2 | 418191.6–424666.3 |
| `phase_margin_deg` | deg | 87.34981–87.45723 | 81.14572–81.35229 |
| `final_unity_hz` | Hz | 401330.1–406136.2 | 418191.6–424666.3 |
| `final_phase_margin_deg` | deg | 87.34981–87.45723 | 81.14572–81.35229 |
| `minimum_return_distance` | 1 | 0.951131511–0.954461146 | 0.876246032–0.881353301 |
| `return_phase_excursion_deg` | deg | 83.8423411–84.6266784 | 84.3700135–85.1620617 |
| `hf_gain_db` | dB | -81.75554–-78.15391 | -111.6189–-111.5727 |
| `minimum_v` | V | 0.8736976–0.8798426 | 0.8674489–0.8756491 |
| `maximum_v` | V | 0.8945545–0.8992763 | 0.9107275–0.9141766 |
| `recovery_load_v` | V | 0.01237304–0.01810482 | 0.00924878–0.01443391 |
| `recovery_release_v` | V | 0.01015946–0.01531135 | 0.007272989–0.01202405 |
| `mean_power_w` | W | 0.0004651032–0.001094364 | 0.000468117–0.001097931 |
| `loaded_ripple_v` | V | 2.23642438e-10–3.15629523e-10 | 1.76985537e-10–7.46975481e-10 |
| `released_ripple_v` | V | 2.01159867e-10–3.69760667e-10 | 3.86381482e-10–8.76434259e-10 |
| `startup_error_v` | V | 0.01012422–0.018016 | 0.007249467–0.01437421 |
| `startup_peak_v` | V | 0.881984–0.8898758 | 0.8856259–0.8927506 |
| `startup_minimum_v` | V | 1.060331e-06–2.311701e-06 | 5.846892e-07–1.271625e-06 |
| `regulation_floor_v` | V | 0.879919–0.9339764 | 0.8902489–0.9642853 |
| `headroom_v` | V | 0.009919–0.0639764 | 0.0202489–0.0942853 |
| `line_span_v` | V | 0.0017495–0.0025942 | 0.0017221–0.0024839 |
| `load_span_v` | V | 0.005342–0.006189 | 0.0046761–0.0054379 |

Ripple rows use raw extrema; finite-precision intermediate extrema in the
ngspice log can subtract to a printed zero. These tiny residuals are numerical
results, not noise or voltage-resolution claims.

The independent extracted functional graph audit maps all 851 functional
devices and 34 logical nets after collapsing parasitic interconnect resistors
and applying Magic's ideal body-tie boundary. Original and added MIM plates,
every divider segment, separate source-tied wells and pass-gate paths remain.
Native LVS independently checks the physical taps and device dimensions.
Extraction uses half-grid import and zero parasitic cutoffs; an isolated Magic
copy retains only Metal3 interface text while native LVS reads the original
GDS and its intrinsic tap labels. Source simulation includes finite body-tap
models; extracted simulation idealizes those ties. Fresh extraction can change
internal names, ordering and parasitic values; exact RC-graph identity is not
claimed. The numerical matrix uses one frozen RC from its reference run.

Tian Eq. 30 uses voltage/current injection at this case's actual divider/input
boundary. The exported port voltages and currents independently reconstruct
the two-port Y matrix. Full 0.01 Hz–1 GHz sampling has one descending unity
crossing in these conditions. First/final crossings, minimum `abs(1+T)`,
continuous return-difference phase and 200 MHz–1 GHz attenuation all pass.
This is finite external-loop and observable recovery qualification, not an
inventory or proof of all internal poles. Sustained error and ripple are
checked separately, so a wide DC-error band cannot hide persistent oscillation.

The numerical/reproduction matrix contains 62 simulation jobs: 16 reference,
16 source, four each half-step/tight/trapezoidal/source-long/RC-long, two tight
startup, two dense DC sweeps and six expected fast-boundary failures. Independent
raw-waveform/Y reconstruction checks 708 observations; 56 jobs pass and six
fail only the documented excursion or startup-peak bounds. Long runs sustain
30 mV error bounds throughout 15–35/60–95 us and 1 mV ripple over 30–35/90–95 us.
The 5 ns long-run step supplements 1/0.5 ns fast-response checks. Startup also
checks sustained tail ripple from raw samples, not just one final voltage.
With `uic`, the first exported point can follow time zero; the startup minimum
is the minimum available in-window sample, while the simulator starts from
zero state. The reported tiny positive minimum is not a nonzero precharge.

Source performance characterization raises only `itl1` and `itl4` to 1000:
the default iteration ceiling fails the initial source operating point at
1.3 V/0.5 mA. No nodeset, fixed initial voltage or damping element is needed.
Candidate nominal runs use the explicitly declared baseline profile. Tight
controls use tenfold tighter current/relative/voltage tolerances, a 1e13 ohm
shunt and 600 AC points/decade; the nominal absolute-current tolerance is 1 pA.
This differs from the earlier 10 fA development draft; the 0.1 pA tight
controls constrain numerical sensitivity without changing the physical RC
or voltage-acceptance bounds.
The numerical shunt and tolerances remain explicit and are not physical devices.
DC power and mean transient power include internal bias consumption, exclude
external bias/reference-generator overhead and do not credit sink energy.

### Calibration and failure boundaries

The added physical 4 pF local branch closes the previously observed internal
oscillation with the complete extracted interconnect. It does not remove the
fast-edge limitation. Initial development stimuli used 20 ns load edges and
1 us startup; the maintained contract explicitly uses 200 ns and 10/20 us.
Voltage-excursion and startup-peak limits are retained. The same final RC with
20 ns load edges exceeds the 0.84–0.95 V excursion window; 1 us synchronized
startup peaks near the supply rail. These are expected failures below, not
unmeasured exclusions or newly relaxed acceptance limits. Slower startup and
load-edge scope must not be described as arbitrary fast-load capability.

| Failure probe on the same frozen RC | Measured range | Retained bound |
| --- | --- | --- |
| 20 ns load-edge minimum | 0.7901692–0.8095776 V | >=0.84 V |
| 20 ns load-edge maximum | 0.9946794–1.038499 V | <=0.95 V |
| 1 us synchronized startup peak | 1.13282–1.284693 V | <=0.95 V |

The 30 mV regulation floor includes error-amplifier headroom; it is not a
pass-resistance-only dropout rating. DC sweep coverage does not qualify every
intermediate supply/load dynamically. Loads below 0.2 mA, arbitrary sequencing,
constant-current loading at zero supply, PVT, precision-reference behavior,
mismatch, noise, PSRR and fabrication signoff remain outside scope.
No framework, backend, PDK or tool-image change is required.

## Reproduce

These operator commands require the installed `ICLayout-Bench-Private` package.
Run preparation from the Public checkout; run any `tests/integration/` commands
from the Private checkout using that environment.

Use the [shared tool setup](../../../../../docs/tools.md#manual-tools) from the
repository root. These commands create fresh reader-generated evidence under
`build/runs/`; reuse verified support resources and the tools image.

```bash
python -m layout_eval.preview prepare \
  --case ldo_001_analoggym_basic --image iclayout-bench-tools:local \
  --output build/runs/ldo_001_analoggym_basic-prepared
python -m layout_eval.preview run \
  --prepared build/runs/ldo_001_analoggym_basic-prepared \
  --output build/runs/ldo_001_analoggym_basic-reference
python -m pytest tests/integration/test_public_references.py \
  -k "ldo_001_analoggym_basic and empty_candidate"
```

The preview performs the complete reference evaluation. The selected regression
checks empty-layout rejection without repeating the expensive reference matrix.

Run all source, numerical and expected-failure controls with that frozen RC.
The fast failure jobs retain the acceptance bounds and assert an electrical
failure; a runtime error cannot substitute for the expected failure.

```bash
uv run --locked python - <<'PYCODE'
from pathlib import Path
import json,copy,tomllib,concurrent.futures
from benchmarking.tasks import load_task
from layout_eval.toolchains import load_toolchain
from benchmarking.evaluation import parse_evaluation
from layout_eval.evaluate import run_evaluation
from benchmarking.files import Asset
case=Path('build/runs/ldo_001_analoggym_basic-prepared/case/case.toml');reference=Path('build/runs/ldo_001_analoggym_basic-reference/reference');root=Path('build/runs/ldo_001_analoggym_basic-checks-final')
task=load_task(case);backends=load_toolchain(case);report=json.loads((reference/'report.json').read_text());assert report['task_success'];rc=Asset((reference/report['jobs']['parasitics']['outputs']['netlist']['path']).read_bytes(),'spice');base=tomllib.loads(case.read_text())['task']['evaluation']
def run(item):
 variant,index=item;plan=copy.deepcopy(base);plan['mode']='characterization';plan.pop('scoring');job=[j for j in plan['jobs'] if j['stage']=='simulate'][index];plan['jobs']=[job];role=job['inputs']['deck'];job['inputs']['dut']='input:simulation';metrics=[]
 for m in plan['metrics']:
  if m['category']!='performance':continue
  m['observations']=[x for x in m['observations'] if x.startswith(job['id']+':')]
  if not m['observations']:continue
  for k in ['dimension','zero_lower','zero_upper']:m.pop(k,None)
  metrics.append(m)
 plan['metrics']=metrics;inputs=task.evaluation_inputs();inputs['input:simulation']=rc
 if variant in ['source','long-source']:inputs['input:simulation']=task.evaluation_inputs()['input:simulation']
 deck=inputs[role].content.decode()
 if variant in ['source','long-source'] and role=='input:performance':deck=deck.replace('.option klu','.option itl1=1000 itl4=1000 klu')
 if variant in ['tight','startup-tight']:
  deck=deck.replace('rshunt=1e12 reltol=1e-5 abstol=1e-12 vntol=1e-8','rshunt=1e13 reltol=1e-6 abstol=1e-13 vntol=1e-9').replace('ac dec 300','ac dec 600')
 if variant=='half-step':deck=deck.replace('tran 1n 18u 0 1n','tran 0.5n 18u 0 0.5n')
 if variant=='trap':deck=deck.replace('method=gear','method=trap')
 if variant.startswith('long'):
  for a,b in [('8u 16u','38u 200u'),('tran 1n 18u 0 1n','tran 5n 100u 0 5n'),('from=5u to=9.5u','from=15u to=35u'),('from=13u to=17.5u','from=60u to=95u'),('from=9u to=9.5u','from=30u to=35u'),('from=17u to=17.5u','from=90u to=95u'),('from=2u to=18u','from=2u to=100u')]:deck=deck.replace(a,b)
 if variant=='dense-sweep':deck=deck.replace('1.3 0.8 -0.001','1.3 0.8 -0.0005').replace('0.0002 0.001 0.00001','0.0002 0.001 0.000005')
 if variant=='fast-load-failure':deck=deck.replace('200n 200n','20n 20n')
 if variant=='fast-startup-failure':job['parameters']['values']['ramp_s']=1e-6
 inputs[role]=Asset(deck.encode(),'spice');q=run_evaluation(parse_evaluation(json.dumps(plan).encode(),file_format='json'),inputs,backends,root/f'{variant}-{index}');expected='failed' if variant.endswith('failure') else 'passed';print(variant,index,q['outcome'],flush=True);assert q['outcome']==expected,(variant,index,q['outcome'])
items=[('source',i) for i in range(16)]+[(v,i) for v in ['half-step','tight','trap','long','long-source','fast-load-failure'] for i in range(4)]+[('startup-tight',i) for i in [4,10]]+[('dense-sweep',i) for i in [12,15]]+[('fast-startup-failure',i) for i in [4,10]]
with concurrent.futures.ThreadPoolExecutor(6) as pool:list(pool.map(run,items))

PYCODE
```

To reproduce the source initialization boundary, use only item `("source", 3)`
in a fresh output directory and omit the line adding `itl1=1000 itl4=1000`.
The source operating point can abort with missing transient output; record that
as a convergence error, not a stability result. No nodeset was used to qualify.

### Independent waveform audit

```bash
uv run --locked python - <<'PYCODE'
from pathlib import Path
import sys,json,math,cmath,bisect,tomllib
sys.path.insert(0,'tests')
from helpers.spice_raw import read_raw
case=Path('build/runs/ldo_001_analoggym_basic-prepared/case/case.toml');root=Path('build/runs/ldo_001_analoggym_basic-checks-final');reference=Path('build/runs/ldo_001_analoggym_basic-reference/reference')
def interp(t,y,x):
 i=bisect.bisect_left(t,x)
 if i==0:return y[0]
 if i==len(t):assert abs(x-t[-1])<1e-12;return y[-1]
 return y[i-1]+(y[i]-y[i-1])*(x-t[i-1])/(t[i]-t[i-1])
def window(t,y,a,b):return [(a,interp(t,y,a))]+[(x,v) for x,v in zip(t,y) if a<x<b]+[(b,interp(t,y,b))]
def avg(t,y,a,b):
 w=window(t,y,a,b);return sum((x2-x1)*(y1+y2)/2 for (x1,y1),(x2,y2) in zip(w,w[1:]))/(b-a)
def phase(z):
 out=[]
 for v in z:
  x=math.degrees(cmath.phase(v))
  if out:
   while x-out[-1]>180:x-=360
   while x-out[-1]<-180:x+=360
  out.append(x)
 return out
out=[]
for path in [reference/'report.json']+sorted(root.glob('*/report.json')):
 p=path.parent;q=json.loads(path.read_text());failure='failure' in str(p);assert q['outcome']==('failed' if failure else 'passed');plan=json.loads((p/q['plan']['path']).read_text())
 for name,j in q['jobs'].items():
  if j['stage']!='simulate':continue
  raw={k:read_raw((p/v['path']).read_bytes()) for k,v in j['outputs'].items()};pt=next(x for x in plan['jobs'] if x['id']==name)['parameters']['values'];expected={};residual=None;crossings=[]
  if 'ac' in raw:
   h=[];res=[];assert len(raw['ac'])==len(raw['voltage'])
   for x,z in zip(raw['ac'],raw['voltage']):
    assert x['frequency']==z['frequency'];e1=z['v(sense)'];f1=z['v(fb)'];i1=z['i(vprobe)'];e2=x['v(sense)'];f2=x['v(fb)'];i2=x['i(vprobe)'];det=e1*f2-e2*f1
    y11=(-i1*f2-(1-i2)*f1)/det;y12=(i1*e2+(1-i2)*e1)/det;y21=(i1*f2-i2*f1)/det;y22=(-i1*e2+i2*e1)/det;v=(y12+y21)/(y11+y22);h.append(v);res.append(abs(v-x['transfer'])/max(abs(v),1e-5))
   assert all(math.isfinite(z.real) and math.isfinite(z.imag) for z in h)
   residual=max(res);assert residual<1e-5;f=[x['frequency'].real for x in raw['ac']];g=[20*math.log10(abs(x)) for x in h];ph=phase(h);rp=phase([1+x for x in h]);assert abs(ph[0])<.5
   assert math.isclose(f[0],.01,rel_tol=1e-9) and math.isclose(f[-1],1e9,rel_tol=1e-9)
   assert all(b>a for a,b in zip(f,f[1:]))
   for i in range(1,len(h)):
    if g[i]*g[i-1]<0:
     u=-g[i-1]/(g[i]-g[i-1]);crossings.append(dict(hz=f[i-1]+u*(f[i]-f[i-1]),pm=180+ph[i-1]+u*(ph[i]-ph[i-1]),descending=g[i]<g[i-1]))
   assert len(crossings)==1 and crossings[0]['descending'],crossings;op=raw['op'][0];vdd=pt['supply_v'];c=crossings[0]
   expected.update(output_v=op['v(vout)'],bias_v=op['v(ib)'],quiescent_a=-op['i(vdd)']-pt['load_a'],power_w=-vdd*op['i(vdd)'],dc_gain_db=g[0],unity_hz=c['hz'],phase_margin_deg=c['pm'],final_unity_hz=c['hz'],final_phase_margin_deg=c['pm'],minimum_return_distance=min(abs(1+x) for x in h),return_phase_excursion_deg=max(abs(x) for x in rp),hf_gain_db=max(x for ff,x in zip(f,g) if 2e8<=ff<=1e9))
  tail=None
  if 'transient' in raw:
   tr=raw['transient'];t=[x['time'] for x in tr];v=[x['v(vout)'] for x in tr];err=[abs(x-.9) for x in v];assert all(b>a for a,b in zip(t,t[1:]));assert all(math.isfinite(x) for x in v)
   def mx(y,a,b):return max(v for x,v in zip(t,y) if a<=x<=b)
   def mn(y,a,b):return -mx([-x for x in y],a,b)
   if name.startswith('startup'):
    expected.update(startup_error_v=mx(err,40e-6,49e-6),peak_v=mx(v,0,50e-6),minimum_v=mn(v,0,50e-6));tail=mx(v,40e-6,49e-6)-mn(v,40e-6,49e-6)
    assert t[0]<1e-9 and math.isclose(t[-1],50e-6,rel_tol=1e-9)
    assert max(x for _,x in window(t,err,40e-6,49e-6))<.03;assert tail<.001
   else:
    long='long' in str(p);hi=(15e-6,35e-6) if long else (5e-6,9.5e-6);lo=(60e-6,95e-6) if long else (13e-6,17.5e-6);hh=(30e-6,35e-6) if long else (9e-6,9.5e-6);ll=(90e-6,95e-6) if long else (17e-6,17.5e-6);end=100e-6 if long else 18e-6
    assert t[0]<=1e-12 and math.isclose(t[-1],end,rel_tol=1e-9)
    expected.update(minimum_v=mn(v,2e-6,end),maximum_v=mx(v,2e-6,end),recovery_load_v=mx(err,*hi),recovery_release_v=mx(err,*lo),mean_power_w=avg(t,[-x['v(vdd)']*x['i(vdd)'] for x in tr],2e-6,end),loaded_ripple_v=mx(v,*hh)-mn(v,*hh),released_ripple_v=mx(v,*ll)-mn(v,*ll));tail=expected['released_ripple_v']
    for a,b in [hi,lo]:assert max(x for _,x in window(t,err,a,b))<.03
  if 'line' in raw:
   line_axis=[x['v(vdd)'] for x in raw['line']];load_axis=[x['i(i-sweep)'] for x in raw['load']]
   dense='dense-sweep' in str(p);line_step=.0005 if dense else .001;load_step=.000005 if dense else .00001
   assert len(line_axis)==(1001 if dense else 501) and len(load_axis)==(161 if dense else 81)
   assert all(math.isclose(a-b,line_step,rel_tol=1e-8) for a,b in zip(line_axis,line_axis[1:]))
   assert all(math.isclose(b-a,load_step,rel_tol=1e-8) for a,b in zip(load_axis,load_axis[1:]))
   assert math.isclose(load_axis[0],.0002,abs_tol=1e-12) and math.isclose(load_axis[-1],.001,abs_tol=1e-12)
   assert all(math.isfinite(x['v(vout)']) for rows in [raw['line'],raw['load']] for x in rows)
   line=raw['line'];vs=[x['v(vdd)'] for x in line];vo=[x['v(vout)'] for x in line];assert math.isclose(vs[0],1.3,abs_tol=1e-9) and math.isclose(vs[-1],.8,abs_tol=1e-9);er=[abs(x-.9) for x in vo];i=next(i for i in range(1,len(er)) if er[i-1]<.03<=er[i]);u=(.03-er[i-1])/(er[i]-er[i-1]);floor=vs[i-1]+u*(vs[i]-vs[i-1]);vf=vo[i-1]+u*(vo[i]-vo[i-1]);w=[y for x,y in zip(vs,vo) if 1.2<=x<=1.3];load=[x['v(vout)'] for x in raw['load']];expected.update(regulation_floor_v=floor,headroom_v=floor-vf,line_span_v=max(w)-min(w),load_span_v=max(load)-min(load))
  failed=[];seen=set()
  for key,m in q['metrics'].items():
   for oid,o in m['observations'].items():
    if not oid.startswith(name+':'):continue
    k=oid.split(':')[1];seen.add(k);value=expected[k];assert math.isclose(value,o['value'],rel_tol=1e-5,abs_tol=1.1e-7),(str(p),name,k,value,o['value'])
    if not m['lower']<=value<=m['upper']:failed.append(key)
  assert seen==set(expected),(name,seen,set(expected))
  assert bool(failed)==failure,(str(p),failed)
  if failure:assert set(failed)<={'minimum_v','maximum_v','startup_peak_v'},failed
  out.append(dict(folder=str(p),job=name,observations=len(expected),twoport_relative_residual=residual,crossings=crossings,tail_span_v=tail,failed_bounds=failed))
assert len(out)==62 and sum(x['observations'] for x in out)==708, 'Incomplete qualification matrix'
(root/'waveform-audit.json').write_text(json.dumps(out,indent=2));print(len(out),'jobs',sum(x['observations'] for x in out),'observations independently verified')

PYCODE
```

### Extracted functional graph audit

```bash
uv run --locked python - <<'PYCODE'
from pathlib import Path
import json, hashlib, collections, tomllib
case = Path("build/runs/ldo_001_analoggym_basic-prepared/case/case.toml")
reference = Path("build/runs/ldo_001_analoggym_basic-reference/reference")
data = tomllib.loads(case.read_text())
report = json.loads((reference / "report.json").read_text())
assert report["task_success"]
src = (case.parent / data["task"]["inputs"]["simulation"]["path"]).read_text()
rc = (reference / report["jobs"]["parasitics"]["outputs"]["netlist"]["path"]).read_text()
ports = next(j for j in data["task"]["evaluation"]["jobs"] if j["id"] == "parasitics")["parameters"]["ports"]
def val(s):
 s=s.lower();return float(s[:-1])*{'u':1e-6,'p':1e-12}[s[-1]] if s[-1] in 'up' else float(s)
def graph(s):
 parent={}
 def root(n):
  parent.setdefault(n,n)
  if parent[n]!=n:parent[n]=root(parent[n])
  return parent[n]
 def join(a,b):parent[root(a)]=root(b)
 lines=[]
 for ln in s.splitlines():
  if ln.startswith('+'):lines[-1]+=' '+ln[1:]
  else:lines.append(ln)
 for ln in lines:
  f=ln.split()
  if not f:continue
  if f[0].startswith('R'):join(f[1],f[2])
  if f[0].startswith('XR') and f[3] in ['ptap1','ntap1']:join(f[1],f[2])
 devices=[]
 for ln in lines:
  f=ln.split()
  if not f or not f[0].startswith('X'):continue
  models=[x for x in f if x in ['sg13_lv_nmos','sg13_lv_pmos','cap_cmim','rhigh']]
  if not models:continue
  model=models[0];i=f.index(model);nodes=[root(x) for x in f[1:i]];par={k:val(v) for k,v in (x.split('=') for x in f[i+1:] if '=' in x)}
  attrs=(model,round(par['w']*1e6,8),round(par['l']*1e6,8))
  roles=['ds','g','ds','b'] if model.startswith('sg13') else (['ab','ab','b'] if model=='rhigh' else ['top','bottom'])
  for k in range(int(par.get('m',1))):devices.append((attrs,list(zip(roles,nodes))))
 nodes={n for _,ends in devices for _,n in ends};anchors={root(p):p for p in ports};colors={n:anchors.get(n,'internal') for n in nodes}
 for _ in range(12):
  new={}
  for n in nodes:
   adj=sorted((attrs,role,tuple(sorted((rr,colors[nn]) for rr,nn in ends))) for attrs,ends in devices for role,nn in ends if nn==n)
   new[n]=hashlib.sha256(repr((colors[n],adj)).encode()).hexdigest()
  colors=new
 assert len(set(colors.values()))==len(nodes), 'Ambiguous net mapping requires exact graph comparison'
 return collections.Counter((attrs,tuple(sorted((role,colors[n]) for role,n in ends))) for attrs,ends in devices),len(nodes),len(devices)
a, b = graph(src), graph(rc)
assert a == b
print(a[2], "functional devices;", a[1], "uniquely mapped nets")

PYCODE
```

## Source and License

Derived from [LDO001 in the fixed source snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/ldo_001_analoggym_basic).
Raw IHP DUT SHA-256:
`4b9daef958a188ec3e419e95f19f9eca010a39611c5765d60adf69dd6af521ed`.
Selected raw DUT, manifest, analyses and collection licensing files were checked
against the fixed Git tree. Normalized materials and the independent witness
retain PolyForm Noncommercial, Required Notice and the recorded CODA-Team
AnalogGym BSD-3-Clause component terms in collection [LICENSE](../../LICENSE)
and [NOTICE](../../NOTICE). The separately authored native measurement decks
are MIT. Component manifest labels do not relicense normalized derivatives.
