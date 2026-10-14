"""Experiment selection, credential boundaries and MCP protocol regressions."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from benchmarking.participants.adapters import prepare as prepare_harness
from benchmarking.participants.adapters.contracts import (
    LaunchContext,
    ParticipantSelection,
)
from benchmarking.participants.bridge import Bridge, dispatch
from benchmarking.participants.config import read_configs, read_matrix, resolve

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('harness,matrix', [
    ('codex', False), ('claude-code', False), ('dsh', False), ('kimi-code', False), ('zcode', False),
    ('codex', True),
])
def test_native_home_paths_are_relative_to_each_configuration(tmp_path, monkeypatch, harness, matrix):
    import tomli_w

    config_dir = tmp_path / 'configs' / harness
    config_dir.mkdir(parents=True)
    home = config_dir / 'subscription'
    home.mkdir()
    row = {'name': 'fixture', 'harness': harness, 'harness_home': 'subscription',
           'model': 'fixture', 'effort': 'high', 'tasks': ['fixture'], 'concurrency': 1, 'repetitions': 1}
    path = config_dir / 'experiment.toml'
    path.write_text(tomli_w.dumps({'defaults': row, 'runs': [{}]} if matrix else row))
    monkeypatch.chdir(tmp_path)
    selected, = (read_matrix(path) if matrix else read_configs([path]))
    assert selected['harness_home'] == str(home)
    assert selected['model'] == 'fixture'


@pytest.mark.parametrize('harness,configuration,credential', [
    ('codex', 'config.toml', 'auth.json'),
    ('claude-code', 'settings.json', '.credentials.json'),
])
def test_native_home_selection_never_falls_back_to_host_authentication(tmp_path, monkeypatch, harness, configuration, credential):
    from benchmarking.participants import adapters

    host = tmp_path / 'host'; host.mkdir()
    chosen = tmp_path / 'chosen'; chosen.mkdir()
    text = 'cli_auth_credentials_store="file"\nforced_login_method="chatgpt"\n' if harness == 'codex' else '{}'
    (host / configuration).write_text(text)
    (chosen / configuration).write_text(text)
    raw = json.dumps({'tokens': {'access_token': 'selected-fixture-token'}})
    (host / credential).write_text(raw)
    metadata = adapters.get(harness).METADATA
    monkeypatch.setenv(metadata.home_environment, str(host))
    monkeypatch.setenv('CODEX_API_KEY', 'host-fixture-key')
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'host-fixture-key')
    with pytest.raises(ValueError, match='authentication|credentials'):
        resolve(harness, 'fixture', 'high', harness_home=chosen)
    (chosen / credential).write_text(raw)
    selection = resolve(harness, 'fixture', 'high', harness_home=chosen)
    assert selection.environment[metadata.home_environment] == str(chosen)
    assert selection.settings['native_home'] == str(chosen)
    assert 'CODEX_API_KEY' not in selection.environment if harness == 'codex' else 'ANTHROPIC_API_KEY' not in selection.environment
    assert 'selected-fixture-token' not in json.dumps(selection.condition) + repr(selection)
    (chosen / configuration).unlink()
    with pytest.raises(ValueError, match='configuration must be a regular file'):
        resolve(harness, 'fixture', 'high', harness_home=chosen)


def test_codex_selected_connection_controls_provider_but_cannot_enable_tools(tmp_path, monkeypatch):
    import tomli_w

    home = tmp_path / 'api'; home.mkdir()
    config = {'model_provider': 'fixture', 'model_providers': {'fixture': {
        'name': 'fixture', 'base_url': 'https://fixture.example/v1', 'env_key': 'EXPERIMENT_KEY', 'wire_api': 'responses'}}}
    path = home / 'config.toml'
    path.write_text(tomli_w.dumps(config))
    monkeypatch.setenv('EXPERIMENT_KEY', 'selected-fixture-key')
    monkeypatch.setenv('CODEX_API_KEY', 'host-fixture-key')
    monkeypatch.setenv('OPENAI_BASE_URL', 'https://host.example/v1')
    selection = resolve('codex', 'fixture-model', 'medium', harness_home=home)
    assert selection.condition['auth_method'] == 'api'
    assert selection.condition['provider'] == 'fixture'
    assert 'CODEX_API_KEY' not in selection.environment and 'OPENAI_BASE_URL' not in selection.environment
    selection.environment['ICLAYOUT_BENCH_TOOL_TIMEOUT_SECONDS'] = '120'
    args = prepare_harness_args(selection.condition, selection.environment, selection.settings,
                                tmp_path / 'mcp.json', tmp_path)
    values = dict(argument.split('=', 1) for argument in args if '=' in argument)
    assert json.loads(values['model_providers.fixture.base_url']) == 'https://fixture.example/v1'
    assert json.loads(values['features.shell_tool']) is False
    assert args[args.index('-m') + 1] == 'fixture-model'
    assert json.loads(values['model_reasoning_effort']) == 'medium'
    assert 'selected-fixture-key' not in json.dumps(selection.condition) + str(args)
    for field, value in [('hooks', {}), ('mcp_servers', {'unreviewed': {}}), ('model', 'different-model')]:
        path.write_text(tomli_w.dumps(config | {field: value}))
        with pytest.raises(ValueError, match='connection settings only'):
            resolve('codex', 'fixture-model', 'medium', harness_home=home)


@pytest.mark.parametrize('home', [' ', 1, '\x00'])
def test_invalid_native_home_is_rejected(tmp_path, home):
    import tomli_w

    path = tmp_path / 'experiment.toml'
    path.write_text(tomli_w.dumps({'harness': 'codex', 'harness_home': home, 'model': 'fixture',
                                  'effort': 'high', 'tasks': ['fixture'], 'concurrency': 1, 'repetitions': 1}))
    with pytest.raises(ValueError, match='harness_home'):
        read_configs([path])


def test_dry_run_can_select_subscription_and_api_homes_in_one_invocation(tmp_path, monkeypatch, capsys):
    import tomli_w

    from benchmarking.participants.cli import main

    paths = []
    for mode in ('chatgpt', 'api'):
        home = tmp_path / mode; home.mkdir()
        (home / 'config.toml').write_text(f'cli_auth_credentials_store="file"\nforced_login_method="{mode}"\n')
        auth = {'tokens': {'access_token': 'subscription-fixture-token'}} if mode == 'chatgpt' else {'OPENAI_API_KEY': 'api-fixture-key'}
        (home / 'auth.json').write_text(json.dumps(auth))
        config = {'harness': 'codex', 'harness_home': mode, 'model': 'fixture', 'effort': 'medium',
                  'tasks': ['fixture'], 'concurrency': 1, 'repetitions': 1}
        path = tmp_path / (mode + '.toml'); path.write_text(tomli_w.dumps(config)); paths.append(str(path))
    monkeypatch.setenv('CODEX_HOME', str(tmp_path / 'missing-host'))
    monkeypatch.setenv('CODEX_API_KEY', 'ambient-fixture-key')
    assert main(['--config', *paths, '--dry-run']) == 0
    raw = capsys.readouterr().out
    assert [row['resolved']['auth_method'] for row in json.loads(raw)] == ['chatgpt', 'api']
    assert 'fixture-token' not in raw and 'fixture-key' not in raw
    assert not (tmp_path / 'results').exists()


def test_codex_native_auth_mode_selects_the_matching_stored_credentials(tmp_path):
    (tmp_path / 'config.toml').write_text('forced_login_method="chatgpt"\n')
    (tmp_path / 'auth.json').write_text(json.dumps({'auth_mode': 'chatgpt',
        'tokens': {'access_token': 'selected-chatgpt-token'}, 'OPENAI_API_KEY': 'inactive-api-key'}))
    selected = resolve('codex', 'fixture', 'medium', harness_home=tmp_path)
    assert selected.condition['auth_method'] == 'chatgpt'
    assert 'selected-chatgpt-token' not in json.dumps(selected.condition)


@pytest.mark.parametrize('explicit', [False, True])
def test_local_service_inherits_the_operator_cache_without_session_controls(tmp_path, monkeypatch, explicit):
    from benchmarking.participants.local_service import service

    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'xdg'))
    monkeypatch.delenv('ICLAYOUT_BENCH_CACHE_DIR', raising=False)
    expected = tmp_path / 'xdg/iclayout-bench'
    if explicit:
        expected = tmp_path / 'chosen-cache'
        monkeypatch.setenv('ICLAYOUT_BENCH_CACHE_DIR', str(expected))
    monkeypatch.setenv('ICLAYOUT_BENCH_SESSION', 'unrelated-session')
    monkeypatch.setenv('ICLAYOUT_BENCH_TOKEN', 'unrelated-token')
    process = Mock(pid=123456)
    process.stdout.readline.return_value = 'Local development service: http://localhost:1234\n'
    spawned = Mock(return_value=process)
    monkeypatch.setattr('benchmarking.service.launch.subprocess.Popen', spawned)
    selector = Mock()
    selector.select.return_value = [object()]
    selector_context = Mock()
    selector_context.__enter__ = Mock(return_value=selector)
    selector_context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr('benchmarking.service.launch.selectors.DefaultSelector',
                        lambda: selector_context)
    output = tmp_path / 'run'
    output.mkdir()
    with service({'dataset': 'fixture', 'case': 'fixture'}, output, 'fixture'):
        environment = spawned.call_args.kwargs['env']
        assert environment['ICLAYOUT_BENCH_CACHE_DIR'] == str(expected)
        assert 'ICLAYOUT_BENCH_SESSION' not in environment
        assert 'ICLAYOUT_BENCH_TOKEN' not in environment


@pytest.mark.parametrize('name,known', [('execute', True), ('check', True), ('submit', True), ('write', False)])
def test_checkpoint_tool_reconciliation_observes_without_replaying(tmp_path, name, known):
    from benchmarking.participants.bridge import reconcile_restarted_tools

    client = Mock()
    client.session.return_value = {'recovery': {'workspace_restored': True}, 'active_execution_id': None}
    response = {'execution_id': 'interrupted'} if name in {'execute', 'check'} else {'submission_id': 'accepted'}
    client.request.return_value = {'known': known, 'response': response if known else None}
    client.poll.return_value = {'state': 'error', 'exit_code': None, 'log_base64': '', 'next_offset': 0, 'truncated': False}
    pending = tmp_path / 'tools.pending.json'
    pending.write_text(json.dumps({'tool': name, 'key': 'original-key', 'arguments': {}}))
    result, = reconcile_restarted_tools(client, 'same-session', tmp_path)
    assert not pending.exists()
    namespace = {'execute': 'executions', 'check': 'executions', 'submit': 'submissions', 'write': 'files'}[name]
    client.request.assert_called_once_with('GET', f'/sessions/same-session/requests/{namespace}/original-key')
    if name in {'execute', 'check'}:
        assert result['result']['state'] == 'error' and result['result']['exit_code'] is None
    elif known:
        assert result['result']['submission_id'] == 'accepted'
    else:
        assert result['result'] == {'state': 'not_committed', 'workspace_rolled_back': True}
    for mutation in (client.execute, client.write, client.submit, client.check):
        mutation.assert_not_called()
    assert json.loads((tmp_path / 'tools.jsonl').read_text()) == result


def test_editable_package_identity_tracks_loaded_source(tmp_path, monkeypatch):
    from benchmarking.participants.config import package_identity

    package = tmp_path / 'benchmarking'
    package.mkdir()
    source = package / '__init__.py'
    source.write_text('VALUE = 1\n')
    dist = Mock(metadata={'Name': 'iclayout-bench'}, version='test', files=[])
    dist.read_text.return_value = json.dumps({'dir_info': {'editable': True}})
    monkeypatch.setattr('importlib.metadata.distribution', lambda name: dist)
    monkeypatch.setattr('benchmarking.__file__', str(source))
    monkeypatch.setattr('benchmarking.participants.config.package_version', lambda: {'commit': 'test-commit'})
    before = package_identity()
    assert before['commit'] == 'test-commit'
    source.write_text('VALUE = 2\n')
    assert package_identity()['installed_content_sha256'] != before['installed_content_sha256']
    cache = package / '__pycache__'
    cache.mkdir()
    before = package_identity()
    (cache / 'test.pyc').write_bytes(b'cache')
    assert package_identity() == before




def prepare_harness_args(condition, env, settings, mcp, directory):
    return prepare_harness(LaunchContext(ParticipantSelection(condition, env, settings), mcp, directory, directory, directory / "bridge.py", "task"))


class SelectionTests(unittest.TestCase):
    def test_dataset_source_environment_resolves_before_selection(self):
        # Dataset I/O is the external boundary; config parsing and identity binding
        # stay real. Missing settings must not silently select a different dataset.
        import tomli_w
        fields = {'harness': 'codex', 'model': 'gpt-6-astra', 'concurrency': 1,
                  'efforts': ['high'], 'repetitions': 1,
                  'dataset': {'source_env': 'EXAMPLE_DATASET', 'name': 'core', 'split': 'test'}}
        dataset = Mock(identity={'source': 'org/public-data', 'commit': 'frozen'})
        records = Mock()
        records.to_list.return_value = [{'task_id': 'fixture'}]
        dataset.native_cases.return_value = (records, {'fixture': Path('case.toml')})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'experiment.toml'
            path.write_text(tomli_w.dumps(fields))
            with patch.dict(os.environ, {'EXAMPLE_DATASET': 'org/public-data'}), \
                    patch('benchmarking.dataset.load_dataset', return_value=dataset) as load:
                rows = read_configs([path])
                load.assert_called_once_with('org/public-data', revision=None, local_files_only=False)
                self.assertEqual(rows[0]['tasks'], ['fixture'])
                self.assertEqual(rows[0]['dataset']['source'], 'org/public-data')
                self.assertNotIn('source_env', rows[0]['dataset'])
            for value in (None, '', '   '):
                with patch.dict(os.environ), patch('benchmarking.dataset.load_dataset') as load:
                    os.environ.pop('EXAMPLE_DATASET', None)
                    if value is not None:
                        os.environ['EXAMPLE_DATASET'] = value
                    with self.assertRaisesRegex(ValueError, 'EXAMPLE_DATASET'):
                        read_configs([path])
                    load.assert_not_called()
            fields['dataset']['source'] = 'ambiguous/data'
            path.write_text(tomli_w.dumps(fields))
            with self.assertRaisesRegex(ValueError, 'exactly one'):
                read_configs([path])

    def test_pair_configs_require_explicit_conditions_and_expand_efforts(self):
        fields = {'harness': 'codex', 'model': 'gpt-6-astra', 'tasks': ['fixture'], 'concurrency': 1,
                  'efforts': ['high', 'xhigh'], 'repetitions': 1}
        import tomli_w
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "codex-astra.toml"
            path.write_text(tomli_w.dumps(fields))
            rows = read_configs([path])
            self.assertEqual([r["effort"] for r in rows], fields['efforts'])
            self.assertTrue(all("hours" not in r for r in rows))
            for key in fields:
                path.write_text(tomli_w.dumps({k: v for k, v in fields.items() if k != key}))
                with self.subTest(missing=key), self.assertRaises(ValueError):
                    read_configs([path])
            for change in ({'efforts': ['default']}, {'benchmark': 'selection.toml'}, {'hours': 3}, {'seconds': 1800},
                           {'tasks': []}, {'tasks': ['same', 'same']}, {'tasks': 'case'},
                           {'concurrency': 0}, {'concurrency': True}, {'concurrency': 1.5}, {'repetitions': 0}, {'efforts': []}, {'efforts': ['high', 'high']}):
                path.write_text(tomli_w.dumps(fields | change))
                with self.subTest(change=change), self.assertRaises(ValueError):
                    read_configs([path])
            path.write_text(tomli_w.dumps(fields))
            with self.assertRaises(ValueError):
                read_configs([path, path])

    def test_claude_inherits_xhigh_and_override_does_not_edit_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            original = json.dumps({"env": {"ANTHROPIC_AUTH_TOKEN": "test-secret",
                                          "ANTHROPIC_MODEL": "glm-5.3[1m]",
                                          "CLAUDE_CODE_EFFORT_LEVEL": "xhigh"}})
            path.write_text(original)
            with patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": directory,
                                         "ICLAYOUT_BENCH_TOKEN": "creation-secret"}):
                selection = resolve("claude-code")
                selected, env, settings = selection.condition, selection.environment, selection.settings
                self.assertEqual(selected["effort_resolved"], "xhigh")
                self.assertIsNone(selected["effort_requested"])
                self.assertNotIn("secret", json.dumps(selected))
                self.assertNotIn("test-secret", repr(selection))
                self.assertNotIn("ICLAYOUT_BENCH_TOKEN", env)
                args = prepare_harness_args(selected, env, settings, Path("mcp.json"), Path(directory))
                self.assertNotIn("--effort", args)
                self.assertNotIn("test-secret", str(args))
                selection = resolve("claude-code", effort="high")
                overridden, env, settings = selection.condition, selection.environment, selection.settings
                self.assertEqual(overridden["effort_resolved"], "high")
                args = prepare_harness_args(overridden, env, settings, Path("mcp.json"), Path(directory))
                self.assertEqual(args[args.index("--effort") + 1], "high")
            self.assertEqual(path.read_text(), original)

    def test_codex_profile_defaults_and_explicit_override(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "config.toml").write_text(
                'model = "gpt-6-astra"\nprofile = "experiment"\n'
                '[profiles.experiment]\nmodel_reasoning_effort = "high"\n')
            with patch.dict(os.environ, {"CODEX_HOME": directory}):
                selected = resolve("codex").condition
                self.assertEqual(selected["effort_resolved"], "high")
                selected = resolve("codex", effort="medium").condition
                self.assertEqual(selected["effort_resolved"], "medium")
                with self.assertRaises(ValueError):
                    resolve("official-codex", model="gpt-6-astra")

    def test_no_configuration_does_not_invent_a_native_effort(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"CODEX_HOME": directory}):
            native = resolve("codex", model="gpt-6-astra").condition
            self.assertIsNone(native["effort_resolved"])

    def test_matrix_defaults_and_duplicate_names(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "matrix.toml"
            path.write_text('[defaults]\ntasks=["task"]\nconcurrency=1\neffort="high"\nrepetitions=1\n'
                            '[[runs]]\nname="glm"\nharness="claude-code"\nmodel="glm-5.3"\n')
            rows = read_matrix(path)
            self.assertEqual(rows[0]["effort"], "high")
            with path.open("a") as stream:
                stream.write('[[runs]]\nname="glm"\nharness="dsh"\n')
            with self.assertRaises(ValueError):
                read_matrix(path)

    def test_dsh_omitted_effort_stays_unspecified(self):
        from benchmarking.participants.adapters.dsh import resolve as resolve_dsh
        with patch("benchmarking.participants.adapters.dsh.configuration", return_value=([], {}, {
                "provider": "deepseek-official", "model": "deepseek-flash"})):
            selected = resolve_dsh(None, None, {}).condition
            self.assertIsNone(selected["effort_resolved"])
            selected = resolve_dsh(None, "max", {}).condition
            self.assertEqual(selected["effort_resolved"], "max")
            with self.assertRaises(ValueError):
                resolve_dsh(None, "xhigh", {})


class FakeClient:
    def __init__(self):
        self.files = {}
        self.keys = []

    def write(self, session, path, content, *, key):
        self.files[path] = content
        self.keys.append(key)
        return {"written": True}

    def read(self, session, path):
        return self.files[path]

    def session(self, session):
        return {'remaining_seconds': 120}


class BridgeTests(unittest.TestCase):
    def test_soft_budget_reply_reminds_and_stops_another_optimization_round(self):
        with tempfile.TemporaryDirectory() as directory:
            client = Mock()
            active = {'remaining_seconds': 1, 'budget': {'policy': 'soft', 'remaining_seconds': 1}}
            expired = {'remaining_seconds': 0, 'budget': {'policy': 'soft', 'remaining_seconds': 0,
                'message': 'Submit immediately without another optimization round'}}
            client.session.side_effect = [active, expired]
            client.execute.return_value = {'execution_id': 'e'}
            client.poll.return_value = {'log_base64': '', 'next_offset': 0,
                'state': 'complete', 'exit_code': 0, 'truncated': False}
            bridge = Bridge(client, 'session', Path(directory) / 'tools.jsonl')
            result = bridge.call('execute', {'command': 'already started'})
            assert client.execute.call_args.args[2] is None
            assert result['budget'] == expired['budget']
            client.session.side_effect = None
            client.session.return_value = expired
            reply = dispatch(bridge, {'id': 1, 'method': 'tools/call',
                'params': {'name': 'execute', 'arguments': {'command': 'another round'}}})
            assert reply['result']['isError'] is True
            assert 'submit immediately' in reply['result']['content'][0]['text']
            client.submit.return_value = {'accepted': True}
            assert bridge.call('submit', {'path': 'output/final.gds'})['accepted'] is True

    def test_expiry_between_status_and_execution_does_not_block_final_submission(self):
        from benchmarking.client import ClientError

        with tempfile.TemporaryDirectory() as directory:
            client = Mock()
            client.session.return_value = {'remaining_seconds': .1, 'budget': {'policy': 'soft'}}
            client.execute.side_effect = ClientError('budget_exhausted', 'expired', status=409)
            bridge = Bridge(client, 'session', Path(directory) / 'tools.jsonl')
            result = dispatch(bridge, {'id': 1, 'method': 'tools/call',
                'params': {'name': 'execute', 'arguments': {'command': 'too late'}}})
            assert result['result']['isError'] is True
            assert not bridge.pending.exists()
            client.submit.return_value = {'accepted': True}
            assert bridge.call('submit', {'path': 'output/final.gds'})['accepted'] is True

    def test_handshake_tools_roundtrip_and_unlimited_mutations_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient()
            log = Path(directory) / "tools.jsonl"
            bridge = Bridge(client, "session", log)
            response = dispatch(bridge, {"id": 1, "method": "initialize"})
            self.assertIn("tools", response["result"]["capabilities"])
            self.assertIsNone(dispatch(bridge, {"method": "notifications/initialized"}))
            self.assertEqual({t['name'] for t in dispatch(bridge, {"id": 2, "method": "tools/list"})['result']['tools']},
                             {'status', 'read', 'write', 'execute', 'submit', 'check', 'report'})
            written = dispatch(bridge, {"id": 3, "method": "tools/call", "params": {
                "name": "write", "arguments": {"path": "probe.txt", "content": "hello"}}})
            self.assertNotIn("isError", written["result"])
            self.assertEqual(bridge.call("read", {"path": "probe.txt"})["content"], "hello")
            bridge.call("read", {"path": "probe.txt"})  # Next request acknowledges the prior mutation reply.
            restarted = Bridge(client, "session", log)
            blocked = dispatch(restarted, {"id": 4, "method": "tools/call", "params": {
                "name": "write", "arguments": {"path": "probe.txt", "content": "changed"}}})
            self.assertNotIn("isError", blocked["result"])
            for _ in range(100):
                restarted.call("write", {"path": "probe.txt", "content": "changed"})
            self.assertEqual(client.files["probe.txt"], b"changed")
            self.assertEqual(len(set(client.keys)), len(client.keys))

    def test_command_uses_service_allowance_and_accepts_long_explicit_timeout(self):
        # Service limits are the authority; no adapter-only 120-second ceiling.
        with tempfile.TemporaryDirectory() as directory:
            client = Mock()
            client.session.return_value = {"remaining_seconds": 800}
            client.execute.return_value = {"execution_id": "exec"}
            client.poll.return_value = {"log_base64": "", "next_offset": 0,
                                       "state": "complete", "exit_code": 0, "truncated": False}
            bridge = Bridge(client, "session", Path(directory) / "tools.jsonl", command_seconds=700)
            for args, expected in (({}, 700), ({"seconds": 500}, 500), ({"seconds": 1000}, 700)):
                bridge.call("execute", {"command": "eda", **args})
                self.assertEqual(client.execute.call_args.args[2], expected)
            client.session.return_value = {"remaining_seconds": 25}
            bridge.call("execute", {"command": "eda"})
            self.assertEqual(client.execute.call_args.args[2], 25)
            for seconds in (0, -1, True, float("inf"), float("nan")):
                with self.assertRaises(ValueError):
                    bridge.call("execute", {"command": "eda", "seconds": seconds})

    def test_rejects_unknown_tool_and_extra_fields_before_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient()
            bridge = Bridge(client, "session", Path(directory) / "tools.jsonl")
            for name, args in (("host_shell", {"command": "pwd"}),
                               ("write", {"path": "a", "content": "b", "endpoint": "elsewhere"})):
                with self.assertRaises(ValueError):
                    bridge.call(name, args)
            self.assertFalse(client.files)


if __name__ == "__main__":
    unittest.main()


def test_unresolved_tool_blocks_other_mutations_and_replays_original_timeout(tmp_path):
    from benchmarking.client import ClientError
    client = Mock()
    client.session.return_value = {'remaining_seconds': 120}
    client.execute.side_effect = [ClientError('transport_error', 'lost', retryable=True), {'execution_id': 'e'}]
    client.poll.return_value = {'log_base64': '', 'next_offset': 0, 'state': 'complete', 'exit_code': 0, 'truncated': False}
    log = tmp_path / 'tools.jsonl'
    bridge = Bridge(client, 's', log)
    with pytest.raises(ClientError):
        bridge.call('execute', {'command': 'increment'})
    first = client.execute.call_args
    bridge = Bridge(client, 's', log)
    with pytest.raises(ClientError, match='unresolved'):
        bridge.call('execute', {'command': 'different'})
    client.session.return_value = {'remaining_seconds': 20}
    bridge.call('execute', {'command': 'increment'})
    assert client.execute.call_args == first
    assert not bridge.pending.exists()


def test_native_resume_keeps_sandbox_and_explicit_session(tmp_path):
    from helpers.harness import native_session

    selected = {'harness': 'codex', 'model': 'fixture', 'effort_resolved': 'high', 'effort_requested': 'high'}
    env = {'ICLAYOUT_BENCH_TOOL_TIMEOUT_SECONDS': '600', 'ICLAYOUT_BENCH_RESUME_ID': 'session-identity'}
    native_session(tmp_path, 'codex', 'session-identity')
    args = prepare_harness_args(selected, env, {}, tmp_path / 'mcp.json', tmp_path)
    assert args[-3:] == ['resume', 'session-identity', '-']
    assert '--ephemeral' not in args
    assert args[args.index('--sandbox') + 1] == 'read-only'
    native_session(tmp_path, 'claude-code', 'session-identity')
    args = prepare_harness_args(selected | {'harness': 'claude-code'}, env, {}, tmp_path / 'mcp.json', tmp_path)
    assert args[args.index('--resume') + 1] == 'session-identity'
    assert '--no-session-persistence' not in args


def test_bridge_restart_does_not_assume_last_reply_was_delivered(tmp_path):
    from benchmarking.client import ClientError
    client = FakeClient()
    log = tmp_path / 'tools.jsonl'
    Bridge(client, 's', log).call('write', {'path': 'a', 'content': 'once'})
    restarted = Bridge(client, 's', log)
    with pytest.raises(ClientError, match='delivery is unknown'):
        restarted.call('write', {'path': 'a', 'content': 'twice'})
    assert client.files['a'] == b'once'


@pytest.mark.parametrize('harness,expected,continuation,overrides', [
    ('codex', 5, True, None), ('claude-code', 5, True, None), ('dsh', 0, True, None),
    ('kimi-code', 5, True, None), ('zcode', 0, False, None), ('command', 0, False, None),
    ('codex', 5, True, {}), ('codex', 5, True, {'http_attempts': 4}),
    ('codex', 5, False, {'resume_session': False}),
])
def test_recovery_defaults_follow_harness_support(harness, expected, continuation, overrides):
    from benchmarking.participants.config import validate
    from benchmarking.participants.recovery import policy

    row = {'name': 'fixture', 'harness': harness, 'model': 'fixture', 'effort': 'high',
           'tasks': ['fixture'], 'concurrency': 1, 'repetitions': 1}
    if overrides is not None:
        row['recovery'] = overrides
    validate(row)
    settings = policy(row.get('recovery'), harness=harness)
    assert settings['capacity_resumes'] == expected
    assert settings['resume_session'] is continuation
    assert settings['http_attempts'] == (4 if overrides == {'http_attempts': 4} else 3)
    assert settings['backoff_seconds'] == 1
    assert settings['max_backoff_seconds'] == 8
    assert settings['network_resumes'] == (0 if harness in {'command', 'zcode'} else 5)


def test_dsh_supports_manual_resume_but_not_ambiguous_capacity_recovery():
    from benchmarking.participants.config import validate
    from benchmarking.participants.recovery import DISABLED
    row = {'name': 'fixture', 'harness': 'dsh', 'model': 'fixture', 'effort': 'high',
           'tasks': ['fixture'], 'concurrency': 1, 'repetitions': 1,
           'recovery': DISABLED | {'resume_session': True}}
    validate(row)
    with pytest.raises(ValueError, match='capacity'):
        validate(row | {'recovery': row['recovery'] | {'capacity_resumes': 1}})


@pytest.mark.parametrize('harness,recovery', [
    ('codex', {'capacity_resumes': True}),
    ('codex', {'capacity_backoff_seconds': float('nan')}),
    ('codex', {'capacity_backoff_seconds': 60, 'capacity_max_backoff_seconds': 30}),
    ('command', {'capacity_resumes': 5}),
    ('codex', {'network_resumes': True}),
    ('codex', {'network_backoff_seconds': float('nan')}),
    ('codex', {'network_backoff_seconds': 60, 'network_max_backoff_seconds': 30}),
    ('command', {'network_resumes': 5}),
])
def test_capacity_recovery_rejects_invalid_or_unsupported_policies(harness, recovery):
    from benchmarking.participants.config import validate
    from benchmarking.participants.recovery import DISABLED

    with pytest.raises(ValueError, match='capacity|network'):
        validate({'name': 'fixture', 'harness': harness, 'model': 'fixture', 'effort': 'high',
                  'tasks': ['fixture'], 'concurrency': 1, 'repetitions': 1,
                  'recovery': DISABLED | recovery})


@pytest.mark.parametrize('recovery', [[], {'http_attempts': 0}, {'resume_session': 1}, {'unexpected': 3},
                                       {'backoff_seconds': 9}, {'network_resumes': -1}])
def test_recovery_overrides_preserve_validation(recovery):
    from benchmarking.participants.recovery import policy

    with pytest.raises(ValueError):
        policy(recovery, harness='codex')


@pytest.mark.parametrize('resume', [False, True])
def test_codex_preapproves_layout_tools_without_granting_host_execution(tmp_path, resume):
    # Regression for real CLI rejection: "requires approval, but approval policy is never".
    # The public adapter must authorize its MCP server in both launch modes;
    # this checks emitted policy, not a model's compliance with that policy.
    selected = {'harness': 'codex', 'model': 'fixture',
                'effort_resolved': 'high', 'effort_requested': 'high'}
    env = {'ICLAYOUT_BENCH_TOOL_TIMEOUT_SECONDS': '600'}
    if resume:
        from helpers.harness import native_session

        env['ICLAYOUT_BENCH_RESUME_ID'] = 'existing-session'
        native_session(tmp_path, 'codex', 'existing-session')
    args = prepare_harness_args(selected, env, {}, tmp_path / 'mcp.json', tmp_path)
    overrides = dict(args[i + 1].split('=', 1) for i, arg in enumerate(args) if arg == '-c')
    config = {key: json.loads(value) for key, value in overrides.items()}
    assert config['mcp_servers.layout.default_tools_approval_mode'] == 'approve'
    assert config['approval_policy'] == 'never'
    assert args[args.index('--sandbox') + 1] == 'read-only'
    assert config['features.shell_tool'] is False
    assert config['features.unified_exec'] is False
    assert '--ignore-user-config' in args
    assert {key.split('.')[1] for key in config if key.startswith('mcp_servers.')} == {'layout'}


def test_tool_schemes_freeze_files_and_keep_contrasts_in_distinct_outputs(tmp_path):
    """Public config owns tool identity; prior model-only paths collided for A/B runs.

    Extend existing config coverage with user-authored script bytes as the oracle.
    This protects configuration/reuse, not the script's quality or model behavior.
    """
    import sys

    from benchmarking.participants.scheme import check, identity

    script = tmp_path / 'tool.py'
    script.write_text('print("version one")\n')
    config = tmp_path / 'contrast.toml'
    config.write_text('[defaults]\nharness="codex"\nmodel="same-model"\neffort="medium"\n'
                      'tasks=["case"]\nconcurrency=1\nrepetitions=1\n'
                      '[[runs]]\nname="baseline"\n[runs.scheme]\ninstructions="Use built-in resources."\n'
                      '[[runs]]\nname="with-a"\n[runs.scheme]\ninstructions="Use tool A."\n'
                      '[runs.scheme.mcp.a]\ncommand=[' + json.dumps(sys.executable) + ',"tool.py"]\nfiles=["tool.py"]\n')
    baseline, augmented = read_matrix(config)
    assert identity(baseline['scheme']) != identity(augmented['scheme'])
    assert augmented['scheme']['mcp']['a']['command'][1] == str(script)
    check(augmented['scheme'])
    script.write_text('print("version two")\n')
    with pytest.raises(ValueError, match='files changed'):
        check(augmented['scheme'])
    changed = read_matrix(config)[1]
    assert identity(changed['scheme']) != identity(augmented['scheme'])
    config.write_text(config.read_text().replace('instructions="Use tool A."', 'solver_image="mutable:latest"'))
    with pytest.raises(ValueError, match='immutable'):
        read_matrix(config)
