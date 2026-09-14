# Four-Stage SiGe HBT Voltage Amplifier

## Overview

This case contains a qualified four-stage direct-coupled SiGe HBT voltage
amplifier. Four `npn13G2` common-emitter stages use collector loads,
emitter degeneration and three interstage `VBIAS` clamps. The case-owned
interface is `IN OUT VDD VSS VBIAS`.

Qualification covers nominal 100 MHz voltage
gain, output bias and `VDD` supply current at the declared bias point. The
candidate extraction boundary and substrate calibration are recorded in
[materials/pex_scope.json](materials/pex_scope.json).

## Files

| File | Purpose |
|---|---|
| [problem.md](problem.md) | Solver-facing layout, physical and electrical contract |
| [case.toml](case.toml) | Frozen task inputs, constraints, toolchain and evaluation plan |
| [materials/circuit.cdl](materials/circuit.cdl) | Strict LVS netlist with drawn HBT geometry |
| [materials/circuit.spice](materials/circuit.spice) | Ready-to-use pre-layout simulator netlist |
| [materials/testbench.spice](materials/testbench.spice) | Shared nominal operating-point and AC testbench |
| [materials/pex_scope.json](materials/pex_scope.json) | Candidate PEX and calibration boundary |
| [Collection LICENSE](../../LICENSE) | Shared terms, delivered as `materials/LICENSE` |
| [reference/lna160_four_stage_distinct_rsil_qualified.gds](reference/lna160_four_stage_distinct_rsil_qualified.gds) | Qualified reference layout, top cell `LNA160_FOUR_STAGE` |

## Reference Results

The reference layout passes artifact validation, the pinned SG13G2 main and
additional maximal DRC scopes without waivers, strict named-port LVS and the
160 × 90 µm functional outline. Post-layout extraction uses candidate HBT
geometry and distributed interconnect R/C. Strict LVS retains the finite
`ptap1`; the approved candidate body boundary reconciles the compact HBT
body to `VSS` with tap extraction disabled. The source tap uses the finite
equivalent `R=81.6666667 Ω` for calibration. The finite-tap and ideal-body
nominal gain differed by only 8.5 × 10⁻⁵ dB, below the 0.1 dB calibration
tolerance.

The table reports the nominal operating point at `VIN=0.8 V` and
`VBIAS=0.76 V`. Acceptance limits are in [problem.md](problem.md).

| Metric | Unit | Pre-layout | Post-layout |
|---|---|---:|---:|
| Functional area | µm² | — | 12,642 |
| Task score (`layout-v1`) | points / 100 | — | 100 |
| 100 MHz voltage gain | dB | 40.85778 | 40.83956 |
| `OUT` DC bias | V | 1.00304 | 0.932008 |
| `VDD` supply current | µA | 537.010 | 544.849 |

The deck also reports `IN` bias and `VBIAS` current as diagnostics; they are
not acceptance metrics. The source and post-layout values above come from
the same testbench, with the post-layout values measured after extracting the
submitted reference layout.

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
  --case 160GHz_LNA \
  --output build/runs/public-preview-160GHz_LNA-01/prepared \
  --image layout-bench-tools:local
uv run --locked python scripts/public_preview.py run \
  --prepared build/runs/public-preview-160GHz_LNA-01/prepared \
  --output build/runs/public-preview-160GHz_LNA-01/run
```

These commands generate the reference evaluation report at
`build/runs/public-preview-160GHz_LNA-01/run/reference/report.json`.
To reproduce pre-layout/post-layout calibration and the reference acceptance
regressions, run:

```bash
uv run --locked pytest -m acceptance_eda \
  tests/integration/test_lna160_postlayout.py
```

The tests create fresh temporary output directories. Reference layouts and
results are available for reproduction and are excluded from standard solver
inputs.

## Source and License

Adapted from the [`160GHz_LNA` circuit](https://github.com/IHP-GmbH/TO_Apr2025/blob/63e203a0eccfb6028a1a0a8364553e4e979b55b3/160GHz_LNA/design_data/qucs-s/160GHz_LNA(MAIN).sch).

Case materials: [Apache-2.0](../../LICENSE). PDK, model and tool licenses
apply to their respective materials.
