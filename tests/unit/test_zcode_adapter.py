"""ZCode connection selection, isolation and credential-safe native evidence."""

import json
import sqlite3
from pathlib import Path

import pytest
from helpers.harness import zcode_session

from benchmarking.participants.attempt.recovery import policy
from benchmarking.participants.harnesses import registry as adapters
from benchmarking.participants.harnesses.contracts import LaunchContext
from benchmarking.participants.harnesses.credentials import credential_values

pytestmark = pytest.mark.unit


def test_recorded_policy_rate_limit_uses_bounded_recovery(tmp_path):
    # Minimized terminal envelope from the 2026-10-14 failed run; no request IDs,
    # provider connection, user content or stack paths are needed to reproduce it.
    event = json.loads((Path(__file__).parents[1] / 'fixtures/agents/zcode-1313.json').read_text())
    (tmp_path / 'harness.jsonl').write_text(json.dumps(event))
    problem = adapters.harness_failure('zcode', tmp_path, exit_code=1)
    assert problem['category'] == 'rate_limit' and problem['retryable']
    assert problem['code'] == 'account_policy_rate_limit'


@pytest.mark.parametrize('attribution,category,retryable', [
    ({'statusCode': 429}, 'unknown', False),
    ({'statusCode': 429, 'reason': 'rate_limited', 'retryable': True}, 'rate_limit', True),
    ({'statusCode': 429, 'providerErrorCode': 'insufficient_quota'}, 'quota_exhausted', False),
    ({'statusCode': 429, 'providerErrorCode': '1312'}, 'provider_overloaded', True),
    ({'statusCode': 429, 'reason': 'provider_overloaded', 'retryable': True}, 'provider_overloaded', True),
    ({'statusCode': 429, 'providerErrorCode': 'unrecognized'}, 'unknown', False),
])
def test_http_429_requires_specific_provider_evidence(tmp_path, attribution, category, retryable):
    event = {'type': 'turn.failed', 'payload': {'error': {
        'code': 'model_request_failed', 'attribution': {'source': 'provider', **attribution}}}}
    (tmp_path / 'harness.jsonl').write_text(json.dumps(event))
    problem = adapters.harness_failure('zcode', tmp_path, exit_code=1)
    assert (problem['category'], problem['retryable']) == (category, retryable)


def profile(home, *, kind='anthropic', file_key=False):
    options = {'baseURL': 'https://fixture.example/v1',
               **({'apiKey': 'selected-fixture-secret'} if file_key else {'apiKeyEnv': 'EXPERIMENT_KEY'})}
    config = {'model': {'main': 'fixture/glm-5.3'}, 'provider': {'fixture': {
        'kind': kind, 'options': options, 'models': {
            'glm-5.3': {'reasoning': {'levels': ['low', 'high', 'max'], 'defaultLevel': 'high'}}}}}}
    (home / 'config.json').write_text(json.dumps(config))
    return config


@pytest.mark.parametrize('kind,wire,file_key', [
    ('anthropic', 'anthropic-messages', False), ('openai', 'openai-responses', False),
    ('openai-compatible', 'openai-chat-completions', False), ('anthropic', 'anthropic-messages', True),
])
def test_selected_api_connection_retains_credentials_only_in_private_inputs(tmp_path, kind, wire, file_key):
    profile(tmp_path, kind=kind, file_key=file_key)
    env = {'EXPERIMENT_KEY': 'selected-fixture-secret', 'ZCODE_MODEL': 'host/different',
           'ZCODE_API_KEY': 'host-secret', 'ANTHROPIC_BASE_URL': 'https://host.example',
           'ZCODE_PERSONAL_PROVIDER_CONFIG_FILE': '/host/credentials.json'}
    selected = adapters.resolve('zcode', 'fixture/glm-5.3', 'max', env, home=tmp_path)
    assert selected.condition['auth_method'] == 'api' and selected.condition['wire_api'] == wire
    assert selected.condition['model'] == 'fixture/glm-5.3' and selected.condition['effort_resolved'] == 'max'
    assert not any(key in selected.environment for key in ['ZCODE_API_KEY', 'ZCODE_MODEL', 'ANTHROPIC_BASE_URL'])
    assert 'selected-fixture-secret' in credential_values(selected.settings)
    assert selected.environment['ZCODE_DATA_BASE_DIR'] == str(tmp_path)
    assert 'selected-fixture-secret' not in json.dumps(selected.condition) + repr(selected)
    assert env['ZCODE_API_KEY'] == 'host-secret'


def test_missing_selected_authentication_or_unsupported_effort_cannot_use_host_defaults(tmp_path):
    config = profile(tmp_path)
    with pytest.raises(ValueError, match='API authentication'):
        adapters.resolve('zcode', 'fixture/glm-5.3', 'high', {'ZCODE_API_KEY': 'host-secret'}, home=tmp_path)
    with pytest.raises(ValueError, match='effort'):
        adapters.resolve('zcode', 'fixture/glm-5.3', 'xhigh', {'EXPERIMENT_KEY': 'selected-fixture-secret'}, home=tmp_path)
    config['hooks'] = {'enabled': True}
    (tmp_path / 'config.json').write_text(json.dumps(config))
    with pytest.raises(ValueError, match='connections only'):
        adapters.resolve('zcode', 'fixture/glm-5.3', 'high', {}, home=tmp_path)


