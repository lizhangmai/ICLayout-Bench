"""Observed Kimi Code contracts at worker, recovery and export seams."""

import json
from pathlib import Path

import pytest
import tomli_w

from benchmarking.participants import adapters
from benchmarking.participants.adapters.contracts import (
    LaunchContext,
    ParticipantSelection,
)
from benchmarking.participants.attempt import AttemptState

pytestmark = pytest.mark.unit


@pytest.fixture
def kimi_config(tmp_path):
    home = tmp_path / 'host'
    home.mkdir()
    config = {'default_model': 'fixture/k3',
              'providers': {'fixture': {'type': 'kimi', 'api_key_env': 'FIXTURE_KEY'}},
              'models': {'fixture/k3': {'provider': 'fixture', 'model': 'k3',
                                       'max_context_size': 8192, 'support_efforts': ['high']}}}
    return home, config


def selection(home, config):
    (home / 'config.toml').write_text(tomli_w.dumps(config))
    return adapters.resolve('kimi-code', 'fixture/k3', 'high',
                            {'KIMI_CODE_HOME': str(home), 'FIXTURE_KEY': 'fixture-key',
                             'ICLAYOUT_BENCH_TOOL_TIMEOUT_SECONDS': '120'})


def context(tmp_path, selected):
    work = tmp_path / '.private/workspace'
    work.mkdir(parents=True, exist_ok=True)
    mcp = work / 'mcp.json'
    mcp.write_text('{"mcpServers":{"layout":{"command":"fixture"}}}')
    return LaunchContext(selected, mcp, work, tmp_path, work / 'bridge.py', 'task')


def native_session(output, *, session='session_fixture', model='fixture/k3', effort='high'):
    root = output / '.private/kimi-home/sessions/wd_workspace_fixture' / session
    wire = root / 'agents/main/wire.jsonl'
    wire.parent.mkdir(parents=True, exist_ok=True)
    (root / 'state.json').write_text(json.dumps({'id': session, 'cwd': str((output / '.private/workspace').resolve())}))
    events = [{'type': 'profile.bind', 'profileName': 'layout-participant', 'agentId': 'main',
               'modelAlias': model, 'thinkingEffort': effort,
               'activeToolNames': ['mcp__layout__*'], 'subagents': []},
              {'type': 'context.append_message', 'agentId': 'main',
               'message': {'role': 'assistant', 'content': [
                   {'type': 'thinking', 'thinking': 'retained native reasoning'}]}}]
    wire.write_text(''.join(json.dumps(event) + '\n' for event in events))
    return root, wire


@pytest.mark.parametrize('key', ['oauth/kimi-code', 'kimi-code', 'oauth/custom', 'custom'])
def test_oauth_credentials_cross_worker_pipe_and_reach_native_storage(tmp_path, kimi_config, key):
    home, config = kimi_config
    config['providers']['fixture'] = {'type': 'kimi', 'oauth': {'storage': 'file', 'key': key}}
    token_name = key.removeprefix('oauth/')
    original = home / 'credentials' / (token_name + '.json')
    original.parent.mkdir()
    original.write_text('{"access_token":"fixture-access","refresh_token":"fixture-refresh"}\n')
    selected = selection(home, config)
    selected = ParticipantSelection(**json.loads(json.dumps(selected.launch_payload())))
    argv = adapters.prepare(context(tmp_path / 'participant', selected))
    staged = Path(selected.environment['KIMI_CODE_HOME']) / 'credentials' / original.name
    assert staged.read_bytes() == original.read_bytes()
    assert staged.stat().st_mode & 0o777 == 0o600
    assert 'fixture-access' not in repr(selected) + ' '.join(argv)


@pytest.mark.parametrize('key', ['../escape', '/absolute', 'oauth/', 'oauth/../escape',
                                'oauth/a/b', 'oauth/.hidden', '.hidden'])
def test_oauth_keys_cannot_escape_native_credential_storage(kimi_config, key):
    home, config = kimi_config
    config['providers']['fixture'] = {'type': 'kimi', 'oauth': {'storage': 'file', 'key': key}}
    with pytest.raises(ValueError, match='OAuth'):
        selection(home, config)


@pytest.mark.parametrize('line, category', [
    ('provider.auth_error: 401 Invalid Authentication', 'authentication'),
    ("provider.auth_error: 403 You've reached your 5-hour usage limit", 'quota_exhausted'),
    ("provider.api_error: 403 You've reached your monthly usage limit", 'quota_exhausted'),
    ("provider.auth_error: 403 You've reached your concurrent request limit", 'rate_limit'),
    ('provider.rate_limit: 429 The engine is currently overloaded', 'provider_overloaded'),
    ("provider.rate_limit: 429 We're receiving too many requests", 'rate_limit'),
    ('provider.overloaded: fixture overload', 'provider_overloaded'),
    ('provider.connection_error: connection refused', 'network_transient'),
    ('provider.api_error: 400 fixture request rejected', 'unknown'),
    ('provider fixture has no credential configured', 'harness_configuration'),
    ('provider.api_error: 429 Selected model is at capacity. Please try a different model.', 'rate_limit'),
])
def test_kimi_terminal_errors_use_its_native_protocol(tmp_path, line, category):
    (tmp_path / 'harness.jsonl').write_text('{"role":"meta","type":"system.version","version":"2.1.1"}\n')
    (tmp_path / 'harness.stderr').write_text('error: failed to run prompt: ' + line + '\nSee log: private path\n')
    problem = adapters.harness_failure('kimi-code', tmp_path, exit_code=1)
    assert problem['category'] == category


