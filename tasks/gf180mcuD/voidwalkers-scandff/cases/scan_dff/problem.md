# Scan D Flip-Flop with Active-Low Reset Layout Task

## Objective

Implement `gf180mcu_voidwalkers_sc_sdffrnq_4` in GF180MCU variant D while preserving the supplied circuit, device dimensions and ordered interface. Functional data and scan selection, rising-edge storage, asynchronous active-low reset, and 50 MHz operation with 50 fF load.

## Inputs and Interface

The delivered files are `materials/circuit.spice` (authoritative circuit), `materials/testbench.spice` (stimuli and measurements), and this problem. Runtime task metadata supplies the same frozen constraints, evaluation conditions and output declaration.

Ordered subcircuit and GDS interface: `S, VDD, Q, B, CLK, A, RN, VSS`.
VDD/VSS: supply/return; A: functional data; B: scan data; S: select (0=A, 1=B); CLK: rising-edge clock; RN: active-low asynchronous reset; Q: stored output.

Preserve topology and total device width, channel length, multiplicity, resistor dimensions and body connections. Equivalent hierarchy, diffusion sharing and parallel-finger implementations are allowed when they pass connectivity and electrical checks. No source-model replacement, idealized internal device or changed device sizing is permitted. A dummy device remains part of the circuit even when its terminals are tied together.

## Operating Conditions

Use 3.3 V and 27 C, a 50 fF Q load and the same 50 MHz clock throughout (first rise 10 ns, rise/fall 0.1 ns, high time 10 ns). Select A initially; select B at 40.1 ns; return to A at 80.1 ns. A rises at 20.1 ns, falls at 60.1 ns, rises at 100.1 ns and falls at 120.1 ns. B rises at 60.1 ns. RN starts low, releases at 5.1 ns, asserts at 85.1 ns and releases at 95.1 ns. All data/reset transitions take 0.1 ns, as specified in the testbench. Simulate through 140 ns.

Use the reviewed typical primitive models with statistical variation disabled. Numerical parameters in the runtime simulation jobs supply the testbench's `parameters.spice`. Follow the delivered testbench for interpolation and detailed PWL definitions. This is a nominal compact-model task; temperature/process corners, mismatch yield, noise, RF/EM and full-chip density closure are outside its qualification scope.

## Physical Requirements

Submit a nonempty GDS with top cell `gf180mcu_voidwalkers_sc_sdffrnq_4` and at most 10485760 bytes. Its functional bounding box must not exceed 80 by 80 um. All relevant device and routing polygons contribute, including implant/well, passive markers, contacts, vias and dummy routing. The complete layer/datatype set is:

`[[5,0],[11,17],[11,39],[12,0],[13,17],[21,0],[22,0],[22,4],[24,0],[24,5],[30,0],[30,4],[31,0],[32,0],[33,0],[34,0],[34,3],[34,4],[34,5],[35,0],[36,0],[36,3],[36,4],[36,5],[37,0],[38,0],[40,0],[41,0],[42,0],[42,3],[42,4],[42,5],[46,0],[46,3],[46,4],[46,5],[49,0],[53,0],[53,3],[53,4],[53,5],[55,0],[62,0],[75,0],[80,5],[81,0],[81,3],[81,4],[81,5],[82,0],[86,17],[88,17],[96,1],[100,5],[100,7],[100,8],[108,5],[110,5],[110,11],[110,12],[110,13],[110,14],[110,15],[110,16],[111,5],[112,1],[115,5],[116,5],[117,5],[117,10],[118,5],[119,5],[122,5],[123,5],[124,5],[125,5],[127,5],[128,17],[137,5],[151,5],[152,5],[153,51],[166,5],[167,5],[173,5],[178,0],[183,0],[184,0],[185,0],[204,0],[210,0],[220,0],[226,0],[227,0],[241,0]]`.

