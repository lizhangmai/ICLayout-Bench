# Divider-Biased NMOS Source Follower

## Overview

A single fixed 50/0.5 um nfet_03v3 (m=1) forms a source follower. Its drain connects to vdd, source to vout, body to vss, and gate to the midpoint of the internal 100 kohm/100 kohm supply divider. Each resistor uses two native ppolyf_u_1k segments, totaling 99995.18 ohm at TT/27 C. There is no control input, external reference, error amplifier or closed-loop regulator.

Only output operating point, finite load-step shift and actual supply loss are scored. Late-window ripple is an unscored diagnostic; sub-nanovolt ripple is below numerical voltage resolution. No regulation accuracy, PSRR, dropout or loop-margin claim is made. The model guide includes 50 um width as a pseudo-device scaling boundary, not a directly measured width sample. The [GF180 model guide](https://gf180mcu-pdk.readthedocs.io/en/latest/analog/model_parameters/LV/LV_2_1.html) identifies -40, 25 and 125 C extraction temperatures; this task stays inside that interval. The [geometry guide](https://gf180mcu-pdk.readthedocs.io/en/latest/analog/model_parameters/LV/LV_2_2.html) distinguishes measured and pseudo-device dimensions. Coefficient 3: local analog bias/transfer and controlled load response; [problem](problem.md) records the independent area estimate.

## Files

- [Schematic](materials/schematic.svg): digest-bound circuit drawing, excluded from solver inputs.

- [Problem](problem.md): complete solver-facing boundary and scoring contract.
- [Case configuration](case.toml): frozen inputs, native backends and source-paired observations.
- [Physical netlist](materials/circuit.cdl), [simulator circuit](materials/circuit.spice), and [testbench](materials/testbench.spice).
- [Reference GDS](reference/ldo_006_stub.gds): independent physical witness, excluded from solver inputs.

## Reference Results

Native DRC/LVS and full reference evaluation pass. Reference score: **22.41713859**; area 23861.1 um2. Ranges below span every declared condition, not statistical corners. Independent raw reconstruction and refinement of applicable analyses (half-step transient/DC sampling, double AC density and tenfold tighter solver tolerances) change the reconstructed paired score by 6.1e-12.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `output_v` | V | 0.0575574833 … 0.199858815 | 0.0576676606 … 0.200078316 |
| `power_w` | W | 7.32628703e-06 … 1.33983144e-05 | 7.32103975e-06 … 1.33914204e-05 |
| `step_shift_v` | V | -0.0645835182 … -0.0143381666 | -0.0646283451 … -0.0143986579 |
| `ripple_v` | V | 6.911138e-15 … 7.960358e-11 | 4.912737e-15 … 9.893034e-11 |

Native operating-point reports place the pass device in weak inversion: VGS is approximately 0.495–0.621 V, below reported VTH 0.724–0.779 V, while VDS 1.09–1.37 V exceeds VDSAT 0.050–0.053 V. The 57.7–200 mV pre-step loaded outputs are not evidence of regulation. Independent loaded OPs agree with the late transient to 0.1 uV.

All static core devices, passives, compact models and ordered ports were checked against the fixed binding and both native topology/RC netlists. Same-condition source simulation supplies the baseline, not the witness score. Qualified cases also pass independent raw-waveform/KCL/window checks; candidate failures are never substituted with a finite score. The verified compatible image contains ngspice 45, Magic 8.3.678 and KLayout 0.30.11. No statistical mismatch, noise or manufactured silicon validation is asserted.

## Reproduce

From the Bench root, reuse a compatible image following the [tools guide](../../../../../docs/tools.md#image-development). These commands create new disposable resources and reports; use a fresh directory when repeating. No Designs or Private checkout is needed.

```bash
uv run --locked python -m benchmarking.engine.preview prepare \
  --case ldo_006_stub --image iclayout-bench-tools:ngspice45 \
  --output "$PWD/build/runs/ldo_006_stub-prepared"
uv run --locked python -m benchmarking.engine.cli evaluate \
  build/runs/ldo_006_stub-prepared/case/case.toml \
  tasks/gf180mcuD/analog-db/cases/ldo_006_stub/reference/ldo_006_stub.gds \
  --output build/runs/ldo_006_stub-evaluation
```

## Source and License

Derived from [MacAnalog ldo_006_stub at commit 263d0322f8900dc331536fbbe6c0e804514fc454](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/ldo_006_stub); retain [collection LICENSE](../../LICENSE) and [NOTICE](../../NOTICE). The fixed manifest calls this an incomplete first-party SpiceXplorer stub. Its actual circuit is nevertheless an independently evaluable divider-biased source follower; the maintained title and scoring use only that function. Physical conversion adds native contacts and routes, expands declared multiplicities and implements resistors with native series segments; topology and total MOS dimensions remain fixed. Independently authored observation decks are MIT; database derivatives retain their separate terms.
