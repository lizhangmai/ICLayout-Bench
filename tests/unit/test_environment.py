import hashlib
import json
import subprocess

import pytest
import tomli_w

from benchmarking.engine import environment
from benchmarking.engine.pdk_resources import prepare_agent_resources

pytestmark = pytest.mark.unit


@pytest.fixture
def pdk(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "tool.py").write_bytes(b"# synthetic tool\n")
    (source / "unlisted.gds").write_bytes(b"must not enter the view")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"profile": "synthetic", "files": {
        "tool.py": hashlib.sha256((source / "tool.py").read_bytes()).hexdigest(),
        "LICENSE": hashlib.sha256(b"Synthetic component terms\n").hexdigest(),
    }}))
    monkeypatch.setattr(environment, "VIEW_MANIFEST", manifest)
    spec = tmp_path / "pdk.toml"
    spec.write_text(tomli_w.dumps({"source": {"kind": "ciel"},
                                  "notices": {"LICENSE": {"content": "Synthetic component terms\n", "format": "text"}}}))
    monkeypatch.setattr(environment, "prepare_installation", lambda _: source)
    return spec, tmp_path / "view"


def test_pdk_view_contains_only_reviewed_files(pdk):
    source, view = pdk
    digest = environment.prepare_pdk(source, view)
    assert environment.verify_pdk(view) == digest
    assert sorted(p.name for p in view.iterdir()) == ["LICENSE", "manifest.json", "tool.py"]
    assert (view / "LICENSE").read_text() == "Synthetic component terms\n"


def test_changed_view_is_rejected(pdk):
    source, view = pdk
    environment.prepare_pdk(source, view)
    tool = view / "tool.py"
    tool.chmod(0o644)
    tool.write_text("changed")
    with pytest.raises(ValueError):
        environment.verify_pdk(view)


# Contract: a newly declared process works through the same preparation interface,
# without local extras, host links or changed upstream bytes. The older view tests
# cover only per-file allowlists. Local Git commits supply an independent content
# oracle; all artifacts are pytest-owned. This proves snapshot isolation, not EDA.
@pytest.fixture
def declared_pdk(tmp_path):
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
    (source / "local-answer.gds").write_text("must not be delivered")
    manifest = root / "pdk.toml"
    manifest.write_text(tomli_w.dumps({"agent": {
        "schema_version": 1, "id": "future-process",
        "sources": {"synthetic": {"checkout": "third_party/synthetic"}},
        "environment": {"PDK": "future-process", "PDK_PATH": "/resources/pdks/synthetic"},
        "checks": [["python", "-c", "print('synthetic')"]],
    }}))
    return root, source, manifest, git


def test_new_process_snapshots_pinned_sources_and_flattens_internal_links(declared_pdk):
    root, _source, manifest, _git = declared_pdk
    bundle = prepare_agent_resources(manifest, root / "resources", root=root)
    files = dict(bundle.files)
    assert files["pdks/synthetic/model.lib"].content == b"synthetic-model"
    assert files["pdks/synthetic/alias.lib"] == files["pdks/synthetic/model.lib"]
    assert not any(".git" in name or "local-answer" in name for name in files)
    from benchmarking.engine.session import resource_environment, resource_preflight
    assert resource_environment(files)["PDK"] == "future-process"
    assert resource_preflight(files)["checks"] == [["python", "-c", "print('synthetic')"]]


@pytest.mark.parametrize("change", ["dirty", "escape", "cycle"])
def test_pdk_snapshot_rejects_local_changes_and_escaping_links(declared_pdk, change):
    root, source, manifest, git = declared_pdk
    if change == "dirty":
        (source / "model.lib").write_text("changed")
    else:
        if change == "escape":
            (source / "alias.lib").unlink()
            (source / "alias.lib").symlink_to("/etc/passwd")
            git(source, "add", "alias.lib")
        else:
            (source / "nested").mkdir()
            (source / "nested/model.lib").write_text("synthetic")
            (source / "nested/loop").symlink_to(".")
            git(source, "add", "nested")
        git(source, "commit", "-qm", "Synthetic unsafe upstream link")
        git(root, "add", "third_party/synthetic")
        git(root, "commit", "-qm", "Pin escaping link")
    with pytest.raises(ValueError, match="differs|normalized relative|cyclic"):
        prepare_agent_resources(manifest, root / "resources", root=root)
    assert not (root / "resources").exists()
    if change == "cycle":
        import tomllib

        data = tomllib.loads(manifest.read_text())
        data["agent"]["sources"]["synthetic"]["exclude"] = ["nested/loop"]
        manifest.write_text(tomli_w.dumps(data))
        bundle = prepare_agent_resources(manifest, root / "resources", root=root)
        assert "pdks/synthetic/nested/model.lib" in dict(bundle.files)
        assert not any("nested/loop" in name for name, _ in bundle.files)
