# Buffered-Reference LDO

## Overview

The fixed upstream GF180 6 V circuit combines its self-biased reference amplifier, gain-two reference divider, RC low-pass filter, self-biased error amplifier, PMOS pass device, bleeder and on-die output capacitor. The two inlined amplifiers retain this LDO accession's own dimensions and compensation values; they are not replaced by the standalone amplifier cases.

Nominal DC regulation, 1 kHz supply rejection and load-step excursion/recovery across four supply/load points. Coefficient 7 reflects interacting regulation stages and recovery across loads. Noise, loop return-ratio, cold start, dropout, PVT and statistical yield are outside this declared scope.

See [the problem](problem.md) for physical adaptation, functional bounds,
coefficient 7 and the 29565.16 um2 area anchor. Each case is independently
usable and does not import another circuit's development code.

## Files

- [Schematic](materials/schematic.svg): digest-bound main-sheet overview; hierarchical device banks remain expandable in the editable source project. This presentation asset is excluded from solver inputs.

- [Configuration](case.toml), [solver contract](problem.md).
- [Physical circuit](materials/circuit.cdl), [simulation circuit](materials/circuit.spice)
  and [measurement deck](materials/testbench.spice).
- [Reference GDS](reference/ldo_005_buffered_ref.gds), excluded from solver inputs.

## Reference Results

**Qualified.** Native standalone DRC and named-port LVS pass; the submitted
reference drives nominal RC extraction and every declared post-layout job.
Separate source jobs use the identical deck, models and condition parameters.
All required observations are finite and all declared functional/domain gates pass.

Conditions: `0`: `supply_v=3`, `load_a=5e-05`; `1`: `supply_v=3`, `load_a=0.0002`; `2`: `supply_v=3.3`, `load_a=5e-05`; `3`: `supply_v=3.3`, `load_a=0.0002`. Temperature is 27 C.
The following ranges are minima–maxima over these conditions; scoring uses the
worst same-condition pair, not a ratio of these range endpoints.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | ---: | ---: |
| `output_v` | V | 1.630587–1.635135 | 1.458141–1.518389 |
| `regulation_error_v` | V | 0.03058662–0.03513479 | 0.08161123–0.1418593 |
| `psrr_db` | dB | 36.40827–36.77022 | 33.20543–35.13973 |
| `excursion_v` | V | 5.458571e-05–0.0001859917 | 0.004311849–0.01727382 |
| `recovery_v` | V | 1.630587–1.635135 | 1.450305–1.516415 |
| `power_w` | W | 0.001282607–0.002191957 | 0.001037922–0.001791285 |
| `minimum_v` | V | 1.630434–1.635051 | 1.440892–1.514071 |
| `maximum_v` | V | 1.63062–1.635135 | 1.458141–1.518389 |
| Functional footprint | um2 | — | 282567.73 |

Reference score: **25.63532**, with area target **29565.16 um2**
and coefficient **7**. The area anchor is the documented
compact device/contact-envelope estimate, not this large routed witness.

The reference's DC regulation error is materially larger than its source's;
that degradation is retained in the continuous score. The 400–500 us recovery
observation is a finite-window mean, not a claim of complete asymptotic settling.
Independent waveform extrema and integration agree with the reported excursion
and recovery values. Excursion is measured directly as peak-to-peak, avoiding
subtraction of separately rounded DC-level extrema. This contract does not
qualify startup, dropout, return-ratio stability, PVT, noise or the upstream
regulated-output specification.

Native extracted compact-device graphs match the source after contracting wire
resistance and excluding wire capacitance for comparison only. The check retains
MOS W/L, physical poly/MIM dimensions, multiplicity and ordered ports in both
topology-only and final RC netlists. The actual simulations retain the extracted
RC, diffusion geometry and physical passive models. Model-only source MOS use
default diffusion geometry. Native resistor-body and well connections are ideal;
there is no distributed substrate, inductance or RF/EM extraction claim.

## Reproduce

Follow the [tools guide](../../../../../docs/tools.md), then run from Bench:

```bash
uv run --locked python -m benchmarking.engine.preview prepare \
  --case ldo_005_buffered_ref --image iclayout-bench-tools:ngspice45 \
  --output build/runs/ldo_005_buffered_ref-prepared
uv run --locked python -m benchmarking.engine.preview run \
  --prepared build/runs/ldo_005_buffered_ref-prepared \
  --output build/runs/ldo_005_buffered_ref-evaluation
```

These commands generate fresh reports and independent paired source observations.
Neither Designs nor Private is required. Use the
[source calibration procedure](../../../../../docs/tools.md#gf180-source-calibration)
with the prepared case to independently rerun the source jobs alone.

## Source and License

Derived from [MacAnalog/spicexplorer-release at 263d0322f8900dc331536fbbe6c0e804514fc454](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/ldo_005_buffered_ref); see the collection [license](../../LICENSE).
