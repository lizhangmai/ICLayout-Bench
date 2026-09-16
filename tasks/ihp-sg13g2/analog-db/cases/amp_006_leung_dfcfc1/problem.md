# Output-Controlled Auxiliary Compensation OTA Layout Task

## Objective

Lay out `amp_006_leung_dfcfc1`, retaining the complete folded PMOS-input stage,
three-stage signal path, direct output feedforward, and auxiliary compensation.
The folded stage drives `net050`, which drives the output PMOS and the
PMOS/diode/mirror path to `net049`. That node drives both the output NMOS
and an auxiliary common-source NMOS whose drain is `net1`; a biased PMOS
loads this auxiliary drain. C0 connects `net050` to output, while C1 connects
`net049` to `net1`. The auxiliary branch therefore acts on the NMOS output
control node. In contrast, the separate AMP007 case's auxiliary PMOS senses
`net050` and its compensation terminates at `net2`.

## Inputs and Interface

- `materials/circuit.cdl`: authoritative native physical device graph.
- `materials/circuit.spice`: matching simulator representation with finite taps.
- `materials/testbench.spice`: public bias, bilateral AC and step measurements.

Ordered ports: `vss vdd vinn vinp vout net013`. VSS is return, VDD supply,
VINN/VINP the inverting/noninverting inputs, VOUT output, and `net013` the
external bias-sink connection. Input PMOS bodies connect to the separate
`net31` source-tied well; other PMOS use the VDD well and NMOS use the VSS
substrate contact. Preserve all 26 MOS groups, 675 physical fingers, W/L/m,
body connections, and both internal capacitive branches. Native equivalent
parallel fingering is allowed only when all physical and electrical checks pass.

The maintained MOS dimensions are rounded to the actual 10 nm PyCell grid;
the 1,413 rounded source fingers are regrouped within their original MOS
groups using integer factors, with <=10 um single width. Each group retains
exactly its rounded total W and L; individual W/m and diffusion perimeter
change. Every body connection remains intact. Distributed 2 x 2 um body
contacts at <=20 um pitch replace continuous tap strips. All capacitors are physical `cap_cmim`:

- `c0`: `net050` (top plate) to `vout` (bottom plate), 8 parallel 48.935 × 48.935 um MIM units.
- `c1`: `net049` (top plate) to `net1` (bottom plate), 3 parallel 50.94 × 50.94 um MIM units.

These are internal compensation devices, distinct from the external load.
The normalized source's 27.4754 uA bias is deliberately calibrated to
6.86885 uA, improving headroom and finite tracking at the declared signal
levels. No ideal output servo or internal numerical damping element is added.

## Operating Conditions

Use typical IHP LV MOS/MIM/poly models at 27 C and VDD=1.2 V, with an external
6.86885 uA sink from `net013` to VSS. Every combination of 5/10/20 pF output
load and 0.5/0.7 V DC input must pass. A zero-volt source from VINN (`vm`) to
VOUT closes unity feedback. VINP is AC ground. The two DC input levels
independently check operating-point error and the complete sampled return ratio.

At the closed input/output boundary, inject a series AC voltage with zero
parallel AC current, then zero series voltage and unit current into `vm`.
Both injections retain the original circuit and loading. With first-run
`b=-I(VPROBE)`, `d=V(vm)` and second-run `a=-I(VPROBE)`, `c=V(vm)`, define
`delta=a*d-b*c` and the bilateral return ratio
`T=(2*delta-a+d)/(1-2*delta+a-d)` (Tian et al., Eq. 30).
The deck exports both injections' voltages/currents for independent two-port
admittance reconstruction. This is a finite external-loop measurement,
not a certificate for every internal pole or a complete Nyquist proof.

Sweep 0.01 Hz–10 GHz at 300 points/decade. Use continuous phase starting
on its natural low-frequency branch, without a phase-offset correction.
Check both first and final descending unity crossings, minimum sampled
`abs(1+T)`, maximum absolute continuous phase of `1+T` across the entire sweep,
and maximum gain over 2–10 GHz. Missing crossings or invalid measurements
are evaluator errors; all sampled return-distance and phase bounds also apply.

For each condition, VINP's pulse starts at 0.5 V, rises to 0.7 V at
2–2.02 us and falls at 10.02–10.04 us, with a 16 us period. Transient uses
its own pulse-start operating point, independently of the AC DC-input setting.
Simulate 0–18 us with the KLU linear solver and Gear order 2, 2 ns maximum step, `itl4=1000`,
`rshunt=1e12`, `reltol=1e-5`, `abstol=1e-12`, and `vntol=1e-8`.
The numerical shunt is not a physical device. The maintained 1 pA absolute
current tolerance is checked at 0.1 pA with tenfold tighter relative/voltage
tolerances and a 1e13 ohm shunt. Initial experimental 10 fA/1 fA current
tolerances produced excessive iteration cost in the extracted low-resistance
network. This numerical-floor calibration preserves every electrical bound
and all physical/parasitic elements; half-step and trapezoidal controls
independently check the observable dynamics. PVT, mismatch, noise,
distortion, supply startup, rail-to-rail operation and arbitrary-load stability
are outside this contract.

## Physical Requirements

