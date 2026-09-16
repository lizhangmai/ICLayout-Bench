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

Every observation must be finite and satisfy its own inclusive limits. The
reference for transient errors is that job's unloaded DC VREF, not a fitted
waveform or the candidate's last transient sample. Errors are maxima over
the entire stated interval, including interpolated endpoints.

| Metric | Definition | Unit | Acceptance | Zero boundaries |
| --- | --- | --- | --- | --- |
| `reference_v` | Unloaded DC VREF | V | 0.35–0.37 | 0.30 / 0.42 |
| `supply_a` | Unloaded DC −I(VDD) | A | 5e-12–3e-9 | 0 / 6e-9 |
| `power_w` | Unloaded DC −VDD·I(VDD) | W | 0–5e-9 | 0 / 1e-8 |
| `startup_error_v` | Maximum absolute reference error, 8–9 ms | V | ≤1e-5 | upper 1e-3 |
| `load_error_v` | Same, 18–19 ms under +1 pA | V | ≤0.004 | upper 0.012 |
| `release_error_v` | Same, 28–29 ms | V | ≤1e-5 | upper 1e-3 |
| `injection_error_v` | Same, 38–39 ms under −1 pA | V | ≤0.004 | upper 0.012 |
| `return_error_v` | Same, 48–49 ms | V | ≤1e-5 | upper 1e-3 |
| `minimum_v` / `maximum_v` | Full transient VREF extrema | V | ≥−1e-5 / ≤0.375 | lower −0.01 / upper 0.42 |
| `line_min_v` / `line_max_v` | Supply-sweep VREF extrema | V | ≥0.35 / ≤0.37 | lower 0.30 / upper 0.42 |
| `line_span_v` | Supply-sweep maximum minus minimum | V | 0–0.012 | 0 / 0.03 |
| `temperature_min_v` / `temperature_max_v` | Temperature-sweep VREF extrema | V | ≥0.35 / ≤0.37 | lower 0.30 / upper 0.42 |
| `temperature_span_v` | Temperature-sweep maximum minus minimum | V | 0–0.003 | 0 / 0.01 |
| `loaded_reference_v` | DC VREF at +1 pA | V | 0.35–0.37 | 0.30 / 0.42 |
| `output_resistance_ohm` | (Unloaded DC VREF − DC VREF at +1 pA)/1 pA | ohm | 0–4e9 | 0 / 1e10 |

Output resistance is a finite-load secant, not broadband impedance. Supply
power excludes external load injection and bias-generator overhead. This
two-transistor self-biased reference has no separate amplifier/CMFB loop or
declared crossover metric; startup, DC sensitivity and finite load recovery
are its observable feedback checks. No exhaustive internal-pole claim is made.

Use the single `layout-v1` score `S=G·(60E+20H+20H·Q)`. G requires passing
artifact, DRC, LVS, hard geometry and complete valid extraction/simulation.
A conclusive physical rejection scores zero; an evaluator error that prevents
grading gives null. H is one only when every electrical bound passes. E is
the mean of the response, bias and supply dimensions, each taking its worst
metric and each metric its worst observation. Transient errors, line/temperature
spans and output resistance belong to response; power belongs to supply;
all other metrics belong to bias. Attainment is one within acceptance and
falls linearly to each stated zero boundary outside it, clipped to [0,1].

`Q=clip((6400−area)/(6400−1600),0,1)` with area in um². The fixed 1600 um²
full-area target accommodates a legal two-device mixed-process layout with
both body contacts and complete routing; 6400 um² is the zero-utility boundary.
Area earns points only after full electrical acceptance. Coefficient 5 reflects
a complete compact self-biased block with stringent leakage, load and startup
requirements. It is not a claim of precision, optimal area or fabrication signoff.

## Tools and Submission

Use the supplied task, process resources and runtime protocol. Write
`/workspace/output/final.gds` and submit it through `python -I /protocol/submit.py`.
The evaluator independently checks the frozen submitted GDS. Collection
licenses, reference layouts, research files and host configuration are not
solver inputs.
