# Adding Tasks and Validating the Judge

For agent-assisted case authoring, use the repository's
[`add-case` skill](../.agents/skills/add-case/SKILL.md). It guides the workflow
across process technologies and toolchains; this guide remains the authority
for task contracts, documentation templates, scoring and qualification.

See the [comparator case](../tasks/ihp-sg13g2/IHP-AnalogAcademy/cases/comparator/case.toml) for an executable task and its embedded toolchain, constraints, and evaluation plan. The selected public IHP and TO_Apr2025 cases are listed in [`tasks/ihp-sg13g2/IHP-AnalogAcademy/catalog.toml`](../tasks/ihp-sg13g2/IHP-AnalogAcademy/catalog.toml) and [`tasks/ihp-sg13g2/TO_Apr2025/catalog.toml`](../tasks/ihp-sg13g2/TO_Apr2025/catalog.toml). Promotion freezes inputs, constraints, evaluation, tool bindings, and independent qualification; shipping a reference layout is optional, and witness-less cases disclose their limits' basis as described under [qualification](#qualification). Model selection, repetitions and access policy belong to the outer [run plan](running.md).
Each case owns its solve budget through `[task].hours`.

Catalogs index maintained cases; source attribution is a URL in each case.
Use `candidate` for incomplete or unvalidated cases and `qualified` after the
[per-case checks](#qualification) pass. Executable cases ship ready-to-use inputs;
source-only circuit inventories do not constitute runnable layout tasks.
The [GF180 collections](tools.md#gf180) contain twenty-seven qualified, executable cases
with passing references, nominal RC evaluation and calibrated scoring, including
the [analog-db regulator core](../tasks/gf180mcuD/analog-db/README.md) with
supply/load, dropout and load-step coverage. The same collection also adds
a cascode gain stage, resistive differential pair, folded-cascode OTA,
hysteretic comparator and temperature-slope cores, including isolated-body
startup at specified supply ramps; each ships an independently
validated reference and its own calibrated operating conditions.
The [analog-db OTA collection](../tasks/ihp-sg13g2/analog-db/README.md) adds an
IHP conversion pilot with fixed sizing, a physical witness and nominal AC/DC
evaluation. The collection also includes a physical-MIM common-mode sampler
and a three-bit capacitor bank with all-eight-code AC/step measurements; see
the collection index for their distinct operating boundaries. Its circuit
materials retain separately identified noncommercial
and upstream license terms; they are not covered by the framework's MIT license.

Public cases are grouped by PDK: IHP AnalogAcademy and TO_Apr2025 cases use one
directory per circuit under `tasks/<pdk>/<collection>/cases/<circuit>/`, with a
single `case.toml` entry point.
The catalog's `config_path` locates the entry point; the full case ID and source
link remain in the manifest. File roles are declared by the manifest;
the loader does not require particular directory names.

### Problem, materials, tools, answer, and scoring

The [comparator case](../tasks/ihp-sg13g2/IHP-AnalogAcademy/cases/comparator/README.md)
provides a concrete entry point for this workflow:

| Role | Comparator location | Runtime responsibility |
|---|---|---|
| Problem | `problem.md` | Solver-facing objective, interface and acceptance requirements; declared as `inputs.description` |
| Materials | `materials/` | Authoritative netlist and public simulation testbench; declared inputs |
| Tools | Tool instructions in `problem.md`; `[toolchain]` in `case.toml` | The problem explains the shared EDA/PDK environment; the case binds evaluator backends on the host. Solver image, reviewed resources and harness come from the outer run configuration |
| Answer | `/workspace/output/final.gds`; maintainer witness in `reference/` | The solver explicitly submits a GDS snapshot; the reference demonstrates feasibility and is excluded from solver inputs |
| Scoring | Rules in `problem.md`; `[task.evaluation]` and `[task.constraints]` in `case.toml` | Public requirements, physical gates, candidate-derived RC and bounded simulation measurements; the evaluator produces `report.json` |

The comparator README describes its current circuit, reference results,
reproduction steps and brief source attribution. Its case directory contains only the current
problem, materials, tool instructions, case configuration and reference GDS;
development records remain in Git history and local `build/runs/` outputs.
`case.toml` defines one current scoring plan. These directory
names organize the case; `[task.inputs]` declares the files a solver
receives. The comparator materializes the problem, netlist and testbench; its problem
includes tool instructions and the complete scoring rules. Inline constraints and
evaluation are published in `/protocol/task.json` and supplied to the evaluator
from the same frozen definitions. The case configuration, reference GDS and case README stay
outside solver inputs. Public qualified cases use the unified `layout-v2`
score described under [task scoring](#task-scoring). Case directories may retain
their manifest-declared paths.

<a id="case-documentation"></a>

### Case Documentation Templates

Include the following headings in this relative order for every case; additional
circuit-specific sections are allowed. Write in English and
describe the current circuit and validated scope. Use descriptive circuit names;
a source directory's frequency or noise label is not a specification. Keep case
IDs and manifest paths stable when improving display names.

`problem.md` is the complete solver-facing contract:

```markdown
# <Circuit Name> Layout Task
## Objective
## Inputs and Interface
## Operating Conditions
## Physical Requirements
## Electrical Requirements and Scoring
## Tools and Submission
```

| Section | Required content |
|---|---|
| Objective | Circuit function, layout objective and target top cell. |
| Inputs and Interface | Declared input files and their roles; ordered ports and their functions. |
| Operating Conditions | Model corners, temperature, rails, bias, loads, stimuli, sweeps and measurement windows. |
| Physical Requirements | Artifact limits, DRC scope, LVS port policy, functional outline and included layers, candidate extraction and relevant model boundaries. |
| Electrical Requirements and Scoring | A metric/definition/unit table, functional bounds, measurement conventions, diagnostic metrics, paired source baselines and normalization rules, dimension assignments and area targets. State that every required operating point must satisfy functional checks and that incomplete evaluation cannot establish success. |
| Tools and Submission | Runtime task, resource and harness discovery, supported feedback, GDS destination and explicit submission procedure. |

Publish the budget as `Solve budget: **<hours> hours**.` in Tools and Submission;
the catalog regression compares it with `[task].hours`.

The structured task configuration owns numerical budgets, limits and scoring
parameters. Publish them here using generated text or consistency checks; explain
measurement meaning and functional-bound rationale alongside them.
Keep acceptance limits here and in their structured configuration. The solver
must be able to understand every requirement from its declared inputs and
runtime protocol; maintainer READMEs, reference results and host configuration
are outside standard solver inputs.

`README.md` is the reader's overview and reference reproduction entry point:

```markdown
# <Circuit Name>
## Overview
## Files
## Reference Results
## Reproduce
## Source and License
```

| Section | Required content |
|---|---|
| Overview | Current circuit topology, purpose and validated operating scope in one or two paragraphs. |
| Files | Links to the problem, configuration, authoritative materials and reference layout when provided. |
| Reference Results | Physical-check summary and a `Metric | Unit | Pre-layout | Post-layout` table under the declared conditions; relevant extraction/calibration scope. For multiple operating points, label ranges or worst-case values explicitly. |
| Reproduce | Commands from the repository root to evaluate the published reference and reproduce any applicable calibration, with a link to shared tool setup. Use fresh output directories and explain that commands generate the cited reports. |
| Source and License | One sentence identifying and linking the source repository and circuit, followed by the applicable license link. |

Use `candidate layout`, `reference layout`, `Pre-layout` and `Post-layout`
consistently, with explicit units in tables. Report measured results in the
README and link to the problem for acceptance limits. Preserve circuit-specific
conditions and model limitations even when one case needs more detail than
another. Describe current design choices in the overview when they explain
behavior; keep original asset failures, repair chronology and discarded results
in development history. Record the upstream URL as `origin.url` and bind maintained input and reference
digests in `case.toml`; retain required copyright and modification notices with the assets.

After editing, update the declared description digest, check local links and
commands, and verify task loading and materialized inputs. A documentation-only
rewrite must preserve circuit, layout, testbench, constraints and scoring
semantics; follow the [verification matrix](../CONTRIBUTING.md#verification)
for the affected scope.

<a id="task-design"></a>

## 1. Confirm Sources and Published Content

Public tasks use public designs and open PDKs/EDAs approved for distribution, and publish their inputs and qualification materials, plus the ready-to-use reference solution when one exists. A reference solution is for debugging and demonstrating feasibility; it is neither the only answer nor an optimum or scoring denominator. A standard solve receives only declared inputs; debugging with reference materials must be distinguished from solving in an empty workspace.

Publish ready-to-use netlists and testbenches under `materials/`, together
with the task contract and any supplied reference GDS. Case creation may use
schematics or conversion tools during development; the published case loads,
materializes and evaluates without regenerating those materials. Keep authoring
scripts, intermediate schematics and export logs in development history.
Validate the maintained LVS and simulation netlists against the circuit contract
and each other, then qualify the submitted-layout evaluation independently.

The case-owned circuit is the benchmark's design authority. An upstream
schematic, layout or simulation may be incomplete or inconsistent without
disqualifying a separately maintained derivative. Record its upstream location in `case.toml` as `origin.url`, retain required
notices with the maintained assets, and keep the README's source attribution
to the repository and circuit plus license.
Describe the current topology, devices, bias and ports in the appropriate case
sections using the [documentation templates](#case-documentation).
A directly authored netlist is permitted when explicitly identified
as such; do not describe it as an untouched schematic export. Check that the
LVS and simulation representations describe the same case-owned circuit.
Qualification requires functional measurements under declared conditions,
matching clean layout evidence and faithful candidate-derived extraction;
simulator convergence or physical-only scoring does not establish this scope.
Original frequency and noise targets are not inherited automatically: define
the derivative's intended function and acceptance limits before qualification.

<a id="asset-rights"></a>

### Sources, Licenses, and Visibility

Record the source, license, and permitted use and distribution scope separately for each design, PDK, EDA tool, model, and derived artifact. The framework's MIT license does not cover third-party assets; retain each license with its corresponding asset. The [repository licensing index](../LICENSING.md) identifies collection scopes, including the noncommercial analog-db materials. Public visibility and technical qualification are not license grants. A public package must preserve required license, copyright, and modification notices rather than summarizing all files under an upstream top-level license.

| Material | Storage and runtime visibility |
|---|---|
| Netlist, constraints, evaluation requirements, required testbench/model/description | Inputs declared by the case TOML's `[task]` section; readable by a standard Agent |
| Reference GDS and case-specific validation results | Case-local maintainer materials; comparator keeps its reference GDS in `reference/` and its overview, reference results, reproduction steps and source attribution in `README.md`; downloadable for debugging but excluded from standard solve inputs |
| Preparation source records | May be referenced by `provenance`; not materialized for the Agent automatically |
| Process and tool materials | Declared, frozen read-only PDK source/support bundles; full PDK sources are permitted, but benchmark/circuit-answer repositories and local Git metadata are excluded; see [Agent PDK resources](tools.md#agent-pdk-resources) |

Hidden tasks use only independently authored or authorized unpublished designs. Their inputs, reference solutions, qualification materials, and raw run evidence are held by the evaluator and do not enter public Git, images, or CI. Every requirement that affects the current task must be provided to the running Agent; hidden data must not become an undisclosed scoring rule. Restricted originals stay in approved environments. Private Git and zero-data-retention endpoints do not by themselves grant permission to store, process, or transmit the data. Bind the specific approval record through the [admission interface](architecture.md#verified-reruns-and-disclosure).

<a id="task-configuration"></a>

## 2. Declare the case `[task]` section and Freeze Inputs

`benchmarking/tasks.py` loads the nested executable task using the existing schema-1 fields. For a public circuit case, those fields live under `[task]` in a schema-2 `kind = "layout_case"` file; standalone framework fixtures may still use the legacy schema-1 task file.

| Field | Meaning |
|---|---|
| `schema_version`, `kind` | Currently `1` and `netlist_to_gds`; unsupported versions or kinds are rejected |
| `id`, `title`, `family`, `status` | Task identity, display name, statistics family, and `candidate` / `qualified` status |
| `hours` | Positive finite solve wall-clock hours, explicitly maintained per executable case and published in the task description. The server converts this to protocol seconds; participant settings and service CLI cannot override it. Legacy evaluation-only fixtures may omit it, but cannot be served without an explicit budget |
| `coefficient` | Integer difficulty coefficient from 1 through 10; default 1 for general task fixtures. Public scored cases declare it explicitly. It is frozen with the task and used only when aggregating independent tasks |
| `environment` | Required process and tool configuration identity; the actual run also records image and PDK-view digests |
| `inputs.netlist` | `path`, `sha256`, and target `subcircuit` |
| `constraints` or `inputs.constraints` | Exactly one: inline structured constraints, or `path` and `sha256` for a separate constraints file |
| `inputs.description`, `inputs.license` | Optional task description and license files, each declaring `path` and `sha256` |
| `evaluation` or `inputs.evaluation` | Optional evaluation plan: an inline table, or a TOML file declaring `path` and `sha256`; declaring both is rejected. Loading validates the [evaluation plan schema](#evaluation-plan) |
| `inputs.<role>` | Other named inputs such as testbenches, models, and stimulus files; declare `path` and `sha256`, with optional `format` (default `text`; simulation files may use `spice`) |
| `output` | Workspace-relative `path`, `format = "gds"`, `top_cell`, and positive-integer `max_bytes` |
| `provenance` | Optional preparation-source record with `path` and `sha256`; readable by maintainers but not materialized for the Agent |

### Shared collection inputs

Store source licenses and required notices at collection level, outside the
default solver input set. Preserve them with repository distributions and material
exports. `Task.materialize()` creates an isolated solve directory, not a complete
redistribution package. A solver needs the circuit contract and design inputs;
license text does not need to be declared as a task input.

The loader also supports shared collection files that are explicitly declared as
inputs. Existing license input declarations remain supported; the following is a
legacy example of the mapping, not a requirement for new cases:

```toml
[task.inputs.license]
path = "materials/LICENSE"
collection_source = "LICENSE"
sha256 = "<SHA-256 of the collection LICENSE>"
format = "text"
```

`path` is always the case's delivered input path. By default it also locates the
source within the case directory; `source` can select a different case-relative
file. Alternatively, `collection_source` selects a file relative to the enclosing
collection of `<collection>/cases/<circuit>/case.toml`. It is supported only for
unified circuit cases in that layout with a regular `catalog.toml` at the collection
root. `source` and `collection_source` are mutually exclusive. Source and destination
paths must be normalized relative paths; traversal, symlinks and directory inputs
are rejected. Every selected file is digest-checked and snapshotted when loading.

This source mapping is maintainer metadata: the solver sees only the declared
materialized paths and bytes. When assembling a standalone prepared case, copy its
inputs with `Task.materialize()` and remove `source`/`collection_source` from its
input declarations so it reads the local snapshots. The prepared configuration has
its own digest. Existing case-local license inputs remain supported.

Keep distinct component terms and circuit modification notices attributable when
centralizing files. Collection notices can include labeled sections for their cases;
case-only additions can remain with the corresponding materials. Material exports
must retain the applicable collection terms independently of the solver input
list. Changing an explicitly declared shared input requires updating its digests
and validating every case that references it.

Each case records only its upstream location under `[origin]`:

```toml
[origin]
url = "https://github.com/owner/repository/tree/revision/path/to/circuit"
```

The URL identifies where the design came from; it does not bind the maintained
circuit to the upstream bytes or require an upstream checkout to load or run.
Case inputs and reference assets retain their own digests; reviewed PDK
resources remain pinned in `pdk.toml`. Resource preparation assembles the tool
environment and does not generate or modify case materials.
Collection catalogs contain only `schema_version` and `[[cases]]` entries with
`id` and `config_path`. Source surveys and original-asset audit results belong
in development history, outside case and catalog configuration.

Resolve paths relative to the task configuration directory. Map inputs to `/task/<path>` and outputs to `/workspace/<output.path>`. The task ID, subcircuit, and top cell come from configuration; the runner does not hard-code tasks. The loader rejects unknown fields, unsupported versions, paths that escape their bounds or use symlinks, overlapping inputs, and digest mismatches. The configuration digest binds the original TOML bytes.

Materialize file snapshots validated at load time. Copy only declared inputs; do not bring in neighboring reference solutions, source records, or a complete checkout. Callers must still use read-only mounts and control access. Successful loading does not prove that the circuit is feasible or that the judge is correct; `status="qualified"` is not a qualification credential. The output path is a convention, and the Agent must explicitly submit it using the [submission protocol](running.md#service-participation).

## 3. Define Executable Constraints

Constraints can live directly in `[task.constraints]` of a circuit case (`[constraints]` in a standalone task). The table contains the existing geometry schema: `schema_version = 1`, `hard` and `quality` arrays. The loader freezes this data as a JSON asset, publishes it under `constraints` in `/protocol/task.json`, and supplies it as `input:constraints` to the evaluator. It does not create an extra solver file or expose the full case configuration. The case digest binds the inline definition. Task loading checks that inline data is a JSON-compatible table; the geometry backend validates its supported rules when evaluating.

Existing `inputs.constraints` files remain supported. Declare exactly one source; missing or duplicate definitions are rejected. The comparator uses inline constraints and keeps the human-readable requirements in `problem.md`.

For every constraint, specify object selection, relationships, units, tolerances, hard/soft status, and measurement method. Every requirement that affects success must come from frozen inputs, with the description and machine checks kept consistent. Identify objects from extracted electrical correspondence and trusted geometry analysis; do not rely only on cell names, labels, or sidecars written by the Agent.

Define the allowed device swaps, fingering, merging, and geometric equivalences for each task; leave out constraints that cannot be mapped reliably. State which functional layers and boundaries participate in area measurement. Metal area cannot stand in for wire length, and geometric symmetry does not establish electrical matching. Declare noise and mismatch requirements only when the models, extraction flow, and measurements actually support them. See the [geometry backend](tools.md#geometry) for the current implementation.

<a id="evaluation-plan"></a>

## 4. Declare an Evaluation Plan

Declare the plan inline under `[task.evaluation]` in a circuit case (`[evaluation]` in a standalone task), or reference a digest-bound TOML file through `inputs.evaluation`. An executable evaluation uses one source; declaring both is rejected. Inline plans use the same schema and validation as file plans. The loader freezes the inline table as a JSON snapshot and exposes its complete definition through `/protocol/task.json` under `evaluation`; it does not create an extra solver file. The case digest binds the original definition, while the evaluation report archives the plan snapshot with its format and digest. Existing TOML plan files retain their original bytes and digests.

Explain the complete scoring rules in the problem: check prerequisites, operating points, measurement definitions, thresholds, aggregation and failure semantics. Testbenches, stimulus, and required models remain declared task inputs. The plan describes what to measure. Trusted toolchain configuration binds each operation to a backend, while the core does not interpret simulator commands. A schema-2 case may contain an optional `[toolchain]` table with the existing toolchain schema: `schema_version = 1`, `[toolchain.backends.<id>]` (`type` and `settings`), and `[toolchain.bindings]`. This host configuration is separate from `[task.inputs]` and never materialized for the solver. Loading a task validates its inputs without starting tools; `load_toolchain` validates the backend configuration before instantiating registered adapters.

The current evaluation schema is `1` and contains `mode`, `jobs`, `metrics`, and
an optional `scoring` declaration. Public qualified tasks declare scoring:

| Object | Fields and semantics |
|---|---|
| `mode` | `physical` performs physical validation only; `characterization` is for independent circuit measurement; only `post_layout` can establish complete task success |
| `jobs[]` | Unique `id`, `stage` (`check` / `extract` / `simulate` / `measure`), logical `operation`, and named `inputs`; optional `outputs`, `requires`, `gate`, and `parameters` |
| `inputs` | Names mapped to data references: `candidate` is the frozen GDS, `task` is a JSON description generated from the loaded configuration, `input:<role>` is a declared task file, and `job:<id>:<output>` is an upstream artifact |
| `outputs`, `requires` | Output-name to format mappings; artifact references create dependencies automatically, while `requires` adds prerequisites that produce check evidence only |
| `gate` | A check step may be marked `artifact`, `drc`, `lvs`, or `constraint`. A layout plan has one of each of the first three, and each must check the candidate GDS directly |
| `parameters` | A parameter table interpreted by the backend, such as measurement names and units, load, temperature, seed, or output filename. The core only checks that it can freeze the table as JSON; it does not interpret EDA syntax |
| `metrics[]` | Unique `id`, `category` (`physical` / `performance`), `observations` (`<job>:<measurement>`), `unit`, `direction` (`minimize` / `maximize` / `target`), and `aggregation` (`min` / `max`); optional `lower` and `upper` |
| `metrics[].dimension` | For every scored performance requirement: `response`, `bias` or `supply` |
| `metrics[].baseline`, `normalization`, `scale` | Same-condition source observations paired with `observations`, normalization rule and optional scale as defined below |
| `metrics[].zero_lower`, `metrics[].zero_upper` | Historical `layout-v1` zero-score boundaries only |
| `scoring` | `method = "layout-v2"`, `area_metric` naming the physical area metric produced by the candidate constraint check, and positive fixed `area_target` in that metric's area unit |

Physical metrics may consume a measurement from a successful `check` step, such as area reported by a geometry check. Performance metrics must still come from `simulate` or `measure`; a check status cannot stand in for performance.

The KLayout DRC adapter accepts an optional case-local `parameters.waivers` list. Each entry must name one report `category`, exact report `cell`, a nonempty list of exact textual `markers`, and a nonempty `reason`. Only those marker items are accepted; the native DRC report and raw violation count remain archived, and any unmatched item still fails the check. Keep waivers in the digest-bound case evaluation plan, never in the shared PDK deck, and use them only for reviewed, intentional structures.

Use separate named jobs for different conditions, and archive their parameters, models, and inputs with the result. **Evaluate limits observation by observation.** `aggregation` controls only how a summary is displayed; an average or one passing condition cannot hide an out-of-limit condition. Report metrics without limits as values only; unscored `target` requires both lower and upper bounds; a baseline-scored target uses its source observation and scale. Units must match exactly. There is currently no implicit unit conversion; missing measurements, non-finite values, and unit mismatches are evaluation errors.

A `post_layout` plan must declare at least one limited performance metric. Its performance observations must come from simulation or a post-simulation measurement step, and the simulation must actually consume artifacts extracted from the candidate GDS. Reject plans that sort results after PEX but continue simulating the schematic netlist. `extract` denotes the post-layout extraction stage and must depend on the three physical-validity gates. Dependency-graph checks ensure that materials flow correctly; backend qualification remains responsible for whether the extracted content is correct.

Backends read conventions such as `output.top_cell` and `netlist_subcircuit` from the `task` input, so the plan need not hard-code them again. This description contains neither preparation sources nor reference solutions. Input references must come from the task manifest or from trusted generated materials, including the frozen `input:constraints` and `input:evaluation` assets for inline definitions. The executor gives a backend only the snapshots declared by its current job; it does not provide the entire task directory automatically.

<a id="task-scoring"></a>

### Unified Task Score

`layout-v2` scores electrical quality relative to source simulation and area
relative to a frozen compact footprint. **100 is a reference, not a maximum.**
Physical and characterization plans do not produce benchmark scores.

```text
Q = area_target / candidate_functional_area
E = geometric_mean(applicable response, bias, supply dimension scores)
S = 100 * sqrt(E * Q)
```

Artifact, DRC, named-interface LVS, hard geometry and declared functional bounds
are prerequisites. A completed rejection scores zero; missing, nonfinite,
wrong-unit or unusable source evidence gives an unknown (`null`) score. An
independently established physical rejection remains zero even if an unrelated
tool errors. There is no electrical acceptance bonus or fixed percentage of
permitted degradation. Passing functionality does not imply a score of 100.

Each quality observation `x` names a same-condition source observation `b` in
`baseline`, paired in order. Source jobs consume the declared source circuit,
independently of the candidate. The paired jobs use the same operation,
parameters, testbench and backend/model resources. The source values are computed
and archived during evaluation; they are not fitted to submitted results.

| Normalization | Quality q | Use |
| --- | --- | --- |
| `ratio`, maximize | `(x+s)/(b+s)` | Positive gain, bandwidth and other increasing benefits |
| `ratio`, minimize | `(b+s)/(x+s)` | Delay, power, error and other decreasing costs |
| `db20` | `10^((x-b)/20)` for maximize; inverse for minimize | Amplitude gain or rejection in dB; never divide dB values |
| `target` | `1/(1+abs(x-b)/s)` | Preserve a bias, signed transfer or intended operating point |

For ratios, optional `scale=s` is a positive numerical floor (default zero),
not an allowed degradation. Candidate and source values must be nonnegative and
the denominator positive. Zero error measurements need a declared floor.
For target normalization, `scale` is a required positive physical normalization
unit; identify its basis in the problem. `db20` cannot specify a scale. Target
quality is at most one; directional and area improvements can exceed one.

A metric uses its **worst paired quality**, independently of the displayed
`aggregation`. Group comparable timing arcs into one delay metric and one output
transition metric so an easy arc cannot dilute a degraded critical arc. Each dimension uses the geometric mean of its scored metrics;
`E` uses the geometric mean of applicable dimensions, with no free points for an
absent dimension. Freeze metric selection and dimensions before evaluation:
adding redundant metrics changes their relative influence. Use `response` for
transfer/timing/stability, `bias` for operating points and `supply` for power.
Functional checks and diagnostic observations do not add quality points.

Use the full functional bounding rectangle, including devices, wells, contacts
and routing, with explicitly documented annotation exclusions. Standard cells
use the declared standard reference layout's measured area. Other circuits use
a fixed engineering estimate based on declared device sizes/multiplicities,
contact/isolation envelopes and routing allowance, with the calculation published
in the problem. An estimate is not a foundry minimum or a demonstrated optimum.
Freeze it before model evaluation; never derive it from the candidate. Fixed row
height, width grid and named supply-rail continuity are standard-cell hard checks.
The current standard-cell timing tasks use one declared input slew and output
load; they do not claim full Liberty/PVT characterization or neighbor abutment.

Reports retain `method="layout-v2"`, `reference=100`, `maximum=null`, raw source
and candidate observations, metric ratios, dimensions, area and `G/E/Q` components.
A reference-equivalent electrical result at the area reference earns 100. The
root benchmark version **3** identifies the migrated contracts. Old results must
keep their frozen task, evaluator and scoring version; rerunning is a new result.

Historical `layout-v1` remains readable and recomputable with its original
`maximum=100` envelope and `S=G*(60E+20H+20HQ)` formula: bounded linear attainment,
worst metrics within each dimension, equal dimension mean, acceptance bonus and
clipped area utility between `area_target` and `area_zero`. Only v1 accepts
`zero_lower`, `zero_upper` and `area_zero`. It is not used for newly authored
public cases. Do not reinterpret its scores on the new scale.

The task coefficient is an integer from 1 through 10. It expresses the capability
needed to implement the fixed circuit under its declared environment and acceptance
contract, independently of the candidate's task score.

| Coefficient | Capability scope |
|---:|---|
| 1 | Basic single-stage logic with connectivity and loaded logic-level checks |
| 2 | Compound logic with multiple conduction paths and input transitions |
| 3 | Local analog or controlled driver behavior: bias, transfer or output states |
| 4 | A complete compact circuit coupling gain, accuracy, load or a physical passive network |
| 5 | Local feedback, clocked state or charge transfer with parasitic-dependent dynamics |
| 6 | Regenerative decisions, storage integrity, coupled startup behavior or a complete compensated loop |
| 7 | Multistage compensation or regulation maintaining frequency response and recovery across loads |
| 8 | Active auxiliary compensation, self-oscillation or broader return-ratio and startup requirements |
| 9 | Strongly interacting control goals or complex regulation combining startup, frequency response and recovery |
| 10 | Clock modulation, signal feedback and actual common-mode control operating together |

Apply the whole acceptance contract and compare neighboring capability anchors;
feedback or startup alone does not imply a high grade. Circuit names, transistor
count, area, simulator runtime, repair effort and observed model success rates do
not determine the coefficient. Unmeasured RF performance, noise, statistical yield
or geometric symmetry requirements cannot raise a task's grade. Each case README
explains its circuit-specific scope and its problem publishes the integer.

Declare coefficients before model evaluation. Using the integer directly as a
[batch score](tasks.md#task-scoring) weight is an aggregation policy, not a claim that
a grade-10 circuit takes ten times the work of a grade-1 circuit. Adding tasks does
not regrade existing ones. Changing coefficients, score boundaries, task membership
or tools creates a different benchmark identity; historical results retain their
frozen coefficients and must not be silently reweighted.

The root benchmark version `3` uses this scale for its unchanged 16 representatives
(total coefficient 92). The catalog contains 81 executable qualified tasks.
PAM4 includes native CC extraction and source-paired RF/tone scoring. The task score formula and electrical
acceptance limits are independent of this grading scale.

<a id="evaluation"></a>

### Decisions and Reporting

The evaluator receives only the frozen GDS from the Agent; the authoritative netlist, top cell, constraints, and rules come from trusted preparation materials. The current evaluation container mounts the candidate and PDK view read-only. Trusted workflows pre-stage task materials, and the evaluator does not access the Agent's writable directory or credentials. A tool exit code of 0 is not sufficient: verify that checks completed, reports are complete, extraction is non-empty, and the specified circuit actually participated in the LVS comparison.

```text
physical_valid = artifact_ok ∧ drc_pass ∧ lvs_pass ∧ all hard constraint gates pass
task_success = physical_valid ∧ all declared requirements pass ∧ required post-layout complete
```

DRC/LVS establishes physical validity under the selected rules and extraction configuration; it is not a complete tape-out signoff. A layout can be legal yet fail the task because its geometry or post-layout measurements exceed limits.

| Result | Meaning |
|---|---|
| `passed` | The current step produced an acceptable result |
| `failed` | A completed check or measurement violated a declared requirement |
| `error` | A crash, timeout, missing measurement, or similar condition prevented a valid result |
| `blocked` | A prerequisite did not pass, so the current step was not run |

Reports store `physical_valid`, `specs_pass`, and `task_success` separately; unknown or not applicable is `null`. Even when a `physical` or `characterization` run passes overall, `task_success` remains `null`. An out-of-limit functional result is a failure; a simulation crash or invalid
measurement window is an evaluation error. Testbench validity checks must abort
with a nonzero simulator exit before reporting invalid observations. Keep their
reported residuals diagnostic, without electrical acceptance bounds. Raw metrics may be saved for a physically valid candidate, while the primary quality report summarizes only successful candidates and discloses coverage. See [statistics](tasks.md#task-scoring) for the policy.

Independent re-evaluation does not run the Agent. `evaluate` and `run` use the case's `[toolchain]` by default. An explicit `--toolchain` selects an independent configuration instead, which remains required for cases without an embedded toolchain. `load_toolchain` also accepts a case TOML directly. Existing backend path semantics remain unchanged: relative `support` paths resolve from the launch working directory. With Public installed, run from the Public checkout with a new output directory:

```text
python -m benchmarking.engine.cli evaluate <case.toml> <candidate.gds> --output <new-output-directory>
```

<a id="qualification"></a>

## 5. Validate Cases and Shared Evaluation

Case qualification means that the maintained materials are consistent and usable
under their declared conditions, including trustworthy candidate-derived
measurements and scoring. It does not certify an upstream data sheet or require
the reference layout to score at least 100. Upstream results provide provenance
and comparison context; same-condition source simulation supplies the electrical
quality baseline. Performance differences affect continuous quality unless a
separately justified functional constraint is violated. The
[case development standard](../tasks/AGENTS.md#1-circuit-contract-and-scope)
defines the source relationship and authoring decisions.

Shared regression tests establish the evaluator's rejection, scoring and error
behavior. Apply the following division of work.

### Per-case validation

For each executable case:

- Load its configuration, verify input/reference digests and materialize only the
  declared inputs. Collection licenses remain distribution metadata outside the
  default solver input set. The result must work independently
  of upstream source checkouts and authoring scripts.
- Check that the authoritative and simulator netlists, ordered ports, device
  parameters, problem, testbench, constraints and measurements describe the same
  circuit. Explain operating conditions, limits and fixed scoring anchors.
- When a reference is supplied, evaluate its ready-to-use GDS through the actual
  declared toolchain. It must pass artifact, DRC, LVS and geometry checks, then
  candidate-derived extraction and every required post-layout measurement.
  Measurements must be valid and declared functional bounds must pass; quality
  observations need not attain upstream performance targets.
- Publish measured results, relevant limitations and reproduction commands in the
  README. Generated reports retain task, input, candidate, tool and resource
  identities under `build/runs/`; per-case evidence archives are unnecessary.

Use `qualified` once these applicable checks pass. Keep `candidate` for incomplete
materials, inconsistent requirements, a failing supplied reference, or an
unvalidated case-specific capability. A reference-free case may qualify when its
inputs and evaluation are validated, but must disclose that post-layout
feasibility is undemonstrated and explain the basis of its limits and area anchors.
Formal [admission](architecture.md#verified-reruns-and-disclosure) separately requires a witness.

Pre/post-layout calibration is required when it establishes a performance limit,
explains a material discrepancy, or validates a new model/extraction boundary.
Reusing an established flow does not require repeating a full calibration matrix
for every circuit. Mark unmeasured table entries as such; preserve useful existing
measurements and regressions.

### Shared evaluator regression

Maintain representative tests for physical and geometry rejection, physically
valid electrical failure, scoring boundaries and area utility, evaluator errors,
permitted equivalent transformations, and repeatability. Validate extraction and
simulation with analytical controls and representative real circuits. When a
harness supports `process-feedback.v1`, test its agreement with the final judge
at the shared harness/evaluator boundary.

Each case need not supply its own area variant, electrical-failure layout or
complete rejection matrix. Add targeted tests when a case introduces a new device,
extraction method or special judging rule; reuse existing coverage for unchanged
mechanisms. Synthetic values can test scoring arithmetic, while physical and
extraction behavior requires real tool evidence. A passing reference alone does
not validate a new backend.

### Changes and scope

Rerun affected per-case checks after input, circuit, rule, limit or tool changes.
Rerun shared regressions when their mechanisms change. For metadata-only status
changes, existing results remain evidence for unchanged executable contracts;
identify them as prior runs and generate fresh identity-bound reports when an
admission or evaluation run requires them.

Qualification covers the declared operating scope, not PVT, mismatch, manufacturing
signoff or optimal layout quality. Formal admission has its own stronger evidence
and identity requirements; changing a catalog status does not grant admission.

<a id="input-isolation"></a>

## Historical Asset Exclusion Checklist

The following historically excluded assets and their copies must stay out of every task release bundle and Agent input:

- The original workspace asset `IHP-AnalogAcademy/modules/module_0_foundations/PEX_Demo/layout/inverter.gds`, including the same asset under `third_party/IHP-AnalogAcademy/`;
- The historical `third_party/IHP-AnalogAcademy/utils/PEX_Demo/` fixture and all geometry, netlists, reports, scripts, and intermediate artifacts produced by it;
- Geometry, images, netlists, reports, scripts, and intermediate artifacts produced by that inverter fixture;
- Historical run records named `local-inverter-unversioned-interface` and their derivatives;
- Historical candidates and caches or derived files with unknown provenance.

Keep these excluded artifacts inaccessible to both people and Agents: do not open, render, screenshot, parse, or count them. Renaming, moving, or archiving an asset does not change its exclusion status, and this checklist does not depend on an old run directory remaining present.

Construct new reference solutions and witnesses independently and record their sources. They may be public for debugging, but they are not standard solve inputs.
