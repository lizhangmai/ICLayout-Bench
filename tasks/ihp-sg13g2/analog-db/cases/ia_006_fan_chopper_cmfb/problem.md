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

Let `d=VOUTP−VOUTN`, `c=(VOUTP+VOUTN)/2`, and let averages and extrema use
the saved transient samples with endpoint interpolation and trapezoidal
integration. The primary windows are:

| Symbol | Window | Meaning |
| --- | --- | --- |
| B | 400–500 us | Settled zero input; two complete clock periods |
| H | 900–1000 us | Settled signed input plateau; two periods |
| R | 1400–1500 us | Settled return to zero; two periods |
| A | 400–1500 us | Complete accepted sequence after initial settling; 22 periods |

`baseline_v`, `plateau_v` and `return_v` are mean d in B, H and R. These
signed means and `dc_cm_v`, `dc_dm_v`, `dc_power_w` are diagnostic values
without independent score bounds. A static DC differential offset may be
modulated by the running choppers; static balance does not establish success.

The required measurements are:

- `gain_vv=(plateau_v−baseline_v)/step_v`, retaining the expected positive sign.
- `baseline_error_v=abs(baseline_v)` and
  `return_error_v=abs(return_v−baseline_v)`.
- `high_drift_v`: absolute difference between mean d over 900–950 us and
  950–1000 us. `return_drift_v`: the analogous difference over 1400–1450 us
  and 1450–1500 us. These check successive full periods, not a first crossing.
- `ripple_rms_v`: square root of the H average of `(d−plateau_v)^2`.
  `ripple_pp_v`: maximum d minus minimum d over all of H, including switching
  edges. No blanking window, smoothing filter or spike exclusion is applied.
- `cm_mean_v`: mean c in H; `cm_min_v` and `cm_max_v`: extrema throughout A.
- `sum_cm_v`: H mean of `(CORE__VSUM_P+CORE__VSUM_N)/2`.
  `sum_error_v`: absolute H mean of
  `(CORE__VSUM_P−CORE__VSUM_N)*(CLK_CHIN/0.6−1)`. The continuous clock factor
  includes its finite ramps; this is demodulated mean error, not a claim that
  the instantaneous differential summing voltage is zero at switching edges.
- `mean_power_w`: A mean of `−1.2*I(VDD)`. It includes the physical amplifier,
  bias and CMFB devices, but excludes external bias/reference generator
  overhead, signal-driver energy and clock-driver supply energy.
- `clock_power_w`: H mean of the sum, over all six clock voltage sources, of
  `max(−Vclock*I(Vclock),0)`. It counts positive supplied power separately for
  each source over complete periods, without crediting returned energy.

Every bound below must hold independently in every load/polarity condition.

| Metric | Unit | Acceptance | Lower / upper zero-score boundaries | Dimension |
| --- | --- | --- | --- | --- |
| `gain_vv` | V/V | 18.5–21 | 0 / 30 | response |
| `baseline_error_v` | V | 0–5e-05 | 0 / 0.005 | response |
| `return_error_v` | V | 0–5e-05 | 0 / 0.005 | response |
| `high_drift_v` | V | 0–1e-05 | 0 / 0.002 | response |
| `return_drift_v` | V | 0–1e-05 | 0 / 0.002 | response |
| `ripple_rms_v` | V | 0–0.015 | 0 / 0.1 | response |
| `ripple_pp_v` | V | 0–0.12 | 0 / 0.6 | response |
| `cm_mean_v` | V | 0.59–0.63 | 0.45 / 0.8 | bias |
| `cm_min_v` | V | 0.57–0.65 | 0.45 / 0.8 | bias |
| `cm_max_v` | V | 0.57–0.65 | 0.45 / 0.8 | bias |
| `sum_cm_v` | V | 0.59–0.61 | 0.45 / 0.75 | bias |
| `sum_error_v` | V | 0–0.0003 | 0 / 0.01 | response |
| `mean_power_w` | W | 0–0.0004 | 0 / 0.0008 | supply |
| `clock_power_w` | W | 0–2.5e-08 | 0 / 1e-06 | supply |

Coefficient **10** represents a system-level combination of input/feedback
modulation, a compensated two-stage signal path and actual common-mode feedback
across both clock states and input polarities. Unified `layout-v1` scoring is
`G × (60E + 20H + 20HQ)`: G requires physical validity and complete valid
measurements, E averages worst attainment in response/bias/supply, and H
requires every electrical bound. Each attainment declines linearly between its
acceptance edge and stated zero boundary. Area utility is
`Q=clip((4800000−area)/3600000,0,1)`, using fixed absolute anchors
1200000/4800000 um². Physical rejection scores zero; incomplete measurements
cannot establish success or receive an invented score. Aggregation cannot hide
a failed condition.

Qualification covers nominal clocked DC transfer, period-mean recovery, full
ripple and common-mode regulation for the specified sequence. It does not
establish a low-noise/low-ripple amplifier, input impedance, broadband frequency
response, PSS/PAC/noise performance, internal loop phase margins, arbitrary
loads/clock phasing, PVT, mismatch, rail-to-rail operation or zero-supply startup.

## Tools and Submission

Discover frozen task inputs, requirements, reviewed resources and harness
feedback in `/protocol/task.json`, `/protocol/resources.json` and
`/protocol/harness.json`. Use the supplied IHP primitives and KLayout, Magic
and ngspice. Write `/workspace/output/final.gds` and explicitly submit through
the harness protocol. Source records, reference GDS and host configuration
remain outside standard solver inputs.
