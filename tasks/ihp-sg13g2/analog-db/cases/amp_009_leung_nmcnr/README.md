> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Shared-Nulling-Resistor Three-Stage OTA

## Overview

The folded PMOS-input stage drives `net050`; the PMOS stage at `net043`
and its NMOS mirror drive `net049`, which controls the NMOS output device.
The output PMOS gate connects to the bias mirror, not to `net050`.
Two capacitors connect `net050` and `net049` to a common `net044` node;
a physical high-poly resistor connects that junction to output. The shared
resistance and bias-controlled output PMOS distinguish this circuit from
both the dual-capacitor feedforward OTA and the two-stage series-R/C OTA.

The maintained circuit retains all 24 source MOS groups as 272 physical
fingers, 3 MIM units and 1 high-poly segments. All MOS dimensions/multiplicities are retained exactly.
The source's 3 uA sink is external through `net013`. Physical
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
- [Reference layout](reference/amp_009_leung_nmcnr.gds): independently constructed witness.

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

Measured `layout-v2` score: **17.143556**, with electrical quality
**E = 0.99930958** and area quality **Q = 0.029410457**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **617432.4315 um2**.

Area reference: **18158.97 um2**. 279 expanded device instances; sum of device/contact envelopes 11930.2526 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `output_v` | V | 0.49966042 | 0.50017676 | 0.9995699 |
| `bias_v` | V | 0.73769917 | 0.73722016 | 0.99960098 |
| `power_w` | W | 7.5986653e-05 | 7.6261598e-05 | 0.99639471 |
| `dc_gain_db` | dB | 91.90065 | 92.57493 | 1.080722 |
| `unity_hz` | Hz | 1236878 … 1433315 | 1306310 … 1620232 | 1.0561349 |
| `phase_margin_deg` | deg | 82.00337 … 90.51311 | 66.998 … 84.14817 | 0.9230515 |
| `recovery_up_v` | V | 0.0008626829 | 0.001596234 | 0.54073661 |
| `recovery_down_v` | V | 0.000339583 | 0.0001767616 … 0.0001768068 | 1.9154667 |
| `step_gain` | V/V | 1.0060115 | 1.007097 | 0.99891568 |
| `mean_power_w` | W | 7.483076e-05 … 7.484843e-05 | 7.507405e-05 … 7.510323e-05 | 0.99660734 |
| `peak_v` | V | 0.7008627 … 0.7099745 | 0.7015962 … 0.7886516 | 0.93846992 |
| `trough_v` | V | 0.4965633 … 0.4993272 | 0.4869953 … 0.4993051 | 0.99208974 |

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
  --case ihp-sg13g2.analog-db.amp_009_leung_nmcnr --image iclayout-bench-tools:local \
  --output build/runs/amp_009_leung_nmcnr-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/amp_009_leung_nmcnr-prepared \
  --output build/runs/amp_009_leung_nmcnr-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'amp_009_leung_nmcnr'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [analog-db amp_009_leung_nmcnr at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_009_leung_nmcnr),
with PolyForm Noncommercial normalized-material terms and recorded CODA-Team
AnalogGym BSD-3-Clause component terms in the collection [LICENSE](../../LICENSE)
and [NOTICE](../../NOTICE); the independently authored measurement deck is MIT.
