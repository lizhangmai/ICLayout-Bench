# Differential Two-Stage Miller Amplifier Without CMFB

## Overview

Fully differential NMOS-input two-stage Miller amplifier without CMFB. Ten physical MOS retain both PMOS first-stage current sources, both PMOS common-source output drivers, NMOS reference/tail/output sinks, and both series R/C Miller branches. VBL and the 20 uA reference source are external apparatus.

1.2 V, 27 C, TT LV MOS and typical passives; inputs have 0.6 V common mode, VBL=0.7087 V and 20 uA flows from VDD into ref. Each output has 10 pF to ground. The fixed binding uses 30 kohm and 0.4 pF per Miller branch, represented by native rhigh/MIM. Open AC drives +0.5/-0.5 V at 1 Hz–1 GHz, 200 points/decade, with no DC or AC common-mode feedback. The separate closed test uses external differential feedback vp=0.6+(signal-voutp+voutn)/2 and vm=0.6-(signal-voutp+voutn)/2. It fixes input common mode only; it neither senses nor servos output common mode. A 10 mV signal pulse starts at 2 us with 100 ns edges and 8 us high width. Maximum transient step is 1 ns through 20 us. Report 8–10 and 18–20 us windows. Closed and open DC differential offsets may differ because one fixture closes differential feedback; their input common mode and external bias are identical.

Coefficient 6 covers the compensated differential feedback experiment. No CMFB is added. Miller capacitors are open at DC and provide no DC common-mode feedback. A large parasitic-induced common-mode shift and reduced differential response are continuous quality losses. These finite-window measurements do not certify robust biasing, settling, phase margin or useful product gain. No numerical node shunt is used.

## Files

- [Schematic](materials/schematic.svg): digest-bound main-sheet overview; hierarchical device banks remain expandable in the editable source project. This presentation asset is excluded from solver inputs.

- [Task contract](problem.md), [configuration](case.toml), [physical circuit](materials/circuit.cdl), [simulation circuit](materials/circuit.spice).
- [Main observations](materials/testbench.spice) and [reference GDS](reference/amp_029_two_stage_miller_comp.gds).

## Reference Results

Native DRC (no waivers), named-interface LVS, functional geometry and candidate-derived distributed RC all pass. Independent compact-device graph audits match source, native topology and RC devices, including every physical passive. Raw exports independently reproduce the declared measurements.

Reference score: **16.70369076**; functional area **26031.180600 um2**, analytical area anchor **2278.38 um2**, coefficient **6**. The reference is a feasible implementation, not the electrical normalization baseline.

Ranges below cover the explicitly declared conditions of each metric; they are not substituted for condition-by-condition scoring. Startup metrics use the separate ramp/resistive-load experiment. DC regulation slopes use ascending sweeps.

| Metric | Unit | Pre-layout | Post-layout |
|---|---|---|---|
| output_cm_v | V | 0.538381222 … 0.538381223 | 1.10484265 … 1.10487361 |
| offset_v | V | -3.47988305e-11 … 2.31592523e-12 | 0.00191119393 … 0.00315425696 |
| power_w | W | 0.000215438689 … 0.000215438689 | 0.000230455207 … 0.000230455836 |
| gain_db | dB | 50.46528 | -3.765136 |
| gain_10khz_db | dB | 50.44357 | -3.765148 |
| late_error_v | V | 2.988441e-05 | 0.004135228 |
| return_error_v | V | 9.457481e-13 | 0.001911192 |
| ripple_v | V | 1.22049e-11 | 4.834892e-10 |
| fixture_cm_max | V | 3.061617e-17 | 3.061617e-17 |
| high_v | V | 0.009970116 | 0.005864772 |
| low_v | V | -8.658507e-13 | 0.001911192 |
| cm_min_v | V | 0.5383812 | 1.104743 |
| cm_max_v | V | 0.5383859 | 1.104848 |
| kcl_a | A | 8.31501751e-16 … 9.41250116e-16 | 4.01649435e-10 … 5.50080008e-10 |

The reference exhibits genuine common-mode sensitivity and differential gain degradation: nominal source output common mode is 0.538381 V, candidate 1.104874 V in open AC. Changing source VBL by -/+0.1 mV moves common mode to 0.304902/0.786737 V. Both low/high output initial guesses converge to the same nominal solution; tightened tolerances and doubled AC sampling retain the observed gain. A half transient step changes candidate late tracking error by about 9 nV. The output PMOS drivers approach their supply rail; the low differential gain and closed-response attenuation remain valid finite observations, not evidence of robust common-mode control. The series capacitors do not provide a DC feedback path.

## Reproduce

From the Bench root, use the existing environment and [tool preparation](../../../../../docs/tools.md). These commands generate disposable reports; choose fresh output directories on rerun.

```bash
uv run --locked python -m benchmarking.engine.preview prepare --case amp_029_two_stage_miller_comp --image iclayout-bench-tools:ngspice45 --output build/runs/amp_029_two_stage_miller_comp-prepared
uv run --locked python -m benchmarking.engine.cli evaluate build/runs/amp_029_two_stage_miller_comp-prepared/case/case.toml tasks/ihp-sg13g2/analog-db/cases/amp_029_two_stage_miller_comp/reference/amp_029_two_stage_miller_comp.gds --output build/runs/amp_029_two_stage_miller_comp-evaluation
```

The full evaluation independently executes source baselines with the same conditions. It needs neither Designs nor Private. Native DRC/LVS, distributed RC extraction, input digests and all declared observations are required; normal simulator exit alone is insufficient.

## Source and License

Derived from [MacAnalog/spicexplorer-release, fixed commit 263d0322f8900dc331536fbbe6c0e804514fc454](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_029_two_stage_miller_comp); retain the [collection license and component terms](../../LICENSE).
