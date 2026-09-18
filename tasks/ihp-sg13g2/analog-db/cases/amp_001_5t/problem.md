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

Physical checks and declared functional bounds remain mandatory. Quality has no
fixed allowed-degradation threshold. Each `source_*` job simulates the declared
source circuit with exactly the same testbench, model resources, parameters,
load and measurement window as its paired extracted-candidate job. A source
observation is the 100-point electrical baseline; it is independent of the
submitted GDS. All individual pairs are retained in the evaluation report.

For a post-layout observation x and its source observation b:

- Maximize: q = x/b; minimize: q = b/x. When a numerical scale s is declared,
  use (x+s)/(b+s) or its inverse. This handles zero-valued error measurements;
  s is a normalization floor, not an allowed degradation or pass threshold.
- Amplitude dB: q = 10^((x-b)/20) for maximize, its inverse for minimize.
- Target: q = 1/(1+abs(x-b)/s), with a declared physical scale s. Signed and
  zero-valued operating points are never divided directly.

A metric uses its worst paired q. Each response/bias/supply dimension takes the
geometric mean of its scored metrics; E is the geometric mean of applicable
dimensions. Q = area_reference / candidate_functional_area. The overall score is
S = 100 * sqrt(E * Q). The baseline is 100, not a ceiling; directional and area
improvements can earn more than 100. Failed physical or functional checks score
zero; missing/invalid evaluation or source measurements produce an unknown score.
Diagnostic observations do not earn points. The runtime task plan publishes the
exact pairing, dimensions, scales and any functional bounds.

| Metric | Definition / observations | Unit | Quality rule | Functional bounds | Scale |
| --- | --- | --- | --- | --- | --- |
| `low_frequency_gain` | nominal:low_frequency_gain | dB | maximize / db20 | −∞ … +∞ | — |
| `unity_gain_bandwidth` | nominal:unity_gain_bandwidth | Hz | maximize / ratio | 0 … +∞ | — |
| `phase_margin` | nominal:phase_margin | deg | target / target | 0 … 180 | 180 |
| `output_bias` | nominal:output_bias | V | target / target | 0 … 1.5 | 1.5 |
| `bias_voltage` | nominal:bias_voltage | V | target / target | 0 … 1.5 | 1.5 |
| `supply_power` | nominal:supply_power | W | minimize / ratio | 0 … +∞ | 1e-12 |

Area reference: **1198.35 um2**. 8 expanded device instances; sum of device/contact envelopes 754.0020 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

The capability coefficient remains **4**; it is independent of
the reference-relative task score.

## Tools and Submission

Solve budget: **3 hours**.

Use the reviewed IHP PDK/EDA resources exposed through `/protocol/resources.json`;
KLayout and Magic support layout checking and extraction, and ngspice supports
simulation. `/protocol/task.json` provides the frozen constraints and evaluation
requirements; `/protocol/harness.json` describes the active harness.
If `process-feedback.v1` is exposed, use its published helper for interim checks.
Write `/workspace/output/final.gds`, then explicitly submit it with
`python -I /protocol/submit.py`. The final judge evaluates the submitted snapshot.
