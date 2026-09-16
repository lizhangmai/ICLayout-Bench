# Architecture and Extension Interfaces

ICLayout-Bench measures an Agent's ability to turn authoritative netlists, constraints, and process resources into GDS. The system under test includes the harness, model, prompt, context strategy, and tools; each measurement covers one task, one configuration, and one independent repetition. The benchmark owns a small session protocol and treats harness internals as opaque. Declared mode labels record measurement conditions; they do not select or install a runtime. See the root [README](../README.md) for the current public scope.

<a id="repositories"></a>

## Repository responsibilities

Public provides both local self-testing and participation in an operator service.
It owns `benchmarking` (harness, client, protocol, task/score definitions and public
analysis), `layout_eval` (preparation, isolated execution, immutable submissions,
EDA backends and independent evaluation), and `layout_service` (the local HTTP
adapter). These packages ship together in the Public wheel. Local evaluation
requires Docker and compatible tool/resources; remote participation does not.

Private owns `layout_operator`: controlled reruns, hidden-task admission, internal
batch verification and reviewed releases. It imports the Public implementation;
it does not carry another evaluator or HTTP server. Hidden tasks, deployment
credentials and restricted evidence remain operator-owned. Source dependency is
**Private → Public**. Public installs and tests without Private.

UserTrial installs the Public wheel and verifies both local self-testing and
remote participation. It contains neither a source clone nor a copied evaluator.
The public catalog checkout is an explicit data/build input for local preparation;
a prepared case can be served using only the installed wheel and Docker. The
`--public-root` preview option locates that catalog independently of Python imports.

Both paths use `layout-http.v1`, the same task checks and scoring arithmetic.
Local results are always `local_development`; choosing an official harness does
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
Messages exclude host paths, exception traces, hidden materials and secrets.
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
and retains acknowledged snapshots and receipts; interrupted work is not success.

The creation response's `limits` contains `wall_seconds`, `cpus`, `memory_mb`,
`pids`, `workspace_mb`, `max_file_bytes`, `max_response_bytes`,
`max_candidate_bytes`, `max_command_seconds`, `max_log_bytes`,
`diagnostic_requests`, `opinion_requests`. The server enforces them. A command is
capped by remaining session time. Logs are bounded with explicit truncation.
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

`condition` is participant-reported metadata: `harness_kind` (`official` or
`custom`), `harness_id`, `harness_version`, `model`, `prompt_sha256`,
`configuration_sha256`. The last two may be null when unknown. Metadata does not
certify model identity or absence of human assistance. Official and custom harness
conditions remain separate comparison groups.

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

## Official harness and trust

`benchmarking.official` owns an observe/action loop, bounded recent history,
explicit retries, execution polling and early submission. Its provider returns a
single structured action. The included Codex provider uses installed authentication
and an explicitly frozen model/effort, with host tool actions rejected. Provider
output is never executed directly on the host. Both this loop and custom local
harnesses call `benchmarking.client`. A model change changes the measured condition.

Public scoring arithmetic and task/evaluation schemas remain auditable. The shared evaluator
freezes inputs and executes the declared checks against immutable candidates.
Public can evaluate prepared public tasks locally without an operator account. Protocol
simulators return explicit errors and cannot be analyzed as model measurements.

Only an evaluator-operated frozen rerun may receive `evaluator_verified`. Merely
requesting `harness_kind=official` never raises trust. Operator evidence binds the
pre-run manifest, complete task/repetition schedule, source and tool identities,
provider actions, receipts and independent reports. Unknown usage stays null; CLI
usage counters in private transcripts do not become gateway-observed usage.

Public analysis groups identical harness/model/prompt/configuration, tool, budget
and trust conditions separately. It preserves infrastructure errors and missing
values rather than filling them with zeros. Hidden-task admission and conservative
aggregate disclosure remain evaluator-side operations.
