import subprocess

import pytest
import tomli_w

from benchmarking.eda.resources.agent import prepare_agent_resources

pytestmark = pytest.mark.unit


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
    monkeypatch.setattr("benchmarking.eda.resources.installation.prepare_installation", lambda _: source)
    return root, source, manifest, git


def test_new_process_binds_original_root_without_flattening_links(declared_pdk):
    root, _source, manifest, _git = declared_pdk
    bundle = prepare_agent_resources(manifest, root / "resources")
    files = dict(bundle.files)
    mount = files["pdks/synthetic"]
    assert mount.path == _source
    assert (mount.path / "model.lib").read_bytes() == b"synthetic-model"
    assert (mount.path / "alias.lib").is_symlink()
    assert (mount.path / "additional-model.lib").is_file()
    assert sorted(p.name for p in (root / "resources").iterdir()) == ["resource.json"]
    from benchmarking.execution.workspace.environment import (
        resource_environment,
        resource_preflight,
    )
    assert resource_environment(files)["PDK"] == "future-process"
    assert resource_preflight(files)["checks"] == [["python", "-c", "print('synthetic')"]]


@pytest.mark.parametrize('selected', ['model.lib', 'tech'])
def test_selected_resources_replace_whole_root_binding(declared_pdk, selected):
    import tomllib

    from benchmarking.execution.workspace.environment import resource_environment

    root, source, manifest, _git = declared_pdk
    (source / 'tech').mkdir()
    (source / 'tech/rules').write_text('reviewed rules')
    (source / 'examples').mkdir()
    (source / 'examples/answer.gds').write_bytes(b'private answer')
    old = prepare_agent_resources(manifest, root / 'whole-root')
    spec = tomllib.loads(manifest.read_text())
    spec['agent']['sources']['synthetic']['paths'] = [selected]
    manifest.write_text(tomli_w.dumps(spec))
    narrowed = prepare_agent_resources(manifest, root / 'selected')
    assert narrowed.manifest.sha256 != old.manifest.sha256
    mounts = {name: path for name, path in narrowed.paths if name.startswith('pdks/')}
    assert mounts == {f'pdks/synthetic/{selected}': source / selected}
    assert resource_environment(dict(narrowed.files))['PDK_PATH'] == '/resources/pdks/synthetic'
    assert (source / 'examples/answer.gds').read_bytes() == b'private answer'


def test_selected_resource_cannot_escape_installation(declared_pdk):
    import tomllib

    root, source, manifest, _git = declared_pdk
    (root / 'outside.gds').write_bytes(b'outside')
    (source / 'outside').symlink_to(root / 'outside.gds')
    spec = tomllib.loads(manifest.read_text())
    spec['agent']['sources']['synthetic']['paths'] = ['outside']
    manifest.write_text(tomli_w.dumps(spec))
    with pytest.raises(ValueError, match='escapes its root'):
        prepare_agent_resources(manifest, root / 'selected')


def test_agent_local_checks_and_native_support_paths_are_portable(declared_pdk, monkeypatch):
    import tomllib

    from benchmarking.execution.workspace.environment import resource_preflight

    root, source, manifest, _git = declared_pdk
    resources = root/'resources-src'
    resources.mkdir()
    (resources/'smoke.py').write_text("print('reviewed check')\n")
    startup = b'pre_osdi /workspace/support/model.osdi\n'
    (resources/'spiceinit').write_bytes(startup)
    spec = tomllib.loads(manifest.read_text())
    spec['agent'].update(local_files={'checks/smoke.py': {'path': 'resources-src/smoke.py', 'format': 'python'}},
                         checks=[['python', '/resources/checks/smoke.py']], support_profiles=['models'])
    spec['profiles'] = {'models': {'local_files': {'.spiceinit': {'path': 'resources-src/spiceinit', 'format': 'text'}}}}
    manifest.write_text(tomli_w.dumps(spec))
    monkeypatch.setattr('benchmarking.eda.resources.agent.installation_path', lambda _: source)
    first = prepare_agent_resources(manifest, root/'prepared-one')
    files = dict(first.files)
    assert files['checks/smoke.py'].content == b"print('reviewed check')\n"
    assert files['support/models/.spiceinit'].content == b'pre_osdi /resources/support/models/model.osdi\n'
    assert (resources/'spiceinit').read_bytes() == startup
    assert resource_preflight(files)['checks'] == [['python', '/resources/checks/smoke.py']]
    (resources/'smoke.py').write_text("print('changed check')\n")
    second = prepare_agent_resources(manifest, root/'prepared-two')
    assert second.manifest.sha256 != first.manifest.sha256
    assert dict(second.files)['checks/smoke.py'].content == b"print('changed check')\n"
