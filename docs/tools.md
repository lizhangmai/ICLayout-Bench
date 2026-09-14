# Tool Environments, Resource Preparation, and EDA Adapters

For the first run, use `quickstart` from the root [README](../README.md#quick-start-no-model-key-required); it builds only one `layout-bench-tools:local` image. This page covers stepwise preparation, troubleshooting, and changes to the tool environment. Run every command from the repository root and use a new output directory. Repository-local generated outputs use `build/`: benchmark runs go under `build/runs/`, independently prepared support bundles under `build/support/`, and Python distributions under `build/dist/`.

## Stepwise Preparation and Reuse

The host uses Linux x86-64, Git, uv, Python 3.12+, and accessible Docker/BuildKit. Versions are maintained by the [Dockerfile](../Dockerfile), [pyproject.toml](../pyproject.toml), and [uv.lock](../uv.lock); framework development needs only `uv sync --locked`.

| `scripts/public_preview.py` subcommand | When to use it |
|---|---|
| `doctor` | Check the host and Docker before downloading; does not call a model |
| `build` | Build only the unified image; accepts `--image`, defaulting to `layout-bench-tools:local` |
| `prepare --output <new-directory>` | Prepare the selected case, Magic, simulation models, KLayout rules, and solver resource bundle from the pinned PDK; bind tools to the actual image ID |
| `run --prepared <prepared-directory> --output <new-directory>` | Evaluate the prepared case witness through its complete declared plan and save raw evidence |

`quickstart` chains host checks, image build, PDK initialization, preparation, and reference evaluation, and writes `prepared/` and `run/`. It defaults to comparator; `quickstart` and `prepare` discover executable post-layout cases from the public SG13G2 catalogs and accept their directory names through `--case`. Use `--help` for the current choices. The script uses each case's `[toolchain]`, constraints, evaluation plan, and published witness. Preparation binds image/resource paths and shared inputs to local snapshots in a host-side copy at `prepared/case/case.toml`. The solver loader still materializes only declared inputs, excluding the copied reference and source README. Models and composite extraction resources are selected by explicit backend metadata rather than inferred from a circuit's name or source collection.

Local preview accepts executable candidates and qualified cases with published
references. Preparation prints the case status; a successful preview does not
establish qualification or formal admission.

Declare `support_profiles` alongside a backend's `type` and `settings` when
automatic preparation needs model or composite support bundles. Each key names
one support-path setting, and its value names a profile in `pdk.toml`. The
mapping must cover all of that backend's `support` and `*_support` settings.
For example, an HBT simulation backend uses:

```toml
[toolchain.backends.simulation]
type = "ngspice-docker"
support_profiles = { support = "hbt-models" }

[toolchain.backends.simulation.settings]
image = "layout-bench-tools:local"
support = "build/support/example-hbt-models"
```

The directory in this example is created by resource preparation; it is not
shipped with the repository. Use `analog-models` for the reviewed CMOS/MIM/tap
model closure. A composite backend can declare
`support_profiles = { klayout_support = "klayout", magic_support = "magic" }`.
The metadata is validated by the host toolchain loader and never passed to a
backend constructor or delivered as a solver input. Legacy KLayout and Magic
backends with a single support setting retain their unambiguous type-based
preparation defaults. Direct evaluation may still use manually prepared bundles.

`--skip-build` reuses the existing image and still binds its actual ID. Existing PDK files are reused and checked against reviewed digests; output directories must be new. Quick start makes no model calls and does not establish new qualification conditions. Case-specific tests cover calibration and rejection behavior; see [CONTRIBUTING](../CONTRIBUTING.md#verification).

The unified image contains KLayout, Python, ngspice, Qucs-S/Qucsator, Magic, OpenVAF, and Xschem. Harness runtimes are deliberately outside this image: a harness supplies its executable and reviewed files, or selects an image that provides them, while the benchmark only requires the common session protocol. Each operation still starts an isolated container, but every EDA operation resolves the same image ID. The image contains no task, PDK, harness source, or credentials; `.dockerignore` allows only dependency declarations and lock files. Install the KLayout CLI and Python API from separate packages and have tool checks confirm that their versions agree. The build does not depend on a local KLayout source tree or private cache.

The build needs access to system packages, tool release sites, and the Python index, and verifies downloaded artifacts against fixed digests. The distribution still resolves base system packages, so the final image identity binds the result; the Dockerfile alone cannot guarantee a byte-for-byte rebuild. To use a host loopback proxy:

```bash
uv run --locked python scripts/public_preview.py build --network host
```

The script preserves existing `HTTP_PROXY`, `HTTPS_PROXY`, and `NO_PROXY` variables. Proxy settings affect the build only; the harness controls networking for run containers.

<a id="preview-troubleshooting"></a>

## Startup Troubleshooting

| Symptom | Handling |
|---|---|
| Docker command is missing or cannot reach the daemon | Install/start Docker first and ensure the current user can run `docker version`; `doctor` checks this before downloading and preparing |
| Native ARM, macOS, or Windows environment | Use a Linux x86-64 host; the current tool image is fixed to amd64 and other platforms are unvalidated |
| `PDK missing` or a pinned source file is absent | Run `quickstart` to initialize the PDK and the required nested KLayout Python dependencies, or run `git submodule update --init --depth 1 third_party/IHP-Open-PDK` followed by `git -C third_party/IHP-Open-PDK submodule update --init --depth 1 ihp-sg13g2/libs.tech/klayout/python/pycell4klayout-api ihp-sg13g2/libs.tech/klayout/python/pypreprocessor`; when a source digest differs, inspect local changes and the recorded commit and keep the hash check enabled |
| A required nested PDK directory is non-empty but has no Git metadata | Do not run recursive update over it. Move the partial directory aside, then run the targeted nested-submodule command above; if its reviewed marker files are complete, `quickstart` reuses it and `prepare` verifies the content |
| `No such image` or image validation fails during preparation | Run `quickstart` or `build`; when naming an image manually, pass `--image` to `prepare` |
| A `build/...` support bundle is missing | Complete `prepare` first. Use the resulting `prepared/case/case.toml`, whose embedded bindings point to the prepared bundles |
| Output directory already exists | Choose a new `--output` path; logs produced by failed steps remain in the old directory for diagnosis |
| Build download fails | Check connectivity to Ubuntu, the Python package index, and tool release sites; downloads require matching digests. With a host loopback proxy, add `--network host` to `quickstart` or `build` and preserve `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY`; see [stepwise preparation and reuse](#stepwise-preparation-and-reuse) for other network setup |
| A real model lacks a key or cannot be reached | Validate the environment with the no-key public flow first, then configure your endpoint, model, and host key variable using [the model gateway and declared wire adapter](running.md#model-inference); public CI does not call a paid model |

<a id="external-sources"></a>

## Upstream and Process Resources

The addresses in `third_party/` are declared by [.gitmodules](../.gitmodules), and versions are fixed by Git submodule references; nested dependencies use the commits recorded upstream. The public preview needs the PDK and its two KLayout Python dependencies used by the reviewed view. The top-level submodules contain evaluator PDK, model and rule resources. Circuit-source repositories are linked through case attribution. Digital, openEMS and Palace dependencies nested inside the PDK are optional. See the [task guide](tasks.md#asset-rights) for source, license, and distribution requirements; retain licenses with each upstream and component. Do not put a complete checkout in Agent mounts or the common image.

```bash
git submodule update --init --depth 1 third_party/IHP-Open-PDK
git -C third_party/IHP-Open-PDK submodule update --init --depth 1 \
  ihp-sg13g2/libs.tech/klayout/python/pycell4klayout-api \
  ihp-sg13g2/libs.tech/klayout/python/pypreprocessor
git submodule status --recursive
```

To update an upstream, fetch it in the target submodule, choose an official commit, fix it at a detached checkout, synchronize nested dependencies, and then inspect `git diff --submodule=log` in the public repository. Validate affected environments and tasks before committing the reference; normal runs do not follow a remote branch automatically. Make PDK source fixes and run upstream regressions in that repository.

After moving the PDK pin, regenerate the support profile digests from the clean checkout and review the resulting diff before rebuilding bundles:

```bash
uv run --locked python -m benchmarking.refresh_support third_party/IHP-Open-PDK tasks/ihp-sg13g2/pdk.toml
```

The refresh refuses a checkout with uncommitted tracked changes and fails on any listed file missing upstream, so a stale or renamed selection surfaces at refresh time rather than during evaluation.

| Resource | Preparation and validation |
|---|---|
| PDK view | `benchmarking.environment` prepares primitives, callbacks, layer tables, rules, and licenses using the per-file digests in [sg13g2_view.json](../benchmarking/sg13g2_view.json); `--bundle` generates the Agent resource bundle |
| Tool support bundle | `benchmarking.prepare_support` follows the profiles in the [tasks/ihp-sg13g2/pdk.toml](../tasks/ihp-sg13g2/pdk.toml) manifest to prepare Magic, MOS models, and KLayout rules; compile models in a separate container |
| Frozen bundle | `manifest.json` binds files, sources, and the actual build environment; loading rejects modifications, missing or extra files, and symlinks, while backends consume byte snapshots. A reviewed PDK bundle is auto-detected by sessions; `/protocol/resources.json` publishes its container-local import paths and a preflight import command without adding task or reference files |

Keep originals byte-for-byte as supplied upstream and register framework-generated startup settings separately in the manifest. Preserve the license notices for components such as PSP models, PyCell, and pypreprocessor. The PDK view currently validates only basic MOS/tap primitives; importing a tool or device does not qualify every parameter or process rule.

<a id="freepdk45"></a>

### FreePDK45 resources and qualification

Five public cases are `qualified` through input consistency and reference evaluation. Their
references are evaluated at **1.0 V, 27 C**, using nominal predictive
FreePDK45 BSIM4 models and candidate-derived Magic RC. Every case ships a passing
reference, its source netlist and testbench, fixed `layout-v1` scoring, and
reference results with reproduction commands. These are standalone transistor-level tasks.

| Collection / case | Function | Coefficient | Area target / zero (um2) |
| --- | --- | --- | --- |
| [OpenRAM / cell_6t](../tasks/freepdk45/OpenRAM/cases/cell_6t/README.md) | Write, hold and nondestructive read | 3 | 1.4 / 2.8 |
| [OpenRAM / sense_amp](../tasks/freepdk45/OpenRAM/cases/sense_amp/README.md) | Clocked differential decision | 3 | 3.8 / 7.6 |
| [OpenRAM / write_driver](../tasks/freepdk45/OpenRAM/cases/write_driver/README.md) | Loaded complementary tri-state drive | 2 | 3.6 / 7.2 |
| [nangate45-pdk / NAND2_X1](../tasks/freepdk45/nangate45-pdk/cases/NAND2_X1/README.md) | Two-input NAND truth table and transitions | 2 | 1.7 / 3.4 |
| [nangate45-pdk / AOI21_X1](../tasks/freepdk45/nangate45-pdk/cases/AOI21_X1/README.md) | Compound AOI truth table and transitions | 2 | 2.1 / 4.2 |

Each problem is self-contained. Its configuration owns the exact devices, loads,
stimuli, observation times, bounds, dimensions and area anchors. References prove
feasibility; they are not scoring denominators or standard solver inputs.

#### Prepare resources

From a Git checkout at the repository root:

```bash
git submodule update --init --depth 1 \
  third_party/FreePDK45_for_KLayout third_party/FreePDK45 \
  third_party/nangate45-pdk
uv sync --locked --group eda
docker build --network host -t layout-bench-tools:local .
uv run --locked python -m benchmarking.prepare_support \
  third_party/FreePDK45_for_KLayout tasks/freepdk45/pdk.toml#klayout \
  build/support/freepdk45-klayout
uv run --locked python -m benchmarking.prepare_support \
  third_party/FreePDK45 tasks/freepdk45/pdk.toml#models \
  build/support/freepdk45-models
uv run --locked python -m benchmarking.prepare_support \
  third_party/nangate45-pdk tasks/freepdk45/pdk.toml#magic-vtg \
  build/support/freepdk45-magic-vtg
uv run --locked python -m benchmarking.prepare_support \
  third_party/nangate45-pdk tasks/freepdk45/pdk.toml#magic-vtl \
  build/support/freepdk45-magic-vtl
```

Reuse a verified existing image and support bundle instead of overwriting them.
The support commands create immutable snapshots in new directories. Distributed-reference regression uses the three evaluator checkouts above.
Circuit-source repositories are not needed to prepare or evaluate these cases.

Profiles in [pdk.toml](../tasks/freepdk45/pdk.toml) select their own source checkout and revision.
Model sources come from the Apache FreePDK45 1.4 publication with SVRF files
removed. The runtime bundles contain neither the full source libraries nor
reference GDS. All EDA operations use the shared tools image.

#### Physical and extraction scope

The KLayout profile enables all implemented DRC, manufacturing-grid and antenna
checks without waivers. The source deck explicitly lacks its different-potential
well-spacing check, so a pass is not complete manufacturing signoff. Strict LVS
flattens an isolated candidate copy with its labels, removes library-specific
`cheat` blocks and implicit/global rail joins, and compares models, W/L, named
ports and real well/tap connectivity. The upstream audit profile is separate and
retains the original library assumptions; it is not the task judge.

The functional footprint includes drawing layers 1/0 through 29/0, including all
ten routing metals and nine vias. The same layer set supplies the hard 100 by
100 um envelope and scored bounding-box area. Annotation and pin-purpose shapes
are excluded; the contract requires functional routing on drawing layers.

Magic imports the candidate on its exact DBU grid, filters electrical text to
poly/metal drawing layers and aliases case-insensitive SPICE port names. It
extracts resistances and capacitances from the GDS, with no schematic replacement.
Independent LVS selects the applicable VTG or VTL model class first. The native
RC topology is checked during qualification against the source after removing
capacitors and collapsing parasitic resistors. Simulation always uses the full,
unchanged extracted RC network.

The predictive extraction model uses:

- Nominal, unmodified VTG/VTL BSIM4 models at 27 C, with junction area/perimeter
  from layout. Diffusion sheet resistance is 5 ohm/square from model `rsh`.
- Poly/metal sheet and contact/via resistance from the
  [NCSU FreePDK45 metal-layer specification](https://eda.ncsu.edu/freepdk/freepdk45/).
  Poly is 7.8 ohm/square; M1 is 0.38, M2/M3 0.25, M4–M6 0.21,
  M7/M8 0.075, and M9/M10 0.03. Contacts are 8 ohm; vias use
  6, 5, 5, 3, 3, 3, 1, 1 and 0.5 ohm, respectively.
- Isolated-wire area and edge fits to the pinned original
  [ElCap PTF table](https://foss-eda-tools.googlesource.com/third_party/freepdk45/+/356e90646f5ef26ea09b1ed8ce4796871403a0c7/Cap_Tables/NCSU_FreePDK_45nm.ptf).
  Fits reproduce the width endpoints and have at most 5.44% error at the other
  published isolated-wire widths. This error describes those samples only.
- Same-plane coupling anchored to the table's minimum-width/minimum-spacing
  sample; wider spacings use Magic's native inverse-spacing approximation.
  Cross-plane overlap uses the published dielectric stack and relative
  permittivity 2.5, with Magic's shielding and native capacitance placement.
  Some coupling remains lumped at original nets; not every capacitance is
  distributed along a wire resistance.
- Lumped wells and substrate connections. Well/substrate sheet resistance,
  well-to-substrate capacitance, inductance, process variation and temperature
  coefficients are outside this nominal scope. The four terminal MOS junction
  model is retained. No substrate-noise or foundry field-solver claim is made.

The original Nangate Magic file's estimated parasitic table is replaced by these
reviewed coefficients. `lambda=2.5` expresses 25 nm in Magic's centimicron units;
confusing it with microns would corrupt MOS dimensions. The shared image fixes
Magic 8.3.678. Coefficient interpretation must be revalidated when changing the
extraction implementation or tool version.

#### Reference regression

The case READMEs provide the reference evaluation commands and measured results.
The shared regression discovers executable witnessed cases from public catalogs,
prepares resources through their declared profiles, and checks the witness against
its own acceptance conditions. It also rejects an empty candidate. It has no
circuit-name branches, geometry recipes or expected score table.

```bash
uv run --locked --group eda pytest tests/integration/test_public_references.py
```

Use `-k freepdk45` to select this PDK. Native reports, extracted netlists and
waveforms are generated in the test's temporary output directories. Direct
`main.py evaluate` commands in each README write them to a selected `build/runs/`
directory. This regression verifies ready-to-use references. Apply the
[case and shared validation rules](tasks.md#qualification) when changing a circuit,
judge or extraction model. Generic scoring, simulator error handling and analytical
RC behavior have their own framework tests.

#### Sources and distribution

The source collections retain their own licenses and notices. The three OpenRAM
cells retain their GPL source
obligations and separate PDK notices, and NAND2/AOI21 use the original Nangate
publication's Apache license and later Silvaco/Si2 NOTICE. Generated upstream
copyright headers remain intact. Source revisions and file hashes are recorded
in each case and collection catalog.

FreePDK45 models, open rule decks, the Magic integration and derived coefficient
records have separate reviewed provenance in the PDK manifest. SVRF/Calibre
materials are not copied into task inputs or prepared evaluator resources.
Qualification is limited to the published nominal conditions; it does not claim
PVT, mismatch, SRAM-array abutment, manufacturing signoff or formal admission.

## EDA Backend Contract

The backend extension interface is described in [architecture](architecture.md#extension-layers). `main.py characterize` performs an independent measurement and `main.py evaluate` re-evaluates a GDS. Tool bindings may be embedded in a schema-2 case as `[toolchain]`, following the [task configuration guide](tasks.md#evaluation-plan). `evaluate` and `run` use these bindings when `--toolchain` is omitted; `characterize` still requires an explicit toolchain configuration. A plan returns 0 when it passes, 1 when a check or specification fails, and 2 for a configuration or execution error. Output includes `report.json` and artifacts saved by digest. Characterization fixtures are not formal layout tasks.

### ngspice and Magic

ngspice writes an input role as `<role>.spice` and uses `deck.spice` as its entry point. The testbench declares analyses and measurements; `parameters.values` generates `parameters.spice`, `parameters.measurements` specifies names and units, and `parameters.exports` names declared artifacts. Exit 0 still requires a complete set of finite measurements. See the [RC](../tests/fixtures/characterization/rc.toml), [divider](../tests/fixtures/characterization/divider.toml), and [MOS post-layout](../tests/fixtures/sg13g2/switch.toml) characterization fixtures.

Magic takes the top cell and ordered `ports` from trusted configuration; check the port list against the authoritative netlist. Later jobs must consume the exported netlist as-is. `magic-capacitance-docker` retains its capacitance-only behavior and records `wire_resistance=false`. `magic-rc-docker` adds distributed resistance and capacitance, and can be bound to `layout.extract_rc`.


Magic import can be configured with `gds_readonly=false` when a technology must
rescale its native import grid to represent the candidate DBU exactly. This does
not permit writes to the submitted GDS: preprocessing and import still operate
on isolated copies. The default remains `true`. Optional `label_layers` is a
nonempty list of GDS layer/datatype pairs that may contain electrical text;
text on other layers is removed from the extraction copy without removing any
geometry. `case_insensitive_ports=true` aliases case variants to unique internal
names before extraction, matching SPICE's port-name semantics. The defaults
preserve all labels and use case-sensitive matching. Settings, alias mappings,
ignored-label counts and the geometric flattening check are archived. The
[FreePDK45 resources](#freepdk45) exercise these options and
publish their predictive model, coefficient provenance and extraction controls.

The RC adapter requires Magic 8.3.653 or newer. It uses a geometrically checked,
flattened extraction copy, keeps devices separate, and sets resistance selection,
minimum resistance, and delay thresholds to zero with network simplification
disabled. `capacitance_threshold_ff` controls capacitance omission; the comparator
uses zero. These are the explicit controls documented by the
[Magic extresist reference](https://opencircuitdesign.com/magic/commandref/extresist.html).
The archived upstream `extresist tolerance 1` setting is deprecated in the
installed Magic and is not used by this backend. Raw extraction, resistance,
topology, feedback, and port/geometry checks are retained with the result.

SG13G2 Magic extraction treats well/substrate ties as ideal connections;
it does not preserve the finite `ntap1`/`ptap1` resistance cards used by the
source simulator netlists. The pinned PDK's
[tap connectivity rules](../third_party/IHP-Open-PDK/ihp-sg13g2/libs.tech/klayout/tech/lvs/rule_decks/tap_connections.lvs)
document this interpretation for Magic and Netgen. Physical LVS can still
check explicit tap geometry. Cases using this RC boundary must disclose the
idealization and calibrate its effect on their declared nominal measurements.
It does not establish distributed well/substrate resistance or substrate-noise
accuracy.

The shared image builds Magic 8.3.678 with one driver-selection correction in
`ResProcessNode`: the W/L accumulator and maximum use floating point, matching
the device reader. Integer truncation otherwise skips unlabelled internal nets
whose MOS drivers all have W/L below one, even with zero extraction thresholds.
The [Dockerfile](../Dockerfile) applies the correction to the pinned source;
the [RC regression](../tests/integration/test_magic_rc.py) checks the analytical
resistance increment of a wire between two such devices. This changes tool
arithmetic, not PDK extraction rules.

The supported RC interface has one declared port per conductor. A native
topology check rejects multiple ports on one conductor: the installed Magic
can otherwise duplicate the resistance network or bypass it with an alias
resistor. This limitation produces an evaluation error. The
[RC integration checks](../tests/integration/test_magic_rc.py) validate a known
wire-resistance increment, its effect on transistor delay, a fixture threshold
rejection, and invalid/unsupported inputs. Case-specific extraction warnings,
models, and calibration still require review; the comparator's current status
and commands are in its [case README](../tasks/ihp-sg13g2/IHP-AnalogAcademy/cases/comparator/README.md).

### KLayout Physical Checks

`klayout-docker` implements the same Backend interface, with `check` selecting `artifact`, `drc`, or `lvs`. A task job supplies only `layout` and `task`; LVS additionally supplies the authoritative `netlist`. For standalone debugging, use `parameters.top_cell`, `max_bytes`, and the LVS `subcircuit`; when `task` is supplied, these must not conflict with it. Checks do not publish an extracted netlist for post-layout simulation. The LVS extraction result is diagnostic evidence; a separate PEX job re-extracts from the same GDS for post-layout simulation.

The artifact check uses KLayout's native reader to validate the GDSII stream, the published file-size limit, the specified top cell, non-empty geometry, and unresolved hierarchy references. DRC/LVS configuration is a JSON file in the frozen support bundle that specifies `deck`, fixed `variables`, and explanatory `scope`; DRC also declares `required_categories`. The optional DRC `additional_decks` list contains `{deck, required_categories}` entries sharing the same variables. Every deck runs in its own KLayout process and must complete and produce its required categories. The gate sums their counts and fails if any deck fails; an execution or report error takes precedence. `report.db` and `report-1.db` (and corresponding logs/completion markers) remain separate native evidence, with per-deck results in `result.json`. Required categories guard against skipping rule groups but are not a complete rule list. Exact case-local `parameters.waivers` are available when declared by a reviewed task. For LVS, native cross-reference data must confirm that comparison occurred, the reference circuit is non-empty, and the requested circuit participated. The `ignore_top_ports_mismatch` variable controls whether the upstream runset and adapter add named-port checks after comparison. The reader follows KLayout's [LVS database](https://www.klayout.de/doc/code/class_LayoutVsSchematic.html) and [comparison result](https://www.klayout.de/doc/code/class_NetlistCrossReference.html) documentation. A missing report, skipped run, crash, or timeout is `error`; a completed check with unwaived violations is `failed`.

### IHP physical-check profiles

Prepare support from the `klayout` profile in `tasks/ihp-sg13g2/pdk.toml`.
Frozen bundles are not updated in place; prepare a new bundle when the manifest
changes. Cases select their check profiles through `[toolchain]`.

| Profile | Scope |
|---|---|
| `drc-upstream.json` | Pinned PDK GUI defaults: main plus extra `sg13g2_maximal.drc`, deep mode, density and antenna off. |
| `lvs-upstream.json` | Pinned PDK GUI defaults: explicit taps, native simplification and strict named ports. |

Evaluate the maintained circuit and candidate using the case's declared task
plan. See the [evaluation command](tasks.md#evaluation) and each case README
for reference results and reproduction instructions.

<a id="geometry"></a>

### Geometry and Port Correspondence

`klayout-geometry-docker` interprets schema 1 of the geometry constraints, supplied as a JSON snapshot from either `[task.constraints]` or a declared constraints file: `bbox_max` names the functional layers that contribute to the outline and sets maximum width and height; `named_metal_ports` names each port, its drawing/pin/text layers, logical connection layer, and minimum square side that can be contacted; `functional_bbox_area` measures area using the layer set from an outline constraint. The top cell must contain exactly one label with each required name. Its center square must lie completely in the intersection of the pin, drawing, and correctly extracted network regions. Adapters extend the set of constraint kinds; the generic plan executor does not interpret process layers or geometry semantics.

LVS can export a native `klayout-lvs` database and a JSON binding. The binding records the candidate GDS, database digest, top cell, and logical-layer mapping. After validating the binding, the geometry adapter uses the native [LayoutVsSchematic](https://www.klayout.de/doc/code/class_LayoutVsSchematic.html), [NetlistCrossReference](https://www.klayout.de/doc/code/class_NetlistCrossReference.html), and [LayoutToNetlist](https://www.klayout.de/doc/code/class_LayoutToNetlist.html) APIs for network correspondence and geometry. Process support bundles declare deck-layer variables; the adapter reads the names actually registered by the run instead of fixing runtime indices such as `l10`, and it does not modify upstream rules.

Magic's SPICE export drops the `!` from `!CONTROL`, causing a collision with `CONTROL`. The extraction adapter first uses KLayout on an isolated GDS copy to give unsafe interface names unique aliases, preserves the original candidate and mapping evidence, and then uses the native SPICE reader to check the count, names, and order of exported ports. It does not rewrite the original task netlist; simulation connects through the declared port order.

The AnalogAcademy LVS profile also accepts ngspice model calls for
`sg13_lv_nmos`, `sg13_lv_pmos`, `cap_cmim`, `ntap1` and `ptap1`. Its
`sg13g2-model-calls.lvs` entry point is generated from the KLayout support
manifest and includes the unchanged upstream runset. A KLayout
[reader delegate](https://www.klayout.de/doc-qt5/code/class_NetlistSpiceReaderDelegate.html)
maps these `X` calls to the native PDK device handlers, preserving their terminal
mapping, parameter units, simplification and comparison rules. Other `X` calls
retain normal hierarchy handling, and legacy CDL primitive cards retain their
native interpretation. Use circuit-local `.param` definitions and compact
expressions on model calls; expression parsing and parameter scoping remain
those of the pinned native reader. This is an input adapter, with no rule
waivers or new device models. The full OTA uses one authoritative circuit for LVS and direct
pre-layout simulation: tap `a`/`p` geometry and derived `r` share the same
parameter definitions, and MOS finger/multiplicity parameters reach ngspice
without LVS simplification. Candidate scoring still simulates only GDS-derived
PEX. Other source dialects require an explicitly validated adaptation.

### HBT core simulation support

[The HBT model profile](../tasks/ihp-sg13g2/pdk.toml) prepares the pinned
HBT, resistor and capacitor include closure, using native ngspice VBIC and
OpenVAF-compiled R3_CMC and MoM models. It retains the R3_CMC license and
NOTICE with the IHP adaptation. No compact-model source is patched.
The `sg13g2-hbt-rc-docker` backend combines candidate-only KLayout native
HBT extraction with Magic distributed interconnect R/C. Its `klayout_support`
and `magic_support` settings use separately reviewed bundles; declare their
profiles through `support_profiles` as shown above. Physical LVS remains a
separate gate against the maintained circuit, including the named interface.

For a declared ideal-body compact-model boundary, the optional boolean
`disable_tap_extraction = true` setting enables the pinned KLayout PDK's
standard tap-connection mode in the candidate extraction only. The default is
`false`. The selected value is recorded in backend identity and the frozen
extraction configuration; it does not change the separate physical LVS
profile. A case using this mode must retain physical tap checks, disclose the
omitted well/substrate/tap resistance and calibrate finite-tap versus ideal-body
behavior under its declared testbench and models.

The adapter preserves extracted HBT multiplicity and validates the drawn
geometry against the compact-device interface. Fixed drawn emitter dimensions
are not passed as effective model dimensions. It checks passive geometry and
connectivity across KLayout, Magic topology and the final RC output, and retains
Magic's external R/C network. Ambiguous mappings, unsupported cards or missing
connectivity evidence fail extraction. An otherwise unreferenced HBT terminal
may be assigned to its candidate-proven port at the compact-device boundary;
this does not replace an external wire or bypass attached parasitics. The
mapping and original extraction outputs are retained as evaluation evidence.

The [design 1 functional regression](../tests/integration/test_tia130_postlayout.py)
checks the same nominal AC/DC deck against the maintained source and extracted
candidate, independently reads waveform voltages and currents, and exercises
port rejection and repeated/translated candidates. This is a distributed-RC
compact-model simulation boundary. RF/EM behavior, noise and statistical
corners require their own declared extraction and validation scope; see the
[case requirements](../tasks/ihp-sg13g2/TO_Apr2025/cases/DC_to_130_GHz_TIA.design_1/problem.md#physical-requirements).

### Qucs-S and Qucsator

The unified image installs Qucs-S 26.1.1 from the pinned Ubuntu 24.04 amd64 OBS package and builds the official Qucsator 0.0.20 core from commit `e995f9acc71a8c7319286944e4a1692318b9dd80`. The image therefore provides `qucs-s`, `qucsator`, `qucsator_rf`, and `qucsconv` alongside Ngspice. Qucs-S is used headlessly as the `.sch` parser/netlister (`QT_QPA_PLATFORM=offscreen`); the simulator remains an explicit backend.

Xyce is not silently substituted by Qucsator. The upstream project does not publish an Ubuntu-compatible open-source binary; a reproducible Xyce backend needs its own source build (including Trilinos) and is outside this image until that build is pinned and validated. Current IHP MPA schematics that declare Xyce analyses must consequently report the backend as unavailable rather than claiming a completed simulation.

<a id="manual-tools"></a>

## Unified tool image

The repository publishes and tests one image: `layout-bench-tools:local`. It contains the complete EDA runtime used by preparation, simulation, extraction, and judging, including Qucs-S, Qucsator/QucsatorRF, Ngspice, Xschem, Magic, OpenVAF, and KLayout. Harnesses remain an external seam and are not baked into the image. Each operation still runs in an isolated container invocation, but all EDA invocations resolve the same frozen image ID.

Build and check that image directly:

```bash
uv run --locked python scripts/public_preview.py build --image layout-bench-tools:local
bash tests/integration/test_toolchain.sh
```

Role-specific image tags are not part of the supported workflow. This keeps tool versions and backend availability consistent across preparation, solving, and evaluation. Prepare the shared support paths with the commands below:

```bash
uv run --locked python -m benchmarking.environment third_party/IHP-Open-PDK build/support/pdk-view
uv run --locked python -m benchmarking.prepare_support third_party/IHP-Open-PDK tasks/ihp-sg13g2/pdk.toml#magic build/support/sg13g2-magic
uv run --locked python -m benchmarking.prepare_support third_party/IHP-Open-PDK tasks/ihp-sg13g2/pdk.toml#mos-models build/support/sg13g2-mos-models
uv run --locked python -m benchmarking.prepare_support third_party/IHP-Open-PDK tasks/ihp-sg13g2/pdk.toml#klayout build/support/sg13g2-klayout
```

Resolve relative `settings.support` paths from the backend's launch working directory, while paths in a plan are relative to the plan file; keep these namespaces distinct. New configurations may use absolute support paths. The [integration tests](../tests/integration) maintain complete fixture invocations; see [CONTRIBUTING](../CONTRIBUTING.md#verification) for how to select and run them.
