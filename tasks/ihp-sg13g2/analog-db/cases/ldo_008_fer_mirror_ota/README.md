> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Mirror-OTA Regulator with Bilateral Return-Ratio Measurements

## Overview

A seven-group mirror-OTA/PMOS-pass regulator retains 81 physical MOS fingers,
40 MIM units and three high-poly resistors. Its 160 pF series compensation and
9/9 kohm feedback divider remain inside the DUT. There is no separate COUT.
The reference is explicitly adjusted from source 0.6 V to 0.5 V for a nominal
1.0 V output; 20 uA supply-fed bias and all source MOS dimensions are retained.

The independent physical witness reuses the verified MOS/MIM/poly/RC path.
The loop measurement uses voltage and current injections at the divider/input
boundary. It preserves port loading and both transmission directions; a raw
voltage ratio at this boundary can falsely cross unity at high frequency.
Qualification includes complete return-difference screens, final crossover,
line/load/headroom, specified startup and fast/large load recovery.

## Files

- [Problem](problem.md): complete circuit and acceptance contract.
- [Configuration](case.toml): frozen inputs, score and witness.
- [Native circuit](materials/circuit.cdl) and [simulator circuit](materials/circuit.spice): matching physical devices.
- [Main deck](materials/testbench.spice): two-injection return ratio and load recovery.
- [Startup](materials/startup.spice), [DC sweeps](materials/sweeps.spice) and [fast response](materials/fast.spice): distinct initialization/time-scale requirements.
- [Reference GDS](reference/ldo_008_fer_mirror_ota.gds): independent physical witness.

Only the problem and six material files are solver inputs. Collection license
and notices accompany distributions separately; source generators and maintainer
waveforms are excluded.

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

Measured `layout-v2` score: **38.261630**, with electrical quality
**E = 0.8502697** and area quality **Q = 0.17217506**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **1003099.879 um2**.

Area reference: **172708.78 um2**. 126 expanded device instances; sum of device/contact envelopes 114596.5905 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `output_v` | V | 1.0015974 … 1.0083595 | 1.000258 … 1.0078599 | 0.99897076 |
| `bias_v` | V | 0.32649287 … 0.32649287 | 0.32708076 … 0.32708145 | 0.99954745 |
| `quiescent_a` | A | 0.0001452354 … 0.00014602215 | 0.00014419116 … 0.00014504558 | 1.0067329 |
| `power_w` | W | 0.00029496076 … 0.00083918181 | 0.00029378411 … 0.00083788316 | 1.0015499 |
| `dc_gain_db` | dB | 44.61466 … 49.0275 | 33.87283 … 48.66397 | 0.29034109 |
| `unity_hz` | Hz | 407773.7 … 458663.1 | 502705.2 … 1247716 | 1.1629154 |
| `phase_margin_deg` | deg | 125.87255 … 131.73902 | 145.61324 … 163.45996 | 0.85017571 |
| `final_unity_hz` | Hz | 407773.7 … 458663.1 | 502705.2 … 76389370 | 1.1629154 |
| `final_phase_margin_deg` | deg | 125.87255 … 131.73902 | 75.9188 … 151.31822 | 0.76329333 |
| `minimum_return_distance` | 1 | 0.81196218 … 0.85138389 | 0.50189633 … 0.70625793 | 0.74491361 |
| `return_phase_excursion_deg` | deg | 78.81361 … 81.410076 | 68.48608 … 80.429118 | 1.0121965 |
| `hf_gain_db` | dB | -7.633848 … -6.412583 | -27.2402 … -18.28299 | 3.9221152 |
| `minimum_v` | V | 0.9742929 … 0.9934197 | 0.9386478 … 0.9871642 | 0.97331245 |
| `maximum_v` | V | 1.020852 … 1.025424 | 1.026383 … 1.067796 | 0.96837655 |
| `recovery_load_v` | V | 0.002639145 … 0.005987694 | 0.005166435 … 0.02089693 | 0.16703473 |
| `recovery_release_v` | V | 0.002086921 … 0.008601531 | 0.002874733 … 0.008467022 | 0.46837098 |
| `mean_power_w` | W | 0.0003549922 … 0.001164775 | 0.0003538111 … 0.001163427 | 1.0011586 |
| `startup_error_v` | V | 0.00217294 … 0.008335321 | 0.004001213 … 0.01461069 | 0.20377198 |
| `startup_peak_v` | V | 0.9970235 … 1.018812 | 0.9853964 … 1.017846 | 0.98969733 |
| `startup_minimum_v` | V | 2.09718e-06 … 2.438187e-05 | 2.756605e-07 … 3.005093e-06 | 0.99998356 |
| `regulation_floor_v` | V | 0.9730788 … 0.9917698 | 0.9996434 … 1.171609 | 0.87847382 |
| `headroom_v` | V | 0.0030788 … 0.0217698 | 0.0296434 … 0.201609 | 0.10389146 |
| `line_span_v` | V | 0.000541 … 0.0008117 | 0.000512 … 0.0115839 | 0.070151663 |
| `load_span_v` | V | 0.0100067 … 0.0113595 | 0.0113922 … 0.0234888 | 0.48363545 |
| `fast_peak_v` | V | 0.0002317423 … 0.0004908346 | 0.0001864905 … 0.0002222358 | 0.99979343 |
| `fast_tail_v` | V | 6.278331e-08 … 1.788685e-07 | 9.042197e-08 … 2.454506e-07 | 0.99999995 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

Capability coefficient: **9** for the fixed circuit and its declared functional scope.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case ihp-sg13g2.analog-db.ldo_008_fer_mirror_ota --image iclayout-bench-tools:local \
  --output build/runs/ldo_008_fer_mirror_ota-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/ldo_008_fer_mirror_ota-prepared \
  --output build/runs/ldo_008_fer_mirror_ota-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'ldo_008_fer_mirror_ota'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [the fixed analog-db snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/ldo_008_fer_mirror_ota).
Normalized derivatives and witness retain PolyForm Noncommercial terms and
the Required Notice; the snapshot records Token Zhang / Arcadia-1 ferrosim MIT
attribution. Its original notice was not independently retrieved. See collection
[LICENSE](../../LICENSE) and [NOTICE](../../NOTICE). Independently authored
measurement decks are MIT.

The two-injection expression follows Eq. (30) of [Tian et al., 2001](https://kenkundert.com/docs/cd2001-01.pdf).
Its sign convention here uses `if = −I(VPROBE)` and `ve = V(SENSE)`.
