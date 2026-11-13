"""Manifest-local files stay independently editable and portable."""

import hashlib
import json

import pytest

from benchmarking.eda.resources.support import (
    manifest_local_paths,
    prepare_support_cache,
)

pytestmark = pytest.mark.unit


def test_local_files_and_patch_fragments_are_read_without_embedding(tmp_path, monkeypatch):
    resources = tmp_path/"resources"
    resources.mkdir()
    (resources/"model.json").write_text('{"resistance": 3250}\n')
    (resources/"adapter.rb").write_text("native_connect\n")
    (tmp_path/"vendor.rb").write_text("before\nANCHOR\nafter\n")
    manifest = tmp_path/"pdk.toml"
    manifest.write_text('''
[source]
kind = "checkout"
[profiles.native.local_files."model.json"]
path = "resources/model.json"
format = "json"
[profiles.native.files."vendor.rb"]
path = "vendor.rb"
format = "text"
[[profiles.native.files."vendor.rb".replace]]
old = "ANCHOR"
new_file = "resources/adapter.rb"
''')
    recipes = []
    def cache(namespace, recipe, build):
        stage = tmp_path/f"stage{len(recipes)}"
        stage.mkdir()
        recipes.append(recipe)
        assert build(stage) == {}
        return stage
    monkeypatch.setattr("benchmarking.eda.resources.support.cached_resources", cache)
    first = prepare_support_cache(tmp_path, str(manifest)+"#native", diagnostics=tmp_path/"diagnostics")
    assert json.loads((first/"model.json").read_text()) == {"resistance": 3250}
    assert (first/"vendor.rb").read_text() == "before\nnative_connect\n\nafter\n"
    changed = b'{"resistance": 1000}\n'
    (resources/"model.json").write_bytes(changed)
    second = prepare_support_cache(tmp_path, str(manifest)+"#native", diagnostics=tmp_path/"diagnostics")
    assert (second/"model.json").read_bytes() == changed
    assert recipes[0] != recipes[1]
    assert recipes[1]["local_files_sha256"]["resources/model.json"] == hashlib.sha256(changed).hexdigest()
    (resources/"before.txt").write_text("ANCHOR")
    manifest.write_text(manifest.read_text().replace('old = "ANCHOR"', 'old_file = "resources/before.txt"'))
    third = prepare_support_cache(tmp_path, str(manifest)+"#native", diagnostics=tmp_path/"diagnostics")
    assert (third/"vendor.rb").read_bytes() == (first/"vendor.rb").read_bytes()


def test_portable_inventory_includes_only_declared_local_files():
    manifest = {"profiles": {"native": {
        "local_files": {"config.json": {"path": "resources/config.json"}},
        "files": {"vendor.rb": {"path": "installed/vendor.rb", "replace": [
            {"old_file": "resources/before.rb", "new_file": "resources/adapter.rb"}]}}}},
        "agent": {"local_files": {"checks/smoke.py": {"path": "resources/smoke.py"}}},
        "runtime": {"control_files": {"strict.tvf": {"path": "resources/strict.tvf"}}},
        "notices": {"LICENSE": {"path": "resources/LICENSE"}}}
    assert manifest_local_paths(manifest) == ("resources/LICENSE", "resources/adapter.rb", "resources/before.rb",
                                              "resources/config.json", "resources/smoke.py", "resources/strict.tvf")
    manifest["notices"]["LICENSE"]["path"] = "../outside"
    with pytest.raises(ValueError):
        manifest_local_paths(manifest)


def test_external_control_paths_preserve_native_text_and_module_clones(tmp_path):
    import tomli_w

    from benchmarking.eda.environment import ExternalRuntime

    native = "# Native control\nset model \"unchanged\"\n"
    resources = tmp_path/"resources"
    resources.mkdir()
    (resources/"strict.tvf").write_text(native)
    manifest = tmp_path/"pdk.toml"
    spec = {"source": {"kind": "external", "runtime": "fixture"}, "runtime": {
        "image": "unused", "mounts": [], "environment": {},
        "modules": {"calibre": ["vendor/one"], "alternate": ["vendor/two"]},
        "control_files": {"strict.tvf": {"path": "resources/strict.tvf"}}}}
    manifest.write_text(tomli_w.dumps(spec))
    runtime = ExternalRuntime.from_manifest(manifest)
    assert runtime.control_assets()["process/strict.tvf"].content == native.encode()
    assert runtime.control_path("@strict.tvf") == "process/strict.tvf"
    assert runtime.select_module("calibre", "alternate").control_assets() == runtime.control_assets()
    legacy = ExternalRuntime("fixture", {**spec["runtime"], "control_files": {"strict.tvf": native}})
    assert runtime.identity == legacy.identity
    (resources/"strict.tvf").write_text("changed")
    assert ExternalRuntime.from_manifest(manifest).identity != runtime.identity
    assert runtime.control_files["strict.tvf"] == native
    spec["runtime"]["control_files"]["strict.tvf"]["path"] = "../outside"
    manifest.write_text(tomli_w.dumps(spec))
    with pytest.raises(ValueError):
        ExternalRuntime.from_manifest(manifest)
