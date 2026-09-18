# Ramos PFC Three-Stage Amplifier

## Overview

Implement `amp_014_ramos_pfc` with the supplied fixed topology and dimensions. The PMOS input pair drives the cascoded NMOS branches at dm_2/net063; the voutn mirror produces net050. XM10 and the XM21/XM22 mirror drive net049, while XM11/XM23 drive the single-ended output. Both compensation paths remain: 63 pF from net050 to vout and 25 pF from net050 to net049. The vb3/vb4 bias network is retained.

The reference loses about 19.60 dB of low-frequency differential gain and develops about 8.83 mV tracking error. Removing only extracted wire resistance in a diagnostic circuit restores differential gain to 100.8458 dB, close to the 100.8461 dB source. This supports distributed routing voltage drop as the cause; the scored candidate retains all extracted resistance.

## Files

- [Schematic](materials/schematic.svg): digest-bound main-sheet overview; hierarchical device banks remain expandable in the editable source project. This presentation asset is excluded from solver inputs.

- [Problem](problem.md): solver-facing topology, interface, conditions and scoring.
- [Configuration](case.toml): frozen input digests, native checks and source pairings.
- [Physical netlist](materials/circuit.cdl) and [simulation netlist](materials/circuit.spice): matching physical core and ordered interface.
- [Follower testbench](materials/testbench.spice): DC bias, closed-loop AC and finite-window transient observations.
- [Differential AC testbench](materials/ac.spice): balanced excitation with checked DC feedback isolation.
- [Reference GDS](reference/amp_014_ramos_pfc.gds): independently generated physical witness.

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

Reference layout-v2 score **46.99594860**, E **0.79917880**,
Q **0.27636108**, functional area **687738.3 um2**.
The compact-area anchor is **190064.1 um2**, estimated from device,
contact/isolation and passive envelopes plus 50% routing allowance, as specified
in the problem. Coefficient **7** follows the circuit capability rationale there.
Electrical quality is paired with independently simulated source measurements,
not paper targets or reference-GDS performance. Low quality does not waive
invalid extraction or measurement; complete finite observations remain mandatory.

| Observation | Unit | Independent source | Extracted reference |
| --- | --- | ---: | ---: |
| `output_v` | V | 0.399860942 | 0.391176082 |
| `power_w` | W | 0.000622605153 | 0.000404762891 |
| `gain_db` | dB | 100.8461 | 81.24882 |
| `gain_10khz_db` | dB | 44.53335 | 34.84534 |
| `closed_gain_10khz_db` | dB | -0.000155305 | -0.002223533 |
| `late_error_v` | V | 0.0001391378 | 0.008833024 |
| `return_error_v` | V | 0.000139065 | 0.008823918 |
| `ripple_v` | V | 2.743934e-09 | 9.133805e-12 |
| `return_ripple_v` | V | 1.578036e-09 | 8.333334e-12 |
| `mean_power_w` | W | 0.000622618 | 0.0004047049 |
| `bias_v` | V | 1.08995852 | 1.08871841 |
| `high_v` | V | 0.4998609 | 0.491167 |
| `low_v` | V | 0.3998609 | 0.3911761 |
| `output_min_v` | V | 0.3993451 | 0.3911761 |
| `output_max_v` | V | 0.5003946 | 0.491167 |
| `fixture_cm_max` | V | 1.39397649e-09 | 1.27665023e-10 |
| `dc_feedback_error_v` | V | 1.28230759e-14 | 0 |

All observations use the exact conditions in the problem and static decks.
Differential AC checks residual common-mode drive and DC feedback mismatch at
1 uV; either failure aborts source/candidate simulation. Independent raw audits
also compare the AC fixture's DC point with the direct follower's DC point.
No phase margin, unity crossing, settling time, CMRR, noise, mismatch or PVT
coverage is declared. Transient starts from DC, not a supply-ramp startup state.

C0 uses sixteen 51.18 um square cmim units: nominal 62.9964384 pF versus 63 pF requested. C1 uses seven 48.74 um square units: 24.9982586 pF versus 25 pF. All 23 units and their original connections remain physical.

Magic retains physical MOS/passive compact models and extracts interconnect R/C
from the candidate. Compact graph checks contract only wire resistance and the
declared tap boundary, then compare devices, parameters, ordered ports and nets.
IHP source models retain finite well/substrate taps; extracted IHP wells connect
to tap rails. GF180 uses the native isolated-well/body representation. Native LVS
checks those physical connections. Junction geometry remains candidate-derived.
This scope does not include distributed substrate, RF/EM or product signoff.

First-half minus second-half output means in the high/return windows are
7.35917e-12/-1.77067e-11 V for the source and
-3.76255e-13/-8.7208e-13 V for the extracted
reference. These window diagnostics are not steady-state estimates.

Numerical calibration halves the maximum transient step for both source and RC.
Across both windows and circuits, the largest changes are 8.80894e-09 V
in output mean, 8.80894e-09 V in mean absolute error,
1.65771e-09 V in full peak-to-peak range and
1.38422e-10 W in mean supply power. Doubling AC sampling from
200 to 400 points/decade changes the two scored gains by less than 1e-9 dB.
These checks support the declared finite-window measurements; they do not prove
settling or steady-state stability. The authoring README supplies both refinement
commands and raw-waveform window diagnostics.

## Reproduce

Run from a Public checkout after [tool setup](../../../../../docs/tools.md).
Each command generates disposable outputs; choose fresh directories on rerun.

```bash
uv run --locked python -m benchmarking.engine.preview prepare \
  --case ihp-sg13g2.analog-db.amp_014_ramos_pfc --image iclayout-bench-tools:ngspice45 \
  --output build/runs/amp_014_ramos_pfc-prepared
uv run --locked python -m benchmarking.engine.preview run \
  --prepared build/runs/amp_014_ramos_pfc-prepared \
  --output build/runs/amp_014_ramos_pfc-reference
uv run --locked --group analysis pytest -m unit tests/unit/test_catalogs.py \
  tests/unit/test_evaluate.py tests/unit/test_scoring.py
```

The independently maintained Designs case README provides optional snapshot
verification, geometry regeneration, compact-graph/raw-waveform audits and
numerical refinement commands. None is a runtime dependency of Public.
Reports and identity-bound raw data are regenerated in the requested directory.

## Source and License

[Fixed upstream source](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_014_ramos_pfc):
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
