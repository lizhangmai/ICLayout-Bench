> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Self-Starting Isolated-Body PTAT Core

## Overview

This GF180MCU D case retains the classic resistor-degenerated four-MOS core,
including its output-connected NMOS body, and adds three MOS for startup.
It qualifies nominal positive temperature slope and zero-state power-up at
specified supply ramps with a 100 fF external load. Output and slope depend
on supply; it is not a precision temperature reference or a pF-load buffer.

The independent witness uses an isolated P-well inside a supply-tied deep
N-well, an explicit N-well annulus and physical body/substrate contacts.
The annulus preserves isolation through the declared Magic RC route without
changing the PDK decks. The original four MOS W/L/m are retained. A 2 by
40 um high-resistance poly device realizes the nominal 20 kohm resistor.
A weak 0.42/20 um PMOS, 2/0.28 um NMOS detector and 0.42/1 um NMOS injector
form the added startup branch. The injection path turns off after bias is
established; the weak bias branch retains static current, included in power.
The maintained circuit therefore differs explicitly from the upstream 4T core.

## Files

| File | Role and consumer |
| --- | --- |
| [case.toml](case.toml) | Native contract, tool/resource bindings, scoring, provenance and witness digest |
| [problem.md](problem.md) | Complete solver-facing requirements; description input |
| [materials/circuit.cdl](materials/circuit.cdl) | Physical LVS authority; netlist input |
| [materials/circuit.spice](materials/circuit.spice) | Equivalent four-terminal simulator circuit; simulation input |
| [materials/testbench.spice](materials/testbench.spice) | Temperature and zero-state startup measurements; performance input |
| [reference/tsn_002_ptat_classic.gds](reference/tsn_002_ptat_classic.gds) | Independent ready-to-use physical witness; maintainer asset |

The physical isolated NMOS is `MM0 ... nfet_03v3_dn`; its simulator call is
`XM0 ... nfet_03v3`. D/G/S/B and W/L/m agree, and source/body both remain on
`vout`. Other devices have the same calls in both representations. This model
mapping is why a separate simulation input is required. References, host
configuration, source records and this README are excluded from solver inputs.
Collection LICENSE and NOTICE accompany material distributions separately.

[Analog Canvas schematic](materials/schematic.svg) is a maintainer-only result
browsing asset, excluded from solver inputs. Same-name labels denote connected
nets; repeated-device banks retain individual instances in editable child sheets.
SVG metadata binds the source digest and records authoring/verification limitations.
The schematic depicts the authoritative netlist; the current layout requirements
and evaluation settings are declared in the task.

## Reference Results

GF180 resources come from the pinned ciel prebuilt distribution, including its
current KLayout rules, nominal models and variant-D Magic extraction.
The reference uses a 0.001 um GDS database unit; dummy COMP fill is included
where required by the rule deck.
See [resource preparation](../../../../../docs/tools.md) and the process manifest
for source pins, scope and reproducible preparation.

The declared reference passes artifact, DRC, LVS, hard geometry, candidate-derived
extraction and the functional checks in the current case plan. Conditions, model
boundaries, measurement windows and normalization rules are specified in
[problem.md](problem.md). Both simulation paths use the same declared testbenches
and trusted resources. The source circuit supplies the electrical baseline;
the reference GDS demonstrates an executable layout, not an optimal solution.

Measured `layout-v2` score: **20.063736**, with electrical quality
**E = 1.000969** and area quality **Q = 0.040216378**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **13157.0774 um2**.

Area reference: **529.13 um2**. 8 expanded device instances; sum of device/contact envelopes 303.6200 um2, per-side envelope allowance 1 um, 50% routing allowance and outer margin 2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `output_v` | V | 0.1166461 … 0.17262961 | 0.11657682 … 0.17239562 | 0.99992889 |
| `power_w` | W | 3.240497e-05 … 6.4031417e-05 | 3.2308093e-05 … 6.3773834e-05 | 1.0028102 |
| `cold_v` | V | 0.1166461 … 0.1201363 | 0.1165768 … 0.1200731 | 0.999979 |
| `hot_v` | V | 0.1678079 … 0.1726296 | 0.1675734 … 0.1723956 | 0.99992888 |
| `slope_v_per_c` | V/C | 0.00042634833 … 0.00043744417 | 0.00042497167 … 0.00043602083 | 0.99698077 |
| `curvature_v` | V | 0.001773968 … 0.001860855 | 0.001761301 … 0.001847731 | 1.0070989 |
| `minimum_slope` | V/C | 0.0003694495 … 0.0003778229 | 0.000368479 … 0.0003767974 | 0.99813892 |
| `maximum_slope` | V/C | 0.0004842871 … 0.0004983875 | 0.000482488 … 0.0004965252 | 0.99662543 |
| `peak_power_w` | W | 4.945078e-05 … 6.403142e-05 | 4.924548e-05 … 6.377383e-05 | 1.0040391 |
| `startup_error_v` | V | 5.107026e-15 … 1.783912e-08 | 3.249415e-12 … 7.470911e-09 | 0.99966659 |
| `ripple_v` | V | 0 | 0 | 1 |
| `final_power_w` | W | 3.240497e-05 … 6.403142e-05 | 3.230809e-05 … 6.377383e-05 | 1.0028103 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

The coefficient is 6 for coupled startup/temperature
behavior and isolated-body layout.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case gf180mcuD.analog-db.tsn_002_ptat_classic --image iclayout-bench-tools:local \
  --output build/runs/tsn_002_ptat_classic-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/tsn_002_ptat_classic-prepared \
  --output build/runs/tsn_002_ptat_classic-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'tsn_002_ptat_classic'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [MacAnalog analog-db tsn_002_ptat_classic](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/tsn_002_ptat_classic).
The normalized derivative and witness retain the [collection license](../../LICENSE)
and [notices](../../NOTICE), including PolyForm Noncommercial and applicable
CODA-Team BSD attribution. The independent measurement deck is MIT. Manifest
license labels do not relicense the normalized materials as a whole.
