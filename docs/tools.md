# Tool Environments and EDA Backends

Local evaluation needs Linux x86-64, Docker and a compatible EDA image. The
participant host runs the model CLI; isolated solver/evaluator environments run
EDA. Remote participants use the operator's service and need no local PDK/tool
installation. [Running](running.md) supplies experiment commands. Use the setup
sections for local runs and the backend reference when configuring a Dataset's
evaluation tools.

- [Environment and resources](#environment-and-resources): image selection, PDK mounts, caches and common execution rules.
- [Open EDA and geometry backends](#open-eda-and-geometry-backends): simulator, physical checks and layout measurements.
- [External commercial runtimes](#external-commercial-runtimes): installed tools, licenses and extraction/simulation adapters.
- [Spectre measurement profiles](#spectre-measurement-profiles): AC/DC/transient observations and calibration.

## Environment and resources

### Prebuilt images and local builds

The published open EDA image is
`docker.io/lizhangmai/iclayout-bench-tools:latest` and supports `linux/amd64`.
Tasks and PDKs are resolved separately. Pull it before running EDA:

```bash
docker pull docker.io/lizhangmai/iclayout-bench-tools:latest
```

The runner uses this image by default. Select another compatible image directly
with `--image IMAGE` or `ICLAYOUT_BENCH_IMAGE`; no retagging is required. Use a
registry digest (`name@sha256:...`) when you need an immutable release.
To build the maintained Dockerfile from source, choose your own output tag:

```bash
git clone https://github.com/lizhangmai/ICLayout-Bench.git
cd ICLayout-Bench
docker build --platform linux/amd64 -t iclayout-bench-tools:dev .
```

The unified open image contains Qucs-S/Qucsator, ngspice, Xschem, Magic, Netgen,
OpenVAF, KLayout and the prepared Python tools below. Its label is
`org.iclayout.eda=open`. Preparation, solver work and evaluation use compatible
frozen image identities; each operation retains its own isolation. Harness CLIs
are installed on the participant host separately.

Open EDA resource loading uses an explicit image, then `ICLAYOUT_BENCH_IMAGE`,
then the published open image. Commercial evaluators run directly on the
operator host and do not resolve or inspect a Docker image.
`scheme.solver_image` or the service's `--solver-image` can choose a distinct
participant image while trusted evaluator bindings remain separate. Commercial
images and installed vendor tools follow [Commercial runtimes](#external-commercial-runtimes).

### Dataset loading

The public task Dataset is `lizhangmai/ICLayout-Bench`. Supply that repository ID,
another Dataset ID or a directory containing a downloaded Dataset. The package
contains no task tree. Case loading reads source contracts without editing them, verifies
declared inputs and resolves resource bindings in memory. Sessions snapshot only
their declared inputs. Full Dataset metadata and reference assets stay outside
the solver mount.

A repository revision selects a fixed asset snapshot; `--offline` selects cached
data. HF owns snapshot downloads, authentication, locking and cache layout. The
Dataset's canonical `data.parquet` indexes its cases. [Running](running.md#static-dataset-inputs)
defines native table selection and task ordering. Evaluator loading binds its
reader cache to the resolved table files automatically.

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
| `platform/` | Rebuildable website object copies. |

Consumers evict only their own namespace. HF Dataset/Xet blobs remain in their
native cache and are read in place. Caches contain rebuildable inputs; results,
recovery checkpoints and archive databases use explicit persistent paths.
Per-job scratch is disposable tmpfs.

Dataset `pdk.toml` pins process releases, repositories/commits and selected
profiles. Ciel-managed and Git installations retain their source notices.
`support_profiles` selects derived Magic/model/KLayout resources before backend
construction. Case preparation binds paths instead of copying PDK installations.
Frozen support bundles are not updated in place; a changed declaration resolves
to a new binding.

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
  and usage checks, also exposed through the `resources` field of `/protocol/task.json`.

Case preparation stores path bindings, not another filesystem view of the PDK.
Benchmark case references, other case directories and unrelated PDK roots are
not added to the resource mount.

Every process uses `ICLAYOUT_BENCH_PDK`, `PDK_ROOT` and `PDK_PATH`; the namespaced
identifier avoids conflicting with tool-owned settings such as gdsfactory's
`PDK` module selector. `PYTHONPATH` and `KLAYOUT_PATH` are declared only where needed. Explicit Agent
Python/KLayout search paths are appended; conflicting fixed settings are rejected.
The PDK mounts are read-only and the Agent stays non-root and offline. Write
generated layouts, simulator decks and tool caches under `/workspace` or `/tmp`.
For ngspice, copy the selected support profile's `.spiceinit` into the working
directory before invoking the simulator; it loads compiled models where needed.

An `[agent]` table in `pdk.toml` declares process
`id`, `sources`, `environment`, `checks`, and optional `support_profiles`.
Each source declares a pinned `repository` and `commit`, or `installation = true`
for the manifest's installation. Optional `path` selects the PDK root within
that checkout or installation. Optional `paths` is a nonempty list of normalized,
nonoverlapping paths below that root. Use it to expose technology files, device
models and licenses while omitting reference cells and example layouts. Paths
are bound directly from the installation; preparation does not copy the PDK.
Changing this selection produces a new resource binding.
Each support profile names an evaluator preparation profile. `checks` is a
nonempty list of executable argument lists run inside the Agent container.
Additional participant tools can be installed in a custom solver image selected
through [participant tool schemes](running.md#participant-tool-schemes).

| Resource | Runtime behavior |
|---|---|
| PDK resources | The selected `pdk.toml` declares roots and container settings; selected roots are mounted read-only. |
| Tool support bundle | Declared profiles select Magic, MOS models and KLayout rules; generated models are compiled in a separate container. |
| PDK resource view | `resource.json` binds shared preparation; containers mount installed roots and derived files read-only. Sessions detect the selected PDK; `/protocol/task.json` → `resources` publishes its container-local import paths and a preflight import command without adding task or reference files |

Keep originals byte-for-byte as supplied upstream and register framework-generated startup settings separately in the manifest. Preserve the license notices for components such as PSP models, PyCell, and pypreprocessor. The PDK view currently validates only basic MOS/tap primitives; importing a tool or device does not qualify every parameter or process rule.

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

<a id="manual-tools"></a>

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

### EDA backend contract

A [task toolchain](tasks.md#tool-bindings-and-drc-waivers) binds logical operations
to trusted backend types/settings. `evaluate` uses the case's embedded toolchain
unless explicitly overridden. `characterize` requires an explicit toolchain.
When the selected toolchain is embedded in a case with declared resource profiles
or an external runtime, these commands prepare and bind those resources through
the same loader as participant sessions. They do not require author-prepared
support directories or reference layouts. `--image` and `ICLAYOUT_BENCH_IMAGE`
override the selected tool image.
Evaluation writes `report.json` and declared artifacts: exit 0 means passed,
1 means completed rejection and 2 means configuration/execution error.
[Tasks](tasks.md#evaluation) defines failure and scoring precedence.

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

The shared native/container tool executor lets EDA jobs finish without per-job
limits by default, including direct operator and preview calls, session feedback,
final judging, standalone evaluation, characterization and qualification.
The default is owned by the shared execution policy; evaluation, feedback and
preview callers inherit it, including across worker threads
(`tool_time_limits = false`). Declared backend `timeout_seconds` does not impose
an automatic cutoff on these jobs. Callers can explicitly select
`run_evaluation(..., limit_tools=True)` for bounded diagnostics; startup/version
probes retain their own bounded timeouts.

Feedback inherits an explicitly bounded workspace command's deadline and its
cancellation scope. Workspace commands and checks have no automatic time limit.
Normal final judging and result collection have no automatic deadline, and the
service does not derive one by adding backend timeouts. An explicitly configured
standalone evaluation allowance remains bounded and is persisted across recovery.
Nested calls and parallel jobs share any explicitly supplied deadline. Tool
failure and cancellation evidence remains available with the accepted candidate.
Phase budgets are specified by the
[session protocol](architecture.md#lifecycle-and-budgets).

Cancelling a process check propagates to native/container jobs and their parallel
workers. Cancelled jobs retain diagnostics and cannot publish successful
extraction. Later checks and final judging use independent cancellation scopes.

#### Automatic tool retries

The shared native/container executor permits at most three attempts for an
immutable EDA job, waiting one and two seconds before the next attempts. It retries
explicit native crashes (including PVS report-cleanup crashes) and recognized
license checkout failures. Capacity and server connectivity failures qualify only
when the native diagnostic explicitly identifies them. A `No such feature exists`
response is also retried because it can occur intermittently during startup;
it does not by itself establish that the feature is permanently absent or that
concurrency caused the failure. Persistent missing-feature responses stop at the
same attempt limit. The combined Cadence `LMF-02002` and
`FLEXnet ERROR(-2, 0, 0): Invalid license file syntax` checkout response also
receives this bounded retry; that response alone does not establish a permanent
configuration defect. Other explicit invalid-file, host, key and expiration
diagnostics remain non-retryable, including when they accompany this response.
Unrecognized exits and input errors do not trigger retries.
Completed DRC/LVS rejections and measurement failures
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

<a id="preview-troubleshooting"></a>

### Startup troubleshooting

| Symptom | Action |
| --- | --- |
| Docker missing or daemon unreachable | Check `docker version` and the current user's access; run `python -m benchmarking.eda doctor`. |
| Unsupported host architecture | Use Linux x86-64 for the maintained amd64 image. |
| Missing image | Pull/build a compatible image and select it explicitly. |
| Pinned PDK file absent | Run `python -m benchmarking.eda --dataset SOURCE fetch --case ID` and inspect the selected release. |
| Derived support missing | Reload the case to rebuild its content-addressed support binding. |
| Existing evaluation output directory | Choose a new output path; retain the old diagnostics. |
| Image build download failure | Check build connectivity and declared source digests. A host proxy can use the build command's explicit `--network host` selection. |
| Model authentication or endpoint failure | Inspect the selected [harness profile](running.md#native-harness-configuration); dry-run does not validate credentials. |

## Open EDA and geometry backends

Bind logical operations using the [task toolchain contract](tasks.md#tool-bindings-and-drc-waivers).
Each backend below defines its settings, required evidence and failure behavior.

### ngspice and Magic

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

#### Simulation inputs

ngspice writes each input role as `<role>.spice` and uses `deck.spice` as its entry
point. The declared testbench selects analyses and measurements:

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

#### Magic extraction

Magic takes the top cell and ordered `ports` from trusted configuration. Match
that interface to the authoritative netlist; later jobs consume the exported
netlist as-is. `magic-capacitance-docker` extracts capacitance only and records
`wire_resistance=false`. `magic-rc-docker` adds distributed resistance and
capacitance and can bind to `layout.extract_rc`.


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
feedback, with the native console retained as supporting evidence. Tool crashes,
execution/cleanup failures and missing/malformed interface reports remain `error`.
Optional `label_layers` is a
nonempty list of GDS layer/datatype pairs that may contain electrical text;
text on other layers is removed from the extraction copy without removing any
geometry. `case_insensitive_ports=true` aliases case variants to unique internal
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

When wire-resistance extraction is enabled, the RC adapter also compares port pairs
joined by resistor cards in the native topology and final RC exports. It rejects a
new resistor-only connection between previously separate topology ports,
including unintended isolated-body/substrate connections. Intentional resistor
connections already present in the topology remain allowed. This guard does
not prove internal device-terminal graph equivalence or substrate accuracy;
case-specific physical mapping and electrical calibration are still required.

SG13G2 Magic extraction treats well/substrate ties as ideal connections;
it does not preserve the finite `ntap1`/`ptap1` resistance cards used by the
source simulator netlists. Physical LVS can still
check explicit tap geometry. Cases using this RC boundary must disclose the
idealization and calibrate its effect on their declared nominal measurements.
It does not establish distributed well/substrate resistance or substrate-noise
accuracy.

Native network reduction can vary in low-level ordering, so byte-identical RC
netlists are not guaranteed across tool versions or runs. Compare extracted
results against the declared task measurements and tolerances.

The supported RC interface has one declared port per conductor. A native
topology check rejects multiple ports on one conductor: the installed Magic
can otherwise duplicate the resistance network or bypass it with an alias
resistor. A completed topology rejection is a candidate failure (`failed`) with
zero score; its same-conductor reason is exposed in process feedback. Case-specific
extraction warnings, models and calibration still require review against the
selected contract.

### Magic and Netgen Physical Checks

`magic-physical-docker` binds independently to `layout.drc` or `layout.lvs`.
Trusted settings select `check`, `technology`, `tech_name`, `style`, the frozen
`support` bundle, and optional positive `grid_subdivision`. LVS additionally
requires a bundled Netgen `setup`; DRC must not specify it. Top-cell and source
subcircuit names come from the task. Candidate-provided extracted netlists are
not accepted as LVS evidence.

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

The `klayout-geometry-docker` backend can evaluate `bbox_max` and functional
area objectives directly from GDS after independent physical gates. Tasks using
this mode omit `database` and `binding`. Connectivity-dependent constraints still
require both the native KLayout LVS database and its exact candidate binding;
omitting either cannot bypass connectivity validation.

### KLayout Physical Checks

`klayout-docker` selects `check = "artifact"`, `"drc"` or `"lvs"`. A job supplies
`layout` and `task`; LVS also supplies the authoritative `netlist`. Standalone
debugging can declare `parameters.top_cell`, `max_bytes` and the LVS `subcircuit`;
these must agree with `task` when both are supplied.

| Check | Required evidence |
| --- | --- |
| Artifact | Readable GDSII, published size bound, correct top cell, nonempty geometry and resolved hierarchy. |
| DRC | Completed declared decks, required report categories and zero unwaived violations. |
| LVS | Completed comparison against a nonempty trusted source, participation of the requested circuit and the declared named-port checks. |

DRC/LVS read a JSON profile from the frozen support bundle, declaring `deck`,
fixed `variables` and explanatory `scope`. DRC also declares `required_categories`;
optional `additional_decks` entries each declare `deck` and `required_categories`
with the same variables. Every deck runs independently. Any execution/report error
takes precedence; otherwise the gate sums counts and fails if any deck fails.
Required categories detect skipped groups rather than enumerating every rule.

Per-deck `report.db`, `report-1.db`, logs and completion markers remain separate
evidence with per-deck results. Reviewed case-local `parameters.waivers` select
exact markers under the [task waiver contract](tasks.md#tool-bindings-and-drc-waivers).
For LVS, `ignore_top_ports_mismatch` controls additional named-port checks.

A missing report, skipped run, crash or timeout is `error`; a completed check with
unwaived violations is `failed`. LVS database output is diagnostic evidence;
post-layout simulation uses a separate extraction job from the same candidate.

### IHP physical-check profiles

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
| `drc-upstream.json` | Pinned PDK GUI defaults: main plus extra `sg13g2_maximal.drc`, deep mode, density and antenna off. |
| `lvs-upstream.json` | Pinned PDK GUI defaults: explicit taps, native simplification and strict named ports. |

Evaluate the maintained circuit and candidate using the case's declared task
plan. See the [evaluation command](running.md#standalone-evaluation) and each case problem
for reference results and reproduction instructions.

<a id="geometry"></a>

### Geometry and Port Correspondence

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

For [commercial runtimes](#external-commercial-runtimes), `virtuoso-geometry-native` accepts `runtime`, `check`
(`artifact` or `geometry`) and `timeout_seconds`. XStream imports the frozen GDS
into an isolated OA library; Virtuoso queries hierarchy and arrays and measures
each non-text shape under its native occurrence transform, without building a
flattened copy of the design. The geometry check supports `bbox_max` and
`functional_bbox_area` with the same layer/datatype semantics above. It does not
support connectivity constraints. Neither KLayout nor an authoring bridge is
needed in this container. Import logs and native geometry measurements are
retained as evaluation evidence.

Both native geometry adapters check stream record lengths, directory/precision
and TEXT record syntax before importing the submitted bytes. In particular, a
TEXT label requires TEXTTYPE and ordered XY/STRING records; permissive OA import
does not establish validity for malformed labels. A confirmed format violation
fails the artifact gate and scores zero. The adapters preserve the submission
without rewriting records; license, execution and unclassified tool failures
remain evaluation errors.

For Synopsys runtimes, `customcompiler-geometry-native` accepts the same settings
and bounding-box constraints. It explicitly runs operator-installed Custom
Compiler on the host, in a fresh job directory. `importStream` preserves GDS
layer/datatype numbers in a generic OA library; native layout editing flattens
hierarchy and arrays before measuring non-text shapes. No reference or PDK
design library resolves submitted cells. Import logs and shape measurements
are retained. Native execution uses the declared license environment and does
not provide container isolation or automatically replace a failed Docker run.

Spectre evaluator containers and solver sessions with a declared Spectre module
allow executable mappings in their isolated workspace so that Spectre can load
compiled AHDL model libraries. The root filesystem and installed tool/PDK mounts
remain read-only.

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

LVS can export a native `klayout-lvs` database and a JSON binding. The binding records the candidate GDS, database digest, top cell, and logical-layer mapping. After validating the binding, the geometry adapter uses the native LVS database APIs for network correspondence and geometry. Process support bundles declare deck-layer variables; the adapter reads the names actually registered by the run instead of fixing runtime indices such as `l10`, and it does not modify upstream rules.

Magic's SPICE export drops the `!` from `!CONTROL`, causing a collision with `CONTROL`. The extraction adapter first uses KLayout on an isolated GDS copy to give unsafe interface names unique aliases, preserves the original candidate and mapping evidence, and then uses the native SPICE reader to check the count, names, and order of exported ports. It does not rewrite the original task netlist; simulation connects through the declared port order.

The `model-calls` diagnostic profile accepts ngspice model calls for
`sg13_lv_nmos`, `sg13_lv_pmos`, `cap_cmim`, `ntap1` and `ptap1`. Its
`sg13g2-model-calls.lvs` entry point is generated from the KLayout support
manifest and includes the unchanged upstream runset. This profile is selected
explicitly when interpreting these model calls. A KLayout reader delegate maps these `X` calls to the native PDK device handlers, preserving their terminal
mapping, parameter units, simplification and comparison rules. Other `X` calls
retain normal hierarchy handling, and CDL primitive cards retain their
native interpretation. Use circuit-local `.param` definitions and compact
expressions on model calls; expression parsing and parameter scoping remain
those of the pinned native reader. This is an input adapter, with no rule
waivers or new device models. Candidate scoring simulates only GDS-derived PEX. Other source dialects require
an explicitly validated adaptation.

### Fixed passive macros

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

### Candidate uniform transmission lines

`rlc-line-docker` implements `layout.rf_line` with a trusted process bundle
(`support`, `profile`), `image` and `timeout_seconds`. It consumes the prior
macro-cut `layout` and `binding`, the untouched candidate as `original`, `task`
and a trusted JSON `specification`. It exports `layout` (GDS), `binding` (JSON)
and `netlist` (SPICE). Native DRC checks the original; native LVS and extraction
check the resulting layout and retain its candidate and parent-proof digests.

The specification declares `cell`, `subcircuit`, `signal_layer`, `ground_layer`,
`landing_um`, `window_um`, `guard_um`, `ground_anchor`, three ordered `ports` and all
`conductor_layers`. Exactly one instance must contain a uniform rectangular
strip at local origin and the complete prescribed return plane. Quarter turns
and reflections preserve the grid. The process fixes width, return geometry,
optional regular ground perforations and permitted length range. Extra
conductors, branches, labels or altered cross-sections inside the modeled cell
are rejected. Surrounding conductors may enter the isolation region only
through the declared end access areas. Existing terminal metal, vias, return
wiring and all free circuit geometry remain subject to native physical checks.
`ground_anchor` names a separately verified fixed cell and a local `point_um`
inside its return metal. The drawn return plane must share one continuous
polygon on `ground_layer` with this transformed anchor. Net labels cannot
replace that physical connection. This interface requires same-layer return
wiring; multilayer return routes need a separately validated model boundary.

The model uses positive series DC resistance and inductance, parallel RL skin
branches and shunt capacitance in a finite pi ladder. Values scale with the
measured candidate length. The process must document its calibration source,
independent accuracy checks and approximation limits. Reusing a calibrated
cross-section permits routine RLC post-simulation without running a full-wave
solver for every candidate. It does not establish accuracy for new widths,
bends, return planes or neighboring conductors. Authors must validate physical
length controls, invalid geometry and disconnected return paths separately.
KPEX accepts the resulting SPICE as optional `model`, with its line proof in
`derivation`. It checks the model digest against that proof, retains the model
as evidence and appends its subcircuit definitions to the extracted candidate
circuit. Other supplied circuit models are rejected. The simulation fixture and
its other inputs remain identical between source and post-layout evaluation.

### HBT core simulation support

The HBT model profile (Dataset: `tasks/ihp-sg13g2/pdk.toml`) prepares the pinned
HBT, resistor and capacitor include closure, using native ngspice VBIC and
OpenVAF-compiled R3_CMC and MoM models. The source retains the R3_CMC license and
NOTICE with the IHP adaptation. No compact-model source is patched.
The `sg13g2-hbt-rc-docker` backend combines candidate-only KLayout native
HBT extraction with Magic distributed interconnect R/C. Its `klayout_support`
and `magic_support` settings use separately reviewed bundles; declare their
profiles through `support_profiles` in the [resource manifest](tools.md#agent-pdk-resources). Physical LVS remains a
separate gate against the maintained circuit, including the named interface.
For the fixed `npn13G2` emitter, the native extractor reports bounding-box X/Y
dimensions as `we`/`le`. The adapter accepts the complete 70 × 900 nm pair in
either axis order, preserving native `Nx` and terminal connections and passing
only the fixed symbol's behavioral parameters to simulation. Other dimensions
remain errors. Native LVS still checks the source's declared geometry; this
serialization rule does not alter its comparison options or the PDK deck.

The `kpex-cc-docker` backend provides nominal 2.5D coupling capacitance.
Its `support` bundle and JSON `profile` declare the process name, bundled native
LVS deck, runset variables, substrate reference node and physical device
interfaces. Each device declares terminal order, extracted parameter units,
native reference-card prefix, and any supported-value constraints. Parameters
are read from native devices; the adapter never supplies missing geometry.
The process profile and support manifest enter backend identity. Tool settings
also include `image` and `timeout_seconds`.

Jobs consume candidate GDS, its native LVS database and a content binding.
When a prior fixed-macro job emits an extraction copy, optional `original` and
`derivation` inputs must be supplied together. Their content proof binds the
original submission, cut GDS and top cell; the independent native LVS binding
still binds that cut GDS to its candidate database. Both proofs enter evidence.
The backend independently extracts annotated geometry, compares it against a
reference exported from that candidate database, and consumes the persisted
native LVS verdict. It preserves the process's device and terminal-equivalence
rules. Physical classes are serialized through the declared interface, including
classes whose native geometry differs from KPEX's primitive writer API.
Undeclared models, unsupported geometry and missing or additional ports fail.
The process reference plane is bound to the task's declared ideal substrate.
Evidence includes both databases, candidate-derived reference, configuration,
geometry log and extracted netlist. This backend declares **CC only**: no wire
resistance or inductance. Tasks explicitly select this scope.

For upstream flows requiring HSPICE-style syntax, `ngspice-docker` accepts
`compatibility = "hsa"`. The effective `.spiceinit` is archived and the choice
is part of backend identity. The default remains the prepared model profile's
startup. Use ngspice 45 or later for this HBT flow.

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

### Qucs-S and Qucsator

The unified image provides `qucs-s`, `qucsator`, `qucsator_rf` and `qucsconv`
alongside ngspice. Qucs-S parses/netlists `.sch` files headlessly with
`QT_QPA_PLATFORM=offscreen`; simulation still selects an explicit backend.

The image does not provide Xyce. A task requiring Xyce needs a compatible runtime
and backend; Qucsator is not a substitute for that simulator.

The pinned ngspice build applies a one-line `xfer` DC Jacobian correction:
the derivative equals the real transfer value at the first table frequency,
matching the model's existing DC output equation. Without this derivative,
even a linear negative feedback circuit can fail its operating-point solve.
The image smoke check compares `xfer` with an equivalent VCVS against an
analytical DC solution. This correction does not add S-parameter thermal noise
or transient support; those analyses require an appropriate passive model.

## External commercial runtimes

Operator-installed EDA and PDKs can be bound to the shared evaluator without
entering the public resource cache. The public package includes generic
commercial tool adapters; it bundles no vendor software or process data.
Commercial evaluation uses licensed tools and an explicitly installed PDK on
the trusted operator host. Agent solving uses the declared commercial Docker
image. The evaluator receives only frozen submissions and declared evaluation
inputs; it does not run inside or read the writable solver workspace.

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
tool's settings after loading its modules. For example, an HSPICE compatibility
setting `LD_PRELOAD = "/lib64/libudev.so.1"` is scoped to HSPICE rather than every
process in the shared image. License values must still be forwarded by name.

Some rootless host-network deployments do not mount sysfs. Calibre 2025.2 can
then detect zero NUMA nodes and crash with `SIGFPE` during LVS initialization.
For those deployments, declare `CALIBRE_DISABLE_NUMA = "1"` under
`[runtime.tool_environment.calibre]`. This tool setting applies after module
loading, reaches both solver commands and evaluator launches, and enters runtime
identity without changing process rules or container privileges.

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
Trusted author/operator utilities `eda.oa.virtuoso.VirtuosoGDSNative` and
`eda.oa.customcompiler.CustomCompilerGDSNative` import explicit frozen GDS
assets into fresh libraries, run native transactions, and export selected cells
and diagnostics. They retain tool failure and timeout evidence; they do not
automatically change execution location or expose a script endpoint to solvers.
Process-specific layout recipes and circuit rules remain with their authors.
No public `profiles` or cached `agent` bundle is supported for an external PDK.
The case's `distribution` controls delivery and is independent of process
installation. Owners must classify asset rights before delivery.
The local service accepts an explicit `--solver-runtime NAME` only when NAME
matches the case's external process declaration. `--solver-image` selects
the solver image; evaluator backends use the operator host. `--image` selects
open EDA evaluator images and does not override commercial host execution. No cached
Agent bundle is required. The process runtime supplies read-only installations
and minimal tool license access. Provider credentials, reference files and operator
repositories stay outside the container. Solver mounts cannot shadow trusted
input/protocol/system paths, or override the trusted reader environment. Resource
limits and frozen submissions still apply. Both solver runtime and evaluator
identities are recorded. The image must provide Python 3.12+ as `/usr/bin/python3`
and `python`. Session commands bypass image entrypoints; load the selected
modulefiles in each shell. Commercial recipes and experiment configuration belong to
the operator, including license/network policy and installation immutability.

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
The runtime provides `ASSURA_ROOT`, `assura`, `quantus` and Python; author OA is
not used. Junction geometry is required by default. An explicit
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
and any orphaned workers; nonzero worker exit status is an error. The native
job timeout bounds the whole process tree. A parent completion message alone is insufficient. Only the extracted
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
port declaration. Floating fill uses Calibre's `REDUCED` equivalent capacitance
network. No source circuit substitutes for extraction.

Recorded Calibre settings group rule bindings, DRC execution, LVS comparison,
and RC adaptation separately. Quantus and StarRC record CCI connectivity and
their extraction settings alongside the shared Calibre configuration.

`inline_includes` maps exact quoted or unquoted include names to mounted process
files whose contents must be inserted before adapting run I/O. Each name must
match once. This handles an xRC wrapper including an LVS deck with single-valued
run controls, without duplicating those statements or changing device rules.
Optional `rule_control = "@filename"` selects a fixed native process wrapper
from `runtime.control_files`. The native rule author owns its device definitions
and validation; the framework only binds run I/O. A TVF wrapper that reads another
deck must itself exclude that deck's fixed run I/O before emitting its rules.
`require_erc_summary = false` is explicit for decks with no standalone ERC
RuleChecks; the default still requires the ERC report.

Process-specific LVS reduction and parameter-comparison rules belong to native
process resources, selected by `rule_control` or `rule_includes`. The framework
does not synthesize device policies. Extraction may declare `mos_parameters`,
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

<a id="native-calibre"></a>

`calibre-native` runs these checks and extraction on the operator's host installation. It uses declared module/resource and
license bindings with identical host/target paths, copies frozen GDS/CDL into a
fresh job directory, and enforces process-group timeouts. It is a trusted
evaluator backend, separate from the solver runtime. It
runs as the operator user with host resources and network; container CPU,
memory, filesystem and network isolation do not apply. Identity records this
execution mode, UID/GID, tool release and declared resources. Select this mode
only in a reviewed operator task configuration; solver isolation is unchanged.

### Calibre with Quantus

`calibre-quantus-native` uses the same explicit operator host execution for
Calibre LVS/CCI followed by Quantus coupled RC. It requires `deck`,
`technology_env` (an environment entry naming a technology directory within a
declared, noncredential resource mount), and `ground` (a declared top-level port).
The technology can share the PDK mount; include its files or directory in that
mount's `identity_paths`. The runtime selects
both `calibre` and `quantus` module profiles. Frozen GDS and source bytes remain
unchanged; source data is used for LVS and naming, while devices and parasitics
come from annotated candidate geometry. Jobs declare `ports` and optionally an
integer `temperature_c` (default 27). The adapter preserves CCI device templates,
requires a complete non-blackboxed LVS match and normal Quantus completion, and
validates extracted MOS geometry before returning a simulation netlist. Identity
includes stable Quantus release/build fields and the worker launcher. Evidence
retains the LVS/CCI/Quantus logs, controls, annotated device netlist and raw DSPF.
The operator must independently validate the selected technology and supported
device interfaces; this interface does not imply foundry certification.

### Calibre with StarRC

`calibre-starrc-native` uses the same operator host execution for Calibre LVS/CCI
followed by StarRC. It selects `deck`, `technology_env`, and resource paths
`grid`, `mapping`, `command_template`, `query_template`, and `hcell_file` within
the declared technology mount. Both `calibre` and `starrc` module profiles are
required. Optional `cores` (1–8) runs the vendor's manual distributed workers.
StarRC may reduce the worker count when fewer partitions are needed. Acceptance
requires successful worker exits, normal extraction completion and zero reported
errors; completion-message counts need not equal the requested worker count.
The vendor command policy is retained; run-specific file paths, top name,
temperature, node reporting and worker count are bound explicitly.
Optional `extraction_mode = "RC"` fills an existing template extraction setting;
`device_pin_file` binds an existing `CALIBRE_OPTIONAL_DEVICE_PIN_FILE` setting to
a resource path inside the declared technology mount. Missing or duplicate
template settings fail rather than silently appending defaults. A job declares
`ports` and optional integer `temperature_c` (default 27). Acceptance requires
complete named-port LVS, successful workers with normal completion and zero
reported errors, and valid extracted physical device geometry and R/C. The raw
DSPF, controls and native logs remain evidence. Frozen GDS/CDL bytes are preserved;
the source is used for LVS and naming, not as a substitute for extraction.

### ICV with StarRC

`icv-native` selects operator host ICV with `check = "drc"`, `"lvs"`, or
`"rc"` and a mounted `deck`. Optional `lvs_control = "@filename"` selects a
declared native runset wrapper, retaining the mounted deck's include directory.
LVS and RC settings require `lvs_checks`, a mapping from native report check names
to expected device-class counts. The adapter verifies this declared coverage and
the native comparison verdict, and passes source inputs unchanged. Process
resources own property comparison and device-equivalence policies.
DRC requires a completed report for the requested top, positive rule coverage
and zero violations. `allowed_unexecuted` records known inactive rules without
suppressing checks.

RC uses native ICV/StarRC, requiring `grid` and the job's ordered `ports`.
It runs coupled RC at 25°C with `ground` (default `GND!`). Optional
`starrc_control = "@filename"` appends declared native StarRC commands, including
explicit process choices for power extraction. Three-terminal
MOS models, geometry and RC cards remain as emitted by StarRC. The existing
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

These Synopsys backends explicitly use the trusted operator host with identical
mount source/target paths. They stage immutable input bytes in fresh job
directories, enforce process-group timeouts and redact passed license settings
from text evidence. Stable releases, resource digests and launcher identity are
recorded. Container CPU, memory, filesystem and network isolation do not apply.
They are evaluator adapters; solver resource filtering and runtime deployment
remain the operator's responsibility. Custom Compiler authoring uses its own
native library definitions and Tcl interface, independent of Virtuoso.


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

The backend setting `max_parallel_jobs` defaults to 1; a positive integer opts
into concurrent independent jobs with isolated tool workspaces. Select it within
the installation's license and resource capacity. Candidate runs inside one
calibration job remain sequential.
All Spectre variants execute on the operator host in fresh job directories.
Frozen input bytes, process-group timeouts and failure evidence are preserved.
Host execution and tool versions are recorded without evaluator image identity
or container resource limits. The retired container `memory_mb` setting is not
accepted; solver container limits remain separate.

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
`ax`, `mx`, `lx`, or `vx`) and `+mt` (`threads` is a positive integer, default 4).
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
Model compatibility belongs to the qualified process extraction and simulator
resources.

Quantus keeps physical instances and process resistor models in native output.
`require_junctions = true` rejects missing MOS AS/AD/PS/PD unless the process
explicitly declares a junctionless device. Numeric interconnect R/C are retained;
numeric resistor cards carrying `segr`, `segl`, `segw`, `effl` or `effw` are
rejected because a flattened process device is not an ordinary wire resistor.
Primitive process resistors require valid native L/W; supplied bipolar area and
multiplicity must be positive finite values and retain their native units.

Author validation must show that declared negative controls remain rejected.
A tool defect may be fixed in a fixed, independently validated extraction flow,
but evaluation does not reconnect a candidate or substitute expected devices.
Unsupported native combinations remain development cases. Preserve diagnostics
and distinguish a completed candidate rejection from an infrastructure failure.

## Spectre measurement profiles

These parameters belong to jobs using the [Spectre backends](#spectre). Select one
measurement profile per job; incompatible profiles are rejected. The trusted
deck supplies stimuli and saved signals. Scoring and functional bounds are
separate declarations in the [task evaluation plan](tasks.md#evaluation-plan).

### DC sweeps

The `dc_sweep` profile reads `results/sweep.dc` from a named `sweep dc` analysis.
It declares `axis`, `axis_unit` (`V` or `degC`), a positive `max_step`, affine
`traces` with physical units, and `measures`. Supported operations are `at`
(with an `at` coordinate), `min`, `max`, `span` (with closed `start`/`stop`
windows), and `ppm_per_axis`. The last also requires `reference_at` and returns
`1e6 * (max-min) / (reference * (stop-start))` in `ppm/V` or `ppm/degC`.
The reference must be positive and inside the window. Incomplete, nonfinite,
nonmonotonic or overly sparse sweeps fail; endpoints use linear interpolation.
Use a parameter name distinct from saved node names to avoid ambiguous PSF signals.

### Discrete calibration

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

### AC response

The AC profile also reports `phase_margin_deg`: 180 degrees plus the unwrapped
transfer phase at the first downward unity crossing, interpolated on log frequency.
Authors must establish negative-feedback polarity, a valid operating point and a
sufficient sweep; this measurement alone does not prove closed-loop stability.

### AC transfer

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

### Waveforms

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

### Window comparisons

`mean_difference` selects a `trace` and subtracts its mean over
`reference_start_s`–`reference_stop_s` from its mean over `start_s`–`stop_s`.
Both windows must be complete; the result retains the trace's physical unit.

### Phase difference

`phase_difference` declares two crossing events (`event`, `reference_event`),
unit `s`, integer `min_edges` of at least two, and `statistic` (`std` or `span`).
Both use the common measurement window. Their first edges are aligned once by
the nearest initial event, and subsequent edges are paired by ordinal position.
Population standard deviation or peak-to-peak span uses these continuous time
differences, preserving accumulated drift and cycle slips. Too few aligned
edges rejects the candidate response. This observation does not establish frequency lock by itself.

### Crossing events

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

### Cycle measurements

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

### ADC transfer

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

### Settling time

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

### Coherent digital ADC spectra

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
