# Fan Dual CMFB OTA

## Overview

The independently frozen flattened composite contains the PMOS input/folded-cascode first stage, static straight-through output chopper and common-source second stage. One seven-transistor CMFB detects the output mean through two 1 MOhm resistors and drives XM8O/XM9O on vb4o. A second seven-transistor CMFB detects stg1_p/stg1_n through two 50 MOhm resistors and drives vb4_ctl, controlling the first-stage tail and folded PMOS sources. The 50 MOhm override, distinct 0.3265 V stage reference, 100 pF inner-loop compensation and both 6 pF Miller capacitors remain. Neither loop is replaced or independently opened to infer joint stability.

W/L are rounded to 10 nm so centred contacts remain on the 5 nm manufacturing grid. The 0.293 um bias NMOS width is raised to 0.300 um to realize valid native active/contact geometry; no other sizing optimization is applied. Every resistor uses native rhigh segments of at most about 250 kOhm; every larger capacitor uses parallel native cap_cmim units of at most about 4 pF. Body taps have finite native models in both source and extracted circuits.

## Files

- [Schematic](materials/schematic.svg): digest-bound main-sheet overview; hierarchical device banks remain expandable in the editable source project. This presentation asset is excluded from solver inputs.

- [Problem](problem.md): interface, conditions, observations and scoring contract.
- [Configuration](case.toml): input digests and executable qualification plan.
- [Physical netlist](materials/circuit.cdl) and [simulation netlist](materials/circuit.spice): matching physical core.
- [Transient/closed-loop deck](materials/testbench.spice) and [balanced differential AC deck](materials/ac.spice).
- [Reference GDS](reference/amp_035_fan_chopper_cmfb_dual.gds): independent physical witness.

Only the problem and four circuit/testbench materials enter solver inputs. Reference geometry, this README and authoring code are excluded. Public preparation and evaluation require neither Designs nor Private. Collection LICENSE/NOTICE accompany material distributions separately.

## Reference Results

