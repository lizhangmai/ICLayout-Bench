# Architecture and Extension Interfaces

ICLayout-Bench measures an Agent's ability to turn authoritative netlists,
constraints and process resources into GDS. Each measurement covers one task,
one participant configuration and one independent repetition. The benchmark
provides task contracts, a session protocol, isolated evaluation and result
formats; participant harness internals remain outside its control. Mode labels
record measurement conditions and do not select or install a runtime. See the
[root README](../README.md) for the public scope.

<a id="repositories"></a>

## System roles and boundaries

ICLayout-Bench is an installable framework for local self-testing and participation
in a service. It loads a selected Dataset from an explicit local path or supported
Dataset repository revision. Task contracts and declared resources are inputs;
normal loading and evaluation do not require an authoring workspace or operator
platform.

Authors prepare task descriptions, static inputs, evaluation declarations and
reference evidence. Operators independently decide what to admit, how to deploy
a service, and whether results or materials may be published. Authoring evidence,
participant credentials and reference layouts are not solver inputs. A solver
receives only the declared task inputs and reviewed resources, with writable
access limited to its session workspace. The evaluator uses immutable candidate
snapshots in a separate trusted environment.

Use the installed package's documented CLI, task format, HTTP session contract
and result formats as integration surfaces. Deployment policy, accounts,
authorization, resource capacity and disclosure remain responsibilities of the
service operator. Local identities and successful protocol exchanges do not by
themselves certify a participant or grant rights to publish task materials.
Tool images, PDK resources and local preparation are described in the
[tool guide](tools.md).

The `python -m benchmarking.service` server is for local development: it binds
to loopback and serves one active session. It is not a production deployment.
Operators provide deployment authentication, TLS, capacity and task admission.
Model credentials stay with the participant host or a controlled gateway; solver
containers receive neither those credentials nor reference layouts.

Python callers may pass a dedicated `session_control` to `LocalService` when
composing the local HTTP adapter. `SessionControl` accepts the run implementation
and session factory; the same authenticated controller operations, durable replay
and result projections remain in use. A supplied supervisor belongs exclusively
to that controller, whose shutdown closes and joins its live sessions.

Author tools may use `benchmarking.engine.qualification.run(runtime, output,
retain_evaluation=True)` with a runtime from `benchmarking.engine.runtime.load_case`.
It keeps raw evaluation evidence in `output/evaluation`, including failed runs;
only a passing complete evaluation writes `qualification.json`. The default keeps
only that compact report. The output must not already exist. To compose author
backends, use `dataclasses.replace(runtime, backends=...)` before calling `run`;
no module globals need to be modified.

### Static website hosting

The repository can host an operator-reviewed static website on its `gh-pages`
branch. That branch contains generated HTML, browser assets and explicitly
published data only. Website authoring, source data, accounts, review and export
tooling remain external operator responsibilities. Package installation and CI
do not depend on this branch or on a website backend.

The optional `Publish reviewed website` workflow is manually dispatched from the
main branch after a reviewed `gh-pages` commit has been pushed. Configure the
repository's Pages source as **GitHub Actions** and restrict the `github-pages`
environment to the main branch. The workflow verifies the release file manifest
and deploys that branch's static artifact; it does not build or import an operator
application. Alternatively, GitHub's built-in branch publishing can serve
`gh-pages` directly when no custom workflow is enabled. Choose one method.

Static publication is a public snapshot, including Git history. Withdrawal
requires a new export and deployment; it cannot revoke already downloaded or
historically committed bytes. A custom domain can later point to an operator
service while preserving public route and record identifiers.

<a id="execution-entry-points"></a>

### Participant and evaluation entry points

`python -m benchmarking.run` runs participant experiments from explicit
configurations, task selections and repetitions. `python -m benchmarking.engine.cli` inspects tasks and evaluates or characterizes candidate
layouts; it does not launch a participant experiment. See the [participation guide](running.md) for configuration and command details.

| Participation method | Participant control | Execution location |
|---|---|---|
| Built-in harness | An installed Codex, Claude Code, DSH or other supported harness owns its model and action loop. | Participant host; layout commands run in the isolated solver workspace. |
| Harness with declared tools | The harness uses declared instructions and optional MCP or command-line tools. | MCP processes may run on the participant host; layout tools run in the solver workspace. |
| Custom participant | A participant command owns its decision loop and uses the HTTP client or MCP interface. | Participant-selected host, container or remote deployment. |

