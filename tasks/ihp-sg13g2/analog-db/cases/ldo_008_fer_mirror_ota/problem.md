# Mirror-OTA Regulator with Bilateral Return-Ratio Measurements Layout Task

## Objective

Implement `ldo_008_fer_mirror_ota`: a mirror-loaded NMOS-input error amplifier,
diode/tail bias network, PMOS pass device, feedback divider and series R/C
compensation. Preserve all seven source MOS groups as 81 physical fingers,
40 MIM units and three high-poly resistors, with explicit substrate/well taps.
The internal compensation and divider remain part of the DUT.

MOS dimensions and multiplicities are unchanged from the fixed IHP binding.
The source 160 pF capacitor becomes forty 51.64 um square MIM units, nominally
160.331872 pF total. The source 2 kohm compensation resistor becomes one
W=1 um / L=1.325 um `rhigh`; each source 9 kohm divider resistor becomes one
W=1 um / L=6.235 um `rhigh`, with m=1 and b=0. Source capacitor PLUS is
`czero`, MINUS is `vout`; the series resistor connects `egate` to `czero`.
Divider upper/lower connect `vout–fb` and `fb–vss`. Every passive stays physical.

The external source bias is unchanged at 20 uA from VDD to NBIAS. The external
reference is deliberately changed from the source 0.6 V to **0.5 V**, giving
a nominal 1.0 V output and defined headroom at 1.2/1.3 V supply. There is no
separate internal or external COUT; compensation still provides physical
output-connected capacitance. This is not a claim of zero internal storage.

## Inputs and Interface

- `materials/circuit.cdl`: authoritative native LVS circuit.
- `materials/circuit.spice`: equivalent simulator representation.
- `materials/testbench.spice`: DC bias, bilateral loop measurements and load steps.
- `materials/startup.spice`: zero-state resistive-load startup.
- `materials/sweeps.spice`: DC line/load and regulation-headroom sweeps.
- `materials/fast.spice`: short, finely resolved load-impulse response.

Ordered ports: `vdd vout vss nbias vref fb sense`. VDD/VSS are supply/return;
VOUT is output; NBIAS receives the supply-fed current; VREF receives the 0.5 V
reference. FB is the physical divider junction and SENSE is the amplifier's
feedback-input gate. Connect SENSE externally to FB through the zero-volt
measurement source. This external link replaces the raw VLP's measurement role;
it is not a manufactured voltage source. The relocated break exposes the
actual input/divider boundary; the upper divider still connects to output.
PMOS bodies connect through the VDD well tap; NMOS/poly bodies through the VSS
tap. Preserve every W/L/m, body connection and physical passive. Equivalent
parallel finger arrangements require native LVS and every other check to pass.

## Operating Conditions

Use typical IHP LV MOS, MIM and resistor models at 27 C. Main conditions are
all combinations of VDD=1.2/1.3 V and initial load 0.1/0.5 mA. The current
load doubles at 2–2.02 us and returns at 10.02–10.04 us. Run to 18 us with
1 ns maximum step, Gear order 2, `rshunt=1e12`, `reltol=1e-5`, `abstol=1e-14`
and `vntol=1e-8`. Startup and fast tests use the same accuracy tolerances.

For AC, independent supply/reference/load sources have no AC excitation.
Perform two sweeps, 0.01 Hz–1 GHz at 300 points/decade, at the same operating
point. VPROBE is oriented SENSE→FB and IINJ from ground→SENSE. Both have
zero DC value and are ordinary external test sources. First set VPROBE AC=1 V,
IINJ AC=0; second set VPROBE AC=0, IINJ AC=1 A. The 1 A is only a normalized
linear AC excitation, not a physical large-signal load.

Let B=−I(VPROBE)/1 V and D=V(SENSE)/1 V from the first sweep; A=−I(VPROBE)/1 A
and C=V(SENSE)/1 A from the second. With delta=AD−BC, define
`T=(2*delta−A+D)/(1−2*delta+A−D)`. This bilateral two-port return ratio includes
both directional transmissions and port loading. The old voltage-only
`−V(FB)/V(SENSE)` is not the accepted loop metric. Reset the circuit before
transient analysis; neither AC experiment changes its DC or transient topology.

This measures the declared external feedback loop with the internal circuit
retained. It is not an exhaustive pole proof for all internal device loops or
an RF/model-validity claim beyond the declared tests. Multiple unity crossings
are allowed only with the full-frequency return-difference and final-crossing
requirements below; the first phase margin alone is insufficient.

Startup uses 1/10 kohm loads and simultaneous linear supply/reference/bias
ramps from zero over 1/10 us: eight combinations including both supplies.
Run with `uic`, no internal-node initial conditions, to 30 us with 2 ns
maximum step. Startup qualification is resistive-load and synchronized-ramp
only, not arbitrary reference sequencing or constant-current startup.

DC sweeps: supply decreases from 1.3 to 0.8 V by 1 mV at 0.1/1 mA; line
span is measured over 1.2–1.3 V. Regulation floor is the first increasing
crossing of `abs(VOUT−1.0)=0.03 V`. Headroom is supply **minus actual output at
that crossing**, not supply minus the nominal target. The lower supply sweep
is a boundary probe, not an extended qualified operating range. Separately
sweep load 0.1–1 mA by 10 uA at each qualified supply, retaining both endpoints.

Fast conditions use the four main DC biases and a +1 uA load pulse beginning
at 1 ns, 5 ps rise/fall and 1 ns high time. Run 100 ns with 5 ps maximum step.
It probes fast recovery around the solved operating point without modifying
compensation, adding an output capacitor or clamping an internal node.

