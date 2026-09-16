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

Every bound applies to every corresponding condition. DC metrics measure
output, bias voltage, VDD power and quiescent current `−I(VDD)−ILOAD`;
quiescent current includes on-chip bias and bleeder current. VDD power includes
the supply-fed external bias current and load delivery, but excludes reference
source and bias-generator overhead. `mean_power_w` averages VDD power over
the full 2–18 us load cycle; the supply current stays positive in calibration.
It is not net energy with recovered power credited.

Recovery errors are maxima of `abs(VOUT−0.9)` in 5–9.5 and 13–17.5 us;
minimum/maximum output cover 2–18 us. Startup error is the maximum absolute
reference error in 25–30 us; startup peak and minimum cover 0–30 us.
Line span and load span are maximum minus minimum output over their stated
DC ranges. Each job is evaluated independently; ranges must not hide failure.

| Metric | Unit | Acceptance | Lower / upper zero-score boundaries | Dimension |
| --- | --- | --- | --- | --- |
| `output_v` | V | 0.87–0.93 | 0.7 / 1.1 | bias |
| `bias_v` | V | 0.36–0.42 | 0 / 0.8 | bias |
| `quiescent_a` | A | 6.5e-05–8.5e-05 | 0 / 0.00017 | supply |
| `power_w` | W | 0–0.00085 | 0 / 0.0017 | supply |
| `dc_gain_db` | dB | 40–65 | 0 / 100 | response |
| `unity_hz` | Hz | 2e+06–7e+06 | 0 / 1.4e+07 | response |
| `phase_margin_deg` | deg | 45–95 | 0 / 180 | response |
| `minimum_v` | V | 0.82–0.94 | 0 / 1.2 | response |
| `maximum_v` | V | 0.9–1 | 0.7 / 1.3 | response |
| `recovery_load_v` | V | 0–0.03 | 0 / 0.15 | response |
| `recovery_release_v` | V | 0–0.03 | 0 / 0.15 | response |
| `mean_power_w` | W | 0–0.0013 | 0 / 0.0026 | supply |
| `startup_error_v` | V | 0–0.03 | 0 / 0.15 | response |
| `startup_peak_v` | V | 0.89–1.04 | 0 / 1.3 | response |
| `startup_minimum_v` | V | -0.01–0.01 | -0.2 / 0.2 | response |
| `regulation_floor_v` | V | 0.9–1.2 | 0.8 / 1.3 | response |
| `headroom_v` | V | 0–0.3 | 0 / 0.5 | response |
| `line_span_v` | V | 0–0.015 | 0 / 0.1 | response |
| `load_span_v` | V | 0–0.025 | 0 / 0.1 | response |

Coefficient **8** covers a complete loaded regulation loop, physical storage
and compensation, supply/load/headroom measurements and specified startup.
Unified score is `G × (60E + 20H + 20HQ)`: G requires physical validity and
complete measurements; E averages worst attainment in bias, response and supply;
H requires all electrical bounds; attainment falls linearly to the zero bounds.
Q is `clip((2000000−area)/1500000,0,1)` using absolute area in um², with target
500000 and zero 2000000. These anchors include all MIM storage, resistor
chains, taps and routing. Physical rejection scores zero; incomplete evaluation
cannot establish success or fabricate a score.

## Tools and Submission

Discover inputs, resources and feedback through `/protocol/task.json`,
`/protocol/resources.json` and `/protocol/harness.json`. Use the supplied IHP
primitives, KLayout, Magic and ngspice. Write `/workspace/output/final.gds` and
explicitly submit it through the harness. Host configuration, source records
and reference layouts are outside the standard solver inputs.