Install and authenticate vendor CLIs separately; the package does not install
them. A custom participant is responsible for forwarding the session contract
to its runtime. Installing a Python library or layout abstraction alone does not
require a new harness.

### Evaluation identity and process checks

A participant configuration freezes its instructions, declared tools and
optional solver image. The evaluator independently identifies the task, trusted
inputs, backend resources and evaluation implementation. A/B comparisons require
matching evaluator context and limits; participant configurations remain
separate conditions. Local identities never imply operator verification.

The local HTTP service may advertise `process-feedback`. When available, the
participant client or MCP `check` operation asks the service to evaluate the
current declared output using the normal trusted evaluation path. A check consumes
the existing solve deadline and diagnostic allowance, creates no submission,
and does not replace final independent evaluation. Inline and paginated check
reports expose candidate measurements and engineering diagnostics, without total
scores or scoring breakdowns. Complete scores belong to the final result after
execution ends. Solver-authored EDA commands remain exploratory.

Authors should retain qualification evidence for delivered task inputs and
reference layouts. The public evaluator can verify an explicitly supplied
reference against its recorded run and declared evaluation inputs; this does not
certify author identity, material rights or operator publication decisions.

<a id="result-handoff-and-storage-ownership"></a>

## Result handoff and storage ownership

| Boundary | Owner | Responsibility |
|---|---|---|
| Evaluation and terminal export | Installed framework, invoked by a participant | Run the declared experiment and write results without changing their evaluation mode. |
| Participant experiment workspace | Participant | Select configurations, retain original exports and control any local archive. It has no operator website credentials or publication authority. |
| Optional local archive | Participant or operator, using the documented archive interface | Index exports for local inspection; it is separate from an operator website. |
| Website ingestion and retained archive | Operator | Select imports, validate and deduplicate packages, retain metadata and artifacts, and track import diagnostics. |
| Public disclosure | Operator | Review and publish results and assets, calculate rankings and handle withdrawal. |

