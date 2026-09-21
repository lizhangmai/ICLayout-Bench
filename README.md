# ICLayout-Bench

An MIT-licensed framework for developing and evaluating integrated-circuit layout
agents, with separately licensed public tasks, independent observation, a generic
HTTP client, a shared evaluation engine and a local evaluation service. [简体中文](README_CN.md)

Run public tasks locally to debug your Agent before participating in an operator's
unified evaluation service. Both paths use the same HTTP contract, isolated EDA
execution and independent scoring implementation. Local results are development
evidence; formal results require operator-controlled conditions and verification.
Operators may add hidden tasks, admission, controlled reruns and reviewed releases.

Current tasks use source simulation as the 100-point electrical reference and a
frozen compact-area reference with circuit-specific metric weights (`layout`);
scores may exceed 100. See
[scoring and task design](docs/tasks.md#task-scoring).

## Install and run

Use Python 3.12+ and install the ICLayout-Bench wheel. Engine source stays on
GitHub; tasks and the official core selection live in an independent
Dataset repository. No Dataset is bundled in the Python package.

Supply an HF Dataset repo ID and optional fixed `--revision` once published, or a
local Dataset working copy for development. The Dataset source and revision are explicit caller inputs. Pull a prebuilt Docker Hub tools image or build and customize the Dockerfile;
see [image setup](docs/tools.md#prebuilt-images-and-local-builds). With that image:

```bash
python -m benchmarking.engine.preview --dataset /path/to/ICLayout-Bench-Dataset \
  run --case NAND2_X1 --image iclayout-bench-tools:local --output build/reference-check
python -m benchmarking.run --config experiment.toml \
  --dataset /path/to/ICLayout-Bench-Dataset --output results/new-experiment
```

Reference evaluation makes no model calls. The experiment runner starts the local
service and the selected participant harness. It records the dataset commit,
input digests and tool identities. HF manages downloaded task caches; resource
installation and derived PDK caches are automatic. There is no prepared case
export. Only declared inputs enter the isolated solver workspace.

For remote participation, use `--endpoint` and operator credentials instead of a
local Dataset. Docker and PDK resources are not needed on the participant host.
See [running](docs/running.md) for experiment configuration and output contracts,
and [tools](docs/tools.md) for reference checks and resource management.

The [participant examples](examples/README.md) provide runnable harness
configurations, installed-package usage instructions and persistent, Git-ignored result storage.

## Licensing and public data

The engine is [MIT licensed](LICENSE). Independently distributed circuits,
reference layouts, PDKs and tools retain their own licenses. Consult the Dataset's
Dataset card and collection notices; public availability does not grant additional
redistribution or commercial-use rights.

Dataset process manifests select pinned external resources. The engine wheel
provides the `benchmarking` namespace and its `engine`, `service`, `participants`
and result subpackages. A local Dataset is an explicit data input, never an
importable dependency on the design authoring workspace or on another Python source checkout.

<a id="resources"></a>

## Guides

| Topic | Guide |
|---|---|
| Protocol, ownership and trust | [Architecture](docs/architecture.md) |
| Local self-testing, remote participation and analysis | [Running](docs/running.md) |
| Task contracts, scoring and qualification | [Tasks](docs/tasks.md) |
| Tool images and resource preparation | [Tools](docs/tools.md) |
| Result storage, comparisons and presentation data | [Result storage](docs/running.md#result-archive) |
| Formal reruns and disclosure | [Admission](docs/architecture.md#verified-reruns-and-disclosure) |
| Verification and contribution | [Contributing](CONTRIBUTING.md) |

## Validation scope

Public owns client/observation tests, engine regressions, container isolation checks
and public reference/counterexample checks. Offline tests need neither Docker nor
operator applications. Container/EDA tests require the declared tools. Operators verify admission,
controlled reruns and disclosure using that same engine. Synthetic protocol runs
are not model scores; reference evaluation is not an Agent measurement.
