# Externally Biased TI-Architecture Error Amplifier

## Overview

All twelve MOS remain, including the externally driven NMOS reference diode, four sinks, NMOS differential pair, level-shift branch and PMOS output stage. RND connects na to nd; all 500 kohm remains. Rz/Cc remain in series between nb and vout. No servo is inside the DUT. Four parallel native resistors implement 470 ohm; 32 parallel MIM units implement 25 pF. Native 6 V PMOS lengths become 0.55 um; other dimensions and multiplicities retain the fixed GF180 binding.

Coefficient 6 reflects the complete two-stage compensated feedback circuit. It does not claim verified open-loop gain, phase margin, noise, PVT or settling time. Late variation is a finite-window observation. The bias sink ratios are geometric ratios, not promises of saturated current mirrors. See the [solver contract](problem.md) for the complete operating boundary and metric definitions.

## Files

- [Schematic](materials/schematic.svg): digest-bound main-sheet overview; hierarchical device banks remain expandable in the editable source project. This presentation asset is excluded from solver inputs.

- [case.toml](case.toml): executable task, frozen inputs, toolchain, scoring and maintainer asset declarations.
- [Physical netlist](materials/circuit.cdl) and [simulator netlist](materials/circuit.spice): the same complete physical core.
- [Main fixture](materials/testbench.spice): independent paired source/candidate measurements; other decks are declared in the configuration.
- [Reference GDS](reference/amp_019_ti_ldo_error.gds): independently authored physical witness, excluded from solver inputs.

## Reference Results

Qualified for the declared nominal task. Native artifact, DRC, named-interface LVS, footprint and candidate GDS-derived distributed RC checks pass, with same-condition independently rerun source baselines. Compact-device graph audits match source, topology-only extraction and full RC, including parameters, physical passive units and ordered ports. Every scored measurement was independently recomputed from raw waveforms.

Reference layout-v2 score: **46.12650084**. Functional area: **278178 um²**. The [problem](problem.md) defines the independent area estimate (63700 um²) and coefficient (6). Qualification means a valid measurement/scoring chain; it does not certify upstream product specifications.

Ranges below are minima/maxima across declared conditions, not paired ratios.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `output_v` | V | 1.4609664 / 1.8663081 | 1.5491155 / 1.8651008 |
| `power_w` | W | 0.0078226751 / 0.0086028544 | 0.0058710518 / 0.006585244 |
| `gain_1hz` | 1 | 1.004626 / 1.018821 | 0.4059027 / 0.9484089 |
| `gain_1mhz` | 1 | 0.9971075 / 1.013682 | 0.3297627 / 0.9308832 |
| `tracking_error_v` | V | 0.06099132 / 0.06640274 | 0.06484943 / 0.1462338 |
| `ripple_v` | V | 2.375877e-14 / 2.797762e-14 | 2.030598e-12 / 7.846168e-12 |
| `step_response_v` | V | 0.01005 / 0.010189 | 0.004237 / 0.009497 |
| `kcl_a` | A | 8.6302493e-17 / 1.1015494e-16 | 1.3006892e-13 / 1.3651818e-13 |

At 1.6 V input, the source output is 1.66295 V. The tail, internal ne sink and output sink carry approximately 489.020, 40.640 and 969.414 uA with a 1 mA external reference. Geometric mirror ratios do not imply saturation: the tail is in its linear region, nlev is approximately 6.54 nV, and M4 is effectively off. The retained bias probe checks nb/nd/ne/nlev KCL including the input NMOS impact-ionization current (1.379 nA at nb). RND and the full series compensation remain physical. These are measured properties of the fixed binding, not corrected by numerical leakage.

The candidate's reduced follower gain is real interconnect degradation. A diagnostic removing only wire resistance restores the source operating point and approximately 1.01412 V/V low-frequency follower gain at 1.6 V. The qualified score uses the complete RC extraction; the diagnostic is not a replacement candidate. Vinp is noninverting under this fixture, and feedback connects vout to vinn.

The TI label identifies the architectural inspiration. The retained MacAnalog first-party reference schematic and its README establish the corpus attribution; they are historical evidence, not sizing authority or a claim that TI licensed a product implementation. The actual fixed GF180 binding and MacAnalog distribution terms govern the delivered derivative.

Halving transient time steps, doubling AC frequency density and tightening solver tolerances tenfold for both source and candidate changes the independently recomputed score by 1.72108e-09 points. The area remains fixed during this check. No rshunt or added DUT servo is used.

## Reproduce

From the Bench repository root, reuse a compatible ngspice 45 / Magic 8.3.678 / KLayout 0.30.11 tools image or follow the [tools guide](../../../../../docs/tools.md#image-development). These commands create disposable prepared bundles and evidence under the specified fresh directories:

```bash
uv run --locked python -m benchmarking.engine.preview prepare \
  --case amp_019_ti_ldo_error --image iclayout-bench-tools:ngspice45 \
  --output build/runs/amp_019_ti_ldo_error/prepared
uv run --locked python -m benchmarking.engine.preview run \
  --prepared build/runs/amp_019_ti_ldo_error/prepared \
  --output build/runs/amp_019_ti_ldo_error/reference
```

Normal evaluation consumes only this static delivery and prepared PDK resources; it requires neither Designs nor Private source. Development recipes and independent raw-waveform, binding and numerical audits belong to the separate ICLayout-Designs repository. Prepared configuration, resource digests, candidate identity, raw waveforms and measurements are recorded in each generated report.

## Source and License

Derived from [MacAnalog/spicexplorer-release, `amp_019_ti_ldo_error`](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_019_ti_ldo_error) at commit `263d0322f8900dc331536fbbe6c0e804514fc454`; retain the collection [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE). Required Notice: Copyright 2026 Danial Noori Zadeh. Circuit derivatives and witnesses retain applicable upstream terms; independently authored measurement decks are MIT.
