> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Six-Transistor SRAM Bitcell

## Overview

Nominal, predictive **qualified** layout task with a distributed passing witness.
The [problem](problem.md) defines the complete circuit, stimuli, limits and score.
Coefficient **6** covers a dynamic storage cell with write, hold and nondestructive read behavior.
The distributed reference preserves the original transistor and routing geometry.

## Files

| File | Purpose |
| --- | --- |
| [problem.md](problem.md) | Solver objective, interface, physical and electrical requirements, and scoring |
| [case.toml](case.toml) | Single case configuration, input digests, toolchain, constraints, and evaluation plan |
| [materials/circuit.spice](materials/circuit.spice) | Authoritative LVS and pre-layout simulator netlist |
| [materials/testbench.spice](materials/testbench.spice) | Stimuli, loads, transient analysis, and measurements |
| [Collection LICENSE](../../LICENSE), [NOTICE](../../NOTICE) | Collection distribution terms; excluded from solver inputs |
| [reference/cell_6t.gds](reference/cell_6t.gds) | Passing feasibility witness, excluded from standard solver inputs |

## Reference Results

Conditions: **1.0 V, 27 C, nominal FreePDK45 BSIM4**; use the problem's loads and
stimuli. Tool scope: KLayout 0.30.11, Magic 8.3.678 and ngspice 42 from the shared
Dockerfile. The witness has zero reported DRC violations with all implemented
checks enabled, no waivers, strict named-port LVS and explicit body connections.
The reference GDS DBU is **0.0005 um**.
Its RC network also matches the source transistor graph after removing capacitors
and shorting parasitic resistors. Simulation consumes the original RC network,
including extracted junction geometry; this explains differences from the source
netlist, which omits layout junction areas and wire parasitics.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `functional_area` | um2 | N/A | 1.367325 |
| `read0` | V | 0.7858571 | 0.7604749 |
| `repeat0` | V | 0.7858571 | 0.7604749 |
| `read1` | V | 0.7858571 | 0.763205 |
| `repeat1` | V | 0.7858571 | 0.763205 |
| `supply` | W | 5.942012e-06 | 6.173096e-06 |

All electrical requirements pass. Reference score: **100/100**.
The absolute area target is **1.4 um2**, a rounded feasible
compact envelope witnessed by this **1.367325 um2** layout. The fixed zero-utility
anchor is **2.8 um2**, allowing additional functional routing
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
  tasks/freepdk45/OpenRAM/cases/cell_6t/case.toml \
  tasks/freepdk45/OpenRAM/cases/cell_6t/reference/cell_6t.gds \
  --output build/runs/freepdk45-cell_6t-reference-evaluation
uv run --locked --group eda pytest tests/integration/test_public_references.py \
  -k cell_6t
```

The evaluation command generates `report.json`, native reports, extracted netlists
and simulation evidence under the selected run directory. The regression creates
fresh temporary directories and prepares resources from the case's PDK profiles.
It uses the same catalog-driven workflow for every process and circuit.

To reproduce the Pre-layout column, use the shared
[source-calibration recipe](../../../../../docs/tools.md#gf180-source-calibration)
with `tasks/freepdk45/OpenRAM/cases/cell_6t/case.toml` and a fresh output directory such as
`build/runs/freepdk45-cell_6t-source-calibration`. The recipe selects this
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

Source: [cell_6t at the pinned publication](https://github.com/ferdous313/OpenRAM/tree/420a33e731d7d80bf9c7cd54ffbeec3603259847).
The upstream location is recorded in `case.toml` as `origin.url`.
The [collection license](../../LICENSE) and [notices](../../NOTICE) accompany
the maintained inputs and derived reference.
PDK models and rule/extraction resources retain their separate notices in the
reviewed support bundles; no Calibre SVRF deck is distributed by these profiles.
