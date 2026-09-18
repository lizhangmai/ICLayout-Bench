> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Five-Transistor OTA Core with Bias Mirror

## Overview

This maintained IHP SG13G2 OTA uses an NMOS differential pair, PMOS mirror load,
NMOS tail device and diode-connected NMOS bias reference. The five-transistor
core therefore has six MOS instances in its complete interface. The fixed
upstream IHP dimensions are retained; explicit well/substrate taps and a fresh
physical layout complete the maintained circuit. The native CDL and simulator
netlists describe the same device connectivity and geometry.

The qualification scope is nominal AC/DC at 1.5 V, 20 uA reference current,
0.8 V input common mode and 10 pF external output load, TT, 27 C. Matching means
fixed electrical dimensions here; no statistical mismatch or physical centroid
constraint is claimed. Noise, distortion, transient settling, PVT and EM are
outside the declared scope.

## Files

| File | Role |
| --- | --- |
| [problem.md](problem.md) | Complete solver-facing requirements and scoring |
| [case.toml](case.toml) | Inputs, physical checks, RC/simulation plan and frozen scoring and functional checks |
| [materials/circuit.cdl](materials/circuit.cdl) | Authoritative native LVS circuit with taps |
| [materials/circuit.spice](materials/circuit.spice) | Same circuit as ngspice model calls, for the source baseline |
| [materials/testbench.spice](materials/testbench.spice) | Shared source/post-layout AC/DC testbench |
| [reference/amp_001_5t.gds](reference/amp_001_5t.gds) | Independently constructed witness; not a solver input |

[Analog Canvas schematic](materials/schematic.svg) is a maintainer-only result
browsing asset, excluded from solver inputs. Same-name labels denote connected
nets; repeated-device banks retain individual instances in editable child sheets.
SVG metadata binds the source digest and records authoring/verification limitations.
The authoritative netlist, simulation decks and evaluation requirements are unchanged.

## Reference Results

Reference results use the pinned IHP SG13G2 ciel release described in
[resource preparation](../../../../../docs/tools.md#ihp-physical-check-profiles).

The declared reference passes artifact, DRC, LVS, hard geometry, candidate-derived
extraction and the functional checks in the current case plan. Conditions, model
boundaries, measurement windows and normalization rules are specified in
[problem.md](problem.md). Both simulation paths use the same declared testbenches
and trusted resources. The source circuit supplies the electrical baseline;
the reference GDS demonstrates an executable layout, not an optimal solution.

Measured `layout-v2` score: **57.088550**, with electrical quality
**E = 0.99948801** and area quality **Q = 0.32607721**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **3675.0499 um2**.

Area reference: **1198.35 um2**. 8 expanded device instances; sum of device/contact envelopes 754.0020 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `low_frequency_gain` | dB | 33.11524 | 33.10943 | 0.99933132 |
| `unity_gain_bandwidth` | Hz | 1211382 | 1206185 | 0.99570986 |
| `phase_margin` | deg | 83.80139 | 83.71266 | 0.9995073 |
| `output_bias` | V | 0.79870636 | 0.79867355 | 0.99997813 |
| `bias_voltage` | V | 0.4146612 | 0.41529479 | 0.99957779 |
| `supply_power` | W | 5.9289935e-05 | 5.9259936e-05 | 1.0005062 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

The coefficient is 4 for a complete compact
amplifier with bias and load matching.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case ihp-sg13g2.analog-db.amp_001_5t --image iclayout-bench-tools:local \
  --output build/runs/amp_001_5t-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/amp_001_5t-prepared \
  --output build/runs/amp_001_5t-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'amp_001_5t'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [MacAnalog analog-db amp_001_5t](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_001_5t), with the applicable [collection license](../../LICENSE) and [notices](../../NOTICE).
