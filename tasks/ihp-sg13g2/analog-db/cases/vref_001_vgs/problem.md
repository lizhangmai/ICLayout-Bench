# Mixed LV/HV VGS Reference Layout Task

## Objective

Implement the two-transistor `vref_001_vgs` reference with its original device
sizes and connections. An upper LV NMOS has gate and source at VREF; a lower
HV NMOS is diode-connected. The maintained function is a high-impedance,
approximately 0.36 V reference for picoampere loads. It is not a bandgap,
precision reference, buffered supply or temperature sensor.

## Inputs and Interface

The declared inputs are this description, `materials/circuit.cdl` for native
LVS, the equivalent `materials/circuit.spice`, and `materials/testbench.spice`.
Ordered ports are `vdd vref vss`: positive supply, reference output, and return.
The LV NMOS has W/L=2.5/2 um, D=VDD, G=S=VREF, B=VSS. The HV NMOS has
W/L=1/2 um, D=G=VREF, S=B=VSS. Both multiplicities are one.

Retain the explicit 40 × 2 um marked substrate tap (A=80 um², P=84 um),
with both terminals on VSS. An unmarked substrate contact establishes that
same-net body boundary. Additional legal same-net contacts are permitted
only when native LVS and the declared checks pass. Do not replace the HV
device with an LV device or change either gate/source connection. The source
simulator represents the marked tap with its finite 5.9756097561 ohm PDK
equivalent; its two terminals are the same net. Parallel fingering is allowed
only if total dimensions, multiplicity, body mapping and all checks agree.

## Operating Conditions

Use the pinned IHP typical LV/HV PSP models. Nine jobs combine VDD=1.0,
1.2 and 1.5 V with temperatures −20, 27 and 85 °C. The only external
capacitance is 100 fF from VREF to VSS. No numerical `rshunt` is added.
Use `gmin=1e-16 S`, `reltol=1e-6`, `abstol=1e-18 A`, `vntol=1e-10 V`,
Gear order two and maximum transient step 1 us. These small currents require
the specified numerical conditioning; default simulator tolerances do not
establish this contract.

For each job, the DC operating point has the declared supply and zero load.
The separate transient starts with VREF=0 and otherwise zero stored charge
(`uic`). VDD rises linearly from zero to its declared value over 100 us.
The run ends at 50 ms. ILOAD is positive when withdrawing current from VREF:
0→+1 pA during 10–10.01 ms, +1→0 pA during 20–20.01 ms,
0→−1 pA during 30–30.01 ms, and −1→0 pA during 40–40.01 ms.
It holds each value between edges. Negative load is an external current
injection, not on-chip power generation.

Each job also sweeps supply 1.0–1.5 V in 10 mV increments at its declared
temperature, load −1–+1 pA in 0.1 pA increments at its declared supply and
temperature, and temperature −20–85 °C in 5 °C increments at its declared
supply. DC sweeps have no time-varying stimulus; line and temperature sweeps
use zero load. All endpoints participate. These are finite sampled conditions,
not process-corner, mismatch or arbitrary temperature/load guarantees.
The DC load sweep uses a −1–+1 V external control in 0.1 V increments and
a 1 pA/V transconductance stimulus; it avoids a tiny-current sweep endpoint
tolerance without changing the DUT or its actual −1–+1 pA load range.

## Physical Requirements

Submit a GDSII with top cell `vref_001_vgs`, at most 1 MiB. It must pass
native main/maximal SG13G2 DRC without waivers, strict named-port LVS, and a
100 × 100 um functional outline. Density and antenna checks are outside
the declared standalone DRC scope. The footprint includes every device,
contact and routing drawing layer enumerated in the runtime constraints;
annotation and pin-purpose layers cannot conceal functional geometry.

