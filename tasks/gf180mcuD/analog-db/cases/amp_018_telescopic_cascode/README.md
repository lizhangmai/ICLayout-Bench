> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Tail-Referenced Telescopic Cascode Amplifier

## Overview

Ten MOS devices form an NMOS-input telescopic cascode amplifier. Fixed upstream W/L/m are retained, including the single finger of XM5. The two ideal internal sources become external bias connections: VDD minus gate_pc is 1.143 V, and casc_n minus tail is 0.917 V. Exposing tail preserves the second source's relative bias instead of replacing it with an absolute ground-referenced voltage.

VDD = 3.3 V; VSS = 0 V; a 20 uA current source from VDD into ibias. VINP is 1.65 V DC with AC amplitude +0.5 V; VINN has DC output feedback through a 1 TH inductor and AC -0.5 V through a 1 F coupling capacitor. These ideal measurement elements are external apparatus. Output loads are 1, 3 and 5 pF. AC uses 100 points/decade from 1 Hz to 1 GHz and transfer V(vout)/(V(vinp)-V(vinn)).  The declared bias gives about 15 dB gain; this is not a high-gain OTA qualification. Large-signal settling, noise, mismatch, other biases and PVT are outside scope.

## Files

| File | Role |
| --- | --- |
| [problem.md](problem.md) | Solver contract and scoring |
| [case.toml](case.toml) | Inputs, tool bindings, constraints and evaluation |
| [materials/circuit.spice](materials/circuit.spice) | Authoritative physical circuit |
| [materials/testbench.spice](materials/testbench.spice) | Source/post-layout measurements |
| [reference/amp_018_telescopic_cascode.gds](reference/amp_018_telescopic_cascode.gds) | Independently constructed witness, excluded from solver inputs |

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

Measured `layout-v2` score: **22.899794**, with electrical quality
**E = 0.99263832** and area quality **Q = 0.052828969**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **10300.22 um2**.

Area reference: **544.15 um2**. 10 expanded device instances; sum of device/contact envelopes 312.9250 um2, per-side envelope allowance 1 um, 50% routing allowance and outer margin 2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `output_v` | V | 1.7459291 | 1.745376 | 0.99983244 |
| `bias_v` | V | 0.79373017 | 0.79463617 | 0.99972553 |
| `tail_v` | V | 0.57707779 | 0.57501006 | 0.99937381 |
| `power_w` | W | 0.00010464449 | 0.00010477608 | 0.99874409 |
| `gain_db` | dB | 15.53969 | 15.39755 | 0.9837687 |
| `unity_hz` | Hz | 101230.5 … 503431.9 | 98648.64 … 481537.5 | 0.95650971 |
| `phase_margin` | deg | 99.22954 … 99.5422 | 99.34665 … 99.69217 | 0.99916753 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

Capability coefficient: **5** for the fixed circuit and its declared functional scope.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case gf180mcuD.analog-db.amp_018_telescopic_cascode --image iclayout-bench-tools:local \
  --output build/runs/amp_018_telescopic_cascode-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/amp_018_telescopic_cascode-prepared \
  --output build/runs/amp_018_telescopic_cascode-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'amp_018_telescopic_cascode'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [MacAnalog analog-db amp_018_telescopic_cascode](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_018_telescopic_cascode), under the retained [collection license](../../LICENSE) and [notices](../../NOTICE).
