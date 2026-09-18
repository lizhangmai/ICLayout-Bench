# Divider-Biased NMOS Source Follower Layout Task

## Objective

A single fixed 50/0.5 um nfet_03v3 (m=1) forms a source follower. Its drain connects to vdd, source to vout, body to vss, and gate to the midpoint of the internal 100 kohm/100 kohm supply divider. Each resistor uses two native ppolyf_u_1k segments, totaling 99995.18 ohm at TT/27 C. There is no control input, external reference, error amplifier or closed-loop regulator. Target top cell: `ldo_006_stub`.

## Inputs and Interface

`materials/circuit.cdl` is the authoritative physical netlist; `materials/circuit.spice` is the same compact-device circuit for simulation. `materials/testbench.spice` supplies the external fixture. Both source and extracted candidate use the exact same deck, bias, loads, excitation, initial-state procedure and measurement windows. Ordered ports: vdd (drain and divider supply), vout (source output), vss (body/divider return).

## Operating Conditions

GF180 TT, 27 C. Supply is independently 1.2 or 1.5 V; output load is independently 100 kohm or 1 Mohm, in parallel with 10 pF. A 1 uA sink turns on at 2 us with a 20 ns edge and stays on throughout the 10 us run. Maximum step is 2 ns. The initial state has zero additional sink current and is computed by DC OP. A separate loaded DC OP with a 1 uA sink is compared with the 8–10 us transient endpoint. Supply power includes the divider, transistor and resistive load.

## Physical Requirements

Use GF180 native KLayout main rule deck and named-interface LVS; Magic RC extraction with its reviewed 10-way grid subdivision. No case-specific waivers. Candidate extraction must preserve every model, multiplicity, size, resistor value, connection and ordered port. The functional outline includes devices, wells, contacts and all routing layers declared in the public task; annotation and pin labels do not add area. Maximum outline: 5000 by 1000 um. Maximum GDS size: 10485760 bytes. Every device and resistor must be physical; no ideal internal macro or auxiliary servo may be added. External sources, probe loads and storage capacitors belong to the testbench.

## Electrical Requirements and Scoring

| Metric | Unit | Definition | Bound | Quality |
| --- | --- | --- | --- | --- |
| `output_v` | V | DC loaded source-follower output | 0 to 1.5 | bias: target, target, scale=0.1 |
| `power_w` | W | DC power including internal 100k/100k divider | 0 to unbounded | supply: ratio, minimize, scale=1e-12 |
| `step_shift_v` | V | Mean output at 8–10 us minus initial output | unbounded to unbounded | response: target, target, scale=0.1 |
| `ripple_v` | V | Peak-to-peak output over final 2 us | 0 to unbounded | diagnostic / functional only |

Only output operating point, finite load-step shift and actual supply loss are scored. Late-window ripple is an unscored diagnostic; sub-nanovolt ripple is below numerical voltage resolution. No regulation accuracy, PSRR, dropout or loop-margin claim is made. The model guide includes 50 um width as a pseudo-device scaling boundary, not a directly measured width sample.

Static output bounds are physical rail-domain checks, nonnegative power/error bounds establish measurement domains, and KCL guards reject inconsistent DC solutions. All required conditions must be valid. No advertised upstream performance is a hard gate. Numerical resolution floors prevent zero-error ratios; target scales are 0.1 V for analog operating points/response, 1 V/V for passive transfer, 0.6 V for inverter threshold and 1 mV/C for temperature slope, as applicable. Timing uses a 1 ps floor, passive settling 1 uV, power 1 pW (1 fW for the subthreshold core); these are normalization units, not acceptance tolerances.

For each metric take the worst same-condition source-paired quality. Target quality is `1/(1+abs(candidate-source)/scale)`; minimizing ratio quality is `(source+scale)/(candidate+scale)`. Geometric means combine metrics within dimensions and applicable dimensions into E. The layout-v2 score is `100*sqrt(E*area_target/functional_area)`, uncapped. Missing/nonfinite/invalid source or candidate measurements and tool failures yield an unknown score; completed physical/functional rejection yields zero. Bounds apply to every observation.

Compact area anchor: 1200 um2 = 50 × 6 um2 pass-device/contact envelope + 4 × 55 × 2 um2 resistor/contact/isolation envelopes + 460 um2 routing/guard-ring allowance. It is a compact engineering estimate independent of witness sparsity. Coefficient 3: local analog bias/transfer and controlled load response. The circuit and these anchors are fixed before participant evaluation.

## Tools and Submission

Solve budget: **6 hours**.

Use the runtime task/protocol and reviewed resource bundle to discover tools and feedback. Submit `/workspace/output/final.gds` explicitly through the protocol; merely writing it is not a submission. The reference and maintainer source records are excluded from solver inputs.
