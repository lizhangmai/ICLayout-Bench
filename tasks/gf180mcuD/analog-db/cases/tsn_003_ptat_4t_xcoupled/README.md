> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

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

[Analog Canvas schematic](materials/schematic.svg) is a maintainer-only result
browsing asset, excluded from solver inputs. Same-name labels denote connected
nets; repeated-device banks retain individual instances in editable child sheets.
SVG metadata binds the source digest and records authoring/verification limitations.
The schematic depicts the authoritative netlist; the current layout requirements
and evaluation settings are declared in the task.

## Reference Results

GF180 resources come from the pinned ciel prebuilt distribution, including its
current KLayout rules, nominal models and variant-D Magic extraction.
The reference uses a 0.001 um GDS database unit; dummy COMP fill is included
where required by the rule deck.
See [resource preparation](../../../../../docs/tools.md) and the process manifest
for source pins, scope and reproducible preparation.

The declared reference passes artifact, DRC, LVS, hard geometry, candidate-derived
extraction and the functional checks in the current case plan. Conditions, model
boundaries, measurement windows and normalization rules are specified in
[problem.md](problem.md). Both simulation paths use the same declared testbenches
and trusted resources. The source circuit supplies the electrical baseline;
the reference GDS demonstrates an executable layout, not an optimal solution.

Measured `layout-v2` score: **33.812431**, with electrical quality
**E = 0.96959529** and area quality **Q = 0.11791317**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **1428 um2**.

Area reference: **168.38 um2**. 4 expanded device instances; sum of device/contact envelopes 85.0000 um2, per-side envelope allowance 1 um, 50% routing allowance and outer margin 2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `output_v` | V | 0.12459976 … 0.16642669 | 0.1251919 … 0.16739006 | 0.99970815 |
| `power_w` | W | 0.00012637395 … 0.00025085206 | 0.0001262096 … 0.00025045312 | 1.0013022 |
| `cold_v` | V | 0.112257 … 0.1503868 | 0.112938 … 0.1515017 | 0.99966227 |
| `hot_v` | V | 0.1437512 … 0.1911575 | 0.1442479 … 0.191957 | 0.99975779 |
| `slope_v_per_c` | V/C | 0.00026245167 … 0.00033975583 | 0.00026091583 … 0.0003371275 | 0.99275199 |
| `curvature_v` | V | 9.307522e-06 … 7.209692e-05 | 1.362163e-05 … 4.369973e-05 | 0.70495027 |
| `minimum_slope` | V/C | 0.0002622107 … 0.0003378454 | 0.0002606222 … 0.0003360066 | 0.99239659 |
| `maximum_slope` | V/C | 0.0002631716 … 0.0003428504 | 0.0002616022 … 0.0003390712 | 0.98961128 |
| `peak_power_w` | W | 0.0001446342 … 0.0002884296 | 0.000144416 … 0.0002879014 | 1.0015109 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

The coefficient is 3 for a complete coupled bias block whose output and power must remain controlled over temperature.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case gf180mcuD.analog-db.tsn_003_ptat_4t_xcoupled --image iclayout-bench-tools:local \
  --output build/runs/tsn_003_ptat_4t_xcoupled-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/tsn_003_ptat_4t_xcoupled-prepared \
  --output build/runs/tsn_003_ptat_4t_xcoupled-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'tsn_003_ptat_4t_xcoupled'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [MacAnalog analog-db tsn_003_ptat_4t_xcoupled](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/tsn_003_ptat_4t_xcoupled), under the retained [collection license](../../LICENSE) and [notices](../../NOTICE).
