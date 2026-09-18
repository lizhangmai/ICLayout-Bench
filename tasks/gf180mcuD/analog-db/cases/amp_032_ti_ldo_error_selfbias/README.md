# Self-Biased LDO Error Amplifier

## Overview

Eleven MOS devices form the fixed upstream two-stage amplifier, with a level-shifted PMOS mirror, its 500 kohm gate-rail tie, diode-connected self-bias and series Miller compensation. The direct common-source output stage is the revision present in the pinned netlist; the retired stacked stage is not used.

This independent static case preserves the pinned GF180 6 V binding, with
5 nm dimension quantization, native minimum channel lengths and physical R/C.
The scope is nominal AC/DC and unity-buffer step response at 1 pF and 10 pF.
Coefficient 6 and the 19112.51 um2 device-envelope area anchor are explained in
[the problem](problem.md). Upstream performance targets are not qualification gates.

## Files

- [Schematic](materials/schematic.svg): digest-bound main-sheet overview; hierarchical device banks remain expandable in the editable source project. This presentation asset is excluded from solver inputs.

- [Configuration](case.toml) and [solver contract](problem.md).
- [Physical circuit](materials/circuit.cdl), [simulation circuit](materials/circuit.spice)
  and [measurement deck](materials/testbench.spice).
- [Reference GDS](reference/amp_032_ti_ldo_error_selfbias.gds), excluded from solver inputs.

## Reference Results

**Qualified.** Native standalone DRC and named-port LVS pass; the submitted
reference drives nominal RC extraction and every declared post-layout job.
Separate source jobs use the identical deck, models and condition parameters.
All required observations are finite and all declared functional/domain gates pass.

Conditions: `0`: `load_f=1e-11`; `1`: `load_f=1e-12`. Temperature is 27 C.
The following ranges are minima–maxima over these conditions; scoring uses the
worst same-condition pair, not a ratio of these range endpoints.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | ---: | ---: |
| `output_v` | V | 1.594239 | 1.595315 |
| `power_w` | W | 0.000596368 | 0.0005325109 |
| `gain_db` | dB | 73.20742–73.20744 | 73.72485–73.72487 |
| `unity_hz` | Hz | 1.934322e+07–1.016426e+08 | 1.074786e+07–1.143218e+07 |
| `phase_margin` | deg | 53.0322–72.0628 | -11.6653–48.1944 |
| `tracking_error_v` | V | 0.005767942–0.005769709 | 0.004691455–0.0136376 |
| `step_response_v` | V | 0.009986 | 0.009987–0.0126 |
| Functional footprint | um2 | — | 170207.37 |

Reference score: **29.78628**, with area target **19112.51 um2**
and coefficient **6**. The area anchor is the documented
compact device/contact-envelope estimate, not this large routed witness.

At 10 pF the reference phase margin is -11.67 degrees and its late
4–5 us output ripple is 82.50 mV peak-to-peak. At 1 pF the phase margin is
48.19 degrees and late ripple is 0.108 mV. This is a measured load-dependent
stability limitation of the witness, not a missing measurement or tool error.
Independent Gear-2 integration at 0.1 ns, reltol=1e-5, abstol=1e-14 A
and vntol=1e-8 V reproduces 82.52 mV late ripple in the same reference RC circuit.
The native RC graph has also been checked against its source. The score retains this degradation; qualification establishes
the declared evaluation chain, not unconditional closed-loop stability.
No startup, mismatch/noise, PVT, saturation-recovery or upstream data-sheet claim
is made.

Native extracted compact-device graphs match the source after contracting wire
resistance and excluding wire capacitance for comparison only. The check retains
MOS W/L, physical poly/MIM dimensions, multiplicity and ordered ports in both
topology-only and final RC netlists. The actual simulations retain the extracted
RC, diffusion geometry and physical passive models. Model-only source MOS use
default diffusion geometry. Native resistor-body and well connections are ideal;
there is no distributed substrate, inductance or RF/EM extraction claim.

## Reproduce

From Bench, follow the [tools guide](../../../../../docs/tools.md), then run:

```bash
uv run --locked python -m benchmarking.engine.preview prepare \
  --case amp_032_ti_ldo_error_selfbias --image iclayout-bench-tools:ngspice45 \
  --output build/runs/amp_032_ti_ldo_error_selfbias-prepared
uv run --locked python -m benchmarking.engine.preview run \
  --prepared build/runs/amp_032_ti_ldo_error_selfbias-prepared \
  --output build/runs/amp_032_ti_ldo_error_selfbias-evaluation
```

These commands generate new reports, including paired source simulations.
They require neither Designs nor Private. For a separate source-only run, use
[the source calibration procedure](../../../../../docs/tools.md#gf180-source-calibration)
with the prepared case configuration. Use new output paths on each invocation.

## Source and License

Derived from [MacAnalog/spicexplorer-release, fixed commit 263d0322f8900dc331536fbbe6c0e804514fc454](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_032_ti_ldo_error_selfbias); see the collection [license](../../LICENSE).
