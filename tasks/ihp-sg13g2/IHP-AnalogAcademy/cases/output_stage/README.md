# CMOS OTA Output Stage

## Overview

`output_stage` is the output stage of a two-stage CMOS operational transconductance
amplifier. `MM5` is the PMOS output current source, `MM9` is its diode-connected
bias replica, and `MM6` is the long-channel NMOS pull-down controlled by `dn4`.
`CC2` provides MIM compensation between `dn4` and `vout`, with explicit tap
devices `RR4` and `RR5`. The maintained interface has five ports: `vdd`, `iout`,
`vout`, `vss`, and `dn4`, in the order declared by [case.toml](case.toml).

Qualification covers DC bias and voltage gain at 1.2 V and 27 °C, with the
input bias and output load defined in [problem.md](problem.md).

## Files

| File | Purpose |
|---|---|
| [problem.md](problem.md) | Solver objective, interface, physical requirements, operating conditions, and scoring |
| [case.toml](case.toml) | Single case configuration, input digests, toolchain, constraints, and evaluation plan |
| [materials/circuit.cdl](materials/circuit.cdl) | Authoritative LVS netlist |
| [materials/circuit.spice](materials/circuit.spice) | Pre-layout simulator netlist |
| [materials/testbench.spice](materials/testbench.spice) | Bias, load, AC sweep, and measurements |
| [Collection LICENSE](../../LICENSE) | License for the declared circuit materials |
| [reference/output_stage.gds](reference/output_stage.gds) | Qualified feasibility witness, excluded from standard solver inputs |

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

Measured `layout-v2` score: **115.823517**, with electrical quality
**E = 0.9902383** and area quality **Q = 1.3547332**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **1692.1044 um2**.

Area reference: **2292.35 um2**. 6 expanded device instances; sum of device/contact envelopes 1466.0063 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `output_gain` | V/V | 9.526243 | 9.35124 | 0.98162938 |
| `output_gain_high` | V/V | 1.122446 | 1.079013 | 0.96130504 |
| `output_bias` | V | 0.64746794 | 0.64656523 | 0.99924831 |
| `supply_power` | W | 4.8148779e-05 | 4.8133109e-05 | 1.0003255 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

### Calibration limits

Replace both finite source taps by 1e-6 ohm connections and run the same
source deck, models, temperature and nominal values. Recorded finite/ideal
output bias is 0.6474679382968 / 0.6474679392507 V; 100 MHz gain is
1.122446 / 1.122463 V/V and has the largest relative difference. Normalize
by the absolute finite-source value, with a 1e-30 floor. No scored requirement changes.

The following maintainer regression limits are read by the reproduction tests;
they do not add solver requirements.

| Comparison | Unit | Maximum difference |
| --- | --- | --- |
| `relative` | 1 | 1.6e-05 |


Coefficient 4 reflects a complete compact gain stage with a current-source
bias replica, compensation capacitor and output-load requirements.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case module_1_bandgap_reference.part_3_layout.OTA_layout.output_stage --image iclayout-bench-tools:local \
  --output build/runs/output_stage-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/output_stage-prepared \
  --output build/runs/output_stage-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'output_stage'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

The model-boundary calibration tolerances above are exercised by `tests/integration/test_output_stage_postlayout.py`.

## Source and License

Adapted from the [`output_stage` circuit](https://github.com/IHP-GmbH/IHP-AnalogAcademy/blob/133ecf657572e021b5921b5a1b7693abfb209623/modules/module_1_bandgap_reference/part_3_layout/OTA_layout/output_stage/schematic_mod/output_stage.sch).

Case materials: [Apache-2.0](../../LICENSE). PDK, model and tool licenses
apply to their respective materials.
