# Fan Dual CMFB OTA Layout Task

## Objective

Implement `amp_035_fan_chopper_cmfb_dual` without changing the declared circuit. The independently frozen flattened composite contains the PMOS input/folded-cascode first stage, static straight-through output chopper and common-source second stage. One seven-transistor CMFB detects the output mean through two 1 MOhm resistors and drives XM8O/XM9O on vb4o. A second seven-transistor CMFB detects stg1_p/stg1_n through two 50 MOhm resistors and drives vb4_ctl, controlling the first-stage tail and folded PMOS sources. The 50 MOhm override, distinct 0.3265 V stage reference, 100 pF inner-loop compensation and both 6 pF Miller capacitors remain. Neither loop is replaced or independently opened to infer joint stability.

## Inputs and Interface

`materials/circuit.cdl` is the physical authority; `materials/circuit.spice` is its equivalent simulator representation. `materials/testbench.spice` and `materials/ac.spice` define the transient/closed-AC and balanced open-AC observations. This problem is the description input. The ordered interface is `vinp vinn voutp voutn vdd vss core__vb1 core__vb2 core__vb3 vref_out vref_s1 stg1_p stg1_n vb4o vb4_ctl`. `vss`/`vdd` are rails, input/output names are signal terminals, and the bias/reference and unloaded monitor ports retain the connections named in the netlist. Independent bias sources and loads belong outside the physical core.

W/L are rounded to 10 nm so centred contacts remain on the 5 nm manufacturing grid. The 0.293 um bias NMOS width is raised to 0.300 um to realize valid native active/contact geometry; no other sizing optimization is applied. Every resistor uses native rhigh segments of at most about 250 kOhm; every larger capacitor uses parallel native cap_cmim units of at most about 4 pF. Body taps have finite native models in both source and extracted circuits.

## Operating Conditions

TT MOS, typical MIM/high-poly, 27 C, 1.2 V supply, 0.6 V input common mode, 10 pF on each output. The external voltage sources are vb1_core core__vb1 vss dc 0.3983759766; vb2_core core__vb2 vss dc 0.65; vb3_core core__vb3 vss dc 0.45; vrefout vref_out vss dc 0.5; vrefs1 vref_s1 vss dc 0.3265. Both the no-disturbance condition and the following combined sequence run for 150 us with a 2 ns maximum step. The differential command rises from 0 to 10 mV at 10 us and returns after 10 us; equal +20 uA currents enter both outputs at 30 us for 2 us. The output reference rises by 25 mV at 50 us for 15 us; input common mode rises by 25 mV at 75 us for 15 us. The stage-1 reference rises by 10 mV at 110 us for 15 us. All edges are 20 ns. Pulse widths are measured after the rising edge, so falling edges start one edge duration after nominal delay plus width. The unperturbed condition sets every step and kick amplitude to zero. The two CMFB loops, where present, remain connected throughout. Monitor ports are unloaded; their extraction and routing parasitics remain. No external clock is applied: straight-through chopper gates stay tied to their actual rails, and crossed paths stay off.

The external fixture enforces inp = icm + (signal − (outp−outn))/2 and inn = icm − (signal − (outp−outn))/2. It closes only the differential measurement loop; the DUT transistors close common-mode feedback. The frequency deck retains this DC feedback, isolates each feedback branch with 1 TH/1 F low-pass elements and injects +0.5/−0.5 V AC. The actual differential excitation remains 1 V and residual common-mode must be at most 1 uV.

Both decks sweep 1 Hz–1 GHz at 200 points/decade. AC describes the linearization of the verified DC point, not proof of a dynamically stable equilibrium. An explicit rshunt=1e14 (100 TOhm) numerical shunt to ground at each node regularizes otherwise floating extraction/series-capacitor nodes; source and candidate use the identical setting. Sensitivity is checked with 1 POhm. Supply startup is not simulated: transient starts from the DC operating point, and the no-disturbance interval tests whether that point persists. Use the default sparse solver with pivtol=1e-18, below the numerical shunt conductance, and the tolerances declared in the decks.

## Physical Requirements

Submit a native SG13G2 GDS with top cell `amp_035_fan_chopper_cmfb_dual`, at most 67108864 bytes, within 20000 × 2000 um. Native main and maximal DRC, named-interface LVS and geometry must pass without marker waivers. Keep every MOS, body connection and passive path. Unit multiplicities and the declared passive series/parallel realization are fixed in the materials.

The functional footprint includes active, gate, contact, metal, via, MIM and complete routing shapes; well, text, annotations and nonfunctional markers alone do not define it. The runtime task supplies the exact layer set. Candidate GDS drives native connectivity extraction and distributed wire resistance/ground capacitance extraction, then the same native MOS/MIM/high-poly simulation models used by the source. This nominal MOS/R/C boundary does not assert RF/coupling extraction, PVT, mismatch, noise or manufacturing signoff.

## Electrical Requirements and Scoring

Every declared simulation must complete with finite measurements and complete raw records. Transient means use full-precision cumulative integration with interpolated endpoint corrections; incomplete windows are errors. PP denotes the full finite-window range, including any oscillation or slow drift. No phase margin, loop gain, settling time or periodic steady state is claimed.

