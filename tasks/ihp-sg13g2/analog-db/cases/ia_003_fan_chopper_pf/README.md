# Fan Clocked Capacitive Instrumentation Amplifier with Positive Feedback

## Overview

All 47 MOS and the input, feedback, output and positive-feedback choppers operate under real clocks. Both positive-feedback capacitors remain in their original connections. Physical MIM and high-poly replace ideal passives without removing or disabling a branch. No CMFB is added. The circuit uses its own pinned transistor dimensions and biases; it does not import another case's implementation. Input impedance and feedback behavior are measured in the full running circuit; no paper impedance-boost ratio is imposed as a hard bound.

## Files

- [Schematic](materials/schematic.svg): digest-bound main-sheet overview; hierarchical device banks remain expandable in the editable source project. This presentation asset is excluded from solver inputs.

- [Problem](problem.md): complete solver-facing interface, conditions and scoring.
- [Configuration](case.toml): frozen input digests, native evaluation and source pairings.
- [Physical netlist](materials/circuit.cdl) and [simulation netlist](materials/circuit.spice): the same physical circuit and ordered interface.
- [Testbench](materials/testbench.spice): the declared external biases, loads, stimuli and observations.
- [Reference GDS](reference/ia_003_fan_chopper_pf.gds): independent physical witness.

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

Reference layout-v2 score: **33.98697121**, E = **1.2949178**,
Q = **0.089203668**. Functional area is
**824713.51 um2**; fixed compact-area anchor is
**73567.47 um2**. The device/contact/passive envelope calculation
and 50% routing allowance are published in the problem. Coefficient
**9** follows the declared capability scope there. The reference
is a feasibility witness; source measurements supply electrical normalization.
No upstream advertised performance is an implicit qualification threshold.

| Observation | Unit | Independent source range | Extracted range | Worst paired quality |
| --- | --- | ---: | ---: | ---: |
| `gain_vv` | V/V | 6.2522776 … 6.2738626 | 10.954029 … 11.35388 | 1.7520063 |
| `phase_deg` | deg | -0.17103086 … -0.16937591 | -2.8370333 … -2.3112921 | diagnostic |
| `zin_ohm` | ohm | 22614926 … 22663708 | 23634356 … 24177022 | 1.0450777 |
| `admittance_real_s` | S | 4.4121148e-08 … 4.420927e-08 | 4.1323144e-08 … 4.2224594e-08 | diagnostic |
| `admittance_imag_s` | S | 4.4638684e-10 … 9.0750308e-10 | 1.7828765e-09 … 2.7071499e-09 | diagnostic |
| `dm_mean_v` | V | -4.187175e-05 … 2.833558e-05 | 0.001309692 … 0.001311196 | 0.99887371 |
| `residual_rms_v` | V | 0.0342101 … 0.0343174 | 0.068632 … 0.0751049 | 0.45693348 |
| `ripple_pp_v` | V | 0.414272 … 0.4458565 | 0.5261478 … 0.567211 | diagnostic |
| `cm_mean_v` | V | 0.5573066 … 0.5576291 | 0.05033126 … 0.05122262 | 0.70286506 |
| `cm_min_v` | V | 0.008014022 … 0.008014058 | 0.01751915 … 0.01785348 | diagnostic |
| `cm_max_v` | V | 1.188255 … 1.1883 | 0.1529732 … 0.1644548 | diagnostic |
| `window_change_v` | V | 0.00021662788 … 0.00031548494 | 3.4847701e-09 … 1.7308256e-08 | 213.92521 |
| `modulation_error_rms_v` | V | 0.000166605 … 0.000166859 | 0.00017552 … 0.000175742 | diagnostic |
| `feedback_error_rms_v` | V | 0.000446435 … 0.000459462 | 0.000777055 … 0.000842549 | diagnostic |
| `power_w` | W | 0.0001587785 … 0.0001587801 | 0.0001646517 … 0.0001646559 | 0.96430495 |
| `clock_power_w` | W | 1.782276e-10 … 1.78367e-10 | 3.431913e-10 … 3.433088e-10 | 0.52054319 |
| `pf_error_rms_v` | V | 0.000446596 … 0.000459615 | 0.000779741 … 0.000845237 | diagnostic |
| `boundary_error_s` | s | 1.3877788e-17 | 1.3877788e-17 | diagnostic; testbench aborts above 1 ps |

Ranges summarize all declared conditions, not interchangeable endpoints for
computing ratios. Reports retain the individual paired observations and score. Invalid endpoint
alignment aborts both source and candidate simulation with an evaluator error;
it never becomes a functional rejection of the layout.

