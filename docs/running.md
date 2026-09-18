# Participation and Result Analysis

## Local self-testing

Run the [README quick start](../README.md#quick-start) to prepare a public case,
check its reference and start the local HTTP service. Use your participant Agent harness against that endpoint. It uses the same evaluation engine as
operator runs, but always reports `local_development`. You control the local task,
image and resources; a local pass does not certify a formal or hidden-task result.

To reuse an existing compatible image and prepare a fresh case without a reference
run, execute from the Public checkout:

```bash
uv run --locked python -m benchmarking.engine.preview prepare \
  --case cell_6t --image iclayout-bench-tools:dev --output build/prepared-cell6t
export ICLAYOUT_BENCH_TOKEN="$(openssl rand -hex 32)"
uv run --locked python -m benchmarking.service \
  --prepared build/prepared-cell6t --data build/local-service \
  --image iclayout-bench-tools:dev --token-env ICLAYOUT_BENCH_TOKEN
```

Preparation requires the public catalog and pinned upstream sources. An installed
wheel accepts `python -m benchmarking.engine.preview --public-root /path/to/ICLayout-Bench
prepare ...`; that checkout supplies resources, not imported Python modules.
Use new output directories. The local server binds to loopback and accepts one
active session. The service reads `[task].hours` from the prepared `case.toml`; `--seconds` is not
accepted. Use `--port` to select a listener port.
Receipt retention is seven days; remove expired local storage when no longer needed.

To inspect an existing candidate without running an Agent, use its prepared case:

```bash
uv run --locked python -m benchmarking.engine.cli evaluate \
  build/prepared-cell6t/case/case.toml my-candidate.gds --output build/candidate-check
```

Inspect the printed failure summary and `build/candidate-check/report.json`, plus
the per-job evidence in that newly generated directory, to locate physical,
connectivity, geometry or post-layout failures. Evaluation uses the case's frozen
toolchain. It does not convert a reference or manually supplied GDS into model output.

## Experiment runner

Use the same entry point for `dsh`, `claude-code`, `codex` or a custom `command`.
`benchmarking.participants` supplies launch/configuration adapters and a scoped
MCP bridge. These adapters configure and supervise native processes; they do not
choose the next Agent action. Native harnesses retain their own conversation/tool
loop. The scoped HTTP client supplies the layout MCP operations. Explicitly
declared participant tools can extend the harness; generators and EDA commands
run inside the service workspace. No Private or UserTrial implementation is imported.
Install and authenticate the
selected vendor CLI separately; the Public wheel does not install vendor CLIs.

Preview a condition without creating a session or making model calls:

```bash
python -m benchmarking.run --config configs/codex-gpt-6-astra.toml --dry-run
```

Run it against locally prepared public resources:

```bash
python -m benchmarking.run --config configs/codex-gpt-6-astra.toml \
  --prepared build/prepared-cell6t --output results/codex-xhigh-1
```

For an operator service, replace `--prepared ...` with `--endpoint https://...`
and supply its creation credential as `ICLAYOUT_BENCH_TOKEN`. Each run gets a
fresh scoped session and exports the independent result. By default the runner
closes on completion/failure; explicit recovery settings can retain an interrupted
remote session until its original deadline. Set `tasks` explicitly in the TOML. Omitting `--output` uses
`results/<harness>-<CLI-version>-<model>-<effort>/` and prints its path. An explicit output
directory must be new unless `--resume` is supplied. Create the configuration using the example below first.

### Saved layout images

Completed local cases retain the actual scored `final.gds` and a high-resolution
`layout.png`. The image's top cell and dimensions are stored in `result.json`.
Export checks the GDS against the scored submission before removing runtime data.
Subsequent rendering uses saved `final.gds` and the recorded tools image in an isolated Docker container.
KLayout displays all layers at full hierarchy depth on a white background, with
proportional framing, a 4096-pixel long edge and 2x supersampling. Default layer
colors are a visualization convention, not a process-qualified layer legend.

Missing PNGs can be regenerated without models, PDK copies or regrading. Delete an
unwanted image before regenerating it; compact results do not checksum saved images:

```bash
python -m benchmarking.layout_preview results/my-condition
```

An existing case directory is also accepted. The command holds the case lock;
image failures are recorded in `result.json` without changing the score. Remote
services currently expose no candidate-download endpoint, so remote-only results
may have neither `final.gds` nor a PNG. Historical exports retain their original evidence; use the release that created
them for recovery, or the one-time result migration described below.

### Participant tool schemes

To compare `Codex + model` with `Codex + A + model`, keep the prepared case,
model, effort, repetitions and trusted toolchain fixed. Declare two schemes in
one matrix. The following example assumes you have installed A as a stdio MCP
server and placed its reviewed script and dependency lock beside this TOML:

```toml
[defaults]
harness = "codex"
model = "gpt-6-astra"
effort = "medium"
tasks = ["freepdk45.OpenRAM.cell_6t"]
concurrency = 1
repetitions = 1

[[runs]]
name = "baseline"
[runs.scheme]
instructions = "Use the standard layout resources."

[[runs]]
name = "with-a"
[runs.scheme]
instructions = "Use tool A to construct the layout; submit through layout MCP."
[runs.scheme.mcp.a]
command = ["python", "a_server.py"]
files = ["a_server.py", "requirements.lock"]
env_vars = []
```

Run `python -m benchmarking.run --matrix contrast.toml --dry-run` to inspect
resolved conditions, then replace `--dry-run` with `--prepared build/prepared-cell6t`
to execute. These files and A are participant-owned; Public does not install an
unspecified A package. Matrix defaults are shallow: each run's `scheme` is a
complete declaration, not a partial merge. Conditions execute in listed order;
this runner does not randomize trials or control provider-side nondeterminism.

For A implemented as a Python library or CLI, install it in a derived solver
image instead of adding an MCP server. Set `scheme.solver_image` to the immutable
`sha256:...` ID returned by `docker image inspect --format '{{.Id}}' YOUR_IMAGE`.
Install fixed versions during the image build, then use `scheme.instructions`
to explain imports or commands. The same image can contain A for both conditions
if the experiment deliberately measures enabling its use; record that choice.
`--image` selects the default local solver image and is resolved to an immutable
ID before dispatch. Each scheme may override it. The prepared case's trusted
EDA images/resources remain unchanged. A remote service must already provide
the declared solver image; a mismatch closes the session before launching the
participant. The participant cannot replace an operator's evaluator.

MCP `command` is an argv list, `files` lists config-relative scripts and dependency
locks, and `env_vars` names runtime variables; never put credentials in argv or
TOML. Arguments equal to declared filenames resolve relative to the TOML;
other arguments are passed literally. Executable and declared file bytes are
checked before/after launch. Declare the files needed to identify A; dependency
locks record intent but do not attest every installed host dependency. Use a
pinned image when a complete runtime identity is needed. `layout` is reserved.
MCP servers receive the scoped session environment so they can call Public's
client. No creation credential is forwarded. Native host shell tools remain
disabled; Python/CLI tools installed in the solver run through layout MCP.

For an existing control program, select `harness = "command"` and declare:

```toml
[scheme]
version = "my-controller-1"
instructions = "Use the provided task contract."
[scheme.launch]
command = ["python", "controller.py"]
files = ["controller.py", "requirements.lock"]
env_vars = ["MODEL_API_KEY"]
```

The process receives the prompt and task contract on stdin. Environment variables
`ICLAYOUT_BENCH_ENDPOINT`, `ICLAYOUT_BENCH_TOKEN` and `ICLAYOUT_BENCH_SESSION`
provide scoped HTTP access; `ICLAYOUT_BENCH_TASK_FILE` points to session metadata,
`ICLAYOUT_BENCH_MCP_CONFIG` to the private MCP config, and
`ICLAYOUT_BENCH_MODEL` / `ICLAYOUT_BENCH_EFFORT` record requested settings.
The command starts in a fresh private directory. A container/remote launcher
must explicitly forward these inputs and preserve its own version identity.
Public enforces the existing session deadline, captures stdout/stderr, cleans up
its process group and collects the terminal result. Custom commands do not
support native same-session continuation; use `resume_session = false`.

Scheme outputs append their name and content digest to the normal condition
path. Changed declared tools, instructions or images cannot reuse an old case.
Archive comparisons distinguish schemes while matching the service's evaluator
identity, limits and verification level. The website exposes the scheme name and
digest; arbitrary instructions, commands and local paths remain internal metadata.
Unknown usage stays unknown, and adding tools grants no new time or repetitions.

### Native harness configuration

The Codex adapter explicitly sets
`mcp_servers.layout.default_tools_approval_mode = "approve"` for its benchmark
MCP server while retaining `approval_policy = "never"`, a read-only host sandbox
and disabled host execution tools. Disabling interactive approval alone does not
preauthorize MCP calls. The adapter supplies this policy on both initial launches
and native resumes; user configuration is ignored for these invocation settings.
Do not add MCP permission fields to the experiment TOML. See the
[Codex MCP configuration reference](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

Model and effort are mandatory experiment conditions. They override the selected
CLI's settings for this invocation without editing user settings files. Dry-run
and `conditions.json` record the requested/resolved selection. Provider-effective
reasoning remains unknown unless independently observed; equal effort names do
not establish equal computation across providers.

| Harness | Configuration read | Invocation behavior |
| --- | --- | --- |
| `dsh` | Headless composed profile and `$DSH_HOME/settings.yaml` | Reuses the selected provider/credential store; private invocation patch selects model/effort and exposes the layout MCP tools |
| `claude-code` | Claude user provider environment, model, effort and optional key helper | Reuses authentication with an isolated invocation; passes the configured effort explicitly |
| `codex` | Codex user model/effort, including its selected profile | Uses existing authentication and explicitly resolved model/effort with the layout MCP tools |

Personal hooks, skills, host shell tools and subagents are excluded from these
experimental native harness conditions. Custom provider deployments requiring
other CLI-specific settings may need an adapter extension. Current DSH direct
DeepSeek adapter effort values are `off`, `low`, `high`, `max`; other adapters and
CLIs validate their own supported values. An effort accepted by the CLI does not
prove how a gateway maps it. `deepseek-flash` is the official API alias for V4.1
Flash as of September 16, 2026 ([DeepSeek announcement](https://www.deepseek.com/en/news/deepseek-v4-1-flash/)).

### Failures, retry ownership and recovery

Recovery is opt-in in each experiment TOML (or `[defaults.recovery]` in a matrix).
All four fields must be declared together; there are no CLI policy overrides:

```toml
[recovery]
http_attempts = 3
backoff_seconds = 1
max_backoff_seconds = 8
resume_session = true
```

Without this table, HTTP requests have one attempt and native continuation is
disabled. `http_attempts` includes the original request (1–10); delays double from
`backoff_seconds`, capped by `max_backoff_seconds` (both 0–60 seconds). Numeric
`Retry-After` is respected; a value beyond the cap stops retries. Only transport
loss and explicitly retryable HTTP 503 responses are automatically retried.
POST replays use the **same key and body**; 429 `budget_exhausted` is not provider
rate limiting. The bridge journals mutations before sending and preserves the
original execution timeout across retries. A lost reply blocks different mutations;
repeating the unresolved tool with identical arguments reuses its key. An uncertain
MCP reply across a bridge restart blocks further mutations and native continuation.
A status query does not prove that an arbitrary command can safely be repeated.

Local session creation has a separate infrastructure provisioning window, bounded
by `SESSION_STARTUP_TIMEOUT_SECONDS` (600 seconds). This includes durable resource
archival and container startup; large PDK bundles can exceed a short HTTP timeout.
The client waits at least that window plus a 30-second response allowance for
`POST /v1/sessions` only. Other HTTP requests retain their configured timeout.
Resource archival remains fsync-backed. Solve time starts at the engine's existing
container-launch boundary, not at the beginning of archival; provisioning never
resets an established solve deadline.

The service persists the creation key before provisioning. A failed or interrupted
startup retains `http.json` and `startup.json` (elapsed time and sanitized failure
reason). It returns a nonretryable infrastructure error; replaying the same key,
also after restart, never provisions another session. Read the retained service
artifacts before arranging a distinct replacement attempt. A successful creation
still replays its original response after a lost HTTP reply.

The client owns service-transport retries. Native harnesses own their provider/SDK
retry loops; the benchmark never wraps them in automatic model-call or process
retries. Provider-native retry limits are not normalized across vendors. Explicit
manual continuation is bounded by the original server deadline, not a renewed
three-hour allowance. No tool-call count limit is imposed.

`failure` records a category, evidence source, sanitized code, retryability and
whether dispatch must stop. Categories distinguish `network_transient`,
`rate_limit`, `quota_exhausted`, `authentication`, `harness_crash`,
`service_failure`, `evaluation_tool_error`, `harness_configuration`, `budget_exhausted`, `task_failure`
and `unknown`. Only structured recognized harness error codes establish provider
failures; free-form text or a positive exit code alone remains unknown. A process
signal establishes a harness crash, not a model failure. Unrecognized provider
wrappers (including free-form DSH headless errors) remain unknown. Independent
scoring is retained separately from harness failures. Quota/authentication stop
subsequent slots for the same harness/provider/model in that invocation; service
failures stop all subsequent dispatch. Blocked slots remain in their case summaries.
Credentials shared across differently named models cannot be inferred reliably.

A structured Codex `layout` MCP failure reporting that approval is required while
approval policy is `never` is `harness_configuration`, even if the CLI exits zero.
It stops related dispatch and is not retried automatically. The run summary
reports `outcome = "error"` with null score/task success, keeping the independent
service verdict under `evaluation_result` and the unchanged analysis export.
Unrecognized failed MCP transport events remain `unknown`; assistant prose is not
evidence. A later completed call to the same tool clears its earlier transport
failure. These rules do not reclassify ordinary tool-result errors as harness
configuration failures. Existing archived batches are not rewritten by an upgrade.


Recover using the **same TOML and endpoint/input arguments**:

```bash
python -m benchmarking.run --config configs/codex-gpt-6-astra.toml \
  --endpoint https://evaluation.example.org --output results/my-batch --resume
```

The directory in this example must have been generated by your original run.
Case recovery compares resolved conditions, the ICLayout-Bench release
(version and Git commit), endpoint and prepared-file content. Started participants also compare CLI version,
native storage location and frozen launch conditions. Atomic state writes and an
exclusive local case lease prevent concurrent owners; the native child inherits
the lease so an orphaned live process also blocks a second runner. Use local
filesystems with reliable `flock`/atomic rename semantics. Completed slots are
skipped; unfinished exports can be collected again without relaunching the Agent.
Unfinished cases retain logs, launch diagnostics and incomplete exports in `.runtime/`; completed cases use the retention rules below.

These are three different operations:

- **Batch recovery:** skip completed slots, recover started slots, then dispatch
  untouched slots. An existing batch cannot be converted to different conditions.
- **New attempt:** a fresh solve/workspace/budget. The Public participant runner
  does not automatically create replacement attempts. Private's operator policy
  owns its separately frozen infrastructure replacement allowance.
- **Same-session continuation:** with `resume_session = true`, Codex or Claude
  can resume a failed/interrupted launch against the same still-active remote
  service workspace, scoped token and deadline. It requires no active execution,
  no unresolved mutation/reply and persisted native session state. This option
  requires `--endpoint`, with a service that outlives the runner; the runner-owned
  `--prepared` service cannot preserve a live workspace after it exits.

Codex uses `codex exec ... resume <thread-id> -`; Claude uses
`claude -p ... --resume <session-id>`. Both persist native histories in
`participant/.private/native-home/` within the run storage (`.runtime/` for default
cases) and reuse the same private working directory.
File-backed native authentication is refreshed from the caller's CLI home at
launch; API environment variables remain runtime-only. OS-keychain/custom login
flows that cannot use this isolated home need an adapter extension. DSH's current
headless implementation always creates a fresh UUID/session: it preserves logs,
but cannot continue a native session through this adapter. Its configurations
reject `resume_session = true` before dispatch.

Reproduce the CLI capability inspection without model calls:

```bash
codex --version
codex exec resume --help
claude --version
claude --help
dsh --version
dsh --profile headless --help
```

Inspection with Codex 0.154.0, Claude Code 2.1.270 and DSH 0.1.5-rc.1 found those
interfaces. For DSH, inspect the installed `@deepseek-ai/dsh-headless/lib/index.js`:
its runner calls `agents.create` with `session-${randomUUID()}`; its schema accepts
`task`, not a resume ID. Recheck installed versions before extending support.
Offline regression tests simulate native processes; they do not certify a paid
provider's continuation behavior.

The service's `created_at`/`deadline` are authoritative. Normal execution, native
provider retries, HTTP backoff, disconnection and human billing/authentication
repair **all consume the original wall budget**. Evaluation/result collection
occurs after solve closure and grants no further solve time. Service restart
currently loses the live workspace: it terminates running execution records as
errors, retains acknowledged receipts and returns `service_interrupted`. Recovery
collects that failure; it never recreates a workspace or resets a deadline.
Unresolved MCP operations, missing native state and expired/removed service records
cannot be turned into a fresh solve by `--resume`.

`repetitions` remains the frozen number of independent experiments. Continuations
are launches inside the same attempt/session, never best-attempt selection. While
unfinished, preserve the complete case including `.runtime/` for local recovery.
It contains service tokens, native authentication and launch diagnostics. Do not
share that live state. Terminal export combines native launch traces into one
`agent.jsonl`, redacts known runtime credentials and removes the native home.
Unknown secrets in arbitrary model/tool output still require review before sharing.
Historical batches retain their original protected raw traces.

Recovery of old batches lacking the durable manifest is not supported.

### Multiple combinations and repetitions

Create a `configs/` directory in your participant project and save TOML experiment configurations there. Each file selects exactly one
`harness` and `model`; edit `efforts` to compare reasoning settings for that pair:

```toml
harness = "codex"
model = "gpt-6-astra"
efforts = ["high", "xhigh"]
tasks = ["freepdk45.OpenRAM.cell_6t"]
concurrency = 1
repetitions = 1
```

Every file explicitly declares harness, model, tasks, concurrency, effort and repetitions.
A single `effort = "high"` is accepted instead of `efforts`. Missing fields and
`"default"` effort are rejected. Each effort runs independently; use only settings
supported by that harness/model. Credentials remain in existing CLI configuration.

Select one or several files (shell wildcards also work):

```bash
python -m benchmarking.run --config configs/codex-gpt-6-astra.toml --dry-run
python -m benchmarking.run --config configs/codex-gpt-6-astra.toml \
  --prepared build/prepared-cell6t --output results/comparison-1
```

The second command makes real model calls for every selected effort and repetition.
Conditions execute in order. Within each condition, `concurrency` bounds the
number of independent case/repetition sessions running at once. Condition names
use the file stem (or optional `name`) plus the effort; names must be unique.
Harness/model/effort/tasks selection and `repetitions` belong in the experiment
TOML. For example, `repetitions = 3` creates three independent runs per condition.
`tasks` must be a nonempty list of distinct case IDs. `concurrency` must be an
explicit positive integer: 1 runs one conversation at a time, 2 permits two.
Every case receives every repetition; retries do not create extra repetitions.
Different configuration files and efforts do not multiply the concurrency cap.
For multiple local cases, pass all prepared directories after `--prepared`;
the runner maps their `case/case.toml` IDs and rejects missing or duplicate cases
before launching. Each running slot gets its own local service and workspace.
A remote endpoint must support the selected cases and concurrent sessions; the
standalone development service serves one case and one active session only.

Condition directories skip completed results on the next identical invocation.
`--output` selects a directory for exactly one resolved condition and uses the same case format.
The runner verifies the frozen configuration, implementation and prepared inputs.
It prints `SKIP case=... condition=... repetition=... outcome=... result=/...`
for each completed slot, including failed task outcomes; it never selects the best
repetition. Missing archived results cause an error. Other batches are not searched
or reused. Suspended sessions follow the recovery policy described above.
For default condition directories, a completed plan can be extended with new cases
and a new concurrency value. Existing cases are skipped; their configuration and
input identities must match.

The solve budget belongs to each case's task contract:

```toml
# In case.toml, alongside the other [task] fields
[task]
hours = 3
```

The runner rejects `hours`, `seconds` and budget CLI overrides in participant
configuration. `--matrix` also requires explicit participant conditions,
and cannot supply a task budget. Positive fractional task hours are accepted;
missing, zero, negative or non-finite task budgets cannot be served. Public cases
currently declare three hours individually; this migration value is not a claim
that all cases require the same effort. Maintain and calibrate each case's value
before comparing experiments.

Local mode reads the prepared case. Remote mode reads the service's published
task contract and checks `limits.wall_seconds == task.description.hours * 3600`
before model calls; participants do not need the operator's case files. Dry-run
resolves participant selections without contacting a service and therefore does
not resolve the task budget. The service enforces wall-clock time, including
model, network and EDA time. Budget changes change task identity: prepare fresh
inputs and start a new batch rather than modifying a batch's frozen conditions.
The runner follows the remaining service time without a separate CLI cap or
an early cleanup reservation. At expiry, the service judges the last accepted
submission, so submit candidates while the session is active. On earlier CLI
exit, the runner attempts a final snapshot before closing the session.

There is no MCP mutation-count cap. Calls remain observable as efficiency data,
not an additional quality score. MCP `execute` defaults to the remaining service
command allowance; the Agent can request a shorter positive timeout with `seconds`.
The local service allows a command to use the entire remaining session. Remote
services may advertise a smaller `max_command_seconds`, which the adapter honors.
Codex, Claude Code and DSH transport waits are set from the service wall budget
plus a response-draining allowance; this adds no execution time beyond the server
deadline. There are no fixed 120/180-second MCP caps or 300-second local command cap.

### Output layout

Default results contain only case directories beneath the harness/model condition.
A completed local case contains:

```text
results/codex-0.154.0-gpt-6-astra-medium/
  freepdk45.OpenRAM.cell_6t/
    report.md                  # outcome, score formula, thresholds and measurements
    result.json                # conditions, state, measurement identities and result
    final.gds                  # candidate used by the independent evaluator
    layout.png
    agent.jsonl                # native launch traces, in order, known credentials redacted
    evaluation/                # frozen plan, measurements, logs and diagnostic outputs
    .case.lock                 # concurrent-owner exclusion
```

There is one machine-readable run result. `result.json` retains the independent
service verdict separately from harness failures and records unknown usage as
unknown. The ICLayout-Bench package version and Git commit identify the release
that defines the inputs. Wheels and source distributions embed this revision at
build time. Prepared cases, PDK dependencies and tool setup must come from that
release; local overrides are outside this reuse contract and require a separate
experiment. The default runner does not fingerprint prepared files or detect
local edits. Copies of PDKs, models, rule sources, tool scripts, native caches and
credentials are not terminal results.
Preparation remains reusable under `build/`. During execution, temporary service
recording and native session storage live in `.runtime/` beneath the case. This
includes temporary evidence snapshots needed by the existing service; they are
removed after terminal export, not retained as another environment archive.

The evaluator report retains its raw job measurements and scoring plan. Relevant
text logs are embedded in `evaluation/report.json`; diagnostic databases and
waveforms remain ordinary files. Reusable source references and per-file checksum
inventories are omitted. Compact version 3 retains task, candidate and condition
hashes needed to bind measurements; historical version 2 exports lack those
identities. A file-name list supports missing-output checks. The tools
image ID remains a runnable locator for image regeneration; it is not a per-file
checksum inventory. Native traces and embedded diagnostic text remain verbatim
except for credential redaction and may contain tool-generated hashes. This is an explicit retention projection, not the original full
operator evidence bundle. It cannot replace Private's formal provenance archive.
Single-repetition cases with archived failures keep their failure summaries in
`result.json`, and any failed-attempt candidate/traces under `attempts/`.

The runner checks source evidence during export, writes artifacts atomically,
checks their presence and atomically commits `result.json`
before deleting `.runtime/`. Unfinished runs keep recovery material. If export
fails, resume retries from that material without a new model session or budget.
Known credentials are redacted from saved traces; a general human review is still
required before sharing model-generated text. Original native session credentials
are deleted with the terminal runtime. A finished case is an analysis result, not
an active session checkpoint.

For multiple repetitions, each case has `repetition-N/` directories containing
these same files; the case lock remains at the case root. Model/case characters
unsafe in paths are percent-escaped. Each selected case/repetition owns its frozen
identity in `result.json`; there is no condition-wide index, summary or log.
All selected cases are locked and validated before dispatch. Repeating a command
skips finished cases and prints result paths. A subset or new cases may be selected
and concurrency changed; changing an existing case's conditions, repetitions or
benchmark release is rejected before dispatch. Selected unfinished cases require
`--resume`. Results remain readable after upgrades, but a different benchmark
release cannot automatically skip or resume them. Compact results do not provide
post-export tamper detection.

Migrate old completed, single-repetition case directories with:

```bash
python -m benchmarking.participants.results results/my-condition/my-case
```

Migration is explicit because it removes redundant resource snapshots and native
session caches. It retains the final candidate, independent result, necessary
logs and archived failure summaries. It refuses active cases, checks candidate
hashes and preserves runtime data on export failure. Multiple-repetition legacy
migration requires handling each repetition explicitly. The command can be retried
following interruption. It also simplifies previous compact exports. A historical
release absent from the original metadata is recorded as unknown, never inferred
from the currently installed migrator; such results cannot be automatically reused
until their original release is established. Existing unrelated user files are left in place.

An explicit `--output` uses the same case/repetition layout and recovery rules.
Multiple conditions use their default condition directories. Historical batch
outputs are retained evidence, not resumable inputs to the current runner. Keep
the original release for unfinished historical batches. Dry-run launches neither
a harness nor a service.

Keep optional plots and standalone candidate rechecks in their owning experiment
directory. Prepared resources are reusable inputs under `build/`, separate from
`results/`; avoid moving prepared resources that contain bound paths. `build/`
is rebuildable scratch space. `results/` is persistent experiment evidence,
excluded from Git but retained across build cleanup. Back it up separately;
ignore rules provide neither backup nor permission to delete results. Legacy
`build/runs/` batches can be moved together without rewriting archived content.

## Observation and analysis

ICLayout-Bench provides the evaluation environment, service observation and scoring.
The selected Agent harness owns its reasoning and tool loop. Every completed
trial exports `participant/observation/`: service events and result are separate
from CLI/tool traces marked `participant_reported`. DSH JSONL session records are
also collected when available. These exports are local; they do not send raw
participant logs to the operator. They preserve unknown usage and the service's
trust label; model-internal reasoning may be unavailable.

Use `benchmarking.results` for compact terminal exports and comparisons.
`benchmarking.analyze` consumes service observation analysis records produced by
`benchmarking.observe`; raw runtime records stay separate from compact exports.


<a id="service-participation"></a>

## Generic client

Install Public, obtain an operator endpoint and creation credential (or start the
local service above), then create a session.
The service owns EDA; the local harness owns its model configuration. Use TLS
except for loopback development. No hosted endpoint is supplied by this checkout.

```bash
export ICLAYOUT_BENCH_ENDPOINT=http://127.0.0.1:8765
# Supply ICLAYOUT_BENCH_TOKEN securely.
uv run --locked python -m benchmarking.client --key create-1 POST sessions <<'JSON'
{"task_id":"freepdk45.OpenRAM.cell_6t","condition":{"harness_kind":"agent","harness_id":"local-cli","harness_version":"1","model":"YOUR_MODEL","prompt_sha256":null,"configuration_sha256":null}}
JSON
```

Keep the returned token private. Set `ICLAYOUT_BENCH_SESSION` to the returned ID and
replace `ICLAYOUT_BENCH_TOKEN` with the scoped session token. Your local Codex,
Claude Code or other harness can call these same commands:

```bash
uv run --locked python -m benchmarking.client status
uv run --locked python -m benchmarking.client exec --key inspect-1 'ls -R /task; ls /resources'
uv run --locked python -m benchmarking.client write --key source-1 generate.py < generate.py
uv run --locked python -m benchmarking.client exec --key generate-1 --seconds 120 'python /workspace/generate.py'
uv run --locked python -m benchmarking.client submit --key candidate-1 output/final.gds
uv run --locked python -m benchmarking.client close --key finish-1
uv run --locked python -m benchmarking.client result --export results/custom-result
```

Write your own generator before running it and use the output path in the task
contract. `exec` polls bounded logs. Commands share workspace files but run in the
foreground; leftover processes are removed. Replay an uncertain mutation using
its identical body/key. A new operation requires a new key. Accepted submissions
are immutable; the last accepted candidate wins. A receipt is not a passing verdict.
Optional diagnostics/opinions are available only when advertised in capabilities.

## Observation

The participant harness controls its own reasoning and tool loop. ICLayout-Bench
observes the HTTP interactions and evaluates submissions independently. Configure
Codex, Claude Code, DSH or another harness to use the client above; model credentials
stay with that harness. The removed `benchmarking.official` solver is not required.

With the session ID and scoped token already set, snapshot its observations:

```bash
uv run --locked python -m benchmarking.observe --output results/session-observation
# Optionally add --participant-file path/to/cli.jsonl for a local trace snapshot.
```

The export includes `service-events.jsonl`, `service-result.json` and a digest
manifest. Optional traces stay in `participant/` with `participant_reported`
provenance. Nothing is uploaded. It works during or after a session; active
snapshots are partial. Execution log content is available through the client
polling interface. Unknown token use/cost stays null; participant traces cannot
upgrade service results. Use a new output directory for each snapshot.

## Analysis

```bash
uv run --locked --group analysis python -m benchmarking.analyze \
  results/custom-result/result.json \
  --output results/analysis --plots
```

Multiple result files or a disclosed operator `verified-results.json` are accepted.
The command generates `results.json`, `runs.csv`, `tasks.csv`, a digest manifest
and optional SVG/PDF figures. Directories must be new. Conditions, tool identities,
budgets and verification levels form separate cohorts; task digests remain distinct.
Tables show per-task mean and sample standard deviation only over known scores,
alongside measured/unknown counts and distinct outcome counts. A lone sample has
no sample standard deviation. Error or incomplete scores are missing, not zero;
no-submission remains the evaluator's conclusive score. This is not an automatically
published leaderboard or a cross-condition model ranking.

## Formal evaluation

Use the operator's endpoint and scoped credentials with the same client/harness.
The operator controls task selection, tools, budgets and verification; installing
the local evaluator grants no access to hidden tasks or formal credentials.
Private's `iclayout_bench_private` owns frozen reruns, admission and reviewed releases.
The shared `benchmarking.engine` engine and `benchmarking.service` adapter remain in Public.
Scoring definitions are [public](tasks.md#task-scoring), and local/verified results
remain separate analysis cohorts.

<a id="result-archive"></a>

## Result storage and presentation

The operator Web service owns result browsing, comparisons, review and publication.
Public provides the shared result import, query and presentation library and CLI;
it does not ship a standalone viewer or frontend. Participants hand complete
terminal collections to the operator as described in
[website result delivery](#website-result-delivery).

For offline archive processing, install `iclayout-bench[results]`. The importer
accepts compact exports (versions 1–3) and terminal `layout-http.v1` results. It
preserves recorded verification levels; importing a local run does not certify it.
Legacy batches should first be migrated with the terminal-export workflow above.
A protocol-only import has no inferred CLI, effort, timing or local candidate.

```bash
uv sync --locked --extra results --group analysis
uv run --locked --extra results python -m benchmarking.results --data results/archive \
  import /path/to/participant/results --experiment my-experiment
uv run --locked --extra results python -m benchmarking.results --data results/archive \
  catalog --public-root /path/to/ICLayout-Bench
```

These optional commands create `results/archive/`; no results ship with the package.
The operator platform imports terminal collections into its own storage and applies
publication permissions independently of an offline archive.

Current `layout-v2` scores use 100 as a source/area reference and may exceed 100.
Plots and comparisons preserve those values. Historical `layout-v1` results keep
their recorded maximum and frozen interpretation; importing never rescales or
rewrites them. See the [score contract](tasks.md#task-scoring).

The matrix keeps task version, tool identity, budget, verification level and score
method separate. Columns distinguish model, harness, CLI and effort as well as
recorded prompt/configuration identities. Cells show all repetitions, measured
counts, failures and missing scores. An error remains unknown, not zero. Overall
means use equally weighted, fully measured common task contexts; coverage and the
common-task count remain visible. Unknown scoring methods form separate contexts.
Planned but unexecuted tasks from runner schedules appear as `Not run`; historical
imports cannot reconstruct an absent experiment schedule. Missing provenance is
not inferred from directory names.

### Task presentations and interactive layouts

`catalog` reads **the full Git commit recorded in each result**, using the supplied
Public checkout as a resource. That checkout must retain the corresponding Git
objects. It verifies the netlist's declared digest and, when present, the recorded
task digest. Missing revisions or mismatched task definitions are reported as
unavailable rather than matched to today's circuit. Legacy compact version 2 lacks
some measurement hashes; its drawing is explicitly bound to the recorded release,
not newly attested as the historical solver input.

The importer generates a net-label schematic from the target SPICE/CDL subcircuit:
equal labels are connected, MOS body pins are explicit, and subcircuit instances
retain ordered pins. It is not an artist-authored schematic or a topology
qualification result. Unsupported device syntax produces an explicit unavailable
result. Netlists, source metadata and available collection license/notice files
are retained with the drawing, outside solver inputs. Catalog import never edits
case definitions or changes task identity.

Cases may declare a maintainer `schematic` asset in SVG format. The importer
prefers that drawing when its declared SHA-256 and embedded
`iclayout-schematic-v1` metadata match the case ID and authoritative netlist
SHA-256. Otherwise cases without a drawing retain the generated view. Invalid
or mismatched drawings are reported as unavailable, never silently accepted.
These diagrams are analysis assets and are not added to solver inputs.

To use reviewed drawings added after a recorded experiment, select their full
Git commit explicitly (replace the placeholder with the desired commit):

```bash
uv run --locked --extra results python -m benchmarking.results \
  --data results/archive catalog --public-root . \
  --schematic-revision <full-drawing-commit>
```

The recorded task and netlist are still read and validated at the experiment's
original revision. A later drawing is accepted only for the identical case ID
and netlist bytes; its separate commit, path and digest are retained in
`source.json`. This changes presentation only, not scores, task versions or
verification levels. Editing uses a standalone Analog Canvas installation; the platform consumes
exported drawings without an editor connection.

Generate optional interactive geometry once, in an environment with the pinned
KLayout dependency:

```bash
uv run --locked --extra results --group eda python -m benchmarking.results \
  --data results/archive geometry
```

The generated data includes layers, physical coordinates, hierarchy-flattened
polygons and labels for platform presentation. Extraction has a 200,000-shape limit; larger candidates retain
their PNG and downloadable GDS. This bounds browser work rather than silently
truncating geometry. KLayout DRC reports can supply top-cell marker overlays.
Hierarchical markers without transforms remain in the report and are counted as
not overlaid. Cross-highlighting schematic nets against layout connectivity and
large-design multiresolution tiles are not implemented.

### Automatic indexing and recovery

Set `results_data = "results/archive"` in an experiment TOML, add
`--results-data results/archive` to `benchmarking.run`, or set
`ICLAYOUT_BENCH_RESULTS_DATA` to the archive directory. The command-line/environment
setting overrides the TOML setting. Relative paths resolve from the invocation
directory; this storage setting is excluded from frozen experiment conditions. This requires the optional
`results` dependencies. Once a terminal export is committed, the runner enqueues its
path and experiment schedule, imports it, then removes the outbox entry. Existing
completed cases are also indexed on skip. An indexing failure does not alter the
verdict or repeat a model call. If the archive disk is unavailable, the terminal
export itself remains the retry source.

```bash
uv run --locked --extra results python -m benchmarking.results --data results/archive retry
uv run --locked --extra results python -m benchmarking.results --data results/archive verify
```

`retry` consumes durable pending entries without starting models. Keep source
exports until pending entries have been delivered. `verify` checks every registered
artifact's bytes against its stored digest. A repeated identical import is a no-op;
a changed run identity or immutable attachment fails. Explicit `import
--reevaluation` retains a new evaluation revision; the newest revision is selected
by default and previous revisions remain accessible. It cannot replace a run's
candidate or task identity. Derived presentation artifacts may be regenerated
without changing any score.

New compact version 3 retains task, candidate and condition hashes. Import-time
hashes for older exports identify copied files only and do not restore missing
historical attestations. Unknown usage stays null; CLI-reported usage never becomes
service-observed usage.

Automatic indexing targets the participant-selected archive, not an operator
website. Neither `results_data` nor archive `retry` uploads files to the website,
and an evaluation `--endpoint` is not a website import endpoint. See
[result handoff and storage ownership](architecture.md#result-handoff-and-storage-ownership)
for the separate transfer, ingestion and publication boundaries.

### Storage, deployment and backup

SQLite metadata resides in `results.sqlite3`; `objects/<prefix>/<sha256>` contains
copied attachments. Source directories may be moved after successful import. Keep
the database and objects together outside disposable `build/` storage. SQLite uses
WAL and short transactions on a local disk; do not put its WAL database on a shared
network filesystem. Stop archive readers and indexing writers before copying the
entire archive (including pending entries and SQLite sidecars). Restore into a new
directory and run `verify` before using it.

For PostgreSQL, install `iclayout-bench[results,postgres]`, provision an empty database,
and set `ICLAYOUT_BENCH_DATABASE_URL` to a SQLAlchemy `postgresql+psycopg` URL. Use the
same `--data` attachment root for all processes. Alembic applies schema revisions
when the archive opens. SQLite and PostgreSQL use the same result model; moving
existing SQL contents between backends is not an automatic database conversion.
Reimport original exports into the target database, then regenerate presentations,
or perform an operator-managed SQL migration. Back up PostgreSQL and its associated
object directory as one quiescent snapshot. Generic public code supplies no formal
operator deployment or result-publication policy.


## Website result delivery

The installed Public package includes a standard-library-only delivery CLI,
independent of Private and the optional SQL archive dependencies. Run your complete
experiment first, then create a portable package:

```bash
python -m benchmarking.transfer pack results/my-experiment my-experiment.zip
```

Participant accounts and uploads are deferred on the current official platform;
use administrator handoff of complete terminal collections. The following client
workflow applies only to deployments that explicitly enable participant access.

Sign in at the operator website's `/account` page using a configured Google/GitHub
provider or a verified email account. Upload the ZIP in that workspace, or create
an upload token there and supply it securely in `ICLAYOUT_UPLOAD_TOKEN`. Do not put
tokens in command arguments, scripts committed to Git, experiment TOMLs or result
packages. The CLI accepts another environment variable via `--token-env`.

```bash
python -m benchmarking.transfer upload my-experiment.zip \
  --website https://benchmark.example --name 'My experiment'
python -m benchmarking.transfer status JOB_ID --website https://benchmark.example
```

Use the actual configured website origin. Remote delivery requires HTTPS; HTTP is
allowed only for loopback development. The client refuses redirects so bearer
credentials cannot be forwarded to another origin. Authentication errors require
sign-in/token replacement; a successfully received upload returns a durable job ID,
not a publication promise. Reuploading identical package bytes with the same name
under the same account returns the same job. Status distinguishes queued/running,
completed, completed-with-errors and failed; the account workspace can retry failed
imports. Correct a malformed package at its source and package it again. The CLI
never reruns an Agent or evaluator and never deletes original results.

### Package and HTTP contract

`iclayout-results.v1` is a ZIP containing `manifest.json` and terminal collections
at `runs/NNNNNN/`. The manifest records `format`, `runs` and a `files` map of member
paths to `{sha256, size}`. Original `result.json` bytes, declared files and available
standard evaluator artifacts are preserved; recovery directories, participant
working trees and local archive databases are excluded. Missing declared artifacts
fail packaging. Packaging does not redact arbitrary trace contents: inspect source
materials before sending them to an operator. Traces are internal evidence and
are not public merely because they were uploaded.

Receivers check the complete manifest, member digests, run count and referenced
files. Duplicate paths, traversal, symlinks, encrypted members and hidden/runtime
paths are rejected. The default cap is 512 MiB for the uploaded ZIP and extracted
contents, and 20,000 data files; split larger experiment collections into packages
without dropping failed outcomes or planned repetitions. The manifest is limited
to 8 MiB. These are transfer limits, not evaluation budgets.

- `POST /api/uploads?name=...`: `application/zip` body; authenticated session or
  `Authorization: Bearer ...`, plus `X-Platform-Request: 1`; returns HTTP 202 with
  `id` and `status_url`.
- `GET /api/uploads/{id}`: same account authorization; returns processing state,
  progress, diagnostics and imported result publication state.
- `POST /api/uploads/{id}/retry`: account authorization and request header; retries
  failed/partially failed ingestion idempotently.

Website ownership and origin come from the authenticated server context, never
from fields in the package. Different participants' session IDs and repetition
cohorts remain isolated even if their declared model conditions match. Public's
recorded scores, methods and verification metadata remain intact. Operator review
still controls score and file publication independently.
