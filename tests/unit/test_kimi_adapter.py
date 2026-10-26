"""Observed Kimi Code contracts at worker, recovery and export seams."""

import json
import tomllib
from pathlib import Path

import pytest
import tomli_w

from benchmarking.participants.attempt.state import AttemptState
from benchmarking.participants.harnesses import registry as adapters
from benchmarking.participants.harnesses.contracts import (
    LaunchContext,
    ParticipantSelection,
)

pytestmark = pytest.mark.unit
CONCURRENT_REQUEST_LIMIT = "provider.auth_error: 403 You've reached your concurrent request limit. Please wait for your ongoing requests to finish and try again."


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


def test_explicit_native_home_selects_kimi_configuration_and_managed_oauth(tmp_path, kimi_config):
    home, config = kimi_config
    config['providers']['fixture'] = {'type': 'kimi', 'oauth': {'storage': 'file', 'key': 'oauth/kimi-code'}}
    (home / 'config.toml').write_text(tomli_w.dumps(config))
    store = home / 'credentials'; store.mkdir()
    token = store / 'kimi-code.json'; token.write_text('{"access_token":"chosen-kimi-token"}')
    selected = adapters.resolve('kimi-code', 'fixture/k3', 'high',
                                {'KIMI_CODE_HOME': str(tmp_path / 'missing-host'),
                                 'ICLAYOUT_BENCH_TOOL_TIMEOUT_SECONDS': '120'}, home=home)
    ctx = context(tmp_path, selected)
    adapters.prepare(ctx)
    assert selected.settings['native_home'] == str(home)
    assert selected.settings['credential_home'] == str(home)
    assert (tmp_path / '.private/kimi-home/credentials').resolve() == store
    assert 'chosen-kimi-token' not in json.dumps(selected.condition) + repr(selected)


def context(tmp_path, selected):
    work = tmp_path / '.private/workspace'
    work.mkdir(parents=True, exist_ok=True)
    mcp = work / 'mcp.json'
    mcp.write_text('{"mcpServers":{"layout":{"command":"fixture"}}}')
    return LaunchContext(selected, mcp, work, tmp_path, work / 'bridge.py', 'task')


@pytest.mark.parametrize('configured,expected', [(None, 10), (1, 1), (17, 17)])
def test_native_attempt_limit_reaches_isolated_cli_without_environment_overrides(tmp_path, kimi_config, configured, expected):
    home, config = kimi_config
    if configured is not None:
        config['loop_control'] = {'max_attempts_per_step': configured, 'max_steps_per_turn': 1}
    selected = selection(home, config)
    original = (home / 'config.toml').read_bytes()
    selected.environment.update(KIMI_LOOP_MAX_ATTEMPTS_PER_STEP='999', KIMI_LOOP_MAX_RETRIES_PER_STEP='999')
    selected = ParticipantSelection(**json.loads(json.dumps(selected.launch_payload())))
    adapters.prepare(context(tmp_path / 'participant', selected))
    native_home = Path(selected.environment['KIMI_CODE_HOME'])
    generated = tomllib.loads((native_home / 'config.toml').read_text())
    assert generated['loop_control'] == {'max_attempts_per_step': expected}
    assert selected.condition['native_max_attempts_per_step'] == expected
    assert not any(key.startswith('KIMI_LOOP_') for key in selected.environment)
    assert (home / 'config.toml').read_bytes() == original


@pytest.mark.parametrize('value', [0, True, '10'])
def test_invalid_native_attempt_limit_is_rejected_before_launch(kimi_config, value):
    home, config = kimi_config
    config['loop_control'] = {'max_attempts_per_step': value}
    with pytest.raises(ValueError, match='max_attempts_per_step.*positive integer'):
        selection(home, config)


def test_changed_native_attempt_limit_cannot_resume_frozen_conditions(tmp_path, kimi_config, monkeypatch):
    from helpers.participant import ServiceFixture

    from benchmarking.participants.attempt.recovery import policy
    from benchmarking.participants.attempt.state import ParticipantAttempt

    monkeypatch.setattr('benchmarking.participants.harnesses.registry.cli_version', lambda *a: 'kimi 2.3.1')
    home, config = kimi_config
    config['loop_control'] = {'max_attempts_per_step': 3}
    selected = selection(home, config)
    output = tmp_path / 'participant'
    output.mkdir()
    row = {'harness': 'kimi-code', 'task': 'fixture'}
    recovery = policy({'capacity_resumes': 2}, harness='kimi-code')
    service = ServiceFixture()
    attempt = ParticipantAttempt.open(service, row, output, selected.condition, selected.environment, '', recovery)
    assert attempt.conditions['selection']['native_max_attempts_per_step'] == 3
    assert attempt.conditions['recovery']['capacity_resumes'] == 2
    original = (output / 'conditions.json').read_bytes()
    config['loop_control']['max_attempts_per_step'] = 7
    changed = selection(home, config)
    with pytest.raises(ValueError, match='Cannot resume changed participant conditions'):
        ParticipantAttempt.open(service, row, output, changed.condition, changed.environment, '', recovery)
    assert (output / 'conditions.json').read_bytes() == original


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


