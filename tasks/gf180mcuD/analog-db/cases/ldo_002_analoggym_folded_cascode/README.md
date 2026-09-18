# Folded-Cascode LDO

## Overview

Nine-MOS folded-cascode error amplifier and a PMOS pass array, with direct output feedback, series RZ/CC and the physical minimum-load bleed. The fixed GF180 6 V binding expands to 259 MOS, three 2 fF/um2 MIM units, one nulling resistor and two series bleed segments. VB1, VB2 and VREF remain external sources; the original 0 V VLP measurement marker becomes a wire.

Nominal supply 2.0 V, external reference 1.8 V, VB1=1.0 V and VB2=0.025 V; 27 C, typical GF180 models with statistical variation disabled. Native 6 V DRC requires NMOS L>=0.70 um and PMOS L>=0.55 um; only undersized lengths are increased to those physical minima. All default widths and the 250-fold 10 um pass-device multiplier are retained. R_bleed is 100 kohm inside the physical DUT and consumes Vout^2/R power; external 1/2 mA load currents are additional, not replacements. CC=2 pF and RZ=3 kohm retain their original connections. External output capacitance is 1 nF with 0.1 ohm series ESR. Evaluate no disturbance, 1-to-2 mA load pulse, and +0.1 V input pulse, plus independent DC points at nominal+0.1 V/1 mA and nominal/2 mA. Pulses start at 100 us, have 1 us edges and 100 us high width; restoration finishes at 202 us. Observe 0–400 us with 10 ns maximum step; pre-step/high/recovery windows are 80–100/180–200/380–400 us. Supply rejection is measured at 1 kHz from a 1 V AC supply input (100 samples/decade, 1 Hz–100 MHz). Ascending DC sweeps cover nominal supply to nominal+0.1 V in 10 mV increments at 1 mA and 1–2 mA load in 0.1 mA increments at nominal supply; adjustment metrics are absolute endpoint slopes. These are finite ranges, not dropout measurements. Startup ramps VDD from zero to nominal in 10 us with fixed external references and a resistive 1 mA nominal load (target voltage/1 mA); it uses the ordinary initial DC solution, no UIC or forced initial output, and observes through 400 us. Startup extrema and late-window output/ripple are diagnostics. No dropout, loop gain or phase margin is claimed. Source and candidate use identical decks and parameters; no numerical shunt is used.

Coefficient 7 covers regulation, frequency response and recovery across loads. The provenance chain distinguishes the Apache-2.0 sky130_ldo_rl netlist from the BSD-3-Clause AnalogGym sizing/testbench; the actual circuit is the pinned MacAnalog GF180 binding, not another reference implementation.

## Files

- [Schematic](materials/schematic.svg): digest-bound main-sheet overview; hierarchical device banks remain expandable in the editable source project. This presentation asset is excluded from solver inputs.

- [Task contract](problem.md), [configuration](case.toml), [physical circuit](materials/circuit.cdl), [simulation circuit](materials/circuit.spice).
- [Main observations](materials/testbench.spice) and [reference GDS](reference/ldo_002_analoggym_folded_cascode.gds).

## Reference Results

Native DRC (no waivers), named-interface LVS, functional geometry and candidate-derived distributed RC all pass. Independent compact-device graph audits match source, native topology and RC devices, including every physical passive. Raw exports independently reproduce the declared measurements.

Reference score: **11.64235756**; functional area **1385144.331700 um2**, analytical area anchor **29211.12 um2**, coefficient **7**. The reference is a feasible implementation, not the electrical normalization baseline.

Ranges below cover the explicitly declared conditions of each metric; they are not substituted for condition-by-condition scoring. Startup metrics use the separate ramp/resistive-load experiment. DC regulation slopes use ascending sweeps.

