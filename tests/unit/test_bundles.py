import pytest
import tomli_w

from benchmarking.bundles import load_bundle, publish_bundle
from benchmarking.engine.prepare_support import prepare_support
from benchmarking.files import Asset

pytestmark = pytest.mark.unit


def test_bundle_snapshots_verified_files_and_retains_their_identity(tmp_path):
    bundle = publish_bundle({"models/a.lib": Asset(b"frozen model", "spice")}, {"test": True}, tmp_path / "bundle")
    (tmp_path / "bundle/models/a.lib").chmod(0o644)
    (tmp_path / "bundle/models/a.lib").write_text("later change")
    assert bundle.mounted_files()["support/models/a.lib"].content == b"frozen model"
    assert bundle.evidence()["support_manifest"].sha256 == bundle.manifest.sha256
    with pytest.raises(ValueError, match="checksum"):
        load_bundle(tmp_path / "bundle")


def test_bundle_rejects_linked_materials(tmp_path):
    root = tmp_path / "bundle"
    publish_bundle({"a": Asset(b"model", "spice")}, {}, root)
    (root / "alias").symlink_to(root / "a")
    with pytest.raises(ValueError):
        load_bundle(root)


def test_support_preparation_binds_pinned_sources_and_reuses_profiles(tmp_path, monkeypatch):
    monkeypatch.setenv("ICLAYOUT_BENCH_CACHE_DIR", str(tmp_path / "cache"))
    model = Asset(b"model source", "spice")
    source = tmp_path / "source"
    source.mkdir()
    (source / "model.lib").write_bytes(model.content)
    (source / "unlisted").write_text("must not be copied")
    manifest = tmp_path / "manifest.toml"
    manifest.write_text(tomli_w.dumps(
        {"source": {"kind": "synthetic"},
         "profiles": {"models": {"files": {"models/a.lib": {"path": "model.lib",
                                                            "format": "spice"}}}}}))
    profile = f"{manifest}#models"
    output = tmp_path / "prepared"
    digest = prepare_support(source, profile, output)
    bundle = load_bundle(output)
    assert bundle.manifest.sha256 == digest
    assert set(dict(bundle.files)) == {"models/a.lib"}
    assert dict(bundle.paths)["models/a.lib"] == source / "model.lib"
    assert not output.is_symlink()
    assert sorted(p.name for p in output.iterdir()) == ["resource.json"]
    second = tmp_path / "another-case"
    prepare_support(source, profile, second)
    assert load_bundle(second).paths == bundle.paths
    with pytest.raises(FileExistsError):
        prepare_support(source, profile, output)
    # PDK content is owned by its package manager, not re-audited by Bench.
    (source / "model.lib").write_text("changed")
    assert dict(load_bundle(output).files)["models/a.lib"].content == b"changed"


# Existing source/bundle tests do not exercise compilation reuse across cases.
# Synthetic compiler outputs distinguish raw, adapted and compiled bytes. Only
# the external compiler is replaced; this verifies storage/reuse, not model physics.
def test_cases_share_derived_files_and_recompile_only_changed_inputs(tmp_path, monkeypatch):
    from benchmarking.engine import prepare_support as module
    from benchmarking.engine.docker import ToolResult

    monkeypatch.setenv("ICLAYOUT_BENCH_CACHE_DIR", str(tmp_path / "cache"))
    source = tmp_path / "source"
    source.mkdir()
    original = Asset(b"upstream model", "verilog-a")
    (source / "model.va").write_bytes(original.content)
    manifest = tmp_path / "pdk.toml"
    config = {"source": {"kind": "synthetic"}, "profiles": {"models": {
        "compile_files": {"model.va": {"path": "model.va", "format": original.format,
                               "replace": [{"old": "upstream", "new": "adapted"}]}},
        "compile": [{"source": "model.va", "output": "model.osdi", "defines": []}]}}}
    manifest.write_text(tomli_w.dumps(config))
    calls = []

    class Compiler:
        def __init__(self, image, *_):
            self.identity = {"image_id": image}

        def run(self, command, files, exports):
            calls.append(command)
            return ToolResult(0, "", {"compiled.osdi": Asset(b"compiled " + files["model.va"].content, "osdi")},
                              {"console": Asset(b"compiler log", "text")})

    monkeypatch.setattr(module, "DockerTool", Compiler)
    bundles = []
    for case in ("one", "two"):
        output = tmp_path / case
        prepare_support(source, f"{manifest}#models", output, compiler_image="image-a")
        bundles.append(load_bundle(output))
        assert not output.is_symlink()
        assert not (output / "manifest.json").exists()
        assert not (output / "bindings.json").exists()
    assert len(calls) == 1
    assert bundles[0].paths == bundles[1].paths
    assert (source / "model.va").read_bytes() == original.content
    assert set(dict(bundles[0].files)) == {"model.osdi"}
    assert dict(bundles[0].files)["model.osdi"].content == b"compiled adapted model"
    prepare_support(source, f"{manifest}#models", tmp_path / "new-image", compiler_image="image-b")
    assert len(calls) == 2
    config["profiles"]["models"]["compile_files"]["model.va"]["replace"][0]["new"] = "changed"
    manifest.write_text(tomli_w.dumps(config))
    prepare_support(source, f"{manifest}#models", tmp_path / "new-adaptation", compiler_image="image-b")
    assert len(calls) == 3


