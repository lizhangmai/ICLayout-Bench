> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Self-Starting Isolated-Body PTAT Core

## Overview

This GF180MCU D case retains the classic resistor-degenerated four-MOS core,
including its output-connected NMOS body, and adds three MOS for startup.
It qualifies nominal positive temperature slope and zero-state power-up at
specified supply ramps with a 100 fF external load. Output and slope depend
on supply; it is not a precision temperature reference or a pF-load buffer.

The independent witness uses an isolated P-well inside a supply-tied deep
N-well, an explicit N-well annulus and physical body/substrate contacts.
The annulus preserves isolation through the declared Magic RC route without
changing the PDK decks. The original four MOS W/L/m are retained. A 2 by
40 um high-resistance poly device realizes the nominal 20 kohm resistor.
A weak 0.42/20 um PMOS, 2/0.28 um NMOS detector and 0.42/1 um NMOS injector
form the added startup branch. The injection path turns off after bias is
established; the weak bias branch retains static current, included in power.
The maintained circuit therefore differs explicitly from the upstream 4T core.

## Files

| File | Role and consumer |
| --- | --- |
| [case.toml](case.toml) | Native contract, tool/resource bindings, scoring, provenance and witness digest |
| [problem.md](problem.md) | Complete solver-facing requirements; description input |
| [materials/circuit.cdl](materials/circuit.cdl) | Physical LVS authority; netlist input |
| [materials/circuit.spice](materials/circuit.spice) | Equivalent four-terminal simulator circuit; simulation input |
| [materials/testbench.spice](materials/testbench.spice) | Temperature and zero-state startup measurements; performance input |
| [reference/tsn_002_ptat_classic.gds](reference/tsn_002_ptat_classic.gds) | Independent ready-to-use physical witness; maintainer asset |

The physical isolated NMOS is `MM0 ... nfet_03v3_dn`; its simulator call is
`XM0 ... nfet_03v3`. D/G/S/B and W/L/m agree, and source/body both remain on
`vout`. Other devices have the same calls in both representations. This model
mapping is why a separate simulation input is required. References, host
configuration, source records and this README are excluded from solver inputs.
Collection LICENSE and NOTICE accompany material distributions separately.

## Reference Results

The reference passes artifact checks, GF180 variant-D DRC including antenna,
strict named-port LVS, geometry, candidate RC and every electrical band. Its
functional footprint is 214.18 by 61.43 um, area **13157.0774 um2**, with
`layout-v1` score **100**. This is a witness score, not a model evaluation.

The table spans all 18 combinations of 2.7/3.0/3.3 V, -20/27/100 C and
0.1/10 us linear supply ramps, with a 100 fF output load. Each job includes
a 121-point -20 to 100 C sweep and a zero-state `uic` transient through
100 us. Final startup observations use 90–100 us. At 27 C, post-layout output
is approximately 134.88–138.81 mV. All models are typical, without statistical
variation.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `output_v` | V | 0.1166461 to 0.1726296 | 0.1165768 to 0.1723956 |
| `power_w` | W | 3.240497e-05 to 6.403142e-05 | 3.230809e-05 to 6.377383e-05 |
| `cold_v` | V | 0.1166461 to 0.1201363 | 0.1165768 to 0.1200731 |
| `hot_v` | V | 0.1678079 to 0.1726296 | 0.1675734 to 0.1723956 |
| `slope_v_per_c` | V/C | 0.0004263483 to 0.0004374442 | 0.0004249717 to 0.0004360208 |
| `curvature_v` | V | 0.001773968 to 0.001860855 | 0.001761301 to 0.001847731 |
| `minimum_slope` | V/C | 0.0003694495 to 0.0003778229 | 0.000368479 to 0.0003767974 |
| `maximum_slope` | V/C | 0.0004842871 to 0.0004983875 | 0.000482488 to 0.0004965252 |
| `peak_power_w` | W | 4.945078e-05 to 6.403142e-05 | 4.924548e-05 to 6.377383e-05 |
| `startup_error_v` | V | 5.107026e-15 to 1.783912e-08 | 3.249415e-12 to 7.470911e-09 |
| `ripple_v` | V | 0 to 0 | 0 to 0 |
| `final_power_w` | W | 3.240497e-05 to 6.403142e-05 | 3.230809e-05 to 6.377383e-05 |

The reported zero ripple is limited by ngspice's printed measurement precision;
it does not claim an identically constant physical voltage. Independent raw
waveform reconstruction checks output, power, endpoint slope/curvature,
finite-difference local slope, startup error, ripple and time-integrated power.
The maximum timestep of 1 ns is compared with 0.5 ns over all 18 post-layout
startup conditions; both retain the declared acceptance result. The largest
change in reported final-window startup error is below 4 pV; printed ripple
and final average power are unchanged. These numerical checks do not extend
the nominal physical/model scope.

