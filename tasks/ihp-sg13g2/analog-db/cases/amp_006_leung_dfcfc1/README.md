> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Output-Controlled Auxiliary Compensation OTA

## Overview

The folded PMOS input stage drives `net050`, which feeds the output PMOS
and a PMOS/diode/NMOS mirror path to `net049`. That node drives the output
NMOS and a separate auxiliary common-source NMOS at `net1`, with a biased
PMOS load. C0 spans `net050`–output and C1 spans `net049`–`net1`.
Unlike AMP007, the auxiliary stage senses the NMOS output control node;
AMP007 senses `net050` with a PMOS and terminates compensation at `net2`.
These different control nodes, active paths and capacitor endpoints establish
the topology distinction; the measurements below establish its finite scope.

All 26 source MOS groups remain. MOS dimensions are rounded to the 10 nm
PyCell grid; integer parallel regrouping reduces 1,413 rounded source fingers
to 675 physical fingers, preserving each group's rounded total W and L.
Individual finger W/m and diffusion perimeter change, with width <=10 um.
The 400-finger PMOS output device remains 400 fingers. Both internal capacitor
branches become complete MIM arrays: eight 48.935 um square C0 devices and
three 50.94 um square C1 devices, approximately 28.74/11.68 pF.
The raw 27.4754 uA sink is explicitly calibrated to an external 6.86885 uA
sink to support the declared headroom and tracking. Internal bias mirrors,
the separate source-tied input well and both compensation branches remain.
Distributed physical 2 x 2 um contacts at <=20 um pitch connect the wells and
substrate. No hidden output servo or internal numerical damping is introduced.

Qualification covers 1.2 V, typical LV models, 27 C, 5/10/20 pF loads,
0.5/0.7 V operating points, bilateral return ratio and finite 0.5↔0.7 V
tracking after approximately 3 us. See the [problem](problem.md) for the
complete interface, measurement definitions, bounds and physical requirements.

## Files

- [Problem](problem.md): complete solver contract.
- [Configuration](case.toml): declared inputs, checks, limits, scoring and witness.
- [Native circuit](materials/circuit.cdl) and [simulation circuit](materials/circuit.spice): matching physical device graphs.
- [Testbench](materials/testbench.spice): bias, bilateral loop and recovery measurements.
- [Reference layout](reference/amp_006_leung_dfcfc1.gds): independent physical witness.

Only the problem and three materials files enter solver inputs. Collection
licenses and notices accompany distributions separately. Source checkouts,
upstream generators, DSL, witness and qualification answers are excluded.

## Reference Results

The reference passes native main/maximal DRC without waivers, strict named-port
LVS, full functional geometry and all six nominal post-layout conditions.
Functional area is 762,378.1052 um²; nominal score is 100. The fixed absolute
area target/zero anchors are 800,000/3,200,000 um², supported by the complete
675-finger, eleven-MIM independent layout, physical taps and full routing.
Coefficient 8 reflects coupled multistage auxiliary compensation, loaded
bilateral response and sustained recovery. This long feasibility witness is
not an area optimum.

