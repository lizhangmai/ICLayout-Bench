# Complementary SRAM Write Driver Layout Task

## Objective

Implement the supplied complementary tri-state write driver: WEN=1 drives BL=DIN and BR=NOT DIN; WEN=0 disables both outputs. Preserve the authoritative netlist's model classes, W/L, interface and connectivity. Submit top cell `write_driver`.

## Inputs and Interface

Ordered SPICE ports: `din bl br wen vdd gnd`. Names are case-insensitive; different names are not interchangeable. The delivered inputs are this problem, `materials/circuit.spice`, and `materials/testbench.spice`. The model and extraction resources are supplied as reviewed support bundles. Reference geometry and qualification evidence are maintainer materials, excluded from solver inputs.

## Operating Conditions

Use the nominal FreePDK45 BSIM4 models at **1.0 V and 27 C**, with ground at 0 V. All transistor lengths are 50 nm; widths and model classes come from the netlist.

BL and BR each drive 10 fF and a 100 kohm resistor to 0.5 V. DIN starts low, rises at 500 ps and falls at 1 ns, with 10 ps edges and a 1 ns period. WEN is high until 2 ns and falls over 10 ps. Sample the enabled complementary outputs at 300 ps and 710 ps, and both disabled outputs at 11.9 ns. The passive midpoint loads test high impedance without accessing internal nodes. Average DUT supply power over 0–2 ns.

The deck defines stimuli and observation times exactly. Tests use only external ports. Qualification covers these nominal conditions, not PVT, mismatch, array abutment, substrate noise or manufacturing signoff.

## Physical Requirements

Submit a nonempty GDSII of at most 10 MiB. Enable all checks present in the supplied KLayout DRC deck, including grid and antenna checks, with no waivers. Strict LVS checks named ports, models, W/L and actual well/tap connectivity; library-specific implicit or global rail connections are disabled. The upstream deck does not implement its documented different-potential well-spacing rule; it is not a complete foundry signoff deck.

The hard functional envelope is 100 um by 100 um. Its bounding rectangle includes every drawing layer 1/0 through 29/0: active, wells, implants, threshold markers, poly, contacts, all ten metals and all nine vias. It supplies the scored footprint in um2. Put functional geometry on these layers; pin-purpose and annotation geometry is excluded. Electrical labels use poly or metal drawing layers (9/0 and 11/0, 13/0, ..., 29/0). Non-electrical annotation text is ignored by extraction.

Translation, equivalent hierarchy and internal instance renaming are allowed. LVS permits source/drain exchange and equivalent parallel devices; any such layout must also pass the same RC-based electrical requirements. Preserve top-level port identities and explicit body connections.

## Electrical Requirements and Scoring

Artifact, DRC, LVS and geometry gates precede candidate GDS extraction. Simulation consumes the candidate's Magic RC netlist unchanged; source simulation supplies the independent scoring baseline. VTG/VTL device classes are checked by independent LVS before the matching extraction profile is used. Extraction includes poly/metal sheet resistance, contacts/vias, geometry-dependent coupling and ground capacitance, and device junction area/perimeter. Wells are lumped connections; BSIM4 supplies device/junction behavior. Interconnect resistance and capacitance use the pinned community FreePDK45 Magic technology's estimated coefficients and native capacitance placement. The extraction adapter binds VTG/VTL models, preserves annotation layers and corrects the technology's dimensional unit conversion. This is a predictive approximation without field-solver signoff accuracy.

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
| `bl_low` | `find v(bl) at=300p` | V | functional check | −∞ … 0.1 | — |
| `br_high` | `find v(br) at=300p` | V | functional check | 0.9 … +∞ | — |
| `bl_high` | `find v(bl) at=710p` | V | functional check | 0.9 … +∞ | — |
| `br_low` | `find v(br) at=710p` | V | functional check | −∞ … 0.1 | — |
| `z_bl` | `find v(bl) at=11.9n` | V | functional check | 0.45 … 0.55 | — |
| `z_br` | `find v(br) at=11.9n` | V | functional check | 0.45 … 0.55 | — |
| `supply` | `avg par('-v(vdd)*i(Vdd)') from=0 to=2n` | W | minimize / ratio | 0 … +∞ | 1e-12 |

| `data_delay` | Worst paired quality over: data_delay_bl, data_delay_br. | s | minimize / ratio | 0 … +∞ | — |

Area reference: **3.36 um2**. 12 expanded device instances; sum of device/contact envelopes 1.7748 um2, per-side envelope allowance 0.12 um, 50% routing allowance and outer margin 0.24 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

The capability coefficient remains **3**; it is independent of
the reference-relative task score.

## Tools and Submission

Solve budget: **3 hours**.

Use the reviewed FreePDK45 KLayout, Magic and ngspice resources from `/protocol/resources.json`. For Magic RC extraction, use `/resources/support/magic-vtg/freepdk45.tech`, which includes the required model and unit adaptations. Runtime `/protocol/task.json` publishes the same constraints, measurements and scoring. Only declared inputs appear under `/task`. Write `/workspace/output/final.gds`, then explicitly submit with `python -I /protocol/submit.py`. A harness that declares `process-feedback.v1` uses the same frozen plan and backend identities for process checks; those snapshots do not count as final submissions.
