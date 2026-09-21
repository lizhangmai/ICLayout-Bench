# Participant examples

Example configurations for Codex, Claude Code and DSH using the installed
ICLayout-Bench package. Install uv, Python 3.12 or newer, and authenticate your
chosen harness before running.

## Run

From `examples/`:

```bash
uv run --no-project --isolated --upgrade --with-requirements requirements.txt \
  python -I -m benchmarking.run \
  --config configs/codex-gpt-6-astra.toml --dry-run
```

This uses the latest compatible package releases in an isolated environment.
Until `iclayout-bench` is published to your package index, add
`--find-links /path/to/wheels` to the uv options to supply a built wheel.

Choose another TOML in `configs/` for Claude Code or DSH. Remove `--dry-run` to
make real model calls. Local evaluation requires Docker and a compatible EDA
image (`--image`); remote evaluation uses `--endpoint`. See the
[running guide](../docs/running.md) for authentication and runner options.

## Dataset and local settings

The TOMLs specify the public Dataset and a fixed Hub revision. For local data or
custom experiments, copy a TOML into the Git-ignored `configs/local/` directory
and pass that file to `--config`. Set `[dataset].source` to your Dataset path and
remove `revision` for local data. Relative Dataset paths resolve against the TOML.

Keep credentials in harness-managed storage or exported environment variables.
These commands do not load `.env` files.

## Results

Complete results, including failures, belong in the persistent, Git-ignored
`results/` directory. Use `--output` to choose a destination; use fresh outputs
when changing inputs or experiment conditions. Resume only with the original
compatible environment and inputs. Preserve historical results and back them up.

Review traces and credentials before sharing. Follow the
[result handoff guide](../docs/running.md#website-result-delivery) to submit
complete collections to an operator; submission and publication are separate steps.
