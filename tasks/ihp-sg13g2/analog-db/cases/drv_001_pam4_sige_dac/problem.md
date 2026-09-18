# Broadband SiGe PAM4 Driver Layout Task

## Objective

Lay out the upstream inductorless, three-cell current-steering PAM4 driver as
`pam4drv_pam4_lay`. One LSB cell and two parallel MSB cells contain twelve
three-finger `npn13G2` HBTs, twelve physical `rsil` resistors and three physical
MIM degeneration capacitors. Preserve the supplied topology and dimensions.
The task coefficient is 4.

## Inputs and Interface

`materials/circuit.cdl` is the native LVS authority;
`materials/circuit.spice` is its simulator representation;
`materials/testbench.spice` defines the electrical measurements.

Ordered ports: `lsbp lsbn msbp msbn outp outn vcc vcasc vcmb tmsb0 tlsb0 tmsb1 sub`.
The first four ports are differential LSB/MSB inputs, `outp/outn` are differential
outputs, `vcc` is the supply, `vcasc` biases the cascode bases, `vcmb` is the input
termination reference, the three tail ports connect to external current sinks,
and `sub` is the ideal substrate reference. The three testbench VCCS tails are
external bias apparatus, not missing physical transistors.

## Operating Conditions

Use the upstream **layout signoff point**, not its separate static sizing point:
4 V supply, 3.35 V cascode bias, 1.9 V input common mode and 15 mA per cell.
The nominal corners are `hbt_typ`, `res_typ` and `cap_typ` at 27 °C. HBTs have
`Nx=3`. Physical dimensions are fixed by the netlists; the nominal targets are
50 Ω collector loads, 48 Ω input terminations, 3.2 Ω degeneration and 16 fF
bridging capacitance. PDK geometry models determine their actual values.

Both RF ports use 50 Ω per side (100 Ω differential). AC gain is differential
power-wave S21 = `2*Vout/Vsrc`, measured at 1 GHz; bandwidth is checked by the
50 GHz gain relative to 1 GHz. S11 is evaluated at **32 GHz**, and S22 at
**50 GHz**, using the testbench's 20 points/decade sweep and interpolation.
Do not substitute the preceding sweep samples for these endpoints.

The large-signal test drives LSB and MSB in phase at 1 GHz through the same
source impedances, with ±0.8 V per source around 1.9 V. Supplies and bias ramp
from zero over 8 ns; sine excitation starts at 9 ns. The 16–21 ns measurement
window contains five periods. Swing is twice the fundamental phasor amplitude
using the exported transient samples, rather than raw peak-to-peak excursion.

## Physical Requirements

Submit GDS with the exact top-cell name, all thirteen labeled ports, and at most
10 MiB. Native SG13G2 DRC checks main and extra maximal rules without density or
antenna; no marker waivers apply. Native LVS compares devices, dimensions,
connectivity and named ports. Functional width/height must not exceed 160/120 µm.
The published `outline` layer list covers HBT, resistor, MIM, substrate-contact,
seven-metal and via geometry; pin/text and presentation layers are excluded.

Post-layout simulation uses KPEX 0.3.12 nominal 2.5D **coupling capacitance** from
the submitted GDS. Native extracted devices are checked against the candidate's
independent LVS database. MIM devices retain extracted endpoints and `w/l/m`;
no MIM layers are stripped and no source devices are reinserted. The process
reference plane is tied to `sub`. Distributed wire resistance, inductance,
pads/package, statistical yield and process-corner robustness are not claimed
by this upstream CC characterization contract. Finite substrate/tail-generator
circuits are outside the physical core. A PAM4 eye/RLM result is not established
by these tone and small-signal checks.

## Electrical Requirements and Scoring

All measurements and their paired source observations must be finite and usable.
Performance is scored continuously against the same-condition source circuit;
upstream data-sheet targets are not acceptance thresholds. Supply consumption
and output swing must be nonnegative; zero or otherwise unusable ratio baselines
cannot establish a score. Physical checks remain mandatory.

| Metric | Definition | Unit | Quality rule | Functional bounds |
| --- | --- | --- | --- | --- |
| `lsb_gain_db` | LSB S21 at 1 GHz | dB | maximize / db20 | none |
| `msb_gain_db` | MSB S21 at 1 GHz | dB | maximize / db20 | none |
| `dac_weight_db` | MSB minus LSB gain | dB | source target | none |
| `lsb_rel50_db` | LSB S21(50 GHz) minus S21(1 GHz) | dB | maximize / db20 | none |
| `msb_rel50_db` | MSB S21(50 GHz) minus S21(1 GHz) | dB | maximize / db20 | none |
| `s11_32g_db` | MSB input return loss at 32 GHz | dB | minimize / db20 | none |
| `s22_50g_db` | Output return loss at 50 GHz | dB | minimize / db20 | none |
| `power_mw` | Power drawn from the 4 V rail at OP | mW | minimize / ratio | ≥ 0 |
| `swing_vpp` | Differential output fundamental swing | V | maximize / ratio | ≥ 0 |

Independent source simulation uses the same deck, conditions and models.
Response quality uses `db20` for gain,
relative bandwidth and return loss, and a maximizing ratio for swing. Binary
weight uses target normalization to its source value with a `20*log10(2)` dB scale, the ideal binary amplitude-weight interval. Supply quality uses a minimizing
power ratio. Each dimension is the geometric mean of its metrics; `E` is the
geometric mean of response, bias and supply quality. Area quality is
`Q = 10000 µm² / functional_area`; the score is `100*sqrt(E*Q)` and is not capped
at 100. Physical or electrical rejection scores zero; incomplete evaluation
cannot establish success. The area target is a compact sizing allowance,
not the area of a qualified reference.

## Tools and Submission

Solve budget: **4 hours**.

Use the reviewed SG13G2 resources and the runtime task/protocol metadata.
Ngspice must be ≥45 with `ngbehavior=hsa`, compiled R3_CMC support and the
specified HBT/capacitor models. The toolchain provides native KLayout checks,
candidate-derived KPEX capacitance and ngspice feedback. Write
`/workspace/output/final.gds` and explicitly submit it through the runtime
submission interface. Reference and maintainer material is not a solver input.
