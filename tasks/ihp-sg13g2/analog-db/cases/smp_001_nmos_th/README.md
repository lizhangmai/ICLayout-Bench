> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Physical NMOS Sample-and-Hold: Headroom and Retention

## Overview

A single W=2 um / L=0.13 um NMOS samples onto one physical 18.2 × 18.2 um
MIM capacitor, nominally 499.772 fF. The maintained circuit retains the source
switch and all storage connectivity, adds an explicit substrate tap and removes
the raw VDD port because it has no electrical connection. The ordered interface
is `vin clk vout vss`; clock drive is external. No output buffer, dummy
compensation, complementary switch, ideal hold capacitor or hold-node servo is
added. The independently routed reference includes the actual MIM plates.

Qualification covers sampled levels 0.1/0.4/0.6/0.7 V at TT, 27/85 C,
1.2 V clock amplitude with 2 ns edges and 1 kohm source resistance. At each
point the input is driven to 0 or 1.2 V while the switch is off: sixteen
conditions. The contract measures sustained acquisition, turn-off pedestal,
isolated-input feedthrough, quiet 10 us hold drift, total stored-value error
and reacquisition. This adds physical storage and input/temperature-dependent
retention to the existing dummy-compensated track-switch case.

These sample points do not establish rail-to-rail operation or an exact maximum
input voltage. Higher inputs and longer holds expose substantial errors in the
published diagnostic recipe. This is model-based retention for a specified
sequence, not precision ADC resolution or measured-silicon leakage validation.
Noise, jitter, distortion, process corners, mismatch and arbitrary clock/source
conditions remain outside qualification. The MIM model's presence does not
validate capacitor dielectric leakage or distributed substrate noise.

## Files

- [Problem](problem.md): complete circuit, sequence, measurement and scoring contract.
- [Configuration](case.toml): frozen inputs, tool bindings and witness identity.
- [Native circuit](materials/circuit.cdl) and [simulation circuit](materials/circuit.spice): equivalent physical-device definitions for the native readers.
- [Testbench](materials/testbench.spice): finite acquisition/hold/reacquisition with off-state input disturbances.
- [Reference layout](reference/smp_001_nmos_th.gds): independently constructed NMOS, MIM, tap and complete routing.

Only the problem and three materials files enter solver inputs. Collection
LICENSE and NOTICE remain with material distributions separately. Source
layouts, generators, DSL and upstream scoring are not runtime dependencies.

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

Measured `layout-v2` score: **36.252609**, with electrical quality
**E = 0.25555805** and area quality **Q = 0.51426736**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **1286.082 um2**.

Area reference: **661.39 um2**. 3 expanded device instances; sum of device/contact envelopes 407.6560 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `track_error_v` | V | 2.690636e-09 … 0.001026075 | 2.713111e-09 … 0.00113599 | 0.6776137 |
| `pedestal_abs_v` | V | 0.0028763 … 0.00376907 | 0.0067678 … 0.00750121 | 0.42493207 |
| `feedthrough_peak_v` | V | 8.031927e-08 … 5.496746e-05 | 4.369319e-05 … 0.0004745488 | 0.0026878863 |
| `hold_drift_v` | V | 1.2e-06 … 0.0115981 | 1.1e-06 … 0.0112294 | 0.92785635 |
| `hold_error_v` | V | 0.002883985 … 0.01517136 | 0.006769885 … 0.01896994 | 0.42608684 |
| `reacquire_error_v` | V | 1.176898e-09 … 4.669633e-06 | 1.200634e-09 … 5.395384e-06 | 0.82169009 |
| `clock_energy_j` | J | 1.86907e-15 … 2.57894e-15 | 7.18974e-15 … 7.90125e-15 | 0.25996361 |
| `target` | V | 0.1 … 0.7 | 0.1 … 0.7 | diagnostic |
| `track_v` | V | 0.1 … 0.7 | 0.1 … 0.7 | diagnostic |
| `held_v` | V | 0.09623093 … 0.6971237 | 0.09249879 … 0.6932302 | diagnostic |
| `before_input_v` | V | 0.09623096 … 0.6971235 | 0.09249884 … 0.6932301 | diagnostic |
| `after_input_v` | V | 0.09622947 … 0.6971235 | 0.09245509 … 0.6934418 | diagnostic |
| `hold_start_v` | V | 0.09601923 … 0.6971229 | 0.09228863 … 0.6934415 | diagnostic |
| `hold_end_v` | V | 0.09163936 … 0.697116 | 0.08809035 … 0.693436 | diagnostic |
| `reacquired_v` | V | 0.1 … 0.7 | 0.1 … 0.7 | diagnostic |
| `pedestal_v` | V | -0.00376907 … -0.0028763 | -0.00750121 … -0.0067678 | diagnostic |
| `feedthrough_v` | V | -5.63e-05 … 5.86e-06 | -0.0003508 … 0.00047174 | diagnostic |
| `drift_v` | V | -0.0115981 … 0.00116347 | -0.0112294 … 0.00123567 | diagnostic |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

Coefficient 5 reflects a complete compact loaded block operating through
acquisition, storage and reacquisition, independently of device count.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case ihp-sg13g2.analog-db.smp_001_nmos_th --image iclayout-bench-tools:local \
  --output build/runs/smp_001_nmos_th-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/smp_001_nmos_th-prepared \
  --output build/runs/smp_001_nmos_th-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'smp_001_nmos_th'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [analog-db smp_001_nmos_th at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/smp_001_nmos_th).
The fixed manifest identifies the sampler as a SpiceXplorer worked example,
records `analog-circuit-design` provenance and an Apache-2.0 component label.
Normalized derivatives and the independent witness retain PolyForm
Noncommercial terms and the database Required Notice. Collection
[LICENSE](../../LICENSE) and [NOTICE](../../NOTICE) preserve the applicable
terms; the normalized circuit is not relicensed under framework MIT.
The independently authored measurement deck is MIT.
