# Fan Clocked Capacitive Instrumentation Amplifier

## Overview

All 39 MOS and the input, feedback and output choppers operate under real clocks. The upstream 16/0.8 pF input/feedback ratio and 1 pF compensation are retained as physical MIM, with 10 Mohm bias returns implemented by forty high-poly segments per arm. No CMFB is added. Each circuit uses its own pinned transistor dimensions and biases; there is no runtime dependency on either OTA case.

## Files

- [Schematic](materials/schematic.svg): digest-bound main-sheet overview; hierarchical device banks remain expandable in the editable source project. This presentation asset is excluded from solver inputs.

- [Problem](problem.md): complete solver-facing interface, conditions and scoring.
- [Configuration](case.toml): frozen input digests, native evaluation and source pairings.
- [Physical netlist](materials/circuit.cdl) and [simulation netlist](materials/circuit.spice): the same physical circuit and ordered interface.
- [Testbench](materials/testbench.spice): the declared external biases, loads, stimuli and observations.
- [Reference GDS](reference/ia_002_fan_chopper_simple.gds): independent physical witness.

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

Reference layout-v2 score: **37.05793966**, E = **1.3883997**,
Q = **0.098911784**. Functional area is
**721546.18 um2**; fixed compact-area anchor is
**71369.42 um2**. The device/contact/passive envelope calculation
and 50% routing allowance are published in the problem. Coefficient
**8** follows the declared capability scope there. The reference
is a feasibility witness; source measurements supply electrical normalization.
No upstream advertised performance is an implicit qualification threshold.

| Observation | Unit | Independent source range | Extracted range | Worst paired quality |
| --- | --- | ---: | ---: | ---: |
| `gain_vv` | V/V | 6.2505554 … 6.2688031 | 6.0290305 … 6.0539511 | 0.96175146 |
| `phase_deg` | deg | -0.16081449 … -0.11283304 | 0.38515535 … 0.69956186 | diagnostic |
| `zin_ohm` | ohm | 12833155 … 12856835 | 13140627 … 13168458 | 1.0220733 |
| `admittance_real_s` | S | 7.765244e-08 … 7.7857674e-08 | 7.5908376e-08 … 7.5977674e-08 | diagnostic |
| `admittance_imag_s` | S | 3.1939698e-09 … 4.4464515e-09 | 2.1576587e-09 … 4.3107989e-09 | diagnostic |
| `dm_mean_v` | V | -7.533662e-06 … 1.054001e-05 | -0.0001081887 … -6.099589e-05 | 0.99991613 |
| `residual_rms_v` | V | 0.034436 … 0.0345688 | 0.0135253 … 0.0137448 | 2.5149355 |
| `ripple_pp_v` | V | 0.3986781 … 0.4337837 | 0.2286549 … 0.2335923 | diagnostic |
| `cm_mean_v` | V | 0.558029 … 0.5583273 | 0.03194777 … 0.03199363 | 0.69511475 |
| `cm_min_v` | V | 0.008013651 … 0.008013652 | 0.01720333 … 0.01732348 | diagnostic |
| `cm_max_v` | V | 1.188266 … 1.188307 | 0.07084184 … 0.07151586 | diagnostic |
| `window_change_v` | V | 0.00018193158 … 0.00020191518 | 3.3347661e-09 … 8.4312267e-09 | 182.32357 |
| `modulation_error_rms_v` | V | 0.000457135 … 0.000458237 | 0.000378147 … 0.000378993 | diagnostic |
| `feedback_error_rms_v` | V | 0.000549125 … 0.000555456 | 0.000326478 … 0.000327654 | diagnostic |
| `power_w` | W | 0.0001587791 … 0.0001587817 | 0.000165738 … 0.0001657381 | 0.95801207 |
| `clock_power_w` | W | 1.02114e-10 … 1.021779e-10 | 2.025068e-10 … 2.025885e-10 | 0.50668577 |
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
  --case ihp-sg13g2.analog-db.ia_002_fan_chopper_simple --image iclayout-bench-tools:ngspice45 \
  --output build/runs/ia_002_fan_chopper_simple-prepared
uv run --locked python -m benchmarking.engine.preview run \
  --prepared build/runs/ia_002_fan_chopper_simple-prepared \
  --output build/runs/ia_002_fan_chopper_simple-reference
uv run --locked pytest -m unit tests/unit/test_catalogs.py \
  tests/unit/test_evaluate.py tests/unit/test_scoring.py
```

The independent authoring repository provides optional regeneration and waveform
and compact-graph audit commands in its case README; it is not needed by any
command above. Reports and raw data are regenerated under the requested output.

## Numerical and Interconnect Controls

At 100 Hz, contracting only primitive interconnect resistance in a diagnostic
copy restores large source-like common-mode cycling, with mean 0.5332636 V,
gain 6.3084123 V/V and input impedance 12.384808 Mohm. Physical devices and
parasitic capacitances remain. This supports interconnect sensitivity of the
no-CMFB operating state; it is not a replacement qualification circuit. The full
RC reference retains its low common mode and all performance consequences.

A 200-to-100 ns maximum-step control on the source at 100 Hz changes gain by
less than 0.003%, impedance by less than 0.010% and residual RMS by less
than 0.007%. Clock power changes by less than 0.6%. Near-zero window
variation is interpreted with the declared 1 uV additive normalization scale,
not as a nanovolt accuracy claim. The authoring README provides reproducible
controls; the main commands above regenerate the complete frozen evaluation.

## Source and License

[Fixed source](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/ia_002_fan_chopper_simple):
Noorizadeh's normalized schematic capture after Fan et al. The circuit retains
its actual IHP sizing defaults, explicit parameter ties and topology. Bias ports,
physical taps/passives and diagnostic interfaces are documented adaptations.
Normalized circuit and layout derivatives retain collection [LICENSE](../../LICENSE)
and [NOTICE](../../NOTICE), including PolyForm Noncommercial 1.0.0 and Required
Notice: Copyright 2026 Danial Noori Zadeh. Independently authored measurement decks
are separately MIT; the framework license does not relicense circuit derivatives.
