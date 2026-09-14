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

## Reference Results

The reference GDS passes artifact, DRC, strict named-port LVS, functional
geometry, candidate-derived RC extraction, and post-layout simulation. The table
compares the pre-layout simulator netlist with the extracted reference layout under the same
nominal deck.

| Metric | Unit | Pre-layout | Post-layout |
|---|---|---:|---:|
| Functional area | µm² | — | 2,723.553175 |
| Task score (`layout-v1`) | points / 100 | — | 100 |
| Low-frequency gain | dB | 70.11943 | 69.99139 |
| Unity-gain bandwidth | MHz | 4.148602 | 4.080965 |
| Phase margin | ° | 61.2768 | 60.0036 |
| Output bias | V | 0.599630 | 0.599710 |
| Quiescent supply power | µW | 197.041 | 197.035 |

All post-layout values satisfy the limits in
[problem.md](problem.md#electrical-requirements-and-scoring). The extracted RC
model uses a compact-device body boundary with ideal model rails; explicit taps
are still checked by LVS. Well/substrate sheet resistance, body coupling, and
noise are outside this qualification scope. The finite-source-tap versus
ideal-body calibration changes unity-gain bandwidth by 1 Hz, supply power by
4.3 × 10⁻¹² W, and output bias by 8 × 10⁻¹³ V; gain and phase margin are
unchanged at printed precision.

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
  --case full_OTA \
  --output build/runs/public-preview-full_OTA-01/prepared \
  --image layout-bench-tools:local
uv run --locked python scripts/public_preview.py run \
  --prepared build/runs/public-preview-full_OTA-01/prepared \
  --output build/runs/public-preview-full_OTA-01/run
```

These commands generate the reference evaluation report at
`build/runs/public-preview-full_OTA-01/run/reference/report.json`.
To reproduce pre-layout/post-layout calibration and the reference acceptance
regressions, run:

```bash
uv run --locked pytest -m acceptance_eda \
  tests/integration/test_full_ota.py
```

The tests create fresh temporary output directories. Reference layouts and
results are available for reproduction and are excluded from standard solver
inputs.

## Source and License

Adapted from the [`two_stage_OTA_layout` circuit](https://github.com/IHP-GmbH/IHP-AnalogAcademy/blob/133ecf657572e021b5921b5a1b7693abfb209623/modules/module_1_bandgap_reference/part_3_layout/OTA_layout/full_OTA/schematic_mod/two_stage_OTA_layout.sch).

Case materials: [Apache-2.0](../../LICENSE). PDK, model and tool licenses
apply to their respective materials.
