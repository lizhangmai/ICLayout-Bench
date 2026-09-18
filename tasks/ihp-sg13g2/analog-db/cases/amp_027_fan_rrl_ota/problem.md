# Fan Telescopic OTA Layout Task

## Objective

Implement the supplied 16-MOS telescopic OTA with its transistor DDA-CMFB. Preserve all devices, connections and dimensions. This task contains only the OTA core.

## Inputs and Interface

- `problem.md`: description input.
- `materials/circuit.cdl`: netlist input.
- `materials/circuit.spice`: simulation input.
- `materials/testbench.spice`: performance input.

Ordered ports: `vinp vinn voutp voutn vdd vss vb1 vb2 vb3 vb4`. Preserve these named connections.

The native CDL and simulator SPICE describe the same circuit. VINP/VINN are
the differential inputs; VOUTP/VOUTN are outputs; VDD/VSS are supply/return;
VB1 through VB4 are bias ports. Independent bias sources are outside the physical core. Physical well/substrate taps are included.

## Operating Conditions

TT, 27 C, VDD=1.2 V, input common mode 0.6 V; vb1/vb2/vb3/vb4=0.45/0.75/0.55/0.6 V. Loads are 1 and 10 pF per output. Differential steps are ±20 uV at 10 us, returning at 40.02 us; 5 uA per output common-mode injection runs from 60 to 61.02 us. Maximum transient step is 2 ns, duration 100 us. This is an open-loop signal test with the internal CMFB operating.

## Physical Requirements

Submit a nonempty GDSII of at most 10485760 bytes.
Native IHP DRC and strict named-interface LVS must pass. Keep the supplied tap geometry and compact-device parameters consistent. Functional device, well, contact and routing layers define area; annotation layers do not. The bounding rectangle must fit 5000 by 1000 um. No DRC waivers apply.

Magic extracts candidate interconnect resistance/capacitance and device
junction geometry. Wells/substrate are connected to physical tap rails; source
simulation retains finite tap models. Distributed substrate, statistical
mismatch and manufacturing signoff are outside this nominal contract.

The scored functional layer/datatype pairs are `[[1, 0], [3, 0], [5, 0], [6, 0], [7, 0], [8, 0], [10, 0], [11, 0], [13, 0], [14, 0], [19, 0], [24, 0], [26, 0], [28, 0], [29, 0], [30, 0], [31, 0], [32, 0], [33, 0], [35, 0], [36, 0], [40, 0], [44, 0], [46, 0], [49, 0], [50, 0], [51, 0], [52, 0], [53, 0], [55, 0], [58, 0], [66, 0], [67, 0], [90, 0], [101, 0], [111, 0], [125, 0], [126, 0], [128, 0], [129, 0], [133, 0], [134, 0], [139, 0], [152, 0]]`.

## Electrical Requirements and Scoring

All declared measurements must be finite and use the extracted candidate. Gain and phase at 10 Hz/100 kHz, output bias, supply power, small differential step response, common-mode kick and recovery are observed by the supplied deck. Step response subtracts 8–9 us baseline from 38–39 us response. The common-mode baseline is 58–59 us; kick peak is 60–62 us and residual is 98–99 us. Continuous quality uses independently simulated same-condition source observations. The physical-domain checks are nonnegative supplied power and nonnegative absolute errors; they are not upstream specifications.

The layout-v2 score is 100 times sqrt(E times Q). Q is 1035.78 um2 divided by functional area. The anchor sums (W+2.4)(L+2.4) for each MOS and 3.2² um2 for each local tap and one global tap, then applies a 50% routing allowance. It is an engineering estimate, not a foundry minimum. Response metrics use source-paired dB gain, target phase (180 degree scale), target step (1 mV scale), and inverse absolute common-mode error (1 uV floor); bias uses a 1.2 V target scale; power uses an inverse ratio with 1 pW floor. Coefficient 6 reflects the complete signal amplifier coupled to a transistor common-mode recovery loop. Qualification does not require matching paper performance and does not cover PVT, noise, mismatch or an RRL system.

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

| Metric | Definition / observation | Unit | Quality / dimension | Functional bounds | Scale |
| --- | --- | --- | --- | --- | --- |
| `functional_area` | Functional bounding-rectangle area | um2 | area quality Q | positive area | — |
| `cm_bias_v` | `(v(outp)+v(outn))/2` | V | target / target / bias | −∞ … +∞ | 1.2 |
| `dm_bias_v` | `v(outp)-v(outn)` | V | target / target / bias | −∞ … +∞ | 1.2 |
| `power_w` | `-v(vdd)*i(VDD)-v(vb1)*i(VB1)-v(vb2)*i(VB2)-v(vb3)*i(VB3)-v(vb4)*i(VB4)` | W | minimize / ratio / supply | 0 … +∞ | 1e-12 |
| `gain_db` | `find gain at=10` | dB | maximize / db20 / response | −∞ … +∞ | — |
| `gain_100khz_db` | `find gain at=100k` | dB | maximize / db20 / response | −∞ … +∞ | — |
| `phase_100khz_deg` | `find phase_deg at=100k` | deg | target / target / response | −∞ … +∞ | 180 |
| `step_response_v` | `dm_high_v-dm_before_v` | V | target / target / response | −∞ … +∞ | 0.001 |
| `cm_before_v` | `avg cm from=58u to=59u` | V | diagnostic | −∞ … +∞ | — |
| `cm_kick_v` | `max cm_delta from=60u to=62u` | V | minimize / ratio / response | 0 … +∞ | 1e-06 |
| `cm_recovery_v` | `max cm_delta from=98u to=99u` | V | minimize / ratio / response | 0 … +∞ | 1e-06 |
| `cm_min_v` | `min cm from=0 to=100u` | V | diagnostic | −∞ … +∞ | — |
| `cm_max_v` | `max cm from=0 to=100u` | V | diagnostic | −∞ … +∞ | — |

Apply each row to every declared load/tone condition. Pair each candidate
observation with its `source_` job under the identical condition. The supplied
deck defines intermediate vectors used in the expressions above.

## Tools and Submission

Solve budget: **6 hours**.

Use the reviewed IHP resources. Submit only the GDS with top cell amp_027_fan_rrl_ota. Evaluation runs native DRC/LVS, area, candidate-derived Magic RC extraction and ngspice post-layout observations. The source circuit is independently simulated for scoring.

Discover the frozen task, resources and submission interface through
`/protocol/task.json`, `/protocol/resources.json` and `/protocol/harness.json`.
Declared inputs are under `/task`. Write `/workspace/output/final.gds`
and explicitly submit with `python -I /protocol/submit.py`. Creating the file
alone does not submit it. Only feedback supported by the active harness is available.
