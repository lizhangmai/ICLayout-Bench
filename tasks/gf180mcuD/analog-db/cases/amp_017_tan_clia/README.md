# Tan CLIA Three-Stage Amplifier

## Overview

Implement `amp_017_tan_clia` with the supplied fixed topology and dimensions. The PMOS input pair and cascoded NMOS branches drive voutn/net050. XM70 and XM71/XM72 form the current-inversion path through net3/net5; XM61 and the DM_1-controlled XM73 bias this path. XM68/XM69 drive the output. The 889198 ohm resistor from net5 to net2, 0.61268 pF net2-to-vss capacitor and 1.07905 pF net8-to-vout capacitor all remain.

The reference differential gain falls from 75.44 to 16.89 dB and its output bias shifts from 0.30001 to 0.26900 V. A diagnostic removal of wire resistance restores the source bias and gain. Native LVS and independent compact-device graph correspondence rule out an omitted or substituted amplifier branch. The scored candidate retains all wire R/C.

## Files

- [Schematic](materials/schematic.svg): digest-bound main-sheet overview; hierarchical device banks remain expandable in the editable source project. This presentation asset is excluded from solver inputs.

- [Problem](problem.md): solver-facing topology, interface, conditions and scoring.
- [Configuration](case.toml): frozen input digests, native checks and source pairings.
- [Physical netlist](materials/circuit.cdl) and [simulation netlist](materials/circuit.spice): matching physical core and ordered interface.
- [Follower testbench](materials/testbench.spice): DC bias, closed-loop AC and finite-window transient observations.
- [Differential AC testbench](materials/ac.spice): balanced excitation with checked DC feedback isolation.
- [Reference GDS](reference/amp_017_tan_clia.gds): independently generated physical witness.

Only the problem and four circuit/testbench materials enter solver inputs.
Collection LICENSE/NOTICE accompany material distributions separately. Reference
GDS, source records, authoring code and this README are maintainer materials.
Public loading, preparation and evaluation require neither Designs nor Private.

## Reference Results