def test_ciel_owns_installation_reuse_and_agent_mounts_the_process_root(tmp_path, monkeypatch):
    """Protect whole-root mounts and reuse without duplicating ciel integrity tests."""
    import tomllib
    from pathlib import Path
    from types import SimpleNamespace

    import ciel.manage
    import ciel.source
    from ciel.common import Version

    from benchmarking.engine.pdk_installation import cache_root, prepare_installation
    from benchmarking.engine.pdk_resources import prepare_agent_resources

    monkeypatch.delenv('ICLAYOUT_BENCH_CACHE_DIR', raising=False)
    monkeypatch.delenv('XDG_CACHE_HOME', raising=False)
    assert cache_root() == Path.home() / '.cache/iclayout-bench'
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'xdg'))
    assert cache_root() == tmp_path / 'xdg/iclayout-bench'
    monkeypatch.setenv('ICLAYOUT_BENCH_CACHE_DIR', str(tmp_path / 'shared cache'))
    from helpers.catalog import ROOT
    if not (ROOT / 'tasks/gf180mcuD/pdk.toml').exists():
        pytest.skip('Set ICLAYOUT_BENCH_DATASET to run dataset checks')
    source = tomllib.loads((ROOT / 'tasks/gf180mcuD/pdk.toml').read_text())['source']
    calls = []

    def fetch(root, family, version, **kwargs):
        calls.append((family, version))
        assert kwargs['include_libraries'] == source['libraries']
        assert kwargs['build_if_not_found'] is False
        installed = Version(version, family)
        path = Path(installed.get_dir(root))
        if not path.exists():
            for name, content in {'gf180mcuD/libs.tech/model.spice': b'model',
                                  'gf180mcuD/examples/answer.gds': b'never deliver'}.items():
                file = path / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(content)
        return installed

    monkeypatch.setattr(ciel.manage, 'fetch', fetch)
    monkeypatch.setattr(ciel.source, 'StaticWebDataSource',
                        lambda _: SimpleNamespace(session=SimpleNamespace(close=lambda: None)))
    cache = prepare_installation(source)
    monkeypatch.setattr(ciel.source, 'StaticWebDataSource', lambda _: pytest.fail('Cached PDK needs no network client'))
    assert prepare_installation(source) == cache
    assert calls == [(source['family'], source['version'])]
    manifest = tmp_path / 'pdk.toml'
    manifest.write_text(tomli_w.dumps({'source': source,
        'profiles': {'models': {'files': {'model.spice': {'path': 'gf180mcuD/libs.tech/model.spice',
                                                        'format': 'spice'}}}},
        'notices': {'LICENSE': {'format': 'text', 'content': 'synthetic terms'}},
        'agent': {'id': 'gf180mcuD', 'support_profiles': ['models'],
                  'sources': {'gf180mcuD': {'installation': True, 'path': 'gf180mcuD'}},
                  'environment': {'PDK_ROOT': '/resources/pdks'}, 'checks': [['true']]}}))
    bundle = prepare_agent_resources(manifest, tmp_path / 'export', root=tmp_path)
    exported = dict(bundle.files)
    assert (exported['pdks/gf180mcuD'].path / 'libs.tech/model.spice').read_bytes() == b'model'
    assert (exported['pdks/gf180mcuD'].path / 'examples/answer.gds').is_file()
    assert 'support/models/LICENSE' not in exported
    assert 'pdks/gf180mcuD/examples/answer.gds' not in exported  # No per-file inventory.
    assert dict(bundle.paths)['pdks/gf180mcuD'] == cache / 'gf180mcuD'
    prepare_agent_resources(manifest, tmp_path / 'another-case', root=tmp_path)
    assert (tmp_path / 'export/resource.json').read_bytes() == (tmp_path / 'another-case/resource.json').read_bytes()
    # No second inventory or checksum audit on reuse of ciel's installation.
    (cache / 'gf180mcuD/libs.tech/model.spice').write_text('local edit')
    assert prepare_installation(source) == cache
