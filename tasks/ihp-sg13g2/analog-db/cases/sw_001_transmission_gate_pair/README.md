# Bidirectional CMOS Transmission Gate

## Overview

The fixed IHP binding has one NMOS and one PMOS, each W=2 um, L=0.13 um, m=1. Both connect the bidirectional signal terminals, with the NMOS body at vss and PMOS body at vdd. No internal clock generator is added.

Coefficient 3 covers local bidirectional analog conduction and loaded control transitions. Tracking error is integrated over exactly 20–60 ns; control-edge excursion uses the inclusive 69–75 ns sample window; held mean shift compares 90–100 ns with 65–69 ns. These are loaded feedthrough/hold observations, not an intrinsic charge-injection constant or perfect floating-node retention. No energy score is claimed: body-rail current alone cannot measure control and signal-driver energy. See the [solver contract](problem.md) for the complete operating boundary and metric definitions.

## Files

- [Schematic](materials/schematic.svg): digest-bound circuit drawing, excluded from solver inputs.

- [case.toml](case.toml): executable task, frozen inputs, toolchain, scoring and maintainer asset declarations.
- [Physical netlist](materials/circuit.cdl) and [simulator netlist](materials/circuit.spice): the same complete physical core.
- [Main fixture](materials/testbench.spice): independent paired source/candidate measurements; other decks are declared in the configuration.
- [Reference GDS](reference/sw_001_transmission_gate_pair.gds): independently authored physical witness, excluded from solver inputs.

## Reference Results

Qualified for the declared nominal task. Native artifact, DRC, named-interface LVS, footprint and candidate GDS-derived distributed RC checks pass, with same-condition independently rerun source baselines. Compact-device graph audits match source, topology-only extraction and full RC, including parameters, physical passive units and ordered ports. Every scored measurement was independently recomputed from raw waveforms.

Reference layout-v2 score: **34.88171099**. Functional area: **1901.76 um²**. The [problem](problem.md) defines the independent area estimate (300 um²) and coefficient (3). Qualification means a valid measurement/scoring chain; it does not certify upstream product specifications.

Ranges below are minima/maxima across declared conditions, not paired ratios.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `ron_ohm` | ohm | 292.54542 / 1082.6849 | 388.28214 / 1140.3263 |
| `on_current_a` | A | 9.2362979e-06 / 3.4182726e-05 | 8.7694196e-06 / 2.5754468e-05 |
| `leakage_a` | A | 3.1587305e-13 / 5.5810698e-12 | 3.1585845e-13 / 5.5810634e-12 |
| `kcl_a` | A | 5.4673975e-19 / 3.2526461e-18 | 9.3642055e-18 / 2.7739491e-16 |
| `tracking_error_v` | V | 1.70384e-09 / 0.0060395764 | 1.7797887e-09 / 0.0064199319 |
| `feedthrough_v` | V | 0.00034842133 / 0.0010229044 | 0.0003496978 / 0.0025350915 |
| `hold_shift_v` | V | -0.00099854892 / 0.001471475 | -0.0024752619 / 0.002762125 |

Both directions are measured at 0.15, 0.75 and 1.35 V common mode with a nonzero 10 mV port difference; every reported on-resistance requires current above 1 nA and the correct conductive sign. Off leakage is a nominal model observation (maximum approximately 5.58 pA), not a silicon leakage guarantee. Dynamic transmission, hold displacement and control feedthrough use 100 ohm input resistance, 1 pF receiving load and a physical 1 Mohm return to the common-mode source. Complementary external controls have 1 ns edges and no additional dead time.

Feedthrough includes both edges of the declared 69–75 ns window; explicit breakpoints and raw endpoint-inclusive extrema prevent sampling or floating-point endpoint exclusion. Hold averages use endpoint-interpolated integrals. Signal/control source energy is not scored, and body-rail current is not presented as total switch energy. Idealizing only the source body-tap boundary changes dynamic voltages by less than 16 nV and on-resistance by less than 1.9e-7 ohm.

Halving transient time steps, doubling AC frequency density and tightening solver tolerances tenfold for both source and candidate changes the independently recomputed score by 0.000206991 points. The area remains fixed during this check. No rshunt or added DUT servo is used.

The declared 0–1.5 V signal/control envelope uses the SG13G2 LV nominal supply (see the [IHP process description](https://www.ihp-microelectronics.com/fileadmin/images/mediathek/annual_reports/annualreport_ihp_2024.pdf)). This is a nominal simulation boundary, not an absolute-maximum or reliability qualification.

## Reproduce

From the Bench repository root, reuse a compatible ngspice 45 / Magic 8.3.678 / KLayout 0.30.11 tools image or follow the [tools guide](../../../../../docs/tools.md#image-development). These commands create disposable prepared bundles and evidence under the specified fresh directories:

```bash
uv run --locked python -m benchmarking.engine.preview prepare \
  --case sw_001_transmission_gate_pair --image iclayout-bench-tools:ngspice45 \
  --output build/runs/sw_001_transmission_gate_pair/prepared
uv run --locked python -m benchmarking.engine.preview run \
  --prepared build/runs/sw_001_transmission_gate_pair/prepared \
  --output build/runs/sw_001_transmission_gate_pair/reference
```

Normal evaluation consumes only this static delivery and prepared PDK resources; it requires neither Designs nor Private source. Development recipes and independent raw-waveform, binding and numerical audits belong to the separate ICLayout-Designs repository. Prepared configuration, resource digests, candidate identity, raw waveforms and measurements are recorded in each generated report.

## Source and License

Derived from [MacAnalog/spicexplorer-release, `sw_001_transmission_gate_pair`](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/sw_001_transmission_gate_pair) at commit `263d0322f8900dc331536fbbe6c0e804514fc454`; retain the collection [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE). Required Notice: Copyright 2026 Danial Noori Zadeh. Circuit derivatives and witnesses retain applicable upstream terms; independently authored measurement decks are MIT.
