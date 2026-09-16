# Multistage Error-Amplifier PMOS Regulator Layout Task

## Objective

Lay out `ldo_001_analoggym_basic`: a PMOS pass regulator with a folded
PMOS-input error amplifier, cascoded bias branches, mirrored loads and an
additional PMOS/NMOS intermediate branch driving the pass-gate node `net1`.
The auxiliary PMOS source and body connect to `net1`; the input pair has a
separate source-tied `net20` well. Internal compensation connects `net106`
to output and the 3:1 physical divider returns one quarter of output voltage.
This complete multistage error amplifier and its internal pass-gate drive
are distinct from the simpler 5T and mirror-OTA regulator cases.

## Inputs and Interface

- `materials/circuit.cdl`: authoritative native physical circuit.
- `materials/circuit.spice`: matching simulator circuit with finite taps.
- `materials/testbench.spice`: bilateral loop and current-load recovery.
- `materials/startup.spice`: synchronized zero-state resistive startup.
- `materials/sweeps.spice`: line/load and downward headroom sweeps.

Ordered ports: `vdd vout vss ib vref vfb sense`. VDD/VSS are supply/return,
VOUT output, IB connects an external current sink to VSS, and VREF is the
external reference. VFB is the physical divider midpoint and SENSE is the
inverting error-amplifier input. Connect them only through the testbench's
zero-volt injection link; no additional servo or feedback element is permitted.
The source's zero-volt output measurement link is collapsed into VOUT and
relocated to this explicitly declared divider/input boundary.

Retain all 24 source MOS groups. Integer regrouping converts 1,168 source
fingers into 831 physical fingers with <=10 um individual width, preserving
each original group's total W, L and body connection exactly. Individual W/m
and diffusion perimeter change, so the maintained simulator and extracted
candidate are qualified independently. Other PMOS bodies use the VDD well;
NMOS bodies and physical high-poly backplates use the VSS substrate contact.
Explicit 2 x 2 um substrate/well taps use <=20 um pitch. Preserve the current
native circuit's dimensions and total multiplicities; equivalent parallel
fingering requires all physical and electrical checks to pass.

All internal passives are physical DUT elements:

- Three parallel 42.685 × 42.685 um `cap_cmim` units: top `net106`, bottom VOUT;
  approximately 8.22 pF total, retaining the source's approximately 8.2 pF branch.
- One 51.64 × 51.64 um `cap_cmim`: top `net10`, bottom VOUT, approximately
  4 pF. This added physical local compensation closes the internal dynamic mode.
- Twelve series `rhigh` segments from VOUT to VFB and four from VFB to VSS,
  each W=1 um, L=17.465 um, b=0: approximately 300/100 kohm total.

There is no additional external output capacitor, but the compensation is
real output-connected storage. Do not delete or idealize any internal passive.

## Operating Conditions

Use typical IHP LV MOS/MIM/poly models at 27 C. VDD is 1.2 or 1.3 V,
VREF=0.225 V, and the external IB-to-VSS sink is 8 uA. The reference is
explicitly changed from the normalized source's 0.4 V: the 3:1 divider then
has a 0.9 V ideal output target, within the LV supply. The 8 uA bias and
all original total MOS widths/lengths are retained. This is a bounded
regulator core, not a precision reference, PVT or manufacturing-signoff task.

Main measurements cover both supplies and initial current loads 0.2/0.5 mA.
After an operating point, the load doubles at 2–2.2 us, remains high for
8 us, and returns at 10.2–10.4 us; the period is 16 us. Simulate 0–18 us
with KLU, Gear order 2, maximum step 1 ns, `rshunt=1e12`, `reltol=1e-5`,
`abstol=1e-12` and `vntol=1e-8`. The numerical shunt is not a physical
bias or startup device. Explicit `.save` lists retain all measured vectors;
every extracted circuit element still participates in the solve.

