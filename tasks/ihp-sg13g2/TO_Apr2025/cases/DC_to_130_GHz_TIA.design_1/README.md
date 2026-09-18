# Two-Stage SiGe HBT Transimpedance Amplifier

## Overview

This case contains a qualified two-stage SiGe HBT transimpedance amplifier.
Q1 and Q2 are direct-coupled common-emitter stages with independent
collector loads; `RRF` provides first-stage resistive feedback and two MIM
capacitors decouple the supply rails. The ordered interface is
`INPUT OUTPUT VCC2V VCC2V1 VEE`.

Qualification covers nominal 1 MHz and
100 MHz transimpedance, bias and supply power at three input-current
conditions. The task uses a same-net substrate tie whose two terminals are
both `VEE`, so it does not create a DC voltage drop.

## Files

| File | Purpose |
|---|---|
| [problem.md](problem.md) | Solver-facing layout, physical and electrical contract |
| [case.toml](case.toml) | Frozen task inputs, constraints, toolchain and evaluation plan |
| [materials/circuit.cdl](materials/circuit.cdl) | Strict LVS netlist |
| [materials/circuit.spice](materials/circuit.spice) | Ready-to-use pre-layout simulator netlist |
| [materials/testbench.spice](materials/testbench.spice) | Shared nominal operating-point and AC testbench |
| [Collection LICENSE](../../LICENSE) | Collection distribution terms; excluded from solver inputs |
| [reference/FMD_QNC_03a_TIA_1.gds](reference/FMD_QNC_03a_TIA_1.gds) | Qualified reference layout, top cell `FMD_QNC_03a_TIA_1` |

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

Measured `layout-v2` score: **8.281639**, with electrical quality
**E = 1.0348389** and area quality **Q = 0.0066276542**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **581243.36 um2**.

Area reference: **3852.28 um2**. 8 expanded device instances; sum of device/contact envelopes 2487.4228 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `transimpedance_low` | ohm | 214.0027 … 218.5573 | 234.6297 … 239.7718 | 1.0963866 |
| `transimpedance_high` | ohm | 214.0021 … 218.5566 | 234.6272 … 239.7692 | 1.096378 |
| `input_bias` | V | 0.94872539 … 0.95122664 | 0.94730512 … 0.94981777 | 0.99929037 |
| `output_bias` | V | 1.3136967 … 1.366563 | 1.2743432 … 1.3311045 | 0.98070296 |
| `supply_power` | W | 0.053154729 … 0.054967593 | 0.052045235 … 0.053835043 | 1.0210374 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

Coefficient 4 reflects a compact transimpedance core with bias, passive
feedback and loaded transfer requirements.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case TO_Apr2025.DC_to_130_GHz_TIA.design_1 --image iclayout-bench-tools:local \
  --output build/runs/DC_to_130_GHz_TIA.design_1-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/DC_to_130_GHz_TIA.design_1-prepared \
  --output build/runs/DC_to_130_GHz_TIA.design_1-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'DC_to_130_GHz_TIA.design_1'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Adapted from the [`DC_to_130_GHz_TIA/design_1` circuit](https://github.com/IHP-GmbH/TO_Apr2025/blob/63e203a0eccfb6028a1a0a8364553e4e979b55b3/DC_to_130_GHz_TIA/design_1/design_data/qucs-s/DC_to_130_GHz_TIA.sch).

Case materials: [Apache-2.0](../../LICENSE). PDK, model and tool licenses
apply to their respective materials.
