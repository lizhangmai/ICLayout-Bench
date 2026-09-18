# Current-Buffered Compensation OTA Layout Task

## Objective

Lay out `amp_005_hoilee_affc` with its physical compensation and fixed transistor network,
for the declared loop response and sustained unity-feedback step recovery.

The folded PMOS-input stage drives `net050`; a PMOS/diode/mirror stage
drives `net049`, followed by the NMOS output stage. A parallel path drives
the output PMOS directly from `net050`. One capacitor connects `net049` to
output. The other connects output to `net1`, the source terminal of an
additional common-gate NMOS returning current to `net050`. Six additional
MOS (XM59–XM64) form this biased current-buffer branch; these devices and
the low-impedance compensation terminal distinguish it from direct Miller
and shared-resistor compensation.

The maintained circuit retains all 30 source MOS groups as 276 physical
fingers, 7 MIM units and 0 high-poly segments. MOS W/L are rounded to the nearest 0.01 um process grid. All source multiplicities are retained.
The maintained 3.15498 uA sink is external through `net013`.
The external bias is deliberately calibrated to 0.3 times the source current; this is not an unchanged upstream operating point. Physical
substrate and separate N-well contacts retain the input PMOS bodies at their
common source `net31`, electrically separate from the VDD well. No internal
ideal bias source or output servo is introduced. Capacitor values are rounded
to physical geometry; every branch remains internal to the DUT.


## Inputs and Interface

- `materials/circuit.cdl`: authoritative native LVS circuit.
- `materials/circuit.spice`: matching process-model circuit.
- `materials/testbench.spice`: public bias, AC injection and transient deck.

Ordered ports: `vss vdd vinn vinp vout net013`. VSS is return, VDD is supply,
VINN/VINP are inverting/noninverting inputs, VOUT is output, and `net013`
connects the external 3.15498 uA sink to VSS. Input PMOS bodies retain
the separate source-tied well; other PMOS bodies use the VDD well and NMOS
bodies use the VSS substrate contact. Preserve device W/L/m, body connectivity,
all internal branches and total multiplicities in the authoritative netlist.
Native equivalent parallel fingers are allowed only when LVS and electrical
requirements pass. Do not short distinct ports or create extra driven monitors.

Internal passives, distinct from the external load:

- `c0`: `net049` → `vout`, 4 parallel `cap_cmim` unit(s), each 44.775 × 44.775 um; nominal total 12.05746 pF.
- `c1`: `vout` → `net1`, 3 parallel `cap_cmim` unit(s), each 49.965 × 49.965 um; nominal total 11.258239 pF.


## Operating Conditions

Use typical MOS/MIM/poly models, 27 C, VDD=1.2 V and the stated external bias.
All output loads 5/10/20 pF must pass. At DC, VINP=0.5 V and VOUT drives VINN
through a zero-volt measurement source. AC injects 1 V in series with this
feedback connection, with VINP AC=0. The return ratio is
`T=-V(vout)/V(vm)` at this high-impedance MOS input boundary. Sweep 0.01 Hz
to 100 MHz at 150 points/decade. Use continuous phase without an arbitrary
low-frequency phase-offset correction; the first descending 0 dB crossing
defines unity frequency and `180+phase(T)` there defines phase margin.
A missing crossing is an evaluator error.

VINP rises 0.5→0.7 V at 2–2.02 us and falls at 10.02–10.04 us, repeating
every 16 us. Simulate 0–18 us with Gear order 2, 2 ns maximum step,
`rshunt=1e12`, `reltol=1e-5`, `abstol=1e-14`, `vntol=1e-8`.
The numerical shunt is not a manufactured bias or startup device.
PVT, mismatch, noise, distortion, rail-to-rail operation, supply startup and
arbitrary-load stability remain outside the contract.

## Physical Requirements

Submit GDSII top cell `amp_005_hoilee_affc`, at most 10 MiB. Pass native IHP main/maximal
DRC without waivers (standalone scope; density/antenna disabled), strict
named-interface LVS with explicit taps and a 3300 × 140 um
functional envelope. All functional device, contact and routing drawing layers
listed in the runtime `outline` constraint contribute to bounding-box area;
annotation and pin-purpose layers do not.

Post-layout simulation consumes candidate-derived Magic RC with the physical
MIM/poly devices and interconnect parasitics. Half-grid GDS import is explicit.
Magic idealizes substrate/well taps; source simulation retains finite tap models.
Distributed substrate resistance/noise and fabrication signoff are unqualified.

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

Area reference: **42066.41 um2**. 286 expanded device instances; sum of device/contact envelopes 27776.6506 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

The capability coefficient remains **8**; it is independent of
the reference-relative task score.

## Tools and Submission

Solve budget: **3 hours**.

Discover inputs, resources and feedback through `/protocol/task.json`,
`/protocol/resources.json` and `/protocol/harness.json`. Use the supplied IHP
primitives with KLayout, Magic and ngspice. Write `/workspace/output/final.gds`
and explicitly submit through the harness protocol. Host configuration, source
records and reference layouts are outside the standard solver inputs.
