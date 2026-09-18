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
| `output_v` | condition_0:output_v, condition_1:output_v, condition_2:output_v, condition_3:output_v | V | target / target | 0 … 1.3 | 1.3 |
| `bias_v` | condition_0:bias_v, condition_1:bias_v, condition_2:bias_v, condition_3:bias_v | V | target / target | 0 … 1.3 | 1.3 |
| `quiescent_a` | condition_0:quiescent_a, condition_1:quiescent_a, condition_2:quiescent_a, condition_3:quiescent_a | A | minimize / ratio | 0 … +∞ | 1e-12 |
| `power_w` | condition_0:power_w, condition_1:power_w, condition_2:power_w, condition_3:power_w | W | minimize / ratio | 0 … +∞ | 1e-12 |
| `dc_gain_db` | condition_0:dc_gain_db, condition_1:dc_gain_db, condition_2:dc_gain_db, condition_3:dc_gain_db | dB | maximize / db20 | −∞ … +∞ | — |
| `unity_hz` | condition_0:unity_hz, condition_1:unity_hz, condition_2:unity_hz, condition_3:unity_hz | Hz | maximize / ratio | 0 … +∞ | — |
| `phase_margin_deg` | condition_0:phase_margin_deg, condition_1:phase_margin_deg, condition_2:phase_margin_deg, condition_3:phase_margin_deg | deg | target / target | 0 … 180 | 180 |
| `final_unity_hz` | condition_0:final_unity_hz, condition_1:final_unity_hz, condition_2:final_unity_hz, condition_3:final_unity_hz | Hz | maximize / ratio | 0 … +∞ | — |
| `final_phase_margin_deg` | condition_0:final_phase_margin_deg, condition_1:final_phase_margin_deg, condition_2:final_phase_margin_deg, condition_3:final_phase_margin_deg | deg | target / target | 0 … 180 | 180 |
| `minimum_return_distance` | condition_0:minimum_return_distance, condition_1:minimum_return_distance, condition_2:minimum_return_distance, condition_3:minimum_return_distance | 1 | target / target | 0 … +∞ | 1.0 |
| `return_phase_excursion_deg` | condition_0:return_phase_excursion_deg, condition_1:return_phase_excursion_deg, condition_2:return_phase_excursion_deg, condition_3:return_phase_excursion_deg | deg | minimize / ratio | 0 … +∞ | 1e-12 |
| `hf_gain_db` | condition_0:hf_gain_db, condition_1:hf_gain_db, condition_2:hf_gain_db, condition_3:hf_gain_db | dB | minimize / db20 | −∞ … +∞ | — |
| `minimum_v` | condition_0:minimum_v, condition_1:minimum_v, condition_2:minimum_v, condition_3:minimum_v | V | target / target | 0 … 1.3 | 1.3 |
| `maximum_v` | condition_0:maximum_v, condition_1:maximum_v, condition_2:maximum_v, condition_3:maximum_v | V | target / target | 0 … 1.3 | 1.3 |
| `recovery_load_v` | condition_0:recovery_load_v, condition_1:recovery_load_v, condition_2:recovery_load_v, condition_3:recovery_load_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `recovery_release_v` | condition_0:recovery_release_v, condition_1:recovery_release_v, condition_2:recovery_release_v, condition_3:recovery_release_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `mean_power_w` | condition_0:mean_power_w, condition_1:mean_power_w, condition_2:mean_power_w, condition_3:mean_power_w | W | minimize / ratio | 0 … +∞ | 1e-12 |
| `startup_error_v` | startup_0:startup_error_v, startup_1:startup_error_v, startup_2:startup_error_v, startup_3:startup_error_v, startup_4:startup_error_v, startup_5:startup_error_v, startup_6:startup_error_v, startup_7:startup_error_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `startup_peak_v` | startup_0:peak_v, startup_1:peak_v, startup_2:peak_v, startup_3:peak_v, startup_4:peak_v, startup_5:peak_v, startup_6:peak_v, startup_7:peak_v | V | target / target | 0 … 1.3 | 1.3 |
| `startup_minimum_v` | startup_0:minimum_v, startup_1:minimum_v, startup_2:minimum_v, startup_3:minimum_v, startup_4:minimum_v, startup_5:minimum_v, startup_6:minimum_v, startup_7:minimum_v | V | target / target | −∞ … +∞ | 1.3 |
| `regulation_floor_v` | sweeps_0:regulation_floor_v, sweeps_1:regulation_floor_v, sweeps_2:regulation_floor_v, sweeps_3:regulation_floor_v | V | target / target | 0 … 1.3 | 1.3 |
| `headroom_v` | sweeps_0:headroom_v, sweeps_1:headroom_v, sweeps_2:headroom_v, sweeps_3:headroom_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `line_span_v` | sweeps_0:line_span_v, sweeps_1:line_span_v, sweeps_2:line_span_v, sweeps_3:line_span_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `load_span_v` | sweeps_0:load_span_v, sweeps_1:load_span_v, sweeps_2:load_span_v, sweeps_3:load_span_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `fast_peak_v` | fast_0:fast_peak_v, fast_1:fast_peak_v, fast_2:fast_peak_v, fast_3:fast_peak_v | V | target / target | 0 … 1.3 | 1.3 |
| `fast_tail_v` | fast_0:fast_tail_v, fast_1:fast_tail_v, fast_2:fast_tail_v, fast_3:fast_tail_v | V | target / target | 0 … 1.3 | 1.3 |

Area reference: **172708.78 um2**. 126 expanded device instances; sum of device/contact envelopes 114596.5905 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

The capability coefficient remains **9**; it is independent of
the reference-relative task score.

## Tools and Submission

Solve budget: **3 hours**.

Discover inputs, resources and feedback through `/protocol/task.json`,
`/protocol/resources.json` and `/protocol/harness.json`. Use supplied IHP
primitives, KLayout, Magic and ngspice. Write `/workspace/output/final.gds`
and explicitly submit through the harness. Source records, host configuration
and reference layouts stay outside standard solver inputs.
