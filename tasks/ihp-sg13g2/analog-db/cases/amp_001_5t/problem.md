# Five-Transistor OTA Core with Bias Mirror Layout Task

## Objective

Implement the fixed six-MOS `amp_001_5t` circuit in IHP SG13G2 and submit a
self-contained GDS. The circuit consists of a five-transistor OTA core and a
sixth, diode-connected bias-reference MOS. Device dimensions are fixed.

## Inputs and Interface

`materials/circuit.cdl` is authoritative for physical LVS;
`materials/circuit.spice` is its simulator representation.
`materials/testbench.spice` defines the AC/DC measurements. Port order is
`vdd vout vinp vinn ibias vss`: supply, single-ended output, non-inverting input,
inverting input, reference-current input, and return. Supply 20 uA from `vdd`
into `ibias`; it is not an ideal voltage-bias input.

The NMOS input pair has W/L = 10/10 um; the PMOS mirror pair 10/7 um;
the NMOS tail and reference devices 3.8/1 um, all with multiplicity 1.
The CDL also declares substrate and well taps. Retain all electrical connections,
body connections, sizes and tap devices. Placement and routing are free; normal
source/drain equivalence and electrically equivalent device splitting are allowed
only when the declared LVS checks accept them. No additional common-centroid or
statistical matching requirement is scored.

## Operating Conditions

The pinned `mos_tt`/`res_typ` models run at 27 C, with VDD = 1.5 V, VSS = 0 V,
20 uA reference current, 0.8 V non-inverting input bias, and an external 10 pF
output load. The 4 GH/4 GF feedback network closes the DC loop and opens the AC
loop. It is testbench apparatus, not part of the submitted layout. AC sweeps
1 Hz to 100 MHz at 100 points per decade. The power measurement includes the
reference-current branch supplied from VDD. The 1e12 ohm numerical shunt is
part of the declared simulation setup.

## Physical Requirements

Submit top cell `amp_001_5t`, with all six named electrical ports, no unresolved
hierarchy, and at most 10 MiB. Artifact, DRC, strict named-port LVS and geometry
checks must pass. DRC uses the pinned main and extra/maximal rules without
waivers; density and antenna are outside this standalone-block scope.

The functional bounding box must fit within 120 by 70 um. Its area includes all
process device and routing drawing layers enumerated in the published runtime
constraints, including wells, taps, implants, active, poly, contacts, all routing
metals/vias and passive/device markers. Annotation text and pin-purpose shapes
are excluded from area; functional routing must use drawing layers.

The judge extracts distributed RC from the submitted GDS and simulates that
extracted DUT. Physical LVS retains explicit taps. Magic models the body
connection through its extracted network without the separate compact `ptap1`
and `ntap1` devices; source calibration records the effect of this boundary.
This task covers nominal deterministic AC/DC behavior, not statistical mismatch,
PVT, noise, distortion, transient settling, EM or manufacturing signoff.

## Electrical Requirements and Scoring

Every observation below must be finite and within its inclusive acceptance band.
Missing measurements, including a missing descending unity-gain crossing, cannot
establish success. Transfer is `V(vout)/(V(vinp)-V(vinn))`.

| Metric | Definition | Unit | Acceptance | Zero-score boundaries | Dimension |
| --- | --- | --- | --- | --- | --- |
| Low-frequency gain | 20 log10 of transfer magnitude at 1 Hz | dB | >= 30 | <= 0 | response |
| Unity-gain bandwidth | First descending 0 dB crossing | Hz | >= 1,000,000 | <= 100,000 | response |
| Phase margin | 180 degrees plus unwrapped transfer phase at that crossing | deg | 60 to 90 | <= 0 or >= 120 | response |
| Output bias | DC output voltage in the feedback configuration | V | 0.78 to 0.82 | <= 0.6 or >= 1.0 | bias |
| Bias voltage | DC reference-current input voltage | V | 0.39 to 0.44 | <= 0.2 or >= 0.6 | bias |
| Supply power | -V(vdd) times current through VDD | W | 0 to 0.000065 | < 0 or >= 0.0001 | supply |

Scoring is `S = G * (60*E + 20*H + 20*H*Q)`. `G` requires valid physical checks
and completed extraction/measurements. `E` averages response, bias and supply
attainment, taking the worst metric in each dimension; attainment is 1 within
the acceptance band and falls linearly toward each zero boundary. `H` is 1
only when every electrical requirement passes.
`Q = clip((8000 - area_um2)/(8000 - 4000), 0, 1)` uses fixed absolute area anchors.
Physical rejection scores 0; a blocking evaluator error produces no score.
The case coefficient is 4: a complete compact amplifier with bias and mirror loads.

## Tools and Submission

Use the reviewed IHP PDK/EDA resources exposed through `/protocol/resources.json`;
KLayout and Magic support layout checking and extraction, and ngspice supports
simulation. `/protocol/task.json` provides the frozen constraints and evaluation
requirements; `/protocol/harness.json` describes the active harness.
If `process-feedback.v1` is exposed, use its published helper for interim checks.
Write `/workspace/output/final.gds`, then explicitly submit it with
`python -I /protocol/submit.py`. The final judge evaluates the submitted snapshot.
