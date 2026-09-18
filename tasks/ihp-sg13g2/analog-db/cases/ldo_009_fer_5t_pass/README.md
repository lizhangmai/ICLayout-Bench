> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Unity-Feedback Regulator with Internal Output Storage

## Overview

A five-transistor NMOS-input error amplifier drives a PMOS pass array;
an on-chip diode-connected NMOS biases the tail mirror. The maintained circuit
retains all seven source MOS groups (29 physical fingers), the output bleeder,
reference-series resistor, Miller path and internal output capacitor. Unity
feedback senses output directly; there is no feedback divider. This adds
physical output storage, a reference impedance, explicit return ratio and
zero-state startup to the existing externally loaded regulator coverage.

The original 2 pF Miller compensation is deliberately retuned to five physical
36.515 um square units, nominally 10.0293 pF. Thirteen 50.635 um square MIM
units retain the approximately 50 pF internal COUT. Four physical high-poly
segments implement the approximately 100 kohm bleeder and one implements
approximately 10 kohm reference resistance. MOS dimensions and multiplicities
are unchanged; explicit substrate/well taps are added. The 20 uA bias source
and 0.9 V reference are external. The raw zero-volt loop measurement source
becomes an external zero-volt link between distinct output and sense ports;
it is not a manufactured voltage-source device or an ideal common-mode servo.

The contract covers typical models at 27 C, 1.2/1.3 V supplies, a 0.9 V
external reference, 0.1–1 mA load regulation, specified current-load steps,
downward supply-headroom sweeps and resistive-load startup. It is not capless:
all output storage remains inside the DUT. Qualification does not imply
arbitrary startup/load conditions, PVT or a precision voltage reference.

## Files

- [Problem](problem.md): complete interface and qualification contract.
- [Configuration](case.toml): frozen inputs, measurements, score and witness.
- [Native circuit](materials/circuit.cdl) and [simulation circuit](materials/circuit.spice): matching physical devices.
- [Main testbench](materials/testbench.spice): bias, return ratio and current-load steps.
- [Startup deck](materials/startup.spice): separate zero-state resistive-load analysis.
- [DC sweeps](materials/sweeps.spice): separate line/load and regulation-floor analysis.
- [Reference](reference/ldo_009_fer_5t_pass.gds): independently constructed physical witness.

The problem and five material files are solver inputs. Collection license and
notices accompany distributions separately; generators, upstream DSL, original
proprietary-process decks and maintainer waveforms are not solver inputs.

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

Measured `layout-v2` score: **37.231470**, with electrical quality
**E = 0.97908762** and area quality **Q = 0.14157899**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **462427.9992 um2**.

Area reference: **65470.09 um2**. 54 expanded device instances; sum of device/contact envelopes 43312.7759 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `output_v` | V | 0.90712498 … 0.92280421 | 0.90692161 … 0.92309995 | 0.99977256 |
| `bias_v` | V | 0.38675793 … 0.38675793 | 0.38718865 … 0.38718883 | 0.99966865 |
| `quiescent_a` | A | 7.3029499e-05 … 7.3352527e-05 | 7.3003989e-05 … 7.3330398e-05 | 1.0002516 |
| `power_w` | W | 0.00020795224 … 0.00074507825 | 0.00020793012 … 0.00074504489 | 1.0000445 |
| `dc_gain_db` | dB | 45.45435 … 53.67274 | 43.65761 … 53.53236 | 0.81313565 |
| `unity_hz` | Hz | 3238258 … 5728183 | 3063653 … 5472154 | 0.94608058 |
| `phase_margin_deg` | deg | 49.457 … 76.5545 | 48.1891 … 74.7216 | 0.98543527 |
| `minimum_v` | V | 0.8620178 … 0.8979894 | 0.8394636 … 0.8940477 | 0.98262336 |
| `maximum_v` | V | 0.933738 … 0.9533911 | 0.9374569 … 0.9790293 | 0.98065973 |
| `recovery_load_v` | V | 0.002161652 … 0.01893865 | 0.001723333 … 0.01913796 | 0.98958616 |
| `recovery_release_v` | V | 0.007124978 … 0.02280421 | 0.00692161 … 0.02309995 | 0.98719793 |
| `mean_power_w` | W | 0.0002680455 … 0.001070795 | 0.0002680227 … 0.001070757 | 1.0000355 |
| `startup_error_v` | V | 0.002141717 … 0.02267805 | 0.001706337 … 0.02296926 | 0.9873223 |
| `startup_peak_v` | V | 0.90309 … 0.9893929 | 0.902639 … 1.003684 | 0.98912638 |
| `startup_minimum_v` | V | 6.799612e-09 … 7.365177e-08 | 1.801741e-07 … 1.977834e-06 | 0.99999854 |
| `regulation_floor_v` | V | 1.029643 … 1.184926 | 1.085568 … 1.185902 | 0.95875509 |
| `headroom_v` | V | 0.129643 … 0.284926 | 0.185568 … 0.285902 | 0.69862962 |
| `line_span_v` | V | 0.0020169 … 0.0083393 | 0.0012052 … 0.0086993 | 0.95862212 |
| `load_span_v` | V | 0.0122965 … 0.018626 | 0.01267 … 0.0202015 | 0.9220146 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

Capability coefficient: **8** for the fixed circuit and its declared functional scope.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case ihp-sg13g2.analog-db.ldo_009_fer_5t_pass --image iclayout-bench-tools:local \
  --output build/runs/ldo_009_fer_5t_pass-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/ldo_009_fer_5t_pass-prepared \
  --output build/runs/ldo_009_fer_5t_pass-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'ldo_009_fer_5t_pass'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [analog-db ldo_009_fer_5t_pass at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/ldo_009_fer_5t_pass),
with normalized PolyForm Noncommercial terms and the snapshot's Token Zhang /
Arcadia-1 ferrosim MIT attribution retained in [LICENSE](../../LICENSE) and
[NOTICE](../../NOTICE); the original ferrosim notice was not independently
retrieved. The independently authored measurement decks are MIT.
