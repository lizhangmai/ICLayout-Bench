# Segmented-Resistor NMOS Common-Mode Controller Layout Task

## Objective

Implement `cmfb_003_5t_nmos_input` in gf180mcuD and submit self-contained GDS. Seven MOS devices form an NMOS-input common-mode error amplifier and self-bias network. Each ideal 5 Mohm sense arm is implemented as twenty series GF180 ppolyf_u_1k segments, each 2 um wide and 500 um long: 5,000 squares per arm. The segmentation, substrate terminals and intermediate nodes are part of the maintained circuit. The independent witness uses compact rows connected by metal; it retains both complete resistance chains.

## Inputs and Interface

`materials/circuit.spice` is the authoritative physical circuit. The same netlist is used for source calibration. `materials/testbench.spice` defines measurements, and this problem is the description input.
Ordered ports: `vinp vinn vcmfb vref vdd vss`. In order: Positive sensed output, negative sensed output, control output, common-mode reference, supply, and return.

Preserve connectivity, W/L/m, passive geometry and body connections. Provide physical contacts. Placement and routing are free; splitting and source/drain interchange are allowed only under the declared LVS equivalences. No statistical matching or common-centroid constraint is scored. Ideal external sources, loads and fixtures belong to the testbench, not the DUT.

## Operating Conditions

Temperature is 27 C. Typical GF180 3.3 V MOS and high-resistance poly models, statistical variation disabled. The substrate is not a distributed silicon resistance network.

VDD = 3.3 V; VSS = 0 V; VREF = 1.65 V. The external first-order inverting plant has drive = 3.3 V - V(vcmfb), followed by 100 kohm and 100 nF to common mode. V(vinp/vinn) = plant output + disturbance +/- d, where d = 0, 0.1 and 0.2 V in separate conditions. Disturbance is 0 through 10 ms, +0.1 V at 10.01 ms through 30 ms, -0.1 V at 30.01 ms through 50 ms, and 0 at 50.01 ms through 70 ms. A 10 pF external capacitor loads vcmfb. Transient output/max step is 10 us. This plant is test apparatus, not an internal ideal servo or a claimed transistor amplifier. Recovery windows are 25–29 ms and 45–49 ms for the positive/negative disturbances; error is measured at the average sensed inputs against VREF. Controller power excludes the external plant.

## Physical Requirements

Top cell `cmfb_003_5t_nmos_input`, named ports, resolved hierarchy, at most 10 MiB. Pass artifact, GF180 variant-D DRC including antenna, with chip-level density and seal-ring closure outside scope; strict named-port LVS; geometry, without DRC waivers. Functional bounding box must fit within 1100 by 280 um. The footprint includes every process device and routing drawing layer in the frozen runtime outline list: active, wells, implants, poly, contacts, metals/vias and device/passive markers. Annotation and pin-purpose shapes are excluded. All functional routing must use drawing layers.

Every scored simulation consumes the submitted GDS-derived distributed wiring RC and extracted device geometry. Qualification covers recovery with this specified external plant, not stability with arbitrary amplifiers. The long physical sense chains retain candidate-derived parasitics. Startup, mismatch, noise, PVT and a complete differential amplifier are outside scope. Fabrication signoff is not claimed.

## Electrical Requirements and Scoring

All 3 operating conditions must complete. Every finite observation must meet its inclusive band; aggregation cannot hide a failing condition. Missing measurements/crossings or incomplete extraction do not establish success.

| Metric | Definition | Unit | Acceptance | Zero-score boundaries | Dimension |
| --- | --- | --- | --- | --- | --- |
| `output_v` | DC output/control voltage | V | 1.64 to 1.67 | <= 1.5 or >= 1.8 | bias |
| `error_v` | Absolute DC sensed common-mode minus VREF | V | 0 to 0.003 | < 0 or >= 0.02 | response |
| `power_w` | DC power delivered by VDD; telescopic also includes both external voltage-bias sources | W | 0 to 0.00018 | < 0 or >= 0.00036 | supply |
| `recovery_up_v` | Maximum absolute recovered error over the upward-step window | V | 0 to 0.003 | < 0 or >= 0.02 | response |
| `recovery_down_v` | Maximum absolute recovered error over the downward-step window | V | 0 to 0.003 | < 0 or >= 0.02 | response |
| `recovery_zero_v` | Maximum absolute sensed common-mode minus VREF over 65–69 ms | V | 0 to 0.003 | < 0 or >= 0.02 | response |
| `peak_error_v` | Maximum absolute sensed common-mode minus VREF over 10–70 ms | V | 0 to 0.22 | < 0 or >= 0.5 | response |
| `mean_power_w` | Time-average -V(vdd)*I(VDD) over the complete transient | W | 0 to 0.00018 | < 0 or >= 0.00036 | supply |

The unified score is `S = G * (60*E + 20*H + 20*H*Q)`. `G` requires physical validity and complete extraction/measurements. `E` averages applicable response, bias and supply dimensions, each using its worst observation's attainment. Attainment is 1 inside its band and decreases linearly to its zero boundary. `H` is 1 only when all electrical limits pass. `Q = clip((1120000 - area_um2)/(1120000 - 280000), 0, 1)`. The fixed absolute area target is 280000 um2 and zero utility is 1120000 um2. Physical rejection scores 0; blocking evaluator errors have no score. Coefficient: 6.

## Tools and Submission

Use reviewed resources from `/protocol/resources.json`. KLayout checks, Magic extracts RC, and ngspice simulates. Frozen constraints and requirements are in `/protocol/task.json`; `/protocol/harness.json` describes the harness. If available, use the published `process-feedback.v1` helper for interim checks. Write `/workspace/output/final.gds` and explicitly submit using `python -I /protocol/submit.py`.
