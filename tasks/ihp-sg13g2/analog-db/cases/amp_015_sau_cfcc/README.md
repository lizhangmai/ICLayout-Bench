> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Input-Driven Active-Feedforward OTA

## Overview

Lay out `amp_015_sau_cfcc` with its complete transistor signal and bias paths.
The PMOS-input folded stage produces `voutn`, controlling the mirror at
`net050` and the auxiliary PMOS at `net049`. The `net050 → net043 → net049`
path and direct input-driven PMOS feedforward jointly drive the output
PMOS/NMOS at `net050/net049`. Preserve the original `net063–vout` compensation
and both explicitly added physical capacitor arrays.

Qualification covers 1.2 V, typical IHP LV models at 27 C, both 0.5/0.7 V
DC input points and 5/10/15 pF external loads. Positive and negative 200 mV
steps must sustain 2 mV tracking in the declared windows. See the
[problem](problem.md) for the complete contract.

MOS dimensions are rounded to the 10 nm physical grid. Parallel regrouping
within each original group preserves its rounded total W and L, with at most
10 um single-finger width; individual width/multiplicity and diffusion perimeter
change. Distributed 2 × 2 um body contacts have at most 20 um pitch.
All internal capacitors use `cap_cmim`:

- `c0`: `net063` (top) to `vout` (bottom), 1 parallel 51.3 × 51.3 um MIM units.
- `clocal`: `net050` (top) to `vout` (bottom), 4 parallel 51.64 × 51.64 um MIM units.
- `cout`: `vout` (top) to `vss` (bottom), 12 parallel 51.64 × 51.64 um MIM units.

The raw 10.0474 uA sink is calibrated to 1.255925 uA. The original
3.94789 pF `net063–vout` compensation remains. Approximately 16 pF is added
at `net050–vout` and another 48 pF at `vout–vss`. These are physical
compensation/output-storage devices, included in the netlist, area and
extracted simulation. This maintained circuit is explicitly not capless.
No ideal servo, diagnostic clamp or hidden damping element is part of this DUT.


## Files

- [Problem](problem.md): complete solver contract.
- [Configuration](case.toml): inputs, physical checks, metrics, scoring and witness.
- [Native circuit](materials/circuit.cdl) and [simulation circuit](materials/circuit.spice): matching physical device graphs.
- [Testbench](materials/testbench.spice): bias, bilateral loop and sustained recovery.
- [Reference layout](reference/amp_015_sau_cfcc.gds): independent physical witness.

Only the problem and three materials files enter solver inputs. Source records,
configuration, reference and qualification answers remain outside those inputs.
Collection license and notice accompany distributions separately.

## Reference Results

The independent witness passes native main/maximal DRC without waivers,
strict named-interface LVS, full functional geometry and all six nominal
post-layout conditions. It contains 225 MOS and 17 MIM devices with
physical well/substrate contacts. Functional area is 397,760.7744 um²;
score is 100. The fixed absolute target/zero anchors are
400,000/1,600,000 um², based on the complete physical device,
capacitor, contact and routing budget. Coefficient 8 reflects multistage
feedback, coupled physical compensation and loaded sustained recovery.
The long feasibility layout is not an area optimum.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `output_v` | V | 0.501727593–0.70175575 | 0.50188431–0.701912732 |
| `output_error_v` | V | 0.00172759309–0.00175574988 | 0.00188431025–0.00191273177 |
| `bias_v` | V | 0.727153284–0.727153505 | 0.727054441–0.727054688 |
| `power_w` | W | 2.28422469e-05–2.29243973e-05 | 2.29179627e-05–2.29993469e-05 |
| `dc_gain_db` | dB | 93.74538–95.57222 | 93.34345–95.34078 |
| `unity_hz` | Hz | 201599.6–203659.9 | 200691.6–202861.6 |
| `phase_margin_deg` | deg | 97.39206–97.82809 | 96.74–97.21597 |
| `final_unity_hz` | Hz | 201599.6–203659.9 | 200691.6–202861.6 |
| `final_phase_margin_deg` | deg | 97.39206–97.82809 | 96.74–97.21597 |
| `minimum_return_distance` | 1 | 0.665941964–0.69266267 | 0.585959798–0.622698914 |
| `return_phase_excursion_deg` | deg | 89.4457059–89.5026226 | 89.4352177–89.4983144 |
| `hf_gain_db` | dB | -71.20634–-69.26125 | -77.36761–-69.27791 |
| `recovery_up_v` | V | 0.001755749–0.001755751 | 0.00191273–0.001912738 |
| `recovery_down_v` | V | 0.001738622–0.001738971 | 0.001895625–0.001896033 |
| `step_gain` | V/V | 1.0001405–1.000141 | 1.000142–1.000142 |
| `mean_power_w` | W | 2.329226e-05–2.337913e-05 | 2.337032e-05–2.345742e-05 |
| `peak_v` | V | 0.7017558–0.704205 | 0.7022219–0.7060984 |
| `trough_v` | V | 0.5017276–0.5017276 | 0.5018843–0.5018843 |

