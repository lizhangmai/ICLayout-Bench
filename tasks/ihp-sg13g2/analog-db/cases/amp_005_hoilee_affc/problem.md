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

Every bound applies independently to every load. `output_v`, `bias_v` and
`power_w` are DC output, external bias-port voltage and positive VDD-supplied
power. `mean_power_w` averages VDD power over the complete 2–18 us cycle,
including on-chip bias current but excluding external bias-generator overhead.
The bias sink is not credited as returned energy.

`recovery_up_v` and `recovery_down_v` are maximum `abs(VOUT−VINP)` in
5–9.5 us and 13–17.5 us, respectively: recovery within approximately 3 us
and sustained tracking, not a first band crossing. `step_gain` is the
9–9.5 us mean output minus the 17–17.5 us mean, divided by 0.2 V.
`peak_v` is maximum output over 2–10 us and `trough_v` is minimum output
over 10.04–18 us; these independently limit the intervening excursion.

| Metric | Unit | Acceptance | Lower / upper zero-score boundaries | Dimension |
| --- | --- | --- | --- | --- |
| `output_v` | V | 0.498–0.502 | 0.45 / 0.55 | bias |
| `bias_v` | V | 0.59–0.65 | 0 / 1.2 | bias |
| `power_w` | W | 0–8e-05 | 0 / 0.00016 | supply |
| `dc_gain_db` | dB | 95–125 | 40 / 140 | response |
| `unity_hz` | Hz | 1.2e+06–1.9e+06 | 0 / 3.8e+06 | response |
| `phase_margin_deg` | deg | 90–130 | 0 / 180 | response |
| `recovery_up_v` | V | 0–0.002 | 0 / 0.02 | response |
| `recovery_down_v` | V | 0–0.002 | 0 / 0.02 | response |
| `step_gain` | V/V | 0.98–1.02 | 0.8 / 1.2 | response |
| `mean_power_w` | W | 0–8e-05 | 0 / 0.00016 | supply |
| `peak_v` | V | 0.695–0.84 | 0.5 / 1.2 | response |
| `trough_v` | V | 0.48–0.505 | 0 / 0.7 | response |

Coefficient **8** covers coupled multistage compensation, physical passive
feedback and loaded loop/recovery measurements. Unified `layout-v1` score is
`G × (60E + 20H + 20HQ)`: G requires physical validity and complete valid
measurements; E averages worst attainment in response, bias and supply;
H requires all bounds. Attainment decreases linearly to the listed zero bounds.
Q is `clip((1680000−area)/1260000,0,1)` for functional
bounding-box area in um², with fixed absolute target 420000 and zero
1680000. A completed physical rejection scores zero. Incomplete
evaluation establishes neither success nor a fabricated numerical score.

## Tools and Submission

Discover inputs, resources and feedback through `/protocol/task.json`,
`/protocol/resources.json` and `/protocol/harness.json`. Use the supplied IHP
primitives with KLayout, Magic and ngspice. Write `/workspace/output/final.gds`
and explicitly submit through the harness protocol. Host configuration, source
records and reference layouts are outside the standard solver inputs.
