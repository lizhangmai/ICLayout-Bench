# Participant examples

Example configurations for Codex, Claude Code, DSH and Kimi Code using the installed
ICLayout-Bench package. Use an existing Python 3.12+ environment with the package
and participant dependencies installed, and authenticate your chosen harness.

## Run

From `examples/`:

```bash
bench_python=/path/to/existing/environment/bin/python
export ICLAYOUT_BENCH_DATASET=/path/to/ICLayout-Bench-Dataset
"$bench_python" -I -m benchmarking.run \
  --config configs/codex-gpt-6-astra-medium.toml --dry-run
```

`bench_python` is the absolute interpreter path of the existing participant
environment. In the AutoLayout workspace, reuse the formal Bench `.venv`; independent
participants use their existing installed-package environment. Python `-I` keeps
the launch independent of the working directory and `PYTHONPATH`.

`requirements.txt` lists participant dependencies. Maintain them in the selected
environment before experiments, using an explicitly supplied wheel when the package
is not available from your index. The run command does not create an environment,
install dependencies or upgrade packages.

Codex and Claude Code runs default to up to five automatic continuations after
recognized capacity errors, without requiring a recovery table in the TOML.
They preserve the original conversation, workspace, model and deadline. See
[recovery settings](../docs/running.md#failures-retry-ownership-and-recovery)
for backoff, dispatch cooldown and supported harnesses. Fresh invocations use
this policy; existing experiment records retain their original settings.

Choose another TOML in `configs/` for Claude Code, DSH or Kimi Code. Remove `--dry-run` to
make real model calls. Local evaluation requires Docker and a compatible EDA
image (`--image`); remote evaluation uses `--endpoint`. See the
[running guide](../docs/running.md) for authentication and runner options.

The Kimi Code example is `configs/kimi-code-k3-high.toml`. Run `kimi login` first;
the model alias `kimi-code/k3` must exist in the Kimi configuration.

## Dataset and local settings

Keep experiment configurations directly in `configs/`, with the effort in each
single-condition filename. The configurations use
`[dataset].source_env = "ICLAYOUT_BENCH_DATASET"`; set this environment variable
to an absolute local Dataset path or a Hub Dataset ID before running, including
for `--dry-run`. When using a Hub ID, add `revision` to the Dataset table to pin
the desired commit. Relative Dataset paths resolve against the TOML.

The maintained configurations retain the chosen task selection and concurrency;
edit these values in the same files for subsequent experiments. Machine-specific
paths and credentials stay outside the TOMLs.
Configurations selecting `core` inherit the Dataset's dispatch order. Define a
`tasks` list only to override that order or select a different subset.

Keep credentials in harness-managed storage or exported environment variables.
These commands do not load `.env` files.

## Results

Complete results, including failures, belong in the persistent, Git-ignored
`results/` directory. Within each experiment, Dataset-backed results follow
`<pdk>/<collection>/cases/<case>/`, matching the Dataset task hierarchy.
The default output is `results/<config-stem>/<timestamp>/`, with no intermediate
`experiment/` directory. Name single-effort configurations with their effort,
for example `configs/codex-gpt-6-astra-medium.toml`. Each invocation creates
a fresh timestamp directory beneath `results/codex-gpt-6-astra-medium/`.
Use `--output` to select an exact destination, including when resuming an existing
run with `--resume`. Resume only with compatible inputs and environment.
After a framework repair, explicitly replace selected unfinished cases using
`--replace-unfinished --output <batch> --case <case>` with the original config.
This preserves old attempts and records the actual new runner version while
requiring unchanged model, effort, task inputs, image and repetitions. Finished
cases are never replaced; see the [replacement guide](../docs/running.md#failures-retry-ownership-and-recovery).
Dispatched cases have independent workers that finish settlement and export if
the scheduler exits. To collect a retained session after its worker also exits,
use `python -m benchmarking.run --collect-only --output <batch> --case <case>`.
This uses recorded identities and accepted candidates without any model calls;
it does not dispatch pending cases. See the [recovery guide](../docs/running.md#collect-interrupted-sessions-without-model-calls).
See the [running guide](../docs/running.md#output-layout) for multi-condition configs.
Preserve historical results and back them up.

Review traces and credentials before sharing. Follow the
[result handoff guide](../docs/running.md#website-result-delivery) to submit
complete collections to an operator; submission and publication are separate steps.
