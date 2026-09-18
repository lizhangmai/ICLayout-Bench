# Song DACFC Three-Stage Amplifier

## Overview

Implement `amp_016_song_dacfc` with the supplied fixed topology and dimensions. The primary PMOS input pair feeds the cascoded voutn/net4 path. The separate XM57/XM58 input pair, biased by XM59, feeds net043/net049 directly; XM7 also feeds net049 from voutn. XM60/XM61 retain the main cascodes, while XM62/XM63, XM68/XM69 and XM64/XM65/XM70/XM71 retain the auxiliary net70 feedback network. XM11/XM23 drive vout. Both compensation capacitors remain: 1.5 pF from vout to net70 and 0.7 pF from net4 to vss.

Both source and extracted follower oscillate in the declared observation window: high-window full peak-to-peak output is about 0.152/0.192 V. Means and full ranges describe finite-time behavior; neither a mean near the input nor a small-signal follower gain near unity establishes closed-loop stability.

## Files

- [Schematic](materials/schematic.svg): digest-bound main-sheet overview; hierarchical device banks remain expandable in the editable source project. This presentation asset is excluded from solver inputs.

- [Problem](problem.md): solver-facing topology, interface, conditions and scoring.
- [Configuration](case.toml): frozen input digests, native checks and source pairings.
- [Physical netlist](materials/circuit.cdl) and [simulation netlist](materials/circuit.spice): matching physical core and ordered interface.
- [Follower testbench](materials/testbench.spice): DC bias, closed-loop AC and finite-window transient observations.
- [Differential AC testbench](materials/ac.spice): balanced excitation with checked DC feedback isolation.
- [Reference GDS](reference/amp_016_song_dacfc.gds): independently generated physical witness.

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

Reference layout-v2 score **33.64334049**, E **0.95944004**,
Q **0.11797239**, functional area **153208.7 um2**.
The compact-area anchor is **18074.4 um2**, estimated from device,
contact/isolation and passive envelopes plus 50% routing allowance, as specified
in the problem. Coefficient **8** follows the circuit capability rationale there.
Electrical quality is paired with independently simulated source measurements,
not paper targets or reference-GDS performance. Low quality does not waive
invalid extraction or measurement; complete finite observations remain mandatory.

| Observation | Unit | Independent source | Extracted reference |
| --- | --- | ---: | ---: |
| `output_v` | V | 0.321423165 | 0.316460324 |
| `power_w` | W | 0.000197105517 | 0.000189439486 |
| `gain_db` | dB | 69.4786 | 67.92232 |
| `gain_10khz_db` | dB | 45.1236 | 44.52714 |
| `closed_gain_10khz_db` | dB | 0.001331662 | -0.0003398908 |
| `late_error_v` | V | 0.04387765 | 0.05437209 |
| `return_error_v` | V | 0.0334657 | 0.04058976 |
| `ripple_v` | V | 0.1522979 | 0.1916692 |
| `return_ripple_v` | V | 0.109958 | 0.1402743 |
| `mean_power_w` | W | 0.0002266865 | 0.0002183554 |
| `bias_v` | V | 1.09438843 | 1.09412591 |
| `high_v` | V | 0.415924 | 0.4073447 |
| `low_v` | V | 0.3182086 | 0.3115436 |
| `output_min_v` | V | 0.2573824 | 0.236271 |
| `output_max_v` | V | 0.4912286 | 0.5026974 |
| `fixture_cm_max` | V | 3.77258338e-11 | 3.12344997e-11 |
| `dc_feedback_error_v` | V | 0 | 0 |

All observations use the exact conditions in the problem and static decks.
Differential AC checks residual common-mode drive and DC feedback mismatch at
1 uV; either failure aborts source/candidate simulation. Independent raw audits
also compare the AC fixture's DC point with the direct follower's DC point.
No phase margin, unity crossing, settling time, CMRR, noise, mismatch or PVT
coverage is declared. Transient starts from DC, not a supply-ramp startup state.

C0 is one 31.57 um square cmim: 1.50004855 pF versus 1.5 pF. C2 is one 21.55 um square cmim: 0.70005175 pF versus 0.7 pF. Both original compensation branches remain physical.

Magic retains physical MOS/passive compact models and extracts interconnect R/C
from the candidate. Compact graph checks contract only wire resistance and the
declared tap boundary, then compare devices, parameters, ordered ports and nets.
IHP source models retain finite well/substrate taps; extracted IHP wells connect
to tap rails. GF180 uses the native isolated-well/body representation. Native LVS
checks those physical connections. Junction geometry remains candidate-derived.
This scope does not include distributed substrate, RF/EM or product signoff.

First-half minus second-half output means in the high/return windows are
-0.000265429/0.00030925 V for the source and
-0.00071188/-1.42735e-05 V for the extracted
reference. These window diagnostics are not steady-state estimates.

Numerical calibration halves the maximum transient step for both source and RC.
Across both windows and circuits, the largest changes are 0.000177677 V
in output mean, 0.000219348 V in mean absolute error,
0.000650208 V in full peak-to-peak range and
9.93791e-08 W in mean supply power. Doubling AC sampling from
200 to 400 points/decade changes the two scored gains by less than 1e-9 dB.
These checks support the declared finite-window measurements; they do not prove
settling or steady-state stability. The authoring README supplies both refinement
commands and raw-waveform window diagnostics.

## Reproduce

Run from a Public checkout after [tool setup](../../../../../docs/tools.md).
Each command generates disposable outputs; choose fresh directories on rerun.

```bash
uv run --locked python -m benchmarking.engine.preview prepare \
  --case ihp-sg13g2.analog-db.amp_016_song_dacfc --image iclayout-bench-tools:ngspice45 \
  --output build/runs/amp_016_song_dacfc-prepared
uv run --locked python -m benchmarking.engine.preview run \
  --prepared build/runs/amp_016_song_dacfc-prepared \
  --output build/runs/amp_016_song_dacfc-reference
uv run --locked --group analysis pytest -m unit tests/unit/test_catalogs.py \
  tests/unit/test_evaluate.py tests/unit/test_scoring.py
```

The independently maintained Designs case README provides optional snapshot
verification, geometry regeneration, compact-graph/raw-waveform audits and
numerical refinement commands. None is a runtime dependency of Public.
Reports and identity-bound raw data are regenerated in the requested directory.

## Source and License

[Fixed upstream source](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_016_song_dacfc):
MacAnalog's normalized capture of the AnalogGym circuit. The chosen ihp-sg13g2 binding
uses its own defaults and explicit parameter ties. Grid adaptation, physical
passives/taps, expanded multiplicities, external bias port and measurement
fixtures are disclosed in the problem; no active feedback branch is removed
or replaced and no servo is added. Other process variants are not mixed in.

Circuit and layout derivatives retain collection [LICENSE](../../LICENSE) and
[NOTICE](../../NOTICE): PolyForm Noncommercial 1.0.0, Required Notice: Copyright
2026 Danial Noori Zadeh, and the recorded AnalogGym BSD-3-Clause component terms.
Independent observation decks are MIT. The framework license does not relicense
these circuit derivatives.
