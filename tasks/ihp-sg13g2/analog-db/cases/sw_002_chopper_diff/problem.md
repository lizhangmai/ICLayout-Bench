# Differential Polarity-Commutating Switch Layout Task

## Objective

Implement `sw_002_chopper_diff` in ihp-sg13g2 and submit self-contained GDS. Eight MOS devices form four transmission paths that connect a differential input directly or with reversed polarity. The two complementary clock nets are independent layout ports. Fixed IHP W/L/m are retained; explicit substrate/well taps are included in both maintained circuit representations.

## Inputs and Interface

`materials/circuit.cdl` is the authoritative physical circuit. `materials/circuit.spice` is its equivalent simulator model-call representation. `materials/testbench.spice` defines measurements, and this problem is the description input.
Ordered ports: `va_p va_n vb_p vb_n vctl vctl_not vdd vss`. In order: Positive input, negative input, positive output, negative output, direct-path clock, complementary clock, supply, and return.

Preserve connectivity, W/L/m, passive geometry and body connections. Provide physical contacts. Placement and routing are free; splitting and source/drain interchange are allowed only under the declared LVS equivalences. No statistical matching or common-centroid constraint is scored. Ideal external sources, loads and fixtures belong to the testbench, not the DUT.

## Operating Conditions

Temperature is 27 C. Typical IHP low-voltage MOS and resistor models; explicit finite physical tap models and a 1e12 ohm ngspice numerical shunt at each node. Candidate Magic RC is extracted with zero coupling-capacitance threshold.

VDD = 1.5 V; VSS = 0 V; input common mode = 0.75 V; differential input = -0.2 or +0.2 V. Each output has an external 10 kohm resistor to common mode and 1 pF to ground. DC checks both clock states (vctl = 0 or 1.5 V), giving four conditions. Transient clocks are complementary 0/1.5 V pulses, delay 1 us, rise/fall 2 ns, high width 5 us and period 10 us; output/max step is 0.1 ns with Gear order 2, stop time 12 us. A second transient sets both inputs to 0.75 V to separate clock feedthrough/injection from signal reversal. The finite clock slopes deliberately permit overlap; non-overlap operation is not claimed.

## Physical Requirements

Top cell `sw_002_chopper_diff`, named ports, resolved hierarchy, at most 10 MiB. Pass artifact, IHP main and maximal DRC, with density and antenna outside this standalone scope; strict named-port LVS; geometry, without DRC waivers. Functional bounding box must fit within 90 by 40 um. The footprint includes every process device and routing drawing layer in the frozen runtime outline list: active, wells, implants, poly, contacts, metals/vias and device/passive markers. Annotation and pin-purpose shapes are excluded. All functional routing must use drawing layers.

Every scored simulation consumes the submitted GDS-derived distributed wiring RC and extracted device geometry. Ron includes the declared terminal loading and common mode. Injection is net terminal charge integrated under driven equal inputs, not stored charge on a disconnected sampler. Noise, chopping an amplifier, RF/EM, mismatch and other clock rates are outside scope. Fabrication signoff is not claimed.

## Electrical Requirements and Scoring

All 4 operating conditions must complete. Every finite observation must meet its inclusive band; aggregation cannot hide a failing condition. Missing measurements/crossings or incomplete extraction do not establish success.

| Metric | Definition | Unit | Acceptance | Zero-score boundaries | Dimension |
| --- | --- | --- | --- | --- | --- |
| `ron_p` | Absolute (selected positive-output input minus V(vb_p)) / current through its 10 kohm load | ohm | 0 to 1600 | < 0 or >= 3200 | response |
| `ron_n` | Absolute (selected negative-output input minus V(vb_n)) / current through its 10 kohm load | ohm | 0 to 1600 | < 0 or >= 3200 | response |
| `transfer` | DC output differential divided by the selected signed input differential | V/V | 0.88 to 1 | <= 0 or >= 1.2 | response |
| `common_error_v` | Absolute DC output common-mode minus 0.75 V | V | 0 to 0.003 | < 0 or >= 0.02 | bias |
| `straight_gain` | Output differential / input differential at 4 us | V/V | 0.88 to 1 | <= 0 or >= 1.2 | response |
| `crossed_gain` | Output differential / input differential at 9 us | V/V | -1 to -0.88 | <= -1.2 or >= 0 | response |
| `common_glitch_v` | Maximum absolute output common-mode minus 0.75 V over 1–1.1 us with equal inputs | V | 0 to 0.002 | < 0 or >= 0.02 | response |
| `differential_glitch_v` | Maximum absolute output differential over 1–1.1 us with equal inputs | V | 0 to 0.003 | < 0 or >= 0.03 | response |
| `input_charge_c` | Absolute integral of I(VAP)+I(VAN) over 1–1.1 us with equal inputs | C | 0 to 3e-15 | < 0 or >= 3e-14 | response |
| `clock_power_w` | Average positive supplied power from both clock sources over 2–12 us with equal inputs; returned energy is not credited | W | 0 to 1e-08 | < 0 or >= 2e-08 | supply |

The unified score is `S = G * (60*E + 20*H + 20*H*Q)`. `G` requires physical validity and complete extraction/measurements. `E` averages applicable response, bias and supply dimensions, each using its worst observation's attainment. Attainment is 1 inside its band and decreases linearly to its zero boundary. `H` is 1 only when all electrical limits pass. `Q = clip((10000 - area_um2)/(10000 - 2500), 0, 1)`. The fixed absolute area target is 2500 um2 and zero utility is 10000 um2. Physical rejection scores 0; blocking evaluator errors have no score. Coefficient: 5.

## Tools and Submission

Use reviewed resources from `/protocol/resources.json`. KLayout checks, Magic extracts RC, and ngspice simulates. Frozen constraints and requirements are in `/protocol/task.json`; `/protocol/harness.json` describes the harness. If available, use the published `process-feedback.v1` helper for interim checks. Write `/workspace/output/final.gds` and explicitly submit using `python -I /protocol/submit.py`.
