# Participation and Result Analysis

## Local self-testing

Run the [README quick start](../README.md#quick-start) to prepare a public case,
check its reference and start the local HTTP service. Use the official harness or
your custom harness against that endpoint. It uses the same evaluation engine as
operator runs, but always reports `local_development`. You control the local task,
image and resources; a local pass does not certify a formal or hidden-task result.

To reuse an existing compatible image and prepare a fresh case without a reference
run, execute from the Public checkout:

```bash
uv run --locked python -m layout_eval.preview prepare \
  --case cell_6t --image iclayout-bench-tools:dev --output build/prepared-cell6t
export ICLAYOUT_BENCH_TOKEN="$(openssl rand -hex 32)"
uv run --locked python -m layout_service \
  --prepared build/prepared-cell6t --data build/local-service \
  --image iclayout-bench-tools:dev --token-env ICLAYOUT_BENCH_TOKEN
```

Preparation requires the public catalog and pinned upstream sources. An installed
wheel accepts `python -m layout_eval.preview --public-root /path/to/ICLayout-Bench
prepare ...`; that checkout supplies resources, not imported Python modules.
Use new output directories. The local server binds to loopback and accepts one
active session. Set `--seconds` for the session budget and `--port` for the listener.
Receipt retention is seven days; remove expired local storage when no longer needed.

To inspect an existing candidate without running an Agent, use its prepared case:

```bash
uv run --locked python -m layout_eval.cli evaluate \
  build/prepared-cell6t/case/case.toml my-candidate.gds --output build/candidate-check
```

Inspect the printed failure summary and `build/candidate-check/report.json`, plus
the per-job evidence in that newly generated directory, to locate physical,
connectivity, geometry or post-layout failures. Evaluation uses the case's frozen
toolchain. It does not convert a reference or manually supplied GDS into model output.

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
{"task_id":"freepdk45.OpenRAM.cell_6t","condition":{"harness_kind":"custom","harness_id":"local-cli","harness_version":"1","model":"YOUR_MODEL","prompt_sha256":null,"configuration_sha256":null}}
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
uv run --locked python -m benchmarking.client result --export build/runs/custom-result
```

Write your own generator before running it and use the output path in the task
contract. `exec` polls bounded logs. Commands share workspace files but run in the
foreground; leftover processes are removed. Replay an uncertain mutation using
its identical body/key. A new operation requires a new key. Accepted submissions
are immutable; the last accepted candidate wins. A receipt is not a passing verdict.
Optional diagnostics/opinions are available only when advertised in capabilities.

## Official harness

`benchmarking.official` implements the public observe/action loop. Its included
Codex provider requests one structured action per model call and rejects model
host-tool events. The harness maintains a bounded recent history, clips long tool
observations, enforces a step limit, reserves closing time, and attempts a snapshot
after each successful command when the declared output exists. This early-submission
policy is part of the measured condition, not a claim that the output is valid.

```bash
uv run --locked python -m benchmarking.official \
  --task freepdk45.OpenRAM.cell_6t --model YOUR_CONFIGURED_MODEL --effort medium \
  --steps 32 --key official-1 --output build/runs/official-1
```

Use an existing authenticated `codex` CLI. Model/effort are explicit; user/project
configuration, plugins, hooks, apps, web search, host skills and multi-agent
operation are disabled for the structured provider. Auth remains with the CLI.
No service credential goes to the provider process. A provider warning or failure
is not a candidate; an invalid action closes the session with a recorded harness
error while retaining accepted candidates. The remote deadline remains authoritative.

The generated directory contains frozen conditions, redacted session metadata,
provider/action/observation JSONL, harness outcome and service result tables.
Growing raw transcripts remain local and should not be committed. Missing model
usage stays null; raw CLI counters are separate provider/participant evidence.
Official harness identity does not certify a participant-controlled run.

## Analysis

```bash
uv run --locked --group analysis python -m benchmarking.analyze \
  build/runs/official-1/analysis/result.json \
  --output build/runs/analysis --plots
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
Private's `layout_operator` owns frozen reruns, admission and reviewed releases.
The shared `layout_eval` engine and `layout_service` adapter remain in Public.
Scoring definitions are [public](tasks.md#task-scoring), and local/verified results
remain separate analysis cohorts.
