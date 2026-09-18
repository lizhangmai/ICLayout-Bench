# Unity-Feedback Regulator with Internal Output Storage Layout Task

## Objective

Lay out `ldo_009_fer_5t_pass` with the complete physical error amplifier, pass array,
compensation, output storage, bleeder and reference path.

A five-transistor NMOS-input error amplifier drives a PMOS pass array;
an on-chip diode-connected NMOS biases the tail mirror. The maintained circuit
retains all seven source MOS groups (29 physical fingers), the output bleeder,
reference-series resistor, Miller path and internal output capacitor. Unity
feedback senses output directly; there is no feedback divider. This adds
physical output storage, a reference impedance, explicit return ratio and
zero-state startup to the existing externally loaded regulator coverage.

The original 2 pF Miller compensation is deliberately retuned to five physical
36.515 um square units, nominally 10.0293 pF. Thirteen 50.635 um square MIM
units retain the approximately 50 pF internal COUT. Four physical high-poly
segments implement the approximately 100 kohm bleeder and one implements
approximately 10 kohm reference resistance. MOS dimensions and multiplicities
are unchanged; explicit substrate/well taps are added. The 20 uA bias source
and 0.9 V reference are external. The raw zero-volt loop measurement source
becomes an external zero-volt link between distinct output and sense ports;
it is not a manufactured voltage-source device or an ideal common-mode servo.


## Inputs and Interface

- `materials/circuit.cdl`: authoritative native LVS circuit.
- `materials/circuit.spice`: matching process-model representation.
- `materials/testbench.spice`: operating point, return ratio and load steps.
- `materials/startup.spice`: distinct zero-state resistive-load startup deck.
- `materials/sweeps.spice`: distinct DC line/load and headroom sweeps.

Ordered ports: `vdd vout vss nbias ref0 sense`. VDD/VSS are supply/return;
VOUT is regulated output; NBIAS receives an external 20 uA source **from VDD**;
REF0 receives an external 0.9 V reference; SENSE connects externally to VOUT
through the zero-volt probe. Preserve this explicit high-impedance feedback
interface. No other drive is permitted on SENSE, and no extra internal servo
or reference generator is part of the DUT. PMOS bodies connect to the VDD
well through its tap; NMOS/poly bodies connect through the VSS substrate tap.
Preserve all W/L/m and internal connectivity; equivalent parallel fingers
are permitted only when native LVS and all measurements pass.

All following passives remain physical DUT devices, not external loads or
parasitic annotations:

- `cmil`: `vout` to `otao`, 5 parallel 36.515 × 36.515 um MIM units, nominal total 10.029301 pF.
- `cout`: `vout` to `vss`, 13 parallel 50.635 × 50.635 um MIM units, nominal total 50.101434 pF.
- `rbld`: `vout` to `vss`, 4 series high-poly segments, each W=1 um / L=17.465 um, m=1 and b=0.
- `rref`: `ref0` to `vref`, 1 series high-poly segments, each W=1 um / L=6.94 um, m=1 and b=0.

## Operating Conditions

Use typical LV MOS, MIM and resistor models at 27 C. Qualification uses
VDD=1.2/1.3 V and REF0=0.9 V. The main deck starts from a solved operating
point with 0.1/0.5 mA constant-current loads; each doubles at 2–2.02 us and
returns at 10.02–10.04 us. Run to 18 us with 1 ns maximum step, Gear order 2,
`rshunt=1e12`, `reltol=1e-5`, `abstol=1e-14`, `vntol=1e-8`.
There is no external output capacitor: internal COUT remains in candidate RC.

AC injects 1 V in series with the zero-volt output-to-SENSE link. Reference,
supply and current sources have zero AC drive. At the high-impedance MOS input
boundary, `T=-V(vout)/V(sense)` defines return ratio. Sweep 0.01 Hz–1 GHz
at 150 points/decade. Gain uses `20 log10(abs(T))`; continuous phase has no
fitted offset. Unity frequency is the first descending 0 dB crossing and phase
margin is 180 degrees plus phase there. Missing crossings are errors.

Startup separately uses 900/9000 ohm output loads, with supply, reference and
bias ramped linearly together from zero over 1/10 us. Use `uic`, no internal
node initial conditions and 2 ns maximum step to 30 us. The load is resistive
throughout startup; this is not constant-current startup qualification. All
eight supply/load/ramp combinations must pass. After startup, the main deck's
constant-current load contract and its finite recovery windows apply separately.

DC sweeps use the same numerical tolerances. Sweep supply downward from 1.3
to 0.8 V in 1 mV steps at 0.1/1 mA; measure line span only over 1.2–1.3 V.
The **regulation floor** is the first rising crossing of
`abs(VOUT−0.9)=0.03 V` on that downward sweep. `headroom_v` is this supply
minus 0.9 V. This includes error-amplifier headroom or pass-device limitation;
it is not a pass-resistance-only dropout rating. The sweep below the floor is
a boundary probe and is not a qualified low-supply operating range. Separately,
sweep load 0.1–1 mA in 10 uA steps at each qualified supply for load span.

## Physical Requirements

Submit GDSII top cell `ldo_009_fer_5t_pass`, at most 10 MiB. Pass native main/maximal
DRC with no waivers (standalone scope, density/antenna disabled), strict
named-interface LVS including taps, and a 1600 × 330 um functional envelope.
The runtime outline includes complete device/contact/routing drawing layers;
annotation and pin-purpose layers do not contribute to bounding-box area.
Candidate Magic RC must retain all physical MOS/MIM/poly and interconnect
parasitics. Half-grid GDS import is explicit. Magic idealizes tap connections;
source simulation uses finite contact models. Distributed substrate resistance,
noise, PVT, mismatch, arbitrary startup/reference sequencing, brownout and
fabrication signoff remain unqualified.

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

Area reference: **65470.09 um2**. 54 expanded device instances; sum of device/contact envelopes 43312.7759 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

The capability coefficient remains **8**; it is independent of
the reference-relative task score.

## Tools and Submission

Solve budget: **3 hours**.

Discover inputs, resources and feedback through `/protocol/task.json`,
`/protocol/resources.json` and `/protocol/harness.json`. Use the supplied IHP
primitives, KLayout, Magic and ngspice. Write `/workspace/output/final.gds` and
explicitly submit it through the harness. Host configuration, source records
and reference layouts are outside the standard solver inputs.
