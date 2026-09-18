# Auxiliary Source-Driven Output-Control OTA Layout Task

## Objective

Lay out `amp_012_peng_tcfc` with its complete transistor signal and bias paths.
The PMOS-input folded stage produces `voutp`, driving the output PMOS and
`net043` branch. The large PMOS path through `net049` feeds `net10`, while
`net043` controls its NMOS pulldown. `net10` drives the output NMOS. Preserve
both original compensation branches and the added local output-control MIM.
Unlike a direct `net050/net049` output stage, this circuit includes the
source-driven auxiliary PMOS and a separate `net10` control node.

## Inputs and Interface

- `materials/circuit.cdl`: authoritative native physical graph.
- `materials/circuit.spice`: equivalent simulator graph with finite body taps.
- `materials/testbench.spice`: DC, bilateral-loop and sustained-step measurements.

Ordered ports: `vss vdd vinn vinp vout vb1`. VSS/VDD are return/supply;
VINN/VINP are inverting/noninverting inputs; VOUT is output; `vb1`
connects to the external bias sink. Input PMOS bodies use the separate
`net31` source-tied well; other PMOS use VDD and NMOS use the VSS substrate.
Preserve all 32 MOS groups, 108 physical fingers,
W/L/m, every body connection and all physical passive devices.

MOS dimensions are rounded to the 10 nm physical grid. Parallel regrouping
within each original group preserves its rounded total W and L, with at most
10 um single-finger width; individual width/multiplicity and diffusion perimeter
change. Distributed 2 × 2 um body contacts have at most 20 um pitch.
All internal capacitors use `cap_cmim`:

- `c0`: `voutp` (top) to `vout` (bottom), 1 parallel 35.325 × 35.325 um MIM units.
- `c1`: `net049` (top) to `vout` (bottom), 1 parallel 41.2 × 41.2 um MIM units.
- `clocal`: `net10` (top) to `vout` (bottom), 1 parallel 51.64 × 51.64 um MIM units.

The raw 1.29849 uA sink is calibrated to 0.16231125 uA. A real approximately
4 pF `net10–vout` MIM is added to suppress the internal output-control
oscillation. Both original 1.87196 pF `voutp–vout` and 2.54606 pF
`net049–vout` branches remain. There is no added output-to-ground capacitor.
No ideal servo, diagnostic clamp or hidden damping element is part of this DUT.

## Operating Conditions

Use typical IHP LV MOS/MIM/poly models at 27 C and VDD=1.2 V, with a
0.162311 uA sink from `vb1` to VSS. All combinations of external
5/10/15 pF load and 0.5/0.7 V DC input must pass. These external loads are
additional to every internal capacitor above.

A zero-volt source connects VINN (`vm`) to VOUT. VINP is AC ground.
Use series voltage and parallel current injection at that boundary, retaining
the complete DUT and loading. With voltage-injection `b=-I(VPROBE)`,
`d=V(vm)` and current-injection `a=-I(VPROBE)`, `c=V(vm)`, set
`delta=a*d-b*c` and `T=(2*delta-a+d)/(1-2*delta+a-d)` (Tian Eq. 30).
Both raw injections are exported for independent Y-matrix reconstruction.
Sweep 0.01 Hz–10 GHz at 300 points/decade. Continuous phase uses its natural
low-frequency branch without an offset correction. Check first and final
descending unity crossings, minimum sampled `abs(1+T)`, maximum absolute
continuous phase of `1+T` across the entire sweep, and gain over 2–10 GHz.
A good first crossover alone cannot establish acceptance.

VINP pulses 0.5→0.7→0.5 V with 20 ns edges, rising at 2 us and falling
at 20.02 us, period 100 us. Transient starts at its own pulse-start operating
point, independently of the AC DC-input setting. Simulate 0–40 us with Gear2,
2 ns maximum step, KLU, `itl4=1000`, `rshunt=1e12`, `reltol=1e-5`,
`abstol=1e-12`, `vntol=1e-8`. The numerical shunt is not a physical device.
Qualification also checks half step, tighter tolerances/dense AC, trapezoidal
integration, long tails and finite stimulus/load boundaries.
These are finite external-loop and observable-recovery requirements, not an
internal pole inventory, arbitrary-load stability, PVT, noise, mismatch,
distortion, rail-to-rail behavior or supply-startup qualification.

## Physical Requirements

Submit GDSII top cell `amp_012_peng_tcfc`, at most 32 MiB. Native IHP main/maximal DRC
must pass without waivers (standalone scope, density/antenna off), together
with strict named-interface LVS and a 1400 × 160 um functional envelope.
All device/contact/interconnect drawing layers in the runtime `outline`
constraint contribute to area; annotation/pin-purpose layers do not.
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

Area reference: **14710.04 um2**. 180 expanded device instances; sum of device/contact envelopes 9648.5648 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

The capability coefficient remains **8**; it is independent of
the reference-relative task score.

## Tools and Submission

Solve budget: **3 hours**.

Discover inputs/resources/feedback through `/protocol/task.json`,
`/protocol/resources.json` and `/protocol/harness.json`. Use supplied IHP
primitives with KLayout, Magic and ngspice. Write `/workspace/output/final.gds`
and explicitly submit through the harness. Host configuration, source records
and reference answers remain outside solver inputs.
