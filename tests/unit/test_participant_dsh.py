"""Check invocation-scoped DSH overlays without making model calls."""
import json
import tempfile
import unittest
from pathlib import Path

import pytest
import zstandard

from benchmarking.participants import adapters
from benchmarking.participants.adapters.contracts import (
    LaunchContext,
    ParticipantSelection,
)
from benchmarking.participants.adapters.dsh import prepare

pytestmark = pytest.mark.unit


def native_session(output, *, session='session-fixture', cwd=None, content='full native reasoning'):
    path = output / '.private/native-home/sessions/workspace' / session / 'session.v4.jsonl.zstd'
    path.parent.mkdir(parents=True, exist_ok=True)
    header = {'type': 'session', 'version': 4, 'id': session,
              'cwd': str(cwd or (output / '.private/workspace').resolve())}
    compressor = zstandard.ZstdCompressor()
    path.write_bytes(compressor.compress((json.dumps(header) + '\n').encode()) +
                     compressor.compress((json.dumps({'type': 'assistant/attempt', 'data': content}) + '\n').encode()))
    return path


def test_dsh_native_credentials_and_refreshed_store_are_isolated(tmp_path):
    host = tmp_path / 'host'; host.mkdir()
    (host / '.credentials.yaml').write_text('version: 1\nrefs:\n  CUSTOM_REF: original-fixture-secret\n')
    (host / '.env').write_text('DEEPSEEK_API_KEY="native-env-secret"\n')
    private = tmp_path / 'participant/.private'; private.mkdir(parents=True)
    env = {'DSH_HOME': str(host)}
    redactions = adapters.stage_credentials('dsh', private, env)
    assert {'original-fixture-secret', 'native-env-secret'} <= redactions
    native = Path(env['DSH_HOME']) / '.credentials.yaml'
    assert native.read_bytes() == (host / '.credentials.yaml').read_bytes()
    assert native.stat().st_mode & 0o777 == 0o600
    native.write_text('version: 1\nrefs:\n  CUSTOM_REF: rotated-fixture-secret\n')
    assert 'rotated-fixture-secret' in adapters.stage_credentials('dsh', private, {'DSH_HOME': str(host)})
    assert 'rotated-fixture-secret' in native.read_text()
    assert 'original-fixture-secret' in (host / '.credentials.yaml').read_text()


def test_dsh_provider_credential_reference_is_redacted_regardless_of_env_name(monkeypatch):
    from benchmarking.participants.credentials import credential_values

    rows = [{'id': 'llm-deepseek', 'config': {'apiKeyEnv': 'CUSTOM_PROVIDER_KEY'}}]
    selected = {'provider': 'deepseek-official', 'model': 'deepseek-flash'}
    monkeypatch.setattr('benchmarking.participants.adapters.dsh.configuration', lambda env: (rows, {}, selected))
    selection = adapters.resolve('dsh', None, 'high', {'CUSTOM_PROVIDER_KEY': 'custom-provider-secret'})
    assert 'custom-provider-secret' in credential_values(selection.settings)


def test_dsh_resumes_exact_persisted_main_session(tmp_path):
    from benchmarking.participants.attempt import AttemptState
    from benchmarking.participants.recovery import continuation_id

    work = tmp_path / '.private/workspace'; work.mkdir(parents=True)
    condition = {'harness': 'dsh', 'provider': 'deepseek-official', 'model': 'deepseek-flash', 'effort_resolved': 'high'}
    env = {'ICLAYOUT_BENCH_TOOL_TIMEOUT_SECONDS': '120', 'ICLAYOUT_BENCH_RESUME_ID': 'session-fixture'}
    ctx = LaunchContext(ParticipantSelection(condition, env, {'rows': [], 'settings': {}}),
                        work / 'mcp.json', work, tmp_path, work / 'bridge.py', 'continue')
    with pytest.raises(ValueError, match='native session'):
        prepare(ctx)
    native_session(tmp_path)
    sid = continuation_id(tmp_path, {'harness': 'dsh'}, AttemptState(), {})
    assert sid == 'session-fixture'
    argv = prepare(ctx)
    assert '--json' in argv and argv[argv.index('--session-id') + 1] == sid
    native_session(tmp_path, session='session-other')
    with pytest.raises(ValueError, match='persisted native'):
        continuation_id(tmp_path, {'harness': 'dsh'}, AttemptState(), {})


def test_dsh_decompresses_all_frames_before_trace_redaction(tmp_path):
    from benchmarking.participants.evidence import read_traces

    content = 'thinking ' + 'x' * 16000 + ' rotated-fixture-secret'
    raw = native_session(tmp_path, content=content)
    home = tmp_path / '.private/native-home'
    (home / '.credentials.yaml').write_text('version: 1\nrefs:\n  CUSTOM_REF: rotated-fixture-secret\n')
    (tmp_path / 'conditions.json').write_text('{"selection":{"harness":"dsh"}}')
    (tmp_path / 'harness.jsonl').write_text('{"type":"thinking","text":"rotated-fixture-secret"}')
    traces = read_traces(tmp_path)
    assert len(traces.native) == 1
    exported = next(iter(traces.native.values()))
    assert b'x' * 16000 in exported and b'<REDACTED>' in exported
    assert b'rotated-fixture-secret' not in traces.agent + exported
    assert all(name.endswith('.jsonl') and 'credentials' not in name for name in traces.native)
    assert raw.is_file()


