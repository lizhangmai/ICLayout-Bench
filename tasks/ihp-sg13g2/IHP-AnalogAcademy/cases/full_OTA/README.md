# Two-Stage CMOS OTA

## Overview

`two_stage_OTA_layout` is a two-stage CMOS operational transconductance
amplifier with a differential input stage, a second-stage output driver, and a
MIM compensation capacitor. Its maintained six-port interface is `v-`, `v+`,
`vss`, `vdd`, `iout`, and `vout` in the order declared by
[case.toml](case.toml).

Qualification covers DC bias and open-loop AC response at 1.2 V and 27 °C,
with an 80 µA bias sink and 500 fF load as defined in [problem.md](problem.md).

## Files

| File | Purpose |
|---|---|
| [problem.md](problem.md) | Solver objective, interface, physical requirements, operating conditions, and scoring |
| [case.toml](case.toml) | Single case configuration, input digests, toolchain, constraints, and evaluation plan |
| [materials/circuit.cdl](materials/circuit.cdl) | Authoritative LVS netlist |
| [materials/circuit.spice](materials/circuit.spice) | Pre-layout simulator netlist |
| [materials/testbench.spice](materials/testbench.spice) | Nominal bias, feedback fixture, AC sweep, and measurements |
| [Collection LICENSE](../../LICENSE) | License for the declared circuit materials |
| [reference/two_stage_OTA_layout.gds](reference/two_stage_OTA_layout.gds) | Qualified feasibility witness, excluded from standard solver inputs |

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

Measured `layout-v2` score: **103.614517**, with electrical quality
**E = 0.99574935** and area quality **Q = 1.0781798**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **2723.553175 um2**.

Area reference: **2936.48 um2**. 24 expanded device instances; sum of device/contact envelopes 1887.1830 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `low_frequency_gain` | dB | 70.11943 | 69.99139 | 0.98536697 |
| `unity_gain_bandwidth` | Hz | 4148602 | 4080965 | 0.98369644 |
| `phase_margin` | deg | 61.2768 | 60.0036 | 0.99297635 |
| `supply_power` | W | 0.00019704069 | 0.00019703475 | 1.0000302 |
| `output_bias` | V | 0.59962952 | 0.59970968 | 0.99993321 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

Coefficient 6 reflects the coupled two-stage gain path and compensation,
with feedback, stability and loaded response requirements.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case module_1_bandgap_reference.part_3_layout.OTA_layout.full_OTA --image iclayout-bench-tools:local \
  --output build/runs/full_OTA-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/full_OTA-prepared \
  --output build/runs/full_OTA-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'full_OTA'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Adapted from the [`two_stage_OTA_layout` circuit](https://github.com/IHP-GmbH/IHP-AnalogAcademy/blob/133ecf657572e021b5921b5a1b7693abfb209623/modules/module_1_bandgap_reference/part_3_layout/OTA_layout/full_OTA/schematic_mod/two_stage_OTA_layout.sch).

Case materials: [Apache-2.0](../../LICENSE). PDK, model and tool licenses
apply to their respective materials.
