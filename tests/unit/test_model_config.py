"""Run configuration keeps credential-like values out of public Agent env."""

import pytest

from benchmarking.engine.model_config import load_run_config
from benchmarking.files import Asset
from benchmarking.harnesses import SESSION_PROTOCOL

pytestmark = pytest.mark.unit


def _config(tmp_path, harness="", *, environment=None):
    script = Asset(b"print('ok')", "python")
    (tmp_path / "cli.py").write_bytes(script.content)
    path = tmp_path / "agent.toml"
    path.write_text(
        f'''
id = "test-agent"
image = "synthetic:tag"
command = ["python", "/agent/cli.py"]
wall_seconds = 10
memory_mb = 128
cpus = 1
pids = 16
workspace_mb = 4
{harness}
[[files]]
path = "cli.py"
target = "cli.py"
sha256 = "{script.sha256}"
'''
    )
    if environment is not None:
        with path.open("a") as stream:
            stream.write("\n[environment]\n" + "\n".join(
                f'{name} = "{value}"' for name, value in environment.items()))
    return path


def test_credential_like_environment_names_are_rejected(tmp_path):
    name = "service_api_key"
    with pytest.raises(ValueError, match="(?i)credential"):
        load_run_config(_config(tmp_path, environment={name: "not-a-real-secret"}))


def test_tool_environment_names_remain_supported(tmp_path):
    config = load_run_config(
        _config(
            tmp_path,
            environment={"KLAYOUT": "1", "PYTHONPATH": "/workspace/lib", "PDK_ROOT": "/workspace/pdk"},
        )
    )

    assert config.environment == {
        "KLAYOUT": "1",
        "PYTHONPATH": "/workspace/lib",
        "PDK_ROOT": "/workspace/pdk",
    }


def test_external_configuration_parent_path_preserves_declared_file_checks(tmp_path, monkeypatch):
    # User-owned sibling projects are documented CLI inputs. Existing fixtures
    # only use canonical absolute roots; this protects normal ../ usage while
    # retaining the independent digest and no-symlink asset requirements.
    import hashlib
    from pathlib import Path

    agent = tmp_path / 'my-agent'
    agent.mkdir()
    bench = tmp_path / 'benchmark'
    bench.mkdir()
    source = _config(agent, environment={})
    payload = b'print("participant")\n'
    harness = agent / 'harness.py'
    harness.write_bytes(payload)
    source.write_text(source.read_text() + '\n[[files]]\npath = "harness.py"\ntarget = "harness.py"\n'
                      + f'sha256 = "{hashlib.sha256(payload).hexdigest()}"\n')
    monkeypatch.chdir(bench)
    config_path = Path('../my-agent/agent.toml')
    assert load_run_config(config_path).files['harness.py'].content == payload
    outside = tmp_path / 'outside.py'
    outside.write_bytes(payload)
    harness.unlink()
    harness.symlink_to(outside)
    with pytest.raises(ValueError, match='non-symlink'):
        load_run_config(config_path)


def test_external_harness_is_the_default_opaque_profile(tmp_path):
    config = load_run_config(_config(tmp_path, ""))

    assert config.harness.identity() == {
        "id": "external-cli",
        "version": "1",
        "protocol": SESSION_PROTOCOL,
        "mode": "opaque",
        "capabilities": [],
        "wire_api": None,
    }


def test_custom_harness_metadata_does_not_change_command_contract(tmp_path):
    config = load_run_config(
        _config(
            tmp_path,
            '''[harness]
id = "custom-runner"
version = "2026.1"
protocol = "layout-session"
mode = "managed"
capabilities = ["tools"]
''',
        )
    )

    assert config.command == ("python", "/agent/cli.py")
    assert config.harness.mode == "managed"
    assert config.harness.capabilities == ("tools",)
