# Clocked Capacitive Instrumentation Amplifier with CMFB Layout Task

## Objective

Implement `ia_006_fan_chopper_cmfb`: a complete capacitively coupled differential
instrumentation amplifier with input, feedback and interstage/output chopping,
a two-stage amplifier and transistor common-mode feedback (CMFB). Preserve the
physical signal/feedback capacitors, both bias-return paths, compensation and
the actual common-mode controller. Validate operation with all clocks running.

## Inputs and Interface

- `materials/circuit.cdl`: authoritative physical circuit for native LVS.
- `materials/circuit.spice`: equivalent process-model simulator representation.
- `materials/testbench.spice`: independent bias, clocks, loads and measurements.

The ordered interface is:

```text
vinp vinn voutp voutn vref
clk_chin clk_chin_not clk_chfb clk_chfb_not clk_chout clk_chout_not
vdd vss core__vb1 core__vb2 core__vb3 core__vb4 vref_cm
core__vsum_p core__vsum_n
```

VINP/VINN and VOUTP/VOUTN are the differential input and output. VREF biases
the summing nodes through physical high-poly return arms; VREF_CM is the
reference for the actual transistor common-mode controller. The four CORE__VB
ports supply the declared core bias voltages. The final two ports are
high-impedance summing-node monitors: the testbench observes them without
applying voltage/current drive, a servo or an external load. Keep these named
connections; they also distinguish the symmetric native LVS branches.

Use the fixed models, dimensions, multiplicities and connections in the
netlist. The 46 source MOS groups have a maintained 61-finger implementation;
parallel fingering/merging is allowed when all checks pass. Core matching pairs
have fixed total W*m/L and on-grid finger dimensions; do not replace them with
unqualified model widths. NMOS and resistor bodies connect to SUB through the
explicit VSS substrate tap, and PMOS bodies to WELL through the VDD well tap.
Do not drive the internal CMFB actuator VB4O externally.

Physical passive requirements are:

| Branch | Physical implementation | Nominal value at TT, 27 C |
| --- | --- | --- |
| Each input arm | Four parallel 51.6 × 51.6 um `cap_cmim` units | 16.008384 pF |
| Each capacitive feedback arm | One 23.11 × 23.11 um `cap_cmim` | 0.80480575 pF |
| Each differential Miller path | One 51.6 × 51.6 um `cap_cmim` | 4.002096 pF |
| CMFB actuator to VSS | One 25.85 × 25.85 um `cap_cmim` | 1.00646975 pF |
| Each summing-node return to VREF | 41 series `rhigh` segments, W=1 um, L=180 um, m=1, b=0 | 10.46156 Mohm |
| Each output-to-common-mode-sense arm | Four of the same high-poly segments | 1.02064 Mohm |

The input/feedback capacitor ratio is approximately 19.891. All internal
passives are physical DUT devices, distinct from external output loads. Preserve
MIM plate orientation. The maintained compensation is deliberately retuned for
the physical combined loop; the source's ideal 1 pF Miller / 1 fF controller
values do not define this task.

## Operating Conditions

Use TT MOS/capacitor/resistor models at 27 C and VDD/VSS=1.2/0 V. VREF and
VREF_CM are both 0.6 V. Relative to VSS, CORE__VB1/2/3/4 are respectively
0.5/0.75/0.45/0.589 V. There is no ideal external output-common-mode or
differential-feedback servo. Each output has a 1 pF or 5 pF external load.
At each load, run both signs of a 10 mV differential input step: four conditions.

The input common mode stays at 0.6 V. Both inputs initially equal 0.6 V.
During 500–501 us they move to `0.6+step_v/2` and `0.6-step_v/2`, hold
for 500 us, then return during 1001–1002 us. `step_v` is +0.01 or −0.01 V.
The pulse period is 10 ms; only the finite 0–1.5 ms sequence is measured.

All three true/complement clock pairs run synchronously at 20 kHz between
0 and 1.2 V. True clocks begin high, fall during 25–25.05 us, hold low for
24.95 us, then rise during 50–50.05 us; the 50 us pattern repeats. Complement
clocks have exactly opposite levels with the same 50 ns edges. Finite
complementary slopes may produce overlap or dead intervals according to device
thresholds; no ideal break-before-make behavior is assumed. Input, feedback and
output/interstage clocks all switch; frozen-clock gain is not an acceptance test.

Transient starts from the solved DC operating point. Use Gear order 2, the
KLU solver, maximum time step 500 ns, `rshunt=1e13`, `reltol=1e-5`,
`abstol=1e-13` and `vntol=1e-8`. Save the declared port voltages and source
currents. The settled observation windows contain integer clock periods;
startup from a zero-supply state is not covered.

## Physical Requirements

Submit GDSII top cell `ia_006_fan_chopper_cmfb`, no larger than 10 MiB.
Pass native IHP main/maximal DRC without waivers (standalone scope with
density/antenna disabled), strict named-interface LVS including taps, and a
3000 × 700 um functional outline. Device, contact and complete routing layers
are enumerated by the runtime outline constraint. Pin/annotation layers are
excluded from area and cannot conceal functional geometry.

The submitted layout must provide the actual capacitors, resistor segments and
matching-aware core. Post-layout simulation consumes candidate-derived Magic
RC with device junction geometry and interconnect. Extraction subdivides the
initial Magic grid by two and uses `gds_readonly=false` on an isolated import;
the submitted GDS remains immutable. No extraction diagnostic is waived.
Magic idealizes the explicit tap devices while retaining its extracted RC
network; the source simulator includes finite tap models. Distributed substrate
noise and manufacturing signoff are not qualified.

## Electrical Requirements and Scoring