def test_assistant_text_and_recovered_native_errors_do_not_trigger_capacity_resume(tmp_path):
    (tmp_path / 'harness.jsonl').write_text(json.dumps({'role': 'assistant', 'content':
        'error: failed to run prompt: provider.overloaded: fixture overload'}))
    (tmp_path / 'harness.stderr').write_text('error: failed to run prompt: provider.overloaded: fixture overload\n')
    assert adapters.harness_failure('kimi-code', tmp_path, exit_code=0) is None
    assert adapters.harness_failure('kimi-code', tmp_path, exit_code=1)['category'] == 'provider_overloaded'
    assert adapters.harness_failure('kimi-code', tmp_path, exit_code=1, timed_out=True)['category'] == 'budget_exhausted'


def test_kimi_native_errors_preserve_structured_quota_precedence(tmp_path):
    (tmp_path / 'harness.jsonl').write_text(json.dumps({'type': 'error', 'code': 'insufficient_quota'}))
    (tmp_path / 'harness.stderr').write_text('error: failed to run prompt: provider.overloaded: fixture overload\n')
    assert adapters.harness_failure('kimi-code', tmp_path, exit_code=1)['category'] == 'quota_exhausted'


@pytest.mark.parametrize('harness', ['codex', 'claude-code', 'dsh', 'command'])
def test_kimi_stderr_semantics_do_not_leak_into_other_adapters(tmp_path, harness):
    (tmp_path / 'harness.jsonl').write_text('{"role":"meta","type":"system.version"}\n')
    (tmp_path / 'harness.stderr').write_text('error: failed to run prompt: provider.overloaded: fixture overload\n')
    assert adapters.harness_failure(harness, tmp_path, exit_code=1)['category'] == 'unknown'


def test_capacity_resume_uses_persisted_session_without_overwriting_refreshed_tokens(tmp_path, kimi_config):
    from benchmarking.participants.recovery import continuation_id, policy

    home, config = kimi_config
    config['providers']['fixture'] = {'type': 'kimi', 'oauth': {'storage': 'file', 'key': 'oauth/fixture'}}
    (home / 'credentials').mkdir()
    (home / 'credentials/fixture.json').write_text('{"access_token":"initial-access"}')
    selected = selection(home, config)
    output = tmp_path / 'participant'
    ctx = context(output, selected)
    first = adapters.prepare(ctx)
    assert '--agent-file' in first and '--session' not in first
    _, wire = native_session(output)
    refreshed = Path(selected.environment['KIMI_CODE_HOME']) / 'credentials/fixture.json'
    refreshed.write_text('{"access_token":"refreshed-access"}')
    # Capacity failures do not emit a session.resume_hint: discover only the
    # single persisted native conversation in this attempt's isolated home.
    (output / 'harness.jsonl').write_text('{"role":"meta","type":"system.version"}\n')
    native_id = continuation_id(output, {'harness': 'kimi-code'}, AttemptState(), {'state': 'active'})
    selected.environment['ICLAYOUT_BENCH_RESUME_ID'] = native_id
    resume = adapters.prepare(ctx)
    assert resume[resume.index('--session') + 1] == 'session_fixture'
    assert '--agent-file' not in resume
    assert refreshed.read_text() == '{"access_token":"refreshed-access"}'
    assert wire.exists()
    assert policy(harness='kimi-code')['capacity_resumes'] == 5


def test_kimi_resume_rejects_missing_ambiguous_or_changed_native_binding(tmp_path, kimi_config):
    home, config = kimi_config
    selected = selection(home, config)
    output = tmp_path / 'participant'
    ctx = context(output, selected)
    adapters.prepare(ctx)
    selected.environment['ICLAYOUT_BENCH_RESUME_ID'] = 'session_fixture'
    with pytest.raises(ValueError, match='native session'):
        adapters.prepare(ctx)
    native_session(output, model='different-model')
    with pytest.raises(ValueError, match='binding'):
        adapters.prepare(ctx)
    native_session(output)
    native_session(output, session='another-session')
    assert adapters.session_id('kimi-code', output, AttemptState()) is None


