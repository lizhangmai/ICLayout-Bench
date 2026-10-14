"""ZCode connection selection, isolation and credential-safe native evidence."""

import json

import pytest

from benchmarking.participants import adapters
from benchmarking.participants.adapters.contracts import LaunchContext
from benchmarking.participants.credentials import credential_values
from benchmarking.participants.recovery import policy

pytestmark = pytest.mark.unit


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
    assert policy(harness='zcode')['resume_session'] is False
    with pytest.raises(ValueError, match='continuation'):
        selected.environment['ICLAYOUT_BENCH_RESUME_ID'] = 'sess_announced'
        adapters.prepare(context)