Magic extracts nominal interconnect R/C from the submitted GDS. Physical MOS,
MIM and high-poly model cards remain in the candidate netlist. Its body boundary
connects wells/substrate to tap rails; source simulation retains finite tap models.
Native LVS verifies the explicit tap dimensions and connectivity, and independent
graph checks compare MOS/passive parameters and connections after contracting only
wire resistance and the diagnostic tap boundary. Compact-core comparison checks
MOS W/L/m and physical passive dimensions. Layout-derived MOS junction areas and
perimeters remain in the extracted simulation. This scope is not foundry signoff,
PVT, mismatch, noise, RF extraction or a complete product specification.

The physical input branches are 16.0021862 pF each, feedback branches
0.7999488 pF each, and compensation branches 1.00026255 pF each by the
nominal MIM area/perimeter formula. The PF case adds two more 0.7999488 pF
branches. Each bias return is 9.999930435 Mohm by the nominal high-poly
formula. All source pairings use these same physical primitives.

The reported gain and impedance are finite-window fundamental magnitudes from
20–40 ms at 100/200 Hz with 5 kHz clocks. They are not static AC, PAC/PNoise or
proof of a settled periodic orbit. The source's no-CMFB core can exhibit slow
rail-to-rail common-mode cycling; the published window-change metric exposes
variation rather than calling it settled ripple. Residual RMS includes all
nonfundamental content; output peak-to-peak includes the signal. Unloaded monitor
ports expose input/feedback/output switching nodes and the positive-feedback
nodes when present. Raw adaptive-grid waveforms are independently integrated;
there is no FFT resampling or hidden aliasing assumption. Full-precision
cumulative integrals avoid subtracting rounded `.meas` averages. Their 20/30/40 ms
endpoint error is checked against 1 ps. The 1 uV normalization scale is an additive
offset that regularizes near-zero residual/window variation; displayed score
digits are not a claim of measurement accuracy. Native extraction can reorder
mesh terminal labels and vary the last digits of fitted R/C between runs.

## Reproduce

Run from a Public checkout after the [shared tools setup](../../../../../docs/tools.md).
These commands generate fresh local output directories; they are not repository
inputs. Reuse a compatible ngspice 45 image or build the documented overlay.

```bash
uv run --locked python -m benchmarking.engine.preview prepare \
  --case ihp-sg13g2.analog-db.ia_003_fan_chopper_pf --image iclayout-bench-tools:ngspice45 \
  --output build/runs/ia_003_fan_chopper_pf-prepared
uv run --locked python -m benchmarking.engine.preview run \
  --prepared build/runs/ia_003_fan_chopper_pf-prepared \
  --output build/runs/ia_003_fan_chopper_pf-reference
uv run --locked pytest -m unit tests/unit/test_catalogs.py \
  tests/unit/test_evaluate.py tests/unit/test_scoring.py
```

The independent authoring repository provides optional regeneration and waveform
and compact-graph audit commands in its case README; it is not needed by any
command above. Reports and raw data are regenerated under the requested output.

## Numerical and Interconnect Controls

At 100 Hz, contracting only primitive interconnect resistance in a diagnostic
copy restores large source-like common-mode cycling, with mean 0.5408735 V,
gain 6.0869398 V/V and input impedance 21.884250 Mohm. Physical devices and
parasitic capacitances remain. This supports interconnect sensitivity of the
no-CMFB operating state; it is not a replacement qualification circuit. The full
RC reference retains its low common mode and all performance consequences.

A 200-to-100 ns maximum-step control on the candidate RC at 100 Hz changes gain by
less than 0.002%, impedance by less than 0.019% and residual RMS by less
than 0.003%. Clock power changes by less than 0.6%. Near-zero window
variation is interpreted with the declared 1 uV additive normalization scale,
not as a nanovolt accuracy claim. The authoring README provides reproducible
controls; the main commands above regenerate the complete frozen evaluation.

## Source and License

[Fixed source](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/ia_003_fan_chopper_pf):
Noorizadeh's normalized schematic capture after Fan et al. The circuit retains
its actual IHP sizing defaults, explicit parameter ties and topology. Bias ports,
physical taps/passives and diagnostic interfaces are documented adaptations.
Normalized circuit and layout derivatives retain collection [LICENSE](../../LICENSE)
and [NOTICE](../../NOTICE), including PolyForm Noncommercial 1.0.0 and Required
Notice: Copyright 2026 Danial Noori Zadeh. Independently authored measurement decks
are separately MIT; the framework license does not relicense circuit derivatives.
