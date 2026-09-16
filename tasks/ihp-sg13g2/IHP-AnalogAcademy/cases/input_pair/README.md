# PMOS Differential Input Pair

## Overview

`input_common_centroid` is a matched PMOS differential input pair with two
active devices, four dummy devices, and an explicit n-well tap. The maintained
interface has six ports: `v-`, `v+`, `vdd`, `dn3`, `dn4`, and `tail`, in the
order declared by [case.toml](case.toml).

Qualification covers DC bias and differential AC response at 1.2 V and 27 °C,
with a 20 µA tail current and 50 kΩ drain loads as defined in
[problem.md](problem.md).

## Files

| File | Purpose |
|---|---|
| [problem.md](problem.md) | Solver objective, interface, physical requirements, operating conditions, and scoring |
| [case.toml](case.toml) | Single case configuration, input digests, toolchain, constraints, and evaluation plan |
| [materials/circuit.cdl](materials/circuit.cdl) | Authoritative LVS netlist |
| [materials/circuit.spice](materials/circuit.spice) | Pre-layout simulator netlist |
| [materials/testbench.spice](materials/testbench.spice) | Bias, load, AC sweep, and measurements |
| [Collection LICENSE](../../LICENSE) | License for the declared circuit materials |
| [reference/input_common_centroid.gds](reference/input_common_centroid.gds) | Qualified feasibility witness, excluded from standard solver inputs |

## Reference Results

The reference GDS passes artifact, DRC, strict named-port LVS, functional
geometry, candidate-derived RC extraction, and post-layout simulation. The table
compares the pre-layout simulator netlist with the extracted reference layout
under the same nominal deck.

| Metric | Unit | Pre-layout | Post-layout |
|---|---|---:|---:|
| Functional area | µm² | — | 1,244.25105 |
| Task score (`layout-v1`) | points / 100 | — | 100 |
| Tail voltage | V | 1.19298 | 1.19313 |
| Common drain voltage | V | 0.499995 | 0.499994 |
| Drain balance | mV | 0.000 | 0.266 |
| Differential gain at 1 MHz | V/V | 2.72776 | 2.72675 |
| Differential gain at 100 MHz | V/V | 3.58466 | 2.42982 |
| Supply power | µW | 24.000 | 24.000 |

All post-layout values satisfy the limits in
[problem.md](problem.md#electrical-requirements-and-scoring). The extracted RC
model uses a compact-device body boundary with ideal model rails; the explicit
tap is still checked by LVS. Well/substrate sheet resistance, body coupling,
and noise are outside this qualification scope. The finite tap versus ideal-rail
calibration preserves the nominal terminal behavior within the regression
tolerance below.

The `layout-v1` scoring boundaries are published in
[problem.md](problem.md#electrical-requirements-and-scoring). Response zero
anchors describe loss of useful response; bias and supply anchors define the
outer grading ranges around the intended operating point and budget. These
are explicit grading choices, with the acceptance limits checked separately.
The fixed absolute area target is a feasible envelope demonstrated by the
reference layout, rather than a ratio to the reference or a claim of optimality.

Coefficient 3 reflects a local differential input block focused on preserving
its paired-device interface and nominal differential response.

### Calibration limits

Replace the finite source tap by a 1e-6 ohm connection and run the same
source deck, models, temperature and nominal values. The recorded finite/ideal
supply powers are 2.400003087359e-5 / 2.39996239543e-5 W; supply power has the
largest relative difference. The comparison normalizes by the larger absolute
finite/ideal value, with a 1e-9 floor. No scored requirement changes.

The following maintainer regression limits are read by the reproduction tests;
they do not add solver requirements.

| Comparison | Unit | Maximum difference |
| --- | --- | --- |
| `relative` | 1 | 1.7e-05 |

## Reproduce

These operator commands require the installed `ICLayout-Bench-Private` package.
Run preparation from the Public checkout; run any `tests/integration/` commands
from the Private checkout using that environment.

Prepare the image and PDK resources using the shared
[tools guide](../../../../../docs/tools.md#manual-tools). Run from the repository
root and choose a fresh output directory for each reproduction:

```bash
python -m layout_eval.preview prepare \
  --case input_pair \
  --output build/runs/public-preview-input_pair-01/prepared \
  --image iclayout-bench-tools:local
python -m layout_eval.preview run \
  --prepared build/runs/public-preview-input_pair-01/prepared \
  --output build/runs/public-preview-input_pair-01/run
```

These commands generate the reference evaluation report at
`build/runs/public-preview-input_pair-01/run/reference/report.json`.
To reproduce pre-layout/post-layout calibration and the reference acceptance
regressions, run:

```bash
python -m pytest -m acceptance_eda \
  tests/integration/test_input_pair_postlayout.py
```

The tests create fresh temporary output directories. Reference layouts and
results are available for reproduction and are excluded from standard solver
inputs.

## Source and License

Adapted from the [`input_common_centroid` circuit](https://github.com/IHP-GmbH/IHP-AnalogAcademy/blob/133ecf657572e021b5921b5a1b7693abfb209623/modules/module_1_bandgap_reference/part_3_layout/OTA_layout/input_pair/schematic_mod/input_common_centroid.sch).

Case materials: [Apache-2.0](../../LICENSE). PDK, model and tool licenses
apply to their respective materials.