@pytest.mark.parametrize('key', ['oauth/kimi-code', 'custom'])
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
    ('The provided authorization grant is invalid', 'authentication'),
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
    assert problem['stop_dispatch'] == (category in {'authentication', 'quota_exhausted', 'harness_configuration'})


def test_assistant_text_and_recovered_native_errors_do_not_trigger_capacity_resume(tmp_path):
    events = [{'role': 'meta', 'type': 'turn.step.retrying', 'failed_attempt': 1,
               'next_attempt': 2, 'max_attempts': 3, 'delay_ms': 500,
               'error_name': 'APIProviderRateLimitError', 'status_code': 429},
              {'role': 'assistant', 'content':
               'error: failed to run prompt: provider.overloaded: fixture overload'}]
    (tmp_path / 'harness.jsonl').write_text(''.join(json.dumps(event) + '\n' for event in events))
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


def test_oauth_refresh_survives_continuation_and_the_next_case(tmp_path, kimi_config):
    import shutil

    from benchmarking.files import atomic_write
    from benchmarking.participants.attempt.recovery import continuation_id, policy

    home, config = kimi_config
    config['providers']['fixture'] = {'type': 'kimi', 'oauth': {'storage': 'file', 'key': 'oauth/fixture'}}
    (home / 'credentials').mkdir()
    (home / 'credentials/fixture.json').write_text('{"access_token":"initial-access"}')
    selected = selection(home, config)
    worker_payload = json.dumps(selected.launch_payload())
    output = tmp_path / 'participant'
    ctx = context(output, selected)
    first = adapters.prepare(ctx)
    assert '--agent-file' in first and '--session' not in first
    _, wire = native_session(output)
    refreshed = Path(selected.environment['KIMI_CODE_HOME']) / 'credentials/fixture.json'
    atomic_write(refreshed, b'{"access_token":"refreshed-access"}')
    # Capacity failures do not emit a session.resume_hint: discover only the
    # single persisted native conversation in this attempt's isolated home.
    (output / 'harness.jsonl').write_text('{"role":"meta","type":"system.version"}\n')
    native_id = continuation_id(output, {'harness': 'kimi-code'}, AttemptState())
    selected.environment['ICLAYOUT_BENCH_RESUME_ID'] = native_id
    resume = adapters.prepare(ctx)
    assert resume[resume.index('--session') + 1] == 'session_fixture'
    assert '--agent-file' not in resume
    assert refreshed.read_text() == '{"access_token":"refreshed-access"}'
    next_selected = ParticipantSelection(**json.loads(worker_payload))
    adapters.prepare(context(tmp_path / 'next-case', next_selected))
    next_token = Path(next_selected.environment['KIMI_CODE_HOME']) / 'credentials/fixture.json'
    assert next_token.read_bytes() == refreshed.read_bytes()
    assert (home / 'credentials/fixture.json').read_bytes() == refreshed.read_bytes()
    assert (Path(next_selected.environment['KIMI_CODE_HOME']) / 'oauth').resolve() == (home / 'oauth').resolve()
    assert wire.exists()
    assert policy(harness='kimi-code')['capacity_resumes'] == 5
    shutil.rmtree(output)
    assert next_token.read_text() == '{"access_token":"refreshed-access"}'


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
    from benchmarking.participants.attempt.evidence import read_traces
    from benchmarking.results.package import traces

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


