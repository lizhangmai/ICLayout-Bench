# Fan Telescopic OTA with Transistor DDA-CMFB

## Overview

The pinned 16-MOS telescopic core retains its transistor DDA-CMFB. It is not a complete RRL or switched-capacitor integrator. The source bias itself regulates near 0.474 V under the declared 0.6 V reference; this independent result is not relabeled as 0.6 V accuracy. Differential amplification and common-mode kick recovery remain observable. The reference is intentionally a straightforward routed witness, not an optimized amplifier.

## Files

- [Schematic](materials/schematic.svg): digest-bound main-sheet overview; hierarchical device banks remain expandable in the editable source project. This presentation asset is excluded from solver inputs.

- [Problem](problem.md): complete solver-facing interface, conditions and scoring.
- [Configuration](case.toml): frozen input digests, native evaluation and source pairings.
- [Physical netlist](materials/circuit.cdl) and [simulation netlist](materials/circuit.spice): the same physical circuit and ordered interface.
- [Testbench](materials/testbench.spice): the declared external biases, loads, stimuli and observations.
- [Reference GDS](reference/amp_027_fan_rrl_ota.gds): independent physical witness.

Only the problem and three circuit/testbench materials enter solver inputs.
Collection LICENSE/NOTICE accompany distributions separately; witnesses, authoring
code, source snapshots and this README are not solver inputs. Public preparation
and evaluation do not import Designs or Private.

## Reference Results

The reference passes native DRC (including the maximal rule set, no waivers),
named-interface LVS, functional geometry, candidate-derived RC extraction and
all declared source/post-layout measurements. The compatible tools environment is
the reproducible [ngspice 45 overlay](../../../../../docs/tools.md#ngspice-45), with
the pinned IHP resources selected by the process manifest. Density and antenna
follow the published native development profile; no tape-out signoff is claimed.

Independent wheel installation was evaluated outside the source checkout. Material
loading checks verify all digests and isolated solver inputs. Compact-device graph
and raw-waveform checks are separate from the evaluator verdict. Shared catalog,
evaluation and scoring regressions exercise rejection and unknown-result semantics.

Reference layout-v2 score: **20.92160074**, E = **0.88886758**,
Q = **0.049243936**. Functional area is
**21033.656 um2**; fixed compact-area anchor is
**1035.78 um2**. The device/contact/passive envelope calculation
and 50% routing allowance are published in the problem. Coefficient
**6** follows the declared capability scope there. The reference
is a feasibility witness; source measurements supply electrical normalization.
No upstream advertised performance is an implicit qualification threshold.

| Observation | Unit | Independent source range | Extracted range | Worst paired quality |
| --- | --- | ---: | ---: | ---: |
| `cm_bias_v` | V | 0.47398683 | 0.47361318 | 0.99968872 |
| `dm_bias_v` | V | -1.2210255e-10 | 0.011611399 | 0.99041657 |
| `power_w` | W | 7.7070861e-05 | 7.5114962e-05 | 1.0260387 |
| `gain_db` | dB | 46.60662 | 46.4552 | 0.9827182 |
| `gain_100khz_db` | dB | 31.02551 … 45.23201 | 30.66026 … 44.90733 | 0.95882092 |
| `phase_100khz_deg` | deg | -80.4361 … -31.40133 | -80.67349 … -33.21182 | 0.99004188 |
| `step_response_v` | V | -0.0042789399 … 0.0042789401 | -0.004207043 … 0.00420294 | 0.9192561 |
| `cm_before_v` | V | 0.4739868 … 0.4739871 | 0.4736045 … 0.4736224 | diagnostic |
| `cm_kick_v` | V | 0.03163173 … 0.03163189 | 0.03266856 … 0.0327199 | 0.96674878 |
| `cm_recovery_v` | V | 3.066692e-08 … 2.692908e-07 | 1.825762e-08 … 8.933328e-06 | 0.12778102 |
| `cm_min_v` | V | 0.4739854 … 0.4739868 | 0.4735621 … 0.4736132 | diagnostic |
| `cm_max_v` | V | 0.5056187 … 0.5056188 | 0.5062755 … 0.5063331 | diagnostic |

Ranges summarize all declared conditions, not interchangeable endpoints for
computing ratios. Reports retain the individual paired observations and score.

Magic extracts nominal interconnect R/C from the submitted GDS. Physical MOS,
MIM and high-poly model cards remain in the candidate netlist. Its body boundary
connects wells/substrate to tap rails; source simulation retains finite tap models.
Native LVS verifies the explicit tap dimensions and connectivity, and independent
graph checks compare MOS/passive parameters and connections after contracting only
wire resistance and the diagnostic tap boundary. Compact-core comparison checks
MOS W/L/m and physical passive dimensions. Layout-derived MOS junction areas and
perimeters remain in the extracted simulation. This scope is not foundry signoff,
PVT, mismatch, noise, RF extraction or a complete product specification.

## Reproduce

Run from a Public checkout after the [shared tools setup](../../../../../docs/tools.md).
These commands generate fresh local output directories; they are not repository
inputs. Reuse a compatible ngspice 45 image or build the documented overlay.

```bash
uv run --locked python -m benchmarking.engine.preview prepare \
  --case ihp-sg13g2.analog-db.amp_027_fan_rrl_ota --image iclayout-bench-tools:ngspice45 \
  --output build/runs/amp_027_fan_rrl_ota-prepared
uv run --locked python -m benchmarking.engine.preview run \
  --prepared build/runs/amp_027_fan_rrl_ota-prepared \
  --output build/runs/amp_027_fan_rrl_ota-reference
uv run --locked pytest -m unit tests/unit/test_catalogs.py \
  tests/unit/test_evaluate.py tests/unit/test_scoring.py
```

The independent authoring repository provides optional regeneration and waveform
and compact-graph audit commands in its case README; it is not needed by any
command above. Reports and raw data are regenerated under the requested output.

## Source and License

[Fixed source](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_027_fan_rrl_ota):
Noorizadeh's normalized schematic capture after Fan et al. The circuit retains
its actual IHP sizing defaults, explicit parameter ties and topology. Bias ports,
physical taps/passives and diagnostic interfaces are documented adaptations.
Normalized circuit and layout derivatives retain collection [LICENSE](../../LICENSE)
and [NOTICE](../../NOTICE), including PolyForm Noncommercial 1.0.0 and Required
Notice: Copyright 2026 Danial Noori Zadeh. Independently authored measurement decks
are separately MIT; the framework license does not relicense circuit derivatives.