def test_selected_network_connection_reaches_isolated_native_config(tmp_path):
    home = tmp_path / 'selected'; home.mkdir()
    config = profile(home)
    config['network'] = {'httpProxy': 'http://127.0.0.1:7890', 'noProxy': 'localhost,127.0.0.1'}
    source = json.dumps(config)
    (home / 'config.json').write_text(source)
    selected = adapters.resolve('zcode', 'fixture/glm-5.3', 'high',
        {'EXPERIMENT_KEY': 'selected-fixture-secret', 'ZCODE_HTTP_PROXY': 'http://host.example:1'}, home=home)
    output = tmp_path / 'output'; work = output / '.private/workspace'; work.mkdir(parents=True)
    selected.environment['ICLAYOUT_BENCH_TOOL_TIMEOUT_SECONDS'] = '60'
    mcp = work / 'mcp.json'; mcp.write_text('{"mcpServers":{}}')
    adapters.prepare(LaunchContext(selected, mcp, work, output, work / 'bridge.py', 'fixture prompt'))
    native = json.loads((output / '.private/native-home/.zcode/cli/config.json').read_text())
    assert native['network'] == config['network']
    assert selected.condition['network'] == config['network']
    assert 'ZCODE_HTTP_PROXY' not in selected.environment
    assert (home / 'config.json').read_text() == source
    config['network']['httpProxy'] = 'http://user:secret@proxy.example'
    (home / 'config.json').write_text(json.dumps(config))
    with pytest.raises(ValueError, match='httpProxy'):
        adapters.resolve('zcode', 'fixture/glm-5.3', 'high',
                         {'EXPERIMENT_KEY': 'selected-fixture-secret'}, home=home)


@pytest.mark.parametrize('source,reason,category', [
    ('network', 'timeout', 'network_transient'),
    ('network', 'network_error', 'network_transient'),
    ('provider', 'unknown', 'unknown'),
])
def test_terminal_network_attribution_is_classified_without_provider_prose(tmp_path, source, reason, category):
    event = {'type': 'turn.failed', 'payload': {'error': {'code': 'UND_ERR_CONNECT_TIMEOUT',
        'attribution': {'source': source, 'reason': reason, 'exceptionKind': 'transport', 'retryable': True}}}}
    (tmp_path / 'harness.jsonl').write_text(json.dumps(event))
    assert adapters.harness_failure('zcode', tmp_path, exit_code=1)['category'] == category
    event['type'] = 'message.upserted'
    (tmp_path / 'harness.jsonl').write_text(json.dumps(event))
    assert adapters.harness_failure('zcode', tmp_path, exit_code=0) is None


@pytest.mark.parametrize('code,category', [('authentication_error', 'authentication'),
                                         ('insufficient_quota', 'quota_exhausted'),
                                         ('rate_limit_error', 'rate_limit'),
                                         ('overloaded_error', 'provider_overloaded')])
def test_native_terminal_provider_errors_are_read_from_the_zcode_envelope(tmp_path, code, category):
    event = {'type': 'turn.failed', 'payload': {'error': {'type': 'unknown_error',
        'attribution': {'source': 'provider', 'providerErrorCode': code}, 'code': code}}}
    (tmp_path / 'harness.jsonl').write_text(json.dumps(event))
    assert adapters.harness_failure('zcode', tmp_path, exit_code=1)['category'] == category
    event['type'] = 'message.upserted'
    (tmp_path / 'harness.jsonl').write_text(json.dumps(event))
    assert adapters.harness_failure('zcode', tmp_path, exit_code=0) is None


def test_failed_native_summary_cannot_become_a_success_without_error_details(tmp_path):
    events = [{'type': 'message.upserted', 'payload': {'text': 'provider_overloaded'}},
              {'type': 'result', 'projection': {'status': 'error'}}]
    (tmp_path / 'harness.jsonl').write_text('\n'.join(json.dumps(event) for event in events))
    assert adapters.harness_failure('zcode', tmp_path, exit_code=0)['category'] == 'unknown'