The reference passes native DRC without marker waivers, named-interface LVS,
functional geometry, submitted-GDS-derived distributed RC extraction, independent
source simulation and all declared post-layout measurements. The compatible
[ngspice 45 overlay](../../../../../docs/tools.md#ngspice-45) uses the process
manifest's pinned PDK resources. These are the native development rule profiles,
not tape-out or density signoff. Compact-device graph and raw-waveform audits are
independent of the evaluator verdict.

Reference layout-v2 score **15.84275602**, E **0.48033719**,
Q **0.05225348**, functional area **1694723 um2**.
The compact-area anchor is **88555.19 um2**, estimated from device,
contact/isolation and passive envelopes plus 50% routing allowance, as specified
in the problem. Coefficient **7** follows the circuit capability rationale there.
Electrical quality is paired with independently simulated source measurements,
not paper targets or reference-GDS performance. Low quality does not waive
invalid extraction or measurement; complete finite observations remain mandatory.

| Observation | Unit | Independent source | Extracted reference |
| --- | --- | ---: | ---: |
| `output_v` | V | 0.300008558 | 0.269003789 |
| `power_w` | W | 0.000166493955 | 0.000104921193 |
| `gain_db` | dB | 75.43526 | 16.88774 |
| `gain_10khz_db` | dB | 54.70374 | 16.87867 |
| `closed_gain_10khz_db` | dB | -0.00120918 | -1.162473 |
| `late_error_v` | V | 5.625202e-06 | 0.04474002 |
| `return_error_v` | V | 8.558068e-06 | 0.03099621 |
| `ripple_v` | V | 5.50282e-13 | 9.139078e-12 |
| `return_ripple_v` | V | 4.42979e-13 | 2.568162e-11 |
| `mean_power_w` | W | 0.0001799124 | 0.0001122367 |
| `bias_v` | V | 0.872333382 | 0.851059702 |
| `high_v` | V | 0.3999944 | 0.35526 |
| `low_v` | V | 0.3000086 | 0.2690038 |
| `output_min_v` | V | 0.28487 | 0.2436802 |
| `output_max_v` | V | 0.433605 | 0.3732061 |
| `fixture_cm_max` | V | 7.4150064e-11 | 1.1945756e-12 |
| `dc_feedback_error_v` | V | 0 | 0 |

All observations use the exact conditions in the problem and static decks.
Differential AC checks residual common-mode drive and DC feedback mismatch at
1 uV; either failure aborts source/candidate simulation. Independent raw audits
also compare the AC fixture's DC point with the direct follower's DC point.
No phase margin, unity crossing, settling time, CMRR, noise, mismatch or PVT
coverage is declared. Transient starts from DC, not a supply-ramp startup state.

C0 uses a 10 by 30.635 um MIM: 612.7 fF versus 612.68 fF. C1 uses two 20 by 13.49 um MIM units: 1.0792 pF versus 1.07905 pF. R0 uses eighteen 1 by 49.4 um ppolyf_u_1k segments: 889.2 kohm by the nominal sheet formula versus 889.198 kohm requested. PDK compact models, including passive parasitics, determine simulation values.

Magic retains physical MOS/passive compact models and extracts interconnect R/C
from the candidate. Compact graph checks contract only wire resistance and the
declared tap boundary, then compare devices, parameters, ordered ports and nets.
IHP source models retain finite well/substrate taps; extracted IHP wells connect
to tap rails. GF180 uses the native isolated-well/body representation. Native LVS
checks those physical connections. Junction geometry remains candidate-derived.
This scope does not include distributed substrate, RF/EM or product signoff.

First-half minus second-half output means in the high/return windows are
-2.05391e-15/-4.38538e-15 V for the source and
-6.7446e-14/-3.85303e-13 V for the extracted
reference. These window diagnostics are not steady-state estimates.

Numerical calibration halves the maximum transient step for both source and RC.
Across both windows and circuits, the largest changes are 6.02205e-10 V
in output mean, 6.02205e-10 V in mean absolute error,
1.94752e-10 V in full peak-to-peak range and
3.71165e-11 W in mean supply power. Doubling AC sampling from
200 to 400 points/decade changes the two scored gains by less than 1e-9 dB.
These checks support the declared finite-window measurements; they do not prove
settling or steady-state stability. The authoring README supplies both refinement
commands and raw-waveform window diagnostics.

## Reproduce

Run from a Public checkout after [tool setup](../../../../../docs/tools.md).
Each command generates disposable outputs; choose fresh directories on rerun.

```bash
uv run --locked python -m benchmarking.engine.preview prepare \
  --case gf180mcuD.analog-db.amp_017_tan_clia --image iclayout-bench-tools:ngspice45 \
  --output build/runs/amp_017_tan_clia-prepared
uv run --locked python -m benchmarking.engine.preview run \
  --prepared build/runs/amp_017_tan_clia-prepared \
  --output build/runs/amp_017_tan_clia-reference
uv run --locked --group analysis pytest -m unit tests/unit/test_catalogs.py \
  tests/unit/test_evaluate.py tests/unit/test_scoring.py
```

The independently maintained Designs case README provides optional snapshot
verification, geometry regeneration, compact-graph/raw-waveform audits and
numerical refinement commands. None is a runtime dependency of Public.
Reports and identity-bound raw data are regenerated in the requested directory.

## Source and License

[Fixed upstream source](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_017_tan_clia):
MacAnalog's normalized capture of the AnalogGym circuit. The chosen gf180mcuD binding
uses its own defaults and explicit parameter ties. Grid adaptation, physical
passives/taps, expanded multiplicities, external bias port and measurement
fixtures are disclosed in the problem; no active feedback branch is removed
or replaced and no servo is added. Other process variants are not mixed in.

Circuit and layout derivatives retain collection [LICENSE](../../LICENSE) and
[NOTICE](../../NOTICE): PolyForm Noncommercial 1.0.0, Required Notice: Copyright
2026 Danial Noori Zadeh, and the recorded AnalogGym BSD-3-Clause component terms.
Independent observation decks are MIT. The framework license does not relicense
these circuit derivatives.