| Metric | Unit | Pre-layout | Post-layout |
|---|---|---|---|
| output_v | V | 1.80081804 … 1.80113024 | 1.78105146 … 1.79136261 |
| regulation_error_v | V | 0.000818043967 … 0.00113023593 | 0.0086373864 … 0.0189485379 |
| power_w | W | 0.00261348596 … 0.00461331483 | 0.00254922278 … 0.00454895712 |
| psrr_db | dB | 53.00476 … 95.06447 | 55.31568 … 78.50224 |
| quiet_ripple_v | V | 5.284662e-14 … 9.903189e-14 | 1.900036e-12 … 6.332934e-12 |
| recovery_ripple_v | V | 4.32987e-14 … 1.31406e-12 | 5.364154e-12 … 6.604273e-12 |
| excursion_v | V | 9.525714e-14 … 0.001019546 | 1.781508e-11 … 0.01224588 |
| late_error_v | V | 0.000818044 … 0.001130236 | 0.008637386 … 0.01894854 |
| mean_power_w | W | 0.002613486 … 0.004613315 | 0.002549223 … 0.004548957 |
| quiet_v | V | 1.800818 … 1.80113 | 1.781051 … 1.791363 |
| high_v | V | 1.800818 … 1.80113 | 1.781051 … 1.791363 |
| recovery_v | V | 1.800818 … 1.80113 | 1.781051 … 1.791363 |
| startup_final_v | V | 1.801033 | 1.791346 |
| startup_ripple_v | V | 2.612799e-12 | 1.916911e-12 |
| startup_min_v | V | -2.6463e-40 | -1.985481e-30 |
| startup_max_v | V | 1.825731 | 1.836659 |
| line_reg_v_per_v | V/V | 0.000974421907 | 0.00066574244 |
| load_reg_ohm | ohm | 0.214749777 | 10.2445773 |
| kcl_a | A | 5.61183044e-16 … 1.28022593e-15 | 1.59529378e-11 … 1.70352168e-11 |

The reference uses 20 um VDD/VSS/VOUT buses to limit physical distribution loss. Regulation remains affected by interconnect resistance and is scored against the independently simulated physical source. Quiet, perturbed, restored and ramp-started waveforms are separate observations; no single DC or AC result establishes regulator operation. The minimum-load bleed/divider and declared external loads remain distinct. Numerical refinement and waveform audit commands are provided in the Designs development README.

Halving maximum transient step from 10 to 5 ns, tightening reltol/abstol/vntol tenfold and doubling AC samples changes the audited voltages by at most 9.812 uV (waveform extrema); late-window means change by at most 0.02364 nV. Ascending DC endpoints agree with independently initialized DC points, and late transient plateaus/recovery agree with their corresponding DC points within 5 uV. All 14 source/candidate raw waveform sets pass the independent audit.

## Reproduce

From the Bench root, use the existing environment and [tool preparation](../../../../../docs/tools.md). These commands generate disposable reports; choose fresh output directories on rerun.

```bash
uv run --locked python -m benchmarking.engine.preview prepare --case ldo_002_analoggym_folded_cascode --image iclayout-bench-tools:ngspice45 --output build/runs/ldo_002_analoggym_folded_cascode-prepared
uv run --locked python -m benchmarking.engine.cli evaluate build/runs/ldo_002_analoggym_folded_cascode-prepared/case/case.toml tasks/gf180mcuD/analog-db/cases/ldo_002_analoggym_folded_cascode/reference/ldo_002_analoggym_folded_cascode.gds --output build/runs/ldo_002_analoggym_folded_cascode-evaluation
```

The full evaluation independently executes source baselines with the same conditions. It needs neither Designs nor Private. Native DRC/LVS, distributed RC extraction, input digests and all declared observations are required; normal simulator exit alone is insufficient.

## Source and License

Derived from [MacAnalog/spicexplorer-release, fixed commit 263d0322f8900dc331536fbbe6c0e804514fc454](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/ldo_002_analoggym_folded_cascode); retain the [collection license and component terms](../../LICENSE).
