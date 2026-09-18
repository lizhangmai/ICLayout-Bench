# Fan Output CMFB OTA

## Overview

The fixed upstream flattened composite contains a PMOS input pair, folded-cascode first stage, statically straight-through transmission-gate output chopper and common-source second stage. Its own seven-transistor PMOS-input CMFB detects the output mean through two 1 MOhm resistors and drives vb4o, exclusively controlling XM8O/XM9O. The tail and folded PMOS sources retain the separate external core__vb4 bias. Both 6 pF Miller branches and the 1 fF vb4o compensation branch remain. This is the upstream composite itself, not a servo added during Bench integration.

W/L are rounded to 10 nm so centred contacts remain on the 5 nm manufacturing grid. The 0.293 um bias NMOS width is raised to 0.300 um to realize valid native active/contact geometry; no other sizing optimization is applied. The subminimum 1 fF CCM is realized by seven series 7.016 fF MIM units (2.11 um sides), approximately 1.002 fF equivalent. Intermediate nodes and their physical parasitics are retained in both source and candidate models. The branch is never omitted. Every resistor uses native rhigh segments of at most about 250 kOhm; every larger capacitor uses parallel native cap_cmim units of at most about 4 pF. Body taps have finite native models in both source and extracted circuits.

## Files

- [Schematic](materials/schematic.svg): digest-bound main-sheet overview; hierarchical device banks remain expandable in the editable source project. This presentation asset is excluded from solver inputs.

- [Problem](problem.md): interface, conditions, observations and scoring contract.
- [Configuration](case.toml): input digests and executable qualification plan.
- [Physical netlist](materials/circuit.cdl) and [simulation netlist](materials/circuit.spice): matching physical core.
- [Transient/closed-loop deck](materials/testbench.spice) and [balanced differential AC deck](materials/ac.spice).
- [Reference GDS](reference/amp_034_fan_chopper_cmfb.gds): independent physical witness.

Only the problem and four circuit/testbench materials enter solver inputs. Reference geometry, this README and authoring code are excluded. Public preparation and evaluation require neither Designs nor Private. Collection LICENSE/NOTICE accompany material distributions separately.

## Reference Results

