# PMOS-Input Common-Mode Detector and Controller Layout Task

## Objective

Implement `cmfb_002_5t_pmos_input` with the complete fixed topology and minimize layout-induced degradation under the declared nominal observations. Seven MOS implement a PMOS-input five-transistor OTA plus the PMOS/NMOS diode bias branch. Two 1 Mohm sensing arms each use four series physical high-poly units. The pinned IHP widths/lengths are quantized to the 10 nm drawing grid, including the 0.29 um bias NMOS. Bodies and all sensing/bias devices are retained.

## Inputs and Interface

`materials/circuit.cdl` is the authoritative physical netlist; `materials/circuit.spice` is its simulator representation. The supplied SPICE decks are the performance fixtures. `problem.md` is this contract. Ordered ports: `vinp vinn vcmfb vref vdd vss`. The resistor midpoint senses input common mode. Reference and input sources are external. This is a standalone detector/controller; it contains neither a controlled amplifier nor a complete common-mode feedback loop. Fixture dependent voltage sources only establish specified input voltages and are outside the DUT.

## Operating Conditions

1.5 V supply; 0.5 and 0.7 V input common mode and equal reference. Output has 1 pF to ground and 10 Mohm to the common-mode source. At each bias, separate unit AC common-mode, reference and balanced differential excitations cover 1 Hz–100 MHz. Verify zero differential component in common-mode excitation and zero common-mode component in differential excitation. Centered 2 mV DC sweeps separately vary the common-mode or reference source. Separate 1 mV common-mode/reference or 100 mV differential steps start at 20 us, have 100 ns edges and last 40 us. The 100 us transient starts at DC, maximum step 20 ns. Rail power includes both diode bias devices, but excludes fixture driver losses. No external plant/servo, solver shunt or forced state.

All source/candidate jobs share exactly the same fixtures, parameters, nominal TT models and 27 C temperature. Testbench control blocks and frozen runtime parameters define all stimulus and measurement details. Source simulation is independent of the reference GDS. No paper or data-sheet performance number is an acceptance threshold.

## Physical Requirements

Submit a valid GDSII containing top cell `cmfb_002_5t_pmos_input`, at most 10485760 bytes. Pass the pinned native DRC profile, named-interface LVS and functional outline checks. Maximum functional width/height are 5000/1000 um. The complete functional layer set is `[[1, 0], [3, 0], [5, 0], [6, 0], [7, 0], [8, 0], [10, 0], [11, 0], [13, 0], [14, 0], [19, 0], [24, 0], [26, 0], [28, 0], [29, 0], [30, 0], [31, 0], [32, 0], [33, 0], [35, 0], [36, 0], [40, 0], [44, 0], [46, 0], [49, 0], [50, 0], [51, 0], [52, 0], [53, 0], [55, 0], [58, 0], [66, 0], [67, 0], [90, 0], [101, 0], [111, 0], [125, 0], [126, 0], [128, 0], [129, 0], [133, 0], [134, 0], [139, 0], [152, 0]]` (layer/datatype pairs); text/annotation geometry is excluded. There are no case-local DRC waivers. Geometry bounds are generous task/resource limits, not an area score anchor.

Post-layout simulation must consume native candidate-GDS-derived distributed wire RC, retaining every physical MOS, resistor and capacitor. Native LVS alone does not substitute for PEX. Magic uses ideal well/substrate tap connections; source simulation retains native finite tap models. This boundary does not establish distributed substrate resistance or substrate-noise accuracy.

## Electrical Requirements and Scoring

Coefficient 4 covers a compact gain/bias/passive network. Positive common-mode and negative reference DC slopes are functional sign constraints, not gain targets. Reported response/ripple windows do not certify a closed-loop CM regulator or upstream optimization claims.

Every required condition must yield finite, valid measurements and pass the functional bounds below. Missing or invalid extraction/measurements are evaluation errors, not low performance scores. Quality uses `layout-v2`: each electrical metric is paired with its same-condition source observation; the worst paired quality determines that metric. Dimension qualities and then applicable dimensions use geometric means. Area quality is area_target / complete functional area; total score is 100 sqrt(electrical_quality × area_quality), with no upper cap.

| Metric | Unit | Definition | Dimension / normalization | Functional bounds |
| --- | --- | --- | --- | --- |
| `output_v` | V | Natural loaded output with zero CM error | bias / target; scale 1.5 | lower=0; upper=1.5 |
| `power_w` | W | Rail power including dual-diode bias | supply / ratio; scale 1e-12 | lower=0 |
| `signed_gain` | 1 | Real transfer at 1 Hz, selected CM/reference/differential input | response / target; scale 1 | Finite measurement |
| `gain_1khz` | 1 | Magnitude at 1 kHz, selected excitation | response / target; scale 1 | Finite measurement |
| `gain_100khz` | 1 | Magnitude at 100 kHz, selected excitation | response / target; scale 1 | Finite measurement |
| `step_response_v` | V | Mean response 50–60 us minus 10–20 us | response / target; scale 0.01 | Finite measurement |
| `ripple_v` | V | Recovery window output variation | response / ratio; scale 0.0001 | lower=0 |
| `dc_cm_slope` | 1 | Centered 2 mV DC output slope for dc_cm_slope | response / target; scale 1 | lower=0 |
| `dc_ref_slope` | 1 | Centered 2 mV DC output slope for dc_ref_slope | response / target; scale 1 | upper=0 |

Target normalization preserves the source operating point/transfer using its declared voltage or gain scale. Ratio floors prevent zero-error/noise-floor division; they are numerical normalization units, not acceptance tolerances. Voltage bounds are the declared physical rails; current-validity and KCL bounds distinguish measurements from numerical noise. There is no source-relative performance hard cutoff.

The area anchor is **10500 um²**: twice the sum of `(W + 6 um) × (L + 8 um)` over every expanded MOS and physical passive unit (15 units, sum 5245.926900 um²), rounded upward to 100 um². Contact/well/tap/isolation envelopes are included in the 6/8 um allowances; the factor two allows routing. This is an engineering compact-footprint estimate, independent of measured witness area, not a foundry minimum or demonstrated optimum. Task coefficient: **4**.

## Tools and Submission

Solve budget: **8 hours**.

Use the runtime task and reviewed PDK resource bundle for the declared native checks, extraction and ngspice measurements. Write `output/final.gds` with the required top cell, then explicitly submit its path through the session submission interface; creating a file alone is not submission. Reference GDS, qualification results and development sources are excluded from standard solver inputs.
