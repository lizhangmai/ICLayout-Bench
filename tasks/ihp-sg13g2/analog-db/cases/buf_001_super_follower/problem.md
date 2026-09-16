# MIM-Compensated Local-Feedback Source Follower Layout Task

## Objective

Implement `buf_001_super_follower` in ihp-sg13g2 and submit self-contained GDS. Six MOS entries expand to 17 physical MOS instances in a local-feedback source follower. Fixed IHP W/L/m are retained. The internal na-to-VSS 250 fF compensation is implemented as a 12.85 by 12.85 um cap_cmim (nominally 249.74 fF at 27 C, including model perimeter capacitance); it is not removed or moved to the output. Explicit physical taps and the MIM dimensions are common to LVS, source simulation and extracted simulation.

## Inputs and Interface

`materials/circuit.cdl` is the authoritative physical circuit. `materials/circuit.spice` is its equivalent simulator model-call representation. `materials/testbench.spice` defines measurements, and this problem is the description input.
Ordered ports: `vdd vout vin ibias vss`. In order: Supply, output, signal input, reference-current input, and return.

Preserve connectivity, W/L/m, passive geometry and body connections. Provide physical contacts. Placement and routing are free; splitting and source/drain interchange are allowed only under the declared LVS equivalences. No statistical matching or common-centroid constraint is scored. Ideal external sources, loads and fixtures belong to the testbench, not the DUT.

## Operating Conditions

Temperature is 27 C. Typical IHP low-voltage MOS and resistor models and typical capacitor models; explicit finite physical tap models and a 1e12 ohm ngspice numerical shunt at each node. Candidate Magic RC is extracted with zero coupling-capacitance threshold.

VDD = 1.5 V; VSS = 0 V; a 20 uA current source from VDD into ibias. VIN = 0.55 V DC, AC amplitude 1 V. External output loads are 5, 10 and 20 pF. AC uses 100 points/decade from 1 Hz to 1 GHz. VIN stays at 0.55 V through 1 us, ramps to 0.65 V at 1.001 us, holds through 3 us, ramps back at 3.001 us and holds through 5 us. Transient output/max step is 0.2 ns. Recovered errors compare output to its 2.5 us and 0.5 us samples, over 1.5–2.9 us and 3.5–4.9 us respectively.

## Physical Requirements

Top cell `buf_001_super_follower`, named ports, resolved hierarchy, at most 10 MiB. Pass artifact, IHP main and maximal DRC, with density and antenna outside this standalone scope; strict named-port LVS; geometry, without DRC waivers. Functional bounding box must fit within 160 by 45 um. The footprint includes every process device and routing drawing layer in the frozen runtime outline list: active, wells, implants, poly, contacts, metals/vias and device/passive markers. Annotation and pin-purpose shapes are excluded. All functional routing must use drawing layers.

Every scored simulation consumes the submitted GDS-derived distributed wiring RC and extracted device geometry. This is a level-shifting source follower with about 0.84 small-signal gain, not a unity-gain rail-to-rail buffer. Qualification is restricted to the stated low-input range; higher input bias compresses the gain. Noise, mismatch, other input levels, PVT and RF/EM are outside scope. Fabrication signoff is not claimed.

## Electrical Requirements and Scoring

All 3 operating conditions must complete. Every finite observation must meet its inclusive band; aggregation cannot hide a failing condition. Missing measurements/crossings or incomplete extraction do not establish success.

| Metric | Definition | Unit | Acceptance | Zero-score boundaries | Dimension |
| --- | --- | --- | --- | --- | --- |
| `output_v` | DC output/control voltage | V | 0.12 to 0.16 | <= 0 or >= 0.3 | bias |
| `bias_v` | DC V(ibias) | V | 0.37 to 0.42 | <= 0.2 or >= 0.6 | bias |
| `power_w` | DC power delivered by VDD; telescopic also includes both external voltage-bias sources | W | 0 to 0.0004 | < 0 or >= 0.0008 | supply |
| `gain_vv` | Magnitude V(vout) at 10 Hz with unit AC input | V/V | 0.78 to 0.9 | <= 0 or >= 1.2 | response |
| `bandwidth_hz` | First falling 3 dB crossing relative to the 10 Hz gain | Hz | >= 2e+07 | <= 0 | response |
| `step_gain` | (Vout at 2.5 us - Vout at 0.5 us) / 0.1 V | V/V | 0.78 to 0.9 | <= 0 or >= 1.2 | response |
| `recovery_up_v` | Maximum absolute recovered error over the upward-step window | V | 0 to 0.0001 | < 0 or >= 0.01 | response |
| `recovery_down_v` | Maximum absolute recovered error over the downward-step window | V | 0 to 0.0001 | < 0 or >= 0.01 | response |
| `mean_power_w` | Time-average -V(vdd)*I(VDD) over the complete transient | W | 0 to 0.0004 | < 0 or >= 0.0008 | supply |

The unified score is `S = G * (60*E + 20*H + 20*H*Q)`. `G` requires physical validity and complete extraction/measurements. `E` averages applicable response, bias and supply dimensions, each using its worst observation's attainment. Attainment is 1 inside its band and decreases linearly to its zero boundary. `H` is 1 only when all electrical limits pass. `Q = clip((22000 - area_um2)/(22000 - 5500), 0, 1)`. The fixed absolute area target is 5500 um2 and zero utility is 22000 um2. Physical rejection scores 0; blocking evaluator errors have no score. Coefficient: 5.

## Tools and Submission

Use reviewed resources from `/protocol/resources.json`. KLayout checks, Magic extracts RC, and ngspice simulates. Frozen constraints and requirements are in `/protocol/task.json`; `/protocol/harness.json` describes the harness. If available, use the published `process-feedback.v1` helper for interim checks. Write `/workspace/output/final.gds` and explicitly submit using `python -I /protocol/submit.py`.