Measure the bilateral return ratio at the actual divider/input boundary:
first inject unit series AC voltage from SENSE to VFB, with zero parallel
current; then use zero series voltage and unit current into SENSE. With
first-run `b=-I(VPROBE)`, `d=V(SENSE)` and second-run `a=-I(VPROBE)`,
`c=V(SENSE)`, define `delta=a*d-b*c` and
`T=(2*delta-a+d)/(1-2*delta+a-d)` (Tian et al., Eq. 30).
Both injections retain divider, input and reverse-path loading. Exported
voltages/currents permit an independent two-port admittance calculation.
Sweep 0.01 Hz–1 GHz at 300 points/decade, using continuous natural phase
without an arbitrary low-frequency offset. Check first/final descending
unity crossings, minimum sampled `abs(1+T)`, full sampled return-difference
phase and maximum 200 MHz–1 GHz gain. This finite external-loop contract
is not an exhaustive proof of all internal poles.

Sweep load 0.2–1 mA in 10 uA steps at each supply. Downward VDD sweeps
1.3–0.8 V in 1 mV steps at 0.2/1 mA measure the first 30 mV output-error
crossing. The line span uses both endpoints of 1.2–1.3 V. The regulation
floor includes amplifier headroom and is not a pass-resistance-only dropout
rating. These DC sweeps do not extend dynamic stability to every intermediate
supply/load combination.

Startup uses `uic` with supply, reference and bias ramping together from zero
in 10 or 20 us. For both supplies, use 900/4500 ohm resistive loads (nominally
1/0.2 mA at 0.9 V), maximum step 2 ns, and simulate to 50 us. This does not
qualify arbitrary sequencing or a constant-current load imposed at zero supply.
Faster 1 us startup and 20 ns current-load edges are outside qualification: they
produce excessive peaks in the same extracted circuit. The README provides
runnable failure probes. The maintained contract explicitly narrows the
initial development stimuli without relaxing the voltage-excursion bounds.
Loads below 0.2 mA are outside the qualified dynamic range.

## Physical Requirements

Submit GDSII top cell `ldo_001_analoggym_basic`, at most 32 MiB. Pass native
IHP main/maximal DRC without waivers (standalone density/antenna disabled),
strict named-interface LVS with explicit taps, and a 5500 × 360 um functional
envelope. All device/contact/interconnect drawing layers in the runtime
`outline` contribute to area; annotation and pin-purpose layers do not.

Candidate-derived Magic RC includes both capacitor plates, every poly segment,
MOS and interconnect parasitic. Half-grid import and zero parasitic thresholds
are explicit. Native LVS checks the original GDS's tap labels; the Magic
extraction copy retains only Metal3 interface text, avoiding internal well-name
aliases without altering geometry. Magic idealizes well/substrate taps while
source simulation includes their finite models. Distributed substrate
resistance/noise and fabrication signoff remain unqualified.

## Electrical Requirements and Scoring

Every applicable operating point must independently pass every bound below.
Incomplete measurements establish neither success nor a fabricated score.

DC `output_v` is VOUT, `bias_v` is IB voltage, `power_w` is `-VDD*I(VDD)`,
and `quiescent_a` is supplied current minus load current. `mean_power_w`
averages VDD-supplied power over 2–18 us. Include on-chip bias consumption;
exclude external reference/bias-generator overhead and do not credit sink
energy as recovered supply power.

`dc_gain_db` is `db(T)` at 0.01 Hz. `unity_hz` and `phase_margin_deg` use
the first descending unity crossing; `final_*` uses the last. Phase margin
is `180+phase(T)` at the applicable crossing. `minimum_return_distance`
and `return_phase_excursion_deg` respectively bound the minimum `abs(1+T)`
and maximum absolute continuous phase of `1+T` over the complete sweep.
`hf_gain_db` is maximum `db(T)` over 200 MHz–1 GHz. Missing crossings are errors.

`minimum_v`/`maximum_v` are VOUT extrema over 2–18 us. Recovery metrics
are maximum `abs(VOUT−0.9)` over 5–9.5 us and 13–17.5 us. Separately,
`loaded_ripple_v` and `released_ripple_v` are peak-to-peak VOUT over
9–9.5 us and 17–17.5 us; a wide error band alone cannot hide persistent
oscillation. Startup error is maximum `abs(VOUT−0.9)` over 40–49 us;
startup peak/minimum cover the entire 0–50 us interval.

