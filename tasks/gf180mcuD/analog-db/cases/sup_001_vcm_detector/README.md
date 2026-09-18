# Passive Resistive Common-Mode Averager

## Overview

Two matched 1 Mohm resistors join vinp to vcm_out and vcm_out to vinn. This is a passive average detector, without a buffer, amplifier or CMFB controller. The fixed IHP binding contains ideal R cards, not process-specific resistor models; the maintained physical adaptation uses forty native GF180 ppolyf_u_1k segments (twenty per branch), totaling 999951.8 ohm per branch at TT/27 C. The extra vss port grounds their physical substrate; it is not a functional supply.

The 2–4 us average absolute step error is a finite-window quantity. Common and differential AC magnitudes use a 1 V half-input normalization; the differential residual is not divided by a near-zero source result. Nominal deterministic matching does not establish statistical mismatch or noise. The [GF180 model guide](https://gf180mcu-pdk.readthedocs.io/en/latest/analog/model_parameters/LV/LV_2_1.html) identifies -40, 25 and 125 C extraction temperatures; this task stays inside that interval. The [geometry guide](https://gf180mcu-pdk.readthedocs.io/en/latest/analog/model_parameters/LV/LV_2_2.html) distinguishes measured and pseudo-device dimensions. Coefficient 4: coupled matching, physical passive network, finite loading and parasitic dynamics; [problem](problem.md) records the independent area estimate.

## Files

- [Schematic](materials/schematic.svg): digest-bound main-sheet overview; hierarchical device banks remain expandable in the editable source project. This presentation asset is excluded from solver inputs.

- [Problem](problem.md): complete solver-facing boundary and scoring contract.
- [Case configuration](case.toml): frozen inputs, native backends and source-paired observations.
- [Physical netlist](materials/circuit.cdl), [simulator circuit](materials/circuit.spice), and [testbench](materials/testbench.spice).
- [Reference GDS](reference/sup_001_vcm_detector.gds): independent physical witness, excluded from solver inputs.

## Reference Results

Native DRC/LVS and full reference evaluation pass. Reference score: **9.16038635**; area 616725 um2. Ranges below span every declared condition, not statistical corners. Independent raw reconstruction and refinement of applicable analyses (half-step transient/DC sampling, double AC density and tenfold tighter solver tolerances) change the reconstructed paired score by 1.32e-06.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `output_v` | V | 0.399873134 … 0.599699865 | 0.399707149 … 0.599646203 |
| `power_w` | W | 8.02837486e-08 … 3.19847809e-07 | 8.0249523e-08 … 3.19692714e-07 |
| `gain` | 1 | 2.400499e-13 … 0.9994998 | 0.0001778698 … 0.9994993 |
| `gain_10khz` | 1 | 4.846298e-13 … 0.9989494 | 0.001340361 … 0.9984351 |
| `step_error_v` | V | 0.000715014137 … 0.00402711633 | 0.00269311624 … 0.00985797052 |


The loaded common and differential observations are distinct:

| Load (ohm) | Drive | Pre/post gain at 1 Hz | Pre/post gain at 10 kHz |
| --- | --- | --- | --- |
| 1e+06 | common | 0.6664552 / 0.6662379 | 0.6662918 / 0.6659149 |
| 1e+06 | differential | 2.400499e-13 / 0.0001778698 | 1.011667e-12 / 0.001340361 |
| 1e+09 | common | 0.9994998 / 0.9994993 | 0.9989494 / 0.9984351 |
| 1e+09 | differential | 8.370837e-13 / 0.0002668428 | 4.846298e-13 / 0.002009661 |

All static core devices, passives, compact models and ordered ports were checked against the fixed binding and both native topology/RC netlists. Same-condition source simulation supplies the baseline, not the witness score. Qualified cases also pass independent raw-waveform/KCL/window checks; candidate failures are never substituted with a finite score. The verified compatible image contains ngspice 45, Magic 8.3.678 and KLayout 0.30.11. No statistical mismatch, noise or manufactured silicon validation is asserted.

## Reproduce

From the Bench root, reuse a compatible image following the [tools guide](../../../../../docs/tools.md#image-development). These commands create new disposable resources and reports; use a fresh directory when repeating. No Designs or Private checkout is needed.

```bash
uv run --locked python -m benchmarking.engine.preview prepare \
  --case sup_001_vcm_detector --image iclayout-bench-tools:ngspice45 \
  --output "$PWD/build/runs/sup_001_vcm_detector-prepared"
uv run --locked python -m benchmarking.engine.cli evaluate \
  build/runs/sup_001_vcm_detector-prepared/case/case.toml \
  tasks/gf180mcuD/analog-db/cases/sup_001_vcm_detector/reference/sup_001_vcm_detector.gds \
  --output build/runs/sup_001_vcm_detector-evaluation
```

## Source and License

Derived from [MacAnalog sup_001_vcm_detector at commit 263d0322f8900dc331536fbbe6c0e804514fc454](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/sup_001_vcm_detector); retain [collection LICENSE](../../LICENSE) and [NOTICE](../../NOTICE). The leaf is independently authored/captured by Noorizadeh after Hsu et al. Its upstream schematic uses unvalued Rm placeholders; the authoritative sizing.yaml supplies the tied 1 Mohm defaults. No material from the excluded ideal-macro parent is used. Physical conversion adds native contacts and routes, expands declared multiplicities and implements resistors with native series segments; topology and total MOS dimensions remain fixed. Independently authored observation decks are MIT; database derivatives retain their separate terms.