Physical checks and declared functional bounds remain mandatory. Quality has no
fixed allowed-degradation threshold. Each `source_*` job simulates the declared
source circuit with exactly the same testbench, model resources, parameters,
load and measurement window as its paired extracted-candidate job. A source
observation is the 100-point electrical baseline; it is independent of the
submitted GDS. All individual pairs are retained in the evaluation report.

For a post-layout observation x and its source observation b:

- Maximize: q = x/b; minimize: q = b/x. When a numerical scale s is declared,
  use (x+s)/(b+s) or its inverse. This handles zero-valued error measurements;
  s is a normalization floor, not an allowed degradation or pass threshold.
- Amplitude dB: q = 10^((x-b)/20) for maximize, its inverse for minimize.
- Target: q = 1/(1+abs(x-b)/s), with a declared physical scale s. Signed and
  zero-valued operating points are never divided directly.

A metric uses its worst paired q. Each response/bias/supply dimension takes the
geometric mean of its scored metrics; E is the geometric mean of applicable
dimensions. Q = area_reference / candidate_functional_area. The overall score is
S = 100 * sqrt(E * Q). The baseline is 100, not a ceiling; directional and area
improvements can earn more than 100. Failed physical or functional checks score
zero; missing/invalid evaluation or source measurements produce an unknown score.
Diagnostic observations do not earn points. The runtime task plan publishes the
exact pairing, dimensions, scales and any functional bounds.

| Metric | Definition / observations | Unit | Quality rule | Functional bounds | Scale |
| --- | --- | --- | --- | --- | --- |
| `gain_vv` | condition_0:gain_vv, condition_1:gain_vv, condition_2:gain_vv, condition_3:gain_vv | V/V | target / target | −∞ … +∞ | 1.0 |
| `baseline_error_v` | condition_0:baseline_error_v, condition_1:baseline_error_v, condition_2:baseline_error_v, condition_3:baseline_error_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `return_error_v` | condition_0:return_error_v, condition_1:return_error_v, condition_2:return_error_v, condition_3:return_error_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `high_drift_v` | condition_0:high_drift_v, condition_1:high_drift_v, condition_2:high_drift_v, condition_3:high_drift_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `return_drift_v` | condition_0:return_drift_v, condition_1:return_drift_v, condition_2:return_drift_v, condition_3:return_drift_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `ripple_rms_v` | condition_0:ripple_rms_v, condition_1:ripple_rms_v, condition_2:ripple_rms_v, condition_3:ripple_rms_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `ripple_pp_v` | condition_0:ripple_pp_v, condition_1:ripple_pp_v, condition_2:ripple_pp_v, condition_3:ripple_pp_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `cm_mean_v` | condition_0:cm_mean_v, condition_1:cm_mean_v, condition_2:cm_mean_v, condition_3:cm_mean_v | V | target / target | 0 … 1.2 | 1.2 |
| `cm_min_v` | condition_0:cm_min_v, condition_1:cm_min_v, condition_2:cm_min_v, condition_3:cm_min_v | V | target / target | 0 … 1.2 | 1.2 |
| `cm_max_v` | condition_0:cm_max_v, condition_1:cm_max_v, condition_2:cm_max_v, condition_3:cm_max_v | V | target / target | 0 … 1.2 | 1.2 |
| `sum_cm_v` | condition_0:sum_cm_v, condition_1:sum_cm_v, condition_2:sum_cm_v, condition_3:sum_cm_v | V | target / target | 0 … 1.2 | 1.2 |
| `sum_error_v` | condition_0:sum_error_v, condition_1:sum_error_v, condition_2:sum_error_v, condition_3:sum_error_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `mean_power_w` | condition_0:mean_power_w, condition_1:mean_power_w, condition_2:mean_power_w, condition_3:mean_power_w | W | minimize / ratio | 0 … +∞ | 1e-12 |
| `clock_power_w` | condition_0:clock_power_w, condition_1:clock_power_w, condition_2:clock_power_w, condition_3:clock_power_w | W | minimize / ratio | 0 … +∞ | 1e-12 |
| `dc_cm_v` | condition_0:dc_cm_v, condition_1:dc_cm_v, condition_2:dc_cm_v, condition_3:dc_cm_v | V | diagnostic | −∞ … +∞ | — |
| `dc_dm_v` | condition_0:dc_dm_v, condition_1:dc_dm_v, condition_2:dc_dm_v, condition_3:dc_dm_v | V | diagnostic | −∞ … +∞ | — |
| `baseline_v` | condition_0:baseline_v, condition_1:baseline_v, condition_2:baseline_v, condition_3:baseline_v | V | diagnostic | −∞ … +∞ | — |
| `plateau_v` | condition_0:plateau_v, condition_1:plateau_v, condition_2:plateau_v, condition_3:plateau_v | V | diagnostic | −∞ … +∞ | — |
| `return_v` | condition_0:return_v, condition_1:return_v, condition_2:return_v, condition_3:return_v | V | diagnostic | −∞ … +∞ | — |
| `dc_power_w` | condition_0:dc_power_w, condition_1:dc_power_w, condition_2:dc_power_w, condition_3:dc_power_w | W | diagnostic | −∞ … +∞ | — |

Area reference: **102216.79 um2**. 166 expanded device instances; sum of device/contact envelopes 67727.1707 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

The capability coefficient remains **10**; it is independent of
the reference-relative task score.

## Tools and Submission

Solve budget: **3 hours**.

Discover frozen task inputs, requirements, reviewed resources and harness
feedback in `/protocol/task.json`, `/protocol/resources.json` and
`/protocol/harness.json`. Use the supplied IHP primitives and KLayout, Magic
and ngspice. Write `/workspace/output/final.gds` and explicitly submit through
the harness protocol. Source records, reference GDS and host configuration
remain outside standard solver inputs.
