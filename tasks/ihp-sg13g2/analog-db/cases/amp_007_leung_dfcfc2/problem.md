# Auxiliary-Stage Miller Compensation OTA Layout Task

## Objective

Lay out `amp_007_leung_dfcfc2` with its physical compensation and fixed transistor network,
for the declared loop response and sustained unity-feedback step recovery.

The folded PMOS-input stage drives `net050`; the PMOS/diode/mirror path
drives `net049` and then the NMOS output stage. Direct feedforward drives
the output PMOS from `net050`. A separate PMOS common-source branch has
gate `net050`, drain `net2` and an NMOS bias sink. C1 connects `net050` to
output; C2 connects `net050` to `net2`, across the auxiliary stage. This
compensation branch is distinct from output-to-current-buffer injection and
from the `net049`-controlled auxiliary termination in the other cases.

The maintained circuit retains all 26 source MOS groups as 440 physical
fingers, 10 MIM units and 0 high-poly segments. All MOS dimensions/multiplicities are retained exactly.
The maintained 20 uA sink is external through `net1`.
The source bias-current value is retained. Physical
substrate and separate N-well contacts retain the input PMOS bodies at their
common source `net31`, electrically separate from the VDD well. No internal
ideal bias source or output servo is introduced. Capacitor values are rounded
to physical geometry; every branch remains internal to the DUT.


## Inputs and Interface

- `materials/circuit.cdl`: authoritative native LVS circuit.
- `materials/circuit.spice`: matching process-model circuit.
- `materials/testbench.spice`: public bias, AC injection and transient deck.

Ordered ports: `vss vdd vinn vinp vout net1`. VSS is return, VDD is supply,
VINN/VINP are inverting/noninverting inputs, VOUT is output, and `net1`
connects the external 20 uA sink to VSS. Input PMOS bodies retain
the separate source-tied well; other PMOS bodies use the VDD well and NMOS
bodies use the VSS substrate contact. Preserve device W/L/m, body connectivity,
all internal branches and total multiplicities in the authoritative netlist.
Native equivalent parallel fingers are allowed only when LVS and electrical
requirements pass. Do not short distinct ports or create extra driven monitors.

Internal passives, distinct from the external load:

- `c1`: `net050` → `vout`, 5 parallel `cap_cmim` unit(s), each 47.61 × 47.61 um; nominal total 17.038429 pF.
- `c2`: `net050` → `net2`, 5 parallel `cap_cmim` unit(s), each 47.61 × 47.61 um; nominal total 17.038429 pF.


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

The transient nonlinear iteration ceiling is explicitly `itl4=1000`, with
unchanged accuracy tolerances. This allows the retained high-multiplicity
mirror/auxiliary network to converge; it is not a relaxed acceptance limit.

## Physical Requirements

Submit GDSII top cell `amp_007_leung_dfcfc2`, at most 10 MiB. Pass native IHP main/maximal
DRC without waivers (standalone scope; density/antenna disabled), strict
named-interface LVS with explicit taps and a 3500 × 130 um
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
| `bias_v` | V | 0.49–0.55 | 0 / 1.2 | bias |
| `power_w` | W | 0–0.00035 | 0 / 0.0007 | supply |
| `dc_gain_db` | dB | 75–105 | 40 / 140 | response |
| `unity_hz` | Hz | 1.8e+06–2.8e+06 | 0 / 5.6e+06 | response |
| `phase_margin_deg` | deg | 65–100 | 0 / 180 | response |
| `recovery_up_v` | V | 0–0.002 | 0 / 0.02 | response |
| `recovery_down_v` | V | 0–0.002 | 0 / 0.02 | response |
| `step_gain` | V/V | 0.98–1.02 | 0.8 / 1.2 | response |
| `mean_power_w` | W | 0–0.00035 | 0 / 0.0007 | supply |
| `peak_v` | V | 0.695–0.75 | 0.5 / 1.2 | response |
| `trough_v` | V | 0.48–0.505 | 0 / 0.7 | response |

Coefficient **8** covers coupled multistage compensation, physical passive
feedback and loaded loop/recovery measurements. Unified `layout-v1` score is
`G × (60E + 20H + 20HQ)`: G requires physical validity and complete valid
measurements; E averages worst attainment in response, bias and supply;
H requires all bounds. Attainment decreases linearly to the listed zero bounds.
Q is `clip((1800000−area)/1350000,0,1)` for functional
bounding-box area in um², with fixed absolute target 450000 and zero
1800000. A completed physical rejection scores zero. Incomplete
evaluation establishes neither success nor a fabricated numerical score.

## Tools and Submission

Discover inputs, resources and feedback through `/protocol/task.json`,
`/protocol/resources.json` and `/protocol/harness.json`. Use the supplied IHP
primitives with KLayout, Magic and ngspice. Write `/workspace/output/final.gds`
and explicitly submit through the harness protocol. Host configuration, source
records and reference layouts are outside the standard solver inputs.