Submit GDSII top cell `amp_006_leung_dfcfc1`, at most 32 MiB. Pass native
IHP main/maximal DRC without waivers (standalone scope, density/antenna off),
strict named-interface LVS with explicit taps, and a 6400 × 130 um functional
envelope. Every device/contact/interconnect drawing layer listed in the
runtime `outline` constraint contributes to area; annotation/pin-purpose
layers do not. Labels alone do not establish electrical connectivity.

Post-layout simulation uses the submitted GDS's complete Magic RC, with
physical MIM devices and interconnect resistances/capacitances. Half-grid
import is explicit. Magic retains only Metal3 interface labels in its isolated
extraction copy to avoid repeated internal well-name aliases, while native LVS
checks the original GDS and its explicit tap devices. No resistance/capacitance threshold omits small parasitics.
Magic idealizes well/substrate taps, whereas source simulation uses finite
physical tap models. Distributed substrate resistance/noise and fabrication
signoff remain unqualified. The long independent witness is a feasibility
layout, not an area optimum.

## Electrical Requirements and Scoring

`output_v` is DC output and `output_error_v=abs(VOUT−VINP)` checks accuracy
at each DC input separately. `bias_v` is bias-port voltage. `power_w` and
`mean_power_w` are positive VDD-supplied power at DC and over the complete
2–18 us cycle, including the on-chip bias network; external bias-generator
overhead is excluded and sink energy is not credited as recovered power.

`dc_gain_db` is bilateral return-ratio magnitude at 0.01 Hz. Unity frequency
and phase margin are measured at the first descending 0 dB crossing;
`final_*` uses the last descending crossing. Phase margin is
`180+phase(T)` at the corresponding crossing. Return-distance, return-phase
and high-frequency gain definitions are given above and apply to every sample
in their stated windows.

`recovery_up_v` and `recovery_down_v` are maximum `abs(VOUT−VINP)` over
5–9.5 us and 13–17.5 us: sustained tracking after approximately 3 us,
not a first band entry or final point. `step_gain` is the difference of mean
output in 9–9.5 us and 17–17.5 us divided by 0.2 V. `peak_v` is maximum
output in 2–10 us; `trough_v` is minimum output in 10.04–18 us.
The evaluator's extrema use ngspice's in-window samples; reference calibration
also checks interpolated endpoints. Means use the complete specified windows.

Every bound below applies independently to all six conditions. All required
measurements must complete; an incomplete evaluation cannot establish success.

| Metric | Unit | Acceptance | Lower / upper zero-score boundaries | Dimension |
| --- | --- | --- | --- | --- |
| `output_v` | V | 0.495–0.705 | 0.4 / 0.8 | bias |
| `output_error_v` | V | 0–0.005 | 0 / 0.05 | bias |
| `bias_v` | V | 0.64–0.7 | 0 / 1.2 | bias |
| `power_w` | W | 0–0.00015 | 0 / 0.0003 | supply |
| `dc_gain_db` | dB | 85–110 | 40 / 140 | response |
| `unity_hz` | Hz | 400000–700000 | 0 / 1.4e+06 | response |
| `phase_margin_deg` | deg | 60–100 | 0 / 180 | response |
| `final_unity_hz` | Hz | 400000–700000 | 0 / 1.4e+06 | response |
| `final_phase_margin_deg` | deg | 60–100 | 0 / 180 | response |
| `minimum_return_distance` | 1 | 0.5–1.1 | 0 / 2 | response |
| `return_phase_excursion_deg` | deg | 0–110 | 0 / 180 | response |
| `hf_gain_db` | dB | -300–-20 | -400 / 0 | response |
| `recovery_up_v` | V | 0–0.005 | 0 / 0.05 | response |
| `recovery_down_v` | V | 0–0.005 | 0 / 0.05 | response |
| `step_gain` | V/V | 0.98–1.02 | 0.8 / 1.2 | response |
| `mean_power_w` | W | 0–0.00015 | 0 / 0.0003 | supply |
| `peak_v` | V | 0.695–0.75 | 0.5 / 1.2 | response |
| `trough_v` | V | 0.48–0.505 | 0 / 0.7 | response |

Coefficient **8** reflects the coupled auxiliary/output control, physical
compensation and loaded stability/recovery requirements. Unified `layout-v1`
score is `G × (60E + 20H + 20HQ)`: G requires physical validity and complete
valid measurements, E averages the worst attainment in response/bias/supply,
and H requires every bound. Attainment decreases linearly to the listed zero
boundaries. Q is `clip((3200000−area)/2400000,0,1)` for functional area in um²,
with fixed absolute target 800,000 and zero 3,200,000 um². These budgets
include all MOS, MIM, taps and routing; they do not depend on the submitted
layout or a changing reference. Completed physical rejection scores zero;
errors preventing scoring produce no fabricated score.

## Tools and Submission

Discover inputs/resources/feedback through `/protocol/task.json`,
`/protocol/resources.json` and `/protocol/harness.json`. Use the supplied
IHP primitives with KLayout, Magic and ngspice. Write
`/workspace/output/final.gds` and explicitly submit via the harness protocol.
Host configuration, source records and reference answers are outside solver inputs.