The 0.40–0.47 mV/C endpoint-slope band and 3 mV curvature ceiling preserve
positive-temperature behavior with explicit nominal model tolerance. Startup
requires error and ripple at most 1 mV throughout the final window, excluding
the zero-bias branch and sustained oscillation. Supply power is at most 80 uW,
including startup bias. The coefficient is 6 for coupled startup/temperature
behavior and isolated-body layout. Fixed area anchors are 14000/56000 um2,
with the lower budget demonstrated feasible by this witness. The witness is
not an area optimum. Electrical zero-score boundaries are fixed in the
problem and plan; neither area nor attainment depends on a changing reference
ratio or model population.

Candidate wiring RC and device geometry are retained. The substrate model is
not a distributed silicon network. Qualification covers the declared 100 fF
load; larger loads can oscillate. Brownout/restart, arbitrary ramps, process
corners, mismatch, noise, supply rejection, absolute temperature accuracy and
fabrication signoff remain outside scope. Settling in the final window does
not establish a first-crossing startup-time or overshoot bound.

## Reproduce

From the repository root, prepare the existing image and reviewed bundles with
the [GF180 instructions](../../../../../docs/tools.md#gf180), then run:

```bash
python -m layout_eval.cli evaluate \
  tasks/gf180mcuD/analog-db/cases/tsn_002_ptat_classic/case.toml \
  tasks/gf180mcuD/analog-db/cases/tsn_002_ptat_classic/reference/tsn_002_ptat_classic.gds \
  --output build/runs/analog-db-tsn_002_ptat_classic-reference
```

This creates an identity-bound report, candidate netlist and raw waveforms in
the selected output directory. Use fresh directories for each run. Reproduce
the pre-layout column with the shared
[source-calibration recipe](../../../../../docs/tools.md#gf180-source-calibration),
using this case path and a fresh `build/runs/analog-db-tsn_002_ptat_classic-source`
destination. The recipe uses this case's `simulation` input and all 18 jobs;
characterization has no layout score.

Repeat the timestep comparison against the extracted reference with all 18
conditions. This creates a separate unscored characterization and changes only
the transient timestep; it does not modify the maintained contract:

```bash
uv run --locked python - <<'PYCODE'
import json, tomllib
from pathlib import Path
from benchmarking.tasks import load_task
from layout_eval.toolchains import load_toolchain
from benchmarking.evaluation import parse_evaluation
from layout_eval.evaluate import run_evaluation
from benchmarking.files import Asset

case = Path("tasks/gf180mcuD/analog-db/cases/tsn_002_ptat_classic/case.toml")
reference = Path("build/runs/analog-db-tsn_002_ptat_classic-reference")
output = Path("build/runs/analog-db-tsn_002_ptat_classic-half-step")
task = load_task(case)
plan = tomllib.loads(case.read_text())["task"]["evaluation"]
plan["mode"] = "characterization"
plan.pop("scoring")
plan["jobs"] = [j for j in plan["jobs"] if j["stage"] == "simulate"]
for j in plan["jobs"]:
    j["inputs"]["dut"] = "input:simulation"
plan["metrics"] = [m for m in plan["metrics"] if m["category"] == "performance"]
for m in plan["metrics"]:
    for key in ["dimension", "zero_lower", "zero_upper"]:
        m.pop(key, None)
report = json.loads((reference / "report.json").read_text())
assert report["task_success"]
netlist = reference / report["jobs"]["parasitics"]["outputs"]["netlist"]["path"]
inputs = task.evaluation_inputs()
inputs["input:simulation"] = Asset(netlist.read_bytes(), "spice")
inputs["input:performance"] = Asset(
    inputs["input:performance"].content.replace(
        b"tran 1n 100u 0 1n uic", b"tran 0.5n 100u 0 0.5n uic"
    ),
    "spice",
)
result = run_evaluation(
    parse_evaluation(json.dumps(plan).encode(), file_format="json"),
    inputs,
    load_toolchain(case),
    output,
)
assert result["outcome"] == "passed"
print(result["outcome"])
PYCODE
```

```bash
uv run --locked --group eda pytest tests/integration/test_public_references.py \
  -k tsn_002_ptat_classic
uv run --locked --group eda pytest tests/integration/test_magic_rc.py \
  -k isolated_body
```

The first command evaluates the published witness and rejects an empty layout;
the second checks rejection of unintended body/substrate RC connectivity and
the explicit N-well control. Retain collection LICENSE and NOTICE with material
exports; solver materialization alone is not a redistribution package.

## Source and License

Derived from [MacAnalog analog-db tsn_002_ptat_classic](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/tsn_002_ptat_classic).
The normalized derivative and witness retain the [collection license](../../LICENSE)
and [notices](../../NOTICE), including PolyForm Noncommercial and applicable
CODA-Team BSD attribution. The independent measurement deck is MIT. Manifest
license labels do not relicense the normalized materials as a whole.
