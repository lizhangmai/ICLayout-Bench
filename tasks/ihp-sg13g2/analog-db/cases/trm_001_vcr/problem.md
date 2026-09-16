# Resistor-Pullup NMOS Shunt Trim Layout Task

## Objective

Implement `trm_001_vcr`, a voltage-controlled NMOS shunt with a physical
approximately 200 kohm supply pullup. Preserve the source W=2 um / L=0.5 um
NMOS, eight series high-poly segments and explicit substrate tap. Qualification
measures loaded trim range, monotonic control, operating-point conductance,
temperature/load sensitivity and finite control-step recovery. This is an
unbuffered nonlinear control node, not an ideal programmable resistor or DAC.

## Inputs and Interface

- `materials/circuit.cdl`: authoritative native LVS circuit.
- `materials/circuit.spice`: matching process-model representation.
- `materials/testbench.spice`: control sweeps, conductance and loaded recovery.

Ordered ports: `vdd vcode vout vss`. VDD is supply, VCODE controls the shunt
MOS gate, VOUT is the pullup/shunt junction and VSS is return. The NMOS source
and substrate connect through the explicit VSS tap; the physical poly body
uses the same substrate. Eight series `rhigh` segments connect VDD to VOUT,
each W=1 um / L=17.465 um, m=1 and b=0. They replace the source ideal 200 kohm
resistor and remain inside the DUT. Preserve device models, dimensions and
connectivity; native equivalent resistor merging is allowed only when LVS and
all other checks pass. There are no internal ideal sources or extra bias ports.

## Operating Conditions

Typical IHP LV MOS/poly models, all eight combinations of supplies 1.1/1.3 V,
temperatures 27/85 C and external output loads 500 kohm/1 Mohm. A 1 pF output
load is external test apparatus. DC operating point uses VCODE=0.4 V.
Sweep VCODE from 0.2 to 0.8 V in 2 mV increments; every sampled slope must
satisfy the monotonic-control bound. This is the declared sampled sweep,
not a proof of global monotonicity beyond the control interval.

For transient, VCODE rises 0.3→0.5 V at 2–2.02 us and falls at
10.02–10.04 us, repeating every 16 us. Run to 18 us with 2 ns maximum step,
Gear order 2, `rshunt=1e12`, `reltol=1e-5`, `abstol=1e-14`, `vntol=1e-8`.
No output clamp, feedback servo or ideal storage is internal to the DUT.

## Physical Requirements

Submit GDSII top cell `trm_001_vcr`, at most 10 MiB. Pass native main/maximal DRC
without waivers (standalone scope, density/antenna disabled), strict named-port
LVS with explicit tap and a 110 × 80 um functional outline. The runtime
outline includes complete device, resistor, contact and routing drawing layers;
annotation/pin-purpose layers do not contribute to its area.
Candidate Magic RC must preserve physical MOS/poly and interconnect parasitics.
The extractor idealizes the substrate contact; source simulation includes the
finite tap model. Distributed substrate effects, PVT, mismatch, noise,
precision trimming and fabrication signoff remain outside qualification.

## Electrical Requirements and Scoring

`output_v` is DC output at VCODE=0.4 V. `high_v`/`low_v` are outputs at
control 0.2/0.8 V and `span_v` is their difference. `knee_code_v` is the first
descending output crossing of 0.2 V. `maximum_slope` is the maximum of ngspice's
`deriv(VOUT)` over the full control sweep; its negative upper bound requires
sampled monotonic decrease. `mid_v` repeats the 0.4 V DC sweep observation as
a diagnostic consistency check and is not independently scored.

At each swept operating point, the port-observed shunt conductance is
`G=(-I(VDD)-VOUT/RLOAD)/VOUT`. `conductance_04_s` and `conductance_06_s`
sample G at control 0.4/0.6 V; `conductance_ratio` is G(0.6)/G(0.4).
This is finite-bias I/V conductance including candidate wiring and the
specified substrate boundary, not small-signal conductance or an isolated MOS
model parameter. External resistor current is removed explicitly.

Recovery errors are maximum deviations from the 9–9.5 us low-output mean
in 5–9.5 us, and from the 17–17.5 us high-output mean in 13–17.5 us.
`step_span_v` is high mean minus low mean. Range and conductance requirements
separately anchor the static transfer; recovery cannot be met by a constant
output. `power_w` is positive DC VDD supply power; `mean_power_w` averages the
same supply over the full 2–18 us cycle. External control-generator overhead
is excluded and returned energy is not credited in the calibrated positive
VDD-current windows.

| Metric | Unit | Acceptance | Lower / upper zero-score boundaries | Dimension |
| --- | --- | --- | --- | --- |
| `output_v` | V | 0.04–0.07 | 0 / 0.15 | response |
| `power_w` | W | 0–1.1e-05 | 0 / 2.2e-05 | supply |
| `high_v` | V | 0.68–1.07 | 0.3 / 1.3 | response |
| `low_v` | V | 0.005–0.016 | 0 / 0.1 | response |
| `knee_code_v` | V | 0.3–0.38 | 0.2 / 0.5 | response |
| `maximum_slope` | V/V | -0.1–-0.005 | -10 / 0.05 | response |
| `span_v` | V | 0.65–1.08 | 0 / 1.3 | response |
| `conductance_04_s` | S | 8e-05–0.00015 | 0 / 0.0003 | response |
| `conductance_06_s` | S | 0.0003–0.0005 | 0 / 0.001 | response |
| `conductance_ratio` | 1 | 2.5–5 | 1 / 10 | response |
| `recovery_down_v` | V | 0–0.0001 | 0 / 0.1 | response |
| `recovery_up_v` | V | 0–0.0001 | 0 / 0.1 | response |
| `mean_power_w` | W | 0–1e-05 | 0 / 2e-05 | supply |
| `step_span_v` | V | 0.25–0.7 | 0 / 1.3 | response |

Every bound applies independently at every supply/temperature/load combination.
Coefficient **4** reflects one MOS with a physical resistor chain and nonlinear
loaded-control measurements. Unified `layout-v1` score is
`G × (60E + 20H + 20HQ)`: G requires physical validity and complete measurements;
E averages worst attainment in response and supply, with linear decrease to
zero-score boundaries; H requires every bound. Q is
`clip((32000−area)/24000,0,1)` for area in um², with fixed absolute target 8000
and zero 32000. Physical rejection scores zero; incomplete evaluation cannot
establish success or fabricate a score.

## Tools and Submission

Discover inputs, resources and feedback through `/protocol/task.json`,
`/protocol/resources.json` and `/protocol/harness.json`. Use the supplied IHP
primitives with KLayout, Magic and ngspice. Write `/workspace/output/final.gds`
and explicitly submit through the harness. Host configuration, source records
and reference layouts are outside the standard solver inputs.
