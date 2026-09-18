# Two-NMOS Temperature-Response Core Layout Task

## Objective

The fixed GF180 binding contains eight parallel 8/0.28 um upper NMOS with gates tied to their sources, and eight parallel 4/1 um diode-connected lower NMOS. Both groups have grounded bodies. This is a two-group temperature-response core; neither its PTAT name nor a successful simulator exit establishes a useful slope or a converged extracted operating point. Target top cell: `tsn_001_ptat_2t`.

## Inputs and Interface

`materials/circuit.cdl` is the authoritative physical netlist; `materials/circuit.spice` is the same compact-device circuit for simulation. `materials/testbench.spice` supplies the external fixture. `materials/temperature.spice` supplies the bidirectional temperature sweep. Both source and extracted candidate use the exact same deck, bias, loads, excitation, initial-state procedure and measurement windows. Ordered ports: vdd (supply), vout (sense voltage), vss (both bodies and return).

## Operating Conditions

GF180 nfet_03v3 TT, fixed 1.2 V supply, 1 Tohm probe resistance and 1 pF to ground. No external current bias changes with temperature. Independent operating points cover -20 through 120 C in 10 C steps; ascending and descending sweeps use 5 C steps. The fixed 50 mV nodeset is a Newton initial guess, not a voltage source or a per-temperature bias adjustment. Sparse 1.3, pivtol=1e-30 S, pivrel=0.001, reltol=1e-7, abstol=1e-18 A, vntol=1e-10 V and gmin=1e-18 S are explicit for both circuits; no rshunt is used.

## Physical Requirements

Use GF180 native KLayout main rule deck and named-interface LVS; Magic RC extraction with its reviewed 10-way grid subdivision. No case-specific waivers. Candidate extraction must preserve every model, multiplicity, size, resistor value, connection and ordered port. The functional outline includes devices, wells, contacts and all routing layers declared in the public task; annotation and pin labels do not add area. Maximum outline: 5000 by 1000 um. Maximum GDS size: 10485760 bytes. Every device and resistor must be physical; no ideal internal macro or auxiliary servo may be added. External sources, probe loads and storage capacitors belong to the testbench.

## Electrical Requirements and Scoring

| Metric | Unit | Definition | Bound | Quality |
| --- | --- | --- | --- | --- |
| `output_v` | V | Independent DC temperature-response output | 0 to 1.2 | bias: target, target, scale=0.1 |
| `power_w` | W | DC supply power at fixed 1.2 V | 0 to unbounded | supply: ratio, minimize, scale=1e-15 |
| `slope_v_c` | V/C | Endpoint temperature slope over -20 to 120 C | unbounded to unbounded | response: target, target, scale=0.001 |
| `curvature_v` | V | Maximum deviation from endpoint secant over -20 to 120 C | 0 to unbounded | response: ratio, minimize, scale=1e-06 |

The simulator uses an explicit branch-current formulation for constant parasitic resistors: a zero-volt current sensor and a current-controlled voltage source impose V=R*I exactly. Every resistance, terminal and extracted capacitance is retained. This avoids loss of tiny node conductances when added to the much larger metal conductance in conventional nodal stamping. The original extraction and the effective simulation netlist are both retained as evidence. Source and candidate use the same backend setting. This deterministic formulation does not model resistor thermal noise; noise is outside this task's scope. KCL and measurement-validity checks remain mandatory. No self-startup, precision temperature sensing or linear PTAT behavior is assumed.

Static output bounds are physical rail-domain checks, nonnegative power/error bounds establish measurement domains, and KCL guards reject inconsistent DC solutions. All required conditions must be valid. No advertised upstream performance is a hard gate. Numerical resolution floors prevent zero-error ratios; target scales are 0.1 V for analog operating points/response, 1 V/V for passive transfer, 0.6 V for inverter threshold and 1 mV/C for temperature slope, as applicable. Timing uses a 1 ps floor, passive settling 1 uV, power 1 pW (1 fW for the subthreshold core); these are normalization units, not acceptance tolerances.

For each metric take the worst same-condition source-paired quality. Target quality is `1/(1+abs(candidate-source)/scale)`; minimizing ratio quality is `(source+scale)/(candidate+scale)`. Geometric means combine metrics within dimensions and applicable dimensions into E. The layout-v2 score is `100*sqrt(E*area_target/functional_area)`, uncapped. Missing/nonfinite/invalid source or candidate measurements and tool failures yield an unknown score; completed physical/functional rejection yields zero. Bounds apply to every observation.

Compact area anchor: 1600 um2 = 8 × 10 × 10 um2 upper-device/contact envelopes + 8 × 6 × 8 um2 lower-device/contact envelopes + 416 um2 routing/body-contact allowance, independent of witness area. Coefficient 3: local analog temperature-dependent bias and transfer. The circuit and these anchors are fixed before participant evaluation.

## Tools and Submission

Solve budget: **6 hours**.

Use the runtime task/protocol and reviewed resource bundle to discover tools and feedback. Submit `/workspace/output/final.gds` explicitly through the protocol; merely writing it is not a submission. The reference and maintainer source records are excluded from solver inputs.
