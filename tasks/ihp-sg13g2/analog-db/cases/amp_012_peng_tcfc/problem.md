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

`output_error_v=abs(VOUT−VINP)` applies independently at each DC level.
`bias_v` is the bias port voltage. `power_w` and `mean_power_w` are positive
VDD-supplied power at DC and over 2–40 us, including the on-chip bias network;
external bias-generator overhead is excluded and sink energy is not credited.
`dc_gain_db` is `db(T)` at 0.01 Hz. Phase margin is `180+phase(T)` at the
respective first/final descending crossing. Full-sweep return-distance/phase
and high-frequency bounds apply independently, as defined above.

`recovery_up_v`/`recovery_down_v` are maximum `abs(VOUT−VINP)` over
15–19 us / 30–39 us. They require sustained tracking, not a first band entry
or a final point. `step_gain` is the difference of mean output in 18–19 us
and 38–39 us divided by 0.2 V. `peak_v` is maximum output in 2–20 us;
`trough_v` is minimum output in 20.04–40 us. Extrema use in-window samples;
reference verification also checks interpolated endpoints and independently
integrated means. All bounds apply separately to all six conditions.

| Metric | Unit | Acceptance | Lower / upper zero-score boundaries | Dimension |
| --- | --- | --- | --- | --- |
| `output_v` | V | 0.495–0.705 | 0.4 / 0.8 | bias |
| `output_error_v` | V | 0–0.002 | 0 / 0.02 | bias |
| `bias_v` | V | 0.8–0.86 | 0 / 1.2 | bias |
| `power_w` | W | 0–2e-05 | 0 / 6e-05 | supply |
| `dc_gain_db` | dB | 95–115 | 40 / 140 | response |
| `unity_hz` | Hz | 300000–450000 | 0 / 900000 | response |
| `phase_margin_deg` | deg | 50–90 | 0 / 180 | response |
| `final_unity_hz` | Hz | 300000–450000 | 0 / 900000 | response |
| `final_phase_margin_deg` | deg | 50–90 | 0 / 180 | response |
| `minimum_return_distance` | 1 | 0.4–1.1 | 0 / 2 | response |
| `return_phase_excursion_deg` | deg | 0–110 | 0 / 180 | response |
| `hf_gain_db` | dB | -300–-20 | -400 / 0 | response |
| `recovery_up_v` | V | 0–0.002 | 0 / 0.02 | response |
| `recovery_down_v` | V | 0–0.002 | 0 / 0.02 | response |
| `step_gain` | V/V | 0.98–1.02 | 0.8 / 1.2 | response |
| `mean_power_w` | W | 0–2e-05 | 0 / 6e-05 | supply |
| `peak_v` | V | 0.695–0.75 | 0.5 / 1.2 | response |
| `trough_v` | V | 0.47–0.505 | 0 / 0.7 | response |

Coefficient **8** reflects coupled physical compensation, multistage feedback,
loaded stability and sustained recovery. Unified `layout-v1` score is
`G × (60E + 20H + 20HQ)`: G requires physical validity and complete valid
measurements, E averages worst attainment in response/bias/supply, and H
requires every bound. Attainment decreases linearly to the listed zero bounds.
Q is `clip((640000−area)/480000,0,1)`, with absolute area target
160,000 um² and zero at 640,000 um². These include all MOS, MIM,
taps and routing and do not depend on a changing reference layout.
Physical rejection scores zero; execution errors do not fabricate a score.

## Tools and Submission

Discover inputs/resources/feedback through `/protocol/task.json`,
`/protocol/resources.json` and `/protocol/harness.json`. Use supplied IHP
primitives with KLayout, Magic and ngspice. Write `/workspace/output/final.gds`
and explicitly submit through the harness. Host configuration, source records
and reference answers remain outside solver inputs.
