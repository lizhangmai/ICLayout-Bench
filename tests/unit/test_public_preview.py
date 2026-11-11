"""Preview configuration stays usable with just one arbitrarily named image."""

import hashlib
import importlib.util
import json
import re
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest
import tomli_w
from helpers.catalog import CASES, read_case
from helpers.protocol import write_protocol_task

from benchmarking.eda.images import DEFAULT_IMAGE
from benchmarking.eda.runtime import load_case, load_case_inputs
from benchmarking.tasks.contract import load_task

pytestmark = [pytest.mark.unit, pytest.mark.acceptance, pytest.mark.acceptance_fast]
ROOT = Path(__file__).resolve().parents[2]
from helpers.catalog import ROOT as PUBLIC_ROOT


@pytest.mark.parametrize('override', [None, 'explicit-image'])
@pytest.mark.parametrize('include_agent', [False, True])
def test_commercial_evaluator_loading_never_accesses_docker(preview_case, monkeypatch, override, include_agent):
    from benchmarking.eda import runtime

    monkeypatch.delenv('ICLAYOUT_BENCH_IMAGE', raising=False)
    root, case = preview_case
    process = root / 'installed-process'
    process.mkdir()
    (process / 'identity').write_text('reviewed process')
    manifest = root / 'tasks/synthetic-pdk/pdk.toml'
    manifest.write_text(tomli_w.dumps({
        'source': {'kind': 'external', 'runtime': 'commercial-fixture', 'release': '1'},
        'runtime': {'image': 'declared-commercial-image', 'environment': {'PDK_ROOT': '/process'},
                    'mounts': [{'source': str(process), 'target': '/process', 'release': '1',
                                'identity_paths': ['identity']}]}}))
    path = case / 'case.toml'
    config = tomllib.loads(path.read_text())
    config['toolchain'] = {'backends': {'external': {'type': 'fixture', 'settings': {'runtime': 'commercial-fixture'}}},
                          'bindings': {'check': 'external', 'simulate': 'external'}}
    path.write_text(tomli_w.dumps(config))
    def inspect(command, **kwargs):
        pytest.fail('Loading a commercial evaluator must not inspect or launch Docker images')

    monkeypatch.setattr(runtime.subprocess, 'check_output', inspect)
    selected = load_case(path, image=override, include_agent=include_agent,
                         factories={'fixture': lambda **settings: object()})
    assert selected.external.name == 'commercial-fixture'
    assert selected.external.image == 'declared-commercial-image'


