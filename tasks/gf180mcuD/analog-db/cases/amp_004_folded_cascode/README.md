> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Externally Biased PMOS-Input Folded-Cascode OTA

## Overview

Fourteen MOS entries (17 instances after multiplicity expansion) form a PMOS-input folded-cascode OTA with a bias mirror and cascode branches. The two ideal internal voltage sources become explicit vb1/vb2 ports. Total MOS widths, lengths and multiplicities are retained; the maintained devices use single-finger geometry instead of the upstream nf settings. Source and extracted simulation both represent this maintained implementation.

VSS = 0 V; VDD = 2.7, 3.0 and 3.3 V; a 20 uA sink from ibias to VSS; VB1 = 1.2 V and VB2 = 1.95 V; external 1 pF output load. VINP has DC 1.65 V and AC +0.5 V. A 1 TH output-to-VINN inductor closes DC feedback; a 1 F coupling capacitor injects AC -0.5 V at VINN. The open-loop transfer is V(vout)/(V(vinp)-V(vinn)). These large L/C elements are external measurement apparatus. At 2.7 V the reduced headroom lowers gain and shifts the DC operating point. The case measures small-signal unity-crossing phase margin with the declared load. Startup, large-signal settling, other loads, mismatch, noise, PVT and EM are outside scope.

## Files

| File | Role |
| --- | --- |
| [problem.md](problem.md) | Complete solver-facing contract and scoring |
| [case.toml](case.toml) | Inputs, physical checks, RC extraction and three simulation conditions |
| [materials/circuit.spice](materials/circuit.spice) | Authoritative fixed circuit and source-calibration DUT |
| [materials/testbench.spice](materials/testbench.spice) | Shared source/post-layout measurement deck |
| [reference/amp_004_folded_cascode.gds](reference/amp_004_folded_cascode.gds) | Independently constructed witness, excluded from solver inputs |

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

Measured `layout-v2` score: **39.343536**, with electrical quality
**E = 0.97728287** and area quality **Q = 0.15838954**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **32514.9 um2**.

Area reference: **5150.02 um2**. 17 expanded device instances; sum of device/contact envelopes 3278.0000 um2, per-side envelope allowance 1 um, 50% routing allowance and outer margin 2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `output_v` | V | 1.5926553 … 1.6500528 | 1.5929005 … 1.6504603 | 0.99987279 |
| `bias_v` | V | 1.8491195 … 2.4491195 | 1.8480297 … 2.4479529 | 0.99964662 |
| `power_w` | W | 0.00019254782 … 0.00026806229 | 0.00019214633 … 0.00026750611 | 1.0020525 |
| `gain_db` | dB | 45.95764 … 85.67452 | 46.29032 … 85.80164 | 1.0137783 |
| `bandwidth_hz` | Hz | 1516.815 … 55221.54 | 1350.2 … 47972.97 | 0.86873655 |
| `unity_hz` | Hz | 11028510 … 26921560 | 9948813 … 23986110 | 0.88991513 |
| `phase_margin` | deg | 64.479 … 88.43546 | 57.3635 … 86.13907 | 0.96143369 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

The coefficient is 5 for independently supplied cascode bias networks coupled through internal parasitics.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case gf180mcuD.analog-db.amp_004_folded_cascode --image iclayout-bench-tools:local \
  --output build/runs/amp_004_folded_cascode-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/amp_004_folded_cascode-prepared \
  --output build/runs/amp_004_folded_cascode-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'amp_004_folded_cascode'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [MacAnalog analog-db amp_004_folded_cascode](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_004_folded_cascode), under the retained [collection license](../../LICENSE) and [notices](../../NOTICE).
