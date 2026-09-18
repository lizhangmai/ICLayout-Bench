# PMOS-Input Common-Mode Detector and Controller

## Overview

Seven MOS implement a PMOS-input five-transistor OTA plus the PMOS/NMOS diode bias branch. Two 1 Mohm sensing arms each use four series physical high-poly units. The pinned IHP widths/lengths are quantized to the 10 nm drawing grid, including the 0.29 um bias NMOS. Bodies and all sensing/bias devices are retained.

Coefficient 4 covers a compact gain/bias/passive network. Positive common-mode and negative reference DC slopes are functional sign constraints, not gain targets. Reported response/ripple windows do not certify a closed-loop CM regulator or upstream optimization claims. See the [solver contract](problem.md) for the complete operating boundary and metric definitions.

## Files

- [Schematic](materials/schematic.svg): digest-bound main-sheet overview; hierarchical device banks remain expandable in the editable source project. This presentation asset is excluded from solver inputs.

- [case.toml](case.toml): executable task, frozen inputs, toolchain, scoring and maintainer asset declarations.
- [Physical netlist](materials/circuit.cdl) and [simulator netlist](materials/circuit.spice): the same complete physical core.
- [Main fixture](materials/testbench.spice): independent paired source/candidate measurements; other decks are declared in the configuration.
- [Reference GDS](reference/cmfb_002_5t_pmos_input.gds): independently authored physical witness, excluded from solver inputs.

## Reference Results

Qualified for the declared nominal task. Native artifact, DRC, named-interface LVS, footprint and candidate GDS-derived distributed RC checks pass, with same-condition independently rerun source baselines. Compact-device graph audits match source, topology-only extraction and full RC, including parameters, physical passive units and ordered ports. Every scored measurement was independently recomputed from raw waveforms.

Reference layout-v2 score: **90.53862314**. Functional area: **12652.3 um²**. The [problem](problem.md) defines the independent area estimate (10500 um²) and coefficient (4). Qualification means a valid measurement/scoring chain; it does not certify upstream product specifications.

Ranges below are minima/maxima across declared conditions, not paired ratios.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `output_v` | V | 0.3463125 / 0.34830127 | 0.34189237 / 0.34376914 |
| `power_w` | W | 4.2903498e-05 / 4.3991398e-05 | 4.2476092e-05 / 4.3696561e-05 |
| `signed_gain` | 1 | -17.5028 / 17.49363 | -17.45015 / 17.44112 |
| `gain_1khz` | 1 | 9.629784e-25 / 17.50274 | 2.521398e-05 / 17.4501 |
| `gain_100khz` | 1 | 2.313066e-24 / 16.99678 | 0.0009077778 / 16.92441 |
| `step_response_v` | V | -0.0174032 / 0.0175966 | -0.01735 / 0.0175444 |
| `ripple_v` | V | 7.150525e-11 / 1.874949e-10 | 1.30417e-10 / 2.335353e-10 |
| `dc_cm_slope` | 1 | 16.482918 / 17.493008 | 16.443225 / 17.440382 |
| `dc_ref_slope` | 1 | -17.502044 / -16.462009 | -17.449396 / -16.423243 |

Positive DC/AC common-mode transfer and negative reference transfer are verified separately at both 0.5 and 0.7 V operating points, with small signed DC sweeps as well as transient steps. At 0.5 V the source natural output is approximately 0.346313 V and rail power 43.9914 uW. The double-diode branch carries approximately 21.5753 uA and the PMOS tail 7.75228 uA. No upstream optimization claim is assumed. This is a standalone detector/controller with a declared output load, not a complete regulated amplifier.

The native narrow-device PCell contact geometry is used for the 0.29 um bias NMOS; its width is not enlarged to hide a routing problem. Idealizing only the source body-tap boundary changes DC output by less than 0.53 nV and AC gain by less than 1.27e-6 V/V. The source retains its native finite tap model; extracted ideal taps and the measured sensitivity are disclosed.

Halving transient time steps, doubling AC frequency density and tightening solver tolerances tenfold for both source and candidate changes the independently recomputed score by 0.0243121 points. The area remains fixed during this check. No rshunt or added DUT servo is used.

The declared 0–1.5 V signal/control envelope uses the SG13G2 LV nominal supply (see the [IHP process description](https://www.ihp-microelectronics.com/fileadmin/images/mediathek/annual_reports/annualreport_ihp_2024.pdf)). This is a nominal simulation boundary, not an absolute-maximum or reliability qualification.

## Reproduce

From the Bench repository root, reuse a compatible ngspice 45 / Magic 8.3.678 / KLayout 0.30.11 tools image or follow the [tools guide](../../../../../docs/tools.md#image-development). These commands create disposable prepared bundles and evidence under the specified fresh directories:

```bash
uv run --locked python -m benchmarking.engine.preview prepare \
  --case cmfb_002_5t_pmos_input --image iclayout-bench-tools:ngspice45 \
  --output build/runs/cmfb_002_5t_pmos_input/prepared
uv run --locked python -m benchmarking.engine.preview run \
  --prepared build/runs/cmfb_002_5t_pmos_input/prepared \
  --output build/runs/cmfb_002_5t_pmos_input/reference
```

Normal evaluation consumes only this static delivery and prepared PDK resources; it requires neither Designs nor Private source. Development recipes and independent raw-waveform, binding and numerical audits belong to the separate ICLayout-Designs repository. Prepared configuration, resource digests, candidate identity, raw waveforms and measurements are recorded in each generated report.

## Source and License

Derived from [MacAnalog/spicexplorer-release, `cmfb_002_5t_pmos_input`](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/cmfb_002_5t_pmos_input) at commit `263d0322f8900dc331536fbbe6c0e804514fc454`; retain the collection [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE). Required Notice: Copyright 2026 Danial Noori Zadeh. Circuit derivatives and witnesses retain applicable upstream terms; independently authored measurement decks are MIT.