The RC functional graph is independently checked after collapsing interconnect
resistors and applying Magic's ideal body-tie boundary. All original active
paths and original plus added capacitor endpoints remain. Native LVS separately
checks physical contacts and dimensions. Magic uses half-grid import, retains
only Metal3 interface text in an isolated extraction copy and retains every
parasitic R/C without a cutoff. The original GDS and its intrinsic tap labels
remain intact for native LVS. Fresh extractions may differ in internal names,
ordering and parasitic values; exact parasitic-graph identity is not claimed.
Each numerical comparison matrix uses one frozen reference RC.

All 33 simulation jobs pass: six source, six reference, nine half-step/tight/
trapezoidal jobs, three 1 ns-edge jobs, six source/RC 200 us long-tail jobs,
and three additional high-input tight AC jobs. Independent raw-waveform
reconstruction checks 576 observations, including window endpoints and
trapezoidal averages. The two-port Y matrix independently reconstructs Tian
Eq. 30 from both raw injections. Every sampled sweep has one descending unity
crossing; first/final crossings, minimum `abs(1+T)`, continuous return-difference
phase and high-frequency decay all pass. A good first crossover alone is not
used as evidence of stability.

Long-tail checks sustain the 2 mV bound throughout 50–75 us high and
100–195 us low windows. The 4 ns long-tail step supplements the 2/1 ns
nominal/half-step and Gear/trapezoidal checks. Tight runs use 600 AC points per
decade, `reltol=1e-6`, `abstol=1e-13`, `vntol=1e-9`, `rshunt=1e13`;
nominal values are explicitly listed in the problem. These solver settings
are not physical damping. Power includes internal bias and excludes external
bias-generator overhead; sink energy is not credited.

This is finite external-loop and observable recovery qualification, not a
complete internal-pole certificate, arbitrary-load stability, PVT, mismatch,
noise, distortion, rail-to-rail operation, startup or fabrication signoff.
The final reader preview passes with score 100; catalog regression separately
passes the supplied witness and rejects the empty layout with score zero.
Materialization and independent configuration checks pass with only the four
declared solver inputs. No framework, backend, PDK or image changes are needed.

## Reproduce

These operator commands require the installed `ICLayout-Bench-Private` package.
Run preparation from the Public checkout; run any `tests/integration/` commands
from the Private checkout using that environment.

