"""Resource bundles publish the environment needed by PDK-aware harnesses."""

import json

import pytest

from benchmarking.engine.sessions.environment import (
    _agent_environment,
    resource_environment,
    resource_preflight,
)
from benchmarking.files import Asset

pytestmark = pytest.mark.unit


def test_generic_resources_do_not_get_pdk_environment_or_reference_material():
    resources = {"README.txt": Asset(b"solver resource", "text")}
    assert resource_environment(resources) == {}
    info = resource_preflight(resources)
    assert info == {"mount": "/resources", "environment": {},
                    "bundles": [], "python_imports": []}


def test_solver_mounts_remain_readable_under_a_private_umask(tmp_path, executable_case):
    import os
    from types import SimpleNamespace

    from benchmarking.engine.sessions.staging import stage_inputs
    from benchmarking.tasks import load_task

    root = tmp_path / 'private-session'
    root.mkdir(mode=0o700)
    harness = SimpleNamespace(capabilities=[], identity=dict)
    config = SimpleNamespace(harness=harness, files={'nested/run.py': Asset(b'# fixture', 'python')})
    old = os.umask(0o077)
    try:
        stage_inputs(root, load_task(executable_case), config,
                     {'nested/resource.txt': Asset(b'resource', 'text')}, 'fixture', {})
    finally:
        os.umask(old)
    assert root.stat().st_mode & 0o777 == 0o700
    for group in ('task', 'agent', 'resources', 'protocol'):
        for path in [root / group, *(root / group).rglob('*')]:
            if path.is_dir():
                assert path.stat().st_mode & 0o005 == 0o005, path
            else:
                assert path.stat().st_mode & 0o777 == 0o444, path


def test_external_resources_publish_container_paths_and_modules_without_host_or_credential_paths():
    from types import SimpleNamespace

    runtime = SimpleNamespace(name='licensed', environment={'PDK_ROOT': '/pdk'}, modules={'hspice': ['vendor/release']},
        tool_environment={'hspice': {'LD_PRELOAD': '/lib64/libudev.so.1'}},
        mounts=[{'source': '/operator/pdk', 'target': '/pdk/rules', 'release': '1'},
                {'source': '/operator/secret', 'target': '/license', 'release': '1', 'credential': True}])
    info = resource_preflight({}, runtime)
    assert info['external'] == {'name': 'licensed', 'environment': {'PDK_ROOT': '/pdk'},
        'modules': {'hspice': ['vendor/release']}, 'tool_environment': {'hspice': {'LD_PRELOAD': '/lib64/libudev.so.1'}},
        'mounts': [{'target': '/pdk/rules', 'release': '1'}]}
    assert '/operator' not in json.dumps(info) and '/license' not in json.dumps(info)


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


@pytest.mark.parametrize('target,environment', [('/task/leak', {}), ('/protocol', {}),
                                               ('/usr/bin', {}), ('/eda/tools', {'LD_PRELOAD': '/evil'})])
def test_external_solver_cannot_shadow_trusted_inputs_or_reader(target, environment):
    # Operator installation mounts are new; bundle tests above do not exercise
    # them. The isolation contract independently forbids shadowing trusted inputs
    # and reader binaries before Docker is contacted (no EDA/model claim).
    from types import SimpleNamespace

    from benchmarking.engine.sessions.docker import DockerSession

    runtime = SimpleNamespace(mounts=[{'target': target}], environment=environment, profile={})
    with pytest.raises(ValueError, match='trusted session'):
        DockerSession('unused', runtime=runtime)
