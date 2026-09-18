# Self-Biased LDO Reference Amplifier

## Overview

Nine MOS devices form the fixed upstream two-stage Miller amplifier, with a matched PMOS mirror and diode-connected self-bias. External unity feedback tests the reference-buffer function; no ideal internal amplifier or bias servo is inserted.

This independent static case preserves the pinned GF180 6 V binding, with
5 nm dimension quantization, native minimum channel lengths and physical R/C.
The scope is nominal AC/DC and unity-buffer step response at 1 pF and 10 pF.
Coefficient 6 and the 6223.21 um2 device-envelope area anchor are explained in
[the problem](problem.md). Upstream performance targets are not qualification gates.

## Files

- [Schematic](materials/schematic.svg): digest-bound main-sheet overview; hierarchical device banks remain expandable in the editable source project. This presentation asset is excluded from solver inputs.

- [Configuration](case.toml) and [solver contract](problem.md).
- [Physical circuit](materials/circuit.cdl), [simulation circuit](materials/circuit.spice)
  and [measurement deck](materials/testbench.spice).
- [Reference GDS](reference/amp_033_ti_ldo_ref_selfbias.gds), excluded from solver inputs.

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
| `output_v` | V | 0.7962012 | 0.7964511 |
| `power_w` | W | 0.0003905593 | 0.0003780534 |
| `gain_db` | dB | 74.18441–74.18444 | 74.23981–74.23984 |
| `unity_hz` | Hz | 7623046–4.237325e+07 | 6706758–3.025004e+07 |
| `phase_margin` | deg | 32.4064–73.4321 | 31.2458–68.3971 |
| `tracking_error_v` | V | 0.00376649–0.003798886 | 0.003522179–0.003560498 |
| `step_response_v` | V | 0.0100666–0.0100667 | 0.0100678–0.0100679 |
| Functional footprint | um2 | — | 42166.414 |

Reference score: **38.13411**, with area target **6223.21 um2**
and coefficient **6**. The area anchor is the documented
compact device/contact-envelope estimate, not this large routed witness.

Both loads have positive measured phase margin. Independent transient
integration agrees with the declared step/error measurements, and the late
4–5 us ripple is below 1 uV in this witness. This is a nominal finite-window
buffer evaluation; startup, mismatch/noise, PVT and saturation recovery are not
qualified. No upstream gain/bandwidth/power target is imposed.

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
  --case amp_033_ti_ldo_ref_selfbias --image iclayout-bench-tools:ngspice45 \
  --output build/runs/amp_033_ti_ldo_ref_selfbias-prepared
uv run --locked python -m benchmarking.engine.preview run \
  --prepared build/runs/amp_033_ti_ldo_ref_selfbias-prepared \
  --output build/runs/amp_033_ti_ldo_ref_selfbias-evaluation
```

These commands generate new reports, including paired source simulations.
They require neither Designs nor Private. For a separate source-only run, use
[the source calibration procedure](../../../../../docs/tools.md#gf180-source-calibration)
with the prepared case configuration. Use new output paths on each invocation.

## Source and License

Derived from [MacAnalog/spicexplorer-release, fixed commit 263d0322f8900dc331536fbbe6c0e804514fc454](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_033_ti_ldo_ref_selfbias); see the collection [license](../../LICENSE).
