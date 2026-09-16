> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Externally Biased 1.8 V PMOS Regulator Core

## Overview

This maintained GF180MCU D regulator core contains a four-transistor error
amplifier, a PMOS pass device of 100 parallel 10/0.3 um units and two physical
100-square high-resistance poly feedback resistors. It exposes five ports:
`vdd vout vref ibias vss`. The upstream MOS sizes and feedback ratio are retained;
the ideal reference and tail sink become external testbench sources, the ideal
divider becomes process resistors, and the zero-volt loop probe becomes a wire.
The reference layout is independently constructed.

The maintained operating point uses an external 0.9 V reference for approximately
1.8 V output, rather than the upstream 0.65 V reference. This gives positive
error-amplifier tail headroom with the retained 200 uA sink; tail voltage is an
explicit requirement. Qualification covers TT, 27 C, three supplies (2.2, 2.7,
3.3 V), three loads (0.1, 1, 5 mA), an ideal external 1 uF output capacitor,
load-step recovery, supply rejection, output impedance peaking and dropout.
It does not qualify a self-biased three-port LDO, startup, full loop phase margin,
PVT, mismatch, noise, EM, thermal behavior or fabrication signoff.

## Files

| File | Role |
| --- | --- |
| [problem.md](problem.md) | Complete solver-facing contract and scoring |
| [case.toml](case.toml) | Inputs, physical checks, RC extraction and 13 simulation jobs |
| [materials/circuit.spice](materials/circuit.spice) | Authoritative physical circuit and source-calibration DUT |
| [materials/testbench.spice](materials/testbench.spice) | DC, supply-rejection and output-impedance analyses |
| [materials/transient.spice](materials/transient.spice) | Distinct load-step transient analysis |
| [materials/dropout.spice](materials/dropout.spice) | Distinct low-supply DC sweep and crossing measurement |
| [reference/ldo_004_basic_pmos.gds](reference/ldo_004_basic_pmos.gds) | Ready-to-use physical witness, excluded from solver inputs |

## Reference Results

The reference passes artifact, GF180 variant-D DRC including antenna checks
without waivers, strict named-port LVS, geometry, distributed RC extraction
and all 67 required electrical observations. Its functional bounding-box area
is 78921.752 um2. The extracted circuit contains 104 MOS devices and the two
physical resistor devices, with candidate-derived wiring RC.

The first six rows below are ranges across all nine supply/load combinations.
Transient rows are ranges across the three supplies for the same 0.1 to 5 to
0.1 mA load sequence. Dropout uses the separate 5 mA sweep and the 1.75 V
output crossing defined in the problem. Both columns use the published decks.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| Output voltage | V | 1.799798 to 1.806099 | 1.800711 to 1.806237 |
| Tail voltage | V | 0.086371 to 0.092771 | 0.084234 to 0.090594 |
| Quiescent current | uA | 208.875 to 209.088 | 208.876 to 209.081 |
| Input power, including load | mW | 0.679592 to 17.189540 | 0.679584 to 17.189510 |
| Supply rejection at 1 kHz | dB | 61.37198 to 104.8581 | 53.56660 to 100.5256 |
| Output impedance peaking | dB | 0 | 0 to 4.07205 |
| Peak absolute output error, 0.9 to 3 ms | mV | 5.909084 to 6.098814 | 6.042273 to 6.237447 |
| High-load settled error, 1.2 to 1.9 ms | mV | 0.073800 to 0.292420 | 0.711200 to 1.356709 |
| Low-load settled error, 2.2 to 3 ms | mV | 5.909084 to 6.098814 | 6.042273 to 6.237447 |
| Transient minimum tail voltage | V | 0.086371 to 0.091123 | 0.084181 to 0.088947 |
| Dropout at 5 mA | mV | 49.365 | 135.254 |

The acceptance bands specify a 1.8 V output within 20 mV, at most 250 uA core
quiescent current, 18 mW input-power budget, at least 40 dB rejection at 1 kHz,
at most 6 dB impedance peaking, and at most 200 mV dropout. The 25 mV load-step
error and 10 mV settled bands require recovery within 200 us. Tail limits check
positive bias headroom rather than accepting regulation with an unphysical
negative tail voltage. These are maintained design targets calibrated against
the measurements above, not imported upstream datasheet claims. See the
problem for all acceptance and zero-score boundaries.

The coefficient is 7 for closed-loop regulation combining amplifier, pass-array
and passive feedback behavior over multiple regimes. The absolute area target
is an 800 by 100 um routing budget (80000 um2), feasible for the independently
constructed one-row pass array and long poly resistors. Area utility reaches
zero at four times that budget (320000 um2). Neither anchor changes with a
submitted candidate or reference-area ratio; this witness is not an area optimum.

The RC model retains distributed metal resistance and coupling capacitance;
it does not model a distributed silicon substrate. The dropout increase and
impedance peaking show sensitivity to the physical implementation. The
load-step test starts from an operating point and is not a startup test.
Closed-loop impedance peaking and recovery do not establish full loop phase
margin. Saved node/current waveforms permit independent reconstruction of every
reported electrical observation with the definitions in the problem.

## Reproduce

From the repository root, prepare the image and three resource bundles using
the shared [GF180 instructions](../../../../../docs/tools.md#gf180), then run:

```bash
python -m layout_eval.cli evaluate \
  tasks/gf180mcuD/analog-db/cases/ldo_004_basic_pmos/case.toml \
  tasks/gf180mcuD/analog-db/cases/ldo_004_basic_pmos/reference/ldo_004_basic_pmos.gds \
  --output build/runs/analog-db-ldo-reference
```

This creates the reader's identity-bound report and saved waveforms under
`build/runs/analog-db-ldo-reference/`. Use a fresh output directory for each run.
For the Pre-layout column, run the shared
[source-calibration recipe](../../../../../docs/tools.md#gf180-source-calibration)
with this case path and `build/runs/analog-db-ldo-source` as the output argument.
It retains all 13 simulation jobs and replaces only the extracted DUT input
with the published physical source netlist; it is unscored characterization.

The catalog-driven regression prepares isolated inputs/resources and verifies
both the published witness and rejection of an empty layout:

```bash
uv run --locked --group eda pytest tests/integration/test_public_references.py \
  -k ldo_004_basic_pmos
```

Keep collection LICENSE and NOTICE with redistributed materials. Prepared solve
and run directories are generated local outputs, not redistribution packages.

## Source and License

Derived from [MacAnalog analog-db ldo_004_basic_pmos](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/ldo_004_basic_pmos), under the retained [collection license](../../LICENSE) and [notices](../../NOTICE).
