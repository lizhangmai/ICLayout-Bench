"""Preview configuration stays usable with just one arbitrarily named image."""

import hashlib
import importlib.util
import json
import re
import shutil
import tomllib
from pathlib import Path

import pytest
import tomli_w
from helpers.protocol import write_protocol_task

from benchmarking import environment, prepare_support
from benchmarking.tasks import load_task

pytestmark = [pytest.mark.unit, pytest.mark.acceptance, pytest.mark.acceptance_fast]
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def preview():
    spec = importlib.util.spec_from_file_location("public_preview", ROOT / "scripts/public_preview.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_build_network_explains_loopback_proxy(preview, monkeypatch):
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:25127")

    with pytest.raises(ValueError, match="loopback proxy"):
        preview._check_build_network("default")

    preview._check_build_network("host")


@pytest.fixture
def preview_case(preview, tmp_path, monkeypatch, circuit_case):
    root = tmp_path / "checkout with spaces"
    source = root / "tasks/ihp-sg13g2/IHP-AnalogAcademy/cases/synthetic"
    task_path = write_protocol_task(source)
    body = task_path.read_text().split("[inputs.netlist]", 1)[1]
    body = re.sub(r"^(\[\[?)", r"\1task.", "[inputs.netlist]" + body, flags=re.MULTILINE)
    config = circuit_case.read_text().replace('status = "candidate"', 'status = "qualified"')
    config += '\n[task]\nkind = "netlist_to_gds"\nfamily = "protocol"\nenvironment = "no-eda"\n' + body
    config += '''
[qualification]
reference = "reference.gds"
evidence = "README.md"
[toolchain]
schema_version = 1
[toolchain.backends.rules]
type = "klayout-docker"
settings = {image = "synthetic-image", support = "source-rules", check = "drc", profile = "reviewed.json"}
support_profiles = {support = "klayout"}
[toolchain.backends.simulation]
type = "ngspice-docker"
settings = {image = "synthetic-image", support = "source-models"}
support_profiles = {support = "analog-models"}
[toolchain.bindings]
check = "rules"
simulate = "simulation"
'''
    (source / "case.toml").write_text(config)
    (source / "reference.gds").write_bytes(b"Maintainer-only witness")
    (source / "README.md").write_text("Maintainer-only provenance")
    (root / "tasks/ihp-sg13g2/IHP-AnalogAcademy/catalog.toml").write_text(
        'schema_version = 3\n\n[[cases]]\n'
        'id = "synthetic-circuit"\nconfig_path = "cases/synthetic/case.toml"\n')
    (root / "third_party/IHP-Open-PDK/ihp-sg13g2").mkdir(parents=True)
    monkeypatch.setattr(preview, "ROOT", root)
    return root, source


@pytest.mark.parametrize("shared_license", [False, True])
def test_preparation_binds_image_and_support_without_delivering_reference(preview, preview_case, monkeypatch, shared_license):
    root, source = preview_case
    if shared_license:
        terms = b"Synthetic collection license\n"
        (source.parent.parent / "LICENSE").write_bytes(terms)
        config = source / "case.toml"
        config.write_text(config.read_text() + '\n[task.inputs.license]\n'
                          'path = "materials/LICENSE"\ncollection_source = "LICENSE"\n'
                          f'sha256 = "{hashlib.sha256(terms).hexdigest()}"\n')
    monkeypatch.setattr(environment, "prepare_pdk_bundle", lambda source, output: output.mkdir())
    inspected, compilers = [], []
    identity = "sha256:" + "a" * 64

    def inspect(command, **kwargs):
        inspected.append(command[-1])
        return identity + "\n"

    def support(source, profile, output, *, compiler_image):
        compilers.append(compiler_image)
        output.mkdir()

    monkeypatch.setattr(preview.subprocess, "check_output", inspect)
    monkeypatch.setattr(prepare_support, "prepare_support", support)
    destination = root / "prepared"
    preview.prepare(destination, "my-unified-image:reviewed", "synthetic")
    assert inspected == ["my-unified-image:reviewed"]
    assert set(compilers) == {identity}
    bound_case = destination / "case/case.toml"
    toolchain = tomllib.loads(bound_case.read_text())["toolchain"]
    for backend in toolchain["backends"].values():
        assert backend["settings"]["image"] == identity
        path = Path(backend["settings"]["support"])
        assert path.is_dir() and path.parent == destination
    assert toolchain["backends"]["rules"]["settings"]["profile"] == "reviewed.json"
    task = load_task(bound_case)
    assert task.evaluation.description() == load_task(source / "case.toml").evaluation.description()
    task.materialize(root / "solver")
    assert (root / "solver/input.spice").read_bytes() == (source / "input.spice").read_bytes()
    assert not (root / "solver/reference.gds").exists()
    assert not (root / "solver/README.md").exists()
    assert not (root / "solver/case.toml").exists()
    if shared_license:
        (source.parent.parent / "LICENSE").unlink()
        assert load_task(bound_case).input_assets()["license"].content == terms
        assert (root / "solver/materials/LICENSE").read_bytes() == terms
    assert (bound_case.parent / "reference.gds").read_bytes() == b"Maintainer-only witness"


def test_discovery_reads_digest_bound_collection_plan(preview, preview_case):
    _, source = preview_case
    path = source / "case.toml"
    data = tomllib.loads(path.read_text())
    plan = data["task"].pop("evaluation")
    content = tomli_w.dumps(plan).encode()
    shared = source.parent.parent / "plan.toml"
    shared.write_bytes(content)
    data["task"]["inputs"]["evaluation"] = {
        "path": "evaluation.toml", "collection_source": shared.name,
        "sha256": hashlib.sha256(content).hexdigest(), "format": "toml",
    }
    path.write_text(tomli_w.dumps(data))
    assert preview._evaluation_mode(path, data) == plan["mode"]
    shared.write_bytes(content + b"\n# changed source\n")
    assert preview._evaluation_mode(path, data) is None


def test_discovery_spans_collections_and_selects_hbt_support(preview, preview_case, monkeypatch):
    root, source = preview_case
    hbt = root / "tasks/ihp-sg13g2/TO_Apr2025/cases/hbt_synthetic"
    hbt.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, hbt)
    config = (hbt / "case.toml").read_text().replace(
        'id = "synthetic-circuit"', 'id = "hbt-synthetic"')
    config = config.replace('support_profiles = {support = "analog-models"}',
                            'support_profiles = {support = "hbt-models"}')
    config += '''
[toolchain.backends.extraction]
type = "sg13g2-hbt-rc-docker"
support_profiles = {klayout_support = "klayout", magic_support = "magic"}
[toolchain.backends.extraction.settings]
image = "synthetic-image"
klayout_support = "source-klayout"
klayout_profile = "reviewed.json"
magic_support = "source-magic"
technology = "magic/ihp-sg13g2.tech"
tech_name = "ihp-sg13g2"
style = "ngspice()"
'''
    (hbt / "case.toml").write_text(config)

    candidate = root / "tasks/ihp-sg13g2/TO_Apr2025/cases/candidate_synthetic"
    shutil.copytree(source, candidate)
    config = (candidate / "case.toml").read_text().replace(
        'id = "synthetic-circuit"', 'id = "candidate-synthetic"')
    (candidate / "case.toml").write_text(config.replace(
        'status = "qualified"', 'status = "candidate"'))

    for collection, entries in {
        "IHP-AnalogAcademy": [("synthetic-circuit", "cases/synthetic/case.toml")],
        "TO_Apr2025": [("hbt-synthetic", "cases/hbt_synthetic/case.toml"),
                       ("candidate-synthetic", "cases/candidate_synthetic/case.toml")],
    }.items():
        catalog = root / "tasks/ihp-sg13g2" / collection / "catalog.toml"
        catalog.parent.mkdir(parents=True, exist_ok=True)
        body = "schema_version = 3\n\n" + "\n".join(
            f'[[cases]]\nid = "{case_id}"\nconfig_path = "{config_path}"\n'
            for case_id, config_path in entries)
        catalog.write_text(body)

    cases = preview.discover_cases()
    assert set(cases) == {"synthetic", "hbt_synthetic", "candidate_synthetic"}
    hbt_backend = cases["hbt_synthetic"]["data"]["toolchain"]["backends"]["simulation"]
    assert preview._support_bindings("simulation", hbt_backend) == [("support", "hbt-models")]
    unbound_hbt = {**hbt_backend}
    unbound_hbt.pop("support_profiles")
    with pytest.raises(ValueError, match="support_profiles metadata"):
        preview._support_bindings("simulation", unbound_hbt)
    assert preview._case_choices() == ("candidate_synthetic", "hbt_synthetic", "synthetic")

    monkeypatch.setattr(environment, "prepare_pdk_bundle", lambda source, output: output.mkdir())
    identity = "sha256:" + "b" * 64
    monkeypatch.setattr(preview.subprocess, "check_output", lambda *args, **kwargs: identity + "\n")
    profiles = []

    def support(source, profile, output, *, compiler_image):
        profiles.append(profile)
        output.mkdir()

    monkeypatch.setattr(prepare_support, "prepare_support", support)
    preview.prepare(root / "candidate-prepared", "synthetic-tools:local", "candidate_synthetic")
    assert load_task(root / "candidate-prepared/case/case.toml").status == "candidate"
    profiles.clear()
    preview.prepare(root / "hbt-prepared", "synthetic-tools:local", "hbt_synthetic")
    assert {profile.rsplit("#", 1)[-1] for profile in profiles} == {"klayout", "magic", "hbt-models"}


