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

Physical checks and declared functional bounds remain mandatory. Quality has no
fixed allowed-degradation threshold. Each `source_*` job simulates the declared
source circuit with exactly the same testbench, model resources, parameters,
load and measurement window as its paired extracted-candidate job. A source
observation is the 100-point electrical baseline; it is independent of the
submitted GDS. All individual pairs are retained in the evaluation report.

For a post-layout observation x and its source observation b:

- Maximize: q = x/b; minimize: q = b/x. When a numerical scale s is declared,
  use (x+s)/(b+s) or its inverse. This handles zero-valued error measurements;
  s is a normalization floor, not an allowed degradation or pass threshold.
- Amplitude dB: q = 10^((x-b)/20) for maximize, its inverse for minimize.
- Target: q = 1/(1+abs(x-b)/s), with a declared physical scale s. Signed and
  zero-valued operating points are never divided directly.

A metric uses its worst paired q. Each response/bias/supply dimension takes the
geometric mean of its scored metrics; E is the geometric mean of applicable
dimensions. Q = area_reference / candidate_functional_area. The overall score is
S = 100 * sqrt(E * Q). The baseline is 100, not a ceiling; directional and area
improvements can earn more than 100. Failed physical or functional checks score
zero; missing/invalid evaluation or source measurements produce an unknown score.
Diagnostic observations do not earn points. The runtime task plan publishes the
exact pairing, dimensions, scales and any functional bounds.

| Metric | Definition / observations | Unit | Quality rule | Functional bounds | Scale |
| --- | --- | --- | --- | --- | --- |
| `output_v` | DC output/control voltage | V | target / target | 0 … 3.3 | 3.3 |
| `bias_v` | DC V(ibias) | V | target / target | 0 … 3.3 | 3.3 |
| `tail_v` | DC V(tail) | V | target / target | 0 … 3.3 | 3.3 |
| `power_w` | DC power delivered by VDD; telescopic also includes both external voltage-bias sources | W | minimize / ratio | 0 … +∞ | 1e-12 |
| `gain_db` | 20 log10(abs(differential transfer)) at 10 Hz | dB | maximize / db20 | −∞ … +∞ | — |
| `unity_hz` | First falling 0 dB crossing | Hz | maximize / ratio | 0 … +∞ | — |
| `phase_margin` | 180 degrees plus unwrapped transfer phase at unity crossing | deg | target / target | 0 … 180 | 180 |

Area reference: **544.15 um2**. 10 expanded device instances; sum of device/contact envelopes 312.9250 um2, per-side envelope allowance 1 um, 50% routing allowance and outer margin 2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

The capability coefficient remains **5**; it is independent of
the reference-relative task score.

## Tools and Submission

Solve budget: **3 hours**.

Use reviewed resources from `/protocol/resources.json`. KLayout checks, Magic extracts RC, and ngspice simulates. Frozen constraints and requirements are in `/protocol/task.json`; `/protocol/harness.json` describes the harness. If available, use the published `process-feedback.v1` helper for interim checks. Write `/workspace/output/final.gds` and explicitly submit using `python -I /protocol/submit.py`.

Use a GDS database unit of 0.001 um, as required by the GF180MCU DRC deck.