| Metric | Unit | Definition | Quality role / functional domain |
| --- | --- | --- | --- |
| `cm_quiet_v` | V | avg cm, 5–9 us | bias; target |
| `cm_pre_kick_v` | V | avg cm, 28–29 us | bias; target |
| `cm_recovery_v` | V | avg cm, 45–49 us | bias; target |
| `cm_ref_v` | V | avg cm, 60–64 us | bias; target |
| `cm_input_cm_v` | V | avg cm, 85–89 us | bias; target |
| `cm_stage_ref_v` | V | avg cm, 120–124 us | bias; target |
| `cm_late_v` | V | avg cm, 145–149 us | bias; target |
| `cm_quiet_pp_v` | V | pp cm, 5–9 us | response; ratio; 0 ≤ value |
| `cm_late_pp_v` | V | pp cm, 145–149 us | response; ratio; 0 ≤ value |
| `cm_kick_v` | V | max cm_delta, 30–33 us | response; ratio; 0 ≤ value |
| `cm_recovery_error_v` | V | avg cm_delta, 45–49 us | response; ratio; 0 ≤ value |
| `s1_quiet_v` | V | avg s1, 5–9 us | bias; target |
| `s1_pre_kick_v` | V | avg s1, 28–29 us | bias; target |
| `s1_recovery_v` | V | avg s1, 45–49 us | bias; target |
| `s1_ref_v` | V | avg s1, 60–64 us | bias; target |
| `s1_input_cm_v` | V | avg s1, 85–89 us | bias; target |
| `s1_stage_ref_v` | V | avg s1, 120–124 us | bias; target |
| `s1_late_v` | V | avg s1, 145–149 us | bias; target |
| `s1_quiet_pp_v` | V | pp s1, 5–9 us | response; ratio; 0 ≤ value |
| `s1_late_pp_v` | V | pp s1, 145–149 us | response; ratio; 0 ≤ value |
| `s1_kick_v` | V | max s1_delta, 30–33 us | response; ratio; 0 ≤ value |
| `s1_recovery_error_v` | V | avg s1_delta, 45–49 us | response; ratio; 0 ≤ value |
| `dm_high_error_v` | V | avg dmerror, 18–19 us | response; ratio; 0 ≤ value |
| `dm_return_error_v` | V | avg dmerror, 25–29 us | response; ratio; 0 ≤ value |
| `mean_power_w` | W | Time-weighted delivered power over the declared transient window | supply; ratio; 0 ≤ value |
| `cm_bias_v` | V | DC cm_bias_v | bias; target |
| `s1_bias_v` | V | DC s1_bias_v | bias; target |
| `dm_bias_v` | V | DC dm_bias_v | bias; target |
| `power_w` | W | DC delivered power from DUT supply and declared external bias/reference sources | supply; ratio; 0 ≤ value |
| `closed_gain_10khz_db` | dB | Direct follower output/signal AC gain at 10 kHz | response; target |
| `gain_db` | dB | Balanced differential open AC gain at 1 Hz | response; db20 |
| `gain_10khz_db` | dB | Balanced differential open AC gain at 10 kHz | response; db20 |
| `fixture_cm_max` | V | Fixture validity fixture_cm_max | diagnostic; unscored; 0 ≤ value ≤ 1e-06 |
| `dc_feedback_error_v` | V | Fixture validity dc_feedback_error_v | diagnostic; unscored; 0 ≤ value ≤ 1e-06 |

`cm` is the output mean and `s1` is the first-stage mean. Quiet/pre-kick/recovery/reference/input-CM/stage-reference/late windows are 5–9, 28–29, 45–49, 60–64, 85–89, 120–124 and 145–149 us. Recovery is relative to each run’s pre-kick mean; it is not a claim of asymptotic settling. All window values are evaluated for both zero-stimulus and disturbed conditions.

Performance is continuously paired with the independently simulated source under exactly the same conditions. Gain quality is 10^((candidate−source)/20); target quality is 1/(1+abs(candidate−source)/scale); inverse-ratio quality is (source+floor)/(candidate+floor). Per-metric observations are aggregated as declared in the runtime task, then geometric means combine metrics within bias, response and supply dimensions. S = 100*sqrt(E*Q), Q = 361466.3 um2 / functional area. The bias scale is 1.2 V; closed-response scale is 6 dB (factor two in amplitude). Error/range floors are 0.1 mV for differential error (1% of the 10 mV step) and 1 mV for common-mode excursions; power floor is 1 pW. Physical/domain and fixture-validity gates are not upstream product targets.

The compact-area anchor sums m*((W+2.4)*(L+2.4)+3.2^2) um2 for MOS, 1.2*C/(1.5 fF/um2) for physical capacitor envelopes, and 2*R/(1360 Ohm) um2 for resistor envelopes, then adds 50% global routing allowance. It is an engineering estimate independent of the reference GDS. Coefficient 9 reflects two interacting transistor CM loops, high-impedance sensing and large physical passive networks.

## Tools and Submission

Solve budget: **8 hours**.

Use the reviewed SG13G2 resources and ngspice 45 tool environment. The runtime `/protocol/task.json` publishes frozen inputs, requirements and tool bindings. Submit `/workspace/output/final.gds` explicitly through the session submission tool; writing the file alone does not submit it. The evaluation executes native checks, candidate-derived RC and independent paired source/post-layout simulations. The reference GDS, maintainer README and development checkout are not solver inputs.
