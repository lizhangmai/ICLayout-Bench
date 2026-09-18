# Tool Environments, Resource Preparation, and EDA Adapters

For a local reference check, `python -m benchmarking.engine.preview quickstart` prepares and evaluates a public witness. It builds one `iclayout-bench-tools:local` image unless `--skip-build` selects an existing compatible image. This page covers stepwise preparation, troubleshooting, and changes to the tool environment. Use a new output directory for each run. Repository-local generated outputs use `build/`: benchmark runs go under `build/runs/`, independently prepared support bundles under `build/support/`, and Python distributions under `build/dist/`.

All preparation, `tests/integration/` and acceptance commands below run from the
Public checkout. The installed Public package contains the shared evaluator;
Private is not needed for public development tasks.

## Stepwise Preparation and Reuse

The host uses Linux x86-64, Git, uv, Python 3.12+, and accessible Docker/BuildKit. Versions are maintained by the [Dockerfile](../Dockerfile), [pyproject.toml](../pyproject.toml), and [uv.lock](../uv.lock); framework development needs only `uv sync --locked`.

| `python -m benchmarking.engine.preview` subcommand | When to use it |
|---|---|
| `doctor` | Check the host and Docker before downloading; does not call a model |
| `list` | List executable public witnesses across every process, with unambiguous case keys |
| `fetch --case <key>` / `fetch --all` | Fetch pinned PDK releases or initialize declared submodules for one case or all executable witnesses |
| `build` | Build only the unified image; accepts `--image`, defaulting to `iclayout-bench-tools:local` |
| `prepare --case <key> --output <new-directory>` | Fetch required sources and prepare the selected case's evaluator resources; bind tools to the actual image ID |
| `run --prepared <prepared-directory> --output <new-directory>` | Evaluate the prepared case witness through its complete declared plan and save raw evidence |

`quickstart` chains host checks, image build, PDK initialization, preparation, and reference evaluation, and writes `prepared/` and `run/`. It defaults to the IHP AnalogAcademy comparator. `quickstart` and `prepare` discover executable post-layout witnesses from all public process catalogs; `list` prints their `--case` keys. Unique directory names and case IDs are accepted; collisions use `process/collection/case`. The historical `comparator` alias retains its original IHP meaning. The script uses each case's `[toolchain]`, constraints, evaluation plan, and published witness. Preparation binds image/resource paths and shared inputs to local snapshots in a host-side copy at `prepared/case/case.toml`. The solver loader still materializes only declared inputs, excluding the copied reference and source README. Models and composite extraction resources are selected by explicit backend metadata rather than inferred from a circuit's name or source collection.

All evaluator resources are prepared from the selected process's `pdk.toml`. A profile-level `source` overrides the manifest source. Git sources resolve against `.gitmodules`; `kind = "ciel"` sources resolve to a verified fixed-version cache. Models, physical rules and extraction technology follow their declared source. Existing `build/support` directories are not read. Those paths in source case configurations support the manual workflow below; public preparation replaces them with newly generated resource paths. Use the resulting `prepared/case/case.toml` with `python -m benchmarking.engine.cli evaluate`; participant experiments use `python -m benchmarking.run --prepared prepared --config experiment.toml`.