Native main and maximal DRC pass without waivers; named-interface LVS, functional geometry, GDS-driven distributed RC extraction, independent source simulation and all declared post-layout jobs pass. The [ngspice 45 tool setup](../../../../../docs/tools.md#ngspice-45) uses pinned PDK resources. These are development-rule checks, not tape-out/density signoff. Independent audits verify compact-device connections/parameters and recompute measurements from raw waveforms.

Reference layout-v2 score **31.16763097**, E **0.83241270**, Q **0.11669947**; functional area **177479 um2**, compact-area anchor **20711.65 um2**, coefficient **8**. The problem documents the device/passive envelope and routing allowances and the coefficient rationale. Electrical scores continuously compare the independently simulated source under identical conditions; upstream product targets are not hard gates.

Ordered ports: `vinp vinn voutp voutn vdd vss core__vb1 core__vb2 core__vb3 core__vb4 vref_cm core__out1_p core__out1_n vb4o`.

TT MOS, typical MIM/high-poly, 27 C, 1.2 V supply, 0.6 V input common mode, 10 pF on each output. The external voltage sources are vb1_core core__vb1 vss dc 0.3983759766; vb2_core core__vb2 vss dc 0.65; vb3_core core__vb3 vss dc 0.45; vb4_core core__vb4 vss dc 0.55; vrefcm vref_cm vss dc 0.5. Both the no-disturbance condition and the following combined sequence run for 150 us with a 2 ns maximum step. The differential command rises from 0 to 10 mV at 10 us and returns after 10 us; equal +20 uA currents enter both outputs at 30 us for 2 us. The output reference rises by 25 mV at 50 us for 15 us; input common mode rises by 25 mV at 75 us for 15 us. The stage-1 reference is not an interface of this circuit. All edges are 20 ns. Pulse widths are measured after the rising edge, so falling edges start one edge duration after nominal delay plus width. The unperturbed condition sets every step and kick amplitude to zero. The two CMFB loops, where present, remain connected throughout. Monitor ports are unloaded; their extraction and routing parasitics remain. No external clock is applied: straight-through chopper gates stay tied to their actual rails, and crossed paths stay off.

The external fixture enforces inp = icm + (signal − (outp−outn))/2 and inn = icm − (signal − (outp−outn))/2. It closes only the differential measurement loop; the DUT transistors close common-mode feedback. The frequency deck retains this DC feedback, isolates each feedback branch with 1 TH/1 F low-pass elements and injects +0.5/−0.5 V AC. The actual differential excitation remains 1 V and residual common-mode must be at most 1 uV.

The numerical shunt is an explicit `rshunt` resistance at every analog node in both source and candidate, retained across DC, AC and transient analysis. Its tenfold-resistance control is part of the sensitivity checks.

Condition 0: no-disturbance transient.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | ---: | ---: |
| `closed_gain_10khz_db` | dB | -0.009874496 | -0.007856213 |
| `cm_bias_v` | V | 0.5145191412 | 0.5080466347 |
| `cm_input_cm_v` | V | 0.5145191411 | 0.5080466348 |
| `cm_kick_v` | V | 5.553535409e-11 | 5.389777513e-11 |
| `cm_late_pp_v` | V | 2.227940055e-11 | 7.120193324e-11 |
| `cm_late_v` | V | 0.5145191411 | 0.5080466348 |
| `cm_pre_kick_v` | V | 0.5145191411 | 0.5080466347 |
| `cm_quiet_pp_v` | V | 2.089473039e-11 | 7.344191921e-11 |
| `cm_quiet_v` | V | 0.5145191411 | 0.5080466348 |
| `cm_recovery_error_v` | V | 3.469314745e-12 | 2.772343757e-11 |
| `cm_recovery_v` | V | 0.5145191411 | 0.5080466348 |
| `cm_ref_v` | V | 0.5145191411 | 0.5080466348 |
| `cm_stage_ref_v` | V | 0.5145191411 | 0.5080466348 |
| `dm_bias_v` | V | -2.930988785e-14 | 0.001166088515 |
| `dm_high_error_v` | V | 3.144151606e-15 | 0.001166088512 |
| `dm_return_error_v` | V | 5.43776621e-14 | 0.001166088512 |
| `mean_power_w` | W | 0.0002723656021 | 0.0003138525968 |
| `power_w` | W | 0.0002723656033 | 0.0003138525968 |
| `s1_bias_v` | V | 0.3265125903 | 0.3540688028 |
| `s1_input_cm_v` | V | 0.3265125898 | 0.3540688028 |
| `s1_kick_v` | V | 2.847755365e-11 | 2.61052846e-11 |
| `s1_late_pp_v` | V | 6.617040249e-12 | 4.6639137e-11 |
| `s1_late_v` | V | 0.3265125898 | 0.3540688028 |
| `s1_pre_kick_v` | V | 0.3265125898 | 0.3540688028 |
| `s1_quiet_pp_v` | V | 5.530909064e-12 | 4.644679086e-11 |
| `s1_quiet_v` | V | 0.3265125898 | 0.3540688028 |
| `s1_recovery_error_v` | V | 6.757258884e-13 | 1.352012115e-11 |
| `s1_recovery_v` | V | 0.3265125898 | 0.3540688028 |
| `s1_ref_v` | V | 0.3265125898 | 0.3540688028 |
| `s1_stage_ref_v` | V | 0.3265125898 | 0.3540688028 |

Condition 1: declared step/disturbance transient.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | ---: | ---: |
| `closed_gain_10khz_db` | dB | -0.009874496 | -0.007856213 |
| `cm_bias_v` | V | 0.5145191412 | 0.5080466347 |
| `cm_input_cm_v` | V | 0.5272836532 | 0.5224530964 |
| `cm_kick_v` | V | 0.01438500999 | 0.01463956022 |
| `cm_late_pp_v` | V | 1.10980336e-10 | 2.755851103e-11 |
| `cm_late_v` | V | 0.5145191407 | 0.5080466325 |
| `cm_pre_kick_v` | V | 0.5145191386 | 0.5080466348 |
| `cm_quiet_pp_v` | V | 2.089473039e-11 | 7.344191921e-11 |
| `cm_quiet_v` | V | 0.5145191411 | 0.5080466348 |
| `cm_recovery_error_v` | V | 3.571577302e-09 | 2.509149797e-11 |
| `cm_recovery_v` | V | 0.5145191422 | 0.5080466348 |
| `cm_ref_v` | V | 0.5392353805 | 0.5329327471 |
| `cm_stage_ref_v` | V | 0.5145191406 | 0.5080466323 |
| `dm_bias_v` | V | -2.930988785e-14 | 0.001166088515 |
| `dm_high_error_v` | V | 1.136437024e-05 | 0.001157048143 |
| `dm_return_error_v` | V | 2.474598949e-13 | 0.001166088512 |
| `mean_power_w` | W | 0.0002577955932 | 0.0002981516725 |
| `power_w` | W | 0.0002723656033 | 0.0003138525968 |
| `s1_bias_v` | V | 0.3265125903 | 0.3540688028 |
| `s1_input_cm_v` | V | 0.2120932661 | 0.2641073425 |
| `s1_kick_v` | V | 0.01603275203 | 0.02078775133 |
| `s1_late_pp_v` | V | 8.190970124e-11 | 8.577916155e-12 |
| `s1_late_v` | V | 0.3265125898 | 0.3540688029 |
| `s1_pre_kick_v` | V | 0.3265126154 | 0.3540688028 |
| `s1_quiet_pp_v` | V | 5.530909064e-12 | 4.644679086e-11 |
| `s1_quiet_v` | V | 0.3265125898 | 0.3540688028 |
| `s1_recovery_error_v` | V | 3.57676013e-08 | 1.491071305e-11 |
| `s1_recovery_v` | V | 0.3265125797 | 0.3540688028 |
| `s1_ref_v` | V | 0.3265146463 | 0.3530364695 |
| `s1_stage_ref_v` | V | 0.3265125898 | 0.3540688029 |

Condition 2: balanced differential AC.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | ---: | ---: |
| `dc_feedback_error_v` | V | 0 | 0 |
| `fixture_cm_max` | V | 7.850462293e-17 | 2.023125477e-12 |
| `gain_10khz_db` | dB | 54.20632 | 54.30874 |
| `gain_db` | dB | 58.87927 | 60.86893 |

The physical core contains 30 MOS, eleven native MIM units (including seven series units for the retained 1 fF branch) and eight high-poly segments.

The output common-mode loop follows the +25 mV reference change and recovers from the common-mode current kick in the observed windows. The first-stage mean is monitored but has no separate reference loop in this circuit. Halving the 2 ns maximum step changes the kick excursion by less than 17 uV and window means by less than 1 uV. Reducing numerical leakage tenfold changes output common-mode means by less than 3.5 uV. These measurements describe the declared 150 us experiment, not unconditional stability.

Doubling frequency samples from 200 to 400 per decade leaves the reported AC observations unchanged at displayed precision. The explicit numerical shunt and sparse-solver settings are declared above and used identically for source and candidate.  Every differential fixture checks actual unit differential drive, residual common-mode excitation and DC feedback; raw audits also compare isolated-fixture and direct-fixture DC points. AC gain is the linearization at that point, not proof of transient stability. No loop-return ratio, phase margin or settling time is claimed.

Transient starts from the DC solution, not a supply ramp. Means use full-precision cumulative integration with interpolated exact endpoints; extrema include interpolated endpoints. Incomplete windows and nonfinite traces are invalid. Sensitivity and independent graph/waveform audit commands are maintained with the development recipe; the static evaluation below reproduces every table entry and the score.

## Reproduce

From the Bench root, use the existing project environment and the [tool guide](../../../../../docs/tools.md). These commands generate disposable reader-local reports with input, candidate, resource and tool identities; choose fresh output directories on rerun.

```bash
uv run --locked python -m benchmarking.engine.preview prepare \
  --case amp_034_fan_chopper_cmfb --image iclayout-bench-tools:ngspice45 \
  --output build/runs/amp_034_fan_chopper_cmfb-prepared
uv run --locked python -m benchmarking.engine.cli evaluate \
  build/runs/amp_034_fan_chopper_cmfb-prepared/case/case.toml \
  tasks/ihp-sg13g2/analog-db/cases/amp_034_fan_chopper_cmfb/reference/amp_034_fan_chopper_cmfb.gds \
  --output build/runs/amp_034_fan_chopper_cmfb-reference
```

## Source and License

This case derives from [MacAnalog/spicexplorer-release `amp_034_fan_chopper_cmfb`](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_034_fan_chopper_cmfb) at fixed commit `263d0322f8900dc331536fbbe6c0e804514fc454`; see [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE) for PolyForm Noncommercial and applicable component terms. Qu/Yan preserve AnalogGym BSD-3-Clause attribution. The framework MIT license does not relicense circuit materials.
