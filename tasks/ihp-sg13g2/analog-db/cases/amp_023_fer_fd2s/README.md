> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Fully Differential Two-Stage OTA with Common-Mode Feedback

## Overview

A folded first stage drives two common-source output stages with physical
series R/C compensation and transistor common-mode feedback. All 28 source
MOS groups retain their W/L/m and connections, expanded into 50 physical MOS.
The original internal ideal sources become explicit `ibias` and `vcmr` ports:
a 20 uA source supplies IBIAS from VDD, and VCMR receives the output common-mode
reference. Mirrors and the common-mode controller remain inside the circuit.

Each compensation path uses a nominal 1.52 kohm high-poly resistor and two
parallel 25.85 × 25.85 um MIM units totaling 2.01294 pF. Each output-sensing
arm uses eight nominal 25.66 kohm poly segments in series, in parallel with
one 9.95 × 9.95 um MIM capacitor (150.096 fF). These implement all original
1.5 kohm / 2 pF compensation and 200 kohm / 150 fF sensing branches; no
functional passive is removed. Explicit well/substrate contacts complete the
physical circuit.

Qualification covers 1.2 V, 27 C, typical models, 0.5 V input common mode and
1/5/10 pF per output. Each load has positive and negative differential steps
paired with positive and negative common-mode current disturbances. External
feedback fixes input common mode and closes only the differential signal loop;
the actual transistor controller regulates output common mode. The measurements
include differential return ratio, common-mode reference transfer and peaking,
sustained recovery after both types of steps, cross-coupled errors, and recovery
from equal output-current kicks. Common-mode transfer is a closed-loop response,
not an internal common-mode loop phase-margin measurement.

Noise, distortion, PVT, mismatch, rail-to-rail operation, startup from zero
supply, arbitrary loads and fabrication signoff are outside this qualification.
The increased common-mode peaking after extraction is a material limitation.

## Files

- [Problem](problem.md): complete solver contract, measurement windows and scoring.
- [Configuration](case.toml): frozen inputs, tool bindings and reference identity.
- [Native circuit](materials/circuit.cdl) and [simulation circuit](materials/circuit.spice):
  equivalent physical device definitions for the two native readers.
- [Testbench](materials/testbench.spice): bias, differential/common-mode AC and transient measurements.
- [Reference layout](reference/amp_023_fer_fd2s.gds): independently constructed physical witness.

Only the problem and three materials files enter solver inputs. Collection
LICENSE and NOTICE accompany distributions separately. Source layouts,
generators, DSL and upstream scoring are not runtime dependencies.

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

Measured `layout-v2` score: **28.043547**, with electrical quality
**E = 0.83670545** and area quality **Q = 0.093992521**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **89741.183 um2**.

Area reference: **8435.0 um2**. 76 expanded device instances; sum of device/contact envelopes 5503.6687 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `output_cm_v` | V | 0.75369086 | 0.75406541 | 0.99968798 |
| `output_dm_v` | V | -1.6064927e-13 | 0.00013771618 | 0.99988525 |
| `bias_v` | V | 0.38675792 | 0.39633581 | 0.99208162 |
| `power_w` | W | 0.00057200809 | 0.00056557461 | 1.0113751 |
| `dm_gain_db` | dB | 61.6623 | 61.86768 | 1.023927 |
| `unity_hz` | Hz | 20703970 … 24605670 | 20435060 … 25278250 | 0.98701167 |
| `phase_margin_deg` | deg | 72.8372 … 101.69952 | 71.1612 … 101.82275 | 0.99077479 |
| `cm_gain_vv` | V/V | 1.064286 | 1.060767 | 0.99649334 |
| `cm_peak_vv` | V/V | 1.083292 … 1.125353 | 1.487001 … 1.657028 | 0.65288002 |
| `dm_up_error_v` | V | 8.268386e-05 | 5.686509e-05 … 0.0002183798 | 0.38145654 |
| `dm_down_error_v` | V | 2.311484e-13 … 7.364109e-13 | 0.0001377162 | 0.007208965 |
| `cm_up_error_v` | V | 0.008070969 | 0.008104683 … 0.008105639 | 0.99572326 |
| `cm_down_error_v` | V | 0.003946135 … 0.004627371 | 0.004340498 … 0.005177779 | 0.88638549 |
| `cm_kick_error_v` | V | 0.003690862 … 0.003690863 | 0.004065405 | 0.90789334 |
| `cm_kick_peak_v` | V | 0.02614724 … 0.04855971 | 0.03333467 … 0.06652192 | 0.98244334 |
| `dm_peak_v` | V | 0.1000001 … 0.1020541 | 0.09991322 … 0.1030632 | 0.99915979 |
| `mean_power_w` | W | 0.0005715061 … 0.0005715175 | 0.0005650758 … 0.0005651148 | 1.0113299 |
| `dm_cm_error_v` | V | 8.399948e-05 | 5.366051e-05 … 0.0002177629 | 0.38854614 |
| `cm_dm_error_v` | V | 0.003690737 | 0.004064678 … 0.004065431 | 0.90785679 |
| `dm_high_v` | V | -0.09991732 … 0.09991732 | -0.09978162 … 0.1000569 | diagnostic |
| `cm_high_v` | V | 0.808071 | 0.8081047 … 0.8081056 | diagnostic |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

Coefficient 9 reflects coupled
differential and common-mode compensation and recovery.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case ihp-sg13g2.analog-db.amp_023_fer_fd2s --image iclayout-bench-tools:local \
  --output build/runs/amp_023_fer_fd2s-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/amp_023_fer_fd2s-prepared \
  --output build/runs/amp_023_fer_fd2s-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'amp_023_fer_fd2s'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [analog-db amp_023_fer_fd2s at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_023_fer_fd2s).
Normalized materials and their derivative witness retain PolyForm Noncommercial
terms; the fixed snapshot records Token Zhang / Arcadia-1 ferrosim and MIT
component attribution. This is not independent verification of the original
ferrosim repository or its original copyright notice. The collection
[LICENSE](../../LICENSE) and [NOTICE](../../NOTICE) retain those terms and the
database Required Notice. The independently authored measurement deck is MIT.