Ranges cover 0.5/0.7 V operating points and 5/10/20 pF loads. Power includes
the on-chip bias network and excludes external bias-generator overhead.
Bias-sink energy is not credited as recovered supply power.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `output_v` | V | 0.50281187–0.70297998 | 0.50371133–0.70393284 |
| `output_error_v` | V | 0.0028118651–0.0029799754 | 0.0037113343–0.003932839 |
| `bias_v` | V | 0.66852399–0.66852442 | 0.6608879–0.66088822 |
| `power_w` | W | 0.00011971951–0.00012011829 | 0.00012235452–0.00012300756 |
| `dc_gain_db` | dB | 95.37677–98.19628 | 95.73468–98.37732 |
| `unity_hz` | Hz | 546056.4–574201.7 | 589380.8–637743.1 |
| `phase_margin_deg` | deg | 80.55115–81.93171 | 81.84918–83.56516 |
| `final_unity_hz` | Hz | 546056.4–574201.7 | 589380.8–637743.1 |
| `final_phase_margin_deg` | deg | 80.55115–81.93171 | 81.84918–83.56516 |
| `minimum_return_distance` | 1 | 0.8047943–0.84772962 | 0.73858462–0.75198342 |
| `return_phase_excursion_deg` | deg | 89.556499–89.622004 | 89.553024–89.616259 |
| `hf_gain_db` | dB | -50.95392–-43.18098 | -71.62955–-63.85617 |
| `recovery_up_v` | V | 0.002978925–0.002978926 | 0.003932837 |
| `recovery_down_v` | V | 0.002831263–0.002837292 | 0.003730845–0.003735375 |
| `step_gain` | V/V | 1.00084 | 1.0011075 |
| `mean_power_w` | W | 0.0001198889–0.0001198912 | 0.0001226652–0.0001226678 |
| `peak_v` | V | 0.7029789 | 0.7039328 |
| `trough_v` | V | 0.5028109 | 0.5037113 |

The independent RC graph audit preserves all 686 functional devices
(675 MOS and 11 MIM). After collapsing parasitic interconnect resistors and
applying Magic's ideal-tap boundary, terminal-role comparison uniquely maps
19 nets, including distinct capacitor plates and the source-tied input well.
Native LVS separately checks the physical contacts and device dimensions.
Magic uses half-grid import and keeps only Metal3 interface text in its
isolated extraction copy, avoiding repeated intrinsic well-name aliases;
native LVS reads the original GDS with those intrinsic contact labels intact.
No parasitic R/C threshold removes small elements.
Independent fresh extractions can differ in internal node names/order and
parasitic values. Their functional terminal graphs are independently checked;
no byte or exact parasitic-graph identity is claimed. All final numerical
comparisons use one frozen RC from the repeated reference evaluation.

The bilateral measurement uses two injections at the input/output boundary
and Tian Eq. 30, independently checked by reconstructing the two-port Y
matrix from the exported voltages/currents. Every sampled sweep is checked
for all unity crossings, the first/final descending crossing, minimum
`abs(1+T)`, full continuous return-difference phase and 2–10 GHz decay.
Natural low-frequency phase is retained. This is a finite external-loop and
observable-recovery qualification, not a complete internal-pole or Nyquist
certificate. DC bias accuracy and sustained positive/negative step recovery
are independent requirements.

All 30 final simulation jobs pass: six source, six reference, nine
half-step/tight/trapezoidal jobs, three additional high-input tight AC jobs,
and six source/RC long-tail jobs. Independent raw-waveform reconstruction
checks **522 observations**, including exact in-window extrema, interpolated
endpoints and trapezoidal means. Every AC sweep has one unity crossing and
natural low-frequency phase. Reconstructed two-port admittance independently
agrees with the deck's bilateral return ratio.

Every required bound survives halving the maximum step to 1 ns, separately
tightening current/relative/voltage tolerances tenfold with 600 AC points per
decade and a 1e13 ohm shunt, and changing Gear order 2 to trapezoidal integration.
The two DC input points share the same transient pulse-start state, so each
numerical transient variant covers the three unique loads; additional tight
AC jobs cover the 0.7 V input point. Maximum changes relative to the matching
nominal reference conditions are:

| Variant | Unity frequency (Hz) | Phase margin (deg) | Sustained recovery error (V) | Peak/trough (V) |
| --- | --- | --- | --- | --- |
| half-step | 0 | 0 | 4.3e-08 | 0 |
| tight | 2.6 | 0.00047 | 1.0234e-05 | 1.02e-05 |
| trap | 0 | 0 | 4.6e-08 | 0 |