@pytest.fixture
def preview():
    spec = importlib.util.spec_from_file_location("public_preview", ROOT / "benchmarking/eda/cli.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = PUBLIC_ROOT
    return module


@pytest.mark.parametrize('override,environment,expected', [
    (None, None, DEFAULT_IMAGE),
    (None, 'registry.example/eda:reviewed', 'registry.example/eda:reviewed'),
    ('selected-image', 'registry.example/eda:reviewed', 'selected-image'),
])
def test_runtime_resolves_published_and_user_selected_images(
        preview_case, monkeypatch, override, environment, expected):
    from benchmarking.eda import runtime

    root, source = preview_case
    monkeypatch.delenv('ICLAYOUT_BENCH_IMAGE', raising=False)
    if environment:
        monkeypatch.setenv('ICLAYOUT_BENCH_IMAGE', environment)
    inspected = []
    monkeypatch.setattr(runtime.subprocess, 'check_output',
                        lambda command, **kwargs: inspected.append(command[-1]) or 'sha256:selected')
    monkeypatch.setattr(runtime, 'prepare_installation', lambda spec: root / 'third_party/synthetic-pdk')
    load_case(source / 'case.toml', image=override, include_agent=False,
              factories={'klayout-docker': lambda **settings: object(),
                         'ngspice-docker': lambda **settings: object()})
    assert inspected == [expected]


def test_resource_commands_list_every_declared_task(preview):
    expected = {path for path in CASES for data in [read_case(path)]
                if data.get("status") in {"candidate", "qualified"}
                and isinstance(data.get("task"), dict)}
    discovered = {record["config"] for record in preview.discover_cases().values()}
    assert discovered == expected
    for key, record in preview.discover_cases().items():
        assert preview._resolve_case(key)["config"] == record["config"]


@pytest.fixture
def preview_case(preview, tmp_path, monkeypatch, circuit_case):
    root = tmp_path / "checkout with spaces"
    source = root / "tasks/synthetic-pdk/fixture/cases/named-case"
    task_path = write_protocol_task(source)
    body = task_path.read_text().split("[inputs.netlist]", 1)[1]
    body = re.sub(r"^(\[\[?)", r"\1task.", "[inputs.netlist]" + body, flags=re.MULTILINE)
    config = circuit_case.read_text().replace('status = "candidate"', 'status = "qualified"')
    config += '\n[task]\nkind = "netlist_to_gds"\nfamily = "protocol"\nenvironment = "no-eda"\n' + body
    config += '''
[qualification]
reference = "reference.gds"
[toolchain]
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
    (root / "third_party/synthetic-pdk/ihp-sg13g2").mkdir(parents=True)
    (root / ".gitmodules").write_text(
        '[submodule "pdk"]\npath = third_party/synthetic-pdk\nurl = https://example.test/pdk.git\n')
    (root / "tasks/synthetic-pdk").mkdir(parents=True, exist_ok=True)
    (root / "tasks/synthetic-pdk/pdk.toml").write_text(tomli_w.dumps({
        "source": {"repository": "https://example.test/pdk", "commit": "a" * 40},
        "profiles": {name: {"files": {}} for name in ("klayout", "analog-models", "hbt-models", "magic")},
    }))
    monkeypatch.setenv("ICLAYOUT_BENCH_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(preview, "ROOT", root)
    return root, source


@pytest.mark.parametrize('operation', ['list', 'fetch'])
def test_delivered_cases_can_be_listed_and_prefetched_without_references(
        preview, preview_case, monkeypatch, capsys, operation):
    from benchmarking.eda.resources import installation

    root, source = preview_case
    path = source / 'case.toml'
    config = tomllib.loads(path.read_text())
    config.pop('qualification')
    path.write_text(tomli_w.dumps(config))
    (source / 'reference.gds').unlink()
    installed = []
    monkeypatch.setattr(installation, 'prepare_installation',
                        lambda spec: installed.append(spec['repository']) or root)
    arguments = ['benchmarking.eda', '--dataset', str(root), operation]
    if operation == 'fetch':
        arguments += ['--case', config['id']]
    monkeypatch.setattr(sys, 'argv', arguments)

    preview.main()

    if operation == 'list':
        assert config['id'] in capsys.readouterr().out
        assert installed == []
    else:
        assert installed and set(installed) == {'https://example.test/pdk'}


def test_reference_evaluation_still_requires_an_explicit_witness(preview, preview_case):
    root, source = preview_case
    path = source / 'case.toml'
    config = tomllib.loads(path.read_text())
    config.pop('qualification')
    path.write_text(tomli_w.dumps(config))
    (source / 'reference.gds').unlink()
    with pytest.raises(ValueError, match='witness'):
        preview.run(config['id'], root / 'reference-run')


def test_candidate_evaluation_prepares_declared_resources_without_references(
        preview_case, tmp_path, monkeypatch, capsys):
    from benchmarking.eda import runtime, toolchain
    from benchmarking.evaluation import cli

    root, source = preview_case
    path = source / 'case.toml'
    config = tomllib.loads(path.read_text())
    config.pop('qualification')
    path.write_text(tomli_w.dumps(config))
    (source / 'reference.gds').unlink()
    candidate = tmp_path / 'candidate.gds'
    candidate.write_bytes(b'Submitted GDS; no author witness')
    inspected = []
    monkeypatch.setattr(runtime.subprocess, 'check_output',
                        lambda command, **kwargs: inspected.append(command[-1]) or 'sha256:fixture')
    monkeypatch.setattr(runtime, 'prepare_installation', lambda spec: root)
    prepared = []

    def backend(**settings):
        support = Path(settings['support'])
        assert support.is_dir(), 'Declared support must be prepared before evaluation'
        assert settings['image'] == 'sha256:fixture'
        prepared.append(support)
        return object()

    original = toolchain.load_toolchain
    monkeypatch.setattr(runtime, 'load_toolchain',
                        lambda config, **settings: original(config, **(settings | {
                            'factories': {'klayout-docker': backend, 'ngspice-docker': backend}})))

    def evaluate(plan, inputs, backends, output, **settings):
        assert inputs['candidate'].content == candidate.read_bytes()
        assert len(prepared) == len(backends) == 2
        assert settings['task_witnessed'] is False
        return {'mode': plan.mode, 'outcome': 'passed', 'physical_valid': True, 'specs_pass': None,
                'task_success': None, 'metrics': {}, 'task_witnessed': False}

    monkeypatch.setattr(cli, 'run_evaluation', evaluate)
    cli.main(['evaluate', str(path), str(candidate), '--image', 'selected-image',
              '--output', str(tmp_path / 'evaluation')])
    assert inspected == ['selected-image']
    assert json.loads(capsys.readouterr().out)['task_witnessed'] is False


@pytest.mark.parametrize('explicit_source', [False, True])
def test_image_build_uses_the_selected_checkout_instead_of_the_package_directory(
        preview, tmp_path, monkeypatch, explicit_source):
    source = tmp_path / 'user source'
    source.mkdir()
    (source / 'Dockerfile').write_text('FROM scratch\n')
    monkeypatch.chdir(tmp_path if explicit_source else source)
    monkeypatch.setattr(preview, 'doctor', lambda: None)
    commands = []
    monkeypatch.setattr(preview.subprocess, 'run',
                        lambda command, **options: commands.append((command, options))
                        or SimpleNamespace(returncode=0))
    arguments = ['benchmarking.eda', 'build', '--image', 'user-image', '--network', 'host']
    if explicit_source:
        arguments += ['--source', str(source)]
    monkeypatch.setattr(sys, 'argv', arguments)
    preview.main()
    command, options = commands[-1]
    assert Path(options['cwd']) == source
    assert command[:2] == ['docker', 'build']
    assert command[command.index('-t') + 1] == 'user-image'


# Dataset inputs and cache bindings must work without any prepared snapshot.
# Reuse the existing case fixture, replacing only Docker/PDK installation I/O.
# Assertions protect source immutability and solver isolation, not physical validity.
def test_runtime_uses_source_case_and_only_materializes_declared_inputs(preview_case, monkeypatch):
    from benchmarking.eda import runtime

    root, source = preview_case
    monkeypatch.setattr(runtime.subprocess, "check_output", lambda *a, **kw: "sha256:tools")
    monkeypatch.setattr(runtime, "prepare_installation", lambda spec: root / "third_party/synthetic-pdk")
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    configured = []
    def factory(**settings):
        configured.append(settings)
        return object()
    case = load_case(source / "case.toml", factories={"klayout-docker": factory, "ngspice-docker": factory})
    assert case.config == source / "case.toml"
    assert case.task.digest == load_task(source / "case.toml").digest
    assert all(settings["image"] == "sha256:tools" for settings in configured)
    assert all(Path(settings["support"]).is_dir() for settings in configured)
    assert before == {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    case.task.materialize(root.parent / "solver")
    assert {p.name for p in (root.parent / "solver").iterdir()} == {"input.spice"}
    assert case.witness().content == (source / "reference.gds").read_bytes()


def test_reference_inputs_load_without_pdk_or_tool_image(preview_case, monkeypatch):
    from benchmarking.eda import runtime

    root, source = preview_case
    (root / "tasks/synthetic-pdk/pdk.toml").unlink()
    monkeypatch.setattr(runtime.subprocess, "check_output", lambda *args, **kwargs: pytest.fail("Tool image inspected"))
    selected = load_case_inputs(source / "case.toml")
    assert selected.task.digest == load_task(source / "case.toml").digest
    assert selected.witness().content == b"Maintainer-only witness"


@pytest.mark.parametrize("shared_blobs", [False, True])
def test_dataset_cache_links_are_read_without_copying(preview_case, tmp_path, monkeypatch, shared_blobs):
    import huggingface_hub.constants

    from benchmarking.files import read_file
    from benchmarking.tasks.dataset import load_dataset

    root, source = preview_case
    revision = "b" * 40
    hub = tmp_path / "hub"
    repository = hub / "datasets--fixture--circuits"
    snapshot = repository / "snapshots" / revision
    blobs = repository / "blobs"
    blobs.mkdir(parents=True)
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        blob = blobs / hashlib.sha256(path.read_bytes()).hexdigest()
        if shared_blobs:
            shared = hub / "blobs" / blob.name[:2] / blob.name
            shared.parent.mkdir(parents=True, exist_ok=True)
            shared.write_bytes(path.read_bytes())
            blob.symlink_to(shared)
        else:
            blob.write_bytes(path.read_bytes())
        link = snapshot / path.relative_to(root)
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(blob)
    monkeypatch.setattr(huggingface_hub.constants, "HF_HUB_CACHE", str(hub))
    dataset = load_dataset("fixture/circuits", revision=revision, local_files_only=True)
    assert dataset.root == snapshot
    assert dataset.identity["commit"] == revision
    config = dataset.case("synthetic-circuit")
    assert dataset.case("named-case") == config
    assert config.is_symlink()
    assert load_task(config).input_assets() == load_task(source / "case.toml").input_assets()
    # Exercise actual profile binding from snapshot symlinks as well as task inputs.
    from benchmarking.eda import runtime
    monkeypatch.setattr(runtime.subprocess, "check_output", lambda *a, **kw: "sha256:tools")
    monkeypatch.setattr(runtime, "prepare_installation", lambda spec: root / "third_party/synthetic-pdk")
    resolved = load_case(config, include_agent=False,
                         factories={"klayout-docker": lambda **kw: object(),
                                    "ngspice-docker": lambda **kw: object()})
    assert resolved.task.digest == load_task(source / "case.toml").digest
    # A file escaping the repository's blob store is still rejected.
    unsafe = config.parent / "unsafe"
    unsafe.symlink_to(source / "input.spice")
    with pytest.raises(ValueError, match="non-symlink"):
        read_file(config.parent, "unsafe")
    # A repository blob may not redirect to arbitrary external files.
    redirected = blobs / "redirected"
    redirected.symlink_to(source / "input.spice")
    unsafe.unlink()
    unsafe.symlink_to(redirected)
    with pytest.raises(ValueError, match="non-symlink"):
        read_file(config.parent, "unsafe")
    if shared_blobs:
        # A second symlink beneath the shared store must not escape its boundary.
        shared.unlink()
        shared.symlink_to(source / "input.spice")
        with pytest.raises(ValueError, match="non-symlink"):
            read_file(link.parent, link.name)


def test_existing_reference_output_is_not_overwritten(preview, preview_case, monkeypatch):
    root, _ = preview_case
    output = root / "run"
    output.mkdir()
    (output / "evidence").write_text("retained")
    with pytest.raises(FileExistsError):
        preview.run("synthetic-circuit", output)
    assert (output / "evidence").read_text() == "retained"
