# Running Experiments and Reading Results

This guide follows an experiment from installation and configuration through
execution, recovery and analysis. Use the [task contract](tasks.md) to interpret
requirements/scores and [Tools](tools.md) to prepare local EDA resources. The
[architecture and HTTP contract](architecture.md) defines isolation and service
integration.

- [Start an experiment](#start-an-experiment): installation, configuration and run commands.
- [Harness configuration](#harness-configuration): native connections, credentials and participant tools.
- [Failure recovery](#failure-recovery): inspect, stop, continue, collect or replace unfinished work.
- [Results and analysis](#results-and-analysis): output files, token/cost statistics, archives and delivery.

## Start an experiment

### Experiment environment

Use Python 3.12+ and choose an installation method.

From PyPI:

```bash
python -m pip install iclayout-bench
```

From a downloaded wheel, replacing the path with your file:

```bash
python -m pip install /path/to/iclayout_bench-VERSION-py3-none-any.whl
```

From source:

```bash
git clone https://github.com/lizhangmai/ICLayout-Bench.git
cd ICLayout-Bench
python -m pip install .
```

The examples use `python` from the environment where Bench is installed. Choose
configuration and output paths to suit your workflow. Install and authenticate
the chosen native Agent CLI separately; see [harness configuration](#harness-configuration).

### First experiment

Local evaluation requires Linux x86-64, Docker, a compatible
[EDA image](tools.md#prebuilt-images-and-local-builds) and an explicit Dataset path
or repository ID. The package bundles no tasks. A published task Dataset excludes
author reference layouts and qualification evidence.

Save the following as `experiment.toml`. Replace the model ID and effort with
values supported by your authenticated native CLI. The public Dataset is
`MAI716/ICLayout-Bench`; replace `source` to use another Dataset ID or directory:

```toml
harness = "codex"
model = "your-model-id"
effort = "medium"
concurrency = 1
repetitions = 1

[dataset]
source = "MAI716/ICLayout-Bench"
name = "core"
split = "test"
```

Inspect the configuration and selected task:

```bash
python -m benchmarking.run \
  --config experiment.toml --case NAND2_X1 --dry-run
```

Dry-run resolves configuration, local connections and Dataset bindings without
model calls or Docker execution. It does not test credentials, quota, electrical
qualification or remote-service availability.

Pull the published tools image, then run the same condition:

```bash
docker pull docker.io/lizhangmai/iclayout-bench-tools:latest
python -m benchmarking.run --config experiment.toml --case NAND2_X1 \
  --image docker.io/lizhangmai/iclayout-bench-tools:latest
```

The runner creates the local service, isolated workspace and harness process,
then independently evaluates the submitted candidate and exports the result.
PDK installation and derived resource binding are automatic. This command makes
real model calls. Omit `--case` to execute the complete configured selection.
Use `--image IMAGE` or `ICLAYOUT_BENCH_IMAGE` to select another compatible image.
Results default to `results/experiment/<task-id>/<timestamp>/`; add
`--output /path/to/results` to select an output root. See
[output selection](#output-selection-and-scheduling) for reuse and scheduling.

### Remote participation

For a remote service, use a configuration with explicit task IDs and no local
Dataset table:

```toml
harness = "codex"
model = "your-model-id"
effort = "medium"
tasks = ["freepdk45.nangate45-pdk.NAND2_X1"]
concurrency = 1
repetitions = 1
```

Save it as `remote-medium.toml`. Supply the operator's creation credential
through `ICLAYOUT_BENCH_TOKEN`, then run:

```bash
python -m benchmarking.run \
  --config remote-medium.toml --endpoint https://evaluation.example.org
```

Use the endpoint and credentials issued by the operator. Local Docker and PDK
resources are unnecessary. The service must support the selected tasks and
concurrency; the bundled development server supports one case and one active
session. Local and remote execution use the [same protocol](architecture.md#http-session).

### Configuration reference

Each TOML selects one harness and model. `effort` selects one condition; `efforts`
expands distinct values into separate conditions. Both fields together, an empty
selection and `"default"` effort are rejected. Support is validated by the
selected harness/model; equal effort names do not imply equal computation.

| Field | Meaning |
| --- | --- |
| `harness`, `model` | Required supported harness and explicit model ID. |
| `effort` or `efforts` | Required reasoning selection. |
| `harness_home` | Optional native connection/authentication profile; see [Harnesses](#native-harness-configuration). |
| `tasks` | Distinct task IDs; required without `[dataset]`, otherwise an optional subset. |
| `concurrency` | Required positive integer limiting simultaneous case/repetition sessions. |
| `repetitions` | Required positive integer of independent solves for every selected task. |
| `name` | Optional configuration name; defaults to the filename stem. |
| `[dataset]` | Explicit Dataset source and row selection. |
| `pricing_file` or `[pricing]` | Optional explicit [model price snapshot](#pricing); use one source. |
| `[recovery]` | Optional overrides of [recovery defaults](#recovery-settings). |
| `[scheme]` | Optional declared [participant tools or custom controller](#participant-tool-schemes). |
| `results_data` | Optional [local archive](#automatic-indexing-and-recovery) directory. |

#### Static Dataset inputs

`[dataset]` requires exactly one of `source` and `source_env`. The former is a
local directory or Dataset repository ID; the latter names a process environment
variable containing that source. Additional fields are:

| Field | Default | Behavior |
| --- | --- | --- |
| `name` | `"core"` | `core` filters `in_core = true`; `all` selects the complete corpus. These are runner selections, not repository configuration names. |
| `split` | `"test"` | Split bound to the Dataset's canonical table. |
| `revision` | Source default | Pins a repository revision; the resolved commit is recorded. |
| `local_files_only` | `false` | Uses cached repository data without downloading. |

The native `data.parquet` table indexes case and PDK paths/digests. Core tasks use
ascending `core_order` where declared; otherwise table order is retained. An
explicit `tasks` list filters the selection and sets dispatch order. Every ID
must belong to the selected rows. Dataset loading snapshots declared inputs in
memory and never creates a prepared case or edits the source contract.

`--dataset`, `--revision` and `--offline` override configured source settings
before row selection. `--dataset` retains the configured `name`, `split` and task
subset. HF owns downloaded snapshots and authentication; Bench separately owns
PDK and derived [resource caches](tools.md#resource-caches).

#### Paths and environment variables

CLI paths resolve from the command's working directory. Dataset sources,
`harness_home`, `pricing_file` and declared scheme files in TOML resolve from that
configuration's directory. `--output` and `results_data` resolve from the command's
working directory. Commands do not search parent directories for `.env` files.

Explicit CLI arguments override environment-backed defaults; process variables
override an explicitly selected dotenv file; application defaults apply last.
Commands use the variables exported in your shell. If you use uv, you can load an
environment file explicitly:

```bash
uv run --env-file /protected/iclayout.env python -m benchmarking.run \
  --config experiment.toml --dry-run
```

`UV_ENV_FILE` selects the file for subsequent `uv run` commands. `--env-file`
overrides that selection and `--no-env-file` disables loading. Direct Python
commands use already exported variables. `ICLAYOUT_BENCH_IMAGE` and
`ICLAYOUT_BENCH_OUTPUT` supply defaults for `--image` and `--output`; a nonempty
output requires one condition. Native provider credentials stay on the harness
host; containers receive only declared resource settings and approved EDA license
access. The runtime filters unrelated inherited session/provider overrides.

### Multiple conditions and repetitions

To compare efforts, replace `effort = "medium"` in the first configuration with
`efforts = ["high", "xhigh"]`, using levels supported by that model. Run it without
`--output`:

```bash
python -m benchmarking.run \
  --config experiment.toml --dry-run
python -m benchmarking.run \
  --config experiment.toml
```

Several `--config` files or shell wildcards are supported. Conditions execute in
order. Within one condition, each completed task/repetition frees a concurrency
slot for the next queued item. Conditions do not multiply that cap. The runner
neither randomizes trials nor controls provider-side nondeterminism.

A matrix uses `[defaults]` and named `[[runs]]` entries. For example, save
`comparison.toml`:

```toml
[defaults]
harness = "codex"
model = "your-model-id"
effort = "medium"
tasks = ["freepdk45.nangate45-pdk.NAND2_X1"]
concurrency = 1
repetitions = 3

[[runs]]
name = "baseline"

[[runs]]
name = "higher-effort"
effort = "high"
```

```bash
python -m benchmarking.run \
  --matrix comparison.toml --dataset /path/to/dataset --dry-run
```

Matrix defaults merge shallowly. Each run's nested scheme/recovery declaration
replaces that whole default table. See [tool comparisons](#participant-tool-schemes)
for adding a library, MCP server or solver image.

### Output selection and scheduling

Omitting `--output` creates fresh timestamped runs. For one configured effort,
results use `results/<config-stem>/<task-id>/<timestamp>/`; multiple efforts add
an effort directory, and matrices add the run name. [Results](#output-layout)
defines the complete layout.

`--output` explicitly selects one condition root and requires exactly one resolved
condition. It reuses each selected task's latest run: finished cases are skipped,
selected unfinished cases require `--resume`, and new cases receive fresh runs.
Changed conditions for existing tasks require a fresh output root. Reusing a root
can extend task selection and change concurrency while preserving existing task
conditions and repetition counts.

`--case` accepts full IDs or unique final components within the configured
selection. Repeat it for multiple cases. Unknown or ambiguous names fail before
sessions start. `--repetitions` and `--concurrency` override positive integer
settings for this invocation. Check overrides with `--dry-run` first.

For a long single-condition batch:

```bash
python -m benchmarking.run \
  --config experiment.toml \
  --output results/my-batch --detach
python -m benchmarking.run --status --output results/my-batch
```

Use a configuration containing one effort for this command. `--detach` returns a
PID/start identity and log location; workers continue independently of the launch
terminal. Inspect `.scheduler/runner.log`, `owner.json` and `events.jsonl` for
progress. [Recovery](#failure-recovery) explains shutdown, resumed scheduling and
collection without model calls.

### Solve budget and process checks

The case's positive `[task].hours` is authoritative. Participant configuration and
service CLI cannot override it. Each repetition receives its own budget; a
continuation keeps the original deadline. Model calls, provider retries, HTTP
waits, EDA work and downtime all consume that budget.

The bundled HTTP service uses a soft budget. At expiry, an operation already
started may finish; new commands, checks and file writes are rejected. Submit the
best candidate and close without another optimization round. Late submission and
overrun are recorded. Independent final judging follows solve closure. A remote
service can advertise a hard policy; the client obeys its published limits. The
[protocol lifecycle](architecture.md#lifecycle-and-budgets) defines both policies.

Use `check` when `process-feedback` is advertised. It evaluates the current GDS
with the final plan and returns physical/electrical diagnostics without a score.
It consumes solve time and creates no submission. `execute` and `check` may return
`running`; poll their execution IDs until terminal and drained, or cancel them.
Only one workspace operation can run at a time. Submit the declared output
explicitly after checking. [Protocol](architecture.md#process-feedback) defines
pagination, candidate snapshots and result semantics.

### Standalone evaluation

Inspect a supplied case or evaluate your own candidate without a model:

```bash
python -m benchmarking.evaluation task \
  /path/to/dataset/tasks/freepdk45/nangate45-pdk/cases/NAND2_X1/case.toml
python -m benchmarking.evaluation evaluate \
  /path/to/dataset/tasks/freepdk45/nangate45-pdk/cases/NAND2_X1/case.toml \
  /path/to/candidate.gds --output results/candidate-check
```

Use a new evaluation output directory. The case's embedded toolchain is used
unless `--toolchain` is supplied; a case without embedded bindings requires that
option. `characterize` measures an explicit source circuit using an explicit
toolchain. Declared case resource profiles are prepared in the shared cache;
no prepared directories from the Dataset author are required. Select another
tool image with `--image` or `ICLAYOUT_BENCH_IMAGE`.
Author reference checks require an author verification snapshot with
the witness present; use [qualification](tasks.md#qualification). Ordinary
delivered Datasets are sufficient for participant runs and candidate evaluation.

## Harness configuration

### Native harness configuration

Set `harness_home` in an experiment TOML or matrix row to select a native
configuration and authentication directory explicitly:

```toml
harness = "codex"
harness_home = "subscription"
model = "your-model-id"
efforts = ["medium"]
tasks = ["your-case-id"]
concurrency = 1
repetitions = 1
```

Relative homes resolve from the experiment TOML or matrix directory, regardless
of the launch working directory. Each condition can select a different home in
the same invocation. The directory and the native configuration file must exist;
an explicit selection never falls back to the caller's default home. Authenticate
the chosen directory with the vendor CLI before running. Omitting `harness_home`
retains the caller's existing native home/environment behavior. This field applies
to native harnesses; a custom `command` owns its declared launch configuration.

| Harness | Home variable used for the selected directory | Required native configuration |
| --- | --- | --- |
| `codex` | `CODEX_HOME` | `config.toml` |
| `claude-code` | `CLAUDE_CONFIG_DIR` | `settings.json` |
| `dsh` | `DSH_HOME` | `settings.yaml` |
| `kimi-code` | `KIMI_CODE_HOME` | `config.toml` |
| `zcode` | `ZCODE_DATA_BASE_DIR` and an isolated child process home | `config.json` |

The shared launcher selects the directory and stages file-backed credentials;
each adapter resolves its vendor's connection format and prepares an isolated
invocation. The model, effort and reviewed tool configuration remain experiment
conditions. Do not archive the native home with the experiment TOML: it contains
credentials and may contain login diagnostics or other native state. Paths and
declared environment variable names can enter local conditions; credential values
remain private and are redacted from exported traces. A dry run verifies local
configuration, not token validity, provider access or available quota.

Model and effort are mandatory experiment conditions. They override the selected
CLI's settings for this invocation without editing user settings files. Dry-run
and `conditions.json` record the requested/resolved selection. Provider-effective
reasoning remains unknown unless independently observed; equal effort names do
not establish equal computation across providers.

Custom provider deployments requiring
other CLI-specific settings may need an adapter extension. The selected adapter
validates model and effort capabilities before dispatch.

#### Codex

An explicit Codex home accepts connection settings only: `model_provider`,
`model_providers`, `cli_auth_credentials_store`, `forced_login_method`,
`forced_chatgpt_workspace_id` and `chatgpt_base_url`. File credential storage is
required. Use `forced_login_method = "chatgpt"` or `"api"` with the corresponding
native `auth.json`; sign in with the chosen `CODEX_HOME`. A custom provider can
instead use its declared `env_key` or `env_http_headers` references from the
existing process/dotenv entry point. Supported provider fields are `name`,
`base_url`, `env_key`, `env_http_headers`, `wire_api`, `requires_openai_auth`,
`request_max_retries`, `stream_max_retries`, `stream_idle_timeout_ms` and
`supports_websockets`. Inline bearer tokens, static headers and command-backed
authentication helpers are not accepted in this connection configuration.
Endpoints must be HTTP(S) URLs without embedded credentials, query parameters or
fragments. Unrelated inherited OpenAI/Codex authentication and endpoint overrides
are removed; explicitly declared environment references remain available.
The adapter passes approved connection settings as CLI overrides while retaining
`--ignore-user-config` and `--ignore-rules`. Model, effort, hooks, skills, plugins
and MCP configuration do not belong in this native connection file.

Bench configures noninteractive approval for the declared MCP tools, a read-only
host sandbox and disabled native host execution tools. These settings also apply
to continuation; MCP permission fields are not experiment TOML options.

#### Claude Code and DSH

An explicit Claude home uses its `settings.json` provider environment or key
helper, or its native `.credentials.json`. Inherited Anthropic/Claude provider
settings do not select a different authentication method. DSH composes its native
headless configuration with the selected `DSH_HOME`; its credential store and
native `.env` fallback come from that directory.
See [Kimi Code](#kimi-code) and [ZCode](#zcode) for their model and provider declarations.

#### Kimi Code

Authenticate with `kimi login` and configure the desired model alias before
running `harness = "kimi-code"`. Set `model` to an alias in your Kimi configuration
and specify an effort listed in the model's effective `support_efforts`.
Unsupported efforts are rejected before dispatch. This harness uses Kimi Code's
`kimi -p` interface.

Bench reuses the selected Kimi login and its native OAuth refreshes across cases.
Provider `api_key_env` is also supported. Each attempt has its own conversation
and exposes only the evaluation MCP and explicitly declared scheme servers;
personal hooks, plugins, skills and unrelated MCP servers are excluded.
Deleting a completed attempt's private runtime does not remove the managed login.

Same-session continuation is enabled by default for remote services and
checkpointed local sessions; see [Recovery](#failure-recovery). Kimi session state,
wire records and diagnostic logs are retained under `native/kimi/` and in the
observation export's `native-traces.zip`. Configuration and credential stores are
excluded, and known initial/refreshed credentials are redacted.

#### ZCode

Select `harness = "zcode"`, an explicit `harness_home`, a `provider/model`
reference and an effort declared by that model. The selected directory contains
`config.json` with API connections only. For example:

```json
{
  "provider": {
    "team": {
      "kind": "anthropic",
      "options": {
        "baseURL": "https://provider.example/api",
        "apiKeyEnv": "TEAM_MODEL_KEY"
      },
      "models": {
        "your-model-id": {
          "reasoning": {"levels": ["high"], "defaultLevel": "high"}
        }
      }
    }
  }
}
```

Use `model = "team/your-model-id"` in the experiment TOML. Supported provider
kinds are `anthropic`, `openai-compatible` and `openai`, corresponding to
Messages, Chat Completions and Responses. Supply the API root rather than the
final operation URL. `apiKeyEnv` is an adapter-resolved environment reference;
its value comes from the existing process/dotenv entry point. Native inline
`options.apiKey` is also supported in a protected profile. Choose one credential
source. No account login or default-home credential import is performed.

An optional `network` object in the selected profile accepts native `httpProxy`
and `noProxy` strings. Use an HTTP(S) proxy URL without credentials, for example
`"network": {"httpProxy": "http://127.0.0.1:7890", "noProxy": "localhost,127.0.0.1"}`.
These connection settings are recorded with the condition and copied into each
isolated native configuration. ZCode model requests do not automatically use the
shell's generic `HTTP_PROXY`/`HTTPS_PROXY`; inherited `ZCODE_*` overrides remain
filtered, so configure the proxy in the selected profile.

Declared reasoning levels must also be supported by the installed ZCode runtime
and selected model. Bench uses the selected profile for isolated invocations and
leaves its connection files unchanged. Unrelated inherited ZCode/provider
authentication and endpoint overrides do not replace that profile.

Only declared MCP servers are available; personal plugins, skills, hooks, memory,
subagents and native host tools are disabled. Calls are noninteractive.
Native model-I/O and JSONL diagnostics are retained under `native/zcode/` with
credential redaction. Same-session continuation follows [Recovery](#failure-recovery).

### Credential lifecycle

Native invocation state lives inside the run's `.runtime/`. Codex, Claude and DSH
reuse authentication during continuation. With explicit `harness_home`, refreshed
credentials can be written back when the selected source credentials have not
changed. Kimi uses its shared managed login; ZCode uses the selected API profile.
API environment values remain runtime-only.

Stop experiments using a profile before logging in again or switching accounts.
Model/provider selection, credential storage paths and recorded conditions must
remain compatible with [continuation](#failure-recovery).

Terminal export redacts known initial and refreshed credentials, retains selected
native diagnostics and removes the private runtime home. Configuration and
credential stores are excluded from exported native traces. Arbitrary generated
text still requires review before transfer.

### Participant tool schemes

Include `scheme.instructions` only when a participant tool or experimental
procedure needs additional usage guidance. Task requirements, acceptance rules and the solver workflow belong in
`problem.md`. Omit the field when no extra guidance is needed, and omit `[scheme]`
entirely when there are no participant customizations. Tool/image/launch fields
can be declared without instructions.

To compare `Codex + model` with `Codex + A + model`, keep the Dataset case,
model, effort, repetitions and trusted toolchain fixed. Declare two schemes in
one matrix. Save the following as `contrast.toml`, after installing A as a stdio
MCP server and placing its script and dependency lock beside this TOML:

```toml
[defaults]
harness = "codex"
model = "your-model-id"
effort = "medium"
tasks = ["freepdk45.OpenRAM.cell_6t"]
concurrency = 1
repetitions = 1

[[runs]]
name = "baseline"

[[runs]]
name = "with-a"
[runs.scheme]
instructions = "Use tool A to construct the layout; submit through layout MCP."
[runs.scheme.mcp.a]
command = ["python", "a_server.py"]
files = ["a_server.py", "requirements.lock"]
env_vars = []
```

Inspect the conditions, then run the comparison:

```bash
python -m benchmarking.run --matrix contrast.toml \
  --dataset /path/to/dataset --dry-run
python -m benchmarking.run --matrix contrast.toml \
  --dataset MAI716/ICLayout-Bench
```

Install A and its dependencies before running. Matrix defaults are shallow: each
run's `scheme` is a complete declaration, not a partial merge. Conditions execute
in listed order; this runner does not randomize trials or control provider-side
nondeterminism.

For A implemented as a Python library or CLI, install it in a derived solver
image instead of adding an MCP server. Set `scheme.solver_image` to the immutable
`sha256:...` ID returned by `docker image inspect --format '{{.Id}}' YOUR_IMAGE`.
Install fixed versions during the image build, then use `scheme.instructions`
to explain imports or commands. The same image can contain A for both conditions
if the experiment deliberately measures enabling its use; record that choice.
`--image` selects the default local solver image and is resolved to an immutable
ID before dispatch. Each scheme may override it. The Dataset case's trusted
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
MCP servers receive the scoped session environment so they can use the Bench
HTTP client. No creation credential is forwarded. Native host shell tools remain
disabled; Python/CLI tools installed in the solver run through layout MCP.

For an existing control program, select `harness = "command"` and declare:

```toml
[scheme]
version = "my-controller-1"
[scheme.launch]
command = ["python", "controller.py"]
files = ["controller.py", "requirements.lock"]
env_vars = ["MODEL_API_KEY"]
```

The process receives only the original problem document on stdin. Environment variables
`ICLAYOUT_BENCH_ENDPOINT`, `ICLAYOUT_BENCH_TOKEN` and `ICLAYOUT_BENCH_SESSION`
provide scoped HTTP access; `ICLAYOUT_BENCH_TASK_FILE` points to session metadata,
`ICLAYOUT_BENCH_MCP_CONFIG` to the private MCP config,
`ICLAYOUT_BENCH_INSTRUCTIONS_FILE` to optional operator-declared `scheme.instructions` (empty when absent), and
`ICLAYOUT_BENCH_MODEL` / `ICLAYOUT_BENCH_EFFORT` record requested settings.
The command starts in a fresh private directory. A container/remote launcher
must explicitly forward these inputs and preserve its own version identity.
The original `problem.md` owns the solver goals, optimization workflow and
completion criteria, following the shared [problem structure](tasks.md#problem-statement-structure).
The runner adds no general solver instructions. Native MCP clients receive only
explicit `scheme.instructions` in the MCP initialization result's `instructions`
field; tool descriptions are independent of the scheme and describe their own
calls. Read `/protocol/task.json` in the EDA workspace for the compact solver
manifest and `/protocol/harness.json` for capabilities, budget and available
helper commands; the full evaluation plan is held by the framework.
The runner follows the service's budget policy, captures stdout/stderr, cleans up
its process group and collects the terminal result. Custom commands do not
support native same-session continuation; use `resume_session = false`.

Scheme outputs append their name and content digest to the normal condition
path. Changed declared tools, instructions or images cannot reuse an old case.
Archive comparisons distinguish schemes while matching the service's evaluator
identity, limits and evaluation mode. Result records include the scheme name and
digest so consumers can distinguish tool configurations.
Unknown usage stays unknown, and adding tools grants no new time or repetitions.

<a id="failures-retry-ownership-and-recovery"></a>

## Failure recovery

### Choose the operation

| Situation | Operation | Effect |
| --- | --- | --- |
| Inspect progress | `--status --output ROOT` | Read scheduling state without configuration, login or service calls. |
| Stop a batch | `--stop --output ROOT` | Shut down recorded workers and local services; retain logs and recovery files. |
| Continue unfinished work | Original config/input arguments plus `--resume --output ROOT` | Observe surviving workers, recover permitted sessions and dispatch pending cases. |
| Export an interrupted session | `--collect-only --output ROOT` | Settle and export without launching a model or starting pending cases. |
| Start a replacement solve | Original config/input arguments plus `--replace-unfinished --output ROOT --case ID` | Create a new attempt and budget while retaining the earlier attempt. |

`ROOT` is the condition root containing task/timestamp directories, not an
individual timestamp directory. Use a local filesystem with reliable locks and
atomic rename. Preserve the entire unfinished case, including `.runtime/`.

### Continue a batch

Use the same Bench version and original configuration:

```bash
python -m benchmarking.run \
  --config experiment.toml \
  --output results/my-batch --resume --detach
```

Reuse the original TOML, endpoint or Dataset arguments, images and conditions.
Finished slots are skipped. Surviving workers retain their leases and deadlines;
the coordinator observes them and dispatches pending work as slots become free.
Workers outside a `--case` subset still count toward the concurrency cap.

An interrupted native launch can continue with a recorded native conversation,
an active recoverable service session and remaining budget. Missing tool replies
and uncertain requests do not prevent continuation. The resumed Agent inspects
status, existing execution IDs and workspace files before deciding whether to
poll, cancel or issue another operation. A service execution may remain active
throughout continuation.

The framework does not inspect whether a tool reply entered the Agent's context
and does not replay tool calls when relaunching the Agent or its MCP bridge.
Each new Agent call receives a new operation key. HTTP transport retries within
that call preserve its original key and body. Request/result evidence remains in
the tool journal, including requests whose outcome could not be observed.
The service continues to enforce execution concurrency, paths and budgets.

Continuation validates resolved conditions, framework release, Dataset inputs,
endpoint, CLI version, native storage and frozen launch settings. Repetitions
remain independent solves; continuation is another launch inside the same attempt.
All waits, human repair and downtime consume the original deadline.

#### Local workspace checkpoints

Supported native harnesses enable `resume_session` by default. Their isolated
local services checkpoint workspace bytes and matching HTTP state after file
writes and command completion. Restart restores the committed checkpoint with
the same session ID, scoped token, accepted candidate, image and deadline.
Changes after the checkpoint are rolled back; interrupted executions become
errors and are never automatically replayed. `/tmp` and live processes are
transient. Unchanged workspaces reuse the committed archive.

Sessions without checkpoints cannot gain them retroactively. External solver
runtimes with writable mounts or network side effects do not support workspace
recovery. A remote service must retain its own session state across participant
interruption. Missing or expired service records cannot be recovered as a new
solve through `--resume`.

### Automatic retries and continuation

| Harness | Same-session continuation | Network continuation | Capacity/rate-limit continuation |
| --- | --- | --- | --- |
| Codex, Claude Code, Kimi Code, ZCode | Enabled | Up to 5 additional launches | Up to 5 additional launches |
| DSH | Enabled | Up to 5 additional launches | Disabled |
| Custom command | Disabled | Disabled | Disabled |

HTTP transport retries apply to every experiment harness. The runner makes three
total attempts by default, retrying transport loss and explicitly retryable HTTP
503 responses with the same mutation key/body. A generic `Client` outside the
runner defaults to one attempt. Provider SDK retries remain native to each CLI.
Automatic continuation begins only after the failed native process has stopped;
it does not replay individual model requests or tool operations.

Network continuation requires recognized transient connection failures and
`resume_session = true`. Capacity continuation handles recognized provider
overload; recognized transient rate limits share that counter and additionally
require `resume_session`. Authentication, exhausted account quota, process
signals and unknown/mixed failures do not authorize an
automatic relaunch. A successful native exit does not trigger continuation.
Adapters classify native evidence; generated assistant prose is not evidence.

Network and capacity waits grow exponentially with up to 20% positive jitter,
bounded by their respective caps. A native `retry_after` is a minimum wait;
a hint above the cap or beyond remaining time ends automatic continuation.
The runtime rechecks service state, remaining budget and the persisted native
conversation before relaunch. Missing native history is reported as
`native_session_missing`; tool-delivery uncertainty does not stop relaunch.

Rate-limit and network interruptions retain sessions when continuation is enabled,
including after retries are exhausted. Exhausted overload handling follows normal
settlement. Two consecutively collected capacity/rate-limit interruptions pause
new dispatch for the same harness/provider/model. Running cases continue; other
conditions are unaffected. A case without these interruptions resets the count.

#### Recovery settings

Omit `[recovery]` to use the defaults above. Explicit values override only their
own fields; unsupported capabilities are rejected before dispatch.

| Setting | Default | Accepted values / meaning |
| --- | --- | --- |
| `http_attempts` | 3 | 1–10, including the initial request. |
| `backoff_seconds` | 1 | 0–60 seconds, initial HTTP retry delay. |
| `max_backoff_seconds` | 8 | 0–60 seconds, HTTP delay cap. |
| `resume_session` | By harness | Boolean; disabling it also disables network continuation and local checkpoints. |
| `network_resumes` | 5 or 0 by harness | 0–10 additional launches. |
| `network_backoff_seconds` | 30 | 0–3600 seconds. |
| `network_max_backoff_seconds` | 300 | 0–3600 seconds, at least the initial network delay. |
| `capacity_resumes` | 5 or 0 by harness | 0–10 additional launches shared by overload/rate-limit failures. |
| `capacity_backoff_seconds` | 30 | 0–3600 seconds. |
| `capacity_max_backoff_seconds` | 300 | 0–3600 seconds, at least the initial capacity delay. |
| `capacity_cooldown_seconds` | 300 | 0–3600 seconds; zero disables the dispatch pause. |

For example:

```toml
[recovery]
http_attempts = 5
network_resumes = 8
```

HTTP `Retry-After` beyond the configured cap stops automatic retry. Service
`budget_exhausted` is a solve-budget response, distinct from provider rate limits.
No continuation renews a solve budget or adds a repetition.

### Stop and inspect

```bash
python -m benchmarking.run --status --output results/my-batch
python -m benchmarking.run --stop --output results/my-batch
```

Stop uses recorded PID/start identities and normal shutdown, then terminates
remaining owned trees after its shutdown allowance (up to 60 seconds per tree).
It also finds workers retained after coordinator exit. Stopping preserves evidence
and the original deadline; later continuation still requires a viable session.
Repeated stops leave exited owners alone.

`.scheduler/` records coordinator ownership, dispatch, adoption, completion and
cooldowns. Case summaries and `execution.capacity_recovery` /
`execution.network_recovery` retain failure history and continuation outcomes.
`agent.jsonl` retains native launches in order after credential redaction.

### Collect interrupted sessions without model calls

After the case worker and native process exit:

```bash
python -m benchmarking.run \
  --collect-only --output results/my-batch --case NAND2_X1
```

Omit `--case` to collect all recorded started cases. Configuration and harness
installation are unnecessary. Collection acquires selected case leases, validates
recorded session/task/condition identity, drains existing executions and closes
while retaining the last accepted candidate. It does not submit mutable workspace
output, replay commands, reset deadlines or start pending cases. Live owners block
collection. Unknown runner exit is recorded as `runner_interrupted`, separately
from the evaluator verdict.

Collection can use a newer framework release because it only settles the
original session and preserves its identities. A missing local service is
reported rather than replaced. Failed close/export retains `.runtime/` for retry;
verified terminal export commits before runtime cleanup.

### Replace unfinished attempts

After collecting a running/finalizing session, explicitly replace selected pending,
blocked or suspended cases:

```bash
python -m benchmarking.run \
  --config experiment.toml \
  --output results/my-batch --case NAND2_X1 --replace-unfinished
```

Finished cases cannot be replaced. Model, effort, Dataset inputs, image, endpoint
and repetitions must match. Repaired framework/CLI versions and recovery settings
are recorded on the new attempt. Prior attempts keep their candidates, traces,
failures and original price snapshots; pending cases keep unused plans. An
interrupted replacement move completes when the same command is repeated.
Operator-controlled evaluations apply their separately frozen replacement policy.

### Settlement and failure interpretation

After a participant stops, the runner drains already-started service executions,
then closes while retaining the last participant-accepted snapshot. It never
submits mutable workspace output or replaces an explicit submission. Soft sessions permit
draining after expiry; hard sessions stop waiting at the original deadline. Cleanup never launches or replays an execution.
`finalization.json` records execution offsets, submission outcome and independent
settlement/close errors; drained logs use `finalization-<execution-id>.log`.

Harness interruption, settlement failure and evaluator verdict remain separate.
Authentication/quota failures stop later slots for the same harness/provider/model;
service failures stop subsequent dispatch. Error or incomplete observations remain
unknown in analysis. Preserve original evidence when repairing an environment;
[Results](#results-and-analysis) defines terminal retention and usage across attempts.

<a id="execution-control"></a>

### Active executions

An operator can query or cancel an existing execution during settlement using
the same protected session environment:

```bash
python -m benchmarking.client poll EXECUTION_ID --offset 0
python -m benchmarking.client cancel EXECUTION_ID --key OPERATOR_KEY
```

These commands use the existing service session without launching a model or
starting another solve. Polling/cancellation follow the [HTTP contract](architecture.md#process-feedback).

<a id="result-storage-and-presentation"></a>

## Results and analysis

### Output layout

Default experiment invocations create fresh timestamped task runs:

| Selection | Condition root |
| --- | --- |
| One effort in a config | `results/<config-stem>/` |
| Multiple efforts in a config | `results/<config-stem>/<effort>/` |
| Matrix run | `results/<matrix-stem>/<run-name>/` |

Each condition contains `<full-task-id>/<YYYYMMDD-HHMMSS-microseconds>/`.
Timestamps use local time; unsafe path characters are percent-escaped. Explicit
`--output` selects a condition root verbatim and requires one condition. Declared
schemes add their name/content digest to default condition paths.

A completed local task run contains:

```text
results/my-condition/
  .scheduler/                  # coordinator ownership and scheduling events
  freepdk45.nangate45-pdk.NAND2_X1/20261022-120000-123456/
    result.json                # identity, state, evaluation, execution, model_usage
    final.gds                  # exact scored candidate, when available locally
    layout.png                 # optional preview
    agent.jsonl                # native launches in order, known secrets redacted
    native/                    # selected native histories and diagnostics
    evaluation/                # plan, measurements, logs and diagnostic outputs
    worker-events.jsonl        # worker lifecycle, when available
    service-http.jsonl         # operation/status/timing, when available
    service-lifecycle.jsonl    # local service lifecycle, when available
    service-launch.jsonl       # startup/exit, when available
    .case.lock                 # concurrent owner exclusion
```

With multiple repetitions, the timestamped task directory contains
`repetition-N/` directories with the same files. The case lock stays at the run
root. Retain the configuration and Bench version when reproducing an experiment.
There is no condition-wide result index: `.scheduler/` records ownership and
dispatch, while each task/repetition retains its own result.

Unfinished runs keep `.runtime/`, including private session tokens, native
credentials and workspace recovery state. Terminal export validates and commits
artifacts and `result.json` atomically before removing runtime data. Failed export
keeps that recovery source. Original and replacement attempts retain separate
candidate/check evidence under `attempts/`; collection and replacement follow
[Recovery](#failure-recovery).

`evaluation/report.json` retains job measurements and relevant text diagnostics;
waveforms and native databases remain separate files. Non-UTF-8 logs remain
byte-exact attachments. The compact export retains task/candidate/condition
bindings and the tool image locator, rather than a full operator provenance
archive. Known credentials are redacted; arbitrary generated text requires review
before transfer. Compact exports do not provide post-export tamper detection.

Keep results outside disposable build/cache storage and back them up. Prepared
resources are rebuildable; experiment evidence and checkpoints are persistent.

### Read a run

| Field | Interpretation |
| --- | --- |
| `identity` | Recorded task, condition, implementation and input bindings. |
| `state`, `summary` | Participant lifecycle and compact outcome. |
| `evaluation` | Independent service verdict, candidate, score and metrics. |
| `execution` | Harness duration, failures and recovery history. |
| `model_usage` | Participant-reported native tokens, timing, costs and coverage. |
| `attempts` | Retained evidence for explicitly replaced attempts. |
| `files`, `image` | Retained artifact paths and optional preview metadata. |

Harness exit, evaluator verdict, settlement and preview success are separate
facts. Preserve the recorded score and evaluation mode when importing or
transferring results. A completed physical/functional rejection can score zero;
an unavailable measurement or infrastructure error remains unknown. The
[task contract](tasks.md#evaluation) owns these rules.

<a id="model-speed-and-cost"></a>

### Model usage and cost

`model_usage` is marked `participant_reported` and uses native harness evidence.
The independent service normally cannot observe model usage, so its
`evaluation.usage` remains null. Those nulls do not erase recorded native usage.

| Field | Meaning |
| --- | --- |
| `tokens.input_tokens` | Total input, including uncached input, cache reads and cache writes. |
| `tokens.uncached_input_tokens` | Input excluding both cache categories. |
| `tokens.cached_input_tokens`, `tokens.cache_write_input_tokens` | Cache-read and cache-write counts. |
| `tokens.output_tokens` | Generated output tokens. |
| `tokens.reasoning_output_tokens` | Reasoning subset when supplied natively; never added to output again. |
| `requests` | Per-request records with available usage, timing, source and cost. |
| `cost`, `currency`, `cost_source` | Task cost and its recorded basis. |
| `pricing` | Frozen selected model price table, when configured. |
| `coverage` | Known/missing record counts for each measured field. |
| `api_seconds`, `wall_seconds` | Native API duration and separate participant runtime. |

Missing counts, native timing or prices remain unknown. Partial request coverage
cannot establish a complete total. Failed requests with recorded usage remain
included; DSH transport-only failures without usage or generated content
contribute zero and stay in failure history. Replaced attempts contribute their
original usage and prices; an unknown attempt makes the complete total unknown.

Cost prefers a valid native amount, including a genuine zero, unless the explicit
price table sets `prefer_reported_cost = false`. Otherwise native token counts
are multiplied by the configured rates. `cost_source` distinguishes `provider`,
`harness_reported`, `api_token_pricing` and combined `mixed` costs. Earlier exports
retain their original labels. Subscription-equivalent API costs and actual
subscription invoices are separate quantities.

#### Pricing

Declare `[pricing]` in the experiment TOML, with rates per 1,000,000 tokens:

```toml
[pricing]
currency = "USD"
source = "https://provider.example/pricing"
as_of = "2026-10-01"
input_per_million = 2.0
cache_read_per_million = 0.2
cache_write_per_million = 2.5
output_per_million = 10.0
```

The numbers and source above are placeholders: supply the selected model's
reviewed rates, HTTPS source and date. Cache-write rates are the complete charge
for those tokens. The cost calculation is:

```text
cost = (uncached_input * input_rate + cached_input * cache_read_rate
        + cache_write_input * cache_write_rate + output * output_rate) / 1_000_000
```

To share rates, replace `[pricing]` with top-level
`pricing_file = "prices.toml"`. The file contains one or more
`[models."exact-model-id"]` tables with the same fields. The configured model
must match a table key. Optional `aliases` identifies equivalent request model
IDs. The file resolves relative to the experiment TOML and is read only through
that explicit reference, independently of `harness_home`.

The selected table is frozen in the condition and attempt. Changes apply to new
runs; resume and replacement inside an existing run retain its prices.

| Optional pricing field | Behavior |
| --- | --- |
| `prefer_reported_cost = false` | Use configured rates even when a native amount is available. |
| `long_context_threshold` and `[pricing.long_context]` | Select four alternative rates above a request's input threshold. |
| `peak_utc_hours`, `off_peak_dates`, `[pricing.off_peak]` | Select time-dependent rates by request timestamp; weekends and listed dates are off-peak. |
| `[pricing.models."other-model"]` | Explicit rates for an auxiliary model. |

Context/time tiers require request-scoped input counts/timestamps. Missing tier
evidence leaves costs unknown. Unknown auxiliary models do not inherit the main
model's rates. Each rate override supplies the four rate fields; auxiliary model
tables also require the applicable metadata.

### Structured analysis

Analyze explicitly selected files without model calls:

```bash
python -m benchmarking.analyze \
  /path/to/run-a/result.json /path/to/run-b/result.json \
  --output results/new-analysis
```

Use a new output directory. Participant exports and HTTP service results must be
analyzed separately; each invocation accepts one format. A collection with a
`results` array is also accepted.

| Input format | Output files |
| --- | --- |
| Participant `result.json` | `results.json`, `runs.csv`, `summary.json`, `manifest.json`. |
| HTTP service result | `results.json`, `manifest.json`; nonempty results also produce `runs.csv` and `tasks.csv`. |

Participant CSV records native tokens, `cost_per_task`, currency, cost source,
API duration and wall duration. `summary.json` reports condition-level usage/cost
coverage. Complete totals require all selected measurements; currencies remain
separate. Service analysis groups scores by task/version, condition, tools,
limits and evaluation mode. It reports known/missing counts and sample standard
deviation; a lone sample has no sample standard deviation. Error or incomplete
scores remain missing. Output consists of structured data for consumers to render.

### Saved layout images

Local terminal exports retain the scored `final.gds` and an optional `layout.png`.
Rendering reads that frozen candidate and records the top cell, dimensions and
renderer identity separately from evaluation. Remote-only exports can lack GDS
and images because the current service has no candidate-download endpoint.

Regenerate missing previews using the recorded image, or select an explicit
compatible rendering image:

```bash
python -m benchmarking.layout_preview results/my-condition
python -m benchmarking.layout_preview results/my-condition --image IMAGE
```

Complete previews are reused. Image rendering uses KLayout with full hierarchy,
a white background, proportional framing and a 4096-pixel long edge at 2x
supersampling. Colors are a display convention. Commercial native rendering can
instead use `--pdk /path/to/pdk.toml`, selecting declared Virtuoso/Custom Compiler
modules and the installed Ghostscript rasterizer. It renders a fresh native
library, omits labels and records native/rasterizer identities. Rendering failure
remains an optional presentation error and cannot change a score.

### Result archive

Evidence exports inline valid UTF-8 text. Native logs with non-UTF-8 or mixed
encodings remain separate byte-exact files referenced by the report; exporting
them does not change measurements or scores. Service evidence attachment validates
all staged artifacts before publishing them and commits the manifest last.
Optional preview failures remain separate from evaluation and attachment status.

Use the optional archive to import results, query records and generate structured
comparison or presentation data. Bench supplies Python interfaces and a CLI;
graphical browsing and publication require a separate application. To hand results
to an evaluation operator, see [website result delivery](#website-result-delivery).

For offline archive processing, install `iclayout-bench[results]`. The importer
accepts `participant-result` exports and terminal `layout-http` results. It
preserves recorded evaluation modes; importing a local run does not certify it.
A protocol-only import has no inferred CLI, effort, timing or local candidate.

```bash
python -m benchmarking.results --data results/archive \
  import /path/to/participant/results --experiment my-experiment
python -m benchmarking.results --data results/archive \
  catalog --dataset /path/to/dataset
```

These optional commands create `results/archive/`; no results ship with the package.
The operator platform imports terminal collections into its own storage and applies
publication permissions independently of an offline archive.

`layout` caps each metric at quality 1 before aggregation with explicit task
weights, giving a maximum of 100. Result imports require this single score
contract; reports and comparisons use the recorded 0–100 values.

#### Comparisons

Comparison data keeps task version, tool identity, budget, evaluation mode and
score method separate. Conditions distinguish model, harness, CLI, effort and
recorded prompt/configuration identities. Task/condition records include all
repetitions, measured counts, failures and missing scores. An error remains
unknown, not zero. Overall means use equally weighted, fully measured common task
contexts; coverage and the common-task count remain visible. Unknown scoring
methods form separate contexts.
Planned but unexecuted tasks from runner schedules appear as `Not run`; historical
imports cannot reconstruct an absent experiment schedule. Missing provenance is
not inferred from directory names.

#### Task presentations and interactive layouts

`catalog` reads **the full Dataset commit recorded in each result**, using the supplied
Dataset repository as a resource. A local Git repository must retain those
Dataset Git objects; a repository ID resolves the recorded Dataset snapshot.
It verifies the netlist's declared digest and, when present, the recorded task
digest. Missing revisions or mismatched task definitions are reported as
unavailable rather than matched to today's circuit.

The catalog attaches the authoritative SPICE/CDL netlist, source metadata and
available collection license/notice files. It preserves netlist bytes without
requiring a schematic renderer or interpreting device syntax for presentation.
These materials remain outside solver inputs. Catalog import never edits case
definitions, changes task identity or regenerates schematic drawings.

Generating optional interactive geometry requires KLayout in the Python
environment running the command:

```bash
python -m benchmarking.results \
  --data results/archive geometry
```

The generated data includes layers, physical coordinates, hierarchy-flattened
polygons and labels for platform presentation. Extraction has a 200,000-shape limit; larger candidates retain
their PNG and downloadable GDS. This bounds browser work rather than silently
truncating geometry. KLayout DRC reports can supply top-cell marker overlays.
Hierarchical markers without transforms remain in the report and are counted as
not overlaid. Cross-highlighting netlist nets against layout connectivity and
large-design multiresolution tiles are not implemented.

#### Automatic indexing and recovery

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
python -m benchmarking.results --data results/archive retry
python -m benchmarking.results --data results/archive verify
```

`retry` consumes durable pending entries without starting models. Keep source
exports until pending entries have been delivered. `verify` checks every registered
artifact's bytes against its stored digest. A repeated identical import is a no-op;
a changed run identity or immutable attachment fails. Explicit `import
--reevaluation` retains a new evaluation revision; the newest revision is selected
by default and previous revisions remain accessible. It cannot replace a run's
candidate or task identity. Derived presentation artifacts may be regenerated
without changing any score.

Participant results retain task, candidate and condition hashes. Unknown usage
stays null; CLI-reported usage never becomes service-observed usage.

Automatic indexing targets the participant-selected archive, not an operator
website. Neither `results_data` nor archive `retry` uploads files to the website,
and an evaluation `--endpoint` is not a website import endpoint. See
[result handoff and storage ownership](architecture.md#result-handoff-and-storage-ownership)
for the separate transfer, ingestion and publication boundaries.

#### Storage, deployment and backup

SQLite metadata resides in `results.sqlite3`; `objects/<prefix>/<sha256>` contains
copied attachments. Source directories may be moved after successful import. Keep
the database and objects together outside disposable `build/` storage. SQLite uses
WAL and short transactions on a local disk; do not put its WAL database on a shared
network filesystem. Stop archive readers and indexing writers before copying the
entire archive (including pending entries and SQLite sidecars). Restore into a new
directory and run `verify` before using it.

For PostgreSQL, install `iclayout-bench[results,postgres]`, provision an empty database,
and set `ICLAYOUT_BENCH_DATABASE_URL` to a SQLAlchemy `postgresql+psycopg` URL. Use the
same `--data` attachment root for all processes. The archive creates missing tables from the current definitions
when it opens; existing columns are not automatically transformed. SQLite and PostgreSQL use the same result model; moving
existing SQL contents between backends is not an automatic database conversion.
Reimport original exports into the target database, then regenerate presentations,
or perform an operator-managed SQL migration. Back up PostgreSQL and its associated
object directory as one quiescent snapshot. Generic public code supplies no formal
operator deployment or result-publication policy.


### Website result delivery

The installed package includes a standard-library-only delivery CLI, independent
of operator applications and optional SQL archive dependencies. Run the complete
experiment first, then create a portable package:

```bash
python -m benchmarking.results.transfer pack results/my-experiment my-experiment.zip
```

Remote upload is available only when the operator deployment enables participant
accounts and ingestion. Otherwise hand the complete package to the operator
through its agreed transfer channel.

Obtain the website URL and an upload token from the operator, then supply the
token in `ICLAYOUT_UPLOAD_TOKEN`. Account creation and authentication depend on
that deployment. Do not put tokens in command arguments, scripts committed to Git,
experiment TOMLs or result packages. The CLI accepts another environment variable
via `--token-env`.

```bash
python -m benchmarking.results.transfer upload my-experiment.zip \
  --website https://benchmark.example --name 'My experiment'
python -m benchmarking.results.transfer status JOB_ID --website https://benchmark.example
```

Use the actual configured website origin. Remote delivery requires HTTPS; HTTP is
allowed only for loopback development. The client refuses redirects so bearer
credentials cannot be forwarded to another origin. Authentication errors require
credential replacement; a successfully received upload returns a durable job ID,
not a publication promise. Reuploading identical package bytes with the same name
under the same account returns the same job. Status distinguishes queued/running,
completed, completed-with-errors and failed. Use the operator's supported retry
interface for failed imports. Correct a malformed package at its source and
package it again. The CLI never reruns an Agent or evaluator and never deletes
original results.

#### Package and HTTP contract

`iclayout-results` is a ZIP containing `manifest.json` and terminal collections
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
cohorts remain isolated even if their declared model conditions match. Original
recorded scores, methods and evaluation mode metadata remain intact. Operator review
still controls score and file publication independently.
