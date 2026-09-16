# Dynamic Comparator

## Overview

`DIFF_COMPARATOR` is a clocked dynamic differential comparator with complementary
outputs. The maintained circuit contains 13 MOS devices and two explicit taps;
the public interface is `vdd`, `gnd`, `V+`, `V-`, `clk`, `out-`, `out+`, and
`vbias` in the order declared by [case.toml](case.toml).

Reference validation covers clocked decisions at 1.2 V and 27 °C across the four
differential-input settings in [problem.md](problem.md).

## Files

| File | Purpose |
|---|---|
| [problem.md](problem.md) | Solver objective, interface, physical requirements, operating conditions, and scoring |
| [case.toml](case.toml) | Single case configuration, input digests, toolchain, constraints, and evaluation plan |
| [materials/circuit.cdl](materials/circuit.cdl) | Authoritative LVS netlist |
| [materials/circuit.spice](materials/circuit.spice) | Pre-layout simulator netlist |
| [materials/testbench.spice](materials/testbench.spice) | Clock stimulus and measurements |
| [Collection LICENSE](../../LICENSE) | Collection distribution terms; excluded from solver inputs |
| [reference/DIFF_COMPARATOR.gds](reference/DIFF_COMPARATOR.gds) | Passing feasibility witness, excluded from standard solver inputs |

## Reference Results

The reference GDS passes artifact, DRC, strict named-port LVS, functional
geometry, candidate-derived RC extraction, and post-layout simulation. The
table reports the pre-layout simulator netlist and the extracted reference after
layout; performance values are worst-case over the four differential-input
settings.

| Metric | Unit | Pre-layout | Post-layout |
|---|---|---:|---:|
| Functional area | µm² | — | 1,662.396 |
| Task score (`layout-v1`) | points / 100 | — | 100 |
| Worst decision delay | ns | 1.872 | 2.542 |
| Minimum decision margin | V | 1.199971 | 1.198178 |
| Maximum average supply power | µW | 58.152 | 64.153 |

The post-layout values satisfy every individual cycle and operating-point limit
in [problem.md](problem.md#electrical-requirements-and-scoring). The extracted
RC model uses a compact-device body boundary with ideal model rails; explicit
taps are still checked by LVS. Well/substrate sheet resistance, body coupling,
and noise are outside this qualification scope. The finite-source-tap versus
ideal-body calibration changes pre-layout delay by at most 8.4 × 10⁻¹⁴ s
and average supply power by at most 1.85 × 10⁻⁹ W; margin is unchanged at printed
precision.

The `layout-v1` scoring boundaries are published in
[problem.md](problem.md#electrical-requirements-and-scoring). Response zero
anchors describe loss of useful response; bias and supply anchors define the
outer grading ranges around the intended operating point and budget. These
are explicit grading choices, with the acceptance limits checked separately.
The fixed absolute area target is a feasible envelope demonstrated by the
reference layout, rather than a ratio to the reference or a claim of optimality.

The regression checks acceptance, waveform measurements, input rejection and
permitted equivalent transformations. Common evaluator tests verify area utility
against independently chosen synthetic values. Input consistency and actual
reference acceptance support this case’s `qualified` status. A separate area
variant is not required for each case.

Coefficient 6 reflects clocked input sensing and regenerative decision stages,
whose interconnect parasitics affect loaded decision delay and margin.

## Reproduce

These operator commands require the installed `ICLayout-Bench-Private` package.
Run preparation from the Public checkout; run any `tests/integration/` commands
from the Private checkout using that environment.

Prepare the image and PDK resources using the shared
[tools guide](../../../../../docs/tools.md#manual-tools). Run from the repository
root and choose a fresh output directory for each reproduction:

```bash
python -m layout_eval.preview prepare \
  --case comparator \
  --output build/runs/public-preview-comparator-01/prepared \
  --image iclayout-bench-tools:local
python -m layout_eval.preview run \
  --prepared build/runs/public-preview-comparator-01/prepared \
  --output build/runs/public-preview-comparator-01/run
```

These commands generate the reference evaluation report at
`build/runs/public-preview-comparator-01/run/reference/report.json`.
To reproduce pre-layout/post-layout calibration and the reference acceptance
regressions, run:

```bash
python -m pytest -m acceptance_eda \
  tests/integration/test_comparator.py
```

The tests create fresh temporary output directories. Reference layouts and
results are available for reproduction and are excluded from standard solver
inputs.

## Source and License

Adapted from the [`DIFF_COMPARATOR` circuit](https://github.com/IHP-GmbH/IHP-AnalogAcademy/tree/133ecf657572e021b5921b5a1b7693abfb209623/modules/module_3_8_bit_SAR_ADC/part_5_analog_layout/comparator).

Case materials: [Apache-2.0](../../LICENSE). PDK, model and tool licenses
apply to their respective materials.
