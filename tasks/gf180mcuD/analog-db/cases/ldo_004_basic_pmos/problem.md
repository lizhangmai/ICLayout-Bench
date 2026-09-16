# Externally Biased 1.8 V PMOS Regulator Core Layout Task

## Objective

Implement the fixed `ldo_004_basic_pmos` regulator core in GF180MCU D and submit
self-contained GDS. The circuit contains an error amplifier, a PMOS pass array
and a physical feedback divider. Reference and tail-current generation are
external to this core.

## Inputs and Interface

`materials/circuit.spice` is authoritative for LVS and source calibration.
`materials/testbench.spice`, `materials/transient.spice` and
`materials/dropout.spice` define the DC/AC, load-step and dropout measurements.
The ordered ports are `vdd vout vref ibias vss`: input supply, regulated output,
reference-voltage input, error-amplifier tail node, and return. An external
200 uA sink connects `ibias` to VSS; this is not a voltage-bias input.

Retain the two NMOS input devices at W/L = 46/0.5 um, two PMOS mirror devices
at 50/0.5 um, and the PMOS pass device at 10/0.3 um with multiplicity 100.
Each feedback resistor is `ppolyf_u_1k`, width 2 um and length 200 um, giving
100 squares of nominal 1 kohm/square poly. Preserve connectivity, dimensions
and body connections. Placement, routing and electrically equivalent device
splitting/source-drain interchange are allowed only as accepted by the declared
LVS checks. Provide physical well/substrate contacts to the declared rails.
No statistical matching or common-centroid constraint is scored.

## Operating Conditions

Use typical 3.3 V MOS and poly-resistor models at 27 C, with statistical
variation disabled, VSS = 0 V, external VREF = 0.9 V and a 200 uA tail sink.
The external output capacitor is an ideal 1 uF, without added ESR. All nine
combinations of VDD = 2.2, 2.7, 3.3 V and load = 0.1, 1, 5 mA are required.
DC measurements follow the operating-point solve. AC uses 60 points per decade
from 1 Hz to 100 MHz. Supply rejection drives VDD with 1 V AC and zero AC load;
output impedance drives the load sink with 1 A AC and zero AC supply.

At each of the three supplies, the transient starts from the DC operating point
at 0.1 mA load. Load rises to 5 mA between 1 and 1.0001 ms, then falls to 0.1 mA
between 2 and 2.0001 ms. Run to 3 ms with a 200 ns output step. Evaluate peak
absolute output error relative to 1.8 V over 0.9 to 3 ms, high-load settled error
over 1.2 to 1.9 ms, low-load settled error over 2.2 to 3 ms, and minimum tail
voltage over 0.9 to 3 ms. These windows require recovery within 200 us.

The separate dropout sweep uses 5 mA load and sweeps VDD from 1.6 to 2.4 V
in 5 mV steps. Dropout is the supply voltage at the first rising crossing of
VOUT = 1.75 V, minus 1.75 V, using interpolated crossing measurement.
All ideal supplies, sinks and the output capacitor are testbench apparatus.

## Physical Requirements

Submit top cell `ldo_004_basic_pmos` with all five named electrical ports,
resolved hierarchy and a maximum file size of 10 MiB. Artifact, GF180 variant-D
DRC including antenna checks, strict named-port LVS and geometry must pass.
There are no DRC waivers. Chip-level density and seal-ring closure are outside
the standalone-block check scope.

The functional bounding box must fit within 800 by 400 um. Area includes all
process device and routing drawing layers listed in the runtime constraints:
wells, implants, active, poly, contacts, metals/vias and passive/device markers.
Annotation text and pin-purpose shapes are excluded; functional routing must
use drawing layers.

The judge extracts distributed interconnect RC from the submitted GDS and uses
that extracted DUT in every simulation. MOS and physical resistor geometry are
candidate-derived. The model boundary retains external body connections but
does not include a distributed silicon substrate network. Qualification covers
nominal DC, AC supply rejection/output impedance and these load steps; it does
not establish full loop phase margin, startup, PVT, statistical mismatch, noise,
EM/current-density limits, thermal behavior or fabrication signoff.

## Electrical Requirements and Scoring

Every required observation must be finite and satisfy its inclusive band;
aggregation cannot hide a failing operating point. A missing dropout crossing
or incomplete extraction/simulation cannot establish success.

| Metric | Definition | Unit | Acceptance | Zero-score boundaries | Dimension |
| --- | --- | --- | --- | --- | --- |
| Output voltage | DC VOUT at each of nine operating points | V | 1.78 to 1.82 | <= 1.5 or >= 2.1 | bias |
| Tail voltage | DC V(ibias) at each operating point | V | 0.05 to 0.15 | <= 0 or >= 0.3 | bias |
| Quiescent current | Supply input current minus measured load current | A | 0 to 0.00025 | < 0 or >= 0.0005 | supply |
| Input power | Power delivered by VDD plus external VREF | W | 0 to 0.018 | < 0 or >= 0.025 | supply |
| Supply rejection | -20 log10(abs(VOUT/VDD)) at 1 kHz | dB | >= 40 | <= 0 | response |
| Output impedance peaking | 20 log10(max(abs(Zout))/abs(Zout at 1 Hz)), 1 Hz to 100 MHz | dB | 0 to 6 | < 0 or >= 20 | response |
| Peak output error | Maximum abs(VOUT - 1.8 V), 0.9 to 3 ms | V | 0 to 0.025 | < 0 or >= 0.1 | response |
| High-load settled error | Maximum abs(VOUT - 1.8 V), 1.2 to 1.9 ms | V | 0 to 0.010 | < 0 or >= 0.05 | response |
| Low-load settled error | Maximum abs(VOUT - 1.8 V), 2.2 to 3 ms | V | 0 to 0.010 | < 0 or >= 0.05 | response |
| Transient tail minimum | Minimum V(ibias), 0.9 to 3 ms | V | >= 0.05 | <= 0 | bias |
| Dropout voltage | Input-output difference at the defined 1.75 V crossing | V | 0 to 0.2 | < 0 or >= 0.5 | response |

Input power includes the delivered load power. Quiescent current includes the
core tail path and divider; it excludes the external load. The external tail
sink absorbs power already supplied through VDD. Output impedance peaking is
an observable closed-loop response metric, not a loop phase-margin measurement.

Scoring is `S = G * (60*E + 20*H + 20*H*Q)`. `G` requires passing physical
checks and complete extraction/measurements. `E` averages response, bias and
supply attainment, using the worst observation in each dimension. Attainment
is 1 inside each band and falls linearly toward its zero boundary. `H` is 1
only if every electrical requirement passes.
`Q = clip((320000 - area_um2)/(320000 - 80000), 0, 1)` uses fixed absolute area
anchors. Physical rejection scores 0; blocking evaluator errors produce no
score. The coefficient is 7 for a closed-loop regulator combining amplification,
a power-device array, feedback passives and multiple operating regimes.

## Tools and Submission

Use the reviewed GF180 PDK/EDA resources listed in `/protocol/resources.json`.
KLayout checks the layout, Magic extracts RC and ngspice simulates the circuit.
`/protocol/task.json` provides frozen constraints and evaluation requirements;
`/protocol/harness.json` describes the active harness. If `process-feedback.v1`
is exposed, use its published helper for interim checks. Write
`/workspace/output/final.gds`, then explicitly submit the snapshot with
`python -I /protocol/submit.py`.
