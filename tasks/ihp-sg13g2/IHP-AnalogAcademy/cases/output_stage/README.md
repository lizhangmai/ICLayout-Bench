# CMOS OTA Output Stage

## Overview

`output_stage` is the output stage of a two-stage CMOS operational transconductance
amplifier. `MM5` is the PMOS output current source, `MM9` is its diode-connected
bias replica, and `MM6` is the long-channel NMOS pull-down controlled by `dn4`.
`CC2` provides MIM compensation between `dn4` and `vout`, with explicit tap
devices `RR4` and `RR5`. The maintained interface has five ports: `vdd`, `iout`,
`vout`, `vss`, and `dn4`, in the order declared by [case.toml](case.toml).

Qualification covers DC bias and voltage gain at 1.2 V and 27 °C, with the
input bias and output load defined in [problem.md](problem.md).

## Files

| File | Purpose |
|---|---|
| [problem.md](problem.md) | Solver objective, interface, physical requirements, operating conditions, and scoring |
| [case.toml](case.toml) | Single case configuration, input digests, toolchain, constraints, and evaluation plan |
| [materials/circuit.cdl](materials/circuit.cdl) | Authoritative LVS netlist |
| [materials/circuit.spice](materials/circuit.spice) | Pre-layout simulator netlist |
| [materials/testbench.spice](materials/testbench.spice) | Bias, load, AC sweep, and measurements |
| [Collection LICENSE](../../LICENSE) | License for the declared circuit materials |
| [reference/output_stage.gds](reference/output_stage.gds) | Qualified feasibility witness, excluded from standard solver inputs |

## Reference Results

The reference GDS passes artifact, DRC, strict named-port LVS, functional
geometry, candidate-derived RC extraction, and post-layout simulation. The table
compares the pre-layout simulator netlist with the extracted reference layout
under the same nominal deck.

| Metric | Unit | Pre-layout | Post-layout |
|---|---|---:|---:|
| Functional area | µm² | — | 1,692.1044 |
| Task score (`layout-v1`) | points / 100 | — | 100 |
| Output bias | V | 0.64747 | 0.64657 |
| Output gain at 1 MHz | V/V | 9.5262 | 9.3512 |
| Output gain at 100 MHz | V/V | 1.1224 | 1.0790 |
| Supply power | µW | 48.149 | 48.133 |

All post-layout values satisfy the limits in
[problem.md](problem.md#electrical-requirements-and-scoring). The extracted RC
model uses a compact-device body boundary with ideal model rails; explicit taps
are still checked by LVS. Well/substrate sheet resistance, body coupling, and
noise are outside this qualification scope. The finite tap versus ideal-rail
calibration preserves the nominal terminal behavior within the regression
tolerance below.

The `layout-v1` scoring boundaries are published in
[problem.md](problem.md#electrical-requirements-and-scoring). Response zero
anchors describe loss of useful response; bias and supply anchors define the
outer grading ranges around the intended operating point and budget. These
are explicit grading choices, with the acceptance limits checked separately.
The fixed absolute area target is a feasible envelope demonstrated by the
reference layout, rather than a ratio to the reference or a claim of optimality.

Coefficient 4 reflects a complete compact gain stage with a current-source
bias replica, compensation capacitor and output-load requirements.

### Calibration limits

Replace both finite source taps by 1e-6 ohm connections and run the same
source deck, models, temperature and nominal values. Recorded finite/ideal
output bias is 0.6474679382968 / 0.6474679392507 V; 100 MHz gain is
1.122446 / 1.122463 V/V and has the largest relative difference. Normalize
by the absolute finite-source value, with a 1e-30 floor. No scored requirement changes.

The following maintainer regression limits are read by the reproduction tests;
they do not add solver requirements.

| Comparison | Unit | Maximum difference |
| --- | --- | --- |
| `relative` | 1 | 1.6e-05 |

## Reproduce

These operator commands require the installed `ICLayout-Bench-Private` package.
Run preparation from the Public checkout; run any `tests/integration/` commands
from the Private checkout using that environment.

Prepare the image and PDK resources using the shared
[tools guide](../../../../../docs/tools.md#manual-tools). Run from the repository
root and choose a fresh output directory for each reproduction:

```bash
python -m layout_eval.preview prepare \
  --case output_stage \
  --output build/runs/public-preview-output_stage-01/prepared \
  --image iclayout-bench-tools:local
python -m layout_eval.preview run \
  --prepared build/runs/public-preview-output_stage-01/prepared \
  --output build/runs/public-preview-output_stage-01/run
```

These commands generate the reference evaluation report at
`build/runs/public-preview-output_stage-01/run/reference/report.json`.
To reproduce pre-layout/post-layout calibration and the reference acceptance
regressions, run:

```bash
python -m pytest -m acceptance_eda \
  tests/integration/test_output_stage_postlayout.py
```

The tests create fresh temporary output directories. Reference layouts and
results are available for reproduction and are excluded from standard solver
inputs.

## Source and License

Adapted from the [`output_stage` circuit](https://github.com/IHP-GmbH/IHP-AnalogAcademy/blob/133ecf657572e021b5921b5a1b7693abfb209623/modules/module_1_bandgap_reference/part_3_layout/OTA_layout/output_stage/schematic_mod/output_stage.sch).

Case materials: [Apache-2.0](../../LICENSE). PDK, model and tool licenses
apply to their respective materials.