GF180MCU D and IHP SG13G2 use pinned prebuilt distributions downloaded by
[ciel](https://github.com/fossi-foundation/ciel), installed with the Public package.
FreePDK45 uses the pinned
[rjordans community installation](https://github.com/rjordans/freepdk45-open-pdks).
GF180 and FreePDK45 expose `/resources/pdks/<process>/libs.tech` and process-owned `libs.ref`
where applicable. IHP retains its official installation layout.

Set `ICLAYOUT_BENCH_CACHE_DIR` to relocate the disposable cache. By default it is
`$XDG_CACHE_HOME/iclayout-bench`, or `~/.cache/iclayout-bench` when XDG_CACHE_HOME
is unset. PDK downloads live under `pdks/`; retained experiment results and
prepared evaluation snapshots stay in their explicitly selected output directories.
For example:

```bash
export ICLAYOUT_BENCH_CACHE_DIR=/path/to/shared-cache
python -m benchmarking.engine.preview fetch --case ota_5t
python -m benchmarking.engine.preview prepare --case ota_5t \
  --image iclayout-bench-tools:local --output build/runs/ota/prepared
```

Each ciel `[source]` declares `kind = "ciel"`, the family, full version commit,
explicit library names and the reviewed installation `sha256`. Preparation uses
ciel's `fetch` API against its official release service, requesting common tool
files and the primitive library. It does not enable a global current version,
read `PDK_ROOT` to select one, or build open-pdks locally. No GF180/open-pdks
source submodules are required. The downloaded family contains multiple variants;
the Agent selection exports only variant D and excludes example circuits.

The cache uses ciel's version directory under `pdks/ciel/<family>/versions/<commit>`.
A per-version lock serializes downloads; staging directories are published only
after verification, so an interrupted download can be retried. Every reuse checks
the complete installed file set and works offline. The tree checksum is SHA-256
of a compact, key-sorted JSON object mapping relative POSIX file paths to their
SHA-256 digests. Extra, missing, modified or linked files fail verification.
Remove only the affected disposable version directory and fetch again to repair
corruption; copying a newer release into an older version directory is invalid.

To update a ciel PDK, select the latest available prebuilt release with
`ciel ls-remote --pdk-family gf180mcu` or `--pdk-family ihp-sg13g2`, inspect its
contents in a separate download root, then update the version, installation
checksum and file selections in the corresponding `tasks/<process>/pdk.toml`.
Use `python -m benchmarking.engine.refresh_support tasks/<process>/pdk.toml` to refresh
profile file hashes from the verified cache. Updates adopt that release's models
and rules and requalify affected cases; normal preparation never follows latest
implicitly or retains a second legacy rule stack.

Support files may declare ordered `replace` entries with `old` and `new` text.
The original file digest is checked first, and each replacement must match exactly
once. This records small integration corrections without embedding copied technology
files in the manifest. Preparation evidence binds both source and modifications.
Shared manifest `notices` contain generated license/attribution files included in
every support profile. They preserve component terms omitted by the prebuilt
archive. Review upstream changes and rerun affected cases before accepting new digests.

All public processes additionally create `prepared/agent-resources` from their
declarative Agent PDK configuration. Reference evaluation needs no model account;
an Agent run consumes this bundle using `--resources`. See the
[resource contract](#agent-pdk-resources) below.

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
image = "iclayout-bench-tools:local"
support = "build/support/example-hbt-models"
```

The directory in this example is created by resource preparation; it is not
shipped with the repository. Use `analog-models` for the reviewed CMOS/MIM/tap
model closure. Use `analog-res-models` when CMOS/MIM circuitry also needs
physical poly resistance: it adds the pinned R3_CMC Verilog-A files, component
notices and compiled OSDI startup to the existing model closure. The
[series-compensated OTA](../tasks/ihp-sg13g2/analog-db/cases/amp_024_smcnr/README.md)
qualifies `rhigh` geometry, connectivity and source/candidate-RC behavior at its
specified conditions. The presence of other resistor models is not blanket
physical qualification. Existing `analog-models` and `hbt-models` profiles are
unchanged. A composite backend can declare
`support_profiles = { klayout_support = "klayout", magic_support = "magic" }`.
The metadata is validated by the host toolchain loader and never passed to a
backend constructor or delivered as a solver input. Legacy KLayout and Magic
backends with a single support setting retain their unambiguous type-based
preparation defaults. Direct evaluation may still use manually prepared bundles.

`--skip-build` reuses the existing image and still binds its actual ID. Existing PDK files are reused and checked against reviewed digests; output directories must be new. Quick start makes no model calls and does not establish new qualification conditions. Case-specific tests cover calibration and rejection behavior; see [CONTRIBUTING](../CONTRIBUTING.md#verification).

The unified image contains KLayout, Python, ngspice, Qucs-S/Qucsator, Magic, OpenVAF, and Xschem. Harness runtimes are deliberately outside this image: a harness supplies its executable and reviewed files, or selects an image that provides them, while the benchmark only requires the common session protocol. Each operation still starts an isolated container, but every EDA operation resolves the same image ID. The image contains no task, PDK, harness source, or credentials; `.dockerignore` allows only dependency declarations, lock files and the pinned native-tool build script. Install the KLayout CLI and Python API from separate packages and have tool checks confirm that their versions agree. The build does not depend on a local KLayout source tree or private cache.

The build needs access to system packages, tool release sites, and the Python index, and verifies downloaded artifacts against fixed digests. The distribution still resolves base system packages, so the final image identity binds the result; the Dockerfile alone cannot guarantee a byte-for-byte rebuild. To use a host loopback proxy:

```bash
python -m benchmarking.engine.preview build --network host
```

The script preserves existing `HTTP_PROXY`, `HTTPS_PROXY`, and `NO_PROXY` variables. Proxy settings affect the build only; the harness controls networking for run containers.

<a id="image-development"></a>

## Image development: reuse first

The public [Dockerfile](../Dockerfile) is the clean-checkout build recipe.
Development does not require executing it on every edit. Choose the smallest
environment change that the work requires:

| Change | Development action |
|---|---|
| Framework code, cases, PDK sources, resource mounts or environment settings | Reuse a compatible image; prepare updated resources and run affected checks |
| Container Python dependencies | Update `pyproject.toml` and `uv.lock`, then use the thin derived build below |
| Native EDA tools or system libraries | Update the public Dockerfile; default to a pinned, thin derived build, followed by tool and affected container/EDA checks |
| No compatible image can be reused or derived, base-system change, or explicitly requested release reproduction | Build the public Dockerfile and run the applicable verification matrix |

A full build is reserved for the last row; state the applicable reason before
starting it. Passing the affected checks with a compatible existing or derived
image completes development validation. The absence of a full rebuild is not a
development validation gap. Updating a dependency, PDK or Dockerfile alone does
not trigger a full build.

Inspect available images with `docker image ls iclayout-bench-tools` and select one
whose tools satisfy the change. A familiar tag alone does not prove compatibility.
For example, after building the default image once:

```bash
python -m benchmarking.engine.preview quickstart --skip-build \
  --image iclayout-bench-tools:local --case cell_6t --output build/runs/dev-cell
```

`prepare --image ...` and `run --prepared ...` also avoid image construction.
Output directories in these examples are generated by the reader's commands.
Preparation freezes the actual image ID: changing a tag later does not update an
already prepared case. Prepare into a new directory when changing the image;
keep the Agent runtime compatible with the declared resources and toolchain.
A participant may derive its solver image separately; case preparation must use
the operator's trusted evaluation image, not an unreviewed participant image.

For Python-only container dependency changes, [Dockerfile.dev](../Dockerfile.dev)
inherits existing native tools and synchronizes only the locked `eda` group:

```bash
docker image inspect --format '{{.Id}}' iclayout-bench-tools:local
docker build -f Dockerfile.dev --build-arg BASE_IMAGE=iclayout-bench-tools:local \
  --build-arg HTTP_PROXY --build-arg HTTPS_PROXY --build-arg NO_PROXY \
  -t iclayout-bench-tools:dev .
```

Use a compatible ICLayout-Bench tools base providing uv, the configured Python
environment and the non-root `ubuntu` user. The recipe inherits the base's uv and
native tools; it does not update them. Add `--network host` to the build for a
host loopback proxy. Keep the base tag intact and use a separate development tag.
Record the inspected base ID with local verification results; `BASE_IMAGE` takes
a local tag or a registry reference with digest, not a bare local image ID.
This build uses the same dependency-only context; no task, PDK or credential is
added. Run affected EDA/PDK usage checks from [CONTRIBUTING](../CONTRIBUTING.md#verification)
as well when those dependencies change.

<a id="ngspice-45"></a>

For the pinned ngspice native-tool upgrade, use the dedicated thin overlay:

```bash
docker build -f Dockerfile.ngspice --build-arg BASE_IMAGE=iclayout-bench-tools:local \
  --build-arg HTTP_PROXY --build-arg HTTPS_PROXY --build-arg NO_PROXY \
  -t iclayout-bench-tools:ngspice45 .
docker run --rm iclayout-bench-tools:ngspice45 ngspice --version
```

[`scripts/build_ngspice.sh`](../scripts/build_ngspice.sh) pins the source commit
and archive digest and is shared by the overlay and release Dockerfile. It
builds XSPICE, OSDI and KLU support. `/opt/ngspice/bin` takes precedence over
the distribution executable that may remain installed for GUI dependencies.
Select this image explicitly for preparation and rerun affected simulations;
an existing prepared case retains its earlier image identity.

An image is immutable; edits inside a disposable container affect only that
container. An experimental `docker commit` snapshot is local debugging state,
not the published build recipe or release evidence. Keep such containers free
of credentials and task answers. Record dependency/tool changes in the public
recipe/lock alongside the derived build so the maintained recipe remains usable
without a maintainer's development image. When release reproduction is explicitly
requested, validate that public recipe from a clean checkout and report that
result separately from development validation.

The public Dockerfile installs Python dependencies after native EDA compilation,
so later lockfile edits can reuse those native layers. The first build after a
layer-layout change may still invalidate old caches; defer it to the appropriate
reproduction check instead of forcing a full build during unrelated iteration.
Normal builds use the cache; cache-disabled builds are for an explicit cache or
clean-build investigation. Report whether checks used an existing image, a
derived image, or the public recipe; these establish different evidence.

<a id="preview-troubleshooting"></a>

## Startup Troubleshooting

| Symptom | Handling |
|---|---|
| Docker command is missing or cannot reach the daemon | Install/start Docker first and ensure the current user can run `docker version`; `doctor` checks this before downloading and preparing |
| Native ARM, macOS, or Windows environment | Use a Linux x86-64 host; the current tool image is fixed to amd64 and other platforms are unvalidated |
| `PDK missing` or a pinned source file is absent | Run `python -m benchmarking.engine.preview fetch --all`; inspect the selected release and cache integrity if a digest differs. Keep hash verification enabled. |
| An Agent PDK source or required nested dependency is non-empty but has no Git metadata | Preserve the existing archive elsewhere, then rerun `fetch --case <key>` to initialize the pinned Git checkout; full source snapshots cannot authenticate an unversioned archive from a few marker files |
| `No such image` or image validation fails during preparation | Run `quickstart` or `build`; when naming an image manually, pass `--image` to `prepare` |
| A `build/...` support bundle is missing | Complete `prepare` first. Use the resulting `prepared/case/case.toml`, whose embedded bindings point to the prepared bundles |
| Output directory already exists | Choose a new `--output` path; logs produced by failed steps remain in the old directory for diagnosis |
| Build download fails | Check connectivity to Ubuntu, the Python package index, and tool release sites; downloads require matching digests. With a host loopback proxy, add `--network host` to `quickstart` or `build` and preserve `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY`; see [stepwise preparation and reuse](#stepwise-preparation-and-reuse) for other network setup |
| A real model lacks a key or cannot be reached | Validate the environment with the no-key public flow first, then configure your endpoint, model, and host key variable using [participant configuration and observation](running.md#observation); public CI does not call a paid model |

<a id="external-sources"></a>

## Upstream and Process Resources

FreePDK45's community installation is the remaining source submodule, declared
in [.gitmodules](../.gitmodules) and fixed by Git. GF180 and IHP use ciel releases
selected in their process manifests. IHP downloads only the primitive library
and shared tool files; Agent resources select SG13G2 tool/model/PCell files and
omit example/test circuits, digital libraries and unrelated process variants.
Circuit-source repositories remain linked through case attribution. See the
[task guide](tasks.md#asset-rights) for source and distribution requirements.
Preserve upstream notices. The common image contains tools, not PDK sources;
standard Agent mounts exclude the benchmark repository and reference answers.

<a id="agent-pdk-resources"></a>

### Agent PDK resources

`python -m benchmarking.engine.preview prepare` uses `benchmarking.engine.pdk_resources` for every process.
The normal session mount remains `/resources`, backed by immutable byte
snapshots rather than live host directories. The prepared bundle contains:

- `pdks/<source>/`: selected files from the pinned source or verified installation,
  including licenses and declared nested dependencies;
- `support/<profile>/`: verified/compiled process resources, separate from the
  evaluator's copies. Framework-generated paths are relocated to this mount;
  any explicit technology adaptations remain recorded in the preparation manifest;
- `pdk-environment.json`: process identity, source versions, public environment
  settings and usage-check argument lists. Sessions publish it through
  `/protocol/resources.json` and merge its environment automatically.

The bundle also retains original support preparation manifests, including model
compiler identities; the outer manifest hashes the actual relocated bytes.
Full source bundles are larger than the old minimal PCell view. Reuse a prepared
Agent bundle across cases of the same process instead of preparing one per run.

Untracked and ignored files, Git metadata and undeclared optional submodules
are excluded. Preparation rejects changed or missing tracked content and wrong
commits. Internal tracked symlinks are materialized as ordinary files; escaping,
missing and cyclic targets fail. A complete Git checkout is required for this
source-snapshot workflow, including declared nested dependencies. The SG13G2
allowlisted `benchmarking.engine.environment` view used by device checks reads
its installation from the same `pdk.toml` ciel declaration.

Every process uses `ICLAYOUT_BENCH_PDK`, `PDK_ROOT` and `PDK_PATH`; the namespaced
process identifier avoids conflicting with tool-owned settings such as gdsfactory's
`PDK` module selector. Tool-specific settings such as
`PYTHONPATH` and `KLAYOUT_PATH` are declared only where needed. Explicit Agent
Python/KLayout search paths are appended; conflicting fixed settings are rejected.
The PDK mounts are read-only and the Agent stays non-root and offline. Write
generated layouts, simulator decks and tool caches under `/workspace` or `/tmp`.
For ngspice, copy the selected support profile's `.spiceinit` into the working
directory before invoking the simulator; it loads compiled models where needed.

To add a process, add an `[agent]` table to its `pdk.toml` with `schema_version = 1`,
`id`, `sources`, `environment`, `checks`, and optional `support_profiles`.
Each source declares a `.gitmodules` `checkout`, optional `include` and `exclude`
path prefixes (default: all tracked files, excluding none), and optional
`submodules` paths. Optional `path` strips a source-directory prefix so an upstream
installation can mount directly at its PDK root. `installation = true` selects the
manifest source's verified ciel installation and replaces `checkout`; it requires
an explicit `include` selection. Filters
select paths in that source repository or installation;
explicitly declared nested dependencies are exported in full. Each support
profile names an existing evaluator preparation profile. `checks` is a nonempty
list of executable argument lists, run inside the Agent container, not on the
host. Add tool dependencies to the locked `eda` group when required. No runner
process branch or case-specific resource wrapper is needed.

Review the *contents*, not just a repository's name. The FreePDK45 community
installation includes finished standard cells, memory macros and KLayout examples;
its Agent selection exports only technology/rules/models and notices. GF180 exports
primitive devices and tool support while excluding DRC/LVS test layouts and Xschem
test circuits. Git metadata and the builder itself are not Agent resources. Source
selections, exclusions and installed bundle identities are recorded in provenance.

After `fetch --all` and selecting a compatible image, verify the actual Agent containers:

```bash
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local python -m pytest \
  tests/integration/test_session.py -k declared_pdks
```

This checks read-only isolation, SG13G2/GF180 MOS PCell generation, FreePDK45
technology loading, and single-device ngspice operating points for all three
processes. GF180 PCells use the image's locked `gdsfactory` dependency. These
are resource-usage checks, not proof that an Agent solves a benchmark case or
that every upstream device/parameter has been qualified.

GF180 and IHP updates select a published ciel version, its explicit library set,
and a reviewed installation checksum. Inspect changes in models, rules and PCells,
refresh support/view file digests, and validate all affected cases before committing.
Normal runs use the fixed release; they do not follow the latest release automatically.
For FreePDK45, update the community submodule to a reviewed detached commit.

```bash
python -m benchmarking.engine.refresh_support tasks/ihp-sg13g2/pdk.toml
```

The refresh verifies the cached installation and fails if a selected file is absent.
The small SG13G2 PCell view has its own reviewed per-file manifest, which must be
updated and checked against the same installation when its selected files change.

| Resource | Preparation and validation |
|---|---|
| PDK view | `benchmarking.engine.environment` prepares primitives, callbacks, layer tables, rules, and licenses using the per-file digests in [sg13g2_view.json](architecture.md#ownership); `--bundle` generates the Agent resource bundle |
| Tool support bundle | `benchmarking.engine.prepare_support` follows the profiles in the [tasks/ihp-sg13g2/pdk.toml](../tasks/ihp-sg13g2/pdk.toml) manifest to prepare Magic, MOS models, and KLayout rules; compile models in a separate container |
| Frozen bundle | `manifest.json` binds files, sources, and the actual build environment; loading rejects modifications, missing or extra files, and symlinks, while backends consume byte snapshots. A reviewed PDK bundle is auto-detected by sessions; `/protocol/resources.json` publishes its container-local import paths and a preflight import command without adding task or reference files |

Keep originals byte-for-byte as supplied upstream and register framework-generated startup settings separately in the manifest. Preserve the license notices for components such as PSP models, PyCell, and pypreprocessor. The PDK view currently validates only basic MOS/tap primitives; importing a tool or device does not qualify every parameter or process rule.

<a id="gf180"></a>

### GF180 resources and qualification

Twenty-two GF180MCU D cases are **qualified**, each with a passing reference layout,
a complete candidate-derived RC evaluation, frozen `layout-v2` scoring and
source/post-layout results. All use typical primitive models with statistical
variation disabled.
Temperature is **27 C** except the temperature cores' explicit **-20 to 100 C**
sweep. The externally biased LDO runs at **2.2, 2.7 and 3.3 V**; the cascode gain stage, folded
OTA and temperature cores use **2.7, 3.0 and 3.3 V**. The buffered-reference LDO uses **3.0 and 3.3 V**. The folded-cascode LDO uses **2.0 and 2.1 V**, and the feedforward-compensated PMOS LDO uses **1.8 and 1.9 V**; both add an explicit ramp-startup experiment. Tan CLIA uses **1.8 V**
with its authored 3.3 V MOS binding. Other cases use **3.3 V**.

| Collection | Circuit | Coefficient | Area reference (um2) |
| --- | --- | --- | --- |
| [Jianxun OTA](../tasks/gf180mcuD/Jianxun-OTA/README.md) | OTA with bias and dummies | 4 | 510.1 |
| [R-2R DAC](../tasks/gf180mcuD/gf-r2r-dac/README.md) | Eight-bit resistor ladder | 4 | 8727.76 |
| [Quadrature VCO](../tasks/gf180mcuD/tt_tnt_gf_vco/README.md) | Oscillator and buffers | 8 | 907.08 |
| [Voidwalkers](../tasks/gf180mcuD/voidwalkers-scandff/README.md) | Scan DFF with active-low reset | 5 | 175.5775 |
| [Chipathon2023 ADC](../tasks/gf180mcuD/Chipathon2023_ADC/README.md) | Dynamic comparator | 6 | 301.49 |
| [2AMLogic SAR ADC](../tasks/gf180mcuD/2AMLogic-sar-adc/README.md) | Dummy-compensated track switch | 4 | 702.46 |
| [analog-db LDO](../tasks/gf180mcuD/analog-db/README.md) | Externally biased PMOS regulator core | 7 | 7597.32 |
| [analog-db gain stage](../tasks/gf180mcuD/analog-db/cases/gs_001_cascode_cs/README.md) | Self-Biased Cascode Common-Source Gain Stage | 4 | 394.4 |
| [analog-db differential pair](../tasks/gf180mcuD/analog-db/cases/dp_001_resistive_load/README.md) | Resistively Loaded Differential Pair | 4 | 925.98 |
| [analog-db temperature core](../tasks/gf180mcuD/analog-db/cases/tsn_003_ptat_4t_xcoupled/README.md) | Four-Transistor Positive-Temperature-Slope Core | 3 | 168.38 |
| [analog-db folded OTA](../tasks/gf180mcuD/analog-db/cases/amp_004_folded_cascode/README.md) | Externally Biased PMOS-Input Folded-Cascode OTA | 5 | 5150.02 |
| [analog-db comparator](../tasks/gf180mcuD/analog-db/cases/cmp_001_hyst_diffpair/README.md) | Resistive-Feedback Hysteretic Comparator | 5 | 8386.58 |
| [analog-db telescopic amplifier](../tasks/gf180mcuD/analog-db/cases/amp_018_telescopic_cascode/README.md) | Tail-referenced cascode bias and loaded AC | 5 | 544.15 |
| [analog-db CMFB](../tasks/gf180mcuD/analog-db/cases/cmfb_003_5t_nmos_input/README.md) | Segmented 5 Mohm sensing and external-plant recovery | 6 | 122380.96 |
| [analog-db isolated-body PTAT](../tasks/gf180mcuD/analog-db/cases/tsn_002_ptat_classic/README.md) | Self-starting resistor-degenerated temperature core | 6 | 529.13 |
| [analog-db Self-Biased LDO Error Amplifier](../tasks/gf180mcuD/analog-db/cases/amp_032_ti_ldo_error_selfbias/README.md) | Nominal source-paired evaluation; see scope and limitations | 6 | 19112.5 |
| [analog-db Self-Biased LDO Reference Amplifier](../tasks/gf180mcuD/analog-db/cases/amp_033_ti_ldo_ref_selfbias/README.md) | Nominal source-paired evaluation; see scope and limitations | 6 | 6223.21 |
| [analog-db Buffered-Reference LDO](../tasks/gf180mcuD/analog-db/cases/ldo_005_buffered_ref/README.md) | Nominal source-paired evaluation; see scope and limitations | 7 | 29565.2 |
| [analog-db StrongARM Dynamic Comparator](../tasks/gf180mcuD/analog-db/cases/cmp_002_strongarm/README.md) | Nominal source-paired evaluation; see scope and limitations | 6 | 490.86 |
| [analog-db Tan CLIA](../tasks/gf180mcuD/analog-db/cases/amp_017_tan_clia/README.md) | Three-stage amplifier with physical compensation R/C and source-paired finite-window observations | 7 | 88555.19 |
| [analog-db Folded-Cascode LDO](../tasks/gf180mcuD/analog-db/cases/ldo_002_analoggym_folded_cascode/README.md) | External reference/bias, physical bleed, load/line recovery and startup | 7 | 29211.12 |
| [analog-db PMOS LDO](../tasks/gf180mcuD/analog-db/cases/ldo_007_pmos/README.md) | Divider/feedforward/Miller compensation, load/line recovery and startup | 7 | 98448.9 |

The [PDK manifest](../tasks/gf180mcuD/pdk.toml) binds `models`, `physical` and
`magic` profiles to one open-pdks installation. `models` uses nominal primitive
ngspice files; `physical` uses the qualified official KLayout rules for variant D,
including geometric/connectivity/off-grid DRC and antenna checks; `magic` uses the
upstream technology built for five metals, 1.1 um top metal and 1 kOhm/square poly.
The prebuilt version and installation/file checksums are explicit in the manifest.
The rule files and extraction coefficients come from that release; only the
SPICE reader adapter below modifies an upstream file. DRC runs all rule groups
except chip-level density, including dummy fill and 0.001 um database-unit checks.
The upstream isolated-worker mode keeps antenna connectivity changes separate
from the geometry/connectivity rule groups.
The KLayout reader adapter recognizes the official `nfet_03v3`,
`pfet_03v3` and `ppolyf_u_1k` X wrappers using their actual SI dimensions and MOS
total width. Named top-level pin correspondence is required independently of
KLayout's topology match.

The Magic profile uses nominal `ngspice()` extraction and a 10-way subdivision
of its 0.05 um internal grid before GDS import. This preserves 5 nm geometry and
port locations during resistance extraction. Candidate-derived MOS/passive
parameters, coupled capacitance and distributed interconnect resistance feed the
same published testbench used for source calibration. Physically distinct
source/body nodes must remain distinct; the model boundary does not include a
distributed silicon substrate network. The standalone-block scope excludes
chip-level density and seal-ring closure, statistical yield and RF/EM analysis.
The isolated-body PTAT uses a physical `nfet_03v3_dn` primitive for native LVS,
with its corresponding four-terminal `nfet_03v3` simulator call. Its independent
witness retains an output-tied isolated P-well, supply-tied deep N-well and an
explicit N-well annulus. The annulus keeps Magic's extresist substrate filling
from joining that body to the outer substrate return. This is a validated
layout route with the existing decks, not a change to PDK extraction rules.
The case additionally qualifies zero-state startup at its declared 100 fF load,
temperatures and supply ramps; larger loads are not covered.

The two self-biased amplifiers and buffered-reference LDO additionally qualify
native 6 V MOS and physical MIM-B 2 fF/um2 capacitors on M4/M5, with
`cap_mim_2f0fF` physical devices and `cap_mim_2f0_m4m5_noshield` simulator wrappers.
Their device graph, dimensions and ordered ports agree in source, native topology
and final RC netlists; waveform-derived measurements were independently checked.
They reuse the existing model bundle and native rules. Only necessary 5 nm
quantization and minimum-length adaptation are applied. StrongARM uses its fixed
3.3 V CMOS binding and the established dynamic timing/decision measurement flow.
The four cases use the reproducible [ngspice 45 overlay](#ngspice-45).
Their qualification does not impose upstream performance targets: notably, the
error-amplifier witness has a disclosed negative phase margin at 10 pF.
Other model families, such as GF180 BJTs, remain outside this qualification.

For automatic setup and reference evaluation, use
`python -m benchmarking.engine.preview quickstart --case ota_5t`.
It downloads the pinned GF180 release and prepares fresh resources without a
pre-existing `build/support` directory. Use `list` to select other GF180 cases.

For direct evaluation with the source case configurations, prepare the shared
image using [the manual tools instructions](#manual-tools), then run from the
repository root:

```bash
python -m benchmarking.engine.preview fetch --case ota_5t
python -m benchmarking.engine.prepare_support \
  tasks/gf180mcuD/pdk.toml#models \
  build/support/gf180-models
python -m benchmarking.engine.prepare_support \
  tasks/gf180mcuD/pdk.toml#physical \
  build/support/gf180-physical-v2
python -m benchmarking.engine.prepare_support \
  tasks/gf180mcuD/pdk.toml#magic \
  build/support/gf180-magic
python -m pytest tests/integration/test_public_references.py -k gf180mcuD -q
```

Reuse verified bundles; preparation deliberately refuses an existing destination.
Each case README supplies its reference command, measured results and scoring
basis. These commands generate the reader's own identity-bound reports under
`build/runs/`. Catalog-driven regressions require every supplied reference to
pass and every empty candidate to fail. These checks cover execution of the
declared case contracts; they do not independently establish the accuracy of
the GF180 parasitic coefficients.

<a id="gf180-source-calibration"></a>

#### Reproduce source calibration

The following example derives an unscored characterization from a case's frozen
simulation jobs. Replace the case and output arguments to characterize any of
these circuits; it automatically retains all configured operating points.
The script consumes the source netlist in place of extracted candidate data.
It removes scoring metadata and retains functional bounds. An unbounded target
observation becomes an unscored scalar diagnostic; its direction has no scoring
effect. It does not modify or bypass the scored post-layout plan.

```bash
uv run --locked python - \
  tasks/gf180mcuD/Jianxun-OTA/cases/ota_5t/case.toml \
  build/runs/gf180-ota-source-calibration <<'PYCODE'
import json
import sys
import tomllib
from pathlib import Path
from benchmarking.tasks import load_task
from benchmarking.engine.toolchains import load_toolchain
from benchmarking.evaluation import parse_evaluation
from benchmarking.engine.evaluate import run_evaluation

case, output = map(Path, sys.argv[1:])
task = load_task(case)
definition = tomllib.loads(case.read_text())["task"]
plan = definition["evaluation"]
plan["mode"] = "characterization"
plan.pop("scoring")
plan["jobs"] = [job for job in plan["jobs"] if job["stage"] == "simulate"]
for job in plan["jobs"]:
    job["inputs"]["dut"] = (
        "input:simulation" if "simulation" in definition["inputs"]
        else "input:netlist"
    )
plan["metrics"] = [m for m in plan["metrics"] if m["category"] == "performance"]
for metric in plan["metrics"]:
    for key in ("dimension", "zero_lower", "zero_upper", "baseline", "normalization", "scale"):
        metric.pop(key, None)
    if metric["direction"] == "target" and not {"lower", "upper"} <= metric.keys():
        # Unbounded target quality becomes an unscored scalar diagnostic.
        metric["direction"] = "maximize"
report = run_evaluation(
    parse_evaluation(json.dumps(plan).encode(), file_format="json"),
    task.evaluation_inputs(), load_toolchain(case), output,
)
print(report["outcome"])
PYCODE
```

Circuits with unresolved process mapping or netlist repair remain absent from
the catalogs. The analog-db LDO is an explicitly maintained five-port core:
reference and tail-current sources are external testbench apparatus, and its
divider uses physical process resistors. OpenFASOC and the ring-modulator
comparator remain excluded. Qualification is a standalone benchmark result;
formal admission and fabrication signoff are separate.

<a id="freepdk45"></a>

### FreePDK45 resources and qualification

Five public cases are `qualified` through input consistency and reference evaluation. Their
references are evaluated at **1.0 V, 27 C**, using nominal predictive
FreePDK45 BSIM4 models and candidate-derived Magic RC. Every case ships a passing
reference, its source netlist and testbench, fixed `layout-v2` scoring, and
reference results with reproduction commands. These are standalone transistor-level tasks.

| Collection / case | Function | Coefficient | Area reference (um2) |
| --- | --- | --- | --- |
| [OpenRAM / cell_6t](../tasks/freepdk45/OpenRAM/cases/cell_6t/README.md) | Write, hold and nondestructive read | 6 | 1.46 |
| [OpenRAM / sense_amp](../tasks/freepdk45/OpenRAM/cases/sense_amp/README.md) | Clocked differential decision | 5 | 2.82 |
| [OpenRAM / write_driver](../tasks/freepdk45/OpenRAM/cases/write_driver/README.md) | Loaded complementary tri-state drive | 3 | 3.36 |
| [nangate45-pdk / NAND2_X1](../tasks/freepdk45/nangate45-pdk/cases/NAND2_X1/README.md) | Two-input NAND truth table and transitions | 1 | 1.6789 |
| [nangate45-pdk / AOI21_X1](../tasks/freepdk45/nangate45-pdk/cases/AOI21_X1/README.md) | Compound AOI truth table and transitions | 2 | 2.0049 |

Each problem is self-contained. Its configuration owns the exact devices, loads,
stimuli, observation times, bounds, dimensions and area anchors. Source simulation defines the electrical scoring baseline. Standard-cell area
uses the reference layout; other areas use the frozen compact estimate. Witnesses
are excluded from standard solver inputs.

#### Prepare resources

For automatic setup and reference evaluation, use
`python -m benchmarking.engine.preview quickstart --case cell_6t`.
It fetches the required FreePDK45 sources and prepares fresh resources without a
pre-existing `build/support` directory. Use `list` to select other FreePDK45 cases.

For direct evaluation with source case configurations, initialize the single
FreePDK45 submodule, then prepare its four profiles:

```bash
git submodule update --init --depth 1 third_party/freepdk45-open-pdks
uv sync --locked --group eda
for profile in klayout models magic-vtg magic-vtl; do
  uv run --locked python -m benchmarking.engine.prepare_support \
    third_party/freepdk45-open-pdks "tasks/freepdk45/pdk.toml#$profile" \
    "build/support/freepdk45-$profile"
done
```

These commands require new destination directories. Reference evaluation uses the
same trusted tools image as other processes. Circuit-source repositories are not
needed to prepare or evaluate the maintained cases. Component licenses and model
notices accompany the exported resources.

#### Physical and extraction scope

The KLayout profile enables all implemented DRC, manufacturing-grid and antenna
checks without waivers. The community deck's POLY.3 spacing is 50 nm, as documented
upstream for Nangate compatibility. The source deck explicitly lacks its different-potential
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

The predictive extraction uses the community Magic technology's estimated
resistance/capacitance coefficients and its native placement of coupling and
ground capacitance, with nominal VTG/VTL ngspice models at 27 C. Wells and substrate
are lumped connections. This is not calibrated field-solver extraction or a
foundry signoff claim; process variation, substrate noise and RF/EM are outside scope.

Use `/resources/support/magic-vtg/freepdk45.tech` or the `magic-vtl` counterpart
for evaluation-equivalent extraction, as specified by the case problem. The unified
PDK directory retains the upstream views; reviewed profiles include the adaptations.

The explicit manifest adaptations map MOS extraction to the LVS-selected model
class, import threshold/annotation markers as non-electrical comments, and correct
`lambda` from 0.025 to **2.5**. Magic expresses this length in centimicrons, so 2.5
represents the technology's 25 nm internal grid; the upstream value otherwise
extracts a 50 nm gate as 0.5 nm. Upstream coefficients are retained. Qualification
checks all five published layouts through the complete extraction and simulation
path. This does not establish stream-out equivalence between Magic and KLayout;
the community repository documents known via/metal stream-out differences.

#### Reference regression

The case READMEs provide the reference evaluation commands and measured results.
The shared regression discovers executable witnessed cases from public catalogs,
prepares resources through their declared profiles, and checks the witness against
its own acceptance conditions. It also rejects an empty candidate. It has no
circuit-name branches, geometry recipes or expected score table.

```bash
python -m pytest tests/integration/test_public_references.py
```

Use `-k freepdk45` to select this PDK. Native reports, extracted netlists and
waveforms are generated in the test's temporary output directories. Direct
`python -m benchmarking.engine.cli evaluate` commands in each README write them to a selected `build/runs/`
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

The backend extension interface is described in [architecture](architecture.md#ownership). `python -m benchmarking.engine.cli characterize` performs an independent measurement and `python -m benchmarking.engine.cli evaluate` re-evaluates a GDS. Tool bindings may be embedded in a schema-2 case as `[toolchain]`, following the [task configuration guide](tasks.md#evaluation-plan). `evaluate` and `run` use these bindings when `--toolchain` is omitted; `characterize` still requires an explicit toolchain configuration. A plan returns 0 when it passes, 1 when a check or specification fails, and 2 for a configuration or execution error. Output includes `report.json` and artifacts saved by digest. Characterization fixtures are not formal layout tasks.

The shared `DockerTool` executor caps each tool container at 4 CPU equivalents,
4 GiB memory and 256 processes, including tool-version probes. These limits are
recorded in the backend identity alongside the image, timeout and implementation
digest. They are fixed measurement conditions, not automatically scaled to the
host. Reserve capacity for concurrent containers and host services. Solver-session
budgets are configured separately in the [run configuration](running.md#observation).
Changing execution budgets creates a new condition; it does not change scoring
formulas, case requirements or per-tool timeouts.

### ngspice and Magic

ngspice writes an input role as `<role>.spice` and uses `deck.spice` as its entry point. The testbench declares analyses and measurements; `parameters.values` generates `parameters.spice`, `parameters.measurements` specifies names and units, and `parameters.exports` names declared artifacts. Exit 0 still requires a complete set of finite measurements. See the [RC](architecture.md#ownership), [divider](architecture.md#ownership), and [MOS post-layout](architecture.md#ownership) characterization fixtures.

For high-impedance cores with low-ohmic extracted wiring, trusted ngspice backend
settings may select `resistor_formulation = "branch"` (default: `"conductance"`).
This represents each positive, literal, four-field R card in non-deck input roles
by a zero-volt series sensor and a CCVS imposing `V = R*I`, avoiding large `1/R`
nodal stamps. It retains every terminal and value; it adds no bias or leakage.
PDK support/model files and testbench fixtures are unchanged. Extended/model/TC
resistor cards and generated-name collisions are rejected. The original input
digest remains in the report; `effective_<role>` evidence records the actual
simulator netlist, and the formulation is part of backend identity.
This deterministic equivalent supports OP/DC/AC/transient analysis but omits
resistor thermal noise, so noise analysis is rejected in branch mode. Use the
[ngspice CCVS definition](https://ngspice.sourceforge.io/docs/ngspice-manual.pdf)
and analytical characterization regressions to review the equivalence. The
[two-NMOS temperature core](../tasks/gf180mcuD/analog-db/cases/tsn_001_ptat_2t/README.md)
uses Sparse 1.3 with explicit pivot settings and independent KCL checks. Changing
matrix formulation does not establish convergence or permit relaxed validity
checks. Internal current sensors must not be counted as external power/KCL ports.

Magic takes the top cell and ordered `ports` from trusted configuration; check the port list against the authoritative netlist. Later jobs must consume the exported netlist as-is. `magic-capacitance-docker` retains its capacitance-only behavior and records `wire_resistance=false`. `magic-rc-docker` adds distributed resistance and capacitance, and can be bound to `layout.extract_rc`.


Magic import can be configured with `gds_readonly=false` when a technology must
rescale its native import grid to represent the candidate DBU exactly. This does
not permit writes to the submitted GDS: preprocessing and import still operate
on isolated copies. The default remains `true`. Optional positive integer `grid_subdivision` (default 1)
refines the internal Magic grid before import, using `scalegrid 1 N`, so labels
and devices share the same resolution during resistance extraction. Ambiguous
styles, missing gate connections and orphaned-node substitutions are extraction
errors even if Magic writes a netlist. Optional `label_layers` is a
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

When wire-resistance extraction is enabled, the RC adapter also compares port pairs
joined by resistor cards in the native topology and final RC exports. It rejects a
new resistor-only connection between previously separate topology ports,
including unintended isolated-body/substrate connections. Intentional resistor
connections already present in the topology remain allowed. This guard does
not prove internal device-terminal graph equivalence or substrate accuracy;
case-specific physical mapping and electrical calibration are still required.
The [isolated-body controls](architecture.md#ownership)
exercise both the rejected deep-well-only route and the explicit N-well route.

SG13G2 Magic extraction treats well/substrate ties as ideal connections;
it does not preserve the finite `ntap1`/`ptap1` resistance cards used by the
source simulator netlists. The pinned PDK's
[tap connectivity rules](https://github.com/IHP-GmbH/IHP-Open-PDK/blob/22f43352dd8219f9007eb659e422e0d5fe28c5fb/ihp-sg13g2/libs.tech/klayout/tech/lvs/rule_decks/tap_connections.lvs)
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
the [RC regression](architecture.md#ownership) checks the analytical
resistance increment of a wire between two such devices. This changes tool
arithmetic, not PDK extraction rules.

The supported RC interface has one declared port per conductor. A native
topology check rejects multiple ports on one conductor: the installed Magic
can otherwise duplicate the resistance network or bypass it with an alias
resistor. This limitation produces an evaluation error. The
[RC integration checks](architecture.md#ownership) validate a known
wire-resistance increment, its effect on transistor delay, a fixture threshold
rejection, and invalid/unsupported inputs. Case-specific extraction warnings,
models, and calibration still require review; the comparator's current status
and commands are in its [case README](../tasks/ihp-sg13g2/IHP-AnalogAcademy/cases/comparator/README.md).

### KLayout Physical Checks

`klayout-docker` implements the same Backend interface, with `check` selecting `artifact`, `drc`, or `lvs`. A task job supplies only `layout` and `task`; LVS additionally supplies the authoritative `netlist`. For standalone debugging, use `parameters.top_cell`, `max_bytes`, and the LVS `subcircuit`; when `task` is supplied, these must not conflict with it. Checks do not publish an extracted netlist for post-layout simulation. The LVS extraction result is diagnostic evidence; a separate PEX job re-extracts from the same GDS for post-layout simulation.

The artifact check uses KLayout's native reader to validate the GDSII stream, the published file-size limit, the specified top cell, non-empty geometry, and unresolved hierarchy references. DRC/LVS configuration is a JSON file in the frozen support bundle that specifies `deck`, fixed `variables`, and explanatory `scope`; DRC also declares `required_categories`. The optional DRC `additional_decks` list contains `{deck, required_categories}` entries sharing the same variables. Every deck runs in its own KLayout process and must complete and produce its required categories. The gate sums their counts and fails if any deck fails; an execution or report error takes precedence. `report.db` and `report-1.db` (and corresponding logs/completion markers) remain separate native evidence, with per-deck results in `result.json`. Required categories guard against skipping rule groups but are not a complete rule list. Exact case-local `parameters.waivers` are available when declared by a reviewed task. For LVS, native cross-reference data must confirm that comparison occurred, the reference circuit is non-empty, and the requested circuit participated. The `ignore_top_ports_mismatch` variable controls whether the upstream runset and adapter add named-port checks after comparison. The reader follows KLayout's [LVS database](https://www.klayout.de/doc/code/class_LayoutVsSchematic.html) and [comparison result](https://www.klayout.de/doc/code/class_NetlistCrossReference.html) documentation. A missing report, skipped run, crash, or timeout is `error`; a completed check with unwaived violations is `failed`.

### IHP physical-check profiles

IHP resources come from one pinned ciel release with `sg13g2_pr` and common
technology files. The model, KLayout, Magic and PCell selections use that release's
native contents. PSP and passive Verilog-A sources are compiled with the selected
tools image during support preparation. Agent resources include the required
PCell Python dependencies from the prebuilt package; no nested Git initialization
or local open-pdks build is needed. The per-file PCell view uses the same cache.

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

`cell_frame` checks a standard cell's complete `functional_layers` bounding box:
fixed `height_um` and integral `width_grid_um` within half the candidate DBU.
Its nonempty `rails` list declares unique supply `name`, drawing `layer`, native
`connectivity_layer`, centre `y_um`, minimum `thickness_um` and `left_um`/`right_um`
insets. Coordinates are relative to the functional lower-left bound, so global
translation is allowed. Each required strip must be continuously covered by metal
on the supply net matched through LVS. A text label alone is insufficient.
This row-interface check does not establish neighbor abutment or external pin access.

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

The `sg13g2-kpex-cc-docker` backend provides nominal 2.5D coupling capacitance
with KPEX from the locked `eda` dependency group. Its only tool settings are
`image` and `timeout_seconds`; jobs consume the candidate GDS, the native LVS
database and its candidate/database/top-cell binding. It independently extracts
annotated geometry with KPEX's bundled SG13G2 technology, compares devices and
connectivity against the native candidate database, then preserves supported
`npn13g2`, `rsil` and `cap_cmim` model calls with their extracted geometry. It
rejects unsupported physical models. Native MIM classes lack KPEX's expected
scalar `C`: the writer adapts those classes to their physical model parameters
without removing layers or reinserting schematic devices. Output evidence
includes both databases, the candidate-derived reference, geometry log and
extracted netlist; the tool image identity binds the bundled technology.
This backend declares **CC only**, an ideal substrate reference, no wire
resistance and no inductance. A task must explicitly choose this scope; it is
not a substitute for a required RC flow.

For upstream flows requiring HSPICE-style syntax, `ngspice-docker` accepts
`compatibility = "hsa"`. The effective `.spiceinit` is archived and the choice
is part of backend identity. The default remains the prepared model profile's
startup. Use ngspice 45 or later for this HBT flow.

The pinned Magic support profile adds the missing local `gec,*m1` connection.
The upstream CIF importer paints `gec` on the physical emitter window; without
this connection, its Metal1-covered emitter is exported as an isolated compact
terminal. The digest-checked replacement is recorded in `pdk.toml` and prepared
resource identities; the upstream checkout and KLayout rules are unchanged.
HBT graph matching also uses retained native resistor geometry and named tail
ports to distinguish otherwise identical branches. Truly ambiguous graphs still
fail, and all passive and final-RC connectivity checks remain mandatory.


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

Magic represents the supported SG13G2 HBTs as native `msubckt` devices.
Its resistance extractor can emit MOS-named missing gate/drain/substrate
contact diagnostics for these compact-device contacts. The HBT composite
backend defers a terminal diagnostic only when its exact device coordinate,
supported HBT model and named terminal agree with the native `.ext` record.
Missing, ambiguous or contradictory evidence is an extraction error. The
standalone Magic backend retains its strict missing-gate rejection; there is
no case-level warning waiver.

Deferral is not acceptance: the composite backend must still complete the
KLayout/topology/final-RC correspondence, preserve proven external wire paths
and pass every device/passive check above. Orphaned-node, tool-error and other
unreviewed diagnostics remain fatal. The complete console log and structured
`magic:terminal_diagnostic_review` evidence are retained alongside `mapping`.
The reviewer implementation and policy are included in backend identity.

The [design 1 functional regression](architecture.md#ownership)
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

The repository maintains one unified image recipe; `iclayout-bench-tools:local` is its default local tag. It contains the complete EDA runtime used by preparation, simulation, extraction, and judging, including Qucs-S, Qucsator/QucsatorRF, Ngspice, Xschem, Magic, OpenVAF, and KLayout. Harnesses remain an external seam and are not baked into the image. Each operation still runs in an isolated container invocation, but all EDA invocations resolve the same frozen image ID. Development tags may select a compatible instance of this same toolchain; see [image development](#image-development).

On first installation, build and check that image directly. For iteration, reuse
an existing compatible image and run the checks without the build command:

```bash
python -m benchmarking.engine.preview build --image iclayout-bench-tools:local
bash tests/integration/test_toolchain.sh
```

Role-specific image tags are not part of the supported workflow. This keeps tool versions and backend availability consistent across preparation, solving, and evaluation. Prepare the shared support paths with the commands below:

```bash
python -m benchmarking.engine.environment tasks/ihp-sg13g2/pdk.toml build/support/pdk-view
python -m benchmarking.engine.prepare_support tasks/ihp-sg13g2/pdk.toml#magic build/support/sg13g2-magic
python -m benchmarking.engine.prepare_support tasks/ihp-sg13g2/pdk.toml#mos-models build/support/sg13g2-mos-models
python -m benchmarking.engine.prepare_support tasks/ihp-sg13g2/pdk.toml#klayout build/support/sg13g2-klayout
```

The IHP `mixed-mos-models` profile adds the pinned HV PSP library closure to
LV MOS support. Case-aware public preparation resolves this profile for
[VREF001](../tasks/ihp-sg13g2/analog-db/cases/vref_001_vgs/README.md); Agent resource
usage checks exercise both LV and HV model availability. Its qualification
covers the declared mixed-device circuit and finite conditions, not arbitrary
HV circuits or process corners. For manual preparation use
`tasks/ihp-sg13g2/pdk.toml#mixed-mos-models` with the same support-preparation
command shown above.

Resolve relative `settings.support` paths from the backend's launch working directory, while paths in a plan are relative to the plan file; keep these namespaces distinct. New configurations may use absolute support paths. The [integration tests](architecture.md#ownership) maintain complete fixture invocations; see [CONTRIBUTING](../CONTRIBUTING.md#verification) for how to select and run them.
