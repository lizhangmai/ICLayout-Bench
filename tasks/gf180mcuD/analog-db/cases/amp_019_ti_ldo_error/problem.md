# Externally Biased TI-Architecture Error Amplifier Layout Task

## Objective

Implement `amp_019_ti_ldo_error` with the complete fixed topology and minimize layout-induced degradation under the declared nominal observations. All twelve MOS remain, including the externally driven NMOS reference diode, four sinks, NMOS differential pair, level-shift branch and PMOS output stage. RND connects na to nd; all 500 kohm remains. Rz/Cc remain in series between nb and vout. No servo is inside the DUT. Four parallel native resistors implement 470 ohm; 32 parallel MIM units implement 25 pF. Native 6 V PMOS lengths become 0.55 um; other dimensions and multiplicities retain the fixed GF180 binding.

## Inputs and Interface

`materials/circuit.cdl` is the authoritative physical netlist; `materials/circuit.spice` is its simulator representation. The supplied SPICE decks are the performance fixtures. `problem.md` is this contract. Ordered ports: `vdd vout vinp vinn ibias vss`. `vinp` is the non-inverting input and `vinn` the inverting input, verified by follower response. The ideal 1 mA source from vdd to ibias is external and included in supply power. The feedback wire connects vout to vinn externally.

## Operating Conditions

3.3 V supply, 1 mA external bias; common-mode inputs 1.4, 1.6 and 1.8 V with 10 pF output load, plus 1.6 V with 1 pF. Direct follower in DC, AC and transient. AC input is 1 V and the reported gain is **closed-loop follower transfer**, never open-loop gain or loop margin. The input rises 10 mV at 20 us with 10 ns edges and returns after 40 us; simulate through 100 us with maximum 10 ns steps. Start at the DC operating point. No extra output resistance, solver shunt, feedback isolation L/C, forced initial conditions or stability claim. Windows are 10–20, 50–60 and 90–100 us.

All source/candidate jobs share exactly the same fixtures, parameters, nominal TT models and 27 C temperature. Testbench control blocks and frozen runtime parameters define all stimulus and measurement details. Source simulation is independent of the reference GDS. No paper or data-sheet performance number is an acceptance threshold.

## Physical Requirements

Submit a valid GDSII containing top cell `amp_019_ti_ldo_error`, at most 10485760 bytes. Pass the pinned native DRC profile, named-interface LVS and functional outline checks. Maximum functional width/height are 5000/1000 um. The complete functional layer set is `[[5, 0], [11, 17], [11, 39], [12, 0], [13, 17], [21, 0], [22, 0], [22, 4], [24, 0], [24, 5], [30, 0], [30, 4], [31, 0], [32, 0], [33, 0], [34, 0], [34, 3], [34, 4], [34, 5], [35, 0], [36, 0], [36, 3], [36, 4], [36, 5], [37, 0], [38, 0], [40, 0], [41, 0], [42, 0], [42, 3], [42, 4], [42, 5], [46, 0], [46, 3], [46, 4], [46, 5], [49, 0], [53, 0], [53, 3], [53, 4], [53, 5], [55, 0], [62, 0], [75, 0], [80, 5], [81, 0], [81, 3], [81, 4], [81, 5], [82, 0], [86, 17], [88, 17], [96, 1], [100, 5], [100, 7], [100, 8], [108, 5], [110, 5], [110, 11], [110, 12], [110, 13], [110, 14], [110, 15], [110, 16], [111, 5], [112, 1], [115, 5], [116, 5], [117, 5], [117, 10], [118, 5], [119, 5], [122, 5], [123, 5], [124, 5], [125, 5], [127, 5], [128, 17], [137, 5], [151, 5], [152, 5], [153, 51], [166, 5], [167, 5], [173, 5], [178, 0], [183, 0], [184, 0], [185, 0], [204, 0], [210, 0], [220, 0], [226, 0], [227, 0], [241, 0]]` (layer/datatype pairs); text/annotation geometry is excluded. There are no case-local DRC waivers. Geometry bounds are generous task/resource limits, not an area score anchor.

Post-layout simulation must consume native candidate-GDS-derived distributed wire RC, retaining every physical MOS, resistor and capacitor. Native LVS alone does not substitute for PEX. The GF180 model boundary retains physical poly substrate and MIM geometry.

## Electrical Requirements and Scoring

Coefficient 6 reflects the complete two-stage compensated feedback circuit. It does not claim verified open-loop gain, phase margin, noise, PVT or settling time. Late variation is a finite-window observation. The bias sink ratios are geometric ratios, not promises of saturated current mirrors.

Every required condition must yield finite, valid measurements and pass the functional bounds below. Missing or invalid extraction/measurements are evaluation errors, not low performance scores. Quality uses `layout-v2`: each electrical metric is paired with its same-condition source observation; the worst paired quality determines that metric. Dimension qualities and then applicable dimensions use geometric means. Area quality is area_target / complete functional area; total score is 100 sqrt(electrical_quality × area_quality), with no upper cap.

| Metric | Unit | Definition | Dimension / normalization | Functional bounds |
| --- | --- | --- | --- | --- |
| `output_v` | V | DC direct-follower output | bias / target; scale 3.3 | lower=0; upper=3.3 |
| `power_w` | W | Total 3.3 V supply power including external 1 mA bias | supply / ratio; scale 1e-12 | lower=0 |
| `gain_1hz` | 1 | Closed-loop follower magnitude at 1 Hz | response / target; scale 1 | Finite measurement |
| `gain_1mhz` | 1 | Closed-loop follower magnitude at 1 MHz | response / target; scale 1 | Finite measurement |
| `tracking_error_v` | V | Mean absolute tracking error, 20–100 us | response / ratio; scale 0.001 | lower=0 |
| `ripple_v` | V | Finite-window peak-to-peak output, 90–100 us | response / ratio; scale 0.001 | lower=0 |
| `step_response_v` | V | Mean output 50–60 us minus 10–20 us | unscored / functional | lower=0 |
| `kcl_a` | A | External DC KCL residual | unscored / functional | lower=0; upper=1e-08 |

Target normalization preserves the source operating point/transfer using its declared voltage or gain scale. Ratio floors prevent zero-error/noise-floor division; they are numerical normalization units, not acceptance tolerances. Voltage bounds are the declared physical rails; current-validity and KCL bounds distinguish measurements from numerical noise. There is no source-relative performance hard cutoff.

The area anchor is **63700 um²**: twice the sum of `(W + 6 um) × (L + 8 um)` over every expanded MOS and physical passive unit (58 units, sum 31829.640000 um²), rounded upward to 100 um². Contact/well/tap/isolation envelopes are included in the 6/8 um allowances; the factor two allows routing. This is an engineering compact-footprint estimate, independent of measured witness area, not a foundry minimum or demonstrated optimum. Task coefficient: **6**.

## Tools and Submission

Solve budget: **8 hours**.

Use the runtime task and reviewed PDK resource bundle for the declared native checks, extraction and ngspice measurements. Write `output/final.gds` with the required top cell, then explicitly submit its path through the session submission interface; creating a file alone is not submission. Reference GDS, qualification results and development sources are excluded from standard solver inputs.
