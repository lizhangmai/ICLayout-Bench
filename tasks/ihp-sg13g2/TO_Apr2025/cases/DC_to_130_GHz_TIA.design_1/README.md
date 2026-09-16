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

## Reference Results

The reference layout passes artifact validation, the pinned SG13G2 main and
additional maximal DRC scopes without waivers, strict named-port LVS and the
720 × 860 µm functional outline. Post-layout extraction uses candidate HBT
geometry and distributed interconnect R/C. The physical same-net `ptap1` is
retained by LVS and represented with its finite PDK equivalent
`R=43.80789 Ω` in the simulator netlist; both terminals are `VEE`, so this
element has no DC voltage drop. The source and post-layout calibration is
stable when `rshunt` is changed by a factor of ten in either direction, with
all nominal measurements within 0.01% of the baseline.

The table gives measured ranges across the `−100 µA`, `0 A` and `+100 µA`
input-current jobs. Acceptance limits are in [problem.md](problem.md).

| Metric | Unit | Pre-layout | Post-layout |
|---|---|---:|---:|
| Functional area | µm² | — | 581,243.36 |
| Task score (`layout-v1`) | points / 100 | — | 100 |
| 1 MHz signed transimpedance | Ω | 214.00–218.56 | 234.63–239.77 |
| 100 MHz transimpedance magnitude | Ω | 214.00–218.56 | 234.63–239.77 |
| Input bias | V | 0.9487–0.9512 | 0.9473–0.9498 |
| Output bias | V | 1.3137–1.3666 | 1.2743–1.3311 |
| Total supply power | mW | 53.15–54.97 | 52.05–53.84 |

The candidate native-device extraction preserves the HBT multiplicities,
terminals and passive geometry before distributed interconnect RC is merged.
The post-layout measurements therefore use the submitted layout-derived
netlist rather than a separate reference netlist.

The `layout-v1` scoring boundaries are published in
[problem.md](problem.md#electrical-requirements-and-scoring). Response zero
anchors describe loss of useful response; bias and supply anchors define the
outer grading ranges around the intended operating point and budget. These
are explicit grading choices, with the acceptance limits checked separately.
The fixed absolute area target is a feasible envelope demonstrated by the
reference layout, rather than a ratio to the reference or a claim of optimality.

The [HBT diagnostic policy](../../../../../docs/tools.md#hbt-core-simulation-support)
checks Magic compact-contact warnings against native device records before
requiring complete candidate graph validation. The reference report retains
the original diagnostics, their review and the final HBT/RC mapping.

Coefficient 4 reflects a compact transimpedance core with bias, passive
feedback and loaded transfer requirements.

## Reproduce

These operator commands require the installed `ICLayout-Bench-Private` package.
Run preparation from the Public checkout; run any `tests/integration/` commands
from the Private checkout using that environment.

Prepare the image and PDK resources using the shared
[tools guide](../../../../../docs/tools.md#manual-tools). Run from the repository
root and choose a fresh output directory for each reproduction:

```bash
python -m layout_eval.preview prepare \
  --case DC_to_130_GHz_TIA.design_1 \
  --output build/runs/public-preview-DC_to_130_GHz_TIA.design_1-01/prepared \
  --image iclayout-bench-tools:local
python -m layout_eval.preview run \
  --prepared build/runs/public-preview-DC_to_130_GHz_TIA.design_1-01/prepared \
  --output build/runs/public-preview-DC_to_130_GHz_TIA.design_1-01/run
```

These commands generate the reference evaluation report at
`build/runs/public-preview-DC_to_130_GHz_TIA.design_1-01/run/reference/report.json`.
To reproduce pre-layout/post-layout calibration and the reference acceptance
regressions, run:

```bash
python -m pytest -m acceptance_eda \
  tests/integration/test_tia130_postlayout.py
```

The tests create fresh temporary output directories. Reference layouts and
results are available for reproduction and are excluded from standard solver
inputs.

## Source and License

Adapted from the [`DC_to_130_GHz_TIA/design_1` circuit](https://github.com/IHP-GmbH/TO_Apr2025/blob/63e203a0eccfb6028a1a0a8364553e4e979b55b3/DC_to_130_GHz_TIA/design_1/design_data/qucs-s/DC_to_130_GHz_TIA.sch).

Case materials: [Apache-2.0](../../LICENSE). PDK, model and tool licenses
apply to their respective materials.
