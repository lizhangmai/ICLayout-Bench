# Tail-Referenced Telescopic Cascode Amplifier Layout Task

## Objective

Implement `amp_018_telescopic_cascode` in gf180mcuD and submit self-contained GDS. Ten MOS devices form an NMOS-input telescopic cascode amplifier. Fixed upstream W/L/m are retained, including the single finger of XM5. The two ideal internal sources become external bias connections: VDD minus gate_pc is 1.143 V, and casc_n minus tail is 0.917 V. Exposing tail preserves the second source's relative bias instead of replacing it with an absolute ground-referenced voltage.

## Inputs and Interface

`materials/circuit.spice` is the authoritative physical circuit. The same netlist is used for source calibration. `materials/testbench.spice` defines measurements, and this problem is the description input.
Ordered ports: `vdd vout vinp vinn ibias vss gate_pc casc_n tail`. In order: Supply, output, positive input, negative input, reference-current input, return, PMOS cascode bias, NMOS cascode bias, and accessible tail node.

Preserve connectivity, W/L/m, passive geometry and body connections. Provide physical contacts. Placement and routing are free; splitting and source/drain interchange are allowed only under the declared LVS equivalences. No statistical matching or common-centroid constraint is scored. Ideal external sources, loads and fixtures belong to the testbench, not the DUT.

## Operating Conditions

Temperature is 27 C. Typical GF180 3.3 V MOS and high-resistance poly models, statistical variation disabled. The substrate is not a distributed silicon resistance network.

VDD = 3.3 V; VSS = 0 V; a 20 uA current source from VDD into ibias. VINP is 1.65 V DC with AC amplitude +0.5 V; VINN has DC output feedback through a 1 TH inductor and AC -0.5 V through a 1 F coupling capacitor. These ideal measurement elements are external apparatus. Output loads are 1, 3 and 5 pF. AC uses 100 points/decade from 1 Hz to 1 GHz and transfer V(vout)/(V(vinp)-V(vinn)).

## Physical Requirements

Top cell `amp_018_telescopic_cascode`, named ports, resolved hierarchy, at most 10 MiB. Pass artifact, GF180 variant-D DRC including antenna, with chip-level density and seal-ring closure outside scope; strict named-port LVS; geometry, without DRC waivers. Functional bounding box must fit within 140 by 100 um. The footprint includes every process device and routing drawing layer in the frozen runtime outline list: active, wells, implants, poly, contacts, metals/vias and device/passive markers. Annotation and pin-purpose shapes are excluded. All functional routing must use drawing layers.

Every scored simulation consumes the submitted GDS-derived distributed wiring RC and extracted device geometry. The declared bias gives about 15 dB gain; this is not a high-gain OTA qualification. Large-signal settling, noise, mismatch, other biases and PVT are outside scope. Fabrication signoff is not claimed.

## Electrical Requirements and Scoring

All 3 operating conditions must complete. Every finite observation must meet its inclusive band; aggregation cannot hide a failing condition. Missing measurements/crossings or incomplete extraction do not establish success.

| Metric | Definition | Unit | Acceptance | Zero-score boundaries | Dimension |
| --- | --- | --- | --- | --- | --- |
| `output_v` | DC output/control voltage | V | 1.7 to 1.8 | <= 1.5 or >= 2 | bias |
| `bias_v` | DC V(ibias) | V | 0.75 to 0.85 | <= 0.5 or >= 1.1 | bias |
| `tail_v` | DC V(tail) | V | 0.53 to 0.62 | <= 0.3 or >= 0.9 | bias |
| `power_w` | DC power delivered by VDD; telescopic also includes both external voltage-bias sources | W | 0 to 0.00013 | < 0 or >= 0.00026 | supply |
| `gain_db` | 20 log10(abs(differential transfer)) at 10 Hz | dB | >= 14 | <= 0 | response |
| `unity_hz` | First falling 0 dB crossing | Hz | >= 90000 | <= 0 | response |
| `phase_margin` | 180 degrees plus unwrapped transfer phase at unity crossing | deg | >= 80 | <= 0 | response |

The unified score is `S = G * (60*E + 20*H + 20*H*Q)`. `G` requires physical validity and complete extraction/measurements. `E` averages applicable response, bias and supply dimensions, each using its worst observation's attainment. Attainment is 1 inside its band and decreases linearly to its zero boundary. `H` is 1 only when all electrical limits pass. `Q = clip((44000 - area_um2)/(44000 - 11000), 0, 1)`. The fixed absolute area target is 11000 um2 and zero utility is 44000 um2. Physical rejection scores 0; blocking evaluator errors have no score. Coefficient: 5.

## Tools and Submission

Use reviewed resources from `/protocol/resources.json`. KLayout checks, Magic extracts RC, and ngspice simulates. Frozen constraints and requirements are in `/protocol/task.json`; `/protocol/harness.json` describes the harness. If available, use the published `process-feedback.v1` helper for interim checks. Write `/workspace/output/final.gds` and explicitly submit using `python -I /protocol/submit.py`.