def test_dsh_terminal_cleanup_retains_complete_decompressed_records(tmp_path):
    from test_participant_runner import terminal_files

    from benchmarking.participants.storage import CaseRecord
    from benchmarking.participants.terminal import finish_case

    record = CaseRecord(tmp_path)
    record.initialize({'endpoint': 'https://fixture', 'plan': [{'model': 'fixture', 'effort': 'high'}]})
    record.begin()
    summary = terminal_files(record.participant)
    summary.update(state='finished', task='fixture', score=None)
    record.record_summary(summary)
    wire = native_session(record.participant, content='complete native reasoning ' + 'x' * 16000)
    relative = wire.relative_to(record.participant / '.private/native-home').with_suffix('')
    (record.participant / 'conditions.json').write_text('{"selection":{"harness":"dsh"}}')
    finish_case(tmp_path)
    assert not record.runtime.exists()
    exported = tmp_path / 'native/dsh' / relative
    assert b'complete native reasoning ' + b'x' * 16000 in exported.read_bytes()
    assert 'native/dsh/' + relative.as_posix() in json.loads(record.manifest.read_text())['files']


def test_dsh_old_cli_is_rejected_before_model_dispatch(monkeypatch):
    from benchmarking.participants.adapters.dsh import configuration

    monkeypatch.setattr('benchmarking.participants.adapters.dsh.subprocess.check_output', lambda *a, **kw: 'Usage: dsh task')
    with pytest.raises(ValueError, match='--json and --session-id'):
        configuration({})


class DshPatchTests(unittest.TestCase):
    def test_default_effort_is_omitted_and_host_tools_are_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = {'rows': [{'id': 'tool-bash'}, {'id': 'tool-fs'}, {'id': 'tool-subagent'},
                                 {'id': 'agent-instructions'}, {'id': 'mcp-other'},
                                 {'id': 'llm-deepseek', 'config': {'baseURL': 'http://fixture-gateway', 'apiKey': 'profile-key-fixture'}},
                                 {'id': 'plan-mode'}, {'id': 'plugin-manager'}],
                        'mcp_servers': {'a': {'command': '/tools/a', 'args': ['serve'], 'env': {'A_API_KEY': 'private-a'}}},
                        'settings': {'llm-pi-ai': {'providers': {}}, 'unrelated': {'flag': True}}}
            original = json.dumps(settings, sort_keys=True)
            env = {'ICLAYOUT_BENCH_TOKEN': 'scoped-fixture', 'ICLAYOUT_BENCH_TOOL_TIMEOUT_SECONDS': '600',
                   'DEEPSEEK_API_KEY': 'provider-fixture'}
            condition = {'provider': 'deepseek-official', 'model': 'deepseek-flash', 'effort_resolved': None}
            args = prepare(LaunchContext(ParticipantSelection(condition, env, settings), root / 'mcp.json', root, root / 'output', root / 'bridge.py', 'task'))
            self.assertEqual(args[:3], ['dsh', '--profile', 'headless'])
            self.assertIn('--json', args)
            self.assertNotIn('provider-fixture', json.dumps(args))
            self.assertNotIn('private-a', json.dumps(args))
            config = json.loads((root / 'dsh-settings.json').read_text())
            self.assertNotIn('reasoningEffort', config['agent-default-model'])
            self.assertNotIn('unrelated', config)
            overlay = json.loads((root / 'dsh.patch.json').read_text())
            provider = next(row['config'] for row in overlay if row.get('id') == 'llm-deepseek')
            self.assertEqual(provider['baseURL'], 'http://fixture-gateway')
            self.assertEqual(provider['apiKey'], 'profile-key-fixture')
            self.assertNotIn('profile-key-fixture', ' '.join(args))
            disabled = {r['id'] for r in overlay if r.get('disabled')}
            self.assertTrue({'tool-bash', 'tool-fs', 'tool-subagent', 'agent-instructions', 'mcp-other', 'plan-mode', 'plugin-manager'} <= disabled)
            added = {r['insert'][0]['config']['serverName']: r['insert'][0]['config'] for r in overlay if 'insert' in r}
            self.assertEqual(added['a']['command'], '/tools/a')
            self.assertEqual(added['a']['env'], {'A_API_KEY': 'private-a'})
            mcp = next(r['insert'][0] for r in overlay if 'insert' in r)
            self.assertEqual(mcp['config']['env']['ICLAYOUT_BENCH_TOKEN'], 'scoped-fixture')
            self.assertNotIn('DEEPSEEK_API_KEY', mcp['config']['env'])
            self.assertEqual((root / 'dsh-settings.json').stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.dumps(settings, sort_keys=True), original)
            condition['effort_resolved'] = 'max'
            prepare(LaunchContext(ParticipantSelection(condition, env, settings), root / 'mcp.json', root, root / 'output', root / 'bridge.py', 'task'))
            config = json.loads((root / 'dsh-settings.json').read_text())
            self.assertEqual(config['agent-default-model']['reasoningEffort'], 'max')


if __name__ == '__main__':
    unittest.main()
