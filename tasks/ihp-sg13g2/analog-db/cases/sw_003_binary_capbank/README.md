> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Three-Bit MIM Capacitive Transfer Bank

## Overview

Twelve minimum-size MOS (W/L = 0.15/0.13 um) select the bottom plates of a 1:1:2:4 MIM capacitor bank between vinp and VCM. Eight identical 25.85 by 25.85 um cap_cmim units implement those weights, each nominally about 1.00647 pF. Explicit physical substrate and well taps are included. For code k, the ideal capacitive transfer is (1+k)/8. Qualification covers all eight static codes and bipolar input steps at each fixed code; live code transitions, ADC conversion, charge redistribution after a code change and mismatch linearity are outside scope.

Typical IHP low-voltage MOS, typical resistor and capacitor models at 27 C; VDD = 1.5 V and VSS = 0 V. Each node has the declared 1e12 ohm numerical shunt. Transient integration uses Gear order 2 with a 1 ns output and maximum step. Physical taps have finite source-model resistance; Magic treats well/substrate ties ideally. Distributed silicon substrate resistance, statistical mismatch, PVT, noise and RF/EM are outside scope.

All eight binary codes are separate required conditions. Bit k is driven by 1.5*bk V and its complement by 1.5*(1-bk) V; controls remain static. VCM = 0.75 V. VINP has DC 0.65 V and unit AC amplitude. AC uses 50 points/decade from 1 kHz to 100 MHz; acceptance measurements are at 10 kHz. VINP stays at 0.65 V through 10 us, rises to 0.85 V at 10.002 us, holds through 30 us, returns to 0.65 V at 30.002 us and holds through 50 us. Vout has an external 1e12 ohm return to ground, in addition to the numerical shunt; no ideal external holding capacitor is added. Absolute output DC is not a retained sample requirement: measurements compare increments. The testbench expected-value voltage source is measurement apparatus only.

## Files

| File | Role |
| --- | --- |
| [problem.md](problem.md) | Complete solver contract and scoring |
| [case.toml](case.toml) | Frozen inputs, tool bindings, constraints and evaluation |
| [materials/circuit.cdl](materials/circuit.cdl) | Authoritative physical netlist |
| [materials/circuit.spice](materials/circuit.spice) | Equivalent simulator representation |
| [materials/testbench.spice](materials/testbench.spice) | Shared source/post-layout measurements |
| [reference/sw_003_binary_capbank.gds](reference/sw_003_binary_capbank.gds) | Independent witness, excluded from solver inputs |

## Reference Results

The independently constructed reference passes artifact checks, main/maximal DRC without waivers, strict named-port LVS, hard geometry, candidate RC extraction and all 64 electrical observations. Functional area is 31000.9828 um2 and the reference score is 100/100; this is witness qualification, not a model score. The table reports min–max across all 8 conditions; each observation is checked separately.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `gain_vv` | V/V | 0.1250002–0.9999999 | 0.1238089–0.9887987 |
| `phase_deg` | deg | -0.008812904–0.09038728 | -0.009028963–0.09203339 |
| `input_cap_f` | F | 3.108802e-15–2.015276e-12 | 2.333301e-13–2.144532e-12 |
| `gain_error` | V/V | 1e-07–8e-07 | 0.0011911–0.0112013 |
| `step_gain` | V/V | 0.12499705–0.99997649 | 0.12380144–0.98874124 |
| `step_error` | V/V | 2.9500987e-06–2.3505869e-05 | 0.001198561–0.01125876 |
| `return_error_v` | V | 6.2005303e-07–4.9593158e-06 | 1.5188666e-06–1.2128095e-05 |
| `settling_error_v` | V | 2.784394e-07–2.201358e-06 | 6.818172e-07–5.433537e-06 |

Coefficient 5 reflects multi-bit switched capacitors and interconnect-dependent capacitive division. Absolute AC and step-gain error limits of 0.015 V/V preserve separation of the 0.125 V/V code intervals, with explicit return and settling limits. These are transfer accuracy requirements under driven input and fixed codes, not DAC INL/DNL or floating-node DC accuracy. Fixed functional area target/zero: 33000 / 132000 um2. See the [problem](problem.md) for all limits, measurement windows, scoring boundaries and footprint layers. The MIM bottom-plate/interconnect parasitics belong to candidate extraction, not an ideal-capacitor substitution.

Halving the transient step from 1 ns to 0.5 ns changed step gain by at most 5e-8 V/V, return error by 6.5 nV and settling error by 9 nV. Both steps satisfy the declared limits. AC and step transfer remain distinct observations; the roughly 1.12% full-scale post-layout gain loss includes bottom-plate and routing parasitics.

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
  tasks/ihp-sg13g2/analog-db/cases/sw_003_binary_capbank/case.toml \
  tasks/ihp-sg13g2/analog-db/cases/sw_003_binary_capbank/reference/sw_003_binary_capbank.gds \
  --output build/runs/sw_003_binary_capbank-reference
```

For pre-layout calibration, apply the [source-characterization recipe](../../../../../docs/tools.md#gf180-source-calibration) to this case, replacing its `input:netlist` substitution with `input:simulation` for the separate IHP simulator representation. It retains every condition and measurement while removing scoring and candidate checks. The scored post-layout plan always consumes candidate RC.

## Source and License

Derived from [analog-db `sw_003_binary_capbank` at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/sw_003_binary_capbank), under the retained [collection license](../../LICENSE) and [notices](../../NOTICE); independently authored testbench under MIT.
