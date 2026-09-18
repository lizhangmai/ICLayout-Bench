# Yan AZ Three-Stage Amplifier

## Overview

XM9/XM10 form the PMOS input pair with bodies tied to net019. XM14/XM15 are the cascoded load branches controlled by XM16/XM17 and the net078 resistive network; XM4/XM5 produce net050. XM11/XM22 drive net094, while XM23 and the distinct XM67 mirror branch drive net057. XM13/XM18 drive VOUT. C0 connects net063 to VOUT, C1 shunts net051, and R2 connects net094 to net051; both net078 load resistors remain. AZ denotes the authored active compensation network, not auto-zero clocks.

W/L are rounded to 10 nm for centred contacts on the 5 nm grid. Every resistor uses native rhigh segments of at most about 250 kOhm; every larger capacitor uses parallel native cap_cmim units of at most about 4 pF. Body taps have finite native models in both source and extracted circuits.

## Files

- [Schematic](materials/schematic.svg): digest-bound main-sheet overview; hierarchical device banks remain expandable in the editable source project. This presentation asset is excluded from solver inputs.

- [Problem](problem.md): interface, conditions, observations and scoring contract.
- [Configuration](case.toml): input digests and executable qualification plan.
- [Physical netlist](materials/circuit.cdl) and [simulation netlist](materials/circuit.spice): matching physical core.
- [Transient/closed-loop deck](materials/testbench.spice) and [balanced differential AC deck](materials/ac.spice).
- [Reference GDS](reference/amp_021_yan_az.gds): independent physical witness.

Only the problem and four circuit/testbench materials enter solver inputs. Reference geometry, this README and authoring code are excluded. Public preparation and evaluation require neither Designs nor Private. Collection LICENSE/NOTICE accompany material distributions separately.

## Reference Results

Native main and maximal DRC pass without waivers; named-interface LVS, functional geometry, GDS-driven distributed RC extraction, independent source simulation and all declared post-layout jobs pass. The [ngspice 45 tool setup](../../../../../docs/tools.md#ngspice-45) uses pinned PDK resources. These are development-rule checks, not tape-out/density signoff. Independent audits verify compact-device connections/parameters and recompute measurements from raw waveforms.

Reference layout-v2 score **42.82186266**, E **1.00409831**, Q **0.18262275**; functional area **131718 um2**, compact-area anchor **24054.76 um2**, coefficient **8**. The problem documents the device/passive envelope and routing allowances and the coefficient rationale. Electrical scores continuously compare the independently simulated source under identical conditions; upstream product targets are not hard gates.

Ordered ports: `vss vdd vinn vinp vout vb1`.

TT MOS, typical MIM/high-poly, 27 C, 1.5 V supply, 0.3 V input reference, 10 pF output load. The external current sink is i0 vb1 vss 1.0981e-05. A direct unity follower receives a 100 mV step at 2 us with 100 ns edges and 8 us high width; falling starts at 10.1 us and completes at 10.2 us. Observe 0–20 us with 0.5 ns maximum step. Report high-window statistics at 8–10 us and return-window statistics at 18–20 us, not a settling time. The rail is adapted from the authored 1.8 V analysis to the actual IHP LV binding; no transistor sizing campaign is performed.

The transient deck directly connects vinn to vout. The frequency deck closes DC feedback through 1 TH, shunts its remote end by 1 F and injects +0.5/−0.5 V AC at the inputs. This isolates the DC feedback at every measured AC frequency. Residual AC common mode and DC feedback mismatch must each be at most 1 uV; open gain is never inferred from a nearly zero closed-loop input error.

The numerical shunt is an explicit `rshunt` resistance at every analog node in both source and candidate, retained across DC, AC and transient analysis. Its tenfold-resistance control is part of the sensitivity checks.

Condition 0: declared step/disturbance transient.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | ---: | ---: |
| `bias_v` | V | 0.5139155539 | 0.513374977 |
| `closed_gain_10khz_db` | dB | -0.04960392 | -0.04993277 |
| `high_v` | V | 0.4152886011 | 0.3647351514 |
| `late_error_v` | V | 0.2624499467 | 0.2520424674 |
| `low_v` | V | 0.2664402564 | 0.2844000465 |
| `mean_power_w` | W | 0.0001372918891 | 0.0001348210259 |
| `output_max_v` | V | 0.8532488151 | 0.9132695697 |
| `output_min_v` | V | 0.01787331298 | 0.01673047109 |
| `output_v` | V | 0.3070477298 | 0.3069969396 |
| `power_w` | W | 9.301193268e-05 | 9.269604966e-05 |
| `return_error_v` | V | 0.1945447625 | 0.1946114715 |
| `return_ripple_v` | V | 0.6096700791 | 0.6120650998 |
| `ripple_v` | V | 0.8149665376 | 0.7957914947 |

Condition 1: balanced differential AC.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | ---: | ---: |
| `dc_feedback_error_v` | V | 0 | 0 |
| `fixture_cm_max` | V | 4.259671464e-08 | 3.486031495e-08 |
| `gain_10khz_db` | dB | 56.77529 | 56.65673 |
| `gain_db` | dB | 130.613 | 130.3049 |

21 authored MOS cards expand to 100 MOS, four native MIM units and ten high-poly segments.

Both source and extracted reference oscillate. Halving the 0.5 ns maximum step moves the source high-window mean by 58.2 mV and mean absolute error by 8.38 mV because the short window samples a different oscillation phase. The source peak-to-peak range changes by only 0.502 mV; recomputing the paired score changes it by 0.015 point against the final public run. The mean is a diagnostic, not a settled value or a scored tracking metric. Absolute error and full peak-to-peak range are scored. No settling time or stable closed-loop claim is made.

Doubling frequency samples from 200 to 400 per decade leaves the reported AC observations unchanged at displayed precision. The explicit numerical shunt and sparse-solver settings are declared above and used identically for source and candidate.  Every differential fixture checks actual unit differential drive, residual common-mode excitation and DC feedback; raw audits also compare isolated-fixture and direct-fixture DC points. AC gain is the linearization at that point, not proof of transient stability. No loop-return ratio, phase margin or settling time is claimed.

Transient starts from the DC solution, not a supply ramp. Means use full-precision cumulative integration with interpolated exact endpoints; extrema include interpolated endpoints. Incomplete windows and nonfinite traces are invalid. Sensitivity and independent graph/waveform audit commands are maintained with the development recipe; the static evaluation below reproduces every table entry and the score.

## Reproduce

From the Bench root, use the existing project environment and the [tool guide](../../../../../docs/tools.md). These commands generate disposable reader-local reports with input, candidate, resource and tool identities; choose fresh output directories on rerun.

```bash
uv run --locked python -m benchmarking.engine.preview prepare \
  --case amp_021_yan_az --image iclayout-bench-tools:ngspice45 \
  --output build/runs/amp_021_yan_az-prepared
uv run --locked python -m benchmarking.engine.cli evaluate \
  build/runs/amp_021_yan_az-prepared/case/case.toml \
  tasks/ihp-sg13g2/analog-db/cases/amp_021_yan_az/reference/amp_021_yan_az.gds \
  --output build/runs/amp_021_yan_az-reference
```

## Source and License

This case derives from [MacAnalog/spicexplorer-release `amp_021_yan_az`](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_021_yan_az) at fixed commit `263d0322f8900dc331536fbbe6c0e804514fc454`; see [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE) for PolyForm Noncommercial and applicable component terms. Qu/Yan preserve AnalogGym BSD-3-Clause attribution. The framework MIT license does not relicense circuit materials.
