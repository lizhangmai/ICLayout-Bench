# CMOS Inverter Threshold Core Layout Task

## Objective

The fixed binding is a CMOS inverter: one 1/0.13 um NMOS and one 2.5/0.13 um PMOS, each m=1. Bodies connect to their respective rails through native physical contacts. It provides a threshold decision core; there is no sampling, independent reference, encoding or complete ADC. Target top cell: `adc_001_inv1b`.

## Inputs and Interface

`materials/circuit.cdl` is the authoritative physical netlist; `materials/circuit.spice` is the same compact-device circuit for simulation. `materials/testbench.spice` supplies the external fixture. Both source and extracted candidate use the exact same deck, bias, loads, excitation, initial-state procedure and measurement windows. Ordered ports: vdd (1.2 V rail), vin (gate input), vout (drain output), vss (return).

## Operating Conditions

IHP LV MOS TT, 27 C, VDD=1.2 V. Input driver impedance is 50 ohm; output capacitance is 20 fF. DC input sweeps 0–1.2 V in 1 mV steps. The transient driver starts at 0 V, rises at 10 ns, falls at 20.1 ns, has 100 ps edges and a 20 ns period. The initial DC output is high. The 31 ns run uses a maximum 1 ps step. Power is the net energy from supply and input driver divided by the 10–30 ns window.

## Physical Requirements

Use IHP native KLayout main and maximum rule decks and named-interface LVS; Magic full RC extraction. No case-specific waivers. Candidate extraction must preserve every model, multiplicity, size, resistor value, connection and ordered port. The functional outline includes devices, wells, contacts and all routing layers declared in the public task; annotation and pin labels do not add area. Maximum outline: 5000 by 1000 um. Maximum GDS size: 10485760 bytes. Every device and resistor must be physical; no ideal internal macro or auxiliary servo may be added. External sources, probe loads and storage capacitors belong to the testbench.

## Electrical Requirements and Scoring

| Metric | Unit | Definition | Bound | Quality |
| --- | --- | --- | --- | --- |
| `threshold_v` | V | Unique DC output=0.6 V crossing | unbounded to unbounded | response: target, target, scale=0.6 |
| `delay_s` | s | Worst 50% input to opposite 50% output delay | 0 to unbounded | response: ratio, minimize, scale=1e-12 |
| `transition_s` | s | Worst output 10–90% or 90–10% transition | 0 to unbounded | response: ratio, minimize, scale=1e-12 |
| `power_w` | W | Mean net supply and input-driver power from 10–30 ns | 0 to unbounded | supply: ratio, minimize, scale=1e-12 |
| `swing_v` | V | DC high minus low output; meaningful logic transition | 0.6 to unbounded | diagnostic / functional only |

The DC threshold is the unique output=0.6 V crossing, not a scan endpoint. Delay is the worse input 50% to opposite output 50% delay. Transition is the worse output 10–90% rise or 90–10% fall. Guards reject missing or multiple DC/transition crossings; independent audits require the intended 10–15 ns and 20–25 ns windows and correct ordering. DC high/low output uses actual endpoint samples, with a minimum 0.6 V swing establishing a meaningful logic transition. This is nominal loaded characterization, not Liberty/PVT or ADC accuracy.

Static output bounds are physical rail-domain checks, nonnegative power/error bounds establish measurement domains, and KCL guards reject inconsistent DC solutions. All required conditions must be valid. No advertised upstream performance is a hard gate. Numerical resolution floors prevent zero-error ratios; target scales are 0.1 V for analog operating points/response, 1 V/V for passive transfer, 0.6 V for inverter threshold and 1 mV/C for temperature slope, as applicable. Timing uses a 1 ps floor, passive settling 1 uV, power 1 pW (1 fW for the subthreshold core); these are normalization units, not acceptance tolerances.

For each metric take the worst same-condition source-paired quality. Target quality is `1/(1+abs(candidate-source)/scale)`; minimizing ratio quality is `(source+scale)/(candidate+scale)`. Geometric means combine metrics within dimensions and applicable dimensions into E. The layout-v2 score is `100*sqrt(E*area_target/functional_area)`, uncapped. Missing/nonfinite/invalid source or candidate measurements and tool failures yield an unknown score; completed physical/functional rejection yields zero. Bounds apply to every observation.

Compact area anchor: 120 um2 = 20 um2 NMOS contact envelope + 30 um2 PMOS/well envelope + 20 um2 body-contact/isolation allowance + 50 um2 routing. These envelopes follow the fixed widths and contact/isolation needs, not the witness bounding box. Coefficient 1: a single logic stage with loaded transitions and connectivity. The circuit and these anchors are fixed before participant evaluation.

## Tools and Submission

Solve budget: **6 hours**.

Use the runtime task/protocol and reviewed resource bundle to discover tools and feedback. Submit `/workspace/output/final.gds` explicitly through the protocol; merely writing it is not a submission. The reference and maintainer source records are excluded from solver inputs.