def test_preview_requires_a_published_witness(preview, preview_case):
    root, source = preview_case
    config = (source / "case.toml").read_text()
    (source / "case.toml").write_text(config.replace('reference = "reference.gds"\n', ""))
    with pytest.raises(ValueError, match="published witness"):
        preview.prepare(root / "prepared", "my-unified-image:reviewed", "synthetic")


@pytest.mark.parametrize("success", [True, False])
def test_reference_run_requires_actual_task_success(preview, preview_case, monkeypatch, success):
    root, source = preview_case
    prepared = root / "prepared"
    prepared.mkdir()
    source.rename(prepared / "case")

    def evaluate(*args, **kwargs):
        report_dir = Path(args[args.index("--output") + 1])
        report_dir.mkdir()
        (report_dir / "report.json").write_text(json.dumps({
            "outcome": "passed" if success else "failed", "task_success": success,
        }))

    monkeypatch.setattr(preview, "python", evaluate)
    output = root / "run"
    if not success:
        with pytest.raises(ValueError, match="complete evaluation"):
            preview.run(prepared, output)
        assert not (output / "preview.json").exists()
    else:
        preview.run(prepared, output)
        summary = json.loads((output / "preview.json").read_text())
        assert summary["reference"] == "passed" and summary["model_called"] is False