Candidate submission to an evaluation session, transfer of terminal exports,
archive import and publication are separate operations. The optional delivery
client creates a portable package and can upload it only when a deployment
explicitly enables participant access. A successful transfer reports receipt or
a durable job identifier, not a publication promise. See [website result
delivery](running.md#website-result-delivery).

Participants do not receive website database credentials. An operator may also
import from a configured read-only filesystem location; a shared mount is a data
handoff, not a source dependency. Importing or moving results never upgrades the
recorded evaluation mode. Direct production database writes require explicit
operator authorization.

<a id="http-session"></a>

## HTTP session contract: `layout-http`

This section owns the wire contract. JSON uses UTF-8, finite numbers, UTC RFC 3339
timestamps and lowercase SHA-256 hex digests. Paths below are relative to the
service URL. Session routes start with `/sessions`.
Responses include `protocol: "layout-http"`. Clients ignore unknown response
fields but reject unknown protocol identifiers. Unknown request fields, malformed JSON
and wrong types return `400`. The protocol field is response metadata, not a
required request member.

Use `Authorization: Bearer <token>` on every request. An operator-issued access
token can create sessions; creation returns a fresh token scoped to that one
session's operations and evidence. Use TLS except on loopback for development.
Model, website and session credentials never enter EDA containers. Explicit
commercial runtimes may provide only the reviewed tool license access described
in [external commercial runtimes](tools.md#external-commercial-runtimes).
Cross-session and nonexistent identifiers
both return `404` after authentication.

Errors have the shape
`{"protocol":"layout-http","error":{"code":"invalid_request","message":"...","retryable":false}}`.
Terminal results may include `failure_category` to distinguish service
interruption, evaluator tool errors and unknown failures; task verdicts remain
independent of participant process exits. Messages exclude host paths, exception traces, hidden materials and secrets.
Status/code pairs are `400 invalid_request`, `401 unauthorized`, `404 not_found`,
`409 conflict`, `410 session_closed`, `413 too_large`, `429 budget_exhausted`,
`503 unavailable`, `500 infrastructure_error`. Only `503` is retryable by default,
with `Retry-After` seconds. A transport timeout has unknown outcome: replay the
same idempotency key or query status before issuing another mutation.

### Lifecycle, concurrency and retries

States are `active → closing → evaluating → complete`, or `error` on an
infrastructure failure. Creation responds only after inputs and isolation are
ready. The deadline starts at `created_at`; disconnects and client exit do not
pause it. Expiry closes the session, cancels execution, selects the last accepted
candidate and evaluates it. Explicit close uses the same selection rule. Queries
remain available until the creation response's `retained_until`. After closure,
new mutations return `410`; identical acknowledged retries still return their
original response. A restart losing a live workspace marks the session `error`
and retains acknowledged snapshots and receipts; running execution records become
`error` with no inferred exit code. Interrupted work is not success. A creation
interrupted before its durable response returns `500 infrastructure_error` on
same-key replay instead of creating a replacement.

The authoritative solve budget is `[task].hours` in the case definition.
The service publishes it in `task.description.hours` and derives
`limits.wall_seconds` from it; participant TOML and the service CLI cannot
override it. It is covered by task identity and cannot change during recovery.

The creation response's `limits` contains `wall_seconds`, `cpus`, `memory_mb`,
`pids`, `workspace_mb`, `max_file_bytes`, `max_response_bytes`,
`max_candidate_bytes`, `max_command_seconds`, `max_log_bytes`,
`opinion_requests`. The server enforces them. A command is
capped by remaining session time. The local service sets `max_command_seconds`
to `wall_seconds`; the built-in participant runner adds no mutation-count budget
or shorter execution deadline. Repetitions belong to experiment scheduling.
Logs are bounded with explicit truncation.
Only one execution or workspace read/write/snapshot can run at once; conflicting
requests return `409`. The deadline and explicit close take precedence and stop
execution before freezing the final selection. Failed creation never returns an
active session; operator capacity limits bound creation and retained storage.

Every POST requires `Idempotency-Key` (1–128 ASCII letters, digits, `-`, `_`, `.`).
The namespace is authenticated principal + route + key. The server durably stores
the validated request and response before acknowledging success. Identical JSON
values replay the same response; reusing a key with different content returns
`409`. Concurrent identical requests wait or return retryable `503`, never run
twice. A submission retry does not reread the workspace. Creation replay reveals
the original token only to the original access principal. Records persist until
`retained_until`. Validation failure does not accept a submission; new keys mean
new operations.

### Operations

`{sid}`, `{eid}` and `{submission_id}` are opaque server identifiers. Request
fields are required unless marked optional. Creation returns `201`; execution
and close return `202`; other successful operations return `200`. Every response
also includes the common `protocol` field.

| Method and path | Request | Success fields |
|---|---|---|
| `POST /sessions` | `task_id`, `condition` | `session_id`, `session_token`, status fields, `task`, `capabilities`, `limits`, `tool_identity`, `retained_until` |
| `GET /sessions/{sid}/reports/{report_id}?offset=N` | None | Participant diagnostic JSON `content`, character `next_offset`, `has_more`; session-token scoped, available after closure |
| `GET /sessions/{sid}` | None | `session_id`, `state`, `created_at`, `deadline`, `remaining_seconds`, `active_execution_id` (nullable), `last_submission` (nullable receipt), `diagnostics` (request/completion counts and elapsed seconds), `opinions_remaining` |
| `GET /sessions/{sid}/file?path=...` | URL-encoded relative path | `path`, `content_base64`, `sha256`, `size_bytes` |
| `POST /sessions/{sid}/files` | `path`, `content_base64` | `path`, `sha256`, `size_bytes` |
| `POST /sessions/{sid}/executions` | `command` (shell string), `timeout_seconds` | `execution_id`, `state` |
| `GET /sessions/{sid}/executions/{eid}?offset=0` | Nonnegative byte offset, default 0 | `execution_id`, `state`, `exit_code` (nullable), `log_base64`, `next_offset`, `truncated` |
| `POST /sessions/{sid}/executions/{eid}/cancel` | `{}` | `execution_id`, `state` |
| `POST /sessions/{sid}/submissions` | `path` | Receipt fields below |
| `GET /sessions/{sid}/submissions/{submission_id}` | None | Receipt fields below |
| `POST /sessions/{sid}/diagnostics` | `submission_id` | `diagnostic_id`, `submission_id`, `candidate_sha256`, `state` |
| `GET /sessions/{sid}/diagnostics/{diagnostic_id}` | None | `diagnostic_id`, `state`, `summary` (nullable), `candidate_sha256` |
| `POST /sessions/{sid}/opinions` | `text`, optional `submission_id` | `opinion_id`, `received_at` |
| `POST /sessions/{sid}/close` | `{}` | `session_id`, `state`, `last_submission` |
| `GET /sessions/{sid}/result` | None | Result fields below |

`capabilities` lists optional implemented operations (`diagnostics`, `opinions`).
Absent optional operations return `404` and their budgets are zero. All other
operations are required. Execution states are `running`, `complete`, `cancelled`,
`timed_out`, `error`; diagnostic states are `running`, `complete`, `error`.
A nonzero shell exit is still `complete`, not a task verdict. Log slices obey
`max_response_bytes`; offsets refer to raw bytes. Decode base64 before joining
slices; poll until terminal and drained. Truncation means bytes beyond the stored
log limit were discarded; `next_offset` never advances beyond retained bytes.

`task` has `id`, `sha256`, `description` (public solver task description),
`input_paths`, `workspace_root: "/workspace"`. Inputs are read-only under `/task`,
approved resources under `/resources`. Only `/workspace` is accessible through
file APIs. Paths use POSIX relative syntax excluding empty segments, `.`, `..`,
NUL, absolute paths, symlinks and special files. Resolve beneath the workspace
without races against commands; writes are atomic. Commands use `/bin/sh -lc`
in `/workspace`, with no network by default, no model, website or session
credentials, references or private repo mounts. An explicitly selected commercial
runtime may provide reviewed tool license access and an operator-restricted
license network as described in the [tool guide](tools.md#external-commercial-runtimes).

Receipts contain `submission_id`, `sequence` (increasing within the session),
`candidate_sha256`, `size_bytes`, `accepted_at`. The server snapshots a bounded
regular GDS file at the declared task output path while execution is quiescent, stores immutable bytes and durably
records acceptance. Acceptance proves delivery, not physical validity. The last
accepted sequence wins; rejected requests never erase previous submissions.
Final evaluation reads those immutable bytes in a separate trusted environment,
without model credentials or writable solver paths. Diagnostics consume a separate
budget, bind to accepted snapshots and expose only approved summaries. Opinions
are unreviewed observations, independent of submissions and scores.

### Conditions, results and export

`condition` identifies the participant Agent: `harness_kind` (`agent`),
`harness_id`, `harness_version`, `model`, `prompt_sha256`, `configuration_sha256`.
The last two may be null when unknown. Metadata does not certify model
identity or absence of human assistance. Different Agent configurations remain
separate comparison groups.

Results contain `session_id`, `state`, `task_id`, `task_sha256`, `condition`,
`tool_identity`, `limits`, `evaluation_mode`, `provenance`, `usage`,
`submission` (nullable receipt), `outcome`, `task_success`, `score`, `metrics`,
`failure_reason`, `evidence`. Before terminal state, verdict fields are null and
metrics/evidence empty. Terminal `outcome` is `pass`, `fail`, `no_submission` or
`error`. Infrastructure error has null success and score; no submission has false
success. Score uses the public task score envelope and incomplete-attempt policy.
Metrics retain units and missing values from the evaluation specification. Do
not conflate physical failure, no submission and infrastructure errors.

`evaluation_mode` describes who controls execution: `self_run` for participant-run
experiments, or `controlled_run` for operator-controlled execution with frozen
conditions and checked evidence. It is independent of pass/fail, score, publication
and model identity certification. The field is required and accepts only these two values.
`provenance` maps `candidate`, `interaction`, `condition`, `usage` to
`server_observed`, `participant_reported` or `unknown`. `usage` contains nullable
`input_tokens`, `output_tokens`, `cached_input_tokens`, `reasoning_output_tokens`,
`cost`. Direct local model usage is unknown to the service, never zero-filled.
`tool_identity` records immutable image identity and public implementation revision.
`evidence` is a list of reviewed artifacts with `path` (session-scoped API-relative
URL), `sha256`, `size_bytes`, `media_type`; it may be empty. Evidence routes require
the session token and never expose private host paths or unreviewed judge files.

Analysis retains task/tool identities, budgets, conditions, provenance, candidate
receipt and nullable outcome data. Simulator runs are protocol tests, never model
scores. Hidden-task result export requires disclosure review.

Participant adapters may supply named native trace bytes through the optional
`native_traces` hook. The adapter selects its own native records and excludes
configuration and credential stores; participant export applies attempt-wide
secret redaction and retains those records under `native/` before runtime
cleanup. Observation exports carry the same records in `native-traces.zip`.
Native contents remain participant-reported and never change evaluation trust
or scores. Shared export and recovery modules do not interpret vendor logs.


<a id="ownership"></a>

## Evaluation observation and participant control

The participant harness owns its conversation, model calls and tool choices.
ICLayout-Bench supplies the task, isolated workspace, HTTP operations, enforced
budgets, observation and independent scoring; it does not choose the participant's
next action.

`GET /sessions/{id}/observations?offset=0` is a read-only, session-token-scoped
view of successful API interactions. It returns `session_id`, `provenance`
(`server_observed`), `available`, ordered `events`, `next_offset` and `has_more`.
Offsets count events from zero; each event contains `sequence`, `timestamp`,
`kind` and `data`. Pages contain up to 100 events and approximately 256 KiB.
Poll from `next_offset` while `has_more` is true. Reading observations never
advances the participant, closes the session or consumes an action allowance.

Events may include session creation, accepted file reads and writes, execution
requests and completion, submissions, cancellation and closing. Denied requests,
participant-local activity and model reasoning are not included. Execution logs
remain available through the execution polling API. The observation endpoint
exposes API-visible material only; it does not reveal evaluator journals, hidden
inputs or judge diagnostics. Older services without the stream report
`available: false`.

The optional observation export can combine service events and a result with
explicitly supplied participant trace files. Its manifest distinguishes
`server_observed` from `participant_reported`; active-session snapshots are
partial. Trace coverage depends on the participant CLI, and hidden reasoning is
not assumed available. Participant usage counters do not overwrite service usage
or change a result's evaluation mode. Local traces are not uploaded automatically.

Public task schemas and scoring arithmetic remain auditable. The evaluator uses
frozen inputs and immutable candidate snapshots. Protocol simulators are for
interface testing only and cannot be analyzed as model measurements. Hidden-task
admission and aggregate disclosure remain operator responsibilities.

## Result archive and platform presentation

The optional `results` extra provides an offline archive CLI for importing,
querying and presenting terminal result collections. It preserves task, candidate
and condition identities and the recorded evaluation mode; importing a local
run does not certify it. The operator platform owns result browsing, review and
publication. The package does not ship a standalone viewer or frontend. See
[result storage and presentation](running.md#result-archive) for supported
commands and formats.

The archive accepts an `object_store` implementing `put(bytes) -> (sha256, size)`
and `path(sha256) -> Path`. The default stores content-addressed files locally;
operator integrations can supply another storage adapter. Artifact membership
and content digests are checked independently of the storage backend. The
`ResultStore` interface supports archive consumers that need transactional
imports and queries; operators retain ownership of publication and account data.

Local SQLite archives keep `results.sqlite3` with the associated `objects/`
directory. Back up or move them together after stopping readers and writers;
verify a restored copy before use. PostgreSQL is available for shared archive
metadata, with an associated attachment store required for all processes.
Neither backend is a website publication policy. See the running guide for
backup and migration details.

Result comparisons keep task, tool identity, budget, condition, provenance and
evaluation mode separate. Missing or failed observations remain explicit and
are not filled with zero. Task presentations are analysis assets, not solver
inputs. Catalog revisions and authored drawings are checked against the recorded
task and netlist identity; presentation changes do not alter scores or trust
labels.

<a id="verified-reruns-and-disclosure"></a>

## Verified reruns and disclosure

The [HTTP protocol](#http-session) distinguishes `self_run` from `controlled_run`.
Self-run experiments are organized by the participant, on a local or remote host.
Controlled runs require the operator to control execution, freeze conditions and
check the complete evidence; merely launching someone else's command is insufficient.
The operator records the task and input identities, participant configuration,
resources, budgets, repetition schedule, candidate bytes and independent verdicts.
Missing or modified evidence prevents verification. A declared remote model
identifier describes requested conditions; it does not attest to the provider's
internal implementation. Unknown usage remains null. Import, publication and
an official source label do not change the evaluation mode.

Restricted task data and evidence are supplied by the operator. Deployments must
enforce authorization, exposure and aggregate disclosure policies before running
restricted tasks or publishing results. Evaluation modes do not establish asset
rights or authorize disclosure. Generating a release artifact does not upload it
or create a leaderboard; release approval belongs to the operator.

## Pre-layout calibration and post-layout evaluation

Task authors supply fixed pre-layout measurements with the static task when the
evaluation uses them. Candidate evaluation runs candidate-dependent post-layout
checks and compares their observations against those frozen baselines; it does
not generate new author baselines during a participant run. See
[electrical quality](tasks.md#electrical-quality) for contract and invalidation
rules.
