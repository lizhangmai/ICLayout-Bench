"""Preview configuration stays usable with just one arbitrarily named image."""

import hashlib
import importlib.util
import re
from pathlib import Path

import pytest
import tomli_w
from helpers.catalog import CASES, read_case
from helpers.protocol import write_protocol_task

from benchmarking.engine.runtime import load_case
from benchmarking.tasks import load_task

pytestmark = [pytest.mark.unit, pytest.mark.acceptance, pytest.mark.acceptance_fast]
ROOT = Path(__file__).resolve().parents[2]
from helpers.catalog import ROOT as PUBLIC_ROOT


@pytest.fixture
def preview():
    spec = importlib.util.spec_from_file_location("public_preview", ROOT / "benchmarking/engine/preview.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = PUBLIC_ROOT
    return module


def test_preview_covers_every_public_executable_witness(preview):
    expected = {path for path in CASES for data in [read_case(path)]
                if data.get("status") in {"candidate", "qualified"}
                and data.get("task") and data.get("qualification", {}).get("reference")}
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


# Dataset inputs and cache bindings must work without any prepared snapshot.
# Reuse the existing case fixture, replacing only Docker/PDK installation I/O.
# Assertions protect source immutability and solver isolation, not physical validity.
def test_runtime_uses_source_case_and_only_materializes_declared_inputs(preview_case, monkeypatch):
    from benchmarking.engine import runtime

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


@pytest.mark.parametrize("shared_blobs", [False, True])
def test_dataset_cache_links_are_read_without_copying(preview_case, tmp_path, monkeypatch, shared_blobs):
    import huggingface_hub.constants

    from benchmarking.dataset import load_dataset
    from benchmarking.files import read_file

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
    from benchmarking.engine import runtime
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
