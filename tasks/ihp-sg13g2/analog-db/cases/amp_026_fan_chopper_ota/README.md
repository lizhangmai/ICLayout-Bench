# Fan Two-Stage OTA with Static Output Chopper

## Overview

The pinned 23-MOS two-stage core retains its static straight-through output chopper, all disabled cross branches and its own precise four bias voltages. Four 44.67 um square MIM units implement the two original 6 pF compensation branches (6.0005211 pF per branch by the nominal area/perimeter formula). No CMFB is added. A differential unity-feedback test fixture controls only differential input; it does not regulate output common mode.

The extracted witness has output common mode near 13.24 mV and low-frequency gain about -4.66 dB, versus approximately 596.19 mV and 59.65 dB for the source. This is measured circuit degradation, not an extraction failure: native LVS and independently contracted compact-device graphs agree. Topology-only extraction and a diagnostic RC netlist with wire resistance removed restore the source operating point and gain. The ratioed no-CMFB bias is sensitive to distributed interconnect voltage drop. These diagnostic ablations are never qualification inputs. Common-mode kick/recovery observations are unscored, because reduced sensitivity at a rail is not evidence of regulation.

## Files

- [Schematic](materials/schematic.svg): digest-bound main-sheet overview; hierarchical device banks remain expandable in the editable source project. This presentation asset is excluded from solver inputs.

- [Problem](problem.md): complete solver-facing interface, conditions and scoring.
- [Configuration](case.toml): frozen input digests, native evaluation and source pairings.
- [Physical netlist](materials/circuit.cdl) and [simulation netlist](materials/circuit.spice): the same physical circuit and ordered interface.
- [Testbench](materials/testbench.spice): the declared external biases, loads, stimuli and observations.
- [Reference GDS](reference/amp_026_fan_chopper_ota.gds): independent physical witness.

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

Reference layout-v2 score: **23.86039744**, E = **0.32839977**,
Q = **0.17336144**. Functional area is
**86090.368 um2**; fixed compact-area anchor is
**14924.75 um2**. The device/contact/passive envelope calculation
and 50% routing allowance are published in the problem. Coefficient
**7** follows the declared capability scope there. The reference
is a feasibility witness; source measurements supply electrical normalization.
No upstream advertised performance is an implicit qualification threshold.

| Observation | Unit | Independent source range | Extracted range | Worst paired quality |
| --- | --- | ---: | ---: | ---: |
| `cm_bias_v` | V | 0.59619398 | 0.013237478 | 0.67303941 |
| `dm_bias_v` | V | 3.0042635e-13 | -1.0472271e-05 | 0.99999127 |
| `power_w` | W | 0.00026891246 | 0.0002533566 | 1.0613991 |
| `gain_db` | dB | 59.65068 | -4.656296 | 0.00060904755 |
| `gain_100khz_db` | dB | 36.03986 … 36.09916 | -7.642615 … -7.642573 | 0.0064999999 |
| `phase_100khz_deg` | deg | -86.72871 … -86.42558 | -48.91648 … -48.85247 | 0.82639988 |
| `step_response_v` | V | -0.04994799 … 0.04994799 | -0.040178588 … 0.041254022 | 0.83654844 |
| `cm_before_v` | V | 0.5957633 … 0.5959001 | 0.0132375 | diagnostic |
| `cm_kick_v` | V | 0.007639619 … 0.007696899 | 0.001105444 … 0.001106401 | diagnostic |
| `cm_recovery_v` | V | 0.001007317 … 0.001119774 | 2.206338e-08 … 2.206339e-08 | diagnostic |
| `cm_min_v` | V | 0.5949331 … 0.5955711 | 0.01317366 … 0.01317411 | diagnostic |
| `cm_max_v` | V | 0.6034029 … 0.603597 | 0.03234411 … 0.03353505 | diagnostic |

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
  --case ihp-sg13g2.analog-db.amp_026_fan_chopper_ota --image iclayout-bench-tools:ngspice45 \
  --output build/runs/amp_026_fan_chopper_ota-prepared
uv run --locked python -m benchmarking.engine.preview run \
  --prepared build/runs/amp_026_fan_chopper_ota-prepared \
  --output build/runs/amp_026_fan_chopper_ota-reference
uv run --locked pytest -m unit tests/unit/test_catalogs.py \
  tests/unit/test_evaluate.py tests/unit/test_scoring.py
```

The independent authoring repository provides optional regeneration and waveform
and compact-graph audit commands in its case README; it is not needed by any
command above. Reports and raw data are regenerated under the requested output.

## Source and License

[Fixed source](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_026_fan_chopper_ota):
Noorizadeh's normalized schematic capture after Fan et al. The circuit retains
its actual IHP sizing defaults, explicit parameter ties and topology. Bias ports,
physical taps/passives and diagnostic interfaces are documented adaptations.
Normalized circuit and layout derivatives retain collection [LICENSE](../../LICENSE)
and [NOTICE](../../NOTICE), including PolyForm Noncommercial 1.0.0 and Required
Notice: Copyright 2026 Danial Noori Zadeh. Independently authored measurement decks
are separately MIT; the framework license does not relicense circuit derivatives.
