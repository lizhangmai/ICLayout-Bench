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
in [materials/pex_scope.json](materials/pex_scope.json).

## Files

| File | Purpose |
|---|---|
| [problem.md](problem.md) | Solver-facing layout, physical and electrical contract |
| [case.toml](case.toml) | Frozen task inputs, constraints, toolchain and evaluation plan |
| [materials/circuit.cdl](materials/circuit.cdl) | Strict LVS netlist |
| [materials/circuit.spice](materials/circuit.spice) | Ready-to-use pre-layout simulator netlist |
| [materials/testbench.spice](materials/testbench.spice) | Shared nominal operating-point and AC testbench |
| [materials/pex_scope.json](materials/pex_scope.json) | Candidate PEX and calibration boundary |
| [Collection LICENSE](../../LICENSE) | Shared terms, delivered as `materials/LICENSE` |
| [reference/FDM_QNC_00_LN_TIA.gds](reference/FDM_QNC_00_LN_TIA.gds) | Qualified reference layout, top cell `FDM_QNC_00_LN_TIA` |

## Reference Results

The reference layout passes artifact validation, the pinned SG13G2 main and
additional maximal DRC scopes without waivers, strict named-port LVS and the
660 × 620 µm functional outline. Post-layout extraction uses candidate HBT
geometry and distributed interconnect R/C. The compact-device substrate body
is reconciled to `VSS` with tap extraction disabled in the candidate path;
the finite source `ptap1` remains in the source calibration and strict LVS
netlist. The native compact-device check differed from the source metrics by
at most 1.4 × 10⁻⁷ relative, and the declared tap and grid-translation checks
remain within the 1 × 10⁻³ relative calibration limit.

The table gives measured ranges across the `−100 µA`, `0 A` and `+100 µA`
input-current jobs. Acceptance limits are in [problem.md](problem.md).

| Metric | Unit | Pre-layout | Post-layout |
|---|---|---:|---:|
| Functional area | µm² | — | 372,960 |
| Task score (`layout-v1`) | points / 100 | — | 100 |
| 1 MHz signed transimpedance | Ω | 71.65–727.95 | 26.86–361.90 |
| 100 MHz transimpedance magnitude | Ω | 71.64–727.93 | 27.56–401.64 |
| Input bias | V | 0.7693–0.8138 | 0.7605–0.8019 |
| Output bias | V | 1.9935–2.0972 | 2.0570–2.0990 |
| Total supply power | mW | 4.763–12.047 | 3.240–3.476 |

The `layout-v1` scoring boundaries are published in
[problem.md](problem.md#electrical-requirements-and-scoring). Response zero
anchors describe loss of useful response; bias and supply anchors define the
outer grading ranges around the intended operating point and budget. These
are explicit grading choices, with the acceptance limits checked separately.
The fixed absolute area target is a feasible envelope demonstrated by the
reference layout, rather than a ratio to the reference or a claim of optimality.

## Reproduce

Prepare the image and PDK resources using the shared
[tools guide](../../../../../docs/tools.md#manual-tools). Run from the repository
root and choose a fresh output directory for each reproduction:

```bash
uv run --locked python scripts/public_preview.py prepare \
  --case 40_GHZ_LOW_NOISE_TIA \
  --output build/runs/public-preview-40_GHZ_LOW_NOISE_TIA-01/prepared \
  --image layout-bench-tools:local
uv run --locked python scripts/public_preview.py run \
  --prepared build/runs/public-preview-40_GHZ_LOW_NOISE_TIA-01/prepared \
  --output build/runs/public-preview-40_GHZ_LOW_NOISE_TIA-01/run
```

These commands generate the reference evaluation report at
`build/runs/public-preview-40_GHZ_LOW_NOISE_TIA-01/run/reference/report.json`.
To reproduce pre-layout/post-layout calibration and the reference acceptance
regressions, run:

```bash
uv run --locked pytest -m acceptance_eda \
  tests/integration/test_to_apr2025_40ghz.py
```

The tests create fresh temporary output directories. Reference layouts and
results are available for reproduction and are excluded from standard solver
inputs.

## Source and License

Adapted from the [`40_GHZ_LOW_NOISE_TIA` circuit](https://github.com/IHP-GmbH/TO_Apr2025/blob/63e203a0eccfb6028a1a0a8364553e4e979b55b3/40_GHZ_LOW_NOISE_TIA/design_data/qucs-s/40_GHz_Low_Noise_TIA.sch).

Case materials: [Apache-2.0](../../LICENSE). PDK, model and tool licenses
apply to their respective materials.
