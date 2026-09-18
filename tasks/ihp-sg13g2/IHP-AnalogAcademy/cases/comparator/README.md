# Dynamic Comparator

## Overview

`DIFF_COMPARATOR` is a clocked dynamic differential comparator with complementary
outputs. The maintained circuit contains 13 MOS devices and two explicit taps;
the public interface is `vdd`, `gnd`, `V+`, `V-`, `clk`, `out-`, `out+`, and
`vbias` in the order declared by [case.toml](case.toml).

Reference validation covers clocked decisions at 1.2 V and 27 °C across the four
differential-input settings in [problem.md](problem.md).

## Files

| File | Purpose |
|---|---|
| [problem.md](problem.md) | Solver objective, interface, physical requirements, operating conditions, and scoring |
| [case.toml](case.toml) | Single case configuration, input digests, toolchain, constraints, and evaluation plan |
| [materials/circuit.cdl](materials/circuit.cdl) | Authoritative LVS netlist |
| [materials/circuit.spice](materials/circuit.spice) | Pre-layout simulator netlist |
| [materials/testbench.spice](materials/testbench.spice) | Clock stimulus and measurements |
| [Collection LICENSE](../../LICENSE) | Collection distribution terms; excluded from solver inputs |
| [reference/DIFF_COMPARATOR.gds](reference/DIFF_COMPARATOR.gds) | Passing feasibility witness, excluded from standard solver inputs |

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

Measured `layout-v2` score: **49.648076**, with electrical quality
**E = 0.81471533** and area quality **Q = 0.30255126**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **1662.396 um2**.

Area reference: **502.96 um2**. 24 expanded device instances; sum of device/contact envelopes 306.3377 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `worst_delay` | s | 1.779459e-09 … 1.871706e-09 | 2.163719e-09 … 2.541667e-09 | 0.73640882 |
| `decision_margin` | V | 1.199971 … 1.199985 | 1.198178 … 1.199435 | functional |
| `supply_power` | W | 5.667991e-05 … 5.815247e-05 | 6.009035e-05 … 6.415317e-05 | 0.9013486 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

Coefficient 6 reflects clocked input sensing and regenerative decision stages,
whose interconnect parasitics affect loaded decision delay and margin.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case module_3_8_bit_SAR_ADC.part_5_analog_layout.comparator --image iclayout-bench-tools:local \
  --output build/runs/comparator-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/comparator-prepared \
  --output build/runs/comparator-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'comparator'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Adapted from the [`DIFF_COMPARATOR` circuit](https://github.com/IHP-GmbH/IHP-AnalogAcademy/tree/133ecf657572e021b5921b5a1b7693abfb209623/modules/module_3_8_bit_SAR_ADC/part_5_analog_layout/comparator).

Case materials: [Apache-2.0](../../LICENSE). PDK, model and tool licenses
apply to their respective materials.
