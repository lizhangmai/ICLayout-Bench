# Dynamic Comparator Layout Task

## Objective

Implement `comp_20240331` in GF180MCU variant D while preserving the supplied circuit, device dimensions and ordered interface. Clocked differential decisions for both signs of a 20 mV input difference at 1.65 V common mode, 50 MHz and 50 fF per output.

## Inputs and Interface

The delivered files are `materials/circuit.spice` (authoritative circuit), `materials/testbench.spice` (stimuli and measurements), and this problem. Runtime task metadata supplies the same frozen constraints, evaluation conditions and output declaration.

Ordered subcircuit and GDS interface: `VDD, CLK, VOUTP, VOUTN, VINP, VINN, VSS`.
VDD/VSS: supply/return; CLK: clock; VINP/VINN: differential inputs; VOUTP/VOUTN: directional differential outputs.

Preserve topology and total device width, channel length, multiplicity, resistor dimensions and body connections. Equivalent hierarchy, diffusion sharing and parallel-finger implementations are allowed when they pass connectivity and electrical checks. No source-model replacement, idealized internal device or changed device sizing is permitted. A dummy device remains part of the circuit even when its terminals are tied together.

## Operating Conditions

Use 3.3 V and 27 C. The clock begins rising at 10 ns and repeats every 20 ns, with 0.1 ns rise/fall and 10 ns high time. Each output has 50 fF to ground. Evaluate polarity = -1 and +1 separately: VINP = 1.65 + polarity*0.01 V and VINN = 1.65 - polarity*0.01 V. Simulate to 100 ns with a 0.01 ns requested step.

Use the reviewed typical primitive models with statistical variation disabled. Numerical parameters in the runtime simulation jobs supply the testbench's `parameters.spice`. Follow the delivered testbench for interpolation and detailed PWL definitions. This is a nominal compact-model task; temperature/process corners, mismatch yield, noise, RF/EM and full-chip density closure are outside its qualification scope.

## Physical Requirements

Submit a nonempty GDS with top cell `comp_20240331` and at most 10485760 bytes. Its functional bounding box must not exceed 200 by 100 um. All relevant device and routing polygons contribute, including implant/well, passive markers, contacts, vias and dummy routing. The complete layer/datatype set is:

`[[5,0],[11,17],[11,39],[12,0],[13,17],[21,0],[22,0],[22,4],[24,0],[24,5],[30,0],[30,4],[31,0],[32,0],[33,0],[34,0],[34,3],[34,4],[34,5],[35,0],[36,0],[36,3],[36,4],[36,5],[37,0],[38,0],[40,0],[41,0],[42,0],[42,3],[42,4],[42,5],[46,0],[46,3],[46,4],[46,5],[49,0],[53,0],[53,3],[53,4],[53,5],[55,0],[62,0],[75,0],[80,5],[81,0],[81,3],[81,4],[81,5],[82,0],[86,17],[88,17],[96,1],[100,5],[100,7],[100,8],[108,5],[110,5],[110,11],[110,12],[110,13],[110,14],[110,15],[110,16],[111,5],[112,1],[115,5],[116,5],[117,5],[117,10],[118,5],[119,5],[122,5],[123,5],[124,5],[125,5],[127,5],[128,17],[137,5],[151,5],[152,5],[153,51],[166,5],[167,5],[173,5],[178,0],[183,0],[184,0],[185,0],[204,0],[210,0],[220,0],[226,0],[227,0],[241,0]]`.

Text and nonfunctional boundary layers 0/0 and 63/0 are excluded from area. Functional geometry may not be hidden on annotation layers. Pass the pinned GF180 D FEOL, BEOL, connectivity, off-grid and antenna checks without marker waivers. The stack is five metals with 1.1 um top metal and the 1 kOhm/square high-resistance poly option. Chip-level density and seal-ring closure are integration responsibilities outside this standalone block.

LVS checks device topology, dimensions, body connections and every named top-level pin (case insensitive). Supply and substrate/well contacts must be physical. Distinct electrical nets must not be joined by touching silicided diffusion. After validity and geometry gates, extract the submitted candidate's devices and distributed interconnect resistance and capacitance. Simulations use that extracted circuit. The substrate compact-model boundary is one equipotential bulk domain with explicit well/body contacts; this does not model a distributed silicon substrate network. Unreliable extraction, absent named ports or incomplete measurements cannot establish success.

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
| `decision` | polarity*(VOUTP-VOUTN) at 99 ns. | V | functional check | 2.97 … +∞ | — |
| `delay` | Final clock rising 1.65 V crossing after 80 ns to the corresponding directional output crossing 2.97 V. | s | minimize / ratio | 0 … +∞ | — |
| `supply` | Average power delivered by VDD over 20–100 ns. | W | minimize / ratio | 0 … +∞ | 1e-12 |

Area reference: **301.49 um2**. 15 expanded device instances; sum of device/contact envelopes 164.1600 um2, per-side envelope allowance 1 um, 50% routing allowance and outer margin 2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

The capability coefficient remains **6**; it is independent of
the reference-relative task score.

## Tools and Submission

Solve budget: **3 hours**.

Use runtime task, resource and harness discovery to locate the delivered inputs and reviewed GF180 resources. Trusted feedback runs the declared physical and post-layout evaluation; source-only simulation is useful for design but is not acceptance. Write the final GDS to `/workspace/output/final.gds` and explicitly submit it using the harness submission interface. A generated file or successful standalone simulation alone does not complete the task.

Use a GDS database unit of 0.001 um, as required by the GF180MCU DRC deck.
