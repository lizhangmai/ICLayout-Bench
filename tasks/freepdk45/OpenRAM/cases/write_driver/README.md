# Complementary SRAM Write Driver

## Overview

Nominal, predictive **qualified** layout task with a distributed passing witness.
The [problem](problem.md) defines the complete circuit, stimuli, limits and score.
Coefficient **2** covers a compact loaded complementary tri-state driver.
The enable label is renamed from en to wen to match the circuit interface.

## Files

| File | Purpose |
| --- | --- |
| [problem.md](problem.md) | Solver objective, interface, physical and electrical requirements, and scoring |
| [case.toml](case.toml) | Single case configuration, input digests, toolchain, constraints, and evaluation plan |
| [materials/circuit.spice](materials/circuit.spice) | Authoritative LVS and pre-layout simulator netlist |
| [materials/testbench.spice](materials/testbench.spice) | Stimuli, loads, transient analysis, and measurements |
| [Collection LICENSE](../../LICENSE), [NOTICE](../../NOTICE) | Shared source declarations; copied to `materials/` when inputs are materialized |
| [reference/write_driver.gds](reference/write_driver.gds) | Passing feasibility witness, excluded from standard solver inputs |

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
| `functional_area` | um2 | N/A | 3.507 |
| `bl_low` | V | 0.0150365 | 0.0153004 |
| `br_high` | V | 0.9886259 | 0.9884149 |
| `bl_high` | V | 0.9860666 | 0.9838029 |
| `br_low` | V | 0.02670905 | 0.03296745 |
| `z_bl` | V | 0.5015592 | 0.5015322 |
| `z_br` | V | 0.502349 | 0.5024897 |
| `supply` | W | 2.174283e-05 | 2.310158e-05 |

All electrical requirements pass. Reference score: **100/100**.
The absolute area target is **3.6 um2**, a rounded feasible
compact envelope witnessed by this **3.507 um2** layout. The fixed zero-utility
anchor is **7.2 um2**, allowing additional functional routing
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
uv run --locked python main.py evaluate \
  tasks/freepdk45/OpenRAM/cases/write_driver/case.toml \
  tasks/freepdk45/OpenRAM/cases/write_driver/reference/write_driver.gds \
  --output build/runs/freepdk45-write_driver-reference-evaluation
uv run --locked --group eda pytest tests/integration/test_public_references.py \
  -k write_driver
```

The evaluation command generates `report.json`, native reports, extracted netlists
and simulation evidence under the selected run directory. The regression creates
fresh temporary directories and prepares resources from the case's PDK profiles.
It uses the same catalog-driven workflow for every process and circuit.

The distributed reference GDS is ready to use. Input consistency and actual
reference acceptance support this case's qualified status. Shared evaluator
regressions cover common rejection and scoring behavior; new extraction or
judging capabilities require targeted validation under the
[task guide](../../../../../docs/tasks.md#qualification).

## Source and License

Source: [write_driver at the pinned publication](https://github.com/ferdous313/OpenRAM/tree/420a33e731d7d80bf9c7cd54ffbeec3603259847).
The upstream location is recorded in `case.toml` as `origin.url`.
The [collection license](../../LICENSE) and [notices](../../NOTICE) accompany
the maintained inputs and derived reference.
PDK models and rule/extraction resources retain their separate notices in the
reviewed support bundles; no Calibre SVRF deck is distributed by these profiles.