`line_span_v` and `load_span_v` are full-window maximum minus minimum of
the respective DC sweeps. `regulation_floor_v` is the first downward-supply
30 mV error crossing; `headroom_v` subtracts the interpolated output there.
Ngspice extrema use in-window samples; calibration also checks interpolated
endpoints. Measurement windows and sweep endpoints must remain complete.

| Metric | Unit | Acceptance | Lower / upper zero-score boundaries | Dimension |
| --- | --- | --- | --- | --- |
| `output_v` | V | 0.87–0.93 | 0.7 / 1.1 | bias |
| `bias_v` | V | 0.67–0.84 | 0 / 1.3 | bias |
| `quiescent_a` | A | 0–0.00011 | 0 / 0.00022 | supply |
| `power_w` | W | 0–0.0009 | 0 / 0.0018 | supply |
| `dc_gain_db` | dB | 40–65 | 0 / 100 | response |
| `unity_hz` | Hz | 400000–1e+06 | 0 / 2e+06 | response |
| `phase_margin_deg` | deg | 65–110 | 0 / 180 | response |
| `final_unity_hz` | Hz | 400000–1e+06 | 0 / 2e+06 | response |
| `final_phase_margin_deg` | deg | 65–110 | 0 / 180 | response |
| `minimum_return_distance` | 1 | 0.5–1.1 | 0 / 2 | response |
| `return_phase_excursion_deg` | deg | 0–110 | 0 / 180 | response |
| `hf_gain_db` | dB | -300–-30 | -400 / 0 | response |
| `minimum_v` | V | 0.84–0.91 | 0.6 / 1.2 | response |
| `maximum_v` | V | 0.88–0.95 | 0.7 / 1.3 | response |
| `recovery_load_v` | V | 0–0.03 | 0 / 0.15 | response |
| `recovery_release_v` | V | 0–0.03 | 0 / 0.15 | response |
| `mean_power_w` | W | 0–0.0012 | 0 / 0.0024 | supply |
| `loaded_ripple_v` | V | 0–0.001 | 0 / 0.03 | response |
| `released_ripple_v` | V | 0–0.001 | 0 / 0.03 | response |
| `startup_error_v` | V | 0–0.03 | 0 / 0.15 | response |
| `startup_peak_v` | V | 0.87–0.95 | 0.7 / 1.3 | response |
| `startup_minimum_v` | V | -0.001–0.001 | -0.1 / 0.1 | response |
| `regulation_floor_v` | V | 0.85–1.05 | 0.7 / 1.3 | response |
| `headroom_v` | V | 0–0.18 | 0 / 0.4 | response |
| `line_span_v` | V | 0–0.006 | 0 / 0.05 | response |
| `load_span_v` | V | 0–0.012 | 0 / 0.1 | response |

Coefficient **9** represents coupled multistage error amplification, pass-gate
control, physical feedback/compensation and regulation/loop/recovery requirements.
Unified score is `G × (60E + 20H + 20HQ)`: G requires physical validity and
complete valid observations; E averages worst attainment in response, bias
and supply; H requires all bounds. Attainment decreases linearly to the stated
zero boundaries. Q is `clip((8000000−area)/6000000,0,1)` with fixed absolute
area target 2,000,000 and zero 8,000,000 um², including all devices, taps,
feedback and routing. The budget is not a ratio to a submitted or changing
reference. Completed physical rejection scores zero; errors preventing scoring
produce no invented numerical score.

## Tools and Submission

Discover task/resources/feedback through `/protocol/task.json`,
`/protocol/resources.json` and `/protocol/harness.json`. Use the supplied
IHP primitives and KLayout/Magic/ngspice. Write `/workspace/output/final.gds`
and explicitly submit via the harness protocol. Host configuration, source
records and reference answers are excluded from standard solver inputs.