Single-pulse 200 us source and RC checks sustain the same 5 mV tracking bound
through the complete 50–75 us high and 100–195 us low windows. Their 10 ns
maximum step checks late recovery and supplements the 2/1 ns fast-response
and integration-method controls. The final catalog regression separately passes
the supplied witness and rejects an empty layout with score zero. A further
reader-preview execution of the final qualified definition also passes with
score 100; its 108 observations are independently rechecked separately.

The absolute-current numerical floor is explicitly calibrated: the initial
experimental 10 fA baseline and 1 fA tighter profiles are replaced by 1 pA
and 0.1 pA. Extracted branches reach approximately 1 mOhm; current convergence
there can request voltage differences below floating-point resolution around
1 V. The fA profiles can require tens of thousands of iterations even during
static prefixes and exceed the runtime envelope. Electrical acceptance bounds,
RC elements, device models and integration order are retained. The maintained
profile is checked with tenfold tighter relative/voltage tolerances, a 1e13 ohm
shunt, 0.1 pA absolute tolerance, doubled AC density, 1 ns steps and trapezoidal
integration. This calibrates solver precision without adding physical damping.

The KLU solver and explicit saved external vectors keep the complete RC
within the tool resource envelope; saving fewer vectors does not remove
internal circuit nodes or devices. Gear order 2 uses the explicit `itl4=1000` iteration ceiling. The numeric shunt remains explicit and its
sensitivity is included in the numerical checks. Source simulation includes
finite tap models, while Magic RC idealizes well/substrate ties. Distributed
substrate noise, PVT, mismatch, startup, noise/distortion, rail-to-rail use,
arbitrary loads and fabrication signoff remain outside qualification.
No framework, backend, PDK or tool image changes are required.

## Reproduce

These operator commands require the installed `ICLayout-Bench-Private` package.
Run preparation from the Public checkout; run any `tests/integration/` commands
from the Private checkout using that environment.

