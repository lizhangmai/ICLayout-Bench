# Linear SiGe HBT Transimpedance Amplifier

## Overview

This case contains a qualified three-stage SiGe HBT transimpedance amplifier
with active emitter-follower feedback. Q1 is the input stage, Q2 is an
intermediate emitter follower, Q3 is the output stage, and Q4 senses `RFOUT`
for active feedback through `RFB`. The ordered interface is
`RFIN RFOUT VCC1 VCC2 VCC3 VSS`.

Reference validation covers nominal 1 MHz and
100 MHz transimpedance, bias, power and a dense DC-linearity measurement at
three input-current conditions. The extraction boundary and calibration
method are recorded in the [problem](problem.md#physical-requirements) and the calibration below.

## Files

| File | Purpose |
|---|---|
| [problem.md](problem.md) | Solver-facing layout, physical and electrical contract |
| [case.toml](case.toml) | Frozen task inputs, constraints, toolchain and evaluation plan |
| [materials/circuit.cdl](materials/circuit.cdl) | Strict LVS netlist |
| [materials/circuit.spice](materials/circuit.spice) | Ready-to-use pre-layout simulator netlist |
| [materials/testbench.spice](materials/testbench.spice) | Shared nominal operating-point, AC and DC-linearity testbench |
| [Collection LICENSE](../../LICENSE) | Collection distribution terms; excluded from solver inputs |
| [reference/FMD_QNC_01_LIN_TIA.gds](reference/FMD_QNC_01_LIN_TIA.gds) | Passing reference layout, top cell `FMD_QNC_01_LIN_TIA` |

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

Measured `layout-v2` score: **23.583241**, with electrical quality
**E = 1.2386059** and area quality **Q = 0.044902839**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **416867.625 um2**.

Area reference: **18718.54 um2**. 17 expanded device instances; sum of device/contact envelopes 12300.6100 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `transimpedance_low` | ohm | 489.9266 … 546.1247 | 471.8016 … 521.9023 | 0.95564676 |
| `transimpedance_high` | ohm | 489.9169 … 546.1136 | 513.6323 … 573.0564 | 1.048407 |
| `linearity_error_pct` | percent | 1.465435 | 1.274188 | 1.1500931 |
| `input_bias` | V | 0.79880232 … 0.80084576 | 0.78853741 … 0.79046105 | 0.99507923 |
| `output_bias` | V | 2.0654884 … 2.0712579 | 2.0679446 … 2.0730464 | 0.99883173 |
| `supply_power` | W | 0.00652874 … 0.0069283423 | 0.0035910793 … 0.0036254514 | 1.8180439 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

### Calibration limits

Change only XRSUB from 81.6666667 ohm to 1e-6 ohm and rerun the same source
deck at all three input-current points. Normalize each difference by the
absolute finite-source value, with a 1e-30 floor. The recorded finite/ideal
output bias is 2.068457712479 / 2.068457712479 V and low-frequency
transimpedance is 518.3655 / 518.3655 ohm; supply3_current has the largest
relative difference. No scored requirement changes.

The independent linearity check reads VSENSE current and RFOUT voltage at every
DC point specified by the public testbench, computes the straight line through
the endpoint samples and normalizes maximum output error by endpoint output
span. The recorded source maximum is 1.4654353 percent over a 0.0057695311 V
output span. Acceptance comes from the task's linearity metric.

The following maintainer regression limits are read by the reproduction tests;
they do not add solver requirements.

| Comparison | Unit | Maximum difference |
| --- | --- | --- |
| `relative` | 1 | 1e-09 |


Coefficient 6 reflects active emitter-follower feedback coupled to the
multistage transfer path, bias headroom and dense-sweep linearity requirements.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case TO_Apr2025.97_GHZ_LINEAR_TIA --image iclayout-bench-tools:local \
  --output build/runs/97_GHZ_LINEAR_TIA-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/97_GHZ_LINEAR_TIA-prepared \
  --output build/runs/97_GHZ_LINEAR_TIA-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k '97_GHZ_LINEAR_TIA'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

The model-boundary calibration tolerances above are exercised by `tests/integration/test_tia97_postlayout.py`.

## Source and License

Adapted from the [`97_GHZ_LINEAR_TIA` circuit](https://github.com/IHP-GmbH/TO_Apr2025/blob/63e203a0eccfb6028a1a0a8364553e4e979b55b3/97_GHZ_LINEAR_TIA/design_data/qucs-s/97_GHZ_LINEAR_TIA.sch).

Case materials: [Apache-2.0](../../LICENSE). PDK, model and tool licenses
apply to their respective materials.
