# Tool Environments and EDA Backends

Local evaluation needs Linux x86-64, Python 3.12+, Git, Docker and a compatible
EDA image. The participant host runs the model CLI; isolated solver/evaluator
environments run EDA. [Running](running.md) supplies experiment commands.

This guide has four parts:

- [Setup for users](#setup-for-users): images, Dataset loading, caches, the Agent's PDK view, prepared Python tools and troubleshooting.
- [Evaluation backends](#evaluation-backends): what evaluation guarantees, how open EDA backends judge a layout, process notes and Spectre measurement profiles.
- [PDK resource manifests](#pdk-resource-manifests-for-dataset-authors): process manifests and support preparation for Dataset authors.
- [Commercial runtimes](#commercial-runtimes-for-operators): installed vendor tools, licenses and adapters for operators.

<a id="environment-and-resources"></a>

## Setup for users

This part covers what you need to run evaluations locally with the published
image and a Dataset.

### Prebuilt images and local builds

The open EDA image `docker.io/lizhangmai/iclayout-bench-tools` supports
`linux/amd64`. Each Bench release publishes `v<version>` from the same commit,
and a released package uses that tag by default, so pinning the package also pins
the toolchain. Development installs default to `latest`, which follows the checked
head of `main`. Tasks and PDKs are resolved separately. Print the default and pull
it before running EDA:

```bash
python -m benchmarking.eda image
docker pull "$(python -m benchmarking.eda image)"
```

The runner uses this image by default. Select another compatible image directly
with `--image IMAGE` or `ICLAYOUT_BENCH_IMAGE`; no retagging is required. Use a
registry digest (`name@sha256:...`) when you need an immutable release.
To build the maintained Dockerfile from source, choose your own output tag:

```bash
git clone https://github.com/lizhangmai/ICLayout-Bench.git
cd ICLayout-Bench
docker build --platform linux/amd64 \
  --build-arg HTTP_PROXY --build-arg HTTPS_PROXY --build-arg NO_PROXY \
  -t iclayout-bench-tools:dev .
```

The build forwards your proxy settings. Add `--network host` only when the
proxy listens on a host loopback address.

The unified open image contains Qucs-S/Qucsator, ngspice, Xschem, Magic, Netgen,
OpenVAF, KLayout and the prepared Python tools below. Its label is
`org.iclayout.eda=open`. Preparation, solver work and evaluation use compatible
frozen image identities; each operation retains its own isolation. Harness CLIs
are installed on the participant host separately.

Open EDA resource loading uses an explicit image, then `ICLAYOUT_BENCH_IMAGE`,
then the default open image above. Commercial evaluators run directly on the
operator host and do not resolve or inspect a Docker image.
`scheme.solver_image` or the service's `--solver-image` can choose a distinct
participant image while trusted evaluator bindings remain separate.
`scheme.solver_image` must be a local immutable image ID of the form
`sha256:<64 hex digits>`, as reported by `docker image inspect --format '{{.Id}}'`. Commercial
images and installed vendor tools follow [Commercial runtimes](#external-commercial-runtimes).

### Dataset loading

The public task Dataset is `lizhangmai/ICLayout-Bench`. Supply that repository ID,
another Dataset ID or a directory containing a downloaded Dataset. The package
contains no task tree. Case loading reads source contracts without editing them, verifies
declared inputs and resolves resource bindings in memory. Sessions snapshot only
their declared inputs. Full Dataset metadata and reference assets stay outside
the solver mount.

A repository revision selects a fixed asset snapshot; `--offline` selects cached
data. Hugging Face (HF) owns snapshot downloads, authentication, locking and
cache layout. The Dataset's canonical `data.parquet` indexes its cases.
[Running](running.md#static-dataset-inputs) defines native table selection and
task ordering.

Inspect host prerequisites or prefetch one case's PDK resources without a model:

```bash
python -m benchmarking.eda doctor
python -m benchmarking.eda \
  --dataset lizhangmai/ICLayout-Bench list
python -m benchmarking.eda \
  --dataset lizhangmai/ICLayout-Bench fetch --case NAND2_X1
```

`list` and `fetch` use task and resource declarations and require no reference
layout. Add `--revision DATASET_COMMIT` before the subcommand to select a fixed
Dataset revision. To download a directory for use with other tools:

```bash
hf download lizhangmai/ICLayout-Bench --type dataset --local-dir /path/to/dataset
```

Ordinary candidate evaluation needs no reference. Author reference evaluation
requires a separate snapshot containing the witness; see
[qualification](tasks.md#qualification).

### Resource caches

Set `ICLAYOUT_BENCH_CACHE_DIR` to choose the shared resource cache. Otherwise,
Bench uses `$XDG_CACHE_HOME/iclayout-bench` when `XDG_CACHE_HOME` is set, or
`~/.cache/iclayout-bench`.

| Namespace | Contents |
| --- | --- |
| `pdks/` | Pinned process installations. |
| `derived/` | Generated support profiles and resource bindings. |
| `diagnostics/` | Retained preparation/compiler failure evidence. |

Consumers evict only their own namespace. HF Dataset/Xet blobs remain in their
native cache and are read in place. Caches contain rebuildable inputs; results,
recovery checkpoints and archive databases use explicit persistent paths.
Per-job scratch is disposable tmpfs.

### Agent PDK resources

For each selected process, runtime loading exposes the declared PDK roots and
support profiles through the normal session mount, `/resources`:

- `pdks/<process>/`: read-only bind mounts of reviewed PDK resources. A source
  with `paths` exposes only those relative files or directories, preserving their
  paths below this prefix. Without `paths`, the whole selected root is mounted;
  authors must review it for task solutions, including examples and libraries.
- `support/<profile>/`: the case's evaluator support files, mounted directly from
  the PDK or shared derived cache. Generated startup paths are adapted for this mount.
- `pdk-environment.json`: process identity, source release, container environment
  and optional usage checks, also exposed through the `resources` field of `/protocol/task.json`.

Case preparation stores path bindings, not another filesystem view of the PDK.
Benchmark case references, other case directories and unrelated PDK roots are
not added to the resource mount.

Every process uses `ICLAYOUT_BENCH_PDK`, `PDK_ROOT` and `PDK_PATH`; the namespaced
identifier avoids conflicting with tool-owned settings such as gdsfactory's
`PDK` module selector. `PYTHONPATH` and `KLAYOUT_PATH` are declared only where needed. Explicit Agent
Python/KLayout search paths are appended; conflicting fixed settings are rejected.
The PDK mounts are read-only and the Agent stays non-root and offline. Write
generated layouts, simulator decks and tool caches under `/workspace` or `/tmp`.
For ngspice, use the task's declared startup configuration and model selections;
shared PDK profiles provide model files and compiled modules.

Additional participant tools can be installed in a custom solver image selected
through [participant tool schemes](running.md#participant-tool-schemes).

The tools image resolves Python packages together with upstream PCell APIs.
Its gdsfactory pin preserves `Component.add_array` and `geometry.boolean`, used
by GF180's native generators; its NumPy and gdstk bounds also constrain compatible
SciPy and pandas releases. Check native MOS, guard-ring and passive generation
when changing this dependency line.

### Prepared Python tools

The image's `python` and `python3` select its prepared Python 3.12 environment at
`/opt/iclayout-bench-tools/bin/python`.

| Use | Packages |
| --- | --- |
| Numerical and symbolic calculations | NumPy, SciPy, SymPy. |
| Tables and YAML | pandas, PyYAML. |
| Geometry and graphs | Shapely, NetworkX. |
| Figures and images | Matplotlib, Pillow. |
| Process inspection | psutil. |

The image installs the locked `agent-tools` group included by `eda`; packages are
available offline. NumPy stays below 2 for compatibility with the maintained
stack. Matplotlib uses `Agg` and `/tmp/matplotlib` so scripts can write figures
under the read-only-root policy. Use the explicit image interpreter if a vendor
tool changes `PATH`.

The image also provides `rg`, `jq`, text/shell utilities, Git, Make, patch tools,
archive tools, process inspection and bounded execution utilities. Dependencies
are installed at image build time; solve scripts use the prepared environment.

### Startup troubleshooting

| Symptom | Action |
| --- | --- |
| Docker missing or daemon unreachable | Check `docker version` and the current user's access; run `python -m benchmarking.eda doctor`, which also checks Linux x86-64, Python 3.12+ and Git. |
| Unsupported host architecture | Use Linux x86-64 for the maintained amd64 image. |
| Missing image | Pull/build a compatible image and select it explicitly. |
| Pinned PDK file absent | Run `python -m benchmarking.eda --dataset SOURCE fetch --case ID` and inspect the selected release. |
| Derived support missing | Reload the case to rebuild its content-addressed support binding. |
| Existing evaluation output directory | Choose a new output path; retain the old diagnostics. |
| Image build download failure | Check build connectivity and declared source digests. Forward proxy settings with the build arguments shown under [local builds](#prebuilt-images-and-local-builds); add `--network host` to `docker build` for a host loopback proxy. |
| Model authentication or endpoint failure | Inspect the selected [harness profile](running.md#native-harness-configuration); dry-run does not validate credentials. |

## Evaluation backends

This part is the public measurement contract: how evaluation judges a frozen
layout and what its reports mean.

### What evaluation guarantees

Evaluation judges a frozen candidate with trusted task materials and the
backends bound by the task toolchain. [Evaluation results](tasks.md#evaluation)
defines step statuses and scoring precedence; the sections below give details.

| Topic | Guarantee |
| --- | --- |
| Results | Each job is `passed`, `failed` (a completed candidate rejection, which scores zero) or `error` (evaluation could not judge it; the score is unknown). Jobs whose prerequisites did not pass are `blocked`. |
| Exit status | Standalone `evaluate` exits 0 when evaluation passes, 1 for a completed rejection and 2 for an error, an incomplete result or invalid configuration. |
| Time limits | EDA jobs have no automatic time limit; see [time limits](#evaluation-time-limits-and-cancellation). |
| Retries | At most three attempts, only for explicit tool crashes and transient license checkout failures; rejections are never retried. See [retries](#automatic-tool-retries). |
| Evidence | A new output directory holds `report.json` and content-addressed `artifacts/`. Each job entry in `report.json` records its status, reason, measurements, outputs and evidence; a retried job adds `tool-attempts.json` and `tool-attempts/N/…` evidence. |

### EDA backend contract

A [task toolchain](tasks.md#tool-bindings-and-drc-waivers) binds logical operations
to trusted backend types/settings. `evaluate` uses the case's embedded toolchain
unless explicitly overridden. `characterize` requires an explicit toolchain.
When the selected toolchain is embedded in a case with declared resource profiles
or an external runtime, these commands prepare and bind those resources through
the same loader as participant sessions. They do not require author-prepared
support directories or reference layouts. `--image` and `ICLAYOUT_BENCH_IMAGE`
override the selected tool image.

#### Isolation and resource limits

The shared Docker executor uses a read-only image, declared read-only resource
mounts and tmpfs workspaces. Inputs/outputs stream through Docker exec. Solver
sessions provide writable `/tmp` and `/var/tmp` (64 MiB each) and a bounded
workspace; tool invocations also use disposable writable scratch. Tool processes
stop before declared outputs are collected, including after failures/timeouts.
Only retained evidence reaches durable host storage.

CPU, memory and PID quotas default to null for solvers, evaluator tools and
version probes. Explicit supported limits are applied and recorded. Operators
manage aggregate load with experiment concurrency and backend job/thread settings;
those scheduling settings do not themselves impose a Docker CPU quota. Files,
logs, workspace sizes and network/input isolation remain separately bounded.

#### Evaluation scheduling and timing

The evaluator batches ready consecutive jobs only when their backend advertises
`max_parallel_jobs`; other backends are serial. Dependencies gate execution, job
workspaces are isolated, and results retain plan order. A failed corner does not
cancel independent corners. Backend-specific concurrency and thread settings are
specified in [Open backends](#ngspice-and-magic) and
[Commercial runtimes](#spectre).

Evaluation reports record wall-clock time and each job's `elapsed_seconds`;
blocked jobs have zero execution time. Concurrent job durations overlap, so their
sum is not evaluation wall time. Resource preparation precedes that interval.

#### Evaluation time limits and cancellation

EDA jobs have no automatic time limit by default. This covers session feedback,
final judging, standalone evaluation, characterization, qualification and
preview. Declared backend `timeout_seconds` values bound tool version probes;
they are not applied automatically to evaluation jobs, and the service does not
derive an evaluation deadline from them.

The local service sets no command or final-judging deadline; the
[session protocol](architecture.md#lifecycle-and-budgets) defines the phase
budgets. A workspace command may request an explicit timeout, and process
feedback started by that command inherits its deadline. Nested calls, retries and
parallel jobs share the enclosing deadline, and a job that reaches it is stopped.
Tool failure and cancellation evidence remains available with the accepted
candidate.

Cancelling a process check propagates to native/container jobs and their parallel
workers. Cancelled jobs retain diagnostics and cannot publish successful
extraction. Later checks and final judging use independent cancellation scopes.

#### Automatic tool retries

The shared native/container executor permits at most three attempts for an
immutable EDA job, waiting one and then two seconds before the next attempts. It
retries only failures that the native diagnostic explicitly identifies: tool
crashes and transient license checkout failures, such as an unavailable feature,
all licenses in use or an unreachable license server. Invalid license files,
hosts or keys and expired features are not retried, nor are unrecognized exits
and input errors. Completed DRC/LVS rejections and measurement failures
remain candidate/evaluation results; they are not retried to seek a better score.

Each attempt uses the same frozen command, inputs, declared resources and tool
identity in a fresh directory or container. Failed processes are stopped before
another attempt starts. Only the last attempt supplies outputs to the backend's
normal completion and result checks. Retry exhaustion remains an evaluation error
with an unknown score, never a fabricated zero or pass.

The retry policy is recorded in the tool identity. When recovery is attempted,
`tool-attempts.json` records attempts, exit codes, failure classifications,
elapsed time and termination; `tool-attempts/N/` retains earlier logs and partial
outputs. These older diagnostics cannot override the final attempt's failure
classification. Report wall time includes attempts and backoff, and retries do
not renew an enclosing command or diagnostic deadline. Cancellation also stops
backoff and prevents another launch. This recovery does not restart a participant
or replay arbitrary solver workspace commands.
Native tools record process/thread states before termination without retaining
command arguments or environment values in those snapshots.

### Open EDA and geometry backends

Bind logical operations using the [task toolchain contract](tasks.md#tool-bindings-and-drc-waivers).
Each backend below defines its settings, required evidence and failure behavior.

#### ngspice and Magic

The tools image provides Ngspice with XSPICE, OSDI and KLU support. Its
`/opt/ngspice/bin` executable takes precedence over a distribution copy that
may remain installed for GUI dependencies. The ngspice backend defaults to
four concurrent jobs and one model thread per job. Its existing backend
`settings` table accepts positive integer
`max_parallel_jobs`, `threads`, and `cpu_budget`:

| Setting | Default | Meaning |
| --- | ---: | --- |
| `max_parallel_jobs` | 4 | Concurrent independent simulation jobs. |
| `threads` | 1 | Model threads per job. |
| `cpu_budget` | 8 | Upper bound on the product of jobs and threads. |

`max_parallel_jobs * threads` must not exceed `cpu_budget`. This scheduling budget
does not impose a Docker CPU quota. For example, eight independent jobs with
one thread each use `max_parallel_jobs = 8`, `threads = 1`, `cpu_budget = 8`.
Two jobs with four threads each use `max_parallel_jobs = 2`, `threads = 4` with
the same budget. Select these settings from measured case workloads.

The adapter appends `set num_threads` to the existing simulator startup without
discarding model initialization, and sets both `OMP_NUM_THREADS` and
`OMP_THREAD_LIMIT`. A deck may request fewer model threads; the environment caps
its OpenMP threads at the configured allocation. Resource settings and the
effective startup are retained in evaluation evidence. The CPU budget bounds
this backend's job/thread allocation, not all simultaneous sessions. Concurrent
jobs may have explicit container memory limits; by default they are uncapped.
Operators must also account for aggregate CPU and memory use across sessions.
When a job supplies an explicit `startup` input, that native file is used unchanged;
its thread selection belongs to the case and the backend's thread environment
continues to bound the allocation.

##### Simulation inputs

ngspice writes each input role as `<role>.spice` and uses `deck.spice` as its entry
point. The optional `startup` role accepts native startup text, written unchanged
as `.spiceinit` and selected through `SPICE_USERINIT_DIR`. It takes precedence over
support initialization; model loading, compatibility, search paths and simulator
thread settings must be declared by the case. Do not also set backend
`compatibility` when supplying a startup file. The declared testbench selects
analyses and measurements:

Model files may come from shared PDK resources. Model sections, process corners
and statistical switches are selected by the case's SPICE testbench or its
declared model-entry input.

| Job parameter | Purpose |
| --- | --- |
| `values` | Generate `parameters.spice`. |
| `measurements` | Declare measurement names and units. |
| `exports` | Name declared output artifacts. |

Exit 0 still requires a complete set of finite measurements.
After normal execution with analysis data, an explicit ngspice WHEN/TRIG/TARG
"out of interval" verdict for a declared measurement, accompanied by its failed
measurement command, is a candidate rejection (`failed`). Missing or ambiguous
scalars alone, invalid values, model/execution errors and crashes remain `error`.
Execution and report failures are checked before accepting a measurement verdict.

For high-impedance cores with low-ohmic extracted wiring, trusted ngspice backend
settings may select `resistor_formulation = "branch"` (default: `"conductance"`).
This represents each positive, literal, four-field R card in non-deck input roles
by a zero-volt series sensor and a CCVS imposing `V = R*I`, avoiding large `1/R`
nodal stamps. It retains every terminal and value; it adds no bias or leakage.
PDK support and model files are unchanged. Extended/model/TC
resistor cards and generated-name collisions are rejected. The original input
digest remains in the report; `effective_<role>` evidence records the actual
simulator netlist, and the formulation is part of backend identity.
This deterministic equivalent supports OP/DC/AC/transient analysis but omits
resistor thermal noise, so noise analysis is rejected in branch mode. Changing
matrix formulation does not establish convergence or permit relaxed validity
checks. Internal current sensors are excluded from external power/KCL ports.

For upstream flows requiring HSPICE-style syntax, `ngspice-docker` accepts
`compatibility = "hsa"`. The effective `.spiceinit` is archived and the choice
is part of backend identity. The default remains the prepared model profile's
startup. Use ngspice 45 or later for the
[SG13G2 HBT flow](#hbt-core-simulation-support).

##### Magic extraction

Magic takes the top cell and ordered `ports` from trusted configuration. Match
that interface to the authoritative netlist; later jobs consume the exported
netlist as-is. `magic-capacitance-docker` extracts capacitance only and records
`wire_resistance=false`. `magic-rc-docker` adds distributed resistance and
capacitance and can bind to `layout.extract_rc`.

Magic's SPICE export rewrites some characters in port names. Before Magic
extraction, interface names that are not simple identifiers (letters, digits and
underscores, not starting with a digit), such as `!CONTROL`, receive unique
aliases on an isolated GDS copy. The adapter preserves the original candidate
and mapping evidence, and then uses the native SPICE reader to check the count,
names, and order of exported ports. It does not rewrite the original task
netlist; simulation connects through the declared port order.

Magic import can be configured with `gds_readonly=false` when a technology must
rescale its native import grid to represent the candidate DBU exactly. This does
not permit writes to the submitted GDS: preprocessing and import still operate
on isolated copies. The default remains `true`. Optional positive integer `grid_subdivision` (default 1)
refines the internal Magic grid before import, using `scalegrid 1 N`, so labels
and devices share the same resolution during resistance extraction. Ambiguous
styles are configuration errors. Missing gate connections and orphaned-node
substitutions reject an unusable candidate extraction even if Magic writes a
netlist. Native interface validation reports explicit `passed`/`failed` verdicts;
after successful tool execution, an explicit candidate rejection takes precedence
over generic console-error matching. Its reason is returned in `check` and report
feedback; the native console and other job files are readable under
[`/checks`](architecture.md#check-files) during the solve. Tool crashes,
execution/cleanup failures and missing/malformed interface reports remain `error`.
Optional `label_layers` is a
nonempty list of GDS layer/datatype pairs that may contain electrical text;
text on other layers is removed from the extraction copy without removing any
geometry. Optional `gds_ignore_layers` lists unique GDS layer/datatype pairs
that the task explicitly excludes from Magic import. The adapter adds native
`ignore` and `calma` declarations to each inline `cifinput` style in a job-local
copy of the technology file. It preserves the shared support bundle and candidate
GDS; the selected pairs enter backend identity, and the effective technology is
retained as `import_technology` evidence. No layers are ignored by default.
Other unmapped layers still report native input errors; import warnings remain
enabled. Styles defined through an `include` inside `cifinput` require an inline
definition before using this setting.
`case_insensitive_ports=true` aliases case variants to unique internal
names before extraction, matching SPICE's port-name semantics. The defaults
preserve all labels and use case-sensitive matching. Settings, alias mappings,
ignored-label counts and the geometric flattening check are archived. The
selected Dataset documents the predictive model, coefficient provenance and
extraction controls for each configured technology.

The RC adapter requires Magic 8.3.653 or newer. It uses a geometrically checked,
flattened extraction copy, keeps devices separate, and sets resistance selection,
minimum resistance, and delay thresholds to zero with network simplification
disabled. `capacitance_threshold_ff` controls capacitance omission and defaults
to zero. These controls enter the extraction evidence.
Raw extraction, resistance,
topology, feedback, and port/geometry checks are retained with the result.

An optional native model interface pairs `model_support` with
`model_technology`, the KPEX technology JSON path inside that support bundle.
Select a Magic extraction style that emits SI geometry. The interface reads
Magic's `.ext` parameter declarations and the technology's model units to
serialize the same extracted physical parameters for simulation. It preserves
model names, terminal order and multiplicities, and copies native interconnect
R/C cards without changing their values or connections. It reads no source
circuit. Missing unit declarations, unsupported model interfaces and missing
geometry are errors. The original native parameter export remains in evidence.

When wire-resistance extraction is enabled, the RC adapter also compares port pairs
joined by resistor cards in the native topology and final RC exports. It rejects a
new resistor-only connection between previously separate topology ports,
including unintended isolated-body/substrate connections. Intentional resistor
connections already present in the topology remain allowed. This guard does
not prove internal device-terminal graph equivalence or substrate accuracy;
case-specific physical mapping and electrical calibration are still required.

Native network reduction can vary in low-level ordering, so byte-identical RC
netlists are not guaranteed across tool versions or runs. Compare extracted
results against the declared task measurements and tolerances.

By default, the RC interface requires one declared port per conductor. A native
topology check rejects aliases because repeated extraction can duplicate their
resistance networks. `resistance_net_selection = "canonical"` instead selects
only native `node`/`substrate` names from the `.ext` file with `extresist include`.
This permits same-conductor ports while retaining the check against new resistor
paths between originally distinct topology nets. Missing native gate, substrate,
source/drain connections and orphaned nodes reject an incomplete extraction.

#### Native Magic external layout fixtures

`magic-fixture-rc-docker` extracts a frozen candidate together with a separately
declared external GDS fixture. It uses canonical native net selection. Inputs
are `layout` and `fixture` GDS assets and `constraints` JSON; the output is one
`netlist` SPICE asset. Independent DRC/LVS and geometry gates remain required
for the candidate.

Job parameters declare `top_cell`, ordered candidate `ports`, `fixture_top`,
ordered `fixture_ports`, corresponding local `fixture_nets`, `outline_constraint`, and a SPICE identifier
`fixture_flag`. Optional `excluded_layers` lists drawing-layer pairs outside
the selected extraction scope. The alignment constraint must be a declared
`bbox_max` constraint. The candidate's functional centre is translated to the
origin on its native database grid. A native geometry comparison verifies the
translation; reserved fixture-label or extraction-cell collisions, excluded drawing layers and
fixture/candidate overlap reject the candidate. The supplied fixture is placed
at its fixed coordinates. Its database unit must match the candidate.

All devices and parasitic cards are emitted by Magic from that combined layout.
The native combined layout is extracted under the reserved internal circuit name
`LB_EXTERNAL_EXTRACTED`. The
adapter appends a port-only wrapper under `top_cell`, binding candidate ports
and the declared local `fixture_nets` to those existing native terminals, plus
`.param <fixture_flag>=1`. The fixed simulation deck can then retain the same
candidate interface as its ideal source anchor. It does not construct physical R/C models, patch native
cards, or inject current at inferred body nodes. Evidence retains the supplied
fixture, preparation report, combined GDS and unmodified native extraction.
Physical coverage follows the selected technology and extraction model; adding
an external fixture does not establish unmodeled well or substrate mechanisms.

#### Magic and Netgen Physical Checks

`magic-physical-docker` binds independently to `layout.drc` or `layout.lvs`.
Trusted settings select `check`, `technology`, `tech_name`, `style`, the frozen
`support` bundle, and optional positive `grid_subdivision`. LVS additionally
requires a bundled Netgen `setup`; DRC must not specify it. Top-cell and source
subcircuit names come from the task. Candidate-provided extracted netlists are
not accepted as LVS evidence.

LVS also accepts the paired `model_support` and `model_technology` settings
described under Magic extraction. In that mode it exports a flat native SI
circuit, applies the declared model interface, and compares it with the original
trusted source through Netgen. The model interface never reads that source.

DRC imports the GDS, verifies the active native rule style, runs the complete
check and requires a completion marker and a nonnegative native violation count.
LVS extracts the candidate independently, invokes Netgen against the trusted
source, and reads its JSON comparisons. Matching exit status alone is
insufficient: the top comparison must contain devices, pins and net counts must
match, and no hierarchy, element or property mismatch may remain. Missing or
malformed reports are errors. Netgen can omit a hierarchy's pin comparison after
reporting a connectivity, device-count or property mismatch; that completed
rejection fails LVS and scores zero. Missing pins without a conclusive mismatch
remain an error. A completed candidate extraction containing no
devices, or a completed empty/black-box top comparison, fails LVS and scores zero;
it does not require a usable Netgen comparison to establish rejection. Native
logs, scripts and comparison evidence are retained. The image pins Netgen 1.5.323
in the public Dockerfile.

PDK-specific unit conventions and any reviewed technology transformations belong
to the task resource manifest. They are included in the support digest; the
adapter does not silently repair source parameters or waive native rules.

#### KLayout Physical Checks

`klayout-docker` selects `check = "artifact"`, `"drc"` or `"lvs"`. A job supplies
`layout` and `task`; LVS also supplies the authoritative `netlist`. Standalone
debugging can declare `parameters.top_cell`, `max_bytes` and the LVS `subcircuit`;
these must agree with `task` when both are supplied.

| Check | Required evidence |
| --- | --- |
| Artifact | Readable GDSII, published size bound, correct top cell, nonempty geometry and resolved hierarchy. |
| DRC | Completed declared decks, required report categories and zero unwaived violations. |
| LVS | Completed comparison against a nonempty trusted source, participation of the requested circuit and the declared named-port checks. |

DRC/LVS settings declare fixed `variables`, passed unchanged as KLayout `-rd`
arguments. DRC requires a native `deck` path. LVS selects either a support `deck`
or a job input named `lvs_macro` with format `text`, containing a native XML
`.lylvs` macro. Declare a case-owned macro as an evaluator input when it is only
needed for independent evaluation. The two LVS control sources are mutually
exclusive; the input macro is retained in the run evidence.

DRC decks accept plain `.drc` scripts and native XML `.lydrc` macros; LVS decks
accept `.lvs` and `.lylvs`. XML macros run through KLayout's `RBA::Macro` API,
using the native DRC or LVS interpreter
and retaining the source path for relative includes. The runner adds its completion
marker to the macro's in-memory body without modifying the declared source.
An early exit, macro execution error or invalid report cannot establish a pass.
An input `lvs_macro` is staged as `task.lylvs` at the support bundle root, so its
native relative includes resolve against that bundle. This filename is reserved
when an input macro is supplied.

For LVS runsets with a fixed default output, `default_report` names that relative
file. The runner omits the `report` variable and collects the native database as
`report.db`; the runset source stays unchanged. XML macro instrumentation starts
on a new line, including when the native macro has no final newline.

LVS can explicitly set `flatten = true` to flatten the selected candidate top
cell with KLayout before comparison. The copy preserves labels and is retained
as `flat-candidate.gds`; the frozen submission and its binding stay unchanged.
Hierarchy, tolerances, virtual connections and pin equivalence otherwise belong
to the declared native controls. Port matching defaults to `named`, checking each
matched pin's name. `port_matching = "native"` accepts the native comparer's pin
correspondence while requiring the complete published pin-name set; callers must
verify interface behavior through their declared electrical tests. This supports
standard-cell tasks with interchangeable logic inputs without copying PDK pin
tables into the adapter.

DRC also declares `required_categories`; optional `additional_decks` entries each
declare `deck` and `required_categories` with the same variables. Every deck runs
independently. Any execution/report error
takes precedence; otherwise the gate sums counts and fails if any deck fails.
Required categories detect skipped groups rather than enumerating every rule.
LVS may declare `layer_names` for geometry checks consuming its database.
These settings can be shared in a [PDK backend declaration](#pdk-manifests).
The existing `profile` setting reads a JSON resource containing the same settings;
it cannot be combined with direct rule settings. Explanatory scope belongs in
the task documentation and is not required by the native invocation.

Per-deck `report.db`, `report-1.db`, logs and completion markers remain separate
evidence with per-deck results. Reviewed case-local `parameters.waivers` select
exact markers under the [task waiver contract](tasks.md#tool-bindings-and-drc-waivers).
For LVS, `ignore_top_ports_mismatch` controls additional named-port checks.

A missing report, skipped run, crash or timeout is `error`; a completed check with
unwaived violations is `failed`. LVS database output is diagnostic evidence;
post-layout simulation uses a separate extraction job from the same candidate.

<a id="geometry"></a>

#### Geometry and Port Correspondence

`klayout-geometry-docker` interprets the geometry constraints, supplied as a JSON
snapshot from either `[task.constraints]` or a declared constraints file.
`bbox_max` declares `functional_layers` and hard maximum width and height.
The `quality` measurement `functional_bbox_area` declares either its own
`functional_layers` or `layers_from` naming an existing `bbox_max` rule, never
both. Each layer is a `[layer, datatype]` pair. Area is the bounding-box area of
all geometry on the selected layers; empty functional geometry fails measurement.
An area objective alone needs no size limit and may use an empty `hard` list.
An explicit `bbox_max` remains a validity gate; use it only for a justified
implementation envelope, following [validity and quality](tasks.md#validity-and-quality).

The `klayout-geometry-docker` backend can evaluate `bbox_max` and functional
area objectives directly from GDS after independent physical gates. Tasks using
this mode omit `database` and `binding`. Connectivity-dependent constraints still
require both the native KLayout LVS database and its exact candidate binding;
omitting either cannot bypass connectivity validation.

LVS can export a native `klayout-lvs` database and a JSON binding. The binding
records the candidate GDS, database digest, top cell, and logical-layer mapping.
After validating the binding, the geometry adapter uses the native LVS database
APIs for network correspondence and geometry. Process support bundles declare
deck-layer variables; the adapter reads the names actually registered by the run
instead of fixing runtime indices such as `l10`, and it does not modify upstream
rules.

`named_metal_ports` names each port, its drawing/pin/text layers, logical connection
layer, and minimum square side that can be contacted. The top cell must contain
exactly one label with each required name. Its center square must lie completely
in the intersection of the pin, drawing, and correctly extracted network regions.
Adapters extend the set of constraint kinds; the generic plan executor does not
interpret process layers or geometry semantics.

`cell_frame` checks a standard cell's complete `functional_layers` bounding box:
fixed `height_um` and integral `width_grid_um` within half the candidate DBU.
Its nonempty `rails` list declares unique supply `name`, drawing `layer`, native
`connectivity_layer`, centre `y_um`, minimum `thickness_um` and `left_um`/`right_um`
insets. Coordinates are relative to the functional lower-left bound, so global
translation is allowed. Each required strip must be continuously covered by metal
on the supply net matched through LVS. A text label alone is insufficient.
This row-interface check does not establish neighbor abutment or external pin access.

#### Fixed passive macros

`fixed-macros-docker` checks immutable layout cells before a separate native
LVS and extraction. A `layout.fixed_macros` check consumes `layout` (candidate
GDS), `task` (JSON), `library` (trusted GDS) and `specification` (trusted JSON),
and exports `layout = "gds"` and `binding = "json"`. Settings are `image` and
`timeout_seconds`. Use a check without a gate; the downstream LVS gate and
extractor require its successful outputs. DRC always checks the original GDS.

The specification contains a nonempty `macros` list. Each entry names a `cell`,
its original `translation_dbu`, nonnegative `clearance_dbu`, `abstract` boolean,
`contact_layers` and `ports`. Exactly one physical instance of each cell is
required. Flattened per-layer polygons and texts must equal the library, and
the cells must retain their relative placement and ground context. Only a
shared translation, grid-preserving quarter turn or reflection is accepted.
Each contact rule maps a drawing `body` layer to its contacting `contacts`
layers, using `[layer, datatype]` pairs. Candidate geometry on those layers
must not enter the protected macro body outside exposed terminal landings.

A port declares `name`, drawing `layer`, `text_layers`, `box_dbu` and `extract`.
Its landing is the intersection of existing macro metal with the box; the
adapter never inserts missing metal. Abstracted macro bodies are removed from
the extraction copy, retaining these existing landings and their declared
native-tool labels. Fixture-only ports use `extract = false` and allow no
free-circuit attachment. Context cells use `abstract = false` and remain in
the extraction copy. All non-macro candidate devices and wiring are retained.

KLayout LVS and SG13G2 HBT RC jobs can consume this derived `layout` together
with `original = "candidate"` and the verifier's `binding`. They check both
GDS digests and the top cell before native processing, retaining the proof as
evidence. Do not bypass native LVS of the exposed terminals. Simulation must
combine the extracted free circuit with the declared fixed-macro models;
source active devices and reference wiring cannot supplement candidate PEX.
Authors must establish model/geometry correspondence, ordered terminals,
ground context, frequency coverage and approximation limits, then validate
negative geometry/connection controls and candidate-dependent performance.
This boundary does not establish full-wave accuracy of inherited models.

<a id="kpex-coupling-capacitance"></a>

#### KPEX coupling capacitance and distributed RC

The `kpex-cc-docker` backend provides nominal 2.5D coupling capacitance;
`kpex-rc-docker` adds distributed wire and contact/via resistance. Both use
KPEX's native consistency checks, blackbox modeled devices and retain coupling
capacitance. RC extraction does not reduce the network. Neither mode extracts
inductance or establishes device/well resistance coverage beyond its native
technology definition.

For maintained KPEX resources, declare `support`, `pdk`, `deck` and `technology`
together. `deck` and `technology` are paths within the prepared support profile;
KPEX uses those selected files rather than its implicit package defaults.
`variables` supplies native deck settings, `top_cell_variable` names its top-cell
argument (default `topcell`), and `substrate_node` names the native ideal
reference plane (default `VSUBS`). The job declares `ports`, `substrate` and the
top cell. An optional `substrate_variable` passes the job's existing substrate
name to the native deck (for example SKY130's `lvs_sub`). Only the reference-plane name may be aliased to the declared
substrate port. Device models, terminal order and parameter conversions come
from the unmodified KPEX technology definition. Unsupported models fail.

An independent LVS job supplies the candidate database and binding. The KPEX
deck re-extracts the same GDS, then KLayout compares its native device netlist
directly with that candidate database before PEX. The comparison must match.
This comparison uses no source or reference-layout devices. RC output must
preserve the existing named ports and native terminal-to-wire connections.

The `kpex-netgen-docker` LVS backend extracts devices with the maintained KPEX
deck, serializes their model calls through KPEX's native technology definition,
and independently compares them with the original source SPICE using Netgen.
It adds `netgen_support` and `setup` settings to the managed resource settings
above. A check job supplies `layout`, `netlist`, and optionally `task`, declares
the substrate port, and produces `database = "klayout-lvs"` and
`binding = "json"`. Without a task input, it also declares `top_cell` and
`subcircuit`. Only a successful full Netgen comparison exports those outputs.
The PEX deck's comparison with a dummy schematic establishes geometry; it is
not treated as a source LVS result.

The CC backend also accepts the earlier explicit process interface:
An explicit JSON `process` job input declares the process name, bundled native
LVS deck, runset variables, substrate reference node and physical device
interfaces. Each device declares terminal order, extracted parameter units,
native reference-card prefix, and any supported-value constraints. Parameters
are read from native devices; the adapter never supplies missing geometry.
The frozen process input enters job evidence. Tool settings include `image` and
`timeout_seconds`. Legacy `support` and `profile` settings remain available as a
pair, record their process and manifest in backend identity, and cannot be
combined with a process input. Task-specific device limits belong to case inputs.

Jobs consume candidate GDS, its native LVS database and a content binding.
When a prior fixed-macro job emits an extraction copy, optional `original` and
`derivation` inputs must be supplied together. Their content proof binds the
original submission, cut GDS and top cell; the independent native LVS binding
still binds that cut GDS to its candidate database. Both proofs enter evidence.
For the earlier explicit process interface, the backend independently extracts
annotated geometry, compares it against a reference exported from that candidate
database, and consumes the persisted native LVS verdict. It preserves the
process's device and terminal-equivalence rules. Physical classes are serialized through the declared interface, including
classes whose native geometry differs from KPEX's primitive writer API.
Undeclared models, unsupported geometry and missing or additional ports fail.
The process reference plane is bound to the task's declared ideal substrate.
The ordinary tool logs retain both databases, the candidate-derived reference,
configuration and extracted netlist. Tasks explicitly choose CC or RC scope.

#### Qucs-S and Qucsator

The unified image provides `qucs-s`, `qucsator`, `qucsator_rf` and `qucsconv`
alongside ngspice. Qucs-S parses/netlists `.sch` files headlessly with
`QT_QPA_PLATFORM=offscreen`; simulation still selects an explicit backend.

The image does not provide Xyce. A task requiring Xyce needs a compatible runtime
and backend; Qucsator is not a substitute for that simulator.

The pinned ngspice build includes an `xfer` DC Jacobian correction for
operating-point convergence. `xfer` does not provide S-parameter thermal noise
or transient support; those analyses require an appropriate passive model.

### Process notes: IHP SG13G2

These notes apply only to cases using the IHP SG13G2 resources declared in the
Dataset's `tasks/ihp-sg13g2/pdk.toml`.

#### IHP physical-check profiles

IHP resources come from one pinned ciel release with `sg13g2_pr` and common
technology files. The model, KLayout, Magic and PCell selections use that release's
native contents. PSP and passive Verilog-A sources are compiled with the selected
tools image during support preparation. Agent resources include the required
PCell Python dependencies from the prebuilt package; no nested Git initialization
or local open-pdks build is needed. The per-file PCell view uses the same cache.

Prepare support from the `klayout` profile in `tasks/ihp-sg13g2/pdk.toml`.
Frozen bundles are not updated in place; prepare a new bundle when the manifest
changes. Cases select their check profiles through `[toolchain]`.

| Profile | Scope |
|---|---|
| `drc-main-maximal` | Main plus extra `sg13g2_maximal.drc`, deep mode, density and antenna off. |
| `lvs-explicit-taps` | Explicit taps, native simplification and strict named ports. |
| `lvs-logical-mos` | Native logical MOS comparison and physical body connectivity, without schematic tap devices. |

These are native backend declarations selected through `from_pdk`. The upstream
LVS reader consumes the declared CDL representation. Dataset authors can use the
PDK's Xschem simulation and `lvs_format` netlisting modes to derive both tool
representations from one authoritative circuit. Author consistency checks belong
with the case; no global model-call reader override is required.

The `magic` support profile retains the pinned upstream technology files.
The `kpex` profile reads SG13G2's maintained PEX deck, technology JSON and license
from the pinned `klayout-pex` distribution in the tools image. Cases selecting
`kpex-rc` use these native model interfaces and unreduced distributed RC, with
candidate devices checked against their independent LVS database. These profiles
require no Dataset-local PDK patches. Device and connectivity controls belong to
the author qualification; they do not establish fabrication or RF signoff.
Candidate scoring simulates only GDS-derived PEX.

Evaluate the maintained circuit and candidate using the case's declared task
plan. See the [evaluation command](running.md#standalone-evaluation) and each case problem
for reference results and reproduction instructions.

#### SG13G2 well and substrate ties

SG13G2 Magic extraction treats well/substrate ties as ideal connections;
it does not preserve the finite `ntap1`/`ptap1` resistance cards used by the
source simulator netlists. Physical LVS can still
check explicit tap geometry. Cases using this RC boundary must disclose the
idealization and calibrate its effect on their declared nominal measurements.
It does not establish distributed well/substrate resistance or substrate-noise
accuracy.

#### HBT core simulation support

The HBT model profile (Dataset: `tasks/ihp-sg13g2/pdk.toml`) prepares the pinned
HBT, resistor and capacitor include closure, using native ngspice VBIC and
OpenVAF-compiled R3_CMC and MoM models. The source retains the R3_CMC license and
NOTICE with the IHP adaptation. No compact-model source is patched.
The `sg13g2-hbt-rc-docker` backend combines candidate-only KLayout native
HBT extraction with Magic distributed interconnect R/C. Its `klayout_support`
and `magic_support` settings use separately reviewed bundles; declare their
profiles through `support_profiles` in the [resource manifest](#agent-resource-declarations). Physical LVS remains a
separate gate against the maintained circuit, including the named interface.
Choose its native KLayout LVS deck with `klayout_deck`, optional
`klayout_variables` and `klayout_layer_names`. The alternative `klayout_profile`
loads a JSON rule profile and cannot be combined with those direct settings.
For the fixed `npn13G2` emitter, the native extractor reports bounding-box X/Y
dimensions as `we`/`le`. The adapter accepts the complete 70 × 900 nm pair in
either axis order, preserving native `Nx` and terminal connections and passing
only the fixed symbol's behavioral parameters to simulation. Other dimensions
remain errors. Native LVS still checks the source's declared geometry; this
serialization rule does not alter its comparison options or the PDK deck.

The SG13G2 Magic support profile declares the emitter-to-Metal1 connection in its
process manifest. HBT graph matching uses retained native resistor geometry and
named tail ports to distinguish otherwise identical branches. Ambiguous graphs
fail, and all passive and final-RC connectivity checks remain mandatory.

For a declared ideal-body compact-model boundary, the optional boolean
`disable_tap_extraction = true` setting enables the pinned KLayout PDK's
standard tap-connection mode in the candidate extraction only. The default is
`false`. The selected value is recorded in backend identity and the frozen
extraction configuration; it does not change the separate physical LVS
profile. A case using this mode must retain physical tap checks, disclose the
omitted well/substrate/tap resistance and calibrate finite-tap versus ideal-body
behavior under its declared testbench and models.

The adapter preserves extracted HBT multiplicity and validates the drawn
geometry against the compact-device interface. Fixed drawn emitter dimensions
are not passed as effective model dimensions. It checks passive geometry and
connectivity across KLayout, Magic topology and the final RC output, and retains
Magic's external R/C network. Ambiguous mappings, unsupported cards or missing
connectivity evidence fail extraction. Every local HBT endpoint must retain its
native connection or an explicitly extracted wire path; isolated terminals are
rejected rather than reconnected to a port or passive anchor. Tap models require
native extracted resistance; the adapter does not derive resistance from area
and perimeter. The mapping and original outputs remain evaluation evidence.

Magic represents the supported SG13G2 HBTs as native `msubckt` devices.
Its resistance extractor can emit MOS-named missing gate/drain/substrate
contact diagnostics for these compact-device contacts. The HBT composite
backend defers a terminal diagnostic only when its exact device coordinate,
supported HBT model and named terminal agree with the native `.ext` record.
Missing, ambiguous or contradictory evidence is an extraction error. The
standalone Magic backend retains its strict missing-gate rejection; there is
no case-level warning waiver.

Deferral is not acceptance: the composite backend must still complete the
KLayout/topology/final-RC correspondence, preserve proven external wire paths
and pass every device/passive check above. Orphaned-node, tool-error and other
unreviewed diagnostics remain fatal. The complete console log and structured
`magic:terminal_diagnostic_review` evidence are retained alongside `mapping`.
The reviewer implementation and policy are included in backend identity.

Distributed-RC compact-model simulation does not establish RF/EM behavior,
noise or statistical corners. Those require separately declared extraction
and validation scope in the selected task contract.

### Native openEMS networks

`openems-docker` runs an explicitly prepared EM geometry through a reviewed
PDK's native GDS reader, material stack, mesh generator, FDTD setup and
S-parameter postprocessor. The open EDA image includes the pinned upstream
CSXCAD/openEMS Python bindings. The backend settings are `image`, `support`,
`workflow` (the workflow module directory inside the support bundle),
`stackup` (the native XML path), `timeout_seconds` and `memory_mb`.

An extraction job accepts `layout` in GDS format and `ports` in JSON format,
and returns `network` in Touchstone format. The port list is ordered and
numbered consecutively from one. Every port uses a distinct non-material GDS
layer containing its native port geometry:

```json
[
  {"number": 1, "source_layer": 201, "impedance": 50,
   "from_layer": "Metal3", "to_layer": "TopMetal2", "direction": "z"},
  {"number": 2, "source_layer": 202, "impedance": 50,
   "target_layer": "Metal2", "direction": "x"}
]
```

Via ports declare `from_layer` and `to_layer`; in-plane ports declare
`target_layer`. Directions are `x`, `y`, `z` or their negative forms. Job
parameters explicitly supply `fstart`, `fstop`, `numfreq`, `cellsize`, `margin`,
`energy_limit` in dB, six `boundaries`, and `threads`. Optional
`merge_polygon_size` selects the native via-array merge distance; its default
is zero. Lengths use micrometers and frequencies use Hz. Every port is excited
separately, producing the complete network. Missing port geometry and port
layers that collide with a native material layer are errors. Native field
outputs and network diagnostics remain execution evidence.

An optional `model` SPICE output requires a `model` parameter object with
`real_poles`, `complex_poles`, `fit_constant` and `maximum_error`. The native
scikit-rf vector fitter and exporter produce a stable, passive network within
the declared maximum complex S error on the complete sampling grid. The
subcircuit is named `EM_NETWORK` and orders its pins as
`p1 p1_ref p2 p2_ref ...`. For ngspice, exported resistances smaller than its
literal-value limit are expressed as `1 scale=<original resistance>` using
the simulator's native instance parameter. The effective resistance is
unchanged; both exported representations remain evidence. Passivity or fitting
errors reject the model.


An optional prepared SPICE `circuit` input requests an assembled `netlist`
output. Optional SPICE `models` supplies its model definitions. The adapter
concatenates these declared bytes and the fitted EM model without changing
device cards or connections.

This backend starts from explicit EM geometry and reference planes. A task
must define and independently validate their relationship to the submitted
physical layout, the compact-device boundaries, DC bias connections and any
fixed RF fixtures. It must also validate mesh convergence and circuit assembly
over its declared operating band. A successful field extraction alone does
not qualify a circuit or establish its noise, startup or transient behavior.

### Native Palace networks

`palace-docker` uses a reviewed PDK's unmodified GDS-to-Palace workflow,
native XML stackup and CSV parser. Its backend settings add `converter`, the
native CSV module inside the support bundle, to the openEMS resource settings.
The open EDA image supplies Palace and Gmsh. GDS port geometry, the ordered
JSON port list and the optional SPICE network use the interfaces described
above. Every port uses the same positive real reference impedance.

Jobs declare `fstart`, `fstop` and `fstep` in Hz, with a positive start and an
integral number of uniform steps; `cellsize`, `margin`, `meshsize_max` and
`air_around` in micrometers; six `boundaries` (`ABC`, `PEC` or `PMC`);
`adaptive_sweep`, `conductor_model` (`surface`, `solve_inside` or
`solve_inside_skin`), basis `order` (1–3), OpenMP `threads` and MPI `processes`.
Optional settings are `merge_polygon_size`, `preprocess_gds`,
`adaptive_mesh_iterations`, `adaptive_tolerance`, `cad_threads`,
`cad_boolean_simplify`, `mesh_algorithm_3d`, `fill_factor_correction`,
`excitation_batch_size`, `parallel_batches`, `linear_solver`,
`complex_coarse_solve`, `solver_maxits`, `solver_tol`, `krylov_max_size`
and the native `model` fit.
The declared CAD thread count enables Gmsh's native parallel OpenCASCADE
operators; its default is the declared OpenMP thread count.
The optional integer simplification mode sets Gmsh's native
`Geometry.OCCBooleanSimplify` (0: disabled, 1: unions, 2: all boolean operations).
The optional `mesh_algorithm_3d` selects Gmsh's native volume mesher:
1 (Delaunay), 4 (Frontal), 7 (MMG3D), or 10 (HXT).
The optional boolean `fill_factor_correction` enables the upstream workflow's
conductivity correction for merged via arrays, using the original via metal
area. Declare it explicitly when using that native homogenization method.
Optional positive integers `excitation_batch_size` and `parallel_batches`
schedule native Palace excitation groups on one fixed mesh. All port
terminations remain active; only incident excitation indices change between
groups. Every matrix column is required exactly once on the same frequency
grid. Missing, unsolved or duplicate columns reject the result. Each group
uses the declared MPI process and OpenMP thread counts, so parallel groups
multiply the resource demand. Batching cannot be combined with adaptive mesh
iterations, which could produce different meshes for different columns.
The adaptive tolerance sets Palace's `Solver.Driven.AdaptiveTol` explicitly.
`linear_solver` selects the upstream preconditioner (`Default`, `AMS`,
`MUMPS`, `SuperLU`, `STRUMPACK` or `STRUMPACK-MP`); the selected solver must
be available in the image. `complex_coarse_solve`, `solver_maxits` and
`solver_tol` pass through to the native workflow. `krylov_max_size` bounds
Palace's GMRES restart space through `Solver.Linear.MaxSize`. These settings
control numerical solving and memory demand; the physical mesh, materials
and complete response requirements still apply.

The adapter requires every matrix entry at every requested frequency. Missing,
unsolved or nonfinite responses, and an adaptive sweep that exhausts its sample
limit before converging, or a linear solver that misses its residual tolerance,
are errors. It preserves the native reference
planes and frequency range without DC extrapolation or port de-embedding.
Mesh convergence, assembly accuracy and circuit qualification remain separate
author checks.

### Spectre measurement profiles

These parameters belong to jobs using the [Spectre backends](#spectre). A
simulation job declares `parameters.measurements`, a nonempty map of requested
measurement names to units, and exactly one measurement profile: `response`,
`ac_transfer`, `dc_sweep`, `transient`, `transients` or `waveform`. Optional
`section` selects a model corner and optional `calibration` runs the profile for
several parameter settings ([Discrete calibration](#discrete-calibration)); other
parameters are rejected. Each requested name must be reported by the selected
profile with the declared unit; otherwise the job is an `error`. The trusted
deck supplies stimuli and saved signals. Scoring and functional bounds are
separate declarations in the [task evaluation plan](tasks.md#evaluation-plan).

#### DC sweeps

The `dc_sweep` profile reads `results/sweep.dc` from a named `sweep dc` analysis.
It declares `axis`, `axis_unit` (`V` or `degC`), a positive `max_step`, affine
`traces` with physical units, and `measures`. Supported operations are `at`
(with an `at` coordinate), `min`, `max`, `span` (with closed `start`/`stop`
windows), and `ppm_per_axis`. The last also requires `reference_at` and returns
`1e6 * (max-min) / (reference * (stop-start))` in `ppm/V` or `ppm/degC`.
The reference must be positive and inside the window. Incomplete, nonfinite,
nonmonotonic or overly sparse sweeps fail; endpoints use linear interpolation.
Use a parameter name distinct from saved node names to avoid ambiguous PSF signals.

#### Discrete calibration

For discrete calibration, a simulation job may declare `parameters.calibration`
and `outputs = {selection = "json"}`. Calibration contains:

- `candidates`: records with a unique nonnegative integer `id` and a `parameters`
  map. Every candidate binds the same simple parameter names to finite numbers.
- `target`: `measurement`, `unit`, and numeric `value` to approach.
- `eligibility`: a list of validity bounds, each with `measurement`, `unit`,
  and at least one of `lower` or `upper`. Units must match declared measurements.
  Use an empty list when all completed, finite candidate measurements may
  participate; a quality target does not require an eligibility window.

The adapter runs every candidate independently with the same DUT, deck, process
section and measurement profile. All runs must complete. Among candidates
satisfying every eligibility bound, it selects the smallest absolute target
error, breaking exact ties by lower ID. No eligible setting is an error and
produces no downstream selection. The report retains all candidate waveforms,
logs and a calibration table; the job's measurements describe the selected run.

Both calibration and subsequent testbenches include `"selection.scs"`. The
adapter generates this file from the selected JSON using only numeric Spectre
parameter declarations. It requires exactly one explicit, uncommented
`include "selection.scs"` line in the deck whenever a selection is supplied;
an unused staged parameter file is an error. Downstream jobs bind an optional `selection` input to
`job:<calibration-id>:selection`; dependency handling ensures that calibration
completed. Reuse that same output for every condition covered by a calibration
decision. Authors define the calibration condition, eligibility, full measurement
window and subsequent performance gates; calibration does not certify those
other operating conditions. Each source or candidate evaluation recalibrates
independently. Do not substitute a reference solution's historical settings.

<a id="ac-response"></a>

#### AC response (`parameters.response`)

The AC response profile measures a differential amplifier from completed PSF
ASCII `ac.ac` and `op.dc` results. `parameters.response` declares `output`,
`positive` and `negative`, saved AC signals forming the complex transfer
`output / (positive - negative)`, plus `supply_current`, a saved DC current, and
numeric `supply_v` in volts. The sweep needs at least two strictly increasing,
positive frequencies; missing or incomplete signals are errors. It reports:

| Measurement | Unit | Definition |
| --- | --- | --- |
| `gain_db` | `dB` | Transfer magnitude at the lowest sweep frequency. |
| `unity_hz` | `Hz` | First downward crossing of unity magnitude. |
| `bandwidth_hz` | `Hz` | First downward crossing of the lowest-frequency magnitude divided by √2 (3 dB below `gain_db`). |
| `phase_margin_deg` | `deg` | Phase margin at `unity_hz`, defined below. |
| `output_v` | `V` | Operating-point value of `output`. |
| `power_w` | `W` | Absolute operating-point `supply_current` multiplied by `supply_v`. |

Crossings interpolate log magnitude against log frequency. Both crossings must
lie inside the sweep even when they are not requested; otherwise the job is an
`error`.

The AC profile also reports `phase_margin_deg`: 180 degrees plus the unwrapped
transfer phase at the first downward unity crossing, interpolated on log frequency.
Authors must establish negative-feedback polarity, a valid operating point and a
sufficient sweep; this measurement alone does not prove closed-loop stability.

#### AC transfer

For open-loop filters and attenuating stages, select `parameters.ac_transfer`
instead of the other measurement profiles. This uses completed `ac.ac` and
`op.dc` samples without requiring a unity crossing or assigning a phase margin.
Declare `input` and `output` as linear signal maps, each with `terms`, for example
`{terms = {inp = 1, inm = -1}}`. The transfer is the complex output combination
divided by the complex input combination; subtraction occurs before magnitude.
Zero excitation, nonfinite transfer magnitudes, incomplete signal arrays,
and nonpositive/nonmonotonic frequency grids fail. `max_frequency_ratio` bounds
every adjacent frequency ratio to reject sparse sweeps.

The `measures` map names observations with `operation` and `unit`:

- `gain_db`: `frequency_hz`; unit `dB`.
- `peak_gain_db` or `peak_frequency_hz`: `start_hz`, `stop_hz`; unit `dB` or `Hz`.
- `peaking_db`: the same window plus `reference_hz`; peak gain minus reference
  gain, unit `dB`.
- `bandwidth_hz`: the same window plus `reference_hz` and negative `relative_db`;
  first downward crossing of that reference-relative level, unit `Hz`. Use
  `relative_db = -3` for an exact 3 dB drop.
- `dc`: `terms` combines saved scalar DC signals; unit `V`, `A`, `W` or `1`.
  For supply power, use negative supply-voltage coefficients on currents entering
  each supplying voltage source. Authors must include the relevant bias supplies.

Exact transfer zeros fail logarithmic measurements only when the requested
point, interpolation segment or window includes them. Zeros outside requested
measurement coverage do not invalidate other observations.
Point values and crossings interpolate gain in dB against log frequency; no
out-of-sweep extrapolation is allowed. Window peaks include interpolated endpoints
and saved interior samples. Peak frequency is the lowest frequency attaining the
sampled maximum, with no fitted peak interpolation. A missing required crossing
fails. Authors must establish sweep/window coverage and numerical convergence;
these AC observations do not prove large-signal or closed-loop stability.

#### Waveforms

For other transient circuits, select `parameters.waveform` instead of `response`
or `transient`. It contains `max_step_s`, named `traces` and named `measures`.
Each trace is an affine combination of saved PSF signals, for example
`{terms = {"VDD:p" = -2.5}, offset = 0}` for supply power at a constant 2.5 V.
Each ordinary measure declares `operation`, `start_s`, `stop_s`, and `unit`. Operations
`mean`, `min`, `max`, `rms`, `integral`, `abs_integral`, `span` and `absmax` also select a `trace`.
`abs_integral` integrates the absolute trace, splitting interpolated segments at
zero crossings so opposite-polarity excursions cannot cancel. Its unit is the
trace unit multiplied by seconds, as for the signed `integral`.
Window endpoints use linear interpolation; integral and RMS integrate that
piecewise-linear signal exactly. Task authors own the physical units and signs.

#### Window comparisons

`mean_difference` selects a `trace` and subtracts its mean over
`reference_start_s`–`reference_stop_s` from its mean over `start_s`–`stop_s`.
Both windows must be complete; the result retains the trace's physical unit.

#### Phase difference

`phase_difference` declares two crossing events (`event`, `reference_event`),
unit `s`, integer `min_edges` of at least two, and `statistic` (`std` or `span`).
Both use the common measurement window. Their first edges are aligned once by
the nearest initial event, and subsequent edges are paired by ordinal position.
Population standard deviation or peak-to-peak span uses these continuous time
differences, preserving accumulated drift and cycle slips. Too few aligned
edges rejects the candidate response. This observation does not establish frequency lock by itself.

#### Crossing events

`count` requires unit `1` and an `event` with `trace`, `threshold` and `direction`
(`rise` or `fall`). `delay` requires unit `s`, `trigger` and `target` events,
one-based ordinal `pairs` such as `[[1,1],[2,2]]`, and `aggregation = "min"` or
`"max"`. Both event lists use the declared window independently. Early targets
produce negative delays; missing requested edges reject the candidate response. This supports
propagation, pulse widths, slew and signed dead time without selecting a later
edge to conceal overlap. Authors must also bound crossing counts and logic
levels to reject glitches or missing cycles. Nonfinite/incomplete signals,
nonmonotonic or sparse time grids, and out-of-range windows fail closed.

An event may replace its numeric `threshold` with `threshold_fraction`, strictly
between zero and one. Its threshold is that fraction of the trace's minimum-to-
maximum range within the measurement window, including interpolated endpoints.
This supports relative slew measurement without imposing an absolute swing gate.
The two threshold forms are mutually exclusive; a constant signal has no relative
threshold and rejects a prescribed response measurement. Both threshold forms use the same event pairing and
missing-edge checks.

#### Cycle measurements

`duty_cycle` requires unit `1`, a `trace`, `threshold`, positive integer
`min_cycles`, and `aggregation = "min"`, `"max"` or `"mean"`. It computes
high time divided by period between each consecutive pair of rising crossings,
requiring exactly one falling crossing inside every complete period. Partial
cycles at the window boundaries are excluded; too few complete periods or
missing/ambiguous falling crossings reject the candidate response. Use separate minimum and maximum
metrics to enforce a duty envelope on every observed cycle; an average alone
does not establish that envelope. Frequency, amplitude and startup requirements
remain separate task gates.

`frequency` uses the same complete-cycle fields as `duty_cycle`, with unit `Hz`,
and aggregates reciprocal individual periods. The mean is the arithmetic mean
of those frequencies. `cycle_extrema` additionally requires `statistic = "min"`
or `"max"`; it computes each complete cycle's trace extremum before applying
`aggregation`, retaining the trace unit. Use the minimum of cycle maxima and
maximum of cycle minima to require every cycle to reach both rails.

`frequency_ratio` and `frequency_relative_difference` require `trace`,
`threshold`, `min_cycles`, `reference_start_s`, `reference_stop_s` and unit `1`
in addition to the common fields. Both windows independently require the minimum
complete-cycle count. With arithmetic mean frequencies `a` in the main window
and `b` in the reference window, they return `a/b` and `abs(a-b)/((a+b)/2)`.
These comparisons do not replace per-cycle frequency, duty or amplitude gates.

After successful Spectre execution, these response rejections produce a `failed`
simulation job and a zero layout score under the shared candidate-rejection rule.
The adapter retains native logs, the sampled waveform, and
`waveform-measurements.json`, which records each rejected measurement with its
declared specification and all independently available values. Undefined values
are never replaced with fabricated scalars. A response rejection in an unrequested
diagnostic measure alone does not reject the requested observations.
Malformed or truncated waveforms, absent signals, invalid declarations, windows
outside the completed analysis, and execution failures remain `error` with an
unknown score. Validation errors take precedence over a response rejection;
neither condition triggers infrastructure retries.

#### ADC transfer

For a clocked, stepped ADC sweep, `parameters.waveform.adc_transfers` maps a
transfer name to `input_trace`, `bit_traces` in least-significant-bit order,
`logic_low_v`, `logic_high_v`, contiguous ascending `codes`, ordered settled
`windows_s = [[start, stop], ...]`, `full_scale_low_v`, `full_scale_high_v`, and
`max_input_ripple_v`. The actual mean input in each window must increase, remain
inside full scale and vary by no more than the declared ripple. Each output bit
must stay entirely below the low rail limit or above the high rail limit within
its window. The decoded sequence must begin and end at the declared endpoint
codes and pass through every declared code in order without skips or reversals.
The optional `encoding = "twos_complement"` interprets the most significant
output bit as a sign bit before checking `codes`; the default is `"unsigned"`.
For example, three raw output bits `101, 110, 111, 000, 001, 010, 011`
represent signed codes `-3, -2, -1, 0, 1, 2, 3`. The declared codes must remain
contiguous and within the range of the selected encoding.
These checks make missing codes, unstable rails and incomplete sweeps measurement
errors; they do not impose a DNL, INL or conversion-time performance limit.

An `operation = "adc_transfer"` measure selects `transfer`, `statistic` and
`unit`, without `start_s` or `stop_s`. Scalar statistics are `code_count` (`1`),
`threshold_uncertainty_v` (`V`), `max_abs_dnl_lsb` (`1`) and `max_abs_inl_lsb`
(`1`). Indexed statistics `threshold_v` (`V`), `dnl_lsb` (`1`) and `inl_lsb`
(`1`) require one-based `index`. For each code change, the transition estimate
is the midpoint between the last input level of the lower code and the first
input level of the upper code. `threshold_uncertainty_v` is the largest half
step around such a transition. If there are `N` declared codes, the ideal LSB
is `(full_scale_high_v - full_scale_low_v)/N`. The `N` widths include both
full-scale endpoints; `DNL_k = width_k/LSB - 1`, and each interior transition
has `INL_k = (transition_k - (full_scale_low_v + k*LSB))/LSB`. These are sampled
estimates with a declared endpoint convention. Refine the input step and
simulation time grid to establish numerical convergence. Use separate waveform
events for sample-to-output conversion delay and score numerical accuracy and
delay as quality unless a task justifies a functional limit.

#### Settling time

The Spectre transient profile selects `parameters.transient` instead of `response`.
It declares differential `positive`/`negative` signals, `trigger`,
`trigger_threshold`, one-based rising `edge_index`, `reference_start_s`,
`reference_stop_s`, `tolerance_v`, and `max_step_s`. The trusted deck saves a
`tran.tran.tran` PSF ASCII analysis. `final_v` is the time-weighted mean over the
reference window; `settling_s` is the last entry into the symmetric tolerance
band after the trigger through the reference-window end. Linear interpolation
is used. A final out-of-band sample returns the full observation interval, so
hard limits must be shorter than that interval. Missing edges, incomplete or
nonfinite data, and sparse/nonmonotonic sampling are errors. Task authors must
bound final amplitude separately to reject stuck or attenuated responses.
Optional trusted job `section` overrides the backend model section.

To measure several settling events from one simulation, use `parameters.transients`
instead of `parameters.transient`. This nonempty table maps names such as `rise`
and `fall` to the same transient settings described above. Names start with an
ASCII letter and contain only letters, digits and underscores. One simulation
and one PSF parse serve all events; results are named `<name>_settling_s` and
`<name>_final_v`. Every declared event must pass measurement validation, including
events whose results are not requested. Other measurement profiles are mutually
exclusive with `transients`.

#### Coherent digital ADC spectra

The waveform profile accepts `adc_spectra` tables with `bits_lsb_first`,
`threshold_v`, `sample_start_s`, `sample_period_s`, `sample_count` and
`fundamental_bin`. Samples are interpolated on the completed transient grid,
decoded as unsigned binary, and analyzed with a rectangular coherent DFT after
removing DC. The even sample count is between 8 and 4096. Single-sided power
doubles interior bins but not Nyquist. `adc_spectrum` measurements select a
`spectrum`, `statistic` and `unit`: `sndr`/`sfdr` (`dB`), `enob`/`code_span`
(`1`), or `logic_margin` (`V`). SNDR includes every non-DC bin except the
fundamental in noise/distortion; SFDR uses the largest of those bins. ENOB is
`(SNDR-1.76)/6.02` without amplitude correction. Authors must declare coherent
stimuli, bit significance and settling time. Missing signal or distortion
power, out-of-range sampling, invalid units and incomplete data are errors.
Spectre measurement errors retain native logs and waveforms for diagnosis.

## PDK resource manifests (for Dataset authors)

This part is for Dataset authors who maintain process manifests and support
profiles. Evaluating a published Dataset does not require it: case loading
prepares declared resources automatically.

### PDK manifests

Dataset `pdk.toml` pins process releases, repositories/commits and selected
profiles. Ciel-managed and Git installations retain their source notices.
`support_profiles` selects derived Magic/model/KLayout resources before backend
construction. Case preparation binds paths instead of copying PDK installations.
Frozen support bundles are not updated in place; a changed declaration resolves
to a new binding.

`pdk.toml` is an index of reviewed process resources. Keep release identities,
module and mount selections, environment settings, profile selection and file
references in the manifest. Shared tool backends may declare native entry paths
and command parameters as TOML tables. Maintain file-format JSON configuration, SPICE entries, native
rules, program text and license/attribution text as separate files in
`resources/` beside it, including content that could fit on one line. Reuse
one file for identical content serving the same purpose. Existing vendor
files remain in their pinned installation rather than being copied into this
directory. Project resources must not contain task solutions or complete DUTs.

`[backends.<name>]` uses the same `type`, `settings` and `support_profiles` tables
as a case backend. A case selects one complete declaration:

```toml
# pdk.toml
[backends.drc]
type = "klayout-docker"
support_profiles = { support = "physical" }
[backends.drc.settings]
image = "docker.io/lizhangmai/iclayout-bench-tools:latest"
check = "drc"
support = "physical"
deck = "drc/gf180mcu.drc"
required_categories = ["'M1.1'"]
[backends.drc.settings.variables]
variant = "D"
decks = "all,-density"

# case.toml
[toolchain.backends.drc]
from_pdk = "drc"
```

The deck path names a file declared by the selected support profile. Runtime
preparation replaces `support` with that profile's prepared path; no build-output
path is needed in the declaration. `from_pdk` is supported only for Dataset cases
with their adjacent process manifest. It cannot be mixed with local fields or
chained through another reference. Standalone toolchains continue to declare
complete backends directly. Image and resource selections supplied by the runtime
still apply after resolution. Native rule or program bodies are referenced as files,
not embedded in TOML strings.

| Declaration | Path base | Meaning |
| --- | --- | --- |
| `profiles.<name>.files` / `compile_files` | Pinned installation | Existing tool/PDK files and compiler inputs. |
| `profiles.<name>.source` | Profile-specific installation | Overrides the manifest source for this profile; installed Python-package resources use the selected tools image. |
| `profiles.<name>.local_files.<target>` | Manifest directory | Project-owned file with `path` and `format`, prepared at the named support target. |
| `replace[].old_file` / `new_file` | Manifest directory | Exact-match replacement fragments. Short single-line `old` / `new` literals are also supported. |
| `agent.local_files.<target>` | Manifest directory | Reviewed Agent resource with `path` and `format`, exposed at `/resources/<target>`. |
| `runtime.control_files.<target>.path` | Manifest directory | Native control file staged at `process/<target>` and selected through the existing `@<target>` interface. |
| `notices.<name>.path` | Manifest directory | Preserved license or attribution file. |

For example, a process can declare an independent native control fragment:

```toml
[runtime.control_files."strict-lvs.tvf"]
path = "resources/strict-lvs.tvf"
```

Paths are explicit normalized relative paths. Keep local files regular and
declared; each support target has one owner. Preparation includes their actual
bytes in its resource identity and preserves native syntax. Agent preparation
relocates project-owned support files from `/workspace/support` to their
`/resources/support/<profile>` view. Checks invoke declared scripts or installed
commands rather than embedded `python -c` or shell programs.

Portable snapshots and publication inventories carry every declared local
file, preserving its relative path, and exclude undeclared files. They do not
copy external installations or credentials.

A tool may distribute native process resources separately from the Ciel PDK.
Select those files from its installed distribution with a profile-specific
`python-package` source:

```toml
[profiles.kpex.source]
kind = "python-package"
distribution = "klayout-pex"
version = "0.9.0"

[profiles.kpex.files."kpex/sky130.lvs"]
path = "klayout_pex/pdk/sky130A/libs.tech/kpex/sky130.lvs"
format = "text"

[profiles.kpex.files."kpex/rule_decks/auto_name_layers.rb"]
path = "klayout_pex/pdk/sky130A/libs.tech/kpex/rule_decks/auto_name_layers.rb"
format = "text"

[profiles.kpex.files."sky130A_tech.pb.json"]
path = "klayout_pex_protobuf/sky130A_tech.pb.json"
format = "json"
```

Paths are relative to the distribution's installation root, as listed in its
installed file inventory. Preparation reads only declared files, checks the
exact installed version and stores the resources in the existing derived cache.
No host Python dependency or additional Python environment is created. The
selected image must already contain that distribution. Include the distribution
license and retain the native files' attribution when declaring a complete profile.

### Agent resource declarations

These declarations produce the [Agent PDK resources](#agent-pdk-resources) view.

An `[agent]` table in `pdk.toml` declares process
`id`, `sources`, and `environment`, with optional `checks`, `support_profiles`
and `local_files`.
Each source declares a pinned `repository` and `commit`, or `installation = true`
for the manifest's installation. Optional `path` selects the PDK root within
that checkout or installation. Optional `paths` is a nonempty list of normalized,
nonoverlapping paths below that root. Use it to expose technology files, device
models and licenses while omitting reference cells and example layouts. Paths
are bound directly from the installation; preparation does not copy the PDK.
Changing this selection produces a new resource binding.
Each support profile names an evaluator preparation profile. When declared,
`checks` lists executable argument lists run inside the Agent container; each
command must be nonempty.

| Resource | Runtime behavior |
|---|---|
| PDK resources | The selected `pdk.toml` declares roots and container settings; selected roots are mounted read-only. |
| Tool support bundle | Declared profiles select Magic, MOS models and KLayout rules; generated models are compiled in a separate container. |
| PDK resource view | `resource.json` binds shared preparation; containers mount installed roots and derived files read-only. Sessions detect the selected PDK; `/protocol/task.json` → `resources` publishes its container-local import paths and any declared preflight commands without adding task or reference files |

Keep upstream files byte-for-byte and maintain simulator startup settings with
the task. Preserve component license notices, including those for PSP models,
PyCell and pypreprocessor.

Resource preflight runs the process's declared `checks` and any selected
support-profile checks. Process `checks` are optional and may be empty; a resource
binding does not require a custom check script. A passing command establishes
only the functionality it exercises; successful imports do not certify every
device parameter or process rule. Physical and electrical coverage comes from
the selected task's declared evaluation scope, as described under
[qualification](tasks.md#qualification).

### Manual support preparation

Normal case loading prepares declared profiles automatically. Standalone
configurations can explicitly prepare a profile from their chosen Dataset:

```bash
export DATASET_ROOT=/path/to/dataset
python -m benchmarking.eda.resources.support \
  "$DATASET_ROOT/tasks/ihp-sg13g2/pdk.toml#magic" build/support/sg13g2-magic
python -m benchmarking.eda.resources.support \
  "$DATASET_ROOT/tasks/ihp-sg13g2/pdk.toml#mos-models" build/support/sg13g2-mos-models
python -m benchmarking.eda.resources.support \
  "$DATASET_ROOT/tasks/ihp-sg13g2/pdk.toml#klayout" build/support/sg13g2-klayout
```

The IHP `mixed-mos-models` profile adds the pinned HV PSP closure to LV MOS
support. Use the same preparation command with that profile when explicitly
needed. Relative standalone backend `settings.support` paths resolve from the
backend launch directory; evaluation-plan paths resolve from the plan file.
[Task tool bindings](tasks.md#tool-bindings-and-drc-waivers) define those declarations.

<a id="external-commercial-runtimes"></a>

## Commercial runtimes (for operators)

This part is for operators who bind licensed vendor tools and process data
installed on their own host.

Operator-installed EDA and PDKs can be bound to the shared evaluator without
entering the public resource cache. The public package includes generic
commercial tool adapters; it bundles no vendor software or process data.
Commercial evaluation uses licensed tools and an explicitly installed PDK on
the trusted operator host. Agent solving uses the declared commercial Docker
image. The evaluator receives only frozen submissions and declared evaluation
inputs; it does not run inside or read the writable solver workspace.

### Host execution

All commercial evaluator backends in this part (`*-native`) run on the trusted
operator host rather than in a container. They use declared module/resource and
license bindings with identical host/target paths, stage immutable input bytes
in fresh job directories, apply any time limit in effect to the whole process
group, preserve failure evidence and redact passed license settings from text
evidence. They run as the operator user with host resources and network;
container CPU, memory, filesystem and network isolation do not apply. Host
execution is selected explicitly and never automatically replaces a failed
Docker run. Identity records this execution mode, UID/GID, stable tool releases,
declared resources and their digests, and the launcher, without evaluator image
identity or container resource limits. These trusted evaluator adapters are
separate from the solver runtime: solver isolation is unchanged, and solver
resource filtering and runtime deployment remain the operator's responsibility.
Select this mode only in a reviewed operator task configuration.

### Runtime manifest

An external process declares one `[runtime]` table in its `pdk.toml`. It
contains `image`, `environment`, `mounts`, optional `modules`, `tool_environment`,
`pass_environment` (names only), `license_hosts`, `control_files` and `network` (default `none`). Each
read-only mount specifies absolute `source` and `target`, `release`, and
`identity_paths` relative to its source. Select model, rule and extraction files
actually used, plus tool identity files. File content, declared releases, tool
version output, host execution mode and UID/GID enter evaluator identity.
The Docker image ID belongs to solver deployment. Installation changes
in selected paths are rejected between preparation and execution. This does not
attest every binary or dependency of an installation: operators must keep the
selected installation immutable during a run and review their identity coverage.

`runtime.control_files` maps relative filenames to fixed native EDA text, such as
a process rule wrapper or simulator model interface. The host evaluator stages these bytes unchanged under `process/` in each
fresh job directory; job inputs
cannot replace them. Their content digests enter runtime identity. Backend
settings that accept an `@filename` reference resolve only this declared table.
These files belong to the process declaration and require independent author
validation. They must not contain task circuits, reference layouts, credentials,
or code that repairs candidate connections or imports source device parameters.

Tool license settings must use `pass_environment`, never literal `environment` values.
An explicitly selected license-file mount uses `credential = true` and omits
`identity_paths`; its bytes and environment values are excluded from identity.
These declarations authorize only reviewed access to the selected EDA tools'
licenses. Model, website, session and other unrelated credentials stay outside
EDA containers; license contents must not enter result exports or static datasets.
Do not mount a whole license directory, operator checkout or Docker socket.
An operator may explicitly select `network = "host"` to share host networking,
including the network identity used by node-locked licenses. Rootless Docker
requires Engine 29.5 or later to share the real host network namespace. Host
networking uses the host's network access policy rather than a container port
allowlist. A named network remains available for deployments with their own
license network policy; implicit `bridge` and `default` networks are rejected.
Without a declaration, the network remains `none`. Version probes and evaluations use the same
read-only mounts, unprivileged user and resource limits.

When a license server alias resolves only on the host, `license_hosts` maps a
forwarded license environment variable name to an operator-selected server IP.
The container receives an explicit DNS alias for each `port@server` entry while
the license setting itself remains forwarded by name. For example,
`license_hosts = { SNPSLMD_LICENSE_FILE = "192.0.2.1" }` selects the transport
address without storing a license setting in the manifest. The address is
recorded in runtime identity. This does not configure the network firewall.

For installations managed by Environment Modules, add a `modules` table to the
process runtime. Keys are command names such as `pvs`, `quantus`, `spectre`, and
`assura`; each value is a nonempty list of module names. Mount the selected
modulefiles read-only, include them in that mount's `identity_paths`, and set
`EDA_ROOT` and `MODULEPATH` to the declared installation paths in `environment`.
Host and container environments provide `/usr/share/Modules/init/bash`.
Host resource paths and declared targets must be identical. Evaluator commands load the selected
modules in each tool process. Solver shell commands load modules explicitly.
Optional `tool_environment.<tool>` tables declare noncredential environment
settings applied after that tool's modules load. The settings enter runtime
identity and `/protocol/task.json` → `resources.external`; solver commands apply the selected
tool's settings after loading its modules. For example, a setting declared under
`[runtime.tool_environment.hspice]` applies to HSPICE rather than every process
in the shared image. License values must still be forwarded by name.

### Solver commands

Each solver `execute` call starts a fresh shell. Load the tool's modules and
apply its `tool_environment` in that same call; exports from a previous call do
not persist. Use the tool's documented batch or headless entry point because no
desktop display is provided. For Custom Compiler, a batch Tcl entry point is:

```bash
custom_shell -gui false -batch true -libDefFile /workspace/lib.defs \
  -command 'source /workspace/your-script.tcl'
```

Create your own library definitions and script using the declared technology
resources. Tool initialization does not construct or
repair the candidate layout.

### Process resources and native libraries

An externally installed process declaration uses `[source] kind = "external"` with
`runtime` and `release`. The `runtime` name identifies the process runtime in
evaluator reports. `PDK_ROOT` names either one noncredential mount or a root
assembled from explicitly mounted files or subdirectories, all with the declared release.
For a file mount, `identity_paths` contains only that file's basename; its bytes
enter the resource identity without exposing adjacent files.
The commercial adapters resolve each process file within those selected
mounts and reject unmounted paths and symlinks escaping the selected directory.
Use subdirectory mounts to omit upstream example layouts, author assets and Git
metadata without copying or modifying the installed PDK. Backend
`settings.runtime` selects this same profile. An explicit `pdk_root_env` selects
another already mounted variant. Standard `PDK_TECH_PATH`, `PDK_LAYER_MAP`,
`PDK_DIR` and `PDK_LIBRARY_DEFINITIONS` paths beneath the original root move with
that selection, retaining the technology library name and unrelated settings.

Native OA discovery uses `PDK_TECH_LIBRARY`, `PDK_TECH_PATH` and `PDK_LAYER_MAP`
for Virtuoso, or `PDK_TECH_LIBRARY`, `PDK_LIBRARY_DEFINITIONS` and `PDK_LAYER_MAP`
for Custom Compiler. These are declared resources, not author working libraries.
Trusted author/operator utilities `benchmarking.eda.oa.virtuoso.VirtuosoGDSNative`
and `benchmarking.eda.oa.customcompiler.CustomCompilerGDSNative` import explicit frozen GDS
assets into fresh libraries, run native transactions, and export selected cells
and diagnostics. They retain tool failure and timeout evidence; they do not
automatically change execution location or expose a script endpoint to solvers.
Process-specific layout recipes and circuit rules remain with their authors.
No public `profiles` or cached `agent` bundle is supported for an external PDK.

#### Solver image requirements

A commercial solver image must:

- provide Python 3.12+ as `/usr/bin/python3` and `python`;
- work without its entrypoint, because session commands bypass image entrypoints;
- load the selected modulefiles in each shell, as described under [Solver commands](#solver-commands).

The process runtime supplies read-only installations and minimal tool license
access. Provider credentials, reference files and operator repositories stay
outside the container. Solver mounts cannot shadow trusted input/protocol/system
paths, or override the trusted reader environment. Resource limits and frozen
submissions still apply.

#### Service flags

The local service selects the solver and evaluator separately:

- `--solver-runtime NAME` is accepted only when NAME matches the case's external process declaration.
- `--solver-image` selects the solver image; evaluator backends use the operator host.
- `--image` selects open EDA evaluator images and does not override commercial host execution.

Both solver runtime and evaluator identities are recorded. Commercial recipes and
experiment configuration belong to the operator, including license/network
policy and installation immutability.

### Virtuoso and Custom Compiler geometry

`virtuoso-geometry-native` accepts `runtime`, `check` (`artifact` or `geometry`)
and `timeout_seconds`. XStream imports the frozen GDS into an isolated OA
library; Virtuoso queries hierarchy and arrays and measures each non-text shape
under its native occurrence transform, without building a flattened copy of the
design. The geometry check supports `bbox_max` and `functional_bbox_area` with
the same layer/datatype semantics as [`klayout-geometry-docker`](#geometry). It
does not support connectivity constraints. Import logs and native geometry
measurements are retained as evaluation evidence.

For Synopsys runtimes, `customcompiler-geometry-native` accepts the same
settings and bounding-box constraints. It runs operator-installed Custom
Compiler under [host execution](#host-execution). `importStream` preserves GDS
layer/datatype numbers in a generic OA library; native layout editing flattens
hierarchy and arrays before measuring non-text shapes. No reference or PDK
design library resolves submitted cells. Import logs and shape measurements are
retained.

Both native geometry adapters check stream record lengths, directory/precision
and TEXT record syntax before importing the submitted bytes. In particular, a
TEXT label requires TEXTTYPE and ordered XY/STRING records; permissive OA import
does not establish validity for malformed labels. A confirmed format violation
fails the artifact gate and scores zero. The adapters preserve the submission
without rewriting records; license, execution and unclassified tool failures
remain evaluation errors.

### Assura

`assura-drc-native` runs the operator-provided `drc_deck` relative to
`PDK_ROOT` with the mounted Assura installation. It accepts frozen GDS and task
inputs, uses the deck's default switches, enables non-45-degree and 0.005 um
off-grid checks, and applies no black boxes or waivers. A pass requires normal
termination, the requested top cell, nonzero execution and cell counts, and zero
errors in both native report columns. Density, antenna and optional DFM checks
are not implied by a default DRC pass. Evidence includes the runset, native log,
summary and error report. The runtime must provide `assura` on PATH.
For a host diagnostic with the same runset and parser, use
`python -m benchmarking.eda.backends.assura --layout FILE --top CELL --deck FILE --output NEW_DIR`.
This command inherits the shared EDA time policy; `--timeout SECONDS` explicitly
requests a bounded diagnostic run.
`assura-lvs-native` accepts frozen GDS, task and reference CDL (`spice` format).
Its `extract_deck`, `compare_deck` and `binding_deck` are relative to `PDK_ROOT`.
It invokes native Assura extraction and CDL comparison without OA access, rule
rewrites or tolerance overrides. The CDL must use the selected reader/deck's
units and device conventions; a SPICE-looking file is not necessarily compatible.
A pass requires normal extraction and LVS termination, a nonempty extraction,
the requested top, and agreement of the native comparison and cell summaries.

The same CLI supports `--check lvs --netlist FILE --compare-deck FILE
--binding-deck FILE` with `--deck` selecting extraction. Add `--pdk PDK_TOML`
to run either check with the declared host modules and resources; deck paths
then become relative installation paths.
These are physical observations, not complete electrical qualification.

`assura-rc-native` uses the same extraction, comparison and binding decks,
then runs Quantus on the freshly matched Assura database. It accepts `ports`
and optional integer `temperature_c` job parameters. `qrc_technology` is a
PDK-relative technology directory. The native output must already use the
qualified simulator model interfaces. It retains
numeric coupled RC, process resistor geometry and substrate connections, and
requires complete native LVS and Quantus reports before publishing a netlist.
The runtime provides `ASSURA_ROOT`, `assura`, `quantus` and Python. Junction
geometry is required by default. An explicit
`junctionless_models` list may identify process devices such as MOS
capacitors whose extraction definition has no diffusion junctions. This does
not exempt other MOS models from geometry validation or synthesize junctions.
Runsets, commands, native reports and raw DSPF remain evaluation evidence.

### PVS

`pvs-native` selects `check = "drc"`, `"lvs"` or `"rc"`. Deck paths and Quantus
technology paths are relative to `PDK_ROOT`. `lvs_includes` explicitly adapts
exact include directives to mounted paths without changing rule logic. DRC
requires a normal completion and a nonempty executed-rule count; LVS requires a
complete match without blackboxed cells. RC extraction checks LVS first and
retains physical instances, resistance and capacitance. A Linux subreaper
(launched with the evaluator Python interpreter) waits for the Quantus command
and any orphaned workers; nonzero worker exit status is an error. When a
[time limit](#evaluation-time-limits-and-cancellation) is in effect, it bounds the
whole process tree. A parent completion message alone is insufficient. Only the extracted
subcircuit port declaration is reordered to match the declared named interface.
This backend requires identical simple layout/source top names and
DSPF top-level ports (including SPICE continuations). Unsupported output is an error, not a pass.
Physical scalar geometry and interconnect resistance accept SPICE engineering
suffixes, such as `30n`, `0.8u`, and `0.1125p`; validation retains the native
parameter spelling and rejects expressions or unsupported units.
When DSPF adaptation rejects native output, the failed job retains that DSPF and
the native logs for diagnosis; it emits no simulation netlist.

### Calibre

`calibre-native` selects `check = "drc"`, `"lvs"` or `"rc"` and an installed
`deck` relative to `PDK_ROOT`. Optional `includes` maps exact quoted include
names to mounted process paths; `source_libraries` supplies process device
declarations for LVS. The adapter changes run I/O statements while preserving
process checks and device definitions.
DRC requires a nonempty executed-check
count and zero results; LVS requires a finished named-port comparison of every
reported cell without blackboxes. Failures and incomplete reports retain native
evidence. RC runs LVS, xRC `-pdb -rcc` and `-fmt -all`, preserves distributed R,
explicit coupling C and physical devices, and reorders only the extracted top
port declaration. No source circuit substitutes for extraction.

Recorded Calibre settings group rule bindings, DRC execution, LVS comparison,
and RC adaptation separately. Quantus and StarRC record CCI connectivity and
their extraction settings alongside the shared Calibre configuration.

`inline_includes` maps exact quoted or unquoted include names to mounted process
files whose contents must be inserted before adapting run I/O. Each name must
match once. This handles an xRC wrapper including an LVS deck with single-valued
run controls, without duplicating those statements or changing device rules.
An optional text job input `rule_control` selects the task's native SVRF or TVF
entrypoint. Declare it as an evaluator input and bind it to each intended job.
This entrypoint owns comparison, virtual-connection, ERC and floating-net
policies. The adapter binds run I/O and enforces named-port comparison; it does
not add `LVS EXECUTE ERC`, `VIRTUAL CONNECT COLON` or
`PEX EXTRACT FLOATING NETS` to a task-supplied entrypoint. The effective control
file remains evidence. Non-UTF-8 comment bytes are preserved.

Alternatively, the backend setting `rule_control = "@filename"` selects a fixed
native process wrapper from `runtime.control_files`; supplying both sources is
an error. Without a task control input, the existing flow requests ERC, disables
colon virtual connections and uses the `REDUCED` floating-metal capacitance
network. A TVF wrapper that reads another deck must itself exclude that deck's
fixed run I/O before emitting its rules.
`require_erc_summary = false` is explicit for decks with no standalone ERC
RuleChecks; the default still requires the ERC report.

Task-specific LVS reduction and parameter-comparison rules belong to the task's
native controls; process resources supply the device and layer definitions. The
framework does not synthesize device policies. Extraction may declare `mos_parameters`,
a mapping from native parameter names to `positive`, `nonnegative` or `positive_integer` domains. These checks reject
unsupported native output without changing its models, parameters or nets.
`require_junctions` independently selects conventional AS/AD/PS/PD checks.
Native process rules and extraction interfaces require author qualification.

Calibre and Spectre backends may select `pdk_root_env`, the name of a manifest
runtime environment entry identifying another explicitly mounted PDK variant.
The default process root remains unchanged for other backends. The selected root
and all declared resources enter the backend identity. Spectre may also select
`module_profile`, an explicitly declared runtime module entry for a supported
tool version. This leaves the default tool selection unchanged and records the
selected module and mounted installation in the backend identity.

Calibre accepts both SVRF and TVF decks, preserving non-UTF-8 comment bytes.
DRC may select `deck_member`, the relative name of a regular file inside the
declared tar archive. Only that member is read; no archive extraction or process
rule selection occurs. TVF I/O additions use the explicit `tvf::VERBATIM` namespace.
DRC-only `threads` selects Calibre `-turbo` workers (a positive integer, default 1)
and enters the backend settings identity. Select it within host and license capacity.
Optional `defines` replaces exactly one existing `#DEFINE` per name;
`text_variables` binds exactly one existing `VARIABLE` per name to a nonempty
list of quoted pin-name strings. It changes declared rule configuration without
adding marker geometry or new named ports to the frozen layout.
`rule_includes` appends mounted process rule files. `hcell_file` and `xcell_file`
select the foundry hierarchy/device boundaries for LVS and xRC. DRC-only
`exclude_checks` lists individually named checks outside the declared scope;
authors must justify each exclusion. These adaptations enter backend identity.
`subcircuit_mos_models` identifies native four-terminal MOS wrappers whose
measured W/L and junction geometry are validated without rewriting them. Optional
`case_insensitive_ports` matches SPICE port names without case distinctions,
rejects ambiguous aliases, and restores the declared spelling in the top header.

Junction geometry is required by default. The declared process deck must
extract it correctly, including shared diffusion. The adapter does not inject
junction formulas or copy geometry from source devices. Optional `ground` names
the physical parasitic reference.

`calibre-native` runs these checks and extraction under [host
execution](#host-execution).

### Calibre with Quantus

`calibre-quantus-native` uses the same explicit [operator host
execution](#host-execution) for Calibre LVS/CCI followed by Quantus coupled RC.
It requires `deck`, `technology_env` (an environment entry naming a technology
directory within a declared, noncredential resource mount), and `ground` (a
declared top-level port). The technology can share the PDK mount; include its
files or directory in that mount's `identity_paths`. An unset `technology_env`
or a directory outside the declared resource mounts fails before tool probes;
the adapter does not supply replacement extraction parameters. The runtime selects both
`calibre` and `quantus` module profiles. Frozen GDS and source bytes remain
unchanged; source data is used for LVS and naming, while devices and parasitics
come from annotated candidate geometry. Jobs declare `ports` and optionally an
integer `temperature_c` (default 27). The adapter preserves CCI device
templates, requires a complete non-blackboxed LVS match and normal Quantus
completion, and validates extracted MOS geometry before returning a simulation
netlist. Identity includes stable Quantus release/build fields and the worker
launcher. Evidence retains the LVS/CCI/Quantus logs, controls, annotated device
netlist and raw DSPF. The operator must independently validate the selected
technology and supported device interfaces; this interface does not imply
foundry certification.

### Calibre with StarRC

`calibre-starrc-native` uses the same [operator host execution](#host-execution)
for Calibre LVS/CCI followed by StarRC. It selects `deck`, `technology_env`, and
resource paths `grid`, `mapping`, `command_template`, `query_template`, and
`hcell_file` within the declared technology mount. Both `calibre` and `starrc`
module profiles are required. Optional `cores` (1–8) runs the vendor's manual
distributed workers. StarRC may reduce the worker count when fewer partitions
are needed. Acceptance requires successful worker exits, normal extraction
completion and zero reported errors; completion-message counts need not equal
the requested worker count. The vendor command policy is retained; run-specific
file paths, top name, temperature, node reporting and worker count are bound
explicitly. Optional `extraction_mode = "RC"` fills an existing template
extraction setting; `device_pin_file` binds an existing
`CALIBRE_OPTIONAL_DEVICE_PIN_FILE` setting to a resource path inside the
declared technology mount. Missing or duplicate template settings fail rather
than silently appending defaults. A job declares `ports` and optional integer
`temperature_c` (default 27). Acceptance requires complete named-port LVS,
successful workers with normal completion and zero reported errors, and valid
extracted physical device geometry and R/C. The raw DSPF, controls and native
logs remain evidence. Frozen GDS/CDL bytes are preserved; the source is used for
LVS and naming, not as a substitute for extraction.

### ICV with StarRC

`icv-native` selects [operator host](#host-execution) ICV with `check = "drc"`,
`"lvs"`, or `"rc"` and a mounted `deck`. An optional text job input
`lvs_control` selects the task's native runset wrapper, retaining the mounted
deck's include directory. Alternatively, the backend setting
`lvs_control = "@filename"` selects a declared runtime control file; supplying
both sources is an error. LVS and RC settings require `lvs_checks`, a mapping
from native report check names to expected device-class counts. The adapter verifies this
declared coverage and the native comparison verdict, and passes source inputs
unchanged. Task controls own property comparison and device-equivalence
policies; shared resources supply process interfaces. DRC requires a completed
report for the requested top, positive rule coverage and zero violations.
`allowed_unexecuted` records known inactive rules
without suppressing checks.

RC uses native ICV/StarRC, requiring `grid` and the job's ordered `ports`.
The adapter binds the block, grid, RC/SPF output and `ground` (default `GND!`).
An optional text job input `starrc_control` appends the task's native StarRC
commands. Alternatively, `starrc_control = "@filename"` selects a runtime
control file; supplying both sources is an error. Native controls select
extraction networks, power extraction, coupling, isolated ports, temperature
and worker count. Controls are evaluator inputs and must be declared and bound
to the corresponding jobs. DRC accepts neither control input, and LVS accepts
only `lvs_control`. The effective runset and StarRC command file remain evidence.
Three-terminal MOS models, geometry and RC cards remain as emitted by StarRC. The existing
named interface may be reordered; missing supply ports and extra generated ports
are rejected instead of added or removed. Native resource templates must produce
the required model names and interface before the flow can be qualified.
Successful completion and zero extraction errors are required; vendor warnings
remain evidence. This interface does not establish manufacturing signoff.

### HSPICE

`hspice-native` uses the declared `hspice` module, mounted `model` and explicit
`sections`. An explicitly empty `sections = []` includes the model file directly
with `.include`, for model cards without library sections. A simulation job
supplies SPICE `deck` and `dut`, with a nonempty
`parameters.measurements` map of measurement names to units. The deck includes
`dut.spice` and one `* ICLAYOUT_MODELS` marker, replaced with the trusted model
library statements. Acceptance requires normal completion, no reported errors,
and exactly one finite scalar for each requested measurement. Failed event
measurements are errors; engineering suffixes include atto (`a`).

### Spectre

`spectre-native` selects a model file and section. Optional `sections` loads
several sections of that file; optional `model_includes` lists additional model
files relative to `PDK_ROOT` or `@filename` entries in `runtime.control_files`.
These native model interfaces do not change the extracted DUT. A job's explicit `section` selects one corner of
the primary model file. These selections enter backend identity and also apply
to APS and Spectre X. It stages `models.scs`,
`deck.scs` and `dut.spice`; trusted testbenches choose conditions. The AC
measurement profile reads completed PSF ASCII `ac.ac` and `op.dc` data and reports
differential AC gain, first downward unity/3 dB crossings, DC output and supply
power. It does not replay general OCEAN/ADE expressions.
[Measurements](#spectre-measurement-profiles) defines the AC, DC and transient profiles.

The optional backend `environment` table declares case simulator startup
settings, for example `SPECTRE_DEFAULTS = "-E"` to select native C preprocessing.
These values are recorded in backend identity and applied after the declared
tool module loads, so module defaults cannot silently replace the case choice.
Empty values can explicitly clear inherited defaults. License values must use
the runtime's named forwarding interface.

The backend setting `max_parallel_jobs` defaults to 1; a positive integer opts
into concurrent independent jobs with isolated tool workspaces. Select it within
the installation's license and resource capacity. Candidate runs inside one
calibration job remain sequential. All Spectre variants use [host
execution](#host-execution). Spectre backends accept no container resource
settings; solver container limits remain separate.

Solver sessions with a declared Spectre module allow executable mappings in
their isolated workspace so that Spectre can load compiled AHDL model libraries.
The root filesystem and installed tool/PDK mounts remain read-only.

### Spectre APS

`spectre-aps-native` explicitly selects licensed APS (`+aps`) with `threads`
set to a positive integer (default 4 threads). Select the count within host and
license capacity. Optional `aps_preset`
(`conservative`, `moderate`, or `liberal`) selects the corresponding `++aps`
mode. Optional `postlayout` (`upa`, `hpa`, or `default`) enables Spectre's
post-layout optimizations; `upa` retains the extracted RC network, while `hpa`
uses conservative RC reduction. The backend shares Spectre's frozen inputs,
measurements, calibration and failure handling, and records the selected options
in its identity. Authors must characterize the source and qualify the reference
with the selected engine and options. License failures remain errors.

### Spectre X

`spectre-x-native` explicitly selects licensed Spectre X with `+preset` (`cx`,
`ax`, `mx`, `lx`, or `vx`; default `ax`) and `+mt` (`threads` is a positive integer, default 4).
It uses the same inputs, measurements, calibration, and native
failure checks as `spectre-native`. Its identity records the selected preset
and thread count. Optional `postlayout_preset` selects `+postlpreset` using the
same preset names, and is also recorded in identity. Characterize source observations and qualify the reference
under the same selected settings.
Optional `preset_override` lists explicit deck parameters that the preset must
honor: `maxstep`, `reltol`, `vabstol`, or `iabstol`. For transient contracts with a
maximum sample interval, select `maxstep` when the preset would otherwise ignore
that deck option. These overrides enter the backend identity.

The declared `spectre` module is loaded for version reporting and execution.
`threads` must fit the evaluator process's host CPU affinity. Select physical
cores within the installation's license capacity. Solver isolation is unchanged.

### Native extracted circuit interfaces

The extraction adapters validate native output and bind the already existing
named top-level ports. Device cards, including continuations and annotations,
are preserved. They do not convert M/Q/R primitives into X calls, rename models,
scale BJT area, infer substrate terminals or remove physical parameters.
Evaluation does not reconnect a candidate or substitute expected devices.
Model compatibility belongs to the qualified process extraction and simulator
resources.

Quantus keeps physical instances and process resistor models in native output.
`require_junctions = true` rejects missing MOS AS/AD/PS/PD unless the process
explicitly declares a junctionless device. Numeric interconnect R/C are retained;
numeric resistor cards carrying `segr`, `segl`, `segw`, `effl` or `effw` are
rejected because a flattened process device is not an ordinary wire resistor.
Primitive process resistors require valid native L/W; supplied bipolar area and
multiplicity must be positive finite values and retain their native units.
