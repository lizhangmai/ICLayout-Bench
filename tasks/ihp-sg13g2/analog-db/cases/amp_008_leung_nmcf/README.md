> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Dual-Capacitor Three-Stage OTA

## Overview

The folded PMOS-input stage drives `net050`; a PMOS stage at `net043`
and its NMOS mirror drive `net049`, which controls the NMOS output device.
A parallel feedforward path drives the output PMOS directly from `net050`.
Two capacitive paths connect `net050` to output and `net049` to output.
These couple two internal gain nodes to the load, unlike the maintained
two-stage OTA's single Miller path.

The maintained circuit retains all 24 source MOS groups as 236 physical
fingers, 3 MIM units and 0 high-poly segments. MOS W/L are rounded to the nearest 0.01 um process grid. All source multiplicities are retained.
The source's 7.52942 uA sink is external through `net013`. Physical
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
- [Reference layout](reference/amp_008_leung_nmcf.gds): independently constructed witness.

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

Measured `layout-v2` score: **31.373188**, with electrical quality
**E = 1.0761413** and area quality **Q = 0.091463537**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **194584.2098 um2**.

Area reference: **17797.36 um2**. 242 expanded device instances; sum of device/contact envelopes 11690.9447 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `output_v` | V | 0.49907771 | 0.49981546 | 0.99938558 |
| `bias_v` | V | 0.72175232 | 0.72096044 | 0.99934053 |
| `power_w` | W | 0.00019054529 | 0.00019177014 | 0.99361291 |
| `dc_gain_db` | dB | 83.75325 | 88.3934 | 1.7061119 |
| `unity_hz` | Hz | 2793689 … 3046550 | 2744138 … 2989930 | 0.98141504 |
| `phase_margin_deg` | deg | 56.8138 … 66.4509 | 51.6184 … 62.1753 | 0.97194639 |
| `recovery_up_v` | V | 0.0003963888 … 0.0003963889 | 0.0005150429 | 0.77006931 |
| `recovery_down_v` | V | 0.0009222942 … 0.0009222943 | 0.0001845354 | 4.9763776 |
| `step_gain` | V/V | 1.0026295 | 1.0034975 | 0.99913275 |
| `mean_power_w` | W | 0.0001865652 … 0.0001865916 | 0.0001876508 … 0.0001876788 | 0.99420712 |
| `peak_v` | V | 0.700899 … 0.7059239 | 0.7057017 … 0.7157009 | 0.99191835 |
| `trough_v` | V | 0.4882809 … 0.495909 | 0.4806747 … 0.4939142 | 0.99370142 |

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
  --case ihp-sg13g2.analog-db.amp_008_leung_nmcf --image iclayout-bench-tools:local \
  --output build/runs/amp_008_leung_nmcf-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/amp_008_leung_nmcf-prepared \
  --output build/runs/amp_008_leung_nmcf-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'amp_008_leung_nmcf'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [analog-db amp_008_leung_nmcf at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_008_leung_nmcf),
with PolyForm Noncommercial normalized-material terms and recorded CODA-Team
AnalogGym BSD-3-Clause component terms in the collection [LICENSE](../../LICENSE)
and [NOTICE](../../NOTICE); the independently authored measurement deck is MIT.
