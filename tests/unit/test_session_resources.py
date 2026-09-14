"""Resource bundles publish the environment needed by PDK-aware harnesses."""

import json

import pytest

from benchmarking.files import Asset
from benchmarking.session import (
    resource_environment,
    resource_preflight,
)

pytestmark = pytest.mark.unit


def pdk_resources(*, manifest=True, missing=()):
    names = {
        "ihp-sg13g2/libs.tech/klayout/python/sg13g2_pycell_lib/__init__.py",
        "ihp-sg13g2/libs.tech/klayout/python/pycell4klayout-api/source/python/cni/box.py",
        "ihp-sg13g2/libs.tech/klayout/python/pypreprocessor/pypreprocessor/__init__.py",
    } - set(missing)
    resources = {name: Asset(b"reviewed", "binary") for name in names}
    if manifest:
        raw = {"schema_version": 1, "files": {},
               "provenance": {"kind": "reviewed-pdk-view", "view_sha256": "a" * 64}}
        resources["manifest.json"] = Asset(json.dumps(raw).encode(), "json")
    return resources


@pytest.mark.parametrize('manifest', [False, True])
def test_resource_paths_resolve_the_pdk_packages(tmp_path, manifest):
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
    assert info == {"schema_version": 1, "mount": "/resources", "environment": {},
                    "bundles": [], "python_imports": []}


def test_preflight_describes_only_reviewed_resource_imports():
    info = resource_preflight(pdk_resources())
    assert info["mount"] == "/resources"
    assert info["environment"] == resource_environment(pdk_resources())
    assert info["python_imports"] == ["klayout", "pya", "sg13g2_pycell_lib"]
    assert "reference" not in json.dumps(info).lower()
