# Passive Resistive Common-Mode Averager Layout Task

## Objective

Two matched 1 Mohm resistors join vinp to vcm_out and vcm_out to vinn. This is a passive average detector, without a buffer, amplifier or CMFB controller. The fixed IHP binding contains ideal R cards, not process-specific resistor models; the maintained physical adaptation uses forty native GF180 ppolyf_u_1k segments (twenty per branch), totaling 999951.8 ohm per branch at TT/27 C. The extra vss port grounds their physical substrate; it is not a functional supply. Target top cell: `sup_001_vcm_detector`.

## Inputs and Interface

`materials/circuit.cdl` is the authoritative physical netlist; `materials/circuit.spice` is the same compact-device circuit for simulation. `materials/testbench.spice` supplies the external fixture. Both source and extracted candidate use the exact same deck, bias, loads, excitation, initial-state procedure and measurement windows. Ordered ports: vcm_out (sense output), vinp (positive input), vinn (negative input), vss (physical substrate).

## Operating Conditions

27 C, TT. External ideal drivers are 0.8 V and 0.4 V, each followed by 1 kohm source resistance. The output has 1 pF and either 1 Mohm or 1 Gohm to ground. Each load uses common-mode AC (both drivers +1 V) and differential AC (+1/-1 V), 1 Hz–10 MHz at 40 points/decade. Both drivers increase by 0.1 V at 1 us, with 10 ns edges, and stay high through the 5 us observation. Maximum transient step is 2 ns. The initial state is the same biased DC operating point for source and candidate. A 1 Gohm load is a finite high-impedance observation, not an unloaded claim. The analytic DC limit is Vcm*RL/(RL+500.5 kohm), tending to Vcm only as RL tends to infinity. Both input-source powers are included; no zero-power claim follows from the absence of a supply pin.

## Physical Requirements

Use GF180 native KLayout main rule deck and named-interface LVS; Magic RC extraction with its reviewed 10-way grid subdivision. No case-specific waivers. Candidate extraction must preserve every model, multiplicity, size, resistor value, connection and ordered port. The functional outline includes devices, wells, contacts and all routing layers declared in the public task; annotation and pin labels do not add area. Maximum outline: 5000 by 1000 um. Maximum GDS size: 10485760 bytes. Every device and resistor must be physical; no ideal internal macro or auxiliary servo may be added. External sources, probe loads and storage capacitors belong to the testbench.

## Electrical Requirements and Scoring

| Metric | Unit | Definition | Bound | Quality |
| --- | --- | --- | --- | --- |
| `output_v` | V | Loaded DC sense voltage | 0 to 0.8 | bias: target, target, scale=0.1 |
| `power_w` | W | Net delivered power from both external input sources | 0 to unbounded | supply: ratio, minimize, scale=1e-12 |
| `gain` | 1 | Output magnitude at 1 Hz for declared common/differential input | unbounded to unbounded | response: target, target, scale=1 |
| `gain_10khz` | 1 | Output magnitude at 10 kHz | unbounded to unbounded | response: target, target, scale=1 |
| `step_error_v` | V | Mean absolute error from settled DC target over 2–4 us | 0 to unbounded | response: ratio, minimize, scale=1e-06 |

The 2–4 us average absolute step error is a finite-window quantity. Common and differential AC magnitudes use a 1 V half-input normalization; the differential residual is not divided by a near-zero source result. Nominal deterministic matching does not establish statistical mismatch or noise.

Static output bounds are physical rail-domain checks, nonnegative power/error bounds establish measurement domains, and KCL guards reject inconsistent DC solutions. All required conditions must be valid. No advertised upstream performance is a hard gate. Numerical resolution floors prevent zero-error ratios; target scales are 0.1 V for analog operating points/response, 1 V/V for passive transfer, 0.6 V for inverter threshold and 1 mV/C for temperature slope, as applicable. Timing uses a 1 ps floor, passive settling 1 uV, power 1 pW (1 fW for the subthreshold core); these are normalization units, not acceptance tolerances.

For each metric take the worst same-condition source-paired quality. Target quality is `1/(1+abs(candidate-source)/scale)`; minimizing ratio quality is `(source+scale)/(candidate+scale)`. Geometric means combine metrics within dimensions and applicable dimensions into E. The layout-v2 score is `100*sqrt(E*area_target/functional_area)`, uncapped. Missing/nonfinite/invalid source or candidate measurements and tool failures yield an unknown score; completed physical/functional rejection yields zero. Bounds apply to every observation.

Compact area anchor: 6000 um2 = 40 × 55 × 2 um2 resistor/contact/isolation envelopes + 1600 um2 routing allowance. Each envelope accommodates the approximately 48.44 um resistor, end contacts and lateral spacing; the estimate permits folding. It is independent of the long, sparse witness. Coefficient 4: coupled matching, physical passive network, finite loading and parasitic dynamics. The circuit and these anchors are fixed before participant evaluation.

## Tools and Submission

Solve budget: **6 hours**.

Use the runtime task/protocol and reviewed resource bundle to discover tools and feedback. Submit `/workspace/output/final.gds` explicitly through the protocol; merely writing it is not a submission. The reference and maintainer source records are excluded from solver inputs.
