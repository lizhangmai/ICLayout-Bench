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


def test_support_preparation_only_reads_the_declared_hash_matching_sources(tmp_path):
    model = Asset(b"model source", "spice")
    source = tmp_path / "source"
    source.mkdir()
    (source / "model.lib").write_bytes(model.content)
    (source / "unlisted").write_text("must not be copied")
    manifest = tmp_path / "manifest.toml"
    manifest.write_text(tomli_w.dumps(
        {"schema_version": 1, "source": {"kind": "synthetic"},
         "profiles": {"models": {"files": {"models/a.lib": {"path": "model.lib", "sha256": model.sha256,
                                                            "format": "spice"}}}}}))
    profile = f"{manifest}#models"
    output = tmp_path / "prepared"
    digest = prepare_support(source, profile, output)
    bundle = load_bundle(output)
    assert bundle.manifest.sha256 == digest
    assert set(dict(bundle.files)) == {"models/a.lib", "preparation.json"}
    with pytest.raises(FileExistsError):
        prepare_support(source, profile, output)
    (source / "model.lib").write_text("changed")
    with pytest.raises(ValueError, match="checksum"):
        prepare_support(source, profile, tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()


def test_ciel_cache_is_pinned_offline_and_only_exports_selected_resources(tmp_path, monkeypatch):
    """An interrupted fetch or edited cache must never become trusted solver input."""
    import hashlib
    import json
    import tomllib
    from pathlib import Path
    from types import SimpleNamespace

    import ciel.manage
    import ciel.source
    from ciel.common import Version

    from benchmarking.engine.pdk_installation import (
        cache_root,
        installation_path,
        prepare_installation,
    )
    from benchmarking.engine.pdk_resources import prepare_agent_resources

    monkeypatch.delenv('ICLAYOUT_BENCH_CACHE_DIR', raising=False)
    monkeypatch.delenv('XDG_CACHE_HOME', raising=False)
    assert cache_root() == Path.home() / '.cache/iclayout-bench'
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'xdg'))
    assert cache_root() == tmp_path / 'xdg/iclayout-bench'
    monkeypatch.setenv('ICLAYOUT_BENCH_CACHE_DIR', str(tmp_path / 'shared cache'))
    assert cache_root() == tmp_path / 'shared cache'
    declared = tomllib.loads((Path(__file__).parents[2] / 'tasks/gf180mcuD/pdk.toml').read_text())['source']
    contents = {'gf180mcuD/libs.tech/model.spice': b'reviewed model',
                'gf180mcuD/examples/answer.gds': b'never deliver'}
    hashes = {k: hashlib.sha256(v).hexdigest() for k, v in contents.items()}
    source = {**declared, 'sha256': hashlib.sha256(
        json.dumps(hashes, sort_keys=True, separators=(',', ':')).encode()).hexdigest()}
    fail = True
    calls = []

    def fetch(root, family, version, **kwargs):
        calls.append((family, version))
        assert kwargs['include_libraries'] == source['libraries']
        assert kwargs['build_if_not_found'] is False
        installed = Version(version, family)
        for name, content in contents.items():
            file = Path(installed.get_dir(root)) / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(content)
        if fail:
            raise OSError('interrupted download')
        return installed

    monkeypatch.setattr(ciel.manage, 'fetch', fetch)
    monkeypatch.setattr(ciel.source, 'StaticWebDataSource',
                        lambda _: SimpleNamespace(session=SimpleNamespace(close=lambda: None)))
    with pytest.raises(OSError, match='interrupted'):
        prepare_installation(source)
    assert not installation_path(source).exists()
    fail = False
    cache = prepare_installation(source)
    # No network/provider construction on reuse, even with an unrelated active PDK.
    monkeypatch.setenv('PDK_ROOT', str(tmp_path / 'unrelated-active-pdk'))
    monkeypatch.setattr(ciel.source, 'StaticWebDataSource', lambda _: pytest.fail('offline reuse contacted provider'))
    assert prepare_installation(source) == cache
    assert len(calls) == 2
    manifest = tmp_path / 'pdk.toml'
    manifest.write_text(tomli_w.dumps({'schema_version': 1, 'source': source,
        'profiles': {'models': {'files': {'model.spice': {'path': 'gf180mcuD/libs.tech/model.spice',
                    'sha256': hashes['gf180mcuD/libs.tech/model.spice'], 'format': 'spice'}}}},
        'notices': {'LICENSE': {'format': 'text', 'content': 'synthetic terms'}},
        'agent': {'schema_version': 1, 'id': 'gf180mcuD', 'support_profiles': ['models'],
                  'sources': {'gf180mcuD': {'installation': True, 'path': 'gf180mcuD',
                             'include': ['gf180mcuD/libs.tech']}},
                  'environment': {'PDK_ROOT': '/resources/pdks'}, 'checks': [['true']]}}))
    bundle = prepare_agent_resources(manifest, tmp_path / 'export', root=tmp_path)
    exported = dict(bundle.files)
    assert exported['pdks/gf180mcuD/libs.tech/model.spice'].content == b'reviewed model'
    assert exported['support/models/LICENSE'].content == b'synthetic terms'
    assert not any('answer.gds' in name for name in exported)
    assert not (tmp_path / 'unrelated-active-pdk').exists()
    (cache / 'gf180mcuD/libs.tech/model.spice').write_text('local edit')
    with pytest.raises(ValueError, match='checksum mismatch'):
        prepare_support(None, f'{manifest}#models', tmp_path / 'rejected-cache')
    assert not (tmp_path / 'rejected-cache').exists()
