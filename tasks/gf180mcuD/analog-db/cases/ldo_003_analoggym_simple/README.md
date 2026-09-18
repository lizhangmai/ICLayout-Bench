# Simple Unity-Feedback LDO

## Overview

A five-transistor NMOS-input error amplifier drives the PMOS pass device, with direct output feedback, the complete 3 kohm/1 pF series compensation and physical 100 kohm bleed. The pass transistor expands to 360 parallel units; the complete core has 365 MOS. GF180 6 V NMOS lengths obey the native 0.70 um minimum and PMOS lengths the 0.55 um minimum. The external bias remains 1.2 V and reference 1.8 V from the fixed binding.

Coefficient 7 reflects compensated regulation, line/load recovery and coordinated startup. No dropout number, loop margin, unlimited load range, PVT or product specification is claimed. Regulation slopes describe the declared finite intervals. Final error/ripple describe 90–100 us, not a proof of asymptotic settling. Input power includes the bleed, delivered load and bias/reference source contributions. See the [solver contract](problem.md) for the complete operating boundary and metric definitions.

## Files

- [Schematic](materials/schematic.svg): digest-bound main-sheet overview; hierarchical device banks remain expandable in the editable source project. This presentation asset is excluded from solver inputs.

- [case.toml](case.toml): executable task, frozen inputs, toolchain, scoring and maintainer asset declarations.
- [Physical netlist](materials/circuit.cdl) and [simulator netlist](materials/circuit.spice): the same complete physical core.
- [Main fixture](materials/testbench.spice): independent paired source/candidate measurements; other decks are declared in the configuration.
- [Reference GDS](reference/ldo_003_analoggym_simple.gds): independently authored physical witness, excluded from solver inputs.

## Reference Results

Qualified for the declared nominal task. Native artifact, DRC, named-interface LVS, footprint and candidate GDS-derived distributed RC checks pass, with same-condition independently rerun source baselines. Compact-device graph audits match source, topology-only extraction and full RC, including parameters, physical passive units and ordered ports. Every scored measurement was independently recomputed from raw waveforms.

Reference layout-v2 score: **26.67746799**. Functional area: **1.77037e+06 um²**. The [problem](problem.md) defines the independent area estimate (169100 um²) and coefficient (7). Qualification means a valid measurement/scoring chain; it does not certify upstream product specifications.

Ranges below are minima/maxima across declared conditions, not paired ratios.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `output_v` | V | 1.7969763 / 1.8101861 | 1.7391239 / 1.7976446 |
| `power_w` | W | 0.0022213893 / 0.010730555 | 0.0022146693 / 0.010722143 |
| `regulation_error_v` | V | 0.0030236799 / 0.010186057 | 0.0023553566 / 0.060876065 |
| `psrr_db` | dB | 46.16796 / 46.85305 | 35.13099 / 47.78565 |
| `quiet_ripple_v` | V | 1.247225e-12 / 1.592282e-12 | 4.308776e-11 / 4.937362e-11 |
| `recovery_ripple_v` | V | 1.673328e-12 / 1.841638e-12 | 2.559353e-11 / 6.445777e-11 |
| `excursion_v` | V | 1.773914e-12 / 0.2750852 | 4.049323e-10 / 0.6150162 |
| `late_error_v` | V | 0.00302368 / 0.01018606 | 0.002355357 / 0.06087606 |
| `kcl_a` | A | 4.8789098e-16 / 9.3675068e-16 | 1.0906985e-11 / 1.0969618e-11 |
| `startup_error_v` | V | 0.01014803 / 0.01014803 | 0.002332139 / 0.002332139 |
| `startup_ripple_v` | V | 1.47149e-12 / 1.47149e-12 | 1.572342e-11 / 1.572342e-11 |
| `line_reg_v_per_v` | V/V | 0.0033453704 / 0.0033453704 | 0.0030986781 / 0.0030986781 |
| `load_reg_ohm` | ohm | 3.4800727 / 3.4800727 | 16.047142 / 16.047142 |

At 2 V and 1 mA, source/candidate output is approximately 1.81019/1.79764 V; at 2.1 V and 5 mA it is 1.79698/1.73912 V. Candidate peak line/load excursions are approximately 0.325575/0.615016 V. The quiet and final recovery windows are stable within the reported finite observation. The independent consistency audit compares quiet/recovery against OP and disturbed plateaus against separate DC sweeps within 10 uV. Coordinated zero-state startup with a resistive load reaches a candidate late mean error of 2.332 mV. No result is generalized to arbitrary supply sequencing or constant-current loading at zero supply.

The 100 kohm bleed is inside the physical DUT and adds to the external load; its current is included once in input power. Vref and Vb remain external sources; Vlp is a zero-volt feedback test marker replaced by a physical wire. All 360 pass-device units and Rz/Cc remain.

The fixed corpus mapping and retained source-rights records distinguish MacAnalog normalized material, AnalogGym BSD-3-Clause source/testbench evidence and the Apache-2.0 sky130_ldo_rl companion. The companion is provenance evidence, not an alternate implementation or sizing source. Collection notices preserve these distinct terms.

Halving transient time steps, doubling AC frequency density and tightening solver tolerances tenfold for both source and candidate changes the independently recomputed score by 5.65989e-06 points. The area remains fixed during this check. No rshunt or added DUT servo is used.

## Reproduce

From the Bench repository root, reuse a compatible ngspice 45 / Magic 8.3.678 / KLayout 0.30.11 tools image or follow the [tools guide](../../../../../docs/tools.md#image-development). These commands create disposable prepared bundles and evidence under the specified fresh directories:

```bash
uv run --locked python -m benchmarking.engine.preview prepare \
  --case ldo_003_analoggym_simple --image iclayout-bench-tools:ngspice45 \
  --output build/runs/ldo_003_analoggym_simple/prepared
uv run --locked python -m benchmarking.engine.preview run \
  --prepared build/runs/ldo_003_analoggym_simple/prepared \
  --output build/runs/ldo_003_analoggym_simple/reference
```

Normal evaluation consumes only this static delivery and prepared PDK resources; it requires neither Designs nor Private source. Development recipes and independent raw-waveform, binding and numerical audits belong to the separate ICLayout-Designs repository. Prepared configuration, resource digests, candidate identity, raw waveforms and measurements are recorded in each generated report.

## Source and License

Derived from [MacAnalog/spicexplorer-release, `ldo_003_analoggym_simple`](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/ldo_003_analoggym_simple) at commit `263d0322f8900dc331536fbbe6c0e804514fc454`; retain the collection [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE). Required Notice: Copyright 2026 Danial Noori Zadeh. Circuit derivatives and witnesses retain applicable upstream terms; independently authored measurement decks are MIT.