Use the [shared tool setup](../../../../../docs/tools.md#manual-tools) from
the repository root. Reuse verified resources and the tools image; the commands
below create the reader's own fresh reports under `build/runs/`.

```bash
python -m layout_eval.preview prepare \
  --case amp_006_leung_dfcfc1 --image iclayout-bench-tools:local \
  --output build/runs/amp_006_leung_dfcfc1-prepared
python -m layout_eval.preview run \
  --prepared build/runs/amp_006_leung_dfcfc1-prepared \
  --output build/runs/amp_006_leung_dfcfc1-reference
python -m pytest tests/integration/test_public_references.py \
  -k amp_006_leung_dfcfc1
```

After the preview, reproduce source and numerical checks using the same
frozen candidate RC. The two DC points share the transient pulse-start
operating point; the long-tail diagnostic therefore uses the three unique
load transients. Its 10 ns step examines late recovery and supplements the
2/1 ns fast-response checks; it does not establish all high-frequency modes.
Keep the acceptance bounds unchanged.

```bash
uv run --locked python - <<'PYCODE'
from pathlib import Path
import json, copy, tomllib, concurrent.futures, sys
from benchmarking.tasks import load_task
from layout_eval.toolchains import load_toolchain
from benchmarking.evaluation import parse_evaluation
from layout_eval.evaluate import run_evaluation
from benchmarking.files import Asset

root = Path("build/runs/amp_006_leung_dfcfc1-checks")
case = Path("build/runs/amp_006_leung_dfcfc1-prepared/case/case.toml")
reference = Path("build/runs/amp_006_leung_dfcfc1-reference/reference")
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
        deck = deck.replace("tran 2n 18u 0 2n", "tran 1n 18u 0 1n")
    if variant == "trap":
        deck = deck.replace("method=gear maxord=2", "method=trap maxord=2")
    if variant.startswith("long-tail"):
        for old, new in [
            ("8u 16u", "78u 400u"),
            ("tran 2n 18u 0 2n", "tran 10n 200u 0 10n"),
            ("from=5u to=9.5u", "from=50u to=75u"),
            ("from=13u to=17.5u", "from=100u to=195u"),
            ("from=9u to=9.5u", "from=70u to=75u"),
            ("from=17u to=17.5u", "from=190u to=195u"),
            ("from=2u to=18u", "from=2u to=200u"),
            ("from=2u to=10u", "from=2u to=80u"),
            ("from=10.04u to=18u", "from=80.04u to=200u"),
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
        for v in ["half-step", "tight", "trap", "long-tail", "long-tail-source"]
        for i in range(3)
    ]
    + [("tight-ac", i) for i in range(3, 6)]
)
with concurrent.futures.ThreadPoolExecutor(6) as pool:
    list(pool.map(run, items))

PYCODE
```

To probe the numerical boundary, repeat the tight jobs in a fresh output
directory with only `abstol=1e-13` changed to `abstol=1e-15`. Keep the other
tight settings, RC and electrical bounds fixed. The fA probe can exceed the
600 s job limit; completion time depends on the extracted ordering and
numerical conditioning. Record incomplete execution as a runtime/convergence
gap, without substituting it for an electrical stability result.

### Independent waveform audit

After the runs above, this reconstructs the bilateral ratio from raw voltage
and current samples, checks every unity crossing and sustained recovery window,
and independently recomputes all 522 scalar observations. It checks ngspice's
in-window extrema and also the interpolated interval endpoints. The shared raw
reader is part of this checkout; no development run or authoring generator is
needed.

```bash
uv run --locked python - <<'PYCODE'
from pathlib import Path
import sys, json, math, cmath, bisect, tomllib

sys.path.insert(0, "tests")
from helpers.spice_raw import read_raw

root = Path("build/runs/amp_006_leung_dfcfc1-checks")
case = Path("build/runs/amp_006_leung_dfcfc1-prepared/case/case.toml")
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
reports = [Path("build/runs/amp_006_leung_dfcfc1-reference/reference/report.json")] + sorted(root.glob("*/report.json"))
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
        assert max(res) < 1e-5, max(res)
        f = [x["frequency"].real for x in raw["ac"]]
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
            bias_v=op["v(net013)"],
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
            hi = (50e-6, 75e-6) if long else (5e-6, 9.5e-6)
            lo = (100e-6, 195e-6) if long else (13e-6, 17.5e-6)
            hm = (70e-6, 75e-6) if long else (9e-6, 9.5e-6)
            lm = (190e-6, 195e-6) if long else (17e-6, 17.5e-6)
            end = 200e-6 if long else 18e-6
            fall = 80.04e-6 if long else 10.04e-6

            def mx(y, a, b):
                return max(z for x, z in zip(t, y) if a <= x <= b)

            assert max(z for x, z in window(t, err, *hi)) <= 0.005
            assert max(z for x, z in window(t, err, *lo)) <= 0.005
            expected.update(
                recovery_up_v=mx(err, *hi),
                recovery_down_v=mx(err, *lo),
                step_gain=(avg(t, v, *hm) - avg(t, v, *lm)) / 0.2,
                mean_power_w=avg(t, [-1.2 * x["i(vdd)"] for x in tr], 2e-6, end),
                peak_v=mx(v, 2e-6, fall - 40e-9),
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

## Source and License

Derived from [AMP006 at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_006_leung_dfcfc1).
The IHP raw DUT SHA-256 is
`74f446ca092d50f5ef367d1987db3985eafc5d8fd3587a0cc7eeb6f748b35131`.
Selected raw DUT, manifest, analyses and collection licensing files were
checked against the fixed Git tree. The normalized circuit derivatives and
independent witness retain PolyForm Noncommercial, the Required Notice and
recorded CODA-Team AnalogGym BSD-3-Clause component terms in collection
[LICENSE](../../LICENSE) and [NOTICE](../../NOTICE). The separately authored
native measurement deck is MIT. Component manifest labels do not relicense
normalized materials or the independent witness MIT.