Text and nonfunctional boundary layers 0/0 and 63/0 are excluded from area. Functional geometry may not be hidden on annotation layers. Pass the pinned GF180 D FEOL, BEOL, connectivity, off-grid and antenna checks without marker waivers. The stack is five metals with 1.1 um top metal and the 1 kOhm/square high-resistance poly option. Chip-level density and seal-ring closure are integration responsibilities outside this standalone block.

LVS checks device topology, dimensions, body connections and every named top-level pin (case insensitive). Supply and substrate/well contacts must be physical. Distinct electrical nets must not be joined by touching silicided diffusion. After validity and geometry gates, extract the submitted candidate's devices and distributed interconnect resistance and capacitance. Simulations use that extracted circuit. The substrate compact-model boundary is one equipotential bulk domain with explicit well/body contacts; this does not model a distributed silicon substrate network. Unreliable extraction, absent named ports or incomplete measurements cannot establish success.


The standard-cell functional frame has fixed height 6.35 um and width on a 0.005 um grid. Coordinates below are relative to its lower-left functional bound; global translation remains allowed. Supply rails must be continuous on metal1 and bound by LVS to the named supply.

- `VDD`: centre y = 6 um, thickness at least 0.23 um, from left + 0 um to right − 0 um.
- `VSS`: centre y = 0.35 um, thickness at least 0.23 um, from left + 0 um to right − 0 um.

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
| `low` | Q at 19, 59, 89, 99 and 139 ns; the 89 ns sample checks asynchronous reset before the next rising clock. | V | functional check | −∞ … 0.33 | — |
| `high` | Q at 39, 79 and 119 ns, exercising functional and scan data. | V | functional check | 2.97 … +∞ | — |
| `propagation_delay` | Worst paired quality over: delay_data_rise, delay_data_fall, delay_scan_rise, delay_scan_fall, delay_reset_fall. | s | minimize / ratio | 0 … +∞ | — |
| `output_transition` | Worst paired quality over: slew_data_rise, slew_data_fall, slew_scan_rise, slew_scan_fall, slew_reset_fall. | s | minimize / ratio | 0 … +∞ | — |
| `supply` | Average VDD power over 20–140 ns. | W | minimize / ratio | 0 … +∞ | 1e-12 |

Area reference: **175.5775 um2**. Complete functional bounding rectangle of the declared standard-cell reference GDS: 27.65 by 6.35 um = 175.577 um2. Reference SHA-256: ffd6654d5505bf6340acbb3061ad81fab36951badda45b3bd3a8448be0fa00ab. This footprint includes the maintained explicit taps and routing.

The capability coefficient remains **5**; it is independent of
the reference-relative task score.

### Standard-cell design guidance

Plan the device rows, power rails and signal access before routing. Represent
pull-up and pull-down connectivity as transistor-edge graphs; explore compatible
Euler trails and alternative orderings to share diffusion and reduce breaks.
Choose among legal orderings using routing length, parasitic loading and signal
access, rather than diffusion sharing alone. Preserve the fixed netlist sizes,
models and connectivity; size optimization is outside this task.

Use the task's declared row height, grid and rail geometry. Keep local routes
compact, leave signal pins accessible, and avoid consuming extra routing layers
without benefit. Check DRC and named-port LVS, then extract the candidate and
compare both transition directions and power with the source simulation. Iterate
on measured parasitic effects rather than visual compactness alone. These are
optional techniques, not a mandated algorithm or reference placement.

Adapted from Xu et al., *Standard Cell Library Design and Optimization Methodology
for ASAP7 PDK*, Sections 2–3 (https://arxiv.org/abs/1807.11396). Its FinFET sizing,
track counts and process-specific dimensions do not apply to this task.

## Tools and Submission

Solve budget: **3 hours**.

Use runtime task, resource and harness discovery to locate the delivered inputs and reviewed GF180 resources. Trusted feedback runs the declared physical and post-layout evaluation; source-only simulation is useful for design but is not acceptance. Write the final GDS to `/workspace/output/final.gds` and explicitly submit it using the harness submission interface. A generated file or successful standalone simulation alone does not complete the task.

Use a GDS database unit of 0.001 um, as required by the GF180MCU DRC deck.
