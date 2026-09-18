# Series-Nulling-Resistor Two-Stage OTA Layout Task

## Objective

Lay out `amp_024_smcnr`, a PMOS-input two-stage OTA with series R/C Miller
compensation, for stable loaded unity-feedback response. Preserve the eight
MOS groups' fixed W/L/m, physical compensation network and explicit bias interface.

## Inputs and Interface

- `materials/circuit.cdl`: authoritative native LVS circuit.
- `materials/circuit.spice`: matching process-model simulation representation.
- `materials/testbench.spice`: nominal bias, loop-gain and finite-step measurements.

Ordered ports: `vss vdd vinn vinp vout ibias`. VSS is return, VDD is supply,
VINN/VINP are inverting/noninverting inputs, VOUT is the output, and IBIAS
connects an external 100 nA current sink to VSS. The bias mirror remains inside
the DUT. No ideal source is a layout device. NMOS and resistor bodies connect
through the explicit substrate tap to VSS; PMOS bodies connect through the
well tap to VDD. Preserve device models and total W/L/m; equivalent parallel
MOS fingers and native resistor merging are allowed when LVS and all other
requirements pass. Supply and return must remain distinct.

The internal compensation path is `outn` → two parallel MIM units → `nzo` →
four series high-poly segments → `vout`. Each `cap_cmim` is 25.85 × 25.85 um,
nominally 1.00647 pF; each `rhigh` is W=1 um, L=18 um, m=1, b=0, giving
approximately 100 kohm for the chain with the process model. These are DUT
devices, separately from the external load. Do not delete or replace them with
ideal parasitic annotations. Internal nodes are not extra bias ports.

## Operating Conditions

Use typical MOS, capacitor and resistor models at 27 C, 1.2 V supply and a
100 nA external bias sink. External output loads are 5, 10 and 20 pF. All
three conditions must pass. Qualification is nominal and does not cover PVT,
mismatch, rail-to-rail operation or arbitrary output loads.

At DC, VINP=0.5 V and VOUT feeds VINN through the zero-volt probe. AC uses a
1 V series injection at this feedback connection, VINP AC=0, and
`T=-V(vout)/V(vm)`. Sweep 0.01 Hz–100 MHz at 150 points/decade. Gain is
`20 log10(abs(T))`; phase is its continuous phase without subtracting a fitted
low-frequency offset. Unity frequency is the first descending 0 dB crossing;
phase margin is 180 degrees plus phase there. Missing crossings are errors.
This voltage-injection measurement uses the high-impedance MOS input boundary.

Transient keeps the zero-volt feedback connection. VINP rises 0.5→0.7 V from
20 to 20.1 us, falls from 100.1 to 100.2 us, and repeats every 160 us. Simulate
0–180 us using Gear order 2 with 50 ns maximum step. Use `rshunt=1e12`,
`reltol=1e-5`, `abstol=1e-14`, `vntol=1e-8`. This weak numerical shunt is
part of the declared simulator boundary, not a physical bias or startup source.

## Physical Requirements

Submit GDSII with top cell `amp_024_smcnr`, at most 10 MiB. Pass native IHP
main plus maximal DRC (standalone scope, density/antenna disabled), strict
named-port LVS with physical taps, and a 650 × 80 um functional envelope.
There are no case DRC waivers. All functional devices, contacts and routing
must lie on the drawing layers listed in the runtime `outline` constraint;
annotation/pin-purpose layers do not contribute to its bounding-box area.

Post-layout simulation must consume the candidate's Magic RC extraction,
including physical R/C devices and extracted interconnect. Well/substrate taps
are ideal connections in this extractor, rather than the finite source tap
models; this is not a distributed substrate or substrate-noise model. The
OSDI resistor model and MOS/MIM model resources must be available.

## Electrical Requirements and Scoring

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
| `output_v` | condition_0:output_v, condition_1:output_v, condition_2:output_v | V | target / target | 0 … 1.2 | 1.2 |
| `bias_v` | condition_0:bias_v, condition_1:bias_v, condition_2:bias_v | V | target / target | 0 … 1.2 | 1.2 |
| `power_w` | condition_0:power_w, condition_1:power_w, condition_2:power_w | W | minimize / ratio | 0 … +∞ | 1e-12 |
| `dc_gain_db` | condition_0:dc_gain_db, condition_1:dc_gain_db, condition_2:dc_gain_db | dB | maximize / db20 | −∞ … +∞ | — |
| `unity_hz` | condition_0:unity_hz, condition_1:unity_hz, condition_2:unity_hz | Hz | maximize / ratio | 0 … +∞ | — |
| `phase_margin_deg` | condition_0:phase_margin_deg, condition_1:phase_margin_deg, condition_2:phase_margin_deg | deg | target / target | 0 … 180 | 180 |
| `recovery_up_v` | condition_0:recovery_up_v, condition_1:recovery_up_v, condition_2:recovery_up_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `recovery_down_v` | condition_0:recovery_down_v, condition_1:recovery_down_v, condition_2:recovery_down_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `step_gain` | condition_0:step_gain, condition_1:step_gain, condition_2:step_gain | V/V | target / target | −∞ … +∞ | 1.0 |
| `mean_power_w` | condition_0:mean_power_w, condition_1:mean_power_w, condition_2:mean_power_w | W | minimize / ratio | 0 … +∞ | 1e-12 |
| `peak_v` | condition_0:peak_v, condition_1:peak_v, condition_2:peak_v | V | target / target | 0 … 1.2 | 1.2 |
| `trough_v` | condition_0:trough_v, condition_1:trough_v, condition_2:trough_v | V | target / target | 0 … 1.2 | 1.2 |

Area reference: **5869.81 um2**. 35 expanded device instances; sum of device/contact envelopes 3813.4378 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

The capability coefficient remains **7**; it is independent of
the reference-relative task score.

## Tools and Submission

Solve budget: **3 hours**.

Discover task, inputs, resources and harness feedback through `/protocol/task.json`,
`/protocol/resources.json` and `/protocol/harness.json`. Use the supplied IHP
primitives and KLayout, Magic and ngspice tools. Write `/workspace/output/final.gds`
and explicitly submit through the harness protocol. Host configuration, source
records and reference layouts are outside the standard solver inputs.
