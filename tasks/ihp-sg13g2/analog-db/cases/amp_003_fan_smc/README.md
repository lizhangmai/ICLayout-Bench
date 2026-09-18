> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Single-Capacitor Three-Stage Feedforward OTA

## Overview

The folded PMOS-input stage drives `net050`; the PMOS stage at `net043`
and its NMOS mirror drive `net049`, which controls the NMOS output device.
An active feedforward path drives the output PMOS directly from `net050`.
A single physical capacitor branch connects `net050` to output. This is the
single-capacitor representative: there is no second `net049` capacitor or
series nulling resistor. The large retained mirror multiplicities and coupled
three-stage/feedforward paths require their own loaded recovery calibration.

The maintained circuit retains all 24 source MOS groups as 412 physical
fingers, 2 MIM units and 0 high-poly segments. All MOS dimensions/multiplicities are retained exactly.
The maintained 3 uA sink is external through `net013`.
The source value was 60 uA; the maintained 3 uA bias is a deliberate headroom calibration, not an unchanged upstream operating point. Physical
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
- [Reference layout](reference/amp_003_fan_smc.gds): independently constructed witness.

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

Measured `layout-v2` score: **26.759802**, with electrical quality
**E = 1.0511159** and area quality **Q = 0.068126362**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **307375.7254 um2**.

Area reference: **20940.39 um2**. 417 expanded device instances; sum of device/contact envelopes 13771.5365 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `output_v` | V | 0.49935918 | 0.49996489 | 0.9994955 |
| `bias_v` | V | 0.82080801 | 0.81960251 | 0.99899642 |
| `power_w` | W | 5.4973186e-05 | 5.575258e-05 | 0.98602048 |
| `dc_gain_db` | dB | 95.33123 | 95.35406 | 1.0026319 |
| `unity_hz` | Hz | 1369789 … 1383658 | 1416461 … 1485272 | 1.0340724 |
| `phase_margin_deg` | deg | 85.30559 … 86.9872 | 76.4297 … 79.2516 | 0.95300676 |
| `recovery_up_v` | V | 0.0009181133 … 0.000918114 | 0.0001642943 … 0.0002066185 | 4.4269335 |
| `recovery_down_v` | V | 0.0006408193 … 0.0006408194 | 3.511188e-05 … 0.0007265121 | 0.88221117 |
| `step_gain` | V/V | 0.9986135 | 0.999353 … 0.999354 | 0.99926005 |
| `mean_power_w` | W | 5.414429e-05 … 5.427551e-05 | 5.486363e-05 … 5.502446e-05 | 0.98638878 |
| `peak_v` | V | 0.6990819 | 0.6998357 … 0.7328612 | 0.97262128 |
| `trough_v` | V | 0.4993592 | 0.489406 … 0.4999641 | 0.9917739 |

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
  --case ihp-sg13g2.analog-db.amp_003_fan_smc --image iclayout-bench-tools:local \
  --output build/runs/amp_003_fan_smc-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/amp_003_fan_smc-prepared \
  --output build/runs/amp_003_fan_smc-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'amp_003_fan_smc'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [analog-db amp_003_fan_smc at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_003_fan_smc),
with PolyForm Noncommercial normalized-material terms and recorded CODA-Team
AnalogGym BSD-3-Clause component terms in the collection [LICENSE](../../LICENSE)
and [NOTICE](../../NOTICE); the independently authored measurement deck is MIT.
