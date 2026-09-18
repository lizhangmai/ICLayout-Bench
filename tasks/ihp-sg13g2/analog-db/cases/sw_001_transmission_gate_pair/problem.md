# Bidirectional CMOS Transmission Gate Layout Task

## Objective

Implement `sw_001_transmission_gate_pair` with the complete fixed topology and minimize layout-induced degradation under the declared nominal observations. The fixed IHP binding has one NMOS and one PMOS, each W=2 um, L=0.13 um, m=1. Both connect the bidirectional signal terminals, with the NMOS body at vss and PMOS body at vdd. No internal clock generator is added.

## Inputs and Interface

`materials/circuit.cdl` is the authoritative physical netlist; `materials/circuit.spice` is its simulator representation. The supplied SPICE decks are the performance fixtures. `problem.md` is this contract. Ordered ports: `port_a port_b vctl vctl_not vdd vss`. The fixture supplies complementary controls externally. Both signal/control ports stay within 0–1.5 V. Native body taps remain physically checked; finite well/substrate resistances are outside the Magic RC compact-model boundary.

## Operating Conditions

1.5 V supply. DC on/off conditions use signal common modes 0.15, 0.75 and 1.35 V and both signs of a 10 mV port difference. On controls are 1.5/0 V; off controls are 0/1.5 V. Ron is the absolute port drop divided by actual port-source current, accepted only above 1 nA and independently checked for the correct current direction. Off leakage uses held voltages at both terminals. Dynamic tests drive each direction separately through 100 ohm, with a 1 pF receiving load and 1 Mohm resistor to the selected common mode. Signal steps are common-mode ±50 mV with 1 ns edges starting at 20 ns; separate static-input runs isolate control feedthrough. Complementary controls turn off at 70 ns for 60 ns, with matched 1 ns edges, no extra overlap/dead interval. Runs start from DC and end at 180 ns with maximum 50 ps steps. The finite receiving resistance defines the off-node behavior physically. The isolated window-marker source only schedules exact time breakpoints; it connects to no DUT terminal.

All source/candidate jobs share exactly the same fixtures, parameters, nominal TT models and 27 C temperature. Testbench control blocks and frozen runtime parameters define all stimulus and measurement details. Source simulation is independent of the reference GDS. No paper or data-sheet performance number is an acceptance threshold.

## Physical Requirements

Submit a valid GDSII containing top cell `sw_001_transmission_gate_pair`, at most 10485760 bytes. Pass the pinned native DRC profile, named-interface LVS and functional outline checks. Maximum functional width/height are 5000/1000 um. The complete functional layer set is `[[1, 0], [3, 0], [5, 0], [6, 0], [7, 0], [8, 0], [10, 0], [11, 0], [13, 0], [14, 0], [19, 0], [24, 0], [26, 0], [28, 0], [29, 0], [30, 0], [31, 0], [32, 0], [33, 0], [35, 0], [36, 0], [40, 0], [44, 0], [46, 0], [49, 0], [50, 0], [51, 0], [52, 0], [53, 0], [55, 0], [58, 0], [66, 0], [67, 0], [90, 0], [101, 0], [111, 0], [125, 0], [126, 0], [128, 0], [129, 0], [133, 0], [134, 0], [139, 0], [152, 0]]` (layer/datatype pairs); text/annotation geometry is excluded. There are no case-local DRC waivers. Geometry bounds are generous task/resource limits, not an area score anchor.

Post-layout simulation must consume native candidate-GDS-derived distributed wire RC, retaining every physical MOS, resistor and capacitor. Native LVS alone does not substitute for PEX. Magic uses ideal well/substrate tap connections; source simulation retains native finite tap models. This boundary does not establish distributed substrate resistance or substrate-noise accuracy.

## Electrical Requirements and Scoring

Coefficient 3 covers local bidirectional analog conduction and loaded control transitions. Tracking error is integrated over exactly 20–60 ns; control-edge excursion uses the inclusive 69–75 ns sample window; held mean shift compares 90–100 ns with 65–69 ns. These are loaded feedthrough/hold observations, not an intrinsic charge-injection constant or perfect floating-node retention. No energy score is claimed: body-rail current alone cannot measure control and signal-driver energy.

Every required condition must yield finite, valid measurements and pass the functional bounds below. Missing or invalid extraction/measurements are evaluation errors, not low performance scores. Quality uses `layout-v2`: each electrical metric is paired with its same-condition source observation; the worst paired quality determines that metric. Dimension qualities and then applicable dimensions use geometric means. Area quality is area_target / complete functional area; total score is 100 sqrt(electrical_quality × area_quality), with no upper cap.

| Metric | Unit | Definition | Dimension / normalization | Functional bounds |
| --- | --- | --- | --- | --- |
| `ron_ohm` | ohm | 10 mV DC port drop divided by measured port current | response / ratio; scale 1 | lower=0 |
| `on_current_a` | A | Absolute DC on current; excludes numerical-noise division | unscored / functional | lower=1e-09 |
| `leakage_a` | A | Off-state current with both ports held at defined voltages | bias / ratio; scale 1e-12 | lower=0 |
| `kcl_a` | A | External KCL including control and body sources | unscored / functional | lower=0; upper=1e-09 |
| `tracking_error_v` | V | Mean loaded dynamic tracking error, 20–60 ns | response / ratio; scale 0.0001 | lower=0 |
| `feedthrough_v` | V | Output excursion during turn-off, 69–75 ns | response / ratio; scale 0.0001 | lower=0 |
| `hold_shift_v` | V | Finite loaded hold mean 90–100 ns minus 65–69 ns | response / target; scale 0.1 | Finite measurement |

Target normalization preserves the source operating point/transfer using its declared voltage or gain scale. Ratio floors prevent zero-error/noise-floor division; they are numerical normalization units, not acceptance tolerances. Voltage bounds are the declared physical rails; current-validity and KCL bounds distinguish measurements from numerical noise. There is no source-relative performance hard cutoff.

The area anchor is **300 um²**: twice the sum of `(W + 6 um) × (L + 8 um)` over every expanded MOS and physical passive unit (2 units, sum 130.080000 um²), rounded upward to 100 um². Contact/well/tap/isolation envelopes are included in the 6/8 um allowances; the factor two allows routing. This is an engineering compact-footprint estimate, independent of measured witness area, not a foundry minimum or demonstrated optimum. Task coefficient: **3**.

## Tools and Submission

Solve budget: **8 hours**.

Use the runtime task and reviewed PDK resource bundle for the declared native checks, extraction and ngspice measurements. Write `output/final.gds` with the required top cell, then explicitly submit its path through the session submission interface; creating a file alone is not submission. Reference GDS, qualification results and development sources are excluded from standard solver inputs.
