# PMOS Differential Input Pair

## Overview

`input_common_centroid` is a matched PMOS differential input pair with two
active devices, four dummy devices, and an explicit n-well tap. The maintained
interface has six ports: `v-`, `v+`, `vdd`, `dn3`, `dn4`, and `tail`, in the
order declared by [case.toml](case.toml).

Qualification covers DC bias and differential AC response at 1.2 V and 27 °C,
with a 20 µA tail current and 50 kΩ drain loads as defined in
[problem.md](problem.md).

## Files

| File | Purpose |
|---|---|
| [problem.md](problem.md) | Solver objective, interface, physical requirements, operating conditions, and scoring |
| [case.toml](case.toml) | Single case configuration, input digests, toolchain, constraints, and evaluation plan |
| [materials/circuit.cdl](materials/circuit.cdl) | Authoritative LVS netlist |
| [materials/circuit.spice](materials/circuit.spice) | Pre-layout simulator netlist |
| [materials/testbench.spice](materials/testbench.spice) | Bias, load, AC sweep, and measurements |
| [Collection LICENSE](../../LICENSE) | License for the declared circuit materials |
| [reference/input_common_centroid.gds](reference/input_common_centroid.gds) | Qualified feasibility witness, excluded from standard solver inputs |

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

Measured `layout-v2` score: **96.490594**, with electrical quality
**E = 0.93715261** and area quality **Q = 0.99348118**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **1244.25105 um2**.

Area reference: **1236.14 um2**. 13 expanded device instances; sum of device/contact envelopes 778.4891 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `differential_gain` | V/V | 2.72776 | 2.726751 | 0.9996301 |
| `differential_gain_high` | V/V | 3.584662 | 2.429818 | 0.67783741 |
| `tail_voltage` | V | 1.1929809 | 1.1931311 | 0.99987481 |
| `common_drain` | V | 0.49999515 | 0.49999415 | 0.99999917 |
| `drain_balance` | V | -1.110223e-16 | 0.00026591766 | 0.99977845 |
| `supply_power` | W | 2.4000031e-05 | 2.4000095e-05 | 0.99999734 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

### Calibration limits

Replace the finite source tap by a 1e-6 ohm connection and run the same
source deck, models, temperature and nominal values. The recorded finite/ideal
supply powers are 2.400003087359e-5 / 2.39996239543e-5 W; supply power has the
largest relative difference. The comparison normalizes by the larger absolute
finite/ideal value, with a 1e-9 floor. No scored requirement changes.

The following maintainer regression limits are read by the reproduction tests;
they do not add solver requirements.

| Comparison | Unit | Maximum difference |
| --- | --- | --- |
| `relative` | 1 | 1.7e-05 |


Coefficient 3 reflects a local differential input block focused on preserving
its paired-device interface and nominal differential response.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case module_1_bandgap_reference.part_3_layout.OTA_layout.input_pair --image iclayout-bench-tools:local \
  --output build/runs/input_pair-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/input_pair-prepared \
  --output build/runs/input_pair-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'input_pair'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

The model-boundary calibration tolerances above are exercised by `tests/integration/test_input_pair_postlayout.py`.

## Source and License

Adapted from the [`input_common_centroid` circuit](https://github.com/IHP-GmbH/IHP-AnalogAcademy/blob/133ecf657572e021b5921b5a1b7693abfb209623/modules/module_1_bandgap_reference/part_3_layout/OTA_layout/input_pair/schematic_mod/input_common_centroid.sch).

Case materials: [Apache-2.0](../../LICENSE). PDK, model and tool licenses
apply to their respective materials.