Candidate-derived Magic distributed RC must retain both LV/HV model calls,
their dimensions and their actual junction/interconnect loading. Extraction
idealizes well/substrate contacts and does not establish distributed substrate
resistance or noise. Only Metal3 text layer 30/25 supplies extraction labels;
native DRC/LVS still inspect the complete original GDS and physical taps.
The external 100 fF load is additional to candidate capacitance.

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
| `reference_v` | Unloaded DC VREF | V | target / target | 0 … 1.5 | 1.5 |
| `supply_a` | Unloaded DC −I(VDD) | A | minimize / ratio | 0 … +∞ | 1e-12 |
| `power_w` | Unloaded DC −VDD·I(VDD) | W | minimize / ratio | 0 … +∞ | 1e-12 |
| `startup_error_v` | Maximum absolute reference error, 8–9 ms | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `load_error_v` | Same, 18–19 ms under +1 pA | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `release_error_v` | Same, 28–29 ms | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `injection_error_v` | Same, 38–39 ms under −1 pA | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `return_error_v` | Same, 48–49 ms | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `minimum_v` | tm20_v10:minimum_v, tm20_v12:minimum_v, tm20_v15:minimum_v, t27_v10:minimum_v, t27_v12:minimum_v, t27_v15:minimum_v, t85_v10:minimum_v, t85_v12:minimum_v, t85_v15:minimum_v | V | target / target | −∞ … +∞ | 1.5 |
| `maximum_v` | tm20_v10:maximum_v, tm20_v12:maximum_v, tm20_v15:maximum_v, t27_v10:maximum_v, t27_v12:maximum_v, t27_v15:maximum_v, t85_v10:maximum_v, t85_v12:maximum_v, t85_v15:maximum_v | V | target / target | 0 … 1.5 | 1.5 |
| `line_min_v` | tm20_v10:line_min_v, tm20_v12:line_min_v, tm20_v15:line_min_v, t27_v10:line_min_v, t27_v12:line_min_v, t27_v15:line_min_v, t85_v10:line_min_v, t85_v12:line_min_v, t85_v15:line_min_v | V | target / target | 0 … 1.5 | 1.5 |
| `line_max_v` | tm20_v10:line_max_v, tm20_v12:line_max_v, tm20_v15:line_max_v, t27_v10:line_max_v, t27_v12:line_max_v, t27_v15:line_max_v, t85_v10:line_max_v, t85_v12:line_max_v, t85_v15:line_max_v | V | target / target | 0 … 1.5 | 1.5 |
| `line_span_v` | Supply-sweep maximum minus minimum | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `temperature_min_v` | tm20_v10:temperature_min_v, tm20_v12:temperature_min_v, tm20_v15:temperature_min_v, t27_v10:temperature_min_v, t27_v12:temperature_min_v, t27_v15:temperature_min_v, t85_v10:temperature_min_v, t85_v12:temperature_min_v, t85_v15:temperature_min_v | V | target / target | 0 … 1.5 | 1.5 |
| `temperature_max_v` | tm20_v10:temperature_max_v, tm20_v12:temperature_max_v, tm20_v15:temperature_max_v, t27_v10:temperature_max_v, t27_v12:temperature_max_v, t27_v15:temperature_max_v, t85_v10:temperature_max_v, t85_v12:temperature_max_v, t85_v15:temperature_max_v | V | target / target | 0 … 1.5 | 1.5 |
| `temperature_span_v` | Temperature-sweep maximum minus minimum | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `output_resistance_ohm` | (Unloaded DC VREF − DC VREF at +1 pA)/1 pA | ohm | minimize / ratio | 0 … +∞ | 1e-06 |
| `loaded_reference_v` | DC VREF at +1 pA | V | target / target | 0 … 1.5 | 1.5 |

Area reference: **210.61 um2**. 3 expanded device instances; sum of device/contact envelopes 121.7863 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

The capability coefficient remains **5**; it is independent of
the reference-relative task score.

## Tools and Submission

Solve budget: **3 hours**.

Use the supplied task, process resources and runtime protocol. Write
`/workspace/output/final.gds` and submit it through `python -I /protocol/submit.py`.
The evaluator independently checks the frozen submitted GDS. Collection
licenses, reference layouts, research files and host configuration are not
solver inputs.
