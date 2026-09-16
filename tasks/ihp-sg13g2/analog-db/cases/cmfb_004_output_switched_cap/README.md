> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# MIM Switched-Capacitor Common-Mode Sampler

## Overview

Sixteen minimum-size MOS (W/L = 0.15/0.13 um) implement eight transmission paths. Four internal MIM capacitors retain the original connections: two separate vbias-to-vcm capacitors and two floating control-to-sense capacitors. Each is a 25.85 by 25.85 um cap_cmim, nominally about 1.00647 pF. Explicit physical substrate and well taps are included. The output samples common-mode displacement; this is a switched-capacitor sensing network with driven inputs, not a complete closed-loop amplifier or a loop-stability qualification.

Typical IHP low-voltage MOS, typical resistor and capacitor models at 27 C; VDD = 1.5 V and VSS = 0 V. Each node has the declared 1e12 ohm numerical shunt. Transient integration uses Gear order 2 with a 1 ns output and maximum step. Physical taps have finite source-model resistance; Magic treats well/substrate ties ideally. Distributed silicon substrate resistance, statistical mismatch, PVT, noise and RF/EM are outside scope.

Vcm = 0.75 V; Vbias = 0.6 V. Each condition starts with input common mode 0.75 V. It changes linearly over 40–40.1 us to common_v, then holds through 100 us. Inputs are common mode +/- diff_v. The five (common_v, diff_v) pairs in volts are (0.65,0), (0.65,0.1), (0.75,0.1), (0.85,0), (0.85,0.1). Phi starts high, falls after 1 us, and alternates with its complementary independent clock; rise/fall times are 2 ns, low width 5 us and period 10 us. Phi high precharges the floating capacitors; phi low couples them to the sensed inputs and output. Finite complementary slopes permit overlap. An external 1 pF loads vcmfb; stop time is 100 us. The target after repeated transfers is 0.6 V + common_v - 0.75 V.

## Files

| File | Role |
| --- | --- |
| [problem.md](problem.md) | Complete solver contract and scoring |
| [case.toml](case.toml) | Frozen inputs, tool bindings, constraints and evaluation |
| [materials/circuit.cdl](materials/circuit.cdl) | Authoritative physical netlist |
| [materials/circuit.spice](materials/circuit.spice) | Equivalent simulator representation |
| [materials/testbench.spice](materials/testbench.spice) | Shared source/post-layout measurements |
| [reference/cmfb_004_output_switched_cap.gds](reference/cmfb_004_output_switched_cap.gds) | Independent witness, excluded from solver inputs |

## Reference Results

The independently constructed reference passes artifact checks, main/maximal DRC without waivers, strict named-port LVS, hard geometry, candidate RC extraction and all 20 electrical observations. Functional area is 20589.5824 um2 and the reference score is 100/100; this is witness qualification, not a model score. The table reports min–max across all 5 conditions; each observation is checked separately.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `output_v` | V | 0.5001887–0.6998088 | 0.5025711–0.697334 |
| `sample_error_v` | V | 2.520536e-06–0.0001925041 | 4.491021e-05–0.002666033 |
| `hold_drift_v` | V | 9.400405e-05–0.0001883919 | 0.0002111748–0.0002683448 |
| `clock_power_w` | W | 3.654853e-10–3.768236e-10 | 2.173587e-08–2.207999e-08 |

Coefficient 5 reflects periodic charge transfer, independent clock routing and interacting floating capacitors. The 5 mV sampling limit resolves a 100 mV common-mode disturbance, and the 0.5 mV hold limit constrains clock feedthrough during disconnection. Clock-power acceptance is 40 nW. It measures the two clock drivers, not total energy supplied by all reference/input sources. Fixed functional area target/zero: 22000 / 88000 um2. See the [problem](problem.md) for all limits, measurement windows, scoring boundaries and footprint layers. The MIM bottom-plate/interconnect parasitics belong to candidate extraction, not an ideal-capacitor substitution.

Halving the transient step from 1 ns to 0.5 ns changed sampled output by at most 1.1 uV, hold drift by 1.93 uV and supplied clock power by 2.44%. Both steps satisfy the declared limits. Clock-energy numerical precision is limited by this comparison; it is not a sub-percent power claim.

## Reproduce

Run from the repository root with the [shared IHP tools and resource setup](../../../../../docs/tools.md#manual-tools). Reuse verified bundles. These commands create the reader's own reports under a fresh `build/runs/` directory; generated evidence is not shipped with this case.

The embedded bindings use these destinations. If they do not already exist, prepare them once from the pinned PDK (preparation refuses an existing destination):

```bash
python -m layout_eval.prepare_support third_party/IHP-Open-PDK tasks/ihp-sg13g2/pdk.toml#klayout build/support/input-pair-klayout
python -m layout_eval.prepare_support third_party/IHP-Open-PDK tasks/ihp-sg13g2/pdk.toml#magic build/support/input-pair-magic
python -m layout_eval.prepare_support third_party/IHP-Open-PDK tasks/ihp-sg13g2/pdk.toml#analog-models build/support/input-pair-models
```

```bash
python -m layout_eval.cli evaluate \
  tasks/ihp-sg13g2/analog-db/cases/cmfb_004_output_switched_cap/case.toml \
  tasks/ihp-sg13g2/analog-db/cases/cmfb_004_output_switched_cap/reference/cmfb_004_output_switched_cap.gds \
  --output build/runs/cmfb_004_output_switched_cap-reference
```

For pre-layout calibration, apply the [source-characterization recipe](../../../../../docs/tools.md#gf180-source-calibration) to this case, replacing its `input:netlist` substitution with `input:simulation` for the separate IHP simulator representation. It retains every condition and measurement while removing scoring and candidate checks. The scored post-layout plan always consumes candidate RC.

## Source and License

Derived from [analog-db `cmfb_004_output_switched_cap` at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/cmfb_004_output_switched_cap), under the retained [collection license](../../LICENSE) and [notices](../../NOTICE); independently authored testbench under MIT.
