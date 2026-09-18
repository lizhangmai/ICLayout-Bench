# PMOS LDO with Feedforward Compensation

## Overview

Five-transistor error amplifier, NMOS bias diode and PMOS pass array with complete resistive feedback divider, feedforward CFF across the upper divider, and series RZ/CC across the pass stage. Seven bound MOS expand to 146 units. The 0 V VLP feedback marker becomes a wire; ideal reference and current bias remain external apparatus.

Nominal supply 1.8 V, external reference 1.05 V and 60 uA from VDD into ebias; 27 C, typical GF180 3.3 V models with statistics disabled. Rtop=5 kohm and Rbottom=35 kohm set nominal output 1.2 V. The 140-fold pass array retains 20 um width and 0.5 um length per unit. CFF=60 pF, CC=0.05 pF and RZ=1 ohm are retained. RZ uses twelve parallel native high-poly units (L=1 um, W=97.21 um), nominal 1.000096 ohm at 27 C, to avoid an impossible sub-grid resistor length. No compensation is deleted. External reference-generation and current-source implementation losses are excluded; the 60 uA drawn from VDD and physical divider are included in rail power. External output capacitance is 1 nF with 0.1 ohm series ESR. Evaluate no disturbance, 1-to-2 mA load pulse, and +0.1 V input pulse, plus independent DC points at nominal+0.1 V/1 mA and nominal/2 mA. Pulses start at 100 us, have 1 us edges and 100 us high width; restoration finishes at 202 us. Observe 0–400 us with 10 ns maximum step; pre-step/high/recovery windows are 80–100/180–200/380–400 us. Supply rejection is measured at 1 kHz from a 1 V AC supply input (100 samples/decade, 1 Hz–100 MHz). Ascending DC sweeps cover nominal supply to nominal+0.1 V in 10 mV increments at 1 mA and 1–2 mA load in 0.1 mA increments at nominal supply; adjustment metrics are absolute endpoint slopes. These are finite ranges, not dropout measurements. Startup ramps VDD from zero to nominal in 10 us with fixed external references and a resistive 1 mA nominal load (target voltage/1 mA); it uses the ordinary initial DC solution, no UIC or forced initial output, and observes through 400 us. Startup extrema and late-window output/ripple are diagnostics. No dropout, loop gain or phase margin is claimed. Source and candidate use identical decks and parameters; no numerical shunt is used.

Coefficient 7 covers regulation, frequency response and recovery across loads. No on-chip reference/bias generator is claimed. No loop-gain measurement is used, so CFF cannot bypass a purported loop break. The native resistor model includes terminal resistance in both source and candidate.

## Files

- [Schematic](materials/schematic.svg): digest-bound main-sheet overview; hierarchical device banks remain expandable in the editable source project. This presentation asset is excluded from solver inputs.

- [Task contract](problem.md), [configuration](case.toml), [physical circuit](materials/circuit.cdl), [simulation circuit](materials/circuit.spice).
- [Main observations](materials/testbench.spice) and [reference GDS](reference/ldo_007_pmos.gds).

## Reference Results

Native DRC (no waivers), named-interface LVS, functional geometry and candidate-derived distributed RC all pass. Independent compact-device graph audits match source, native topology and RC devices, including every physical passive. Raw exports independently reproduce the declared measurements.

Reference score: **21.34748315**; functional area **1363213.467000 um2**, analytical area anchor **98448.9 um2**, coefficient **7**. The reference is a feasible implementation, not the electrical normalization baseline.

Ranges below cover the explicitly declared conditions of each metric; they are not substituted for condition-by-condition scoring. Startup metrics use the separate ramp/resistive-load experiment. DC regulation slopes use ascending sweeps.

| Metric | Unit | Pre-layout | Post-layout |
|---|---|---|---|
| output_v | V | 1.20052908 … 1.20116379 | 1.16424906 … 1.18390523 |
| regulation_error_v | V | 0.000529075214 … 0.00116379421 | 0.0160947726 … 0.0357509446 |
| power_w | W | 0.00206200767 … 0.00386196861 | 0.00206227585 … 0.00386223279 |
| psrr_db | dB | 69.12994 … 79.12494 | 68.05275 … 77.44029 |
| quiet_ripple_v | V | 7.41629e-14 … 8.641088e-12 | 9.473311e-12 … 1.160561e-11 |
| recovery_ripple_v | V | 6.195044e-14 … 1.048317e-11 | 6.221024e-12 … 8.382184e-12 |
| excursion_v | V | 8.138823e-12 … 0.002793266 | 3.948553e-11 … 0.01969175 |
| late_error_v | V | 0.0005290752 … 0.001163794 | 0.01609477 … 0.03575094 |
| mean_power_w | W | 0.002062008 … 0.003861969 | 0.002062276 … 0.003862233 |
| quiet_v | V | 1.200529 … 1.201164 | 1.164249 … 1.183905 |
| high_v | V | 1.200529 … 1.201164 | 1.164249 … 1.183905 |
| recovery_v | V | 1.200529 … 1.201164 | 1.164249 … 1.183905 |
| startup_final_v | V | 1.201163 | 1.184167 |
| startup_ripple_v | V | 1.089706e-11 | 6.057377e-13 |
| startup_min_v | V | 3.334193e-38 | 3.340265e-05 |
| startup_max_v | V | 1.211155 | 1.199298 |
| line_reg_v_per_v | V/V | 0.000290247731 | 0.000322270132 |
| load_reg_ohm | ohm | 0.634718996 | 19.656172 |
| kcl_a | A | 2.77555756e-17 … 2.29460548e-15 | 4.01637361e-12 … 4.36800617e-12 |

The reference uses 20 um VDD/VSS/VOUT buses to limit physical distribution loss. Regulation remains affected by interconnect resistance and is scored against the independently simulated physical source. Quiet, perturbed, restored and ramp-started waveforms are separate observations; no single DC or AC result establishes regulator operation. The minimum-load bleed/divider and declared external loads remain distinct. Numerical refinement and waveform audit commands are provided in the Designs development README.

Halving maximum transient step from 10 to 5 ns, tightening reltol/abstol/vntol tenfold and doubling AC samples changes the audited voltages by at most 14.57 uV (waveform extrema); late-window means change by at most 0.02208 nV. Ascending DC endpoints agree with independently initialized DC points, and late transient plateaus/recovery agree with their corresponding DC points within 5 uV. All 14 source/candidate raw waveform sets pass the independent audit.

## Reproduce

From the Bench root, use the existing environment and [tool preparation](../../../../../docs/tools.md). These commands generate disposable reports; choose fresh output directories on rerun.

```bash
uv run --locked python -m benchmarking.engine.preview prepare --case ldo_007_pmos --image iclayout-bench-tools:ngspice45 --output build/runs/ldo_007_pmos-prepared
uv run --locked python -m benchmarking.engine.cli evaluate build/runs/ldo_007_pmos-prepared/case/case.toml tasks/gf180mcuD/analog-db/cases/ldo_007_pmos/reference/ldo_007_pmos.gds --output build/runs/ldo_007_pmos-evaluation
```

The full evaluation independently executes source baselines with the same conditions. It needs neither Designs nor Private. Native DRC/LVS, distributed RC extraction, input digests and all declared observations are required; normal simulator exit alone is insufficient.

## Source and License

Derived from [MacAnalog/spicexplorer-release, fixed commit 263d0322f8900dc331536fbbe6c0e804514fc454](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/ldo_007_pmos); retain the [collection license and component terms](../../LICENSE).
