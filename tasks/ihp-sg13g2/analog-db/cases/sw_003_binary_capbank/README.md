> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Three-Bit MIM Capacitive Transfer Bank

## Overview

Twelve minimum-size MOS (W/L = 0.15/0.13 um) select the bottom plates of a 1:1:2:4 MIM capacitor bank between vinp and VCM. Eight identical 25.85 by 25.85 um cap_cmim units implement those weights, each nominally about 1.00647 pF. Explicit physical substrate and well taps are included. For code k, the ideal capacitive transfer is (1+k)/8. Qualification covers all eight static codes and bipolar input steps at each fixed code; live code transitions, ADC conversion, charge redistribution after a code change and mismatch linearity are outside scope.

Typical IHP low-voltage MOS, typical resistor and capacitor models at 27 C; VDD = 1.5 V and VSS = 0 V. Each node has the declared 1e12 ohm numerical shunt. Transient integration uses Gear order 2 with a 1 ns output and maximum step. Physical taps have finite source-model resistance; Magic treats well/substrate ties ideally. Distributed silicon substrate resistance, statistical mismatch, PVT, noise and RF/EM are outside scope.

All eight binary codes are separate required conditions. Bit k is driven by 1.5*bk V and its complement by 1.5*(1-bk) V; controls remain static. VCM = 0.75 V. VINP has DC 0.65 V and unit AC amplitude. AC uses 50 points/decade from 1 kHz to 100 MHz; acceptance measurements are at 10 kHz. VINP stays at 0.65 V through 10 us, rises to 0.85 V at 10.002 us, holds through 30 us, returns to 0.65 V at 30.002 us and holds through 50 us. Vout has an external 1e12 ohm return to ground, in addition to the numerical shunt; no ideal external holding capacitor is added. Absolute output DC is not a retained sample requirement: measurements compare increments. The testbench expected-value voltage source is measurement apparatus only.

## Files

| File | Role |
| --- | --- |
| [problem.md](problem.md) | Complete solver contract and scoring |
| [case.toml](case.toml) | Frozen inputs, tool bindings, constraints and evaluation |
| [materials/circuit.cdl](materials/circuit.cdl) | Authoritative physical netlist |
| [materials/circuit.spice](materials/circuit.spice) | Equivalent simulator representation |
| [materials/testbench.spice](materials/testbench.spice) | Shared source/post-layout measurements |
| [reference/sw_003_binary_capbank.gds](reference/sw_003_binary_capbank.gds) | Independent witness, excluded from solver inputs |

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

Measured `layout-v2` score: **12.673425**, with electrical quality
**E = 0.052232868** and area quality **Q = 0.30749928**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **31000.9828 um2**.

Area reference: **9532.78 um2**. 22 expanded device instances; sum of device/contact envelopes 6227.9559 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `gain_vv` | V/V | 0.1250002 … 0.9999999 | 0.1238089 … 0.9887987 | 0.98892288 |
| `phase_deg` | deg | -0.008812904 … 0.09038728 | -0.009028963 … 0.09203339 | 0.99999086 |
| `input_cap_f` | F | 3.108802e-15 … 2.015276e-12 | 2.333301e-13 … 2.144532e-12 | 0.013323626 |
| `gain_error` | V/V | 1e-07 … 8e-07 | 0.0011911 … 0.0112013 | 9.0168097e-06 |
| `step_gain` | V/V | 0.12499705 … 0.99997649 | 0.12380144 … 0.98874124 | 0.98888957 |
| `step_error` | V/V | 2.9500987e-06 … 2.3505869e-05 | 0.001198561 … 0.01125876 | 0.0020878067 |
| `return_error_v` | V | 6.2005303e-07 … 4.9593158e-06 | 1.5188666e-06 … 1.2128095e-05 | 0.45393607 |
| `settling_error_v` | V | 2.784394e-07 … 2.201358e-06 | 6.818172e-07 … 5.433537e-06 | 0.49760466 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

Coefficient 5 reflects multi-bit switched capacitors and interconnect-dependent capacitive division.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case ihp-sg13g2.analog-db.sw_003_binary_capbank --image iclayout-bench-tools:local \
  --output build/runs/sw_003_binary_capbank-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/sw_003_binary_capbank-prepared \
  --output build/runs/sw_003_binary_capbank-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'sw_003_binary_capbank'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [analog-db `sw_003_binary_capbank` at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/sw_003_binary_capbank), under the retained [collection license](../../LICENSE) and [notices](../../NOTICE); independently authored testbench under MIT.
