import subprocess

import pytest
import tomli_w

from benchmarking.engine import environment
from benchmarking.engine.pdk_resources import prepare_agent_resources

pytestmark = pytest.mark.unit


@pytest.fixture
def pdk(tmp_path, monkeypatch):
    monkeypatch.setenv("ICLAYOUT_BENCH_CACHE_DIR", str(tmp_path / "cache"))
    source = tmp_path / "source"
    (source / "ihp-sg13g2").mkdir(parents=True)
    (source / "ihp-sg13g2/tool.py").write_bytes(b"# synthetic tool\n")
    (source / "ihp-sg13g2/unlisted.gds").write_bytes(b"must not enter the view")
    spec = tmp_path / "pdk.toml"
    spec.write_text(tomli_w.dumps({"source": {"kind": "ciel"},
                                  "notices": {"LICENSE": {"content": "Synthetic component terms\n", "format": "text"}}}))
    monkeypatch.setattr(environment, "prepare_installation", lambda _: source)
    return spec, tmp_path / "view"


def test_pdk_view_binds_the_whole_process_root(pdk):
    source, view = pdk
    digest = environment.prepare_pdk(source, view)
    from benchmarking.bundles import load_bundle
    assert load_bundle(view).manifest.sha256 == digest
    assert not view.is_symlink()
    mount = dict(load_bundle(view).files)["ihp-sg13g2"]
    assert (mount.path / "tool.py").is_file()
    assert (mount.path / "unlisted.gds").is_file()
    assert sorted(p.name for p in view.iterdir()) == ["resource.json"]


# Whole-process mounts use the installed root without filtering or enumerating it.
@pytest.fixture
def declared_pdk(tmp_path, monkeypatch):
    monkeypatch.setenv("ICLAYOUT_BENCH_CACHE_DIR", str(tmp_path / "cache"))
    root = tmp_path / "repo"
    source = root / "third_party/synthetic"
    source.mkdir(parents=True)

    def git(path, *args):
        return subprocess.check_output(["git", "-C", str(path), *args], stderr=subprocess.PIPE)

    for path in (root, source):
        git(path, "init", "-q")
        git(path, "config", "user.name", "Synthetic test")
        git(path, "config", "user.email", "test@example.invalid")
    (source / "model.lib").write_text("synthetic-model")
    (source / "alias.lib").symlink_to("./model.lib")
    git(source, "add", ".")
    git(source, "commit", "-qm", "Synthetic PDK")
    (root / ".gitmodules").write_text('[submodule "pdk"]\npath = third_party/synthetic\nurl = https://example.invalid/pdk\n')
    git(root, "add", ".gitmodules", "third_party/synthetic")
    git(root, "commit", "-qm", "Pin synthetic PDK")
    (source / "additional-model.lib").write_text("installed resource")
    manifest = root / "pdk.toml"
    manifest.write_text(tomli_w.dumps({"source": {"repository": "https://example.invalid/pdk",
                                               "commit": git(source, "rev-parse", "HEAD").decode().strip()},
                                      "agent": {
        "id": "future-process",
        "sources": {"synthetic": {"installation": True}},
        "environment": {"PDK": "future-process", "PDK_PATH": "/resources/pdks/synthetic"},
        "checks": [["python", "-c", "print('synthetic')"]],
    }}))
    monkeypatch.setattr("benchmarking.engine.pdk_installation.prepare_installation", lambda _: source)
    return root, source, manifest, git


def test_new_process_binds_original_root_without_flattening_links(declared_pdk):
    root, _source, manifest, _git = declared_pdk
    bundle = prepare_agent_resources(manifest, root / "resources", root=root)
    files = dict(bundle.files)
    mount = files["pdks/synthetic"]
    assert mount.path == _source
    assert (mount.path / "model.lib").read_bytes() == b"synthetic-model"
    assert (mount.path / "alias.lib").is_symlink()
    assert (mount.path / "additional-model.lib").is_file()
    assert sorted(p.name for p in (root / "resources").iterdir()) == ["resource.json"]
    from benchmarking.engine.session import resource_environment, resource_preflight
    assert resource_environment(files)["PDK"] == "future-process"
    assert resource_preflight(files)["checks"] == [["python", "-c", "print('synthetic')"]]
