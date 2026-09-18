# Fer Two-Stage Miller Amplifier

## Overview

PMOS differential input pair, NMOS mirror load, NMOS common-source second stage and PMOS current-source load, retaining Miller CC and the complete NMOS-to-PMOS bias mirror. The 10 bound MOS expand to 63 physical units; CC is a 36.46 um square native MIM (1.999831 pF).

1.5 V, 27 C, TT LV MOS and typical passives; external 20 uA flows from VDD into ibias. The NMOS diode/mirror drives the PMOS diode: bias/tail/output-load multiplicities are 3:3:17; input-pair multiplicities are 5 each, NMOS load 2 each, and second-stage NMOS 24. The PMOS input bodies remain VDD. vinp is noninverting. The unity follower ties vinn directly to vout. Input is 0.6 V with a +0.2 V pulse at 2 us, 100 ns edges, 8 us high width; falling completes at 10.2 us. The load is 10 pF, maximum transient step 0.5 ns, total window 20 us. High/return statistics use 8–10/18–20 us. Balanced AC uses +0.5/-0.5 V excitation and a 1 TH/1 F DC-feedback isolation network over 1 Hz–1 GHz (200 points/decade). Residual AC common mode and DC feedback mismatch must be at most 1 uV.

Coefficient 6 covers a complete compensated feedback loop with direct-follower recovery. No numerical node shunt is used. No phase margin, unity-gain crossing, noise or settling-time claim is made.

## Files

- [Schematic](materials/schematic.svg): digest-bound main-sheet overview; hierarchical device banks remain expandable in the editable source project. This presentation asset is excluded from solver inputs.

- [Task contract](problem.md), [configuration](case.toml), [physical circuit](materials/circuit.cdl), [simulation circuit](materials/circuit.spice).
- [Main observations](materials/testbench.spice) and [reference GDS](reference/amp_022_fer_two_stage.gds).

## Reference Results

Native DRC (no waivers), named-interface LVS, functional geometry and candidate-derived distributed RC all pass. Independent compact-device graph audits match source, native topology and RC devices, including every physical passive. Raw exports independently reproduce the declared measurements.

Reference score: **42.30426629**; functional area **38602.956000 um2**, analytical area anchor **7022.72 um2**, coefficient **6**. The reference is a feasible implementation, not the electrical normalization baseline.

Ranges below cover the explicitly declared conditions of each metric; they are not substituted for condition-by-condition scoring. Startup metrics use the separate ramp/resistive-load experiment. DC regulation slopes use ascending sweeps.

| Metric | Unit | Pre-layout | Post-layout |
|---|---|---|---|
| output_v | V | 0.599174091 | 0.598748316 |
| power_w | W | 0.000362342856 | 0.000360279185 |
| gain_db | dB | 51.50621 | 51.53177 |
| gain_10khz_db | dB | 51.36271 | 51.38548 |
| closed_gain_10khz_db | dB | -0.01778975 | -0.01766448 |
| late_error_v | V | 0.00116107303 | 0.00158238938 |
| return_error_v | V | 0.000825909215 | 0.00125168432 |
| ripple_v | V | 2.14697149e-11 | 3.54227758e-12 |
| return_ripple_v | V | 7.19433402e-11 | 6.07247586e-12 |
| mean_power_w | W | 0.000358859939 | 0.000356809856 |
| bias_v | V | 0.386757941 | 0.393896291 |
| high_v | V | 0.798838927 | 0.798417611 |
| low_v | V | 0.599174091 | 0.598748316 |
| output_min_v | V | 0.598200494 | 0.597439283 |
| output_max_v | V | 0.800064866 | 0.800016869 |
| fixture_cm_max | V | 7.46190924e-12 | 7.20330361e-12 |
| dc_feedback_error_v | V | 0 | 0 |
| kcl_a | A | 1.0944018e-14 … 1.95838354e-14 | 1.04879755e-14 … 1.16827934e-14 |

Halving maximum transient step from 0.5 to 0.25 ns changes late means/errors by less than 7 pV and average rail power by less than 0.1 pW. Doubling AC sampling reproduces the 1 Hz and 10 kHz gains to floating-point precision. The direct-follower and isolated balanced-AC DC operating points agree within the independently audited 5 uV bound. Window ripple is numerical-scale, not a claimed noise floor.

## Reproduce

From the Bench root, use the existing environment and [tool preparation](../../../../../docs/tools.md). These commands generate disposable reports; choose fresh output directories on rerun.

```bash
uv run --locked python -m benchmarking.engine.preview prepare --case amp_022_fer_two_stage --image iclayout-bench-tools:ngspice45 --output build/runs/amp_022_fer_two_stage-prepared
uv run --locked python -m benchmarking.engine.cli evaluate build/runs/amp_022_fer_two_stage-prepared/case/case.toml tasks/ihp-sg13g2/analog-db/cases/amp_022_fer_two_stage/reference/amp_022_fer_two_stage.gds --output build/runs/amp_022_fer_two_stage-evaluation
```

The full evaluation independently executes source baselines with the same conditions. It needs neither Designs nor Private. Native DRC/LVS, distributed RC extraction, input digests and all declared observations are required; normal simulator exit alone is insufficient.

## Source and License

Derived from [MacAnalog/spicexplorer-release, fixed commit 263d0322f8900dc331536fbbe6c0e804514fc454](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_022_fer_two_stage); retain the [collection license and component terms](../../LICENSE).
