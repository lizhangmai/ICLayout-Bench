# StrongARM Dynamic Comparator

## Overview

Fifteen upstream MOS instances implement the clocked StrongARM latch: differential input pair, clocked tail, cross-coupled regenerative devices, four precharge devices and two output inverters. The input pair multiplicities expand the physical circuit to seventeen devices. The maintained GF180 3.3 V binding uses the fixed sizing defaults and authored ties from the pinned accession.

Four nominal input-polarity/common-mode combinations, reset, decision delay/slew and average supply power. Coefficient 6 reflects regenerative decisions with clocked reset and buffered loads. Offset distribution, metastability statistics, noise, PVT and RF/EM are outside this declared scope.

See [the problem](problem.md) for physical adaptation, functional bounds,
coefficient 6 and the 490.86 um2 area anchor. Each case is independently
usable and does not import another circuit's development code.

## Files

- [Schematic](materials/schematic.svg): digest-bound circuit drawing, excluded from solver inputs.

- [Configuration](case.toml), [solver contract](problem.md).
- [Physical circuit](materials/circuit.cdl), [simulation circuit](materials/circuit.spice)
  and [measurement deck](materials/testbench.spice).
- [Reference GDS](reference/cmp_002_strongarm.gds), excluded from solver inputs.

## Reference Results

**Qualified.** Native standalone DRC and named-port LVS pass; the submitted
reference drives nominal RC extraction and every declared post-layout job.
Separate source jobs use the identical deck, models and condition parameters.
All required observations are finite and all declared functional/domain gates pass.

Conditions: `0`: `polarity=1`, `common_v=1.2`; `1`: `polarity=-1`, `common_v=1.2`; `2`: `polarity=1`, `common_v=1.65`; `3`: `polarity=-1`, `common_v=1.65`. Temperature is 27 C.
The following ranges are minima–maxima over these conditions; scoring uses the
worst same-condition pair, not a ratio of these range endpoints.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | ---: | ---: |
| `delay_s` | s | 3.284388e-10–4.099738e-10 | 7.518335e-10–1.100915e-09 |
| `slew_s` | s | 2.837858e-10–2.98826e-10 | 5.01812e-10–5.793005e-10 |
| `power_w` | W | 6.995383e-05–7.492169e-05 | 0.0001493069–0.0001612673 |
| `decision_v` | V | 3.3 | 3.3 |
| `reset_p_v` | V | 3.68746e-09–3.693198e-09 | 2.635351e-06–2.819031e-06 |
| `reset_n_v` | V | 3.68746e-09–3.693198e-09 | 2.681988e-06–2.868409e-06 |
| Functional footprint | um2 | — | 9519.3 |

Reference score: **17.38276**, with area target **490.86 um2**
and coefficient **6**. The area anchor is the documented
compact device/contact-envelope estimate, not this large routed witness.

Both differential polarities resolve correctly at both common modes, and
both buffered outputs reset below half-rail before the fifth evaluate edge.
Independent waveform interpolation reproduces fifth-edge delay and slew;
time-weighted supply-current integration reproduces power. This does not
qualify offset, input-referred noise, near-zero-input metastability, kickback,
PVT or an upstream speed/energy target.

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
  --case cmp_002_strongarm --image iclayout-bench-tools:ngspice45 \
  --output build/runs/cmp_002_strongarm-prepared
uv run --locked python -m benchmarking.engine.preview run \
  --prepared build/runs/cmp_002_strongarm-prepared \
  --output build/runs/cmp_002_strongarm-evaluation
```

These commands generate fresh reports and independent paired source observations.
Neither Designs nor Private is required. Use the
[source calibration procedure](../../../../../docs/tools.md#gf180-source-calibration)
with the prepared case to independently rerun the source jobs alone.

## Source and License

Derived from [MacAnalog/spicexplorer-release at 263d0322f8900dc331536fbbe6c0e804514fc454](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/cmp_002_strongarm); see the collection [license](../../LICENSE).
