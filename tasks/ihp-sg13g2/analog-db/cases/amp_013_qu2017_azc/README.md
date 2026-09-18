# Qu AZC Three-Stage Amplifier

## Overview

XM9/XM10 form the PMOS input pair with their bodies tied to the common source net019. XM14–XM17 form the active NMOS load around DM_2/net063; XM4/XM5 convert this to net050. XM11 drives net094 and XM12 with the XM6/XM7 mirror drives net057. XM23/XM24 drive net049; XM13/XM18 drive VOUT. The active compensation retains C0 (net063–VOUT), C1 (net051–vss), C2 (net043–vss), both resistors from net078 to net077/net082, and both resistors from net057 to net051/net043. The entire bias tree and all body relationships remain.

The integer-micrometre MOS dimensions are unchanged. Every resistor uses native rhigh segments of at most about 250 kOhm; every larger capacitor uses parallel native cap_cmim units of at most about 4 pF. Body taps have finite native models in both source and extracted circuits.

## Files

- [Schematic](materials/schematic.svg): digest-bound main-sheet overview; hierarchical device banks remain expandable in the editable source project. This presentation asset is excluded from solver inputs.

- [Problem](problem.md): interface, conditions, observations and scoring contract.
- [Configuration](case.toml): input digests and executable qualification plan.
- [Physical netlist](materials/circuit.cdl) and [simulation netlist](materials/circuit.spice): matching physical core.
- [Transient/closed-loop deck](materials/testbench.spice) and [balanced differential AC deck](materials/ac.spice).
- [Reference GDS](reference/amp_013_qu2017_azc.gds): independent physical witness.

Only the problem and four circuit/testbench materials enter solver inputs. Reference geometry, this README and authoring code are excluded. Public preparation and evaluation require neither Designs nor Private. Collection LICENSE/NOTICE accompany material distributions separately.

## Reference Results

Native main and maximal DRC pass without waivers; named-interface LVS, functional geometry, GDS-driven distributed RC extraction, independent source simulation and all declared post-layout jobs pass. The [ngspice 45 tool setup](../../../../../docs/tools.md#ngspice-45) uses pinned PDK resources. These are development-rule checks, not tape-out/density signoff. Independent audits verify compact-device connections/parameters and recompute measurements from raw waveforms.

Reference layout-v2 score **27.00336559**, E **1.08768964**, Q **0.06703951**; functional area **120513 um2**, compact-area anchor **8079.11 um2**, coefficient **8**. The problem documents the device/passive envelope and routing allowances and the coefficient rationale. Electrical scores continuously compare the independently simulated source under identical conditions; upstream product targets are not hard gates.

Ordered ports: `vss vdd vinn vinp vout vb1`.

TT MOS, typical MIM/high-poly, 27 C, 1.5 V supply, 0.3 V input reference, 10 pF output load. The external current sink is i0 vb1 vss 1e-06. A direct unity follower receives a 100 mV step at 2 us with 100 ns edges and 8 us high width; falling starts at 10.1 us and completes at 10.2 us. Observe 0–20 us with 0.5 ns maximum step. Report high-window statistics at 8–10 us and return-window statistics at 18–20 us, not a settling time. The rail is adapted from the authored 1.8 V analysis to the actual IHP LV binding; no transistor sizing campaign is performed.

The transient deck directly connects vinn to vout. The frequency deck closes DC feedback through 1 TH, shunts its remote end by 1 F and injects +0.5/−0.5 V AC at the inputs. This isolates the DC feedback at every measured AC frequency. Residual AC common mode and DC feedback mismatch must each be at most 1 uV; open gain is never inferred from a nearly zero closed-loop input error.

The numerical shunt is an explicit `rshunt` resistance at every analog node in both source and candidate, retained across DC, AC and transient analysis. Its tenfold-resistance control is part of the sensitivity checks.

Condition 0: declared step/disturbance transient.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | ---: | ---: |
| `bias_v` | V | 1.106408136 | 1.106317992 |
| `closed_gain_10khz_db` | dB | -0.0006658398 | -0.000693029 |
| `high_v` | V | 0.3938931706 | 0.3961631505 |
| `late_error_v` | V | 0.02909861622 | 0.02361496066 |
| `low_v` | V | 0.295071928 | 0.2961545488 |
| `mean_power_w` | W | 0.0003398277773 | 0.0002468372035 |
| `output_max_v` | V | 0.4332952726 | 0.4244492702 |
| `output_min_v` | V | 0.2366318589 | 0.2394486012 |
| `output_v` | V | 0.2992326076 | 0.2990329575 |
| `power_w` | W | 7.228702552e-05 | 7.024828141e-05 |
| `return_error_v` | V | 0.02576292792 | 0.02187625446 |
| `return_ripple_v` | V | 0.09314135562 | 0.08328253822 |
| `ripple_v` | V | 0.1068905198 | 0.09108766769 |

Condition 1: balanced differential AC.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | ---: | ---: |
| `dc_feedback_error_v` | V | 0 | 5.551115123e-17 |
| `fixture_cm_max` | V | 1.209647589e-10 | 8.971373713e-11 |
| `gain_10khz_db` | dB | 51.5633 | 51.42548 |
| `gain_db` | dB | 79.63834 | 79.08087 |

25 authored MOS cards expand to 152 MOS, three native MIM units and five high-poly segments.

Both source and extracted reference show sustained finite-window ripple. Halving the 0.5 ns maximum step changes source means/errors by at most 112 uV and candidate means/errors by at most 60 uV. Peak-to-peak changes stay below 44 uV. No settling time or stable closed-loop claim is made.

Doubling frequency samples from 200 to 400 per decade leaves the reported AC observations unchanged at displayed precision. The explicit numerical shunt and sparse-solver settings are declared above and used identically for source and candidate.  Every differential fixture checks actual unit differential drive, residual common-mode excitation and DC feedback; raw audits also compare isolated-fixture and direct-fixture DC points. AC gain is the linearization at that point, not proof of transient stability. No loop-return ratio, phase margin or settling time is claimed.

Transient starts from the DC solution, not a supply ramp. Means use full-precision cumulative integration with interpolated exact endpoints; extrema include interpolated endpoints. Incomplete windows and nonfinite traces are invalid. Sensitivity and independent graph/waveform audit commands are maintained with the development recipe; the static evaluation below reproduces every table entry and the score.

## Reproduce

From the Bench root, use the existing project environment and the [tool guide](../../../../../docs/tools.md). These commands generate disposable reader-local reports with input, candidate, resource and tool identities; choose fresh output directories on rerun.

```bash
uv run --locked python -m benchmarking.engine.preview prepare \
  --case amp_013_qu2017_azc --image iclayout-bench-tools:ngspice45 \
  --output build/runs/amp_013_qu2017_azc-prepared
uv run --locked python -m benchmarking.engine.cli evaluate \
  build/runs/amp_013_qu2017_azc-prepared/case/case.toml \
  tasks/ihp-sg13g2/analog-db/cases/amp_013_qu2017_azc/reference/amp_013_qu2017_azc.gds \
  --output build/runs/amp_013_qu2017_azc-reference
```

## Source and License

This case derives from [MacAnalog/spicexplorer-release `amp_013_qu2017_azc`](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_013_qu2017_azc) at fixed commit `263d0322f8900dc331536fbbe6c0e804514fc454`; see [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE) for PolyForm Noncommercial and applicable component terms. Qu/Yan preserve AnalogGym BSD-3-Clause attribution. The framework MIT license does not relicense circuit materials.
