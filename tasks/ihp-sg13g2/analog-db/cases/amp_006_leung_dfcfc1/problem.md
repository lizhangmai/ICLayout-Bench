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
| `output_v` | condition_0:output_v, condition_1:output_v, condition_2:output_v, condition_3:output_v, condition_4:output_v, condition_5:output_v | V | target / target | 0 … 1.2 | 1.2 |
| `output_error_v` | condition_0:output_error_v, condition_1:output_error_v, condition_2:output_error_v, condition_3:output_error_v, condition_4:output_error_v, condition_5:output_error_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `bias_v` | condition_0:bias_v, condition_1:bias_v, condition_2:bias_v, condition_3:bias_v, condition_4:bias_v, condition_5:bias_v | V | target / target | 0 … 1.2 | 1.2 |
| `power_w` | condition_0:power_w, condition_1:power_w, condition_2:power_w, condition_3:power_w, condition_4:power_w, condition_5:power_w | W | minimize / ratio | 0 … +∞ | 1e-12 |
| `dc_gain_db` | condition_0:dc_gain_db, condition_1:dc_gain_db, condition_2:dc_gain_db, condition_3:dc_gain_db, condition_4:dc_gain_db, condition_5:dc_gain_db | dB | maximize / db20 | −∞ … +∞ | — |
| `unity_hz` | condition_0:unity_hz, condition_1:unity_hz, condition_2:unity_hz, condition_3:unity_hz, condition_4:unity_hz, condition_5:unity_hz | Hz | maximize / ratio | 0 … +∞ | — |
| `phase_margin_deg` | condition_0:phase_margin_deg, condition_1:phase_margin_deg, condition_2:phase_margin_deg, condition_3:phase_margin_deg, condition_4:phase_margin_deg, condition_5:phase_margin_deg | deg | target / target | 0 … 180 | 180 |
| `final_unity_hz` | condition_0:final_unity_hz, condition_1:final_unity_hz, condition_2:final_unity_hz, condition_3:final_unity_hz, condition_4:final_unity_hz, condition_5:final_unity_hz | Hz | maximize / ratio | 0 … +∞ | — |
| `final_phase_margin_deg` | condition_0:final_phase_margin_deg, condition_1:final_phase_margin_deg, condition_2:final_phase_margin_deg, condition_3:final_phase_margin_deg, condition_4:final_phase_margin_deg, condition_5:final_phase_margin_deg | deg | target / target | 0 … 180 | 180 |
| `minimum_return_distance` | condition_0:minimum_return_distance, condition_1:minimum_return_distance, condition_2:minimum_return_distance, condition_3:minimum_return_distance, condition_4:minimum_return_distance, condition_5:minimum_return_distance | 1 | target / target | 0 … +∞ | 1.0 |
| `return_phase_excursion_deg` | condition_0:return_phase_excursion_deg, condition_1:return_phase_excursion_deg, condition_2:return_phase_excursion_deg, condition_3:return_phase_excursion_deg, condition_4:return_phase_excursion_deg, condition_5:return_phase_excursion_deg | deg | minimize / ratio | 0 … +∞ | 1e-12 |
| `hf_gain_db` | condition_0:hf_gain_db, condition_1:hf_gain_db, condition_2:hf_gain_db, condition_3:hf_gain_db, condition_4:hf_gain_db, condition_5:hf_gain_db | dB | minimize / db20 | −∞ … +∞ | — |
| `recovery_up_v` | condition_0:recovery_up_v, condition_1:recovery_up_v, condition_2:recovery_up_v, condition_3:recovery_up_v, condition_4:recovery_up_v, condition_5:recovery_up_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `recovery_down_v` | condition_0:recovery_down_v, condition_1:recovery_down_v, condition_2:recovery_down_v, condition_3:recovery_down_v, condition_4:recovery_down_v, condition_5:recovery_down_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `step_gain` | condition_0:step_gain, condition_1:step_gain, condition_2:step_gain, condition_3:step_gain, condition_4:step_gain, condition_5:step_gain | V/V | target / target | −∞ … +∞ | 1.0 |
| `mean_power_w` | condition_0:mean_power_w, condition_1:mean_power_w, condition_2:mean_power_w, condition_3:mean_power_w, condition_4:mean_power_w, condition_5:mean_power_w | W | minimize / ratio | 0 … +∞ | 1e-12 |
| `peak_v` | condition_0:peak_v, condition_1:peak_v, condition_2:peak_v, condition_3:peak_v, condition_4:peak_v, condition_5:peak_v | V | target / target | 0 … 1.2 | 1.2 |
| `trough_v` | condition_0:trough_v, condition_1:trough_v, condition_2:trough_v, condition_3:trough_v, condition_4:trough_v, condition_5:trough_v | V | target / target | 0 … 1.2 | 1.2 |

Area reference: **82915.92 um2**. 1164 expanded device instances; sum of device/contact envelopes 54901.4182 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

The capability coefficient remains **8**; it is independent of
the reference-relative task score.

## Tools and Submission

Solve budget: **3 hours**.

Discover inputs/resources/feedback through `/protocol/task.json`,
`/protocol/resources.json` and `/protocol/harness.json`. Use the supplied
IHP primitives with KLayout, Magic and ngspice. Write
`/workspace/output/final.gds` and explicitly submit via the harness protocol.
Host configuration, source records and reference answers are outside solver inputs.
