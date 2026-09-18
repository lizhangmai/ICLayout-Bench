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
| `output_v` | dc_0_0:output_v, dc_0_1:output_v, dc_0_2:output_v, dc_1_0:output_v, dc_1_1:output_v, dc_1_2:output_v, dc_2_0:output_v, dc_2_1:output_v, dc_2_2:output_v | V | target / target | 0 … 3.3 | 3.3 |
| `tail_v` | dc_0_0:tail_v, dc_0_1:tail_v, dc_0_2:tail_v, dc_1_0:tail_v, dc_1_1:tail_v, dc_1_2:tail_v, dc_2_0:tail_v, dc_2_1:tail_v, dc_2_2:tail_v | V | target / target | 0 … 3.3 | 3.3 |
| `quiescent_a` | dc_0_0:quiescent_a, dc_0_1:quiescent_a, dc_0_2:quiescent_a, dc_1_0:quiescent_a, dc_1_1:quiescent_a, dc_1_2:quiescent_a, dc_2_0:quiescent_a, dc_2_1:quiescent_a, dc_2_2:quiescent_a | A | minimize / ratio | 0 … +∞ | 1e-12 |
| `power_w` | dc_0_0:power_w, dc_0_1:power_w, dc_0_2:power_w, dc_1_0:power_w, dc_1_1:power_w, dc_1_2:power_w, dc_2_0:power_w, dc_2_1:power_w, dc_2_2:power_w | W | minimize / ratio | 0 … +∞ | 1e-12 |
| `psrr_db` | dc_0_0:psrr_db, dc_0_1:psrr_db, dc_0_2:psrr_db, dc_1_0:psrr_db, dc_1_1:psrr_db, dc_1_2:psrr_db, dc_2_0:psrr_db, dc_2_1:psrr_db, dc_2_2:psrr_db | dB | maximize / db20 | −∞ … +∞ | — |
| `peaking_db` | dc_0_0:peaking_db, dc_0_1:peaking_db, dc_0_2:peaking_db, dc_1_0:peaking_db, dc_1_1:peaking_db, dc_1_2:peaking_db, dc_2_0:peaking_db, dc_2_1:peaking_db, dc_2_2:peaking_db | dB | minimize / db20 | −∞ … +∞ | — |
| `peak_error_v` | step_0:peak_error_v, step_1:peak_error_v, step_2:peak_error_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `high_settled_error_v` | step_0:high_settled_error_v, step_1:high_settled_error_v, step_2:high_settled_error_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `low_settled_error_v` | step_0:low_settled_error_v, step_1:low_settled_error_v, step_2:low_settled_error_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `tail_min_v` | step_0:tail_min_v, step_1:tail_min_v, step_2:tail_min_v | V | target / target | 0 … 3.3 | 3.3 |
| `dropout_v` | dropout:dropout_v | V | minimize / ratio | 0 … +∞ | 1e-06 |

Area reference: **7597.32 um2**. 106 expanded device instances; sum of device/contact envelopes 4876.0000 um2, per-side envelope allowance 1 um, 50% routing allowance and outer margin 2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

The capability coefficient remains **7**; it is independent of
the reference-relative task score.

## Tools and Submission

Solve budget: **3 hours**.

Use the reviewed GF180 PDK/EDA resources listed in `/protocol/resources.json`.
KLayout checks the layout, Magic extracts RC and ngspice simulates the circuit.
`/protocol/task.json` provides frozen constraints and evaluation requirements;
`/protocol/harness.json` describes the active harness. If `process-feedback.v1`
is exposed, use its published helper for interim checks. Write
`/workspace/output/final.gds`, then explicitly submit the snapshot with
`python -I /protocol/submit.py`.

Use a GDS database unit of 0.001 um, as required by the GF180MCU DRC deck.
