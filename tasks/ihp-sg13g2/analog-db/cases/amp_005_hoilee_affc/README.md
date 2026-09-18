> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Current-Buffered Compensation OTA

## Overview

The folded PMOS-input stage drives `net050`; a PMOS/diode/mirror stage
drives `net049`, followed by the NMOS output stage. A parallel path drives
the output PMOS directly from `net050`. One capacitor connects `net049` to
output. The other connects output to `net1`, the source terminal of an
additional common-gate NMOS returning current to `net050`. Six additional
MOS (XM59–XM64) form this biased current-buffer branch; these devices and
the low-impedance compensation terminal distinguish it from direct Miller
and shared-resistor compensation.

The maintained circuit retains all 30 source MOS groups as 276 physical
fingers, 7 MIM units and 0 high-poly segments. MOS W/L are rounded to the nearest 0.01 um process grid. All source multiplicities are retained.
The maintained 3.15498 uA sink is external through `net013`.
The external bias is deliberately calibrated to 0.3 times the source current; this is not an unchanged upstream operating point. Physical
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
- [Reference layout](reference/amp_005_hoilee_affc.gds): independently constructed witness.

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

Measured `layout-v2` score: **31.429388**, with electrical quality
**E = 0.95656953** and area quality **Q = 0.10326551**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **407361.6524 um2**.

Area reference: **42066.41 um2**. 286 expanded device instances; sum of device/contact envelopes 27776.6506 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `output_v` | V | 0.50042683 | 0.50081656 | 0.99967533 |
| `bias_v` | V | 0.62230999 | 0.62180958 | 0.99958317 |
| `power_w` | W | 6.6881242e-05 | 6.7130626e-05 | 0.9962851 |
| `dc_gain_db` | dB | 110.1142 | 112.7191 | 1.3497241 |
| `unity_hz` | Hz | 1469052 … 1565806 | 1444115 … 1577847 | 0.98302511 |
| `phase_margin_deg` | deg | 111.14645 … 113.17744 | 105.12373 … 108.54054 | 0.96762374 |
| `recovery_up_v` | V | 0.0004901745 … 0.000490238 | 0.0009075803 … 0.0009080797 | 0.54036846 |
| `recovery_down_v` | V | 0.0004268312 … 0.0004271043 | 0.0008165578 … 0.0008167475 | 0.52330392 |
| `step_gain` | V/V | 1.000317 | 1.000455 | 0.99986202 |
| `mean_power_w` | W | 6.678601e-05 … 6.686937e-05 | 6.702041e-05 … 6.711366e-05 | 0.99636006 |
| `peak_v` | V | 0.7674106 … 0.8123348 | 0.7472856 … 0.7902726 | 0.98067819 |
| `trough_v` | V | 0.5004251 … 0.5004268 | 0.5008078 … 0.5008166 | 0.99967527 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

Coefficient
8 reflects coupled multistage compensation, loaded loop response and recovery.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case ihp-sg13g2.analog-db.amp_005_hoilee_affc --image iclayout-bench-tools:local \
  --output build/runs/amp_005_hoilee_affc-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/amp_005_hoilee_affc-prepared \
  --output build/runs/amp_005_hoilee_affc-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'amp_005_hoilee_affc'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [analog-db amp_005_hoilee_affc at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_005_hoilee_affc),
with PolyForm Noncommercial normalized-material terms and recorded CODA-Team
AnalogGym BSD-3-Clause component terms in the collection [LICENSE](../../LICENSE)
and [NOTICE](../../NOTICE); the independently authored measurement deck is MIT.
