> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Auxiliary-Branch Compensation OTA

## Overview

The folded PMOS-input stage drives `net050`; a PMOS/diode/mirror stage
drives `net049`, followed by the NMOS output stage. The output PMOS also
receives feedforward drive from `net050`. C0 connects `net050` to output,
while C1 connects `net049` to `net1`. The auxiliary node has a bias-fed PMOS,
a diode-connected PMOS and an NMOS controlled by `net043`; this three-device
branch creates a distinct active compensation termination. It is neither a
second output-connected Miller capacitor nor the six-MOS current-buffer
branch of the other representative.

The maintained circuit retains all 27 source MOS groups as 237 physical
fingers, 6 MIM units and 0 high-poly segments. MOS W/L are rounded to the nearest 0.01 um process grid. All source multiplicities are retained.
The maintained 1.80825 uA sink is external through `net013`.
The external bias is deliberately calibrated to 0.1 times the source current; this is not an unchanged upstream operating point. Physical
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
- [Reference layout](reference/amp_010_peng_acbc.gds): independently constructed witness.

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

Measured `layout-v2` score: **36.526719**, with electrical quality
**E = 1.024973** and area quality **Q = 0.13016941**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **252948.4545 um2**.

Area reference: **32926.15 um2**. 246 expanded device instances; sum of device/contact envelopes 21714.0299 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `output_v` | V | 0.49902625 | 0.49928499 | 0.99978443 |
| `bias_v` | V | 0.81169171 | 0.81150661 | 0.99984577 |
| `power_w` | W | 4.4557631e-05 | 4.4632727e-05 | 0.99831747 |
| `dc_gain_db` | dB | 90.95124 | 90.99614 | 1.0051827 |
| `unity_hz` | Hz | 240024.7 … 244699.6 | 237848 … 242598.5 | 0.99093135 |
| `phase_margin_deg` | deg | 87.03286 … 88.03197 | 86.41132 … 87.44605 | 0.99655888 |
| `recovery_up_v` | V | 0.0009865102 … 0.0009865104 | 0.0007260225 | 1.3582939 |
| `recovery_down_v` | V | 0.0009737532 … 0.0009737533 | 0.0007150125 … 0.0007150126 | 1.3613632 |
| `step_gain` | V/V | 0.9999365 | 0.999945 | 0.9999915 |
| `mean_power_w` | W | 4.446528e-05 … 4.44657e-05 | 4.453962e-05 … 4.454004e-05 | 0.99833092 |
| `peak_v` | V | 0.6990135 | 0.699274 | 0.99978296 |
| `trough_v` | V | 0.4990262 | 0.499285 | 0.99978438 |

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
  --case ihp-sg13g2.analog-db.amp_010_peng_acbc --image iclayout-bench-tools:local \
  --output build/runs/amp_010_peng_acbc-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/amp_010_peng_acbc-prepared \
  --output build/runs/amp_010_peng_acbc-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'amp_010_peng_acbc'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [analog-db amp_010_peng_acbc at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_010_peng_acbc),
with PolyForm Noncommercial normalized-material terms and recorded CODA-Team
AnalogGym BSD-3-Clause component terms in the collection [LICENSE](../../LICENSE)
and [NOTICE](../../NOTICE); the independently authored measurement deck is MIT.
