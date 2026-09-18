# Three-Stage SiGe HBT Transimpedance Amplifier

## Overview

This case contains a qualified three-stage, single-ended SiGe HBT
transimpedance amplifier. Q1, Q2 and Q3 form the input, intermediate and
output stages; the resistor network supplies feedback, loading and emitter
degeneration, and three MIM capacitors decouple the independent rails. The
ordered interface is `RFin RFout VSS vcc1 vcc2 vcc3`.

Qualification covers the nominal 1 MHz to
100 MHz transfer, bias and supply-power behavior at three input-current
conditions. The extraction boundary and its substrate treatment are recorded
in the [problem](problem.md#physical-requirements) and the calibration below.

## Files

| File | Purpose |
|---|---|
| [problem.md](problem.md) | Solver-facing layout, physical and electrical contract |
| [case.toml](case.toml) | Frozen task inputs, constraints, toolchain and evaluation plan |
| [materials/circuit.cdl](materials/circuit.cdl) | Strict LVS netlist |
| [materials/circuit.spice](materials/circuit.spice) | Ready-to-use pre-layout simulator netlist |
| [materials/testbench.spice](materials/testbench.spice) | Shared nominal operating-point and AC testbench |
| [Collection LICENSE](../../LICENSE) | Collection distribution terms; excluded from solver inputs |
| [reference/FDM_QNC_00_LN_TIA.gds](reference/FDM_QNC_00_LN_TIA.gds) | Qualified reference layout, top cell `FDM_QNC_00_LN_TIA` |

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

Measured `layout-v2` score: **20.182896**, with electrical quality
**E = 0.81797696** and area quality **Q = 0.049799603**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **372960 um2**.

Area reference: **18573.26 um2**. 15 expanded device instances; sum of device/contact envelopes 12204.4550 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `transimpedance_low` | ohm | 71.6458 … 727.9483 | 26.86401 … 361.9013 | 0.37495582 |
| `transimpedance_high` | ohm | 71.64499 … 727.9277 | 27.56153 … 401.6418 | 0.38469585 |
| `input_bias` | V | 0.76928563 … 0.81379893 | 0.76052814 … 0.80190337 | 0.99436735 |
| `output_bias` | V | 1.9934517 … 2.0972304 | 2.0569739 … 2.0989965 | 0.97063944 |
| `supply_power` | W | 0.0047628705 … 0.012047075 | 0.0032400708 … 0.0034757852 | 1.4668038 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

### Calibration limits

Run the same source deck at all three input-current points with the finite
source tap, then change only XSUBTAP to R=1e-6. Compare input/output bias,
all three supply currents, total power and both transimpedance measurements.
The native compact-netlist control uses candidate extraction with tap cards
disabled. These are source/model controls, not alternative layout acceptance.
The regression also translates the complete reference by 13 um in X and
17 um in Y and compares area, transfer, bias and power; the relative
repeatability tolerance is 1e-3.

The following maintainer regression limits are read by the reproduction tests;
they do not add solver requirements.

| Comparison | Unit | Maximum difference |
| --- | --- | --- |
| `relative` | 1 | 0.001 |


Coefficient 5 reflects three HBT stages with separate supplies and
interstage parasitics across the declared input-current conditions.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case TO_Apr2025.40_GHZ_LOW_NOISE_TIA --image iclayout-bench-tools:local \
  --output build/runs/40_GHZ_LOW_NOISE_TIA-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/40_GHZ_LOW_NOISE_TIA-prepared \
  --output build/runs/40_GHZ_LOW_NOISE_TIA-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k '40_GHZ_LOW_NOISE_TIA'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

The model-boundary calibration tolerances above are exercised by `tests/integration/test_to_apr2025_40ghz.py`.

## Source and License

Adapted from the [`40_GHZ_LOW_NOISE_TIA` circuit](https://github.com/IHP-GmbH/TO_Apr2025/blob/63e203a0eccfb6028a1a0a8364553e4e979b55b3/40_GHZ_LOW_NOISE_TIA/design_data/qucs-s/40_GHz_Low_Noise_TIA.sch).

Case materials: [Apache-2.0](../../LICENSE). PDK, model and tool licenses
apply to their respective materials.
