> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Current-Buffer and Active-Feedforward OTA

## Overview

The folded PMOS-input stage drives `net050`; a PMOS common-source stage
drives `net013`, then a PMOS stage and NMOS mirror at `net043` drive the
output NMOS. An active feedforward path drives the output PMOS directly
from `net050`. One capacitor connects output to `net063`, the source side
of the first-stage NMOS cascode; the second connects `net050` to `net013`.
The current-buffer compensation terminal and the additional active path
are real connection differences from the dual-capacitor and shared-resistor
representatives. This case is not counted from a changed circuit name or size.

The maintained circuit retains all 24 source MOS groups as 89 physical
fingers, 4 MIM units and 0 high-poly segments. MOS W/L are rounded to the nearest 0.01 um process grid. The original W=18/20/30 um devices use 2×9/2×10/3×10 um parallel fingers; the resulting short-width model behavior is calibrated independently.
The source's 14.3293 uA sink is external through `net1`. Physical
substrate and separate N-well contacts retain the input PMOS bodies at their
common source `net31`, electrically separate from the VDD well. No internal
ideal bias source or output servo is introduced. Capacitor values are rounded
to physical geometry; every branch remains internal to the DUT.

Qualification covers 1.2 V, 27 C, 5/10/20 pF loads, return ratio around
0.5 V unity feedback and 0.5↔0.7 V step recovery. See the
[problem](problem.md) for all bounds and limitations.

## Files

- [Problem](problem.md): complete solver contract.
- [Configuration](case.toml): inputs, limits, score, backend bindings and witness.
- [Native circuit](materials/circuit.cdl) and [simulation circuit](materials/circuit.spice): matching device graphs.
- [Testbench](materials/testbench.spice): source/RC measurement deck.
- [Reference layout](reference/amp_002_alfio_raffc.gds): independently constructed witness.

Only the problem and three materials files enter solver inputs; collection
licenses/notices accompany distributions separately. No upstream generator,
layout, DSL, tuning history or scoreboard is needed.

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

Measured `layout-v2` score: **34.504961**, with electrical quality
**E = 0.89036629** and area quality **Q = 0.13371939**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **154727.0795 um2**.

Area reference: **20690.01 um2**. 96 expanded device instances; sum of device/contact envelopes 13605.7469 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `output_v` | V | 0.49954682 | 0.50059202 | 0.99912976 |
| `bias_v` | V | 0.23269814 | 0.23217761 | 0.99956641 |
| `power_w` | W | 0.0004119832 | 0.00041444618 | 0.99405718 |
| `dc_gain_db` | dB | 93.72582 | 82.33763 | 0.26951969 |
| `unity_hz` | Hz | 1884332 … 1910778 | 1881988 … 1916285 | 0.99875606 |
| `phase_margin_deg` | deg | 73.7404 … 79.3754 | 74.3891 … 80.16008 | 0.99565959 |
| `recovery_up_v` | V | 0.0004710615 … 0.0004710616 | 0.00147994 | 0.31875802 |
| `recovery_down_v` | V | 0.0004531763 | 0.0005920233 … 0.0005920234 | 0.76586573 |
| `step_gain` | V/V | 0.9999105 | 1.0044395 | 0.99549142 |
| `mean_power_w` | W | 0.0004069606 … 0.0004069685 | 0.0004094145 … 0.000409421 | 0.99400632 |
| `peak_v` | V | 0.6995289 | 0.7014799 | 0.99837681 |
| `trough_v` | V | 0.4994566 … 0.4995032 | 0.5005453 … 0.500567 | 0.99909357 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

Coefficient
7 reflects coupled multistage compensation, loaded loop response and recovery.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case ihp-sg13g2.analog-db.amp_002_alfio_raffc --image iclayout-bench-tools:local \
  --output build/runs/amp_002_alfio_raffc-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/amp_002_alfio_raffc-prepared \
  --output build/runs/amp_002_alfio_raffc-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'amp_002_alfio_raffc'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [analog-db amp_002_alfio_raffc at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_002_alfio_raffc),
with PolyForm Noncommercial normalized-material terms and recorded CODA-Team
AnalogGym BSD-3-Clause component terms in the collection [LICENSE](../../LICENSE)
and [NOTICE](../../NOTICE); the independently authored measurement deck is MIT.