Transient extrema and AC sweep screens use the saved in-window samples;
DC crossing locations and mean power use interpolation/integration. Numerical
qualification also checks interpolated recovery-window endpoints.

## Physical Requirements

Submit GDSII top cell `ldo_008_fer_mirror_ota`, at most 10 MiB. Native main/maximal
DRC has no waivers (standalone scope, density/antenna disabled). Strict named-port
LVS includes physical taps. Functional outline is at most 3350 × 310 um and
includes all device, passive, contact and routing drawing layers; annotation
and pin-purpose layers do not contribute. Magic candidate RC must preserve
all physical MOS/MIM/poly and interconnect parasitics. Half-grid import is
explicit; extraction idealizes taps whereas source simulation uses their finite
models. Distributed substrate resistance, PVT, mismatch, noise, fabrication
signoff and arbitrary-load stability are outside qualification.

## Electrical Requirements and Scoring

Every metric applies independently to every corresponding condition. Main DC
metrics observe output, bias and VDD power. Quiescent current is
`−I(VDD)−ILOAD`, including the bias and divider. Mean power averages
`−VDD*I(VDD)` over 2–18 us; calibrated supply current remains forward throughout
that window. Supply-fed bias current and load delivery are included; reference
and bias-generator overhead are excluded. Recovered energy is not credited.

Gain is `20*log10(abs(T))`. `unity_hz` and `phase_margin_deg` use the first
falling 0 dB crossing; `final_unity_hz` and `final_phase_margin_deg` use the last
falling crossing. Margins use 180 degrees plus continuous phase, without a
fitted offset. `minimum_return_distance` is minimum `abs(1+T)` over the complete
sweep. `return_phase_excursion_deg` is maximum absolute continuous phase of
`1+T`; its bound excludes crossing the negative real axis in the sampled
positive-frequency return-difference trace. `hf_gain_db` is maximum gain from
200 MHz to 1 GHz. Missing required crossings/measurements are errors.

Main output extrema cover 2–18 us. Recovery errors are maxima of
`abs(VOUT−1.0)` in 5–9.5 and 13–17.5 us. Startup error is its maximum in
25–30 us; startup extrema cover 0–30 us. Line/load spans are maximum minus
minimum output in their stated ranges. Fast error is absolute deviation from
the solved DC output: peak over 0–100 ns and tail maximum over 80–100 ns.

| Metric | Unit | Acceptance | Lower / upper zero-score boundaries | Dimension |
| --- | --- | --- | --- | --- |
| `output_v` | V | 0.97–1.03 | 0.7 / 1.3 | bias |
| `bias_v` | V | 0.3–0.35 | 0 / 0.7 | bias |
| `quiescent_a` | A | 0.00013–0.00016 | 0 / 0.00032 | supply |
| `power_w` | W | 0–0.0009 | 0 / 0.0018 | supply |
| `dc_gain_db` | dB | 30–60 | 0 / 100 | response |
| `unity_hz` | Hz | 300000–1.5e+06 | 0 / 3e+06 | response |
| `phase_margin_deg` | deg | 110–175 | 0 / 180 | response |
| `final_unity_hz` | Hz | 300000–9e+07 | 0 / 1.8e+08 | response |
| `final_phase_margin_deg` | deg | 60–175 | 0 / 180 | response |
| `minimum_return_distance` | 1 | 0.4–2 | 0 / 4 | response |
| `return_phase_excursion_deg` | deg | 0–120 | 0 / 180 | response |
| `hf_gain_db` | dB | -100–-3 | -160 / 0 | response |
| `minimum_v` | V | 0.92–1.01 | 0 / 1.3 | response |
| `maximum_v` | V | 1–1.09 | 0.7 / 1.3 | response |
| `recovery_load_v` | V | 0–0.03 | 0 / 0.15 | response |
| `recovery_release_v` | V | 0–0.03 | 0 / 0.15 | response |
| `mean_power_w` | W | 0–0.0013 | 0 / 0.0026 | supply |
| `startup_error_v` | V | 0–0.03 | 0 / 0.15 | response |
| `startup_peak_v` | V | 0.97–1.04 | 0 / 1.3 | response |
| `startup_minimum_v` | V | -0.01–0.01 | -0.2 / 0.2 | response |
| `regulation_floor_v` | V | 0.97–1.2 | 0.8 / 1.3 | response |
| `headroom_v` | V | 0–0.25 | 0 / 0.5 | response |
| `line_span_v` | V | 0–0.015 | 0 / 0.1 | response |
| `load_span_v` | V | 0–0.03 | 0 / 0.1 | response |
| `fast_peak_v` | V | 0–0.0006 | 0 / 0.003 | response |
| `fast_tail_v` | V | 0–2e-06 | 0 / 1e-05 | response |

Coefficient **9** reflects a complete regulation loop, physical compensation
and divider, bilateral loop measurements, DC boundaries, startup and two time
scales of loaded recovery. Unified `layout-v1` score is
`G × (60E + 20H + 20HQ)`: G requires physical validity and complete measurements;
E averages worst attainment in bias, response and supply; H requires every
bound. Attainment falls linearly to the stated zero boundaries. Q is
`clip((4400000−area)/3300000,0,1)` with absolute area target 1100000 and zero
4400000 um². These fixed anchors cover 40 physical MIM units, all transistor
fingers, resistors, taps and routing. Physical rejection scores zero;
incomplete evaluation cannot establish success or manufacture a score.

## Tools and Submission

Discover inputs, resources and feedback through `/protocol/task.json`,
`/protocol/resources.json` and `/protocol/harness.json`. Use supplied IHP
primitives, KLayout, Magic and ngspice. Write `/workspace/output/final.gds`
and explicitly submit through the harness. Source records, host configuration
and reference layouts stay outside standard solver inputs.