@pytest.mark.parametrize('terminal_error,stop', [
    ('provider.rate_limit: 429 The engine is currently overloaded', 'success'),
    (CONCURRENT_REQUEST_LIMIT, 'success'),
    (CONCURRENT_REQUEST_LIMIT, 'unanswered_tool'),
    *[(CONCURRENT_REQUEST_LIMIT, stop) for stop in ('pause_-15', 'pause_130')],
    ("provider.rate_limit: 429 We're receiving too many requests", 'success'),
    *[(CONCURRENT_REQUEST_LIMIT, stop) for stop in
      ('mixed_failure', 'signal', 'resume_disabled', 'quota', 'retry_after')],
])
def test_runner_continues_kimi_capacity_failure_in_the_same_session_and_exports_wire(tmp_path, kimi_config, monkeypatch, terminal_error, stop):
    import zipfile
    from unittest.mock import patch

    from helpers.participant import ServiceFixture

    from benchmarking.participants.attempt.runner import run_participant

    home, config = kimi_config
    config['loop_control'] = {'max_attempts_per_step': 3}
    selected = selection(home, config)
    service = ServiceFixture()
    service.remaining = 1000
    monkeypatch.setattr('benchmarking.participants.attempt.runner.Client', lambda *a, **kw: service)
    monkeypatch.setattr('benchmarking.participants.harnesses.registry.cli_version', lambda *a: 'kimi 2.1.1')
    monkeypatch.setattr('benchmarking.participants.attempt.recovery.capacity_delay', lambda settings, n: 30 * 2 ** n)
    launches, delays, timeouts = [], [], []
    output = tmp_path / 'result'
    row = {'harness': 'kimi-code', 'task': 'fixture'}
    if stop == 'resume_disabled':
        row['recovery'] = {'resume_session': False}

    def sleep(seconds):
        delays.append(seconds)
        service.remaining -= seconds

    monkeypatch.setattr('benchmarking.participants.attempt.runner.time.sleep', sleep)

    def execute(argv, *, stdout, stderr, **kwargs):
        launches.append(argv)
        timeouts.append(kwargs['timeout'])
        stdout.write('{"role":"meta","type":"system.version","version":"2.1.1"}\n')
        if stop == 'retry_after':
            stdout.write('{"type":"error","code":"rate_limit_error","retry_after":400}\n')
        if len(launches) == 1:
            _, wire = native_session(output)
            if stop == 'unanswered_tool':
                with wire.open('a') as stream:
                    for event in [
                        {'type': 'step.begin', 'uuid': 'interrupted-step'},
                        {'type': 'tool.call', 'uuid': 'interrupted-call', 'stepUuid': 'interrupted-step',
                         'toolCallId': 'original-call', 'name': 'mcp__layout__execute',
                         'args': {'command': 'native tool'}},
                    ]:
                        stream.write(json.dumps({'type': 'context.append_loop_event',
                            'agentId': 'main', 'event': event}) + '\n')
            stderr.write('error: failed to run prompt: ' + terminal_error + '\n')
            if stop == 'mixed_failure':
                stderr.write('error: failed to run prompt: provider.api_error: 400 fixture request rejected\n')
            return (-15 if stop == 'signal' else 1), False
        if stop.startswith('pause_'):
            return int(stop.removeprefix('pause_')), False
        if stop == 'quota':
            stderr.write("error: failed to run prompt: provider.auth_error: 403 You've reached your 5-hour usage limit\n")
            return 1, False
        stdout.write('{"role":"assistant","content":"fixture completion"}\n')
        return 0, False

    monkeypatch.setattr('benchmarking.participants.attempt.runner.execute', execute)
    with patch.object(service, 'create', wraps=service.create) as create:
        result, error = run_participant(service, row, output, selected)
        assert create.call_count == 1
        frozen = json.loads((output / 'conditions.json').read_text())
        assert frozen['selection']['native_max_attempts_per_step'] == 3
        assert frozen['recovery']['capacity_resumes'] == 5
        native_config = tomllib.loads((Path(selected.environment['KIMI_CODE_HOME']) / 'config.toml').read_text())
        assert native_config['loop_control']['max_attempts_per_step'] == 3
        summary = json.loads((output / 'harness-summary.json').read_text())
        for argv in launches[1:]:
            assert argv[argv.index('--session') + 1] == 'session_fixture'
        if stop.startswith('pause_'):
            assert error == 'cli_exit_' + stop.removeprefix('pause_')
            assert result['state'] == 'active' and result['session_id'] == 'fixture-session'
            assert service.closed == [] and len(launches) == 2 and delays == [30]
            assert summary['capacity_recovery']['resumes'] == 1
            assert json.loads((output / '.private/recovery.json').read_text())['phase'] == 'suspended'
            return
        if stop not in {'success', 'unanswered_tool'}:
            assert error == ('cli_exit_-15' if stop == 'signal' else 'cli_exit_1')
            assert len(launches) == (2 if stop == 'quota' else 1)
            assert service.closed == (['fixture-session'] if stop in {'quota', 'resume_disabled'} else [])
            if stop in {'quota', 'retry_after'}:
                assert summary['capacity_recovery']['outcome'] == {
                    'quota': 'stopped_on_other_error',
                    'retry_after': 'retry_after_exceeds_cap'}[stop]
            else:
                assert 'capacity_recovery' not in summary and not delays
            return
    assert error is None and result['outcome'] == 'no_submission'
    assert len(launches) == 2 and '--agent-file' in launches[0] and '--agent-file' not in launches[1]
    assert launches[1][launches[1].index('--session') + 1] == 'session_fixture'
    summary = json.loads((output / 'harness-summary.json').read_text())
    assert summary['capacity_recovery']['resumes'] == 1
    assert summary['capacity_recovery']['outcome'] == 'recovered'
    assert delays == [30] and timeouts == [1000, 970]
    assert service.closed == ['fixture-session']
    with zipfile.ZipFile(output / 'observation/participant/native-traces.zip') as archive:
        wire = [name for name in archive.namelist() if name.endswith('/wire.jsonl')]
        assert len(wire) == 1 and b'retained native reasoning' in archive.read(wire[0])


def test_terminal_cleanup_keeps_kimi_native_records(tmp_path):
    from helpers.participant import terminal_files

    from benchmarking.participants.attempt.storage import CaseRecord
    from benchmarking.participants.attempt.worker import finish_case

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
    from benchmarking.participants.harnesses.credentials import credential_values

    home, config = kimi_config
    selected = selection(home, config)
    assert 'fixture-key' in credential_values(selected.settings)