Native main and maximal DRC pass without waivers; named-interface LVS, functional geometry, GDS-driven distributed RC extraction, independent source simulation and all declared post-layout jobs pass. The [ngspice 45 tool setup](../../../../../docs/tools.md#ngspice-45) uses pinned PDK resources. These are development-rule checks, not tape-out/density signoff. Independent audits verify compact-device connections/parameters and recompute measurements from raw waveforms.

Reference layout-v2 score **21.75337721**, E **0.81273268**, Q **0.05822449**; functional area **6.20815e+06 um2**, compact-area anchor **361466.3 um2**, coefficient **9**. The problem documents the device/passive envelope and routing allowances and the coefficient rationale. Electrical scores continuously compare the independently simulated source under identical conditions; upstream product targets are not hard gates.

Ordered ports: `vinp vinn voutp voutn vdd vss core__vb1 core__vb2 core__vb3 vref_out vref_s1 stg1_p stg1_n vb4o vb4_ctl`.

TT MOS, typical MIM/high-poly, 27 C, 1.2 V supply, 0.6 V input common mode, 10 pF on each output. The external voltage sources are vb1_core core__vb1 vss dc 0.3983759766; vb2_core core__vb2 vss dc 0.65; vb3_core core__vb3 vss dc 0.45; vrefout vref_out vss dc 0.5; vrefs1 vref_s1 vss dc 0.3265. Both the no-disturbance condition and the following combined sequence run for 150 us with a 2 ns maximum step. The differential command rises from 0 to 10 mV at 10 us and returns after 10 us; equal +20 uA currents enter both outputs at 30 us for 2 us. The output reference rises by 25 mV at 50 us for 15 us; input common mode rises by 25 mV at 75 us for 15 us. The stage-1 reference rises by 10 mV at 110 us for 15 us. All edges are 20 ns. Pulse widths are measured after the rising edge, so falling edges start one edge duration after nominal delay plus width. The unperturbed condition sets every step and kick amplitude to zero. The two CMFB loops, where present, remain connected throughout. Monitor ports are unloaded; their extraction and routing parasitics remain. No external clock is applied: straight-through chopper gates stay tied to their actual rails, and crossed paths stay off.

The external fixture enforces inp = icm + (signal − (outp−outn))/2 and inn = icm − (signal − (outp−outn))/2. It closes only the differential measurement loop; the DUT transistors close common-mode feedback. The frequency deck retains this DC feedback, isolates each feedback branch with 1 TH/1 F low-pass elements and injects +0.5/−0.5 V AC. The actual differential excitation remains 1 V and residual common-mode must be at most 1 uV.

The numerical shunt is an explicit `rshunt` resistance at every analog node in both source and candidate, retained across DC, AC and transient analysis. Its tenfold-resistance control is part of the sensitivity checks. The 100 TOhm nominal and 1 POhm control use `pivtol=1e-18`, below either shunt conductance, to permit sparse-matrix pivots on otherwise floating extracted nodes. See the [ngspice options reference](https://ngspice.sourceforge.io/docs/ngspice-45-manual.pdf). This changes numerical conditioning without altering the DUT or adding a feedback path.

Condition 0: no-disturbance transient.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | ---: | ---: |
| `closed_gain_10khz_db` | dB | -0.008363524 | -0.008937515 |
| `cm_bias_v` | V | 0.5124550434 | 0.5098427407 |
| `cm_input_cm_v` | V | 0.5223745686 | 0.509842743 |
| `cm_kick_v` | V | 4.798649196e-06 | 5.465364827e-10 |
| `cm_late_pp_v` | V | 0.002818616922 | 3.240721358e-09 |
| `cm_late_v` | V | 0.02422180974 | 0.5098427502 |
| `cm_pre_kick_v` | V | 0.5124554955 | 0.5098427371 |
| `cm_quiet_pp_v` | V | 4.771258055e-08 | 8.0451934e-10 |
| `cm_quiet_v` | V | 0.5124549598 | 0.5098427401 |
| `cm_recovery_error_v` | V | 3.519040434e-05 | 1.606224689e-09 |
| `cm_recovery_v` | V | 0.5124906859 | 0.5098427355 |
| `cm_ref_v` | V | 0.5120268894 | 0.5098427364 |
| `cm_stage_ref_v` | V | 0.566685214 | 0.5098427568 |
| `dm_bias_v` | V | -4.265476861e-13 | 0.00171653418 |
| `dm_high_error_v` | V | 1.782649028e-13 | 0.001716534285 |
| `dm_return_error_v` | V | 1.225932966e-13 | 0.001716534351 |
| `mean_power_w` | W | 0.0003949871582 | 0.0002971693555 |
| `power_w` | W | 0.000328315467 | 0.0002971693942 |
| `s1_bias_v` | V | 0.3417966386 | 0.343932505 |
| `s1_input_cm_v` | V | 0.2581049352 | 0.3439324937 |
| `s1_kick_v` | V | 3.240564107e-05 | 2.585091335e-09 |
| `s1_late_pp_v` | V | 0.0947987116 | 1.508221448e-08 |
| `s1_late_v` | V | 1.064845563 | 0.3439324572 |
| `s1_pre_kick_v` | V | 0.3417923834 | 0.3439325211 |
| `s1_quiet_pp_v` | V | 3.612232494e-07 | 2.837214463e-09 |
| `s1_quiet_v` | V | 0.3417972243 | 0.3439325068 |
| `s1_recovery_error_v` | V | 0.0002209070423 | 8.141093699e-09 |
| `s1_recovery_v` | V | 0.3415714764 | 0.3439325292 |
| `s1_ref_v` | V | 0.3444762083 | 0.3439325252 |
| `s1_stage_ref_v` | V | 0.001948147066 | 0.3439324276 |

Condition 1: declared step/disturbance transient.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | ---: | ---: |
| `closed_gain_10khz_db` | dB | -0.008363524 | -0.008937515 |
| `cm_bias_v` | V | 0.5124550434 | 0.5098427407 |
| `cm_input_cm_v` | V | 0.02984540186 | 0.5205785042 |
| `cm_kick_v` | V | 0.01239092289 | 0.01698102772 |
| `cm_late_pp_v` | V | 0.0002234986411 | 0.004652953328 |
| `cm_late_v` | V | 0.02282106359 | 0.4708657071 |
| `cm_pre_kick_v` | V | 0.5124625481 | 0.5098771239 |
| `cm_quiet_pp_v` | V | 4.771258055e-08 | 8.0451934e-10 |
| `cm_quiet_v` | V | 0.5124549598 | 0.5098427401 |
| `cm_recovery_error_v` | V | 6.188717858e-05 | 6.781104803e-05 |
| `cm_recovery_v` | V | 0.5125244353 | 0.509944935 |
| `cm_ref_v` | V | 0.5399578064 | 0.5375235243 |
| `cm_stage_ref_v` | V | 0.5847758973 | 0.4678569621 |
| `dm_bias_v` | V | -4.265476861e-13 | 0.00171653418 |
| `dm_high_error_v` | V | 9.636491192e-06 | 0.001702887586 |
| `dm_return_error_v` | V | 2.664109428e-08 | 0.001714255453 |
| `mean_power_w` | W | 0.0004800261426 | 0.0004285444646 |
| `power_w` | W | 0.000328315467 | 0.0002971693942 |
| `s1_bias_v` | V | 0.3417966386 | 0.343932505 |
| `s1_input_cm_v` | V | 0.9118090511 | 0.2822504833 |
| `s1_kick_v` | V | 0.01313044432 | 0.02710342905 |
| `s1_late_pp_v` | V | 0.01042919563 | 0.007729819796 |
| `s1_late_v` | V | 1.122327917 | 0.4749169629 |
| `s1_pre_kick_v` | V | 0.3417404592 | 0.3437588602 |
| `s1_quiet_pp_v` | V | 3.612232494e-07 | 2.837214463e-09 |
| `s1_quiet_v` | V | 0.3417972243 | 0.3439325068 |
| `s1_recovery_error_v` | V | 0.0004713319322 | 0.0003248150703 |
| `s1_recovery_v` | V | 0.3412691273 | 0.3434340451 |
| `s1_ref_v` | V | 0.3226353654 | 0.3290425994 |
| `s1_stage_ref_v` | V | 0.02513125631 | 0.4759621815 |

Condition 2: balanced differential AC.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | ---: | ---: |
| `dc_feedback_error_v` | V | 1.110223025e-16 | 0 |
| `fixture_cm_max` | V | 1.000741511e-16 | 1.822111577e-12 |
| `gain_10khz_db` | dB | 54.65695 | 55.05229 |
| `gain_db` | dB | 60.34043 | 60.02319 |

The physical core contains 37 MOS, 29 native MIM units and 408 high-poly segments; each 50 MOhm stage-1 sensing branch retains all 200 native segments.

Both transistor CMFB loops remain connected. In the quiet source record the output mean moves from 0.512455 V at 5–9 us to 0.024222 V at 145–149 us, while the first-stage mean moves from 0.341797 V to 1.064846 V. The extracted quiet record remains near 0.509843/0.343932 V; after the combined disturbances its late means are 0.470866/0.474917 V. These are coupled finite-window dynamics, not settled operation or joint-stability certification. The output-reference step produces 0.539958/0.537524 V source/RC means in its declared window, but does not establish stability over other conditions. Both references and both control-node waveforms are retained; individual loops are not opened to assemble a stability claim.

Halving the maximum step to 1 ns changes the disturbed source first-stage input-CM-window mean by 34.8 mV, while the largest candidate voltage-observation change is 8.1 uV. The quiet source late-window phase is much more sensitive: the stage-1 mean changes by 0.258 V under step refinement and 1.065 V under the leakage control. Such means and peak-to-peak values must not be read as steady-state bias or intrinsic ripple specifications. Candidate quiet means move by less than 0.1 uV under step refinement and 47 uV under leakage refinement. The paired score, with both quiet and disturbed records refined together, is 21.75475303 at 1 ns and 21.60289163 at 1 POhm, versus 21.75337721 nominal. This approximately 0.7% numerical sensitivity is part of the declared scope. The 100 TOhm to 1 POhm DC control shifts each source/candidate first-stage operating point by about 46 uV. All samples remain finite and each entire observation window is available.

Doubling frequency samples from 200 to 400 per decade leaves the reported AC observations unchanged at displayed precision. The explicit numerical shunt and sparse-solver settings are declared above and used identically for source and candidate.  Every differential fixture checks actual unit differential drive, residual common-mode excitation and DC feedback; raw audits also compare isolated-fixture and direct-fixture DC points. AC gain is the linearization at that point, not proof of transient stability. No loop-return ratio, phase margin or settling time is claimed.

Transient starts from the DC solution, not a supply ramp. Means use full-precision cumulative integration with interpolated exact endpoints; extrema include interpolated endpoints. Incomplete windows and nonfinite traces are invalid. Sensitivity and independent graph/waveform audit commands are maintained with the development recipe; the static evaluation below reproduces every table entry and the score.

## Reproduce

From the Bench root, use the existing project environment and the [tool guide](../../../../../docs/tools.md). These commands generate disposable reader-local reports with input, candidate, resource and tool identities; choose fresh output directories on rerun.

```bash
uv run --locked python -m benchmarking.engine.preview prepare \
  --case amp_035_fan_chopper_cmfb_dual --image iclayout-bench-tools:ngspice45 \
  --output build/runs/amp_035_fan_chopper_cmfb_dual-prepared
uv run --locked python -m benchmarking.engine.cli evaluate \
  build/runs/amp_035_fan_chopper_cmfb_dual-prepared/case/case.toml \
  tasks/ihp-sg13g2/analog-db/cases/amp_035_fan_chopper_cmfb_dual/reference/amp_035_fan_chopper_cmfb_dual.gds \
  --output build/runs/amp_035_fan_chopper_cmfb_dual-reference
```

## Source and License

This case derives from [MacAnalog/spicexplorer-release `amp_035_fan_chopper_cmfb_dual`](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_035_fan_chopper_cmfb_dual) at fixed commit `263d0322f8900dc331536fbbe6c0e804514fc454`; see [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE) for PolyForm Noncommercial and applicable component terms. Qu/Yan preserve AnalogGym BSD-3-Clause attribution. The framework MIT license does not relicense circuit materials.
