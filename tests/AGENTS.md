# Test Conventions

Applies to test code, fixtures and generators. Use the
[verification guide](../CONTRIBUTING.md#verification) for commands and the
[qualification guide](../CONTRIBUTING.md#task-qualification) for evidence requirements.

## Before Adding a Regression

Inspect existing coverage and relevant test-cleanup history before creating a
test or fixture. Establish these four points in working notes:

1. The public behavior protected and a concrete defect that would fail the test.
2. The gap in existing coverage and the smallest extension that closes it;
   justify a separate test file or fixture only when reuse is insufficient.
3. The authority for inputs/settings and the independent basis for expectations.
4. The artifact owner and the precise claim a passing result would support.

Add a regression only when all four are established. Adding a case or PDK does
not itself require a new test file, circuit or generator. Use existing catalog
regressions for ordinary case acceptance. Keep exploratory circuits, layout
repair scripts and debugging decks under `build/runs/`; a successful experiment
does not make them maintained tests. Missing validation remains a reported gap,
not a reason to weaken this gate or claim qualification from test counts.

## Assertions and Configuration

1. **Protect a contract, not the implementation.** Every test names a behavior, protects a contract, and has a real defect that would make it fail. Derive expectations independently — from requirements, public interfaces, or separate calculation. Comparing code with itself or copying current output proves nothing.
2. **Declare each value once.** Every limit, digest, count, or option has exactly one authoritative home: the configuration, the protocol, or the documentation. A test that restates a declared value as a literal locks a second copy — it breaks on legitimate changes and catches no defect. Read the value from its authority at runtime and assert behavior or relationships instead. When two records must agree, check them against each other; a third copy in the test adds nothing.
3. **Keep refactoring cheap.** Assert only what the contract guarantees. Exact paths, ordering, counts, and internal call sequences are off-limits unless the contract specifies them.
4. **Fake only the boundaries.** Test doubles belong at external I/O, tools, and execution; the behavior under test runs for real. Prefer minimal synthetic inputs through public entry points; use real data only where the check depends on it.
5. **A failing test is a question, not noise.** Check requirements and implementation first. Update expectations only when the contract has changed — copying new output to restore a pass is not a fix. Remove assertions that no longer distinguish correct from incorrect.

## Public Case Regressions

Discover cases and obtain their inputs, resources, interfaces and limits from the
catalog/configuration. A shared regression must work without branches on circuit
names, duplicated port/layer tables, or a prescribed witness score. Witness tests
check published acceptance conditions; scoring policy and error semantics belong
in the common evaluator tests.

Construct case environments through their declared toolchain and resource
profiles. Keep process options, model names and layer mappings in their owning
configuration; tests must not assemble a parallel process configuration.
Published witness assets belong to the Dataset; full case-specific validation
results remain with the author. Acceptance summaries are explicit author-owned inputs, outside the Dataset.

## Analytical Controls

A maintained analytical control must satisfy the regression gate above and
document the following next to the test:

- The isolated physical or tool behavior, governing equation or external
  reference, assumptions, and justified tolerance.
- Which parameters come from the configuration under test and which evidence
  is independent. Reading a deck coefficient can test application of that
  coefficient; copying it into an expected-value literal does not validate its
  accuracy. A formula alone does not establish an independent oracle.
- Why the minimal geometry or circuit is necessary. Prefer an existing declared
  case when device behavior is required. A new MOS circuit with routing, biasing
  and a simulation deck needs its own justification; calling it a wire control
  or placing it in `fixtures/` does not provide one.
- The validity prerequisites and claimed scope. Device/connectivity assumptions
  require appropriate physical and connectivity checks or independent evidence.
  A pure geometric control need not be a manufacturable circuit, but its result
  cannot establish circuit feasibility, device correctness or physical signoff.

Choose counterexamples from a stated contract or physical law. Witness geometry
tuned to a desired score and circuit design/repair procedures are not independent
oracles. Renaming, relocating or rewriting such a procedure does not qualify it
as a regression; evaluate any proposed replacement against the same gate.

## Completion Review

Review every added or changed test, fixture and generator, including untracked
files, against the gate before reporting completion. Remove redundant coverage
and duplicated configuration. When withdrawing a test, update its callers and
documentation claims; preserve useful experiments only as development history.
Report the behavior actually verified and remaining evidence gaps. Passing
reference evaluation, regression coverage and independent extraction accuracy
are distinct claims; keep them distinct in case qualification documentation.
