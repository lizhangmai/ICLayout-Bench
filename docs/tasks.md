# Task Contract and Scoring

This reference defines the files and fields accepted by the engine, how submitted
layouts are evaluated, and how scores and result states are interpreted. Dataset
authors choose circuits, membership, measurements and parameter values. Their
development and publication policies are not engine configuration defaults.

- [Task files](#task-design)
- [Scoring](#task-scoring)
- [Evaluation results](#evaluation)
- [Configuration reference](#task-configuration)
- [Input isolation](#input-isolation)

See [running](running.md) for commands, [tools](tools.md) for PDK/backend setup,
and [qualification](../CONTRIBUTING.md#task-qualification) for the verification API.

<a id="task-design"></a>

## Task files

The package loads an explicit Dataset directory or HF Dataset snapshot; it bundles
no tasks. Cases use `tasks/<pdk>/<collection>/cases/<case>/case.toml`; stable IDs
come from that file, independently of directory names. The hierarchy identifies
PDK and collection, with shared process declarations at `tasks/<pdk>/pdk.toml`.

| File | Engine interpretation | Participant access |
| --- | --- | --- |
| `case.toml` | Identity, task settings, input digests and tool bindings | Normalized task fields through the runtime protocol |
| `problem.md` | Complete written requirements | When declared as `inputs.description` |
| `materials/` | Netlists, testbenches and other assets | Only declared `task.inputs` |
| `reference/` | Witness material when supplied for explicit verification | Excluded from standard solver inputs |

The native `data.jsonl` table indexes every case. Its boolean `in_core` comes from
`case.toml`; the engine uses it for explicit core selection and supplies no built-in
membership or selection policy. Table loading and indexing are documented in
[running](running.md#dataset-publication-files).

`[origin].url` supplies attribution. Optional `[presentation]` fields `category`
and `summary` must be nonempty strings; they support browsing and do not alter
requirements or scoring. Case-specific explanations belong in `problem.md`.

`status = "candidate"` or `"qualified"` is declared metadata, not proof produced
by loading a file. The qualification commands verify actual witness evidence.
A missing witness cannot pass witness qualification; normal solver sessions
never receive a reference layout.

<a id="task-coefficient"></a>

`coefficient` is an integer from 1 to 10 used in cross-task aggregation. It is
separate from the individual task's metric weights. Dataset authors own the
capability rubric and each assigned value; result consumers preserve the
recorded coefficient. See [aggregation](running.md#result-storage-and-presentation).

<a id="asset-rights"></a>

### Asset rights

The engine's MIT license does not relicense supplied materials, PDKs or tools.
Consult their own licenses and notices. Solver materialization is an isolated
input projection, not a redistribution bundle. Public-file enumeration uses
[the publication-file API](running.md#dataset-publication-files); authorization
and publication decisions belong to the data owner or operator.

<a id="task-scoring"></a>

## Scoring

Public tasks use `layout`. Electrical quality is measured relative to a
simulation of the source circuit under the same conditions. Area is measured
relative to a fixed reference footprint. A score of 100 represents both reference
values; scores may exceed 100.

```text
q_area = area_target / candidate_functional_area
q_i = worst source-paired quality for metric i
S = 100 * product(q_i ** w_i)  # includes q_area and its weight
```

Artifact, DRC, named-interface LVS, hard geometry and electrical requirements
must pass. A completed rejection scores zero. Missing, nonfinite, wrong-unit or
unusable source measurements produce an unknown (`null`) score. An independently
established physical rejection remains zero if an unrelated tool errors.
Physical-only and characterization runs do not produce benchmark scores.

### Electrical quality

Each scored observation `x` is paired with a source observation `b` through the
metric's `baseline` field. Pre-layout characterization runs during case design
and sets the frozen targets in `task.evaluation.pre_layout`. It records source
job definitions, finite measurements with units, input digests, backend identity
and the source report digest. Candidate evaluation runs only the post-layout
jobs in `task.evaluation.jobs`, using extracted candidate circuits. Baselines
come from the frozen task, never from candidate report jobs.

Each baseline pair must use the same operation, parameters and external fixture.
Changing source inputs invalidates calibration: task loading and evaluation
reject stale input digests before invoking tools. Model/toolchain changes require
review and affected calibration in the design authoring workspace. Source-only simulations belong in a
standalone `characterization` plan; they are rejected in a `post_layout` plan.

| Normalization | Quality q | Use |
| --- | --- | --- |
| `ratio`, maximize | `(x+s)/(b+s)` | Positive gain, bandwidth and other increasing benefits |
| `ratio`, minimize | `(b+s)/(x+s)` | Delay, power, error and other decreasing costs |
| `db20` | `10^((x-b)/20)` for maximize; inverse for minimize | Amplitude gain or rejection in dB; never divide dB values |
| `target` | `1/(1+abs(x-b)/s)` | Preserve a bias, signed transfer or intended operating point |

For ratios, `scale=s` is an optional positive numerical floor; its default is
zero. Both values must be nonnegative and the denominator positive. Error
metrics that can reach zero require a floor. For `target`, a positive `scale`
is required and defines the physical size of a deviation from the source value.
`db20` does not accept a scale. These scales normalize quality; they are not
acceptance tolerances.

A metric's quality is the worst of its paired observations, regardless of its
summary `aggregation`. Scored metrics are grouped into three dimensions:

| Dimension | Measurements |
| --- | --- |
| `response` | Transfer, timing and stability |
| `bias` | Operating points |
| `supply` | Power |

Weights are declared for each source-paired metric and for area. They are finite,
nonnegative and sum to one (absolute tolerance `1e-9`); the evaluator normalizes
roundoff in that sum. At least one electrical metric must have positive weight.
Every metric is checked in every required condition, including zero-weight
metrics. A zero quality with positive weight makes the score zero; a zero-weight
metric contributes no quality but still requires valid evidence and passing bounds.

Dimensions organize report summaries; moving a metric between dimensions does not
change its weight. `E` is the weighted geometric mean of electrical qualities,
normalized by total electrical weight. Each dimension is summarized the same way
using its own positive weights; a dimension with no positive weight is `null`.
Functional-only checks and unpaired diagnostics add no quality points. `target`
quality cannot exceed one; directional and area improvements can.

### Metric weights

Each task publishes its weights and their rationale in `problem.md`. The same
values are stored under `[task.evaluation.scoring]`. For example, a delay-focused
comparator can assign 70% to delay, 20% to power and 10% to area:

```toml
[task.evaluation.scoring]
method = "layout"
area_metric = "functional_area"
area_target = 1000.0
rationale = "Delay is the main objective; power and area are secondary costs."

[task.evaluation.scoring.weights]
worst_delay = 0.7
supply_power = 0.2
functional_area = 0.1
```

The example assumes these are the plan's only source-paired metrics. The weight
table must name every source-paired metric and the area metric exactly once;
unpaired diagnostics cannot have weights. The area target and weights for a
particular task come from its configuration, not from this example.

A larger weight gives stronger relative influence; only a functional bound
prevents compensation by other metrics. Dataset authors own metric budgets and
their rationale. Cross-task coefficients do not affect an individual task score.

### Area

Functional area is the bounding rectangle of the included devices, wells,
contacts and routing. Each task lists included layers and annotation exclusions.
The positive `area_target` is frozen in the task contract and independent of
submissions. Its derivation belongs in the task's `problem.md`; the engine does
not infer a minimum footprint from the circuit type.

### Score reports

Reports include the raw source/candidate observations, metric qualities,
weights, dimension summaries, area and `G/E/Q` components. The score envelope
uses `method="layout"`, `reference=100` and `maximum=null`. The task definition
and evaluator digests bind each result to its scoring configuration.

<a id="evaluation"></a>

## Evaluation results

Evaluation uses an immutable submitted GDS with trusted task materials and a
read-only PDK view. It does not use the participant's writable directory or
credentials. Physical checks precede extraction and post-layout simulation.

```text
physical_valid = artifact_ok ∧ drc_pass ∧ lvs_pass ∧ all hard constraint gates pass
task_success = physical_valid ∧ all declared requirements pass ∧ required post-layout complete
```

| Step status | Meaning |
| --- | --- |
| `passed` | The step completed and met its requirements |
| `failed` | A completed check or measurement violated a requirement |
| `error` | A crash, timeout or invalid/missing measurement prevented a result |
| `blocked` | A prerequisite did not pass |

Reports store `physical_valid`, `specs_pass` and `task_success` separately.
Unknown or inapplicable values are `null`. `task_success` is also `null` for
physical-only and characterization runs. DRC/LVS success establishes physical
validity within the selected rules; task success additionally requires the
specified geometry and electrical behavior. Neither is full manufacturing signoff.

For the command and output paths, see [standalone evaluation](running.md#standalone-evaluation).
For witness verification, see [task qualification](../CONTRIBUTING.md#task-qualification).

<a id="interpretation-limits"></a>

### Interpretation limits

Electrical coverage is limited to each task's declared measurements. Source-paired
quality alone does not establish noise, mismatch, process-corner robustness or
application-level performance. Consult the case's own measurement limits.

Numerical consistency observations check the simulation or measurement setup,
not circuit performance. If a case currently expresses such an observation as
a bounded metric, its bound still participates in the verdict; consult the case
plan and raw job status when diagnosing a rejection. New measurement-validity
checks should report unusable evidence as evaluator errors.

<a id="task-configuration"></a>

## Configuration reference

A public case uses `kind = "layout_case"`, with the executable
task under `[task]` with `kind = "netlist_to_gds"`. The loader takes `id`, `title`
and `status` from the outer case into the executable task.
Standalone task files declare those fields directly. The table below
lists the normalized task fields; in a case file, set identity/status at the
outer level and the remaining task settings under `[task]`.

| Field | Meaning |
|---|---|
| `kind` | Executable task: `netlist_to_gds`; outer case: `layout_case` |
| `id`, `title`, `family`, `status` | Task identity, display name, statistics family, and `candidate` / `qualified` status |
| `hours` | Positive finite solve time in hours, published in the problem and converted to protocol seconds. Required for serving a task; participants and service CLI cannot override it |
| `coefficient` | Integer from 1 to 10 for cross-task aggregation. Public scored cases declare it; the default for other tasks is 1 |
| `environment` | Required process and tool configuration identity; the actual run also records image and PDK-view digests |
| `inputs.netlist` | `path`, `sha256`, and target `subcircuit` |
| `constraints` or `inputs.constraints` | Exactly one: inline structured constraints, or `path` and `sha256` for a separate constraints file |
| `inputs.description`, `inputs.license` | Optional task description and license files, each declaring `path` and `sha256` |
| `evaluation` or `inputs.evaluation` | Optional evaluation plan: an inline table, or a TOML file declaring `path` and `sha256`; declaring both is rejected. Loading validates the [evaluation plan schema](#evaluation-plan) |
| `inputs.<role>` | Other named inputs such as testbenches, models, and stimulus files; declare `path` and `sha256`, with optional `format` (default `text`; simulation files may use `spice`) |
| `output` | Workspace-relative `path`, `format = "gds"`, `top_cell`, and positive-integer `max_bytes` |
| `provenance` | Optional preparation-source record with `path` and `sha256`; readable by maintainers but not materialized for the Agent |

### Input paths and snapshots

Each input declares a delivered `path` and SHA-256 digest. By default, the same
path locates the source relative to the case directory. `source` selects a
different case-relative file. All inputs remain inside their case; collection
notices are publication metadata and do not require a solver input. For example:

```toml
[task.inputs.stimulus]
path = "stimulus.spice"
source = "materials/stimulus.spice"
sha256 = "<SHA-256 of the stimulus file>"
format = "spice"
```

License files normally remain distribution metadata rather than solver inputs.
The source mapping applies to files that the task actually requires.
Paths must be normalized relative paths. Traversal, symlinks, directory inputs,
overlapping inputs, unknown fields and digest mismatches
are rejected.

The loader verifies and snapshots input bytes. `Task.materialize()` copies only
those snapshots; it does not create a complete redistribution package. Inputs
appear at `/task/<path>` and output at `/workspace/<output.path>`. Case files are read directly from the selected Dataset snapshot, retaining their
original digest. HF snapshot links into the Hub blob cache are supported; other
asset symlinks remain rejected. An input change requires a matching digest in the affected case. Runtime isolation additionally requires read-only mounts and access controls.

Source attribution is stored in the outer case table:

```toml
[origin]
url = "https://github.com/owner/repository/tree/revision/path/to/circuit"
```

This URL does not require an upstream checkout at runtime. Inputs and reference
assets have their own digests; PDK resources are pinned in `pdk.toml`.
Collection catalogs contain `[[cases]]` entries with `id`
and `config_path`.

### Geometry constraints

Declare exactly one of `[task.constraints]` or `inputs.constraints`. Inline
constraints contain `hard` and `quality` arrays. They are
published through `/protocol/task.json` and passed to the evaluator as a JSON
snapshot named `input:constraints`; no extra solver file is created. Task loading
checks JSON compatibility, while the geometry backend validates supported rules.

Constraints specify object selection, relationships, units, tolerances and
measurement methods. Electrical correspondence and trusted geometry analysis
identify the objects. Allowed device swaps, fingering, merging and equivalent
geometry must be explicit. The task also specifies functional-area layers and
exclusions. See the [geometry backend](tools.md#geometry) for supported checks.

<a id="evaluation-plan"></a>

### Evaluation plan

Declare `[task.evaluation]` or a digest-bound TOML file at `inputs.evaluation`,
but not both. Inline and file plans use the same schema. The runtime protocol
exposes the complete plan, and the evaluation report retains its snapshot,
format and digest. Inline plans are serialized as JSON; file plans retain their
original TOML bytes.

An evaluation plan contains `mode`, `jobs`, `metrics`, optional `scoring` and
frozen `pre_layout` calibration when metrics use source baselines.
Qualified public cases declare scoring.

| Object | Fields and semantics |
|---|---|
| `mode` | `physical` performs physical validation only; `characterization` is for independent circuit measurement; only `post_layout` can establish complete task success |
| `pre_layout` | Frozen source `jobs` keyed by ID, `source_report_sha256`, and `backends` identities. Each source stores operation, inputs, outputs, parameters, input digests and measurements; these jobs are not executed during candidate evaluation |
| `jobs[]` | Unique `id`, `stage` (`check` / `extract` / `simulate` / `measure`), logical `operation`, and named `inputs`; optional `outputs`, `requires`, `gate`, and `parameters` |
| `inputs` | Names mapped to data references: `candidate` is the frozen GDS, `task` is a JSON description generated from the loaded configuration, `input:<role>` is a declared task file, and `job:<id>:<output>` is an upstream artifact |
| `outputs`, `requires` | Output-name to format mappings; artifact references create dependencies automatically, while `requires` adds prerequisites that produce check evidence only |
| `gate` | A check step may be marked `artifact`, `drc`, `lvs`, or `constraint`. A layout plan has one of each of the first three, and each must check the candidate GDS directly |
| `parameters` | A parameter table interpreted by the backend, such as measurement names and units, load, temperature, seed, or output filename. The core only checks that it can freeze the table as JSON; it does not interpret EDA syntax |
| `metrics[]` | Unique `id`, `category` (`physical` / `performance`), `observations` (`<job>:<measurement>`), `unit`, `direction` (`minimize` / `maximize` / `target`), and `aggregation` (`min` / `max`); optional `lower` and `upper` |
| `metrics[].dimension` | For every source-paired metric: `response`, `bias` or `supply` |
| `metrics[].baseline`, `normalization`, `scale` | Same-condition source observations paired with `observations`, normalization rule and optional scale as defined under [scoring](#task-scoring) |
| `scoring` | `method = "layout"`, `area_metric`, positive fixed `area_target`, complete `weights` table and nonempty `rationale`; see [metric weights](#metric-weights) |

A post-layout plan has artifact, DRC and LVS gates on the candidate GDS. Extraction
depends on all three. Performance simulation must consume the extracted circuit,
and the plan must contain at least one performance metric with a limit. Physical
metrics may come from a successful check; performance metrics come from simulation
or post-simulation measurement. Dependency validation checks artifact flow;
backend validation establishes extraction and measurement correctness.

Use separate jobs for operating conditions. Every observation must satisfy its
bounds; `aggregation` affects only the displayed summary. A metric without bounds
has no acceptance threshold, though it may contribute source-paired quality.
An unscored `target` metric requires both bounds; a scored target uses its paired
source value and scale. Units must match exactly. Missing, nonfinite and wrong-unit
measurements are errors; no implicit unit conversion is performed.

Backends receive only the inputs declared for their jobs. The `task` input
provides fields such as `output.top_cell` and `netlist_subcircuit`, without reference
layouts or preparation sources. Inline plans and constraints are available through
`input:evaluation` and `input:constraints`.

### Tool bindings and DRC waivers

A case may include `[toolchain]` with backend
`type`/`settings` under `[toolchain.backends.<id>]` and operation bindings under
`[toolchain.bindings]`. These are host settings, separate from participant inputs.
Task loading validates inputs without starting tools; `load_toolchain` validates
bindings before constructing adapters. See [EDA backends](tools.md#eda-backend-contract).

The KLayout DRC adapter accepts case-local `parameters.waivers`. Each entry names
a report `category`, exact `cell`, a nonempty list of exact `markers` and a
nonempty `reason`. Only those markers are waived; unmatched violations fail.
Waivers apply to reviewed intentional structures and are recorded in the case
plan. The shared PDK deck and archived native report remain unchanged.

<a id="input-isolation"></a>


## Input isolation

Load only the declared task inputs and reviewed resource profiles into a solver
session. Keep witnesses, development probes, other cases, operator credentials
and retained run evidence outside that environment. Check provenance and asset
rights before admitting new inputs. Repository-specific source exclusions belong
to the source owner's internal admission records; they are not package defaults.
