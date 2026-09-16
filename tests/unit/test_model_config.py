"""Run configuration keeps credential-like values out of public Agent env."""

import pytest

from layout_eval.model_config import load_run_config

pytestmark = pytest.mark.unit


def _config(tmp_path, environment):
    path = tmp_path / "agent.toml"
    lines = [
        "schema_version = 1",
        'id = "test-agent"',
        'image = "synthetic:tag"',
        'command = ["python", "-c", "pass"]',
        "wall_seconds = 10",
        "memory_mb = 128",
        "cpus = 1",
        "pids = 16",
        "workspace_mb = 4",
        "",
        "[environment]",
    ]
    lines.extend(f'{name} = "{value}"' for name, value in environment.items())
    path.write_text("\n".join(lines) + "\n")
    return path


@pytest.mark.parametrize(
    "name",
    ["OPENAI_API_KEY", "GITHUB_TOKEN", "DATABASE_SECRET", "DB_PASSWORD"],
)
def test_credential_like_environment_names_are_rejected(tmp_path, name):
    with pytest.raises(ValueError, match="(?i)credential"):
        load_run_config(_config(tmp_path, {name: "not-a-real-secret"}))


def test_credential_like_environment_names_are_rejected_case_insensitively(tmp_path):
    with pytest.raises(ValueError, match="(?i)credential"):
        load_run_config(_config(tmp_path, {"service_token": "not-a-real-secret"}))


def test_tool_environment_names_remain_supported(tmp_path):
    config = load_run_config(
        _config(
            tmp_path,
            {"KLAYOUT": "1", "PYTHONPATH": "/workspace/lib", "PDK_ROOT": "/workspace/pdk"},
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
    source = _config(agent, {})
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
