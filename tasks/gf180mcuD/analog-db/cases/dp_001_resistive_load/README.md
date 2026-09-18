> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Resistively Loaded Differential Pair

## Overview

Four NMOS devices form a differential input pair and tail-current mirror. Two physical GF180 ppolyf_u_1k loads each have width 2 um and length 44 um (22 squares, nominally 22 kohm). MOS dimensions and the resistor ratio follow the fixed binding; the ideal source resistors become process devices with substrate terminals at VSS.

VDD = 3.3 V, VSS = 0 V; 20 uA from VDD into ibias; input common mode = 1.2, 1.65 and 2.1 V; external 1 pF on each output. The input differential signal is split +0.5/-0.5 around common mode. AC differential amplitude is 1 V. DC transfer sweeps differential input from -10.1 to +10.1 mV in 0.1 mV increments; requirements use only -10 to +10 mV. Output differential voltage is V(voutn)-V(voutp). The output has a high common-mode level; it is not a rail-to-rail amplifier. Transient settling, mismatch, noise, PVT and EM are outside scope.

## Files

| File | Role |
| --- | --- |
| [problem.md](problem.md) | Complete solver-facing contract and scoring |
| [case.toml](case.toml) | Inputs, physical checks, RC extraction and three simulation conditions |
| [materials/circuit.spice](materials/circuit.spice) | Authoritative fixed circuit and source-calibration DUT |
| [materials/testbench.spice](materials/testbench.spice) | Shared source/post-layout measurement deck |
| [reference/dp_001_resistive_load.gds](reference/dp_001_resistive_load.gds) | Independently constructed witness, excluded from solver inputs |

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

Measured `layout-v2` score: **29.265342**, with electrical quality
**E = 0.55651093** and area quality **Q = 0.15389819**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **6016.8349 um2**.

Area reference: **925.98 um2**. 6 expanded device instances; sum of device/contact envelopes 552.0000 um2, per-side envelope allowance 1 um, 50% routing allowance and outer margin 2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `output_v` | V | 2.9949753 … 3.0889733 | 2.9955456 … 3.088604 | 0.99982722 |
| `imbalance_v` | V | 5.5067062e-14 … 6.3504757e-14 | 0.00011469878 … 0.00018881118 | 0.0052683938 |
| `bias_v` | V | 0.63335378 … 0.63335378 | 0.63414916 … 0.634217 | 0.99973849 |
| `power_w` | W | 0.00012824943 … 0.00015597732 | 0.00012819087 … 0.00015556785 | 1.0004568 |
| `gain_db` | dB | 10.89406 … 12.94184 | 10.87388 … 12.89242 | 0.99432647 |
| `bandwidth_hz` | Hz | 7805460 … 8235992 | 7578496 … 7990159 | 0.97015138 |
| `linearity_v` | V | 1.820086e-05 … 2.070048e-05 | 1.816947e-05 … 2.063697e-05 | 1.0016375 |
| `slope` | V/V | 3.499673 … 4.432213 | 3.491637 … 4.407119 | 0.99500626 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

The coefficient is 4 for a biased differential block with physical matched loads.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case gf180mcuD.analog-db.dp_001_resistive_load --image iclayout-bench-tools:local \
  --output build/runs/dp_001_resistive_load-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/dp_001_resistive_load-prepared \
  --output build/runs/dp_001_resistive_load-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'dp_001_resistive_load'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [MacAnalog analog-db dp_001_resistive_load](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/dp_001_resistive_load), under the retained [collection license](../../LICENSE) and [notices](../../NOTICE).
