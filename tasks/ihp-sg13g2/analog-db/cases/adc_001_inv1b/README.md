# CMOS Inverter Threshold Core

## Overview

The fixed binding is a CMOS inverter: one 1/0.13 um NMOS and one 2.5/0.13 um PMOS, each m=1. Bodies connect to their respective rails through native physical contacts. It provides a threshold decision core; there is no sampling, independent reference, encoding or complete ADC.

The DC threshold is the unique output=0.6 V crossing, not a scan endpoint. Delay is the worse input 50% to opposite output 50% delay. Transition is the worse output 10–90% rise or 90–10% fall. Guards reject missing or multiple DC/transition crossings; independent audits require the intended 10–15 ns and 20–25 ns windows and correct ordering. DC high/low output uses actual endpoint samples, with a minimum 0.6 V swing establishing a meaningful logic transition. This is nominal loaded characterization, not Liberty/PVT or ADC accuracy. Coefficient 1: a single logic stage with loaded transitions and connectivity; [problem](problem.md) records the independent area estimate.

## Files

- [Schematic](materials/schematic.svg): digest-bound circuit drawing, excluded from solver inputs.

- [Problem](problem.md): complete solver-facing boundary and scoring contract.
- [Case configuration](case.toml): frozen inputs, native backends and source-paired observations.
- [Physical netlist](materials/circuit.cdl), [simulator circuit](materials/circuit.spice), and [testbench](materials/testbench.spice).
- [Reference GDS](reference/adc_001_inv1b.gds): independent physical witness, excluded from solver inputs.

## Reference Results

Native DRC/LVS and full reference evaluation pass. Reference score: **10.59976816**; area 4291.52 um2. Ranges below span every declared condition, not statistical corners. Independent waveform reconstruction and half-step transient/DC sampling with tenfold tighter tolerances change the paired score by 0.000140376.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `threshold_v` | V | 0.6299057 | 0.6298425 |
| `delay_s` | s | 6.921866e-11 | 1.671058e-10 |
| `transition_s` | s | 7.341807e-11 | 2.075646e-10 |
| `power_w` | W | 1.879725e-06 | 6.172636e-06 |
| `swing_v` | V | 1.19999992 | 1.19999991 |

All static core devices, passives, compact models and ordered ports were checked against the fixed binding and both native topology/RC netlists. Same-condition source simulation supplies the baseline, not the witness score. Qualified cases also pass independent raw-waveform/KCL/window checks; candidate failures are never substituted with a finite score. The verified compatible image contains ngspice 45, Magic 8.3.678 and KLayout 0.30.11. No statistical mismatch, noise or manufactured silicon validation is asserted.

## Reproduce

From the Bench root, reuse a compatible image following the [tools guide](../../../../../docs/tools.md#image-development). These commands create new disposable resources and reports; use a fresh directory when repeating. No Designs or Private checkout is needed.

```bash
uv run --locked python -m benchmarking.engine.preview prepare \
  --case adc_001_inv1b --image iclayout-bench-tools:ngspice45 \
  --output "$PWD/build/runs/adc_001_inv1b-prepared"
uv run --locked python -m benchmarking.engine.cli evaluate \
  build/runs/adc_001_inv1b-prepared/case/case.toml \
  tasks/ihp-sg13g2/analog-db/cases/adc_001_inv1b/reference/adc_001_inv1b.gds \
  --output build/runs/adc_001_inv1b-evaluation
```

## Source and License

Derived from [MacAnalog adc_001_inv1b at commit 263d0322f8900dc331536fbbe6c0e804514fc454](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/adc_001_inv1b); retain [collection LICENSE](../../LICENSE) and [NOTICE](../../NOTICE). The fixed manifest identifies a SpiceXplorer worked example with analog-circuit-design Apache-2.0 provenance. The normalized database and physical derivative retain PolyForm Noncommercial terms; component attribution does not replace the database license. The fixed upstream analysis supply of 1.2 V is retained. Physical conversion adds native contacts and routes, expands declared multiplicities and implements resistors with native series segments; topology and total MOS dimensions remain fixed. Independently authored observation decks are MIT; database derivatives retain their separate terms.
