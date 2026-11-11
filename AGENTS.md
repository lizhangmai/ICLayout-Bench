# ICLayout-Bench Repository Conventions

This public repository owns the standalone evaluation framework, participant interfaces,
shared scoring, EDA adapters, HTTP evaluation service and result interfaces.
Tracked files and commit messages stay free of private task material, internal
paths and credentials. Start with [README](README.md), run `git status --short --branch`,
and preserve unrelated changes.

## Read for the Change

| Work | Read first |
| --- | --- |
| Public interfaces or protocol boundaries | [Architecture](docs/architecture.md), especially the [HTTP contract](docs/architecture.md#http-session) |
| Tasks, inputs, metrics or judges | [Task contract](docs/tasks.md) and [qualification](docs/tasks.md#qualification) |
| Participation, native configuration, scheduling or recovery | [Running](docs/running.md) |
| Statistics, archives or presentation assets | [Results and analysis](docs/running.md#results-and-analysis) and [archive verification](CONTRIBUTING.md#result-archive-verification) |
| Shared execution, frozen evidence or result finalization | [Shared interfaces](docs/architecture.md#shared-execution-and-evidence-interfaces) |
| Images, PDKs, adapters or measurements | [Tools](docs/tools.md) and [image development](CONTRIBUTING.md#image-development) |
| Result handoff or evaluation mode | [Handoff](docs/architecture.md#result-handoff-and-storage-ownership) and [evaluation mode](docs/architecture.md#evaluation-mode) |
| Result packages or upload | `benchmarking/results/transfer.py` docstring and `--help` (unreleased; kept out of `docs/`) |
| Tests or fixtures | [Test conventions](tests/AGENTS.md) |

## Implementation Boundaries

- Follow the public interface boundaries in the architecture guide. Consumers use installed
  public interfaces; package imports, installation and offline CI work without sibling repositories.
- Load static Dataset inputs through explicit paths or IDs. Authoring code and
  qualification evidence remain with the author; operator policy and website code
  remain with their owning applications.
- Standard solves expose only [declared inputs and reviewed resources](docs/tasks.md#input-isolation).
  Evaluate frozen candidates independently of solver credentials and writable directories.
- Evaluate submitted circuits without completing solver work. Adapters may bind run
  I/O, parse reports and reorder existing named ports; preserve extracted device
  models, parameters and connections. Process compatibility belongs to declared
  resources and author validation. Before changing extraction or netlist adapters,
  read [evaluator responsibilities](docs/architecture.md#system-roles-and-boundaries).
- Own shared participant lifecycle, single-run evidence verification, machine-readable
  results, usage semantics, shared statistical interfaces and EDA layout preview assets;
  analysis commands export JSON/CSV. Keep original scores, usage, identities and
  verification levels when archiving or delivering results, and distinguish derived
  aggregates from original results. Consuming applications own secondary aggregation,
  weighting, ranking, charts, interactive comparisons and report presentation; review
  and publication belong to the operator.
- Set up development dependencies from the project declarations and lockfile using
  [development setup](CONTRIBUTING.md#development-setup). Keep generated results,
  credentials and machine-specific settings out of tracked source. Document commands
  that work from a fresh clone or an installed package; accept explicit Dataset,
  image and output selections without requiring a maintainer's workspace layout.
- For PDK manifests, resource adapters or runtime control files, follow
  [PDK resource manifests](docs/tools.md#pdk-resource-manifests-for-dataset-authors).
  Keep native content in referenced files and cover preparation, Agent relocation
  and portable file inventory.

## Documentation

- README is the user quick start and owns documentation navigation; edit
  `README.md` and `README_CN.md` together. `docs/` holds English user guides and
  public contracts; CONTRIBUTING owns development and verification workflows.
- Document released behavior for users, in the present tense. Features not yet
  open to users, such as hosted remote participation and website result
  delivery, stay in code and docstrings until release. Incident notes, version
  history and migration steps belong in commit messages; plans, review logs and
  local validation evidence stay out of `docs/`.
- Make each guide usable from this repository alone: links in `docs/` stay inside
  it, and required behavior is explained locally rather than through root
  documents, upstream websites, local evidence or sibling repositories.
- When behavior changes, update the owning guide and keep existing anchors
  resolvable; add an explicit `<a id>` when renaming a heading.

## Completion

Select checks by change scope and delivery stage from [CONTRIBUTING](CONTRIBUTING.md#verification).
Check changed links and commands, and report actual validation scope and Git status.
Verify affected repositories separately; commit only when authorized, with one repository per commit.
