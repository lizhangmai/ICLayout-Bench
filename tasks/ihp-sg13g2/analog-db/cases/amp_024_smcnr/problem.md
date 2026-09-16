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

Every bound applies to every load. `output_v`, `bias_v` and `power_w` are the
DC output, bias-port voltage and positive VDD-supplied power. The external sink
is not credited as recovered supply energy; no sink-generator overhead is modeled.
`mean_power_w` averages the same supplied power over one full 20–180 us cycle.
`recovery_up_v` and `recovery_down_v` are maximum absolute tracking error
`abs(VOUT−VINP)` over 50–95 us and 130–175 us, respectively. Thus the contract
requires recovery within approximately 30 us and sustained accuracy over those
windows, not merely a single late sample. `step_gain` is the difference of
90–95 us and 170–175 us mean outputs divided by 0.2 V. `peak_v` is the maximum
output over 20–100 us; `trough_v` is the minimum over 100.2–180 us.

| Metric | Unit | Acceptance | Lower / upper zero-score boundaries | Dimension |
| --- | --- | --- | --- | --- |
| `output_v` | V | 0.495–0.505 | 0.45 / 0.55 | bias |
| `bias_v` | V | 0.57–0.61 | 0.4 / 0.8 | bias |
| `power_w` | W | 0–1.8e-06 | 0 / 3.6e-06 | supply |
| `dc_gain_db` | dB | 65–90 | 40 / 110 | response |
| `unity_hz` | Hz | 100000–200000 | 0 / 400000 | response |
| `phase_margin_deg` | deg | 40–90 | 0 / 180 | response |
| `recovery_up_v` | V | 0–0.0005 | 0 / 0.02 | response |
| `recovery_down_v` | V | 0–0.0005 | 0 / 0.02 | response |
| `step_gain` | V/V | 0.99–1.01 | 0.8 / 1.2 | response |
| `mean_power_w` | W | 0–1.8e-06 | 0 / 3.6e-06 | supply |
| `peak_v` | V | 0.695–0.8 | 0.5 / 1.2 | response |
| `trough_v` | V | 0.45–0.505 | 0 / 0.7 | response |

Coefficient **7** reflects coupled two-stage compensation, loaded stability and
closed-loop settling. Unified `layout-v1` score is
`G × (60E + 20H + 20HQ)`. G requires physical validity and complete valid
measurements. E averages worst attainment in response, bias and supply;
attainment decreases linearly to the stated zero boundaries. H requires every
electrical bound. Q is `clip((152000−area)/114000,0,1)`, using absolute
functional bounding-box area in um²: target 38000, zero 152000. A completed
physical rejection scores zero; an incomplete evaluator result cannot establish
success and has no fabricated score. Report extrema cannot hide a failed load.

## Tools and Submission

Discover task, inputs, resources and harness feedback through `/protocol/task.json`,
`/protocol/resources.json` and `/protocol/harness.json`. Use the supplied IHP
primitives and KLayout, Magic and ngspice tools. Write `/workspace/output/final.gds`
and explicitly submit through the harness protocol. Host configuration, source
records and reference layouts are outside the standard solver inputs.