def test_launch_isolates_native_home_config_and_exposes_declared_mcp_only(tmp_path):
    home = tmp_path / 'selected'; home.mkdir(); profile(home)
    selected = adapters.resolve('zcode', 'fixture/glm-5.3', 'high',
                                {'EXPERIMENT_KEY': 'selected-fixture-secret', 'HOME': '/original'}, home=home)
    output = tmp_path / 'output'; work = output / '.private/workspace'; work.mkdir(parents=True)
    selected.environment['ICLAYOUT_BENCH_TOOL_TIMEOUT_SECONDS'] = '60'
    mcp = work / 'mcp.json'
    mcp.write_text(json.dumps({'mcpServers': {'layout': {'command': 'fixture-bridge', 'args': []}}}))
    context = LaunchContext(selected, mcp, work, output, work / 'bridge.py', 'fixture prompt')
    argv = adapters.prepare(context)
    runtime = output / '.private/native-home'
    assert selected.environment['HOME'] == str(runtime)
    assert selected.environment['ZCODE_DATA_BASE_DIR'] == str(runtime)
    assert '--prompt' in argv and argv[-1] == context.prompt
    assert 'selected-fixture-secret' not in str(argv)
    config = json.loads((runtime / '.zcode/cli/config.json').read_text())
    assert list(config['mcp']['servers']) == ['layout']
    assert config['features'] == {'mcp': True, 'subagent': False, 'skill': False, 'memory': False}
    assert not config['plugins']['enabled'] and not config['hooks']['enabled']
    assert 'Bash' in argv[argv.index('--disallowed-tools') + 1].split(',')
    connection = json.loads((runtime / '.zcode/v2/provider_config.json').read_text())
    assert connection['config']['defaultModelSelection'] == {
        'providerId': 'fixture', 'modelId': 'glm-5.3', 'options': {'reasoningLevel': 'high'}}
    assert (runtime / '.zcode/v2/provider_config.json').stat().st_mode & 0o777 == 0o600
    trace = runtime / '.zcode/cli/rollout/model-io-session.jsonl'
    trace.parent.mkdir(); trace.write_text('{"thinking":"retained native reasoning"}\n')
    assert adapters.native_traces('zcode', output) == {'zcode/rollout/model-io-session.jsonl': trace.read_bytes()}
    assert adapters.credential_redactions('zcode', output) == {'selected-fixture-secret'}
    assert policy(harness='zcode')['resume_session'] is True
    with pytest.raises(ValueError, match='persisted'):
        selected.environment['ICLAYOUT_BENCH_RESUME_ID'] = 'sess_announced'
        adapters.prepare(context)


def resume_context(root):
    home = root / 'selected'; home.mkdir(); profile(home)
    selected = adapters.resolve('zcode', 'fixture/glm-5.3', 'high', {'EXPERIMENT_KEY': 'fixture-secret'}, home=home)
    selected.environment['ICLAYOUT_BENCH_TOOL_TIMEOUT_SECONDS'] = '60'
    work = root / '.private/workspace'; work.mkdir(parents=True)
    mcp = work / 'mcp.json'
    mcp.write_text(json.dumps({'mcpServers': {'layout': {'command': 'fixture-bridge', 'args': [],
        'env': {'ICLAYOUT_BENCH_SESSION': 'service-original', 'ICLAYOUT_BENCH_TOKEN': 'scoped-secret'}}}}))
    context = LaunchContext(selected, mcp, work, root, work / 'bridge.py', 'continue original')
    adapters.prepare(context)
    return context


@pytest.mark.parametrize('change', ['none', 'cwd', 'model', 'effort', 'tools', 'scope', 'ambiguous', 'pending', 'missing'])
def test_resume_requires_persisted_conversation_and_frozen_bindings(tmp_path, change):
    context = resume_context(tmp_path)
    db_path = zcode_session(tmp_path)
    with sqlite3.connect(db_path) as db:
        if change == 'cwd':
            db.execute("UPDATE session SET directory = '/elsewhere'")
        elif change in {'model', 'effort'}:
            binding = json.loads(db.execute('SELECT data FROM session_entry').fetchone()[0])
            if change == 'model':
                binding['modelSelection']['modelId'] = 'another'
            else:
                binding['modelSelection']['options']['reasoningLevel'] = 'max'
            db.execute('UPDATE session_entry SET data = ?', (json.dumps(binding),))
        elif change == 'ambiguous':
            db.execute("INSERT INTO session SELECT 'sess_another', parent_id, directory, path, revert, time_archived FROM session")
        elif change == 'pending':
            db.execute('INSERT INTO part (message_id, session_id, data) VALUES (?, ?, ?)', ('user', 'sess_fixture', json.dumps({
                'type': 'tool', 'tool': 'mcp__layout__write', 'state': {'status': 'running'}})))
        elif change == 'missing':
            db.execute('DELETE FROM message')
    if change in {'tools', 'scope'}:
        servers = json.loads(context.mcp.read_text())
        if change == 'tools':
            servers['mcpServers']['layout']['command'] = 'different-tool'
        else:
            servers['mcpServers']['layout']['env']['ICLAYOUT_BENCH_SESSION'] = 'another-session'
        context.mcp.write_text(json.dumps(servers))
    context.selection.environment['ICLAYOUT_BENCH_RESUME_ID'] = 'sess_fixture'
    if change in {'none', 'pending'}:
        argv = adapters.prepare(context)
        assert argv[argv.index('--resume') + 1] == 'sess_fixture'
        assert argv[-1] == context.prompt
    else:
        with pytest.raises(ValueError, match='ZCode'):
            adapters.prepare(context)