def test_existing_evidence_rejected_before_build_or_pdk_update(preview, tmp_path, monkeypatch):
    evidence = tmp_path / "run.json"
    evidence.write_text("retained evidence")
    monkeypatch.setattr(preview, "doctor", lambda: None)
    monkeypatch.setattr(preview, "_check_build_network", lambda network: None)
    monkeypatch.setattr(preview, "call", lambda *args, **kwargs: pytest.fail("Must not run preparation commands"))
    with pytest.raises(ValueError, match="Output already exists"):
        preview.quickstart(tmp_path, preview.IMAGE, "default", False)
    assert evidence.read_text() == "retained evidence"


def test_quickstart_skip_build_reuses_prepared_resources(preview, tmp_path, monkeypatch):
    monkeypatch.setattr(preview, "doctor", lambda: None)
    monkeypatch.setattr(preview, "build", lambda *args: pytest.fail("--skip-build must not build an image"))
    monkeypatch.setattr(preview, "ensure_pdk", lambda: None)
    completed = []

    def prepare(destination, image, case):
        assert case == "comparator"
        assert image == "synthetic-tools:local"
        destination.mkdir()
        (destination / "sentinel").write_text("prepared resources")

    def run(prepared, output):
        assert (prepared / "sentinel").read_text() == "prepared resources"
        assert output.is_relative_to(tmp_path / "skip-build")
        completed.append(output)

    monkeypatch.setattr(preview, "prepare", prepare)
    monkeypatch.setattr(preview, "run", run)

    output = tmp_path / "skip-build"
    preview.quickstart(output, "synthetic-tools:local", "host", True)

    assert len(completed) == 1


def _populate_required_pdk(root, preview, *, complete=True):
    pdk = root / preview.PDK_PATH
    pdk.mkdir(parents=True, exist_ok=True)
    (pdk / ".git").write_text("gitdir: synthetic\n")
    for relative, marker in preview.PDK_REQUIRED_SUBMODULES.items():
        path = pdk / relative
        path.mkdir(parents=True)
        if complete:
            (path / marker).parent.mkdir(parents=True, exist_ok=True)
            (path / marker).write_bytes(b"synthetic")
    return pdk


