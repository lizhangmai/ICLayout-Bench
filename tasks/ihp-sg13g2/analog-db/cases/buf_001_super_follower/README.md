> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# MIM-Compensated Local-Feedback Source Follower

## Overview

Six MOS entries expand to 17 physical MOS instances in a local-feedback source follower. Fixed IHP W/L/m are retained. The internal na-to-VSS 250 fF compensation is implemented as a 12.85 by 12.85 um cap_cmim (nominally 249.74 fF at 27 C, including model perimeter capacitance); it is not removed or moved to the output. Explicit physical taps and the MIM dimensions are common to LVS, source simulation and extracted simulation.

VDD = 1.5 V; VSS = 0 V; a 20 uA current source from VDD into ibias. VIN = 0.55 V DC, AC amplitude 1 V. External output loads are 5, 10 and 20 pF. AC uses 100 points/decade from 1 Hz to 1 GHz. VIN stays at 0.55 V through 1 us, ramps to 0.65 V at 1.001 us, holds through 3 us, ramps back at 3.001 us and holds through 5 us. Transient output/max step is 0.2 ns. Recovered errors compare output to its 2.5 us and 0.5 us samples, over 1.5–2.9 us and 3.5–4.9 us respectively. This is a level-shifting source follower with about 0.84 small-signal gain, not a unity-gain rail-to-rail buffer. Qualification is restricted to the stated low-input range; higher input bias compresses the gain. Noise, mismatch, other input levels, PVT and RF/EM are outside scope.

## Files

| File | Role |
| --- | --- |
| [problem.md](problem.md) | Solver contract and scoring |
| [case.toml](case.toml) | Inputs, tool bindings, constraints and evaluation |
| [materials/circuit.cdl](materials/circuit.cdl) | Authoritative physical circuit |
| [materials/circuit.spice](materials/circuit.spice) | Equivalent simulator representation |
| [materials/testbench.spice](materials/testbench.spice) | Source/post-layout measurements |
| [reference/buf_001_super_follower.gds](reference/buf_001_super_follower.gds) | Independently constructed witness, excluded from solver inputs |

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

Measured `layout-v2` score: **50.212422**, with electrical quality
**E = 0.99982388** and area quality **Q = 0.25217315**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **4928.677 um2**.

Area reference: **1242.88 um2**. 20 expanded device instances; sum of device/contact envelopes 782.8540 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `output_v` | V | 0.13800078 | 0.1373654 | 0.99957659 |
| `bias_v` | V | 0.39406997 | 0.39915676 | 0.99662027 |
| `power_w` | W | 0.00034650957 | 0.00033967943 | 1.0201076 |
| `gain_vv` | V/V | 0.8375134 | 0.8370302 | 0.99951703 |
| `bandwidth_hz` | Hz | 1.986676e+08 … 4.328583e+08 | 1.737159e+08 … 3.822466e+08 | 0.87440478 |
| `step_gain` | V/V | 0.833601 | 0.833981 | 0.99962014 |
| `recovery_up_v` | V | 3.65123e-08 … 3.651418e-08 | 6.128534e-09 … 6.129687e-09 | 1.0301982 |
| `recovery_down_v` | V | 1.619487e-08 … 1.62009e-08 | 3.378466e-09 … 3.379001e-09 | 1.0127733 |
| `mean_power_w` | W | 0.0003466058 … 0.0003466118 | 0.0003397777 … 0.0003397826 | 1.0200958 |

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
  --case ihp-sg13g2.analog-db.buf_001_super_follower --image iclayout-bench-tools:local \
  --output build/runs/buf_001_super_follower-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/buf_001_super_follower-prepared \
  --output build/runs/buf_001_super_follower-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'buf_001_super_follower'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [MacAnalog analog-db buf_001_super_follower](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/buf_001_super_follower), under the retained [collection license](../../LICENSE) and [notices](../../NOTICE).
