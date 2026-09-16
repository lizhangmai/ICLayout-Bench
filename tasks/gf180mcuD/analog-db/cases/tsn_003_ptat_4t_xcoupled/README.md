> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Four-Transistor Positive-Temperature-Slope Core

## Overview

Two NMOS and two PMOS devices form a resistorless temperature-dependent voltage core with cross-coupled bias connections. The fixed GF180 sizes are retained. The output increases with temperature under each declared supply, but both voltage and slope depend strongly on supply. This is a temperature-slope layout task, not a precision reference or calibrated thermometer.

VSS = 0 V; VDD = 2.7, 3.0 and 3.3 V. Measure the operating point at 27 C, then sweep temperature from -20 to 100 C inclusive in 1 C steps at each supply. The output is unloaded except for the measurement probe. No ideal internal source or passive is added. The temperature sweep is a nominal model sweep, not process-corner or statistical qualification. Startup, output drive, absolute temperature accuracy, supply rejection, mismatch, noise and EM are outside scope.

## Files

| File | Role |
| --- | --- |
| [problem.md](problem.md) | Complete solver-facing contract and scoring |
| [case.toml](case.toml) | Inputs, physical checks, RC extraction and three simulation conditions |
| [materials/circuit.spice](materials/circuit.spice) | Authoritative fixed circuit and source-calibration DUT |
| [materials/testbench.spice](materials/testbench.spice) | Shared source/post-layout measurement deck |
| [reference/tsn_003_ptat_4t_xcoupled.gds](reference/tsn_003_ptat_4t_xcoupled.gds) | Independently constructed witness, excluded from solver inputs |

## Reference Results

The reference functional area is 1428.0000 um2. It passes artifact, GF180 variant-D DRC including antenna without
waivers, strict named-port LVS, geometry, distributed RC extraction and all
27 required electrical observations. The table gives ranges over all three
declared conditions; temperature extrema and comparator transient windows are
defined in the problem. Both columns use the same maintained testbench.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `output_v` | V | 0.12459976 to 0.16642669 | 0.1251919 to 0.16739006 |
| `power_w` | W | 0.00012637395 to 0.00025085206 | 0.0001262096 to 0.00025045312 |
| `cold_v` | V | 0.112257 to 0.1503868 | 0.112938 to 0.1515017 |
| `hot_v` | V | 0.1437512 to 0.1911575 | 0.1442479 to 0.191957 |
| `slope_v_per_c` | V/C | 0.00026245167 to 0.00033975583 | 0.00026091583 to 0.0003371275 |
| `curvature_v` | V | 9.307522e-06 to 7.209692e-05 | 1.362163e-05 to 4.369973e-05 |
| `minimum_slope` | V/C | 0.0002622107 to 0.0003378454 | 0.0002606222 to 0.0003360066 |
| `maximum_slope` | V/C | 0.0002631716 to 0.0003428504 | 0.0002616022 to 0.0003390712 |
| `peak_power_w` | W | 0.0001446342 to 0.0002884296 | 0.000144416 to 0.0002879014 |

The targets require a positive 0.24–0.36 mV/C slope, at most 0.2 mV endpoint-line error and 320 uW peak power under each specified supply. Supply dependence is explicit; the bands do not establish an absolute thermometer calibration. The coefficient is 3 for a complete coupled bias block whose output and power must remain controlled over temperature. Acceptance and zero-score bands are calibrated against these nominal
source/RC measurements, rather than inherited from upstream targets. The
absolute area budget is 1500 um2, verified feasible by this witness; area utility
reaches zero at 6000 um2. These frozen budgets do not depend on a submitted
layout, a changing reference-area ratio or model population. The witness is
not an area optimum. Physical area and the final evaluation score are reported
by the reproduction command below.

The extracted RC network and device geometry come from the reference GDS.
Finite substrate resistance, process/statistical corners and fabrication
signoff are outside this nominal physical/simulation boundary.

## Reproduce

From the repository root, prepare the image and shared verified bundles using
the [GF180 instructions](../../../../../docs/tools.md#gf180), then run:

```bash
python -m layout_eval.cli evaluate \
  tasks/gf180mcuD/analog-db/cases/tsn_003_ptat_4t_xcoupled/case.toml \
  tasks/gf180mcuD/analog-db/cases/tsn_003_ptat_4t_xcoupled/reference/tsn_003_ptat_4t_xcoupled.gds \
  --output build/runs/analog-db-tsn_003_ptat_4t_xcoupled-reference
```

This generates the reader's identity-bound report and raw waveforms in the
selected output directory; use a fresh directory for every execution. Reproduce
the Pre-layout column using the shared
[source-calibration recipe](../../../../../docs/tools.md#gf180-source-calibration),
with this case path and a fresh `build/runs/analog-db-tsn_003_ptat_4t_xcoupled-source` destination.
That recipe keeps all three conditions and replaces only the extracted DUT
with the published source netlist; characterization is not a layout score.

```bash
uv run --locked --group eda pytest tests/integration/test_public_references.py \
  -k tsn_003_ptat_4t_xcoupled
```

The catalog-driven checks evaluate the witness and reject an empty layout.
Retain collection LICENSE and NOTICE with distributions; they are outside the
three declared solver inputs. Prepared solves are not redistribution packages.

## Source and License

Derived from [MacAnalog analog-db tsn_003_ptat_4t_xcoupled](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/tsn_003_ptat_4t_xcoupled), under the retained [collection license](../../LICENSE) and [notices](../../NOTICE).
