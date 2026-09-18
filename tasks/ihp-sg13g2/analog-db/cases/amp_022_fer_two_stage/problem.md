# Fer Two-Stage Miller Amplifier Layout Task

## Objective

Implement `amp_022_fer_two_stage` as a GDS layout preserving the complete declared circuit. PMOS differential input pair, NMOS mirror load, NMOS common-source second stage and PMOS current-source load, retaining Miller CC and the complete NMOS-to-PMOS bias mirror. The 10 bound MOS expand to 63 physical units; CC is a 36.46 um square native MIM (1.999831 pF).

## Inputs and Interface

- `materials/circuit.cdl`: authoritative physical circuit and ordered named interface.
- `materials/circuit.spice`: equivalent source simulation, including physical passives.
- `materials/testbench.spice`: performance observations.
- `materials/ac.spice`: frequency observations.
- `problem.md`: this contract.

Ordered ports: `vdd vout vinp vinn ibias vss`. `vss` is ground, `vdd` the positive rail; signal/output and bias/reference ports have the functions and directions specified below. Every named interface must be preserved. Device multipliers are explicitly expanded; series/parallel passive realizations are already declared in the circuit. The reference layout and development source are not solver inputs.

## Operating Conditions

1.5 V, 27 C, TT LV MOS and typical passives; external 20 uA flows from VDD into ibias. The NMOS diode/mirror drives the PMOS diode: bias/tail/output-load multiplicities are 3:3:17; input-pair multiplicities are 5 each, NMOS load 2 each, and second-stage NMOS 24. The PMOS input bodies remain VDD. vinp is noninverting. The unity follower ties vinn directly to vout. Input is 0.6 V with a +0.2 V pulse at 2 us, 100 ns edges, 8 us high width; falling completes at 10.2 us. The load is 10 pF, maximum transient step 0.5 ns, total window 20 us. High/return statistics use 8–10/18–20 us. Balanced AC uses +0.5/-0.5 V excitation and a 1 TH/1 F DC-feedback isolation network over 1 Hz–1 GHz (200 points/decade). Residual AC common mode and DC feedback mismatch must be at most 1 uV.

## Physical Requirements

IHP native standalone-block DRC, named-port LVS and distributed Magic RC extraction. Physical source and extracted simulations retain finite native body taps. The functional footprint includes active/poly, passives, all routed metals and vias, excluding text and nonfunctional boundary markers. No DRC waivers are declared. The core topology, body connections and physical compensation are fixed. Geometrically equivalent implementations must retain the named ports and device parameters. Functional bounds are 2000 by 1000 um; they bound the supported block footprint, not electrical quality.

## Electrical Requirements and Scoring

| Metric | Unit | Definition | Assignment |
|---|---|---|---|
| output_v | V | DC follower output | bias; target (scale 1.5) |
| power_w | W | DC rail power, -VDD*I(VDD); includes external reference current drawn from VDD | supply; ratio (scale 1e-12) |
| gain_db | dB | Balanced differential open AC gain at 1 Hz | response; db20 |
| gain_10khz_db | dB | Balanced differential open AC gain at 10 kHz | response; db20 |
| closed_gain_10khz_db | dB | Direct follower output/signal AC gain at 10 kHz | response; target (scale 6) |
| late_error_v | V | Mean absolute follower tracking error, 8–10 us | response; ratio (scale 0.001) |
| return_error_v | V | Mean absolute follower tracking error, 18–20 us | response; ratio (scale 0.001) |
| ripple_v | V | Full output peak-to-peak range, 8–10 us | response; ratio (scale 0.001) |
| return_ripple_v | V | Full output peak-to-peak range, 18–20 us | response; ratio (scale 0.001) |
| mean_power_w | W | Time-weighted rail power over 2–20 us; includes external reference current drawn from VDD | supply; ratio (scale 1e-12) |
| bias_v | V | External current-bias port DC voltage | diagnostic; unscored |
| high_v | V | Mean follower output, 8–10 us | diagnostic; unscored |
| low_v | V | Mean follower output, 18–20 us | diagnostic; unscored |
| output_min_v | V | Minimum output over 0–20 us | diagnostic; unscored |
| output_max_v | V | Maximum output over 0–20 us | diagnostic; unscored |
| fixture_cm_max | V | Residual common-mode excitation in the differential AC fixture | diagnostic; unscored |
| dc_feedback_error_v | V | DC voltage mismatch across the external feedback inductor | diagnostic; unscored |
| kcl_a | A | Absolute external DC current-balance residual; numerical validity bound 10 nA | diagnostic; unscored |

All required jobs must finish with finite valid measurements. The 10 nA DC KCL residual bounds numerical validity; nonnegative power/error/range bounds follow their physical definitions. Additional fixture validity bounds are stated above and in runtime task metadata. There are no data-sheet gain, regulation-accuracy or speed gates. Failed extraction, invalid measurements and missing jobs cannot be replaced by low scores.

Use `layout-v2`: physical validity G gates the score; electrical E is the geometric mean of the bias/response/supply dimension geometric means, and compactness Q is area_target/functional_area. Score is 100*G*sqrt(E*Q). Each scored candidate observation is paired with the independent source observation in the identical condition. Ratio-minimize uses (source+scale)/(candidate+scale); target uses scale/(scale+abs(candidate-source)); db20-maximize uses 10^((candidate-source)/20). Scores are continuous and not capped at 100. Each metric uses its worst same-condition paired quality. Diagnostics are unscored. Source results, not the reference GDS, define performance normalization. The 1 mV error/ripple floors and 1 pW power floors regularize zero values; they are not acceptance tolerances. Target scales use the stated rail/output voltage or differential step amplitude.

Area anchor: 7022.72 um2. 1.5 times the sum over expanded physical MOS, resistor and capacitor units of (W + 4 um)*(L + 4 um). The 4 um allowances cover local contacts/isolation; 50% covers compact routing. Body taps are covered by the allowance, not counted twice. This is an analytical compact-area anchor, not the witness footprint.

Coefficient 6 covers a complete compensated feedback loop with direct-follower recovery. No numerical node shunt is used. No phase margin, unity-gain crossing, noise or settling-time claim is made.

## Tools and Submission

Solve budget: **8 hours**.

Use the runtime task/resource discovery interface for the frozen tool image, PDK and declared feedback operations. The evaluator checks the submitted GDS independently and extracts its parasitics. Submit `output/final.gds`, top cell `amp_022_fer_two_stage`; do not submit a source netlist in place of a layout. Keep all named ports. The resource bundle contains the approved open PDK and native EDA tools.