Use the [shared tool setup](../../../../../docs/tools.md#manual-tools) from the
repository root. Reuse verified resources and the tools image. These commands
create fresh reader-generated evidence under `build/runs/`.

```bash
python -m layout_eval.preview prepare \
  --case amp_015_sau_cfcc --image iclayout-bench-tools:local \
  --output build/runs/amp_015_sau_cfcc-prepared
python -m layout_eval.preview run \
  --prepared build/runs/amp_015_sau_cfcc-prepared \
  --output build/runs/amp_015_sau_cfcc-reference
python -m pytest tests/integration/test_public_references.py \
  -k amp_015_sau_cfcc
```

Run the source and numerical matrix against that same frozen RC:

```bash
uv run --locked python - <<'PYCODE'
from pathlib import Path
import json, copy, tomllib, concurrent.futures, sys
from benchmarking.tasks import load_task
from layout_eval.toolchains import load_toolchain
from benchmarking.evaluation import parse_evaluation
from layout_eval.evaluate import run_evaluation
from benchmarking.files import Asset

root = Path("build/runs/amp_015_sau_cfcc-checks")
case = Path("build/runs/amp_015_sau_cfcc-prepared/case/case.toml")
reference = Path("build/runs/amp_015_sau_cfcc-reference/reference")
task = load_task(case)
report = json.loads((reference / "report.json").read_text())
assert report["task_success"]
backends = load_toolchain(case)
rc = Asset(
    (
        reference / report["jobs"]["parasitics"]["outputs"]["netlist"]["path"]
    ).read_bytes(),
    "spice",
)
base = tomllib.loads(case.read_text())["task"]["evaluation"]


def run(item):
    variant, index = item
    plan = copy.deepcopy(base)
    plan["mode"] = "characterization"
    plan.pop("scoring")
    jobs = [j for j in plan["jobs"] if j["stage"] == "simulate"]
    job = jobs[index]
    job["inputs"]["dut"] = "input:simulation"
    plan["jobs"] = [job]
    plan["metrics"] = [m for m in plan["metrics"] if m["category"] == "performance"]
    for metric in plan["metrics"]:
        metric["observations"] = [
            x for x in metric["observations"] if x.startswith(job["id"] + ":")
        ]
        for key in ("dimension", "zero_lower", "zero_upper"):
            metric.pop(key, None)
    inputs = task.evaluation_inputs()
    inputs["input:simulation"] = rc
    if variant in ("source", "long-tail-source"):
        inputs["input:simulation"] = task.evaluation_inputs()["input:simulation"]
    deck = inputs["input:performance"].content.decode()
    if variant in ("tight", "tight-ac"):
        deck = deck.replace(
            "rshunt=1e12 reltol=1e-5 abstol=1e-12 vntol=1e-8",
            "rshunt=1e13 reltol=1e-6 abstol=1e-13 vntol=1e-9",
        ).replace("ac dec 300", "ac dec 600")
    if variant == "half-step":
        deck = deck.replace("tran 2n 40u 0 2n", "tran 1n 40u 0 1n")
    if variant == "trap":
        deck = deck.replace("method=gear maxord=2", "method=trap maxord=2")
    if variant == "fast":
        deck = deck.replace("20n 20n", "1n 1n").replace("from=20.04u", "from=20.002u")
    if variant.startswith("long-tail"):
        for old, new in [
            ("18u 100u", "78u 400u"),
            ("tran 2n 40u 0 2n", "tran 4n 200u 0 4n"),
            ("from=15u to=19u", "from=50u to=75u"),
            ("from=30u to=39u", "from=100u to=195u"),
            ("from=18u to=19u", "from=70u to=75u"),
            ("from=38u to=39u", "from=190u to=195u"),
            ("from=2u to=40u", "from=2u to=200u"),
            ("from=2u to=20u", "from=2u to=80u"),
            ("from=20.04u to=40u", "from=80.04u to=200u"),
        ]:
            deck = deck.replace(old, new)
    if variant == "tight-ac":
        deck = deck.split("\nreset")[0] + "\nquit\n.endc\n.end\n"
        job["outputs"].pop("transient")
        job["parameters"]["exports"].pop("transient")
        excluded = {
            "recovery_up_v",
            "recovery_down_v",
            "step_gain",
            "mean_power_w",
            "peak_v",
            "trough_v",
        }
        plan["metrics"] = [m for m in plan["metrics"] if m["id"] not in excluded]
        job["parameters"]["measurements"] = {
            k: v
            for k, v in job["parameters"]["measurements"].items()
            if k not in excluded
        }
    inputs["input:performance"] = Asset(deck.encode(), "spice")
    report = run_evaluation(
        parse_evaluation(json.dumps(plan).encode(), file_format="json"),
        inputs,
        backends,
        root / f"{variant}-{index}",
    )
    print(variant, index, report["outcome"], flush=True)
    assert report["outcome"] == "passed", (variant, index, report)


items = (
    [("source", i) for i in range(6)]
    + [
        (v, i)
        for v in ["half-step", "tight", "trap", "fast", "long-tail", "long-tail-source"]
        for i in range(3)
    ]
    + [("tight-ac", i) for i in range(3, 6)]
)
with concurrent.futures.ThreadPoolExecutor(6) as pool:
    list(pool.map(run, items))

PYCODE
```

### Independent waveform audit

```bash
uv run --locked python - <<'PYCODE'
from pathlib import Path
import sys, json, math, cmath, bisect, tomllib

sys.path.insert(0, "tests")
from helpers.spice_raw import read_raw

case_name = "amp_015_sau_cfcc"
base = Path("build/runs/amp_015_sau_cfcc-reference")
root = Path("build/runs/amp_015_sau_cfcc-checks")
case = Path("build/runs/amp_015_sau_cfcc-prepared/case/case.toml")
limits = {
    m["id"]: (m.get("lower"), m.get("upper"))
    for m in tomllib.loads(case.read_text())["task"][
        "evaluation"
    ]["metrics"]
}


def interp(t, y, x):
    i = bisect.bisect_left(t, x)
    if i == 0:
        return y[0]
    if i == len(t):
        assert abs(x - t[-1]) < 1e-12
        return y[-1]
    return y[i - 1] + (y[i] - y[i - 1]) * (x - t[i - 1]) / (t[i] - t[i - 1])


def window(t, y, a, b):
    return (
        [(a, interp(t, y, a))]
        + [(x, v) for x, v in zip(t, y) if a < x < b]
        + [(b, interp(t, y, b))]
    )


def avg(t, y, a, b):
    p = window(t, y, a, b)
    return sum((x2 - x1) * (y1 + y2) / 2 for (x1, y1), (x2, y2) in zip(p, p[1:])) / (
        b - a
    )


def phase(h):
    a = []
    for z in h:
        x = math.degrees(cmath.phase(z))
        if a:
            while x - a[-1] > 180:
                x -= 360
            while x - a[-1] < -180:
                x += 360
        a.append(x)
    return a


out = []
reports = [base / "reference/report.json"] + sorted(root.glob("*/report.json"))
for report_path in reports:
    p = report_path.parent
    folder = str(p)
    q = json.loads((p / "report.json").read_text())
    assert q["outcome"] == "passed", (folder, q["outcome"])
    plan = json.loads((p / q["plan"]["path"]).read_text())
    for name, j in q["jobs"].items():
        if j["stage"] != "simulate":
            continue
        raw = {
            k: read_raw((p / v["path"]).read_bytes()) for k, v in j["outputs"].items()
        }
        assert len(raw["ac"]) == len(raw["voltage"])
        h = []
        res = []
        for x, z in zip(raw["ac"], raw["voltage"]):
            assert x["frequency"] == z["frequency"]
            e1 = z["v(vm)"]
            f1 = z["v(vout)"]
            i1 = z["i(vprobe)"]
            e2 = x["v(vm)"]
            f2 = x["v(vout)"]
            i2 = x["i(vprobe)"]
            det = e1 * f2 - e2 * f1
            y11 = (-i1 * f2 - (1 - i2) * f1) / det
            y12 = (i1 * e2 + (1 - i2) * e1) / det
            y21 = (i1 * f2 - i2 * f1) / det
            y22 = (-i1 * e2 + i2 * e1) / det
            v = (y12 + y21) / (y11 + y22)
            h.append(v)
            res.append(abs(v - x["transfer"]) / max(abs(v), 1e-5))
        assert all(math.isfinite(z.real) and math.isfinite(z.imag) for z in h)
        assert max(res) < 1e-5, max(res)
        f = [x["frequency"].real for x in raw["ac"]]
        assert math.isclose(f[0], 0.01, rel_tol=1e-9)
        assert math.isclose(f[-1], 1e10, rel_tol=1e-9)
        assert all(b > a for a, b in zip(f, f[1:]))
        g = [20 * math.log10(abs(x)) for x in h]
        ph = phase(h)
        rp = phase([1 + x for x in h])
        cross = [i for i in range(1, len(h)) if g[i] * g[i - 1] < 0]
        assert abs(ph[0]) < 0.5
        assert len(cross) == 1, (folder, name, cross)
        idx = cross[0]
        assert g[idx] < g[idx - 1]
        u = -g[idx - 1] / (g[idx] - g[idx - 1])
        fc = f[idx - 1] + u * (f[idx] - f[idx - 1])
        pm = 180 + ph[idx - 1] + u * (ph[idx] - ph[idx - 1])
        op = raw["op"][0]
        vin = next(x for x in plan["jobs"] if x["id"] == name)["parameters"]["values"][
            "input_v"
        ]
        expected = dict(
            output_v=op["v(vout)"],
            output_error_v=abs(op["v(vout)"] - vin),
            bias_v=op["v(vb1)" if case_name.startswith("amp_012") else "v(net013)"],
            power_w=-1.2 * op["i(vdd)"],
            dc_gain_db=g[0],
            unity_hz=fc,
            phase_margin_deg=pm,
            final_unity_hz=fc,
            final_phase_margin_deg=pm,
            minimum_return_distance=min(abs(1 + x) for x in h),
            return_phase_excursion_deg=max(abs(x) for x in rp),
            hf_gain_db=max(x for ff, x in zip(f, g) if 2e9 <= ff <= 1e10),
        )
        tail = None
        if "transient" in raw:
            tr = raw["transient"]
            t = [x["time"] for x in tr]
            v = [x["v(vout)"] for x in tr]
            err = [abs(x["v(vout)"] - x["v(vp)"]) for x in tr]
            long = "long" in folder
            hi = (50e-6, 75e-6) if long else (15e-6, 19e-6)
            lo = (100e-6, 195e-6) if long else (30e-6, 39e-6)
            hm = (70e-6, 75e-6) if long else (18e-6, 19e-6)
            lm = (190e-6, 195e-6) if long else (38e-6, 39e-6)
            end = 200e-6 if long else 40e-6
            assert t[0] <= 1e-12 and math.isclose(t[-1], end, rel_tol=1e-9)
            assert all(b > a for a, b in zip(t, t[1:]))
            fall = 80.04e-6 if long else (20.002e-6 if "fast" in folder else 20.04e-6)

            def mx(y, a, b):
                return max(z for x, z in zip(t, y) if a <= x <= b)

            assert max(z for x, z in window(t, err, *hi)) <= 0.002
            assert max(z for x, z in window(t, err, *lo)) <= 0.002
            expected.update(
                recovery_up_v=mx(err, *hi),
                recovery_down_v=mx(err, *lo),
                step_gain=(avg(t, v, *hm) - avg(t, v, *lm)) / 0.2,
                mean_power_w=avg(t, [-1.2 * x["i(vdd)"] for x in tr], 2e-6, end),
                peak_v=mx(v, 2e-6, (80e-6 if long else 20e-6)),
                trough_v=-mx([-x for x in v], fall, end),
            )
            tail = mx(v, *lm) + mx([-x for x in v], *lm)
        for k, x in expected.items():
            actual = q["metrics"][k]["observations"][name + ":" + k]["value"]
            assert math.isclose(x, actual, rel_tol=1e-5, abs_tol=3e-8), (
                folder,
                name,
                k,
                x,
                actual,
            )
            lo, hi = limits[k]
            assert lo <= x <= hi, (folder, name, k, x, limits[k])
        out.append(
            dict(
                folder=folder,
                job=name,
                observations=len(expected),
                twoport_relative_residual=max(res),
                crossings=[dict(hz=fc, pm_deg=pm)],
                low_tail_span_v=tail,
            )
        )
(root / "waveform-audit.json").write_text(json.dumps(out, indent=2))
print(
    len(out),
    "jobs",
    sum(x["observations"] for x in out),
    "observations independently verified",
)

PYCODE
```

### Calibration boundary

Qualification applies to the explicitly compensated maintained circuit.
The 5/15 pF load endpoints and 1 ns stimulus edges above are finite boundary
checks; no extrapolation beyond them is claimed.

### Extracted functional graph audit

This independent check preserves terminal roles and physical device dimensions,
collapsing only parasitic interconnect resistors and idealized tap connections.

```bash
uv run --locked python - <<'PYCODE'
from pathlib import Path
import json, hashlib, collections, tomllib
case = Path("build/runs/amp_015_sau_cfcc-prepared/case/case.toml")
reference = Path("build/runs/amp_015_sau_cfcc-reference/reference")
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

Derived from [the fixed source snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_015_sau_cfcc).
IHP raw DUT SHA-256: `4a36b71803bfc2a6fb18296c8a24815887837a3f68285bd76c0e18a2417553af`.
Selected raw DUT, manifest, analyses and collection licensing files were checked
against the fixed Git tree. Normalized circuit derivatives and the independent
witness retain PolyForm Noncommercial, Required Notice and recorded CODA-Team
AnalogGym BSD-3-Clause component terms in collection [LICENSE](../../LICENSE)
and [NOTICE](../../NOTICE). The separately authored native measurement deck
is MIT. Component labels do not relicense normalized materials or the witness.
