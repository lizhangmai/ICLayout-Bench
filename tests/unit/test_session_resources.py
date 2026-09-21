"""Resource bundles publish the environment needed by PDK-aware harnesses."""

import json

import pytest

from benchmarking.engine.session import (
    _agent_environment,
    resource_environment,
    resource_preflight,
)
from benchmarking.files import Asset

pytestmark = pytest.mark.unit


def pdk_resources(*, manifest=True, missing=()):
    names = {
        "ihp-sg13g2/libs.tech/klayout/python/sg13g2_pycell_lib/__init__.py",
        "ihp-sg13g2/libs.tech/klayout/python/pycell4klayout-api/source/python/cni/box.py",
        "ihp-sg13g2/libs.tech/klayout/python/pypreprocessor/pypreprocessor/__init__.py",
    } - set(missing)
    resources = {name: Asset(b"reviewed", "binary") for name in names}
    if manifest:
        raw = {"files": {},
               "provenance": {"kind": "reviewed-pdk-view", "view_sha256": "a" * 64}}
        resources["manifest.json"] = Asset(json.dumps(raw).encode(), "json")
    return resources


def test_resource_paths_resolve_the_pdk_packages(tmp_path):
    manifest = True
    from importlib.machinery import PathFinder
    from pathlib import PurePosixPath

    resources = pdk_resources(manifest=manifest)
    for name in resources:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('# synthetic importable module\n')
    environment = resource_environment(resources)
    assert environment['KLAYOUT'] == '1'
    paths = [str(tmp_path / PurePosixPath(path).relative_to('/resources'))
             for path in environment['PYTHONPATH'].split(':')]
    for module in ['sg13g2_pycell_lib', 'cni']:
        spec = PathFinder.find_spec(module, paths)
        assert spec is not None, (module, paths)
        assert all(str(tmp_path) in str(path) for path in spec.submodule_search_locations)


def test_incomplete_pdk_bundle_fails_before_container_start():
    with pytest.raises(ValueError, match="PDK resource bundle is incomplete"):
        resource_environment(pdk_resources(missing=(
            "ihp-sg13g2/libs.tech/klayout/python/pypreprocessor/pypreprocessor/__init__.py",
        )))


def test_generic_resources_do_not_get_pdk_environment_or_reference_material():
    resources = {"README.txt": Asset(b"solver resource", "text")}
    assert resource_environment(resources) == {}
    info = resource_preflight(resources)
    assert info == {"mount": "/resources", "environment": {},
                    "bundles": [], "python_imports": []}


# A descriptor must configure any future process without granting host paths or
# overriding protected runtime settings. Synthetic mounted files are sufficient;
# actual PDK/tool use is exercised separately in the real session regression.
def declared_resources(environment):
    return {
        "pdks/new/python/tool.py": Asset(b"# synthetic", "python"),
        "pdk-environment.json": Asset(json.dumps({
            "id": "new", "environment": environment,
            "sources": {}, "checks": [["python", "-c", "pass"]],
        }).encode(), "json"),
    }


def test_declared_environment_merges_search_paths_and_rejects_conflicts():
    from types import SimpleNamespace

    resources = declared_resources({"PDK": "new", "PYTHONPATH": "/resources/pdks/new/python"})
    config = SimpleNamespace(environment={"PYTHONPATH": "/agent/python"})
    result = _agent_environment(config, resources)
    assert result == {"PDK": "new", "PYTHONPATH": "/resources/pdks/new/python:/agent/python"}
    with pytest.raises(ValueError, match="PDK resources require"):
        _agent_environment(SimpleNamespace(environment={"PDK": "another"}), resources)


@pytest.mark.parametrize("environment", [
    {"PDK_PATH": "/home/host/pdk"},
    {"HOME": "/resources/pdks/new"},
])
def test_declared_environment_rejects_missing_host_and_reserved_paths(environment):
    with pytest.raises(ValueError):
        resource_environment(declared_resources(environment))
