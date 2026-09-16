> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Resistive-Feedback Hysteretic Comparator

## Overview

A differential input stage, resistive positive feedback and three output inverters form a hysteretic comparator. Twelve MOS entries expand to 28 physical instances. The physical ppolyf_u_1k resistors are width 2 um: two 600 um feedback devices (300 squares) and one 12 um tail device (6 squares). MOS sizes and multiplicities are retained; ideal resistors become substrate-connected process devices.

VDD = 3.3 V, VSS = 0 V, VINN = 1.65 V. VINP stays at 1.45 V through 0.1 ms, ramps to 1.85 V at 1.1 ms, holds through 1.2 ms, ramps back to 1.45 V at 2.2 ms, then holds through 2.3 ms. Each ramp magnitude is 0.4 V/ms. Evaluate external loads of 1, 5 and 10 pF separately with a 0.2 us transient output step. The transient starts from its DC operating point. Thresholds include this finite ramp rate and output load. Offset is intentional and is not zero-centered about VINN. Metastability, fast decision delay, startup, noise, statistical offset, PVT and EM are outside scope.

## Files

| File | Role |
| --- | --- |
| [problem.md](problem.md) | Complete solver-facing contract and scoring |
| [case.toml](case.toml) | Inputs, physical checks, RC extraction and three simulation conditions |
| [materials/circuit.spice](materials/circuit.spice) | Authoritative fixed circuit and source-calibration DUT |
| [materials/testbench.spice](materials/testbench.spice) | Shared source/post-layout measurement deck |
| [reference/cmp_001_hyst_diffpair.gds](reference/cmp_001_hyst_diffpair.gds) | Independently constructed witness, excluded from solver inputs |

## Reference Results

The reference functional area is 60543.6549 um2. It passes artifact, GF180 variant-D DRC including antenna without
waivers, strict named-port LVS, geometry, distributed RC extraction and all
18 required electrical observations. The table gives ranges over all three
declared conditions; temperature extrema and comparator transient windows are
defined in the problem. Both columns use the same maintained testbench.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `rising_input` | V | 1.694373 to 1.694397 | 1.693921 to 1.693936 |
| `falling_input` | V | 1.681959 to 1.682001 | 1.680888 to 1.680902 |
| `hysteresis_v` | V | 0.012372 to 0.012438 | 0.013033 to 0.013046 |
| `mean_power_w` | W | 0.0005595666 to 0.0005599238 | 0.0005542839 to 0.0005544049 |
| `low_v` | V | 2.869148e-09 to 2.86915e-09 | 5.468602e-05 |
| `high_v` | V | 3.3 | 3.298868 |

The targets require an 8–20 mV hysteresis window, explicit threshold bands, near-rail settled output and a 650 uW average power budget under all three loads. Thresholds are finite-ramp measurements. The coefficient is 5 for regenerative feedback and a multi-stage output path. Acceptance and zero-score bands are calibrated against these nominal
source/RC measurements, rather than inherited from upstream targets. The
absolute area budget is 65000 um2, verified feasible by this witness; area utility
reaches zero at 260000 um2. These frozen budgets do not depend on a submitted
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
  tasks/gf180mcuD/analog-db/cases/cmp_001_hyst_diffpair/case.toml \
  tasks/gf180mcuD/analog-db/cases/cmp_001_hyst_diffpair/reference/cmp_001_hyst_diffpair.gds \
  --output build/runs/analog-db-cmp_001_hyst_diffpair-reference
```

This generates the reader's identity-bound report and raw waveforms in the
selected output directory; use a fresh directory for every execution. Reproduce
the Pre-layout column using the shared
[source-calibration recipe](../../../../../docs/tools.md#gf180-source-calibration),
with this case path and a fresh `build/runs/analog-db-cmp_001_hyst_diffpair-source` destination.
That recipe keeps all three conditions and replaces only the extracted DUT
with the published source netlist; characterization is not a layout score.

```bash
uv run --locked --group eda pytest tests/integration/test_public_references.py \
  -k cmp_001_hyst_diffpair
```

The catalog-driven checks evaluate the witness and reject an empty layout.
Retain collection LICENSE and NOTICE with distributions; they are outside the
three declared solver inputs. Prepared solves are not redistribution packages.

## Source and License

Derived from [MacAnalog analog-db cmp_001_hyst_diffpair](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/cmp_001_hyst_diffpair), under the retained [collection license](../../LICENSE) and [notices](../../NOTICE).
