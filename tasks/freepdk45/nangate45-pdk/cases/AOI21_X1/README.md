> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# AND-OR-Invert Gate

## Overview

Nominal, predictive **qualified** layout task with a distributed passing witness.
The [problem](problem.md) defines the complete circuit, stimuli, limits and score.
Coefficient **2** covers a compact loaded compound logic cell.
The reference adds explicit well/substrate taps and extends rails to them, extends the outer poly ends by 10 nm, encloses poly contacts by at least 5 nm, and centers rail labels inside metal. Transistor W/L and topology are unchanged.

## Files

| File | Purpose |
| --- | --- |
| [problem.md](problem.md) | Solver objective, interface, physical and electrical requirements, and scoring |
| [case.toml](case.toml) | Single case configuration, input digests, toolchain, constraints, and evaluation plan |
| [materials/circuit.spice](materials/circuit.spice) | Authoritative LVS and pre-layout simulator netlist |
| [materials/testbench.spice](materials/testbench.spice) | Stimuli, loads, transient analysis, and measurements |
| [Collection LICENSE](../../LICENSE), [NOTICE](../../NOTICE) | Collection distribution terms; excluded from solver inputs |
| [reference/AOI21_X1.gds](reference/AOI21_X1.gds) | Passing feasibility witness, excluded from standard solver inputs |

## Reference Results

Conditions: **1.0 V, 27 C, nominal FreePDK45 BSIM4**; use the problem's loads and
stimuli. Tool scope: KLayout 0.30.11, Magic 8.3.678 and ngspice 42 from the shared
Dockerfile. The witness has zero reported DRC violations with all implemented
checks enabled, no waivers, strict named-port LVS and explicit body connections.
The reference GDS DBU is **0.0001 um**.
Its RC network also matches the source transistor graph after removing capacitors
and shorting parasitic resistors. Simulation consumes the original RC network,
including extracted junction geometry; this explains differences from the source
netlist, which omits layout junction areas and wire parasitics.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `functional_area` | um2 | N/A | 2.0049 |
| `state_0` | V | 0.999952 | 0.9999511 |
| `state_1` | V | 0.9998967 | 0.9998954 |
| `state_2` | V | 0.0001918556 | 0.0001955403 |
| `state_3` | V | 0.9994024 | 0.9993944 |
| `state_4` | V | 0.0004865273 | 0.0005187056 |
| `state_5` | V | 1.239731e-06 | 1.242926e-06 |
| `state_6` | V | 8.142936e-05 | 8.542029e-05 |
| `state_7` | V | -3.673975e-05 | -3.792539e-05 |
| `state_8` | V | 0.9998379 | 0.9998351 |
| `state_9` | V | 0.0004804343 | 0.0005106174 |
| `state_10` | V | 0.0003069374 | 0.0003168796 |
| `state_11` | V | 1.216504e-06 | 1.23889e-06 |
| `state_12` | V | 7.794863e-05 | 8.130596e-05 |
| `state_13` | V | 0.99935 | 0.9993347 |
| `state_14` | V | 0.0001950317 | 0.0001987454 |
| `state_15` | V | 0.9998362 | 0.9998289 |
| `state_16` | V | 0.9997699 | 0.9997679 |
| `supply` | W | 4.305193e-06 | 4.297991e-06 |

All electrical requirements pass. Reference score: **100/100**.
The absolute area target is **2.1 um2**, a rounded feasible
compact envelope witnessed by this **2.0049 um2** layout. The fixed zero-utility
anchor is **4.2 um2**, allowing additional functional routing
before area utility vanishes. These anchors are frozen absolute requirements;
the evaluator never divides by a reference layout area.

Electrical thresholds express rail-valid logic or read margin at fixed deadlines
and a nominal supply budget. Zero boundaries distinguish an indeterminate logic
level (0.5 V), absent bitline differential (0 V), or excessive power (five times
the accepted budget). The response and supply dimensions each use their worst observation.

The reference regression evaluates the supplied GDS against the case's public
acceptance conditions and verifies that an empty candidate is rejected. It does
not prescribe a reference score or construct circuit-specific geometry variants.
Scope excludes PVT, mismatch, array abutment and substrate-noise qualification;
the open DRC deck and predictive RC fit are not foundry signoff.

## Reproduce

Prepare the image and resources using the
[tools guide](../../../../../docs/tools.md#freepdk45). From the repository root,
choose a fresh output directory:

```bash
python -m layout_eval.cli evaluate \
  tasks/freepdk45/nangate45-pdk/cases/AOI21_X1/case.toml \
  tasks/freepdk45/nangate45-pdk/cases/AOI21_X1/reference/AOI21_X1.gds \
  --output build/runs/freepdk45-AOI21_X1-reference-evaluation
uv run --locked --group eda pytest tests/integration/test_public_references.py \
  -k AOI21_X1
```

The evaluation command generates `report.json`, native reports, extracted netlists
and simulation evidence under the selected run directory. The regression creates
fresh temporary directories and prepares resources from the case's PDK profiles.
It uses the same catalog-driven workflow for every process and circuit.

To reproduce the Pre-layout column, use the shared
[source-calibration recipe](../../../../../docs/tools.md#gf180-source-calibration)
with `tasks/freepdk45/nangate45-pdk/cases/AOI21_X1/case.toml` and a fresh output directory such as
`build/runs/freepdk45-AOI21_X1-source-calibration`. The recipe selects this
case's authoritative SPICE netlist, retains every simulation condition and
measurement, and produces an unscored characterization report. Compare its
measurements with the Pre-layout column above; the GDS evaluation produces the
Post-layout column.

The distributed reference GDS is ready to use. Input consistency and actual
reference acceptance support this case's qualified status. Shared evaluator
regressions cover common rejection and scoring behavior; new extraction or
judging capabilities require targeted validation under the
[task guide](../../../../../docs/tasks.md#qualification).

## Source and License

Source: [AOI21_X1 at the pinned publication](https://foss-eda-tools.googlesource.com/third_party/freepdk45/+/356e90646f5ef26ea09b1ed8ce4796871403a0c7).
The upstream location is recorded in `case.toml` as `origin.url`.
The [collection license](../../LICENSE) and [notices](../../NOTICE) accompany
the maintained inputs and derived reference.
PDK models and rule/extraction resources retain their separate notices in the
reviewed support bundles; no Calibre SVRF deck is distributed by these profiles.
