> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Externally Biased PMOS-Input Folded-Cascode OTA

## Overview

Fourteen MOS entries (17 instances after multiplicity expansion) form a PMOS-input folded-cascode OTA with a bias mirror and cascode branches. The two ideal internal voltage sources become explicit vb1/vb2 ports. Total MOS widths, lengths and multiplicities are retained; the maintained devices use single-finger geometry instead of the upstream nf settings. Source and extracted simulation both represent this maintained implementation.

VSS = 0 V; VDD = 2.7, 3.0 and 3.3 V; a 20 uA sink from ibias to VSS; VB1 = 1.2 V and VB2 = 1.95 V; external 1 pF output load. VINP has DC 1.65 V and AC +0.5 V. A 1 TH output-to-VINN inductor closes DC feedback; a 1 F coupling capacitor injects AC -0.5 V at VINN. The open-loop transfer is V(vout)/(V(vinp)-V(vinn)). These large L/C elements are external measurement apparatus. At 2.7 V the reduced headroom lowers gain and shifts the DC operating point. The case measures small-signal unity-crossing phase margin with the declared load. Startup, large-signal settling, other loads, mismatch, noise, PVT and EM are outside scope.

## Files

| File | Role |
| --- | --- |
| [problem.md](problem.md) | Complete solver-facing contract and scoring |
| [case.toml](case.toml) | Inputs, physical checks, RC extraction and three simulation conditions |
| [materials/circuit.spice](materials/circuit.spice) | Authoritative fixed circuit and source-calibration DUT |
| [materials/testbench.spice](materials/testbench.spice) | Shared source/post-layout measurement deck |
| [reference/amp_004_folded_cascode.gds](reference/amp_004_folded_cascode.gds) | Independently constructed witness, excluded from solver inputs |

## Reference Results

The reference functional area is 32514.9000 um2. It passes artifact, GF180 variant-D DRC including antenna without
waivers, strict named-port LVS, geometry, distributed RC extraction and all
21 required electrical observations. The table gives ranges over all three
declared conditions; temperature extrema and comparator transient windows are
defined in the problem. Both columns use the same maintained testbench.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `output_v` | V | 1.5926553 to 1.6500528 | 1.5929008 to 1.6504604 |
| `bias_v` | V | 1.8491195 to 2.4491195 | 1.8480297 to 2.4479529 |
| `power_w` | W | 0.00019254782 to 0.00026806229 | 0.00019214635 to 0.0002675061 |
| `gain_db` | dB | 45.95764 to 85.67452 | 46.29033 to 85.80164 |
| `bandwidth_hz` | Hz | 1516.815 to 55221.54 | 1350.202 to 47973.04 |
| `unity_hz` | Hz | 11028510 to 26921560 | 9948836 to 23986120 |
| `phase_margin` | deg | 64.479 to 88.43546 | 57.3635 to 86.13904 |

The targets require 40 dB minimum gain, 9 MHz unity bandwidth, 55-degree phase margin and a 300 uW DC budget across all three supplies. The much lower 2.7 V gain is retained in the measured scope. The coefficient is 5 for independently supplied cascode bias networks coupled through internal parasitics. Acceptance and zero-score bands are calibrated against these nominal
source/RC measurements, rather than inherited from upstream targets. The
absolute area budget is 34000 um2, verified feasible by this witness; area utility
reaches zero at 136000 um2. These frozen budgets do not depend on a submitted
layout, a changing reference-area ratio or model population. The witness is
not an area optimum. Physical area and the final evaluation score are reported
by the reproduction command below.

The extracted RC network and device geometry come from the reference GDS.
Finite substrate resistance, process/statistical corners and fabrication
signoff are outside this nominal physical/simulation boundary.

## Reproduce

From the repository root, prepare the image and shared verified bundles using
the [GF180 instructions](../../../../../docs/tools.md#gf180), then run:

```bash
python -m layout_eval.cli evaluate \
  tasks/gf180mcuD/analog-db/cases/amp_004_folded_cascode/case.toml \
  tasks/gf180mcuD/analog-db/cases/amp_004_folded_cascode/reference/amp_004_folded_cascode.gds \
  --output build/runs/analog-db-amp_004_folded_cascode-reference
```

This generates the reader's identity-bound report and raw waveforms in the
selected output directory; use a fresh directory for every execution. Reproduce
the Pre-layout column using the shared
[source-calibration recipe](../../../../../docs/tools.md#gf180-source-calibration),
with this case path and a fresh `build/runs/analog-db-amp_004_folded_cascode-source` destination.
That recipe keeps all three conditions and replaces only the extracted DUT
with the published source netlist; characterization is not a layout score.

```bash
uv run --locked --group eda pytest tests/integration/test_public_references.py \
  -k amp_004_folded_cascode
```

The catalog-driven checks evaluate the witness and reject an empty layout.
Retain collection LICENSE and NOTICE with distributions; they are outside the
three declared solver inputs. Prepared solves are not redistribution packages.

## Source and License

Derived from [MacAnalog analog-db amp_004_folded_cascode](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_004_folded_cascode), under the retained [collection license](../../LICENSE) and [notices](../../NOTICE).