@pytest.mark.parametrize("empty_directory", [False, True], ids=["absent", "empty-checkout"])
def test_pdk_initializes_an_unpopulated_checkout(preview, tmp_path, monkeypatch, empty_directory):
    root = tmp_path / "checkout"
    if empty_directory:
        # A Git checkout without submodule initialization leaves this directory.
        (root / preview.PDK_PATH).mkdir(parents=True)
    monkeypatch.setattr(preview, "ROOT", root)
    commands = []

    def update(*args, **kwargs):
        commands.append(args)
        _populate_required_pdk(root, preview)

    monkeypatch.setattr(preview, "call", update)
    preview.ensure_pdk()

    assert commands == [("git", "submodule", "update", "--init", "--depth", "1",
                         "third_party/IHP-Open-PDK")]


@pytest.mark.parametrize("complete", [False, True], ids=["incomplete", "complete"])
def test_pdk_preserves_populated_directories_without_git_metadata(preview, tmp_path, monkeypatch, complete):
    pdk = _populate_required_pdk(tmp_path, preview, complete=complete)
    (pdk / ".git").unlink()
    local_file = pdk / "local.txt"
    local_file.write_text("Retain local contents")
    monkeypatch.setattr(preview, "ROOT", tmp_path)
    monkeypatch.setattr(preview, "call", lambda *args, **kwargs: pytest.fail("Must not clone over local files"))

    if complete:
        preview.ensure_pdk()
    else:
        with pytest.raises(ValueError, match="no Git metadata"):
            preview.ensure_pdk()
    assert local_file.read_text() == "Retain local contents"


def test_pdk_update_does_not_recurse_into_optional_nested_submodules(preview, tmp_path, monkeypatch):
    root = tmp_path / "checkout"
    pdk = _populate_required_pdk(root, preview)
    optional = pdk / "ihp-sg13g2/libs.tech/digital"
    optional.mkdir(parents=True)
    (optional / "README").write_text("untracked optional checkout")
    monkeypatch.setattr(preview, "ROOT", root)
    commands = []
    monkeypatch.setattr(preview, "call", lambda *args, **kwargs: commands.append(args))

    preview.ensure_pdk()

    assert commands == [("git", "submodule", "update", "--init", "--depth", "1",
                         "third_party/IHP-Open-PDK")]


def test_pdk_update_explains_incomplete_non_git_nested_directory(preview, tmp_path, monkeypatch):
    root = tmp_path / "checkout"
    pdk = _populate_required_pdk(root, preview, complete=False)
    nested = pdk / next(iter(preview.PDK_REQUIRED_SUBMODULES))
    (nested / "untracked.txt").write_text("partial checkout")
    monkeypatch.setattr(preview, "ROOT", root)
    commands = []
    monkeypatch.setattr(preview, "call", lambda *args, **kwargs: commands.append(args))

    with pytest.raises(ValueError, match="non-empty directory without Git metadata") as error:
        preview.ensure_pdk()

    assert "git -C third_party/IHP-Open-PDK submodule update --init --depth 1" in str(error.value)
    assert not any("--recursive" in command for args in commands for command in args)


def test_pdk_update_initializes_only_missing_required_nested_submodules(preview, tmp_path, monkeypatch):
    root = tmp_path / "checkout"
    pdk = _populate_required_pdk(root, preview, complete=False)
    monkeypatch.setattr(preview, "ROOT", root)
    commands = []

    def update(*args, **kwargs):
        commands.append(args)
        if args[1:3] == ("-C", pdk):
            for relative in args[8:]:
                relative = Path(relative)
                marker = preview.PDK_REQUIRED_SUBMODULES[relative]
                target = pdk / relative / marker
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"synthetic")

    monkeypatch.setattr(preview, "call", update)
    preview.ensure_pdk()

    assert commands[0][-1] == "third_party/IHP-Open-PDK"
    assert commands[1][:7] == ("git", "-C", pdk, "submodule", "update", "--init", "--depth")
    assert set(commands[1][8:]) == {str(path) for path in preview.PDK_REQUIRED_SUBMODULES}
    assert "--recursive" not in commands[1]
