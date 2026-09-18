# Architecture and Extension Interfaces

ICLayout-Bench measures an Agent's ability to turn authoritative netlists, constraints, and process resources into GDS. The system under test includes the harness, model, prompt, context strategy, and tools; each measurement covers one task, one configuration, and one independent repetition. The benchmark owns a small session protocol and treats harness internals as opaque. Declared mode labels record measurement conditions; they do not select or install a runtime. See the root [README](../README.md) for the current public scope.

<a id="repositories"></a>

## Repository responsibilities

Public provides both local self-testing and participation in an operator service.
All Public implementation lives in the `benchmarking` package. Its top-level
modules own observation, the client, protocol, task/score definitions and analysis.
`benchmarking.engine` owns preparation, isolated execution, immutable submissions,
EDA backends and independent evaluation. `benchmarking.service` is the HTTP adapter
over that engine. `benchmarking.participants` owns reusable CLI launch adapters,
configuration resolution, MCP bridging, lifecycle cleanup and trace collection;
`benchmarking.run` schedules explicit case lists and repetitions with bounded
concurrency per condition, independent sessions, and case-owned result reuse. These are subpackages of one distribution, not separately
installed products. Participant recovery uses the shared atomic file writer and
batch lease, with private per-session credentials and frozen experiment conditions;
see [recovery semantics](running.md#failures-retry-ownership-and-recovery). Local evaluation requires Docker and compatible tool/resources;
remote participation does not.

```text
benchmarking/
  client.py, protocol.py, observe.py, analysis.py, ...
  engine/     # shared evaluator and execution implementation
  service/    # HTTP transport and local server entry point
  participants/ # native Agent launch adapters and scoped MCP bridge
  run.py      # experiment runner entry point
```

ICLayout-Designs independently owns design development, reconstruction recipes,
editable schematic projects and static delivery generation. Bench consumes reviewed
static netlists, decks, layouts and SVGs; its installation, tests and runtime do not
require Designs. Designs may stage proposed task configurations, but Bench owns
the authoritative task contract, validation, evaluation and qualification. Changes
to development recipes do not update published tasks automatically.

Private owns `iclayout_bench_private`: controlled reruns, hidden-task admission,
internal batch verification, the operator website and reviewed releases. It reuses
Public's evaluation engine and evaluation-session HTTP adapter. Its separate
website API owns administrator authentication, import jobs, publication and asset
access; it is not another evaluator or a participant session endpoint. Hidden
tasks, deployment credentials and restricted evidence remain operator-owned.
Source dependency is **Private → Public**. Public installs and tests without Private.

UserTrial installs the Public wheel to run local self-tests and remote experiments.
It maintains concrete TOML configurations, dependency requirements and usage
instructions, and calls `benchmarking.run` directly. Framework regression tests
belong to Public. UserTrial has no test suite, runner/adapter implementation,
source clone or copied evaluator.
The public catalog checkout is an explicit data/build input for local preparation;
a prepared case can be served using only the installed wheel and Docker. The
`--public-root` preview option locates that catalog independently of Python imports.

PDK preparation belongs to the shared engine. Process manifests select pinned
upstreams or ciel prebuilt releases and evaluator profiles. The tool image
contains EDA programs; installed PDKs remain separately hashed resources. Evaluator
support and the filtered Agent mount derive from the same declared installation,
with explicit profile adaptations. The configurable download cache is disposable; fixed release pins and full
installation checksums remain authoritative during offline reuse. See the
[preparation contract](tools.md#external-sources).

### Execution entry points

`python -m benchmarking.run` is the participant experiment entry point. It owns
TOMLs, launch adapters, case/repetition scheduling, recovery and terminal exports.
`python -m benchmarking.engine.cli` owns task inspection, candidate evaluation,
characterization and inference preflight. It does not launch participant experiments.

| Method | Control program | Execution location |
| --- | --- | --- |
| Built-in harness | Installed Codex, Claude Code or DSH; Public supplies launch settings and observation | Participant host; layout commands execute in the service's isolated solver workspace |
| Harness with tool A | The same harness, with declared instructions, stdio MCP tools and/or A installed in a pinned solver image | MCP processes on the participant host; Python/CLI layout tools in the solver workspace |
| Custom participant | A declared command owning its decision loop and using Public's HTTP client or MCP bridge | Participant-selected host, container or remote deployment; the launcher must forward the session contract to that runtime |

Adding a Python library or layout abstraction does not require writing a new
Agent. Install it in the solver image and give the existing harness instructions
for using it. A custom command is appropriate when the participant already has
its own control program. Public supervises that command without implementing its
Agent loop. See [scheme configuration](running.md#participant-tool-schemes).

The solver environment and trusted evaluator are separate. A scheme freezes its
instructions, declared tool files, executable bytes and optional solver image.
The service attests a separate evaluator identity from the task, trusted inputs,
backend identities and evaluation implementation. A/B comparisons share only an
identical evaluator context and limits; scheme identities remain distinct.
Historical unsplit tool identities stay intact and are not promoted into new
attestations. Local identities never imply operator verification.

`benchmarking.engine.execution.run_session` requires the caller's session. It
records inputs, runs that session and evaluates its accepted snapshot. The HTTP
service supplies its attached workspace session; Private swarm supplies a frozen
Docker session. Private's HTTP rerun uses the same service and Public's process
supervisor while retaining operator freeze, evidence and verification policy.
Those operator workflows retain their different replacement and admission
semantics; ordinary users use the Public experiment entry point.

### Result handoff and storage ownership

| Boundary | Owner | Responsibility |
| --- | --- | --- |
| Evaluation and terminal export | Public implementation, invoked by UserTrial or another participant | Run the declared experiment, observe the evaluator and write the shared result format without changing its verification level. |
| Participant experiment workspace | UserTrial | Choose configurations, invoke the installed Public runner and retain original exports; it has no website database credentials or publication authority. |
| Optional participant archive | Public `benchmarking.results`, installed in the participant environment | Index exports for local inspection; this is separate from the operator website's database. |
| Website ingestion and retained archive | Private | Accept operator-selected exports, validate and deduplicate using Public code, store metadata and artifacts, and track import diagnostics. |
| Public disclosure | Private | Review and publish results and assets separately, calculate website rankings and enforce withdrawal. |

Submitting a candidate to an evaluation session, transferring terminal exports,
importing records and publishing them are separate operations. Public's
`benchmarking.transfer` owns the portable package contract and generic upload/status
client. When enabled by the operator, Private accepts authenticated HTTP uploads,
assigns account ownership and source labels, validates packages, and queues ingestion.
The participant's
`results_data` outbox only indexes its selected local archive; it is not a website
delivery queue. Evaluation `--endpoint` and upload `--website` are distinct services.

UserTrial exercises the installed Public client as an ordinary participant; it has
no website database credentials or publication authority. Private still supports
administrator-triggered imports from a configured read-only filesystem root.
A same-machine mount is a data handoff, not a UserTrial source dependency. Neither
upload nor import promotes an evaluation's recorded verification level. Configuring
the generic archive with PostgreSQL does not authorize direct production writes.

The archive accepts an `object_store` with `put(bytes) -> (sha256, size)` and
`path(sha256) -> Path`. Public supplies `FileObjects`; Private supplies S3 objects
with a disposable local cache. `ResultStore.artifact` checks SQL membership and
content digests regardless of storage. Public's SQLAlchemy `results.schema` and
`ensure_record` support transactional joins and insert-once records; Private owns
its publication/ownership tables and queries. This avoids per-table forwarding
APIs and private-method overrides. Schema changes require coordinated consumers
and migrations; no database schema or recorded identity is changed by choosing
an object adapter.

See [website result delivery](running.md#website-result-delivery) for the package,
client commands and failure/retry contract. Private owns provider configuration,
email delivery, accounts, authorization, storage, review and publication.

Local self-testing and operator-service participation use `layout-http.v1`,
the same task checks and scoring arithmetic.
Local results are always `local_development`; a harness name does
not certify a participant-controlled run. Only a frozen evaluator-operated rerun
can receive `evaluator_verified`. Equal task, resources, engine and tool identities
are needed to compare local and operator results; hidden tasks can differ.
`tool_identity.public_revision` is a `sha256:` content identity of the installed
Public implementation, including packaged runtime resources, independent of Git.

The local service binds to loopback, supports one active session and advertises
no optional diagnostics/opinions. It retains receipts across restart, marks lost
live work as an error, and requires manual cleanup after retention. It is a local
development server, not a supplied production deployment. Operators must provide
their deployment authentication, TLS, capacity and task admission arrangements.
Model credentials stay with the local harness or controlled host gateway; solver
containers receive neither credentials nor reference layouts.

<a id="http-session"></a>

## HTTP session contract: `layout-http.v1`

This section owns the wire contract. JSON uses UTF-8, finite numbers, UTC RFC 3339
timestamps and lowercase SHA-256 hex digests. Paths below are relative to the
service URL. Version 1 uses `/v1`; incompatible changes require another version.
Responses include `protocol: "layout-http.v1"`. Clients ignore unknown response
fields but reject incompatible versions. Unknown request fields, malformed JSON
and wrong types return `400`. The protocol field is response metadata, not a
required request member.

Use `Authorization: Bearer <token>` on every request. An operator-issued access
token can create sessions; creation returns a fresh token scoped to that one
session's operations and evidence. Use TLS except on loopback for development.
Credentials never enter EDA containers. Cross-session and nonexistent identifiers
both return `404` after authentication.

Errors have the shape
`{"protocol":"layout-http.v1","error":{"code":"invalid_request","message":"...","retryable":false}}`.
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
`diagnostic_requests`, `opinion_requests`. The server enforces them. A command is
capped by remaining session time. The local service sets `max_command_seconds`
to `wall_seconds`; participant adapters add no mutation-count budget or shorter
execution deadline. Repetitions belong to experiment scheduling. Logs are bounded with explicit truncation.
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
| `POST /v1/sessions` | `task_id`, `condition` | `session_id`, `session_token`, status fields, `task`, `capabilities`, `limits`, `tool_identity`, `retained_until` |
| `GET /v1/sessions/{sid}` | None | `session_id`, `state`, `created_at`, `deadline`, `remaining_seconds`, `active_execution_id` (nullable), `last_submission` (nullable receipt), `diagnostics_remaining`, `opinions_remaining` |
| `GET /v1/sessions/{sid}/file?path=...` | URL-encoded relative path | `path`, `content_base64`, `sha256`, `size_bytes` |
| `POST /v1/sessions/{sid}/files` | `path`, `content_base64` | `path`, `sha256`, `size_bytes` |
| `POST /v1/sessions/{sid}/executions` | `command` (shell string), `timeout_seconds` | `execution_id`, `state` |
| `GET /v1/sessions/{sid}/executions/{eid}?offset=0` | Nonnegative byte offset, default 0 | `execution_id`, `state`, `exit_code` (nullable), `log_base64`, `next_offset`, `truncated` |
| `POST /v1/sessions/{sid}/executions/{eid}/cancel` | `{}` | `execution_id`, `state` |
| `POST /v1/sessions/{sid}/submissions` | `path` | Receipt fields below |
| `GET /v1/sessions/{sid}/submissions/{submission_id}` | None | Receipt fields below |
| `POST /v1/sessions/{sid}/diagnostics` | `submission_id` | `diagnostic_id`, `submission_id`, `candidate_sha256`, `state` |
| `GET /v1/sessions/{sid}/diagnostics/{diagnostic_id}` | None | `diagnostic_id`, `state`, `summary` (nullable), `candidate_sha256` |
| `POST /v1/sessions/{sid}/opinions` | `text`, optional `submission_id` | `opinion_id`, `received_at` |
| `POST /v1/sessions/{sid}/close` | `{}` | `session_id`, `state`, `last_submission` |
| `GET /v1/sessions/{sid}/result` | None | Result fields below |

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
in `/workspace`, with no network, credentials, references or private repo mounts.

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
The last two may be null when unknown. Historical `official` and `custom` kind
labels remain readable for protocol compatibility; neither is an evaluation mode
or trust claim. New participants use `agent`. Metadata does not certify model
identity or absence of human assistance. Different Agent configurations remain
separate comparison groups.

Results contain `session_id`, `state`, `task_id`, `task_sha256`, `condition`,
`tool_identity`, `limits`, `verification_level`, `provenance`, `usage`,
`submission` (nullable receipt), `outcome`, `task_success`, `score`, `metrics`,
`failure_reason`, `evidence`. Before terminal state, verdict fields are null and
metrics/evidence empty. Terminal `outcome` is `pass`, `fail`, `no_submission` or
`error`. Infrastructure error has null success and score; no submission has false
success. Score uses the public task score envelope and incomplete-attempt policy.
Metrics retain units and missing values from the evaluation specification. Do
not conflate physical failure, no submission and infrastructure errors.

`verification_level` is `local_development`, `service_recorded` or
`evaluator_verified`; the last requires a frozen evaluator-operated rerun.
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


<a id="ownership"></a>

## Evaluation observation and participant control

The evaluation framework and the participant Agent harness are separate layers.
Codex, Claude Code, DSH or another participant owns its conversation, context,
model calls and tool choices. ICLayout-Bench supplies the task, isolated workspace,
HTTP tools, server-enforced budgets, observation and independent scoring. It does
not choose the participant's next action. `benchmarking.official` and its
structured-action solver loop have been removed.

`GET /v1/sessions/{id}/observations?offset=0` is a read-only, session-token-scoped
view of successful API interactions. It returns `session_id`, `provenance`
(`server_observed`), `available`, ordered `events`, `next_offset` and `has_more`.
The offset is a zero-based event count; each event has `sequence`, `timestamp`,
`kind` and `data`. Pages contain up to 100 events and approximately 256 KiB.
Invalid offsets are rejected. Poll from `next_offset` while `has_more` is true;
a caught-up active session can gain events later. Reading observations never
advances the Agent, closes its session or consumes an action allowance.

Events cover session creation, accepted file writes/reads (path and digest),
execution requests (command and timeout), execution completion, submissions,
cancellation and closing. Idempotent mutation replays do not duplicate events.
They persist across restart. Denied requests, Agent-local activity and internal
model reasoning are outside this stream. Original execution logs remain available
through the execution polling interface. The endpoint exposes API-visible material,
not the evaluator's internal journal, hidden inputs or judge diagnostics. Older
stores without this stream return `available: false`, not fabricated history.

`benchmarking.observe` snapshots these events and the service result, while
optionally copying explicitly supplied local participant traces into a separate
`participant/` directory. Its manifest binds file digests and distinguishes
`server_observed` from `participant_reported`. It can run during or after a session;
an active snapshot is partial. Public participant adapters collect available CLI messages,
tool traces and session records through this exporter without imposing a benchmark
reasoning loop. Trace coverage depends on the CLI; hidden reasoning is not assumed
available. CLI usage counters remain raw participant evidence and never overwrite
service usage or change a result's trust label. Files are local, never uploaded.

Public scoring arithmetic and task/evaluation schemas remain auditable. The shared evaluator
freezes inputs and executes the declared checks against immutable candidates.
Public can evaluate prepared public tasks locally without an operator account. Protocol
simulators return explicit errors and cannot be analyzed as model measurements.

Only independently verified evaluator-controlled conditions can receive
`evaluator_verified`. The generic operator process launcher freezes its command,
files and declared condition, and binds the complete task/repetition schedule,
service observations, receipts and independent reports. Its outputs remain
`service_recorded`: starting a process does not attest its remote model identity. Unknown usage stays null; CLI
usage counters in private transcripts do not become gateway-observed usage.

Public analysis groups identical harness/model/prompt/configuration, tool, budget
and trust conditions separately. It preserves infrastructure errors and missing
values rather than filling them with zeros. Hidden-task admission and conservative
aggregate disclosure remain evaluator-side operations.

## Result archive and platform presentation

`benchmarking.results` owns database import, immutable run/evaluation identities,
artifact copies, comparison grouping, task presentations and schema migrations.
Its `ResultStore` interface is shared by the CLI, participant outbox and operator platform.
SQLAlchemy supports local SQLite and PostgreSQL; Alembic owns schema versions.
Original exports remain evidence, while normalized columns serve paginated queries.
Evaluation revisions are append-only. Content-addressed artifacts are persisted
before their SQL references are committed; an interrupted transaction can leave
unreferenced objects but never a committed reference to an unwritten object.

Private owns the unified Web service, browser frontend, HTTP routes and publication
permissions. Public ships shared result storage, queries and presentation processing
through the optional `results` extra, with no standalone Web server or frontend.
The evaluation HTTP service remains a separate execution interface.

`benchmarking.participants.archive` is a terminal-export outbox. A committed result
can be indexed or retried without altering a session or invoking a provider.
Indexing is opt-in through TOML `results_data`, `--results-data`, or
`ICLAYOUT_BENCH_RESULTS_DATA`; storage selection does not change run identity.
Prepared environments, authentication homes and `.runtime` are not archive inputs.
Task presentations use explicitly supplied Public catalog resources at recorded
Git revisions. They remain analysis assets, never implicit solver inputs. Authored SVGs can
come from a separately selected Git revision only after case identity, source
netlist digest, asset digest and embedded provenance checks. The archive records
both revisions; the platform renders images without embedding an editor.

UserTrial only installs this Public implementation and chooses storage/configuration.
Private remains responsible for formal deployments and disclosure. A public
platform must consume reviewed exports rather than unrestricted hidden-task stores.
See [result archive operation](running.md#result-archive) for formats, comparison
semantics, presentation limitations and backups.

## Verified reruns and disclosure

The public [protocol](#http-session) owns trust labels and result
fields. Admission, raw evidence verification and release construction execute in
Private. A participant harness identity does not raise its trust level.

### Frozen evaluator-operated reruns

Before model calls, an operator freezes the task set and digests, model/harness
configuration, prompt policy, source digests, participant executable identity, EDA image and
backend identities, resource inventories, budgets and repetition schedule. Each
slot starts an independent workspace. The pre-run manifest digest is retained
outside the output bundle as the verification anchor.

The operator checks every scheduled slot, the harness configuration and action
transcript, last durable submission, archived candidate bytes and independent
verdict. Modified evidence or missing repetitions fail verification. The generic participant-process
launcher retains `service_recorded`, including failed launches: it freezes declared
configuration but cannot attest the actual remote model. `evaluator_verified`
requires independently verified controlled conditions. Local runs remain
`local_development`. These are
operator assertions backed by evidence, not signatures authenticating a remote
operator. Publish the identity/trust arrangement separately when deploying a service.

CLI-reported token counters remain separate from service-observed usage. A frozen
model identifier establishes requested conditions, not an assertion about a remote
provider's internal implementation. Unknown cost/usage is never zero-filled.

### Hidden data

The operator HTTP rerun exporter accepts only `public_development`. Hidden designs
use Private's admission-controlled workflow: unpublished sources and authorization,
qualification evidence, resource/endpoint review, an immutable task/repetition
plan and a single-use exposure reservation are required before execution.
Synthetic hidden fixtures test these boundaries; they are not real hidden tasks.
Software cannot prove unpublished origin, licensing rights or provider retention
arrangements. Those remain explicit operator records.

A hidden release is reconstructed from an approved field allowlist and fixed
aggregate groups. It suppresses small task/family/trial groups and exposes neither
per-task identifiers/metrics nor raw logs, paths, candidates or qualifications.
Changing the release policy after a run cannot relax its original restrictions.
Public-task rerun releases and hidden aggregate releases are different artifacts.

### Publication boundary

Analysis is local by default. Generating a reviewed release artifact does not
upload it or make a leaderboard. Keep credentials and growing raw evidence out
of Git. Actual hidden-task qualification, deployment identities and authority to
publish restricted materials must exist before a real hidden release. The
framework's tests and a successful public rerun do not supply that authority.
