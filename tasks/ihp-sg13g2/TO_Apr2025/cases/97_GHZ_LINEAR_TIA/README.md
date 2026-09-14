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
method are recorded in [materials/pex_scope.json](materials/pex_scope.json).

## Files

| File | Purpose |
|---|---|
| [problem.md](problem.md) | Solver-facing layout, physical and electrical contract |
| [case.toml](case.toml) | Frozen task inputs, constraints, toolchain and evaluation plan |
| [materials/circuit.cdl](materials/circuit.cdl) | Strict LVS netlist |
| [materials/circuit.spice](materials/circuit.spice) | Ready-to-use pre-layout simulator netlist |
| [materials/testbench.spice](materials/testbench.spice) | Shared nominal operating-point, AC and DC-linearity testbench |
| [materials/pex_scope.json](materials/pex_scope.json) | Candidate PEX and calibration boundary |
| [Collection LICENSE](../../LICENSE) | Shared terms, delivered as `materials/LICENSE` |
| [reference/FMD_QNC_01_LIN_TIA.gds](reference/FMD_QNC_01_LIN_TIA.gds) | Passing reference layout, top cell `FMD_QNC_01_LIN_TIA` |

## Reference Results

The reference layout passes artifact validation, the pinned SG13G2 main and
additional maximal DRC scopes without waivers, strict named-port LVS and the
720 × 620 µm functional outline. Post-layout extraction uses candidate HBT
geometry and distributed interconnect R/C. The compact-device substrate body
is reconciled to `VSS` with tap extraction disabled in the candidate path;
the finite source `ptap1` remains in the source calibration and strict LVS
netlist. The finite-tap and ideal-body calibration agreed within 8.7 × 10⁻¹³
relative across the reported values, below the declared 1 × 10⁻⁹ limit.

The table gives measured ranges across the `−5 µA`, `0 A` and `+5 µA`
input-current jobs. Linearity is the scalar maximum from the 21-point
`−5 µA` to `+5 µA` DC sweep for each job. Acceptance limits are in
[problem.md](problem.md).

| Metric | Unit | Pre-layout | Post-layout |
|---|---|---:|---:|
| Functional area | µm² | — | 416,867.625 |
| Task score (`layout-v1`) | points / 100 | — | 100 |
| 1 MHz signed transimpedance | Ω | 489.92–546.12 | 471.80–521.90 |
| 100 MHz transimpedance magnitude | Ω | 489.92–546.11 | 513.63–573.06 |
| Linearity error | % | 1.4654 | 1.2742 |
| Input bias | V | 0.7988–0.8008 | 0.7885–0.7905 |
| Output bias | V | 2.0655–2.0713 | 2.0679–2.0730 |
| Total supply power | mW | 6.529–6.928 | 3.591–3.625 |

The source and candidate native-device checks use the same compact HBT model
and preserve the declared `Nx` values. A grid translation of the complete
reference layout also preserves all declared metrics within the 1 × 10⁻³
relative repeatability limit.

The `layout-v1` scoring boundaries are published in
[problem.md](problem.md#electrical-requirements-and-scoring). Response zero
anchors describe loss of useful response; bias and supply anchors define the
outer grading ranges around the intended operating point and budget. These
are explicit grading choices, with the acceptance limits checked separately.
The fixed absolute area target is a feasible envelope demonstrated by the
reference layout, rather than a ratio to the reference or a claim of optimality.

The regression checks the witness, independent waveform/linearity calculations,
port rejection and repeatability. Input consistency and actual reference acceptance
support this case’s `qualified` status. Electrical-failure handling is covered by
shared evaluator regressions; this case does not supply a dedicated failing layout.

## Reproduce

Prepare the image and PDK resources using the shared
[tools guide](../../../../../docs/tools.md#manual-tools). Run from the repository
root and choose a fresh output directory for each reproduction:

```bash
uv run --locked python scripts/public_preview.py prepare \
  --case 97_GHZ_LINEAR_TIA \
  --output build/runs/public-preview-97_GHZ_LINEAR_TIA-01/prepared \
  --image layout-bench-tools:local
uv run --locked python scripts/public_preview.py run \
  --prepared build/runs/public-preview-97_GHZ_LINEAR_TIA-01/prepared \
  --output build/runs/public-preview-97_GHZ_LINEAR_TIA-01/run
```

These commands generate the reference evaluation report at
`build/runs/public-preview-97_GHZ_LINEAR_TIA-01/run/reference/report.json`.
To reproduce pre-layout/post-layout calibration and the reference acceptance
regressions, run:

```bash
uv run --locked pytest -m acceptance_eda \
  tests/integration/test_tia97_postlayout.py
```

The tests create fresh temporary output directories. Reference layouts and
results are available for reproduction and are excluded from standard solver
inputs.

## Source and License

Adapted from the [`97_GHZ_LINEAR_TIA` circuit](https://github.com/IHP-GmbH/TO_Apr2025/blob/63e203a0eccfb6028a1a0a8364553e4e979b55b3/97_GHZ_LINEAR_TIA/design_data/qucs-s/97_GHZ_LINEAR_TIA.sch).

Case materials: [Apache-2.0](../../LICENSE). PDK, model and tool licenses
apply to their respective materials.