def test_native_reasoning_and_logs_survive_export_without_credentials(tmp_path):
    from benchmarking.participants.evidence import read_traces
    from benchmarking.results.participant_export import traces

    output = tmp_path / 'participant'
    root, wire = native_session(output)
    home = output / '.private/kimi-home'
    (home / 'credentials').mkdir()
    (home / 'credentials/fixture.json').write_text('{"access_token":"refreshed-access","refresh_token":"private-refresh"}')
    (home / 'logs').mkdir()
    (home / 'logs/kimi-code.log').write_text('diagnostic refreshed-access private-refresh scoped-secret')
    (home / 'config.toml').write_text('must not be exported')
    (output / '.private/recovery.json').write_text(json.dumps({'redactions': ['scoped-secret']}))
    (output / 'conditions.json').write_text('{"selection":{"harness":"kimi-code"}}')
    (output / 'harness.jsonl').write_text('{"role":"assistant","content":"visible reply"}\n')
    (output / 'harness.stderr').write_text('diagnostic stderr')
    exported, files = tmp_path / 'result', []
    traces(read_traces(output), exported, files)
    retained = exported / 'native/kimi' / wire.relative_to(home)
    assert retained.read_bytes() == wire.read_bytes()
    log = exported / 'native/kimi/logs/kimi-code.log'
    assert log.read_text() == 'diagnostic <REDACTED> <REDACTED> <REDACTED>'
    assert (exported / 'native/kimi' / (root / 'state.json').relative_to(home)).is_file()
    assert not any('credentials' in name or 'config.toml' in name for name in files)
    assert 'native/kimi/logs/kimi-code.log' in files


def test_runner_continues_kimi_capacity_failure_in_the_same_session_and_exports_wire(tmp_path, kimi_config, monkeypatch):
    import zipfile

    from test_participant_runner import ServiceFixture

    from benchmarking.participants.runner import run_participant

    home, config = kimi_config
    selected = selection(home, config)
    service = ServiceFixture()
    monkeypatch.setattr('benchmarking.participants.runner.Client', lambda *a, **kw: service)
    monkeypatch.setattr('benchmarking.participants.adapters.cli_version', lambda *a: 'kimi 2.1.1')
    monkeypatch.setattr('benchmarking.participants.runner.time.sleep', lambda *a: None)
    launches = []
    output = tmp_path / 'result'

    def execute(argv, *, stdout, stderr, **kwargs):
        launches.append(argv)
        stdout.write('{"role":"meta","type":"system.version","version":"2.1.1"}\n')
        if len(launches) == 1:
            native_session(output)
            stderr.write('error: failed to run prompt: provider.rate_limit: 429 The engine is currently overloaded\n')
            return 1, False
        stdout.write('{"role":"assistant","content":"fixture completion"}\n')
        return 0, False

    monkeypatch.setattr('benchmarking.participants.runner.execute', execute)
    result, error = run_participant(service, {'harness': 'kimi-code', 'task': 'fixture'}, output, selected)
    assert error is None and result['outcome'] == 'no_submission'
    assert len(launches) == 2 and '--agent-file' in launches[0] and '--agent-file' not in launches[1]
    assert launches[1][launches[1].index('--session') + 1] == 'session_fixture'
    summary = json.loads((output / 'harness-summary.json').read_text())
    assert summary['capacity_recovery']['resumes'] == 1
    assert summary['capacity_recovery']['outcome'] == 'recovered'
    assert service.closed == ['fixture-session']
    with zipfile.ZipFile(output / 'observation/participant/native-traces.zip') as archive:
        wire = [name for name in archive.namelist() if name.endswith('/wire.jsonl')]
        assert len(wire) == 1 and b'retained native reasoning' in archive.read(wire[0])


def test_terminal_cleanup_keeps_kimi_native_records(tmp_path):
    from test_participant_runner import terminal_files

    from benchmarking.participants.storage import CaseRecord
    from benchmarking.participants.terminal import finish_case

    record = CaseRecord(tmp_path)
    record.initialize({'endpoint': 'https://fixture', 'plan': [{'model': 'fixture', 'effort': 'high'}]})
    record.begin()
    summary = terminal_files(record.participant)
    summary.update(state='finished', task='fixture', score=None)
    record.record_summary(summary)
    _, wire = native_session(record.participant)
    (record.participant / 'conditions.json').write_text('{"selection":{"harness":"kimi-code"}}')
    original = wire.read_bytes()
    relative = wire.relative_to(record.participant / '.private/kimi-home')
    finish_case(tmp_path)
    assert not record.runtime.exists()
    assert (tmp_path / 'native/kimi' / relative).read_bytes() == original
    result = json.loads(record.manifest.read_text())
    assert 'native/kimi/' + relative.as_posix() in result['files']


def test_provider_api_key_environment_is_redacted_regardless_of_variable_name(kimi_config):
    from benchmarking.participants.credentials import credential_values

    home, config = kimi_config
    selected = selection(home, config)
    assert 'fixture-key' in credential_values(selected.settings)
