"""Installed native CLIs against a local provider fixture; no paid model calls."""

import json
import os
import shutil
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import tomli_w

from benchmarking.execution.process import execute
from benchmarking.participants import mcp as bridge
from benchmarking.participants.attempt.evidence import read_traces
from benchmarking.participants.attempt.state import AttemptState
from benchmarking.participants.harnesses import registry as adapters
from benchmarking.participants.harnesses.contracts import LaunchContext
from benchmarking.participants.isolation import NativeRuntime
from benchmarking.protocol import PROTOCOL

pytestmark = pytest.mark.integration


@pytest.fixture
def provider():
    state = {'status': 401, 'code': 'authentication_error', 'message': 'fixture authentication', 'requests': 0}

    class Handler(BaseHTTPRequestHandler):
        def service_reply(self, value):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'protocol': PROTOCOL, **value}).encode())

        def do_GET(self):
            self.service_reply({'state': 'active', 'remaining_seconds': 60})

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
            if 'resourceLogs' in request:
                state['proxied_telemetry'] = state.get('proxied_telemetry', 0) + 1
                self.send_error(502)
                return
            if self.path.endswith('/files'):
                state['writes'] = state.get('writes', 0) + 1
                self.service_reply({'path': request['path'], 'written': 4})
                return
            if 'model' not in request:
                self.service_reply({})
                return
            state['authenticated'] = any('fixture-provider-secret' in self.headers.get(name, '')
                                         for name in ('Authorization', 'x-api-key'))
            state.setdefault('payloads', []).append(request)
            state['tools'] = [tool.get('name') for tool in request.get('tools', [])]
            state['model'] = request.get('model')
            state['request_path'] = self.path
            state['effort'] = request.get('output_config', {}).get('effort')
            state['requests'] += 1
            if state.get('tool_sent') and not state.get('resumed'):
                state.update(status=429, code='1313', message='fixture policy rate limit')
            self.send_response(state['status'])
            if state['status'] == 200:
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                if self.path.endswith('/responses'):
                    message = {'id': 'msg_fixture', 'type': 'message', 'role': 'assistant', 'status': 'completed',
                               'content': [{'type': 'output_text', 'text': 'fixture complete', 'annotations': []}]}
                    response = {'id': 'resp_fixture', 'object': 'response', 'created_at': 1792100000,
                                'status': 'completed', 'model': request['model'], 'output': [message],
                                'usage': {'input_tokens': 100, 'output_tokens': 20, 'total_tokens': 120,
                                    'input_tokens_details': {'cached_tokens': 60, 'cache_write_tokens': 0},
                                    'output_tokens_details': {'reasoning_tokens': 5}}}
                    events = [{'type': 'response.created', 'response': {**response, 'status': 'in_progress', 'output': []}},
                              {'type': 'response.output_item.added', 'output_index': 0, 'item': message},
                              {'type': 'response.output_text.delta', 'output_index': 0, 'content_index': 0,
                               'item_id': 'msg_fixture', 'delta': 'fixture complete'},
                              {'type': 'response.output_item.done', 'output_index': 0, 'item': message},
                              {'type': 'response.completed', 'response': response}]
                    for event in events:
                        if state.get('stream_delay'):
                            time.sleep(state['stream_delay'])
                        self.wfile.write(('event: ' + event['type'] + '\ndata: ' + json.dumps(event) + '\n\n').encode())
                        self.wfile.flush()
                    self.wfile.flush()
                    return
                if self.path.endswith('/chat/completions'):
                    base = {'id': 'chat_fixture', 'object': 'chat.completion.chunk', 'created': 1792100000,
                            'model': request['model']}
                    events = [{**base, 'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': 'fixture complete'},
                                                   'finish_reason': None}]},
                              {**base, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}],
                               'usage': {'prompt_tokens': 100, 'prompt_cache_hit_tokens': 60,
                                         'prompt_cache_miss_tokens': 40, 'completion_tokens': 20, 'total_tokens': 120}}]
                    for event in events:
                        self.wfile.write(('data: ' + json.dumps(event) + '\n\n').encode())
                    self.wfile.write(b'data: [DONE]\n\n')
                    self.wfile.flush()
                    return
                events = [
                    {'type': 'message_start', 'message': {'id': 'msg_fixture', 'type': 'message', 'role': 'assistant',
                     'model': request['model'], 'content': [], 'stop_reason': None, 'stop_sequence': None,
                     'usage': {'input_tokens': 40, 'cache_read_input_tokens': 60, 'output_tokens': 0}}},
                    {'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}},
                    {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': 'fixture complete'}},
                    {'type': 'content_block_stop', 'index': 0},
                    {'type': 'message_delta', 'delta': {'stop_reason': 'end_turn', 'stop_sequence': None}, 'usage': {'output_tokens': 20}},
                    {'type': 'message_stop'},
                ]
                if state.get('tool_once') and not state.get('tool_sent'):
                    events[1:4] = [
                        {'type': 'content_block_start', 'index': 0, 'content_block': {
                            'type': 'tool_use', 'id': 'call_fixture', 'name': 'mcp__layout__write', 'input': {}}},
                        {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'input_json_delta',
                            'partial_json': '{"path":"output.txt","content":"once"}'}},
                        {'type': 'content_block_stop', 'index': 0},
                    ]
                    events[4]['delta']['stop_reason'] = 'tool_use'
                    state['tool_sent'] = True
                for event in events:
                    self.wfile.write(('event: ' + event['type'] + '\ndata: ' + json.dumps(event) + '\n\n').encode())
                self.wfile.flush()
                return
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'type': 'error', 'error': {'type': state['code'],
                                                                   'code': state['code'], 'message': state['message']}}).encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    state['url'] = f'http://127.0.0.1:{server.server_port}'
    yield state
    server.shutdown(); thread.join(); server.server_close()


def native_context(root, harness, url, *, zcode_effort='high'):
    if shutil.which(adapters.get(harness).METADATA.executable) is None:
        pytest.skip('native CLI is not installed: ' + harness)
    work = root / '.private/workspace'; work.mkdir(parents=True)
    host = root / 'fixture-host'; host.mkdir()
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(('CODEX_', 'OPENAI_', 'ANTHROPIC_', 'CLAUDE_', 'DEEPSEEK_', 'DSH_', 'KIMI_', 'ZCODE_', 'ZAI_', 'ICLAYOUT_BENCH_'))
           and 'proxy' not in key.lower()}
    env.update(ICLAYOUT_BENCH_ENDPOINT=url, ICLAYOUT_BENCH_TOKEN='fixture-scoped-secret',
               ICLAYOUT_BENCH_SESSION='fixture-session', ICLAYOUT_BENCH_PARTICIPANT_TOOL_LOG=str(root / 'tools.jsonl'),
               ICLAYOUT_BENCH_COMMAND_SECONDS='20', ICLAYOUT_BENCH_TOOL_TIMEOUT_SECONDS='20',
               ICLAYOUT_BENCH_NATIVE_ID='e0b0bd21-c1bf-4d09-909e-01063f03105e',
               ICLAYOUT_BENCH_RECOVERY='{"http_attempts":1,"backoff_seconds":0,"max_backoff_seconds":0,"resume_session":false}')
    if harness == 'claude-code':
        env.update(CLAUDE_CONFIG_DIR=str(host), ANTHROPIC_API_KEY='fixture-provider-secret', ANTHROPIC_BASE_URL=url,
                   CLAUDE_CODE_MAX_RETRIES='0', CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1',
                   DISABLE_AUTOUPDATER='1', API_TIMEOUT_MS='5000')
        model, effort = 'claude-sonnet-4-6', 'medium'
    elif harness == 'dsh':
        env.update(DSH_HOME=str(host), DEEPSEEK_API_KEY='fixture-provider-secret', DEEPSEEK_BASE_URL=url)
        model, effort = 'deepseek-flash', 'high'
    elif harness == 'zcode':
        (host / 'config.json').write_text(json.dumps({'provider': {'fixture': {
            'kind': 'anthropic', 'options': {'baseURL': url, 'apiKeyEnv': 'FIXTURE_PROVIDER_KEY'},
            'models': {'glm-5.3': {'reasoning': {'levels': ['low', 'high', 'max']}}}}}}))
        env['FIXTURE_PROVIDER_KEY'] = 'fixture-provider-secret'
        model, effort = 'fixture/glm-5.3', zcode_effort
    elif harness == 'kimi-code':
        config = {'default_model': 'fixture/k3',
                  'providers': {'fixture': {'type': 'anthropic', 'base_url': url, 'api_key_env': 'FIXTURE_PROVIDER_KEY'}},
                  'models': {'fixture/k3': {'provider': 'fixture', 'model': 'k3', 'max_context_size': 8192,
                                            'max_output_size': 1024, 'support_efforts': ['high']}}}
        (host / 'config.toml').write_text(tomli_w.dumps(config))
        env.update(KIMI_CODE_HOME=str(host), FIXTURE_PROVIDER_KEY='fixture-provider-secret')
        model, effort = 'fixture/k3', 'high'
    else:
        env.update(CODEX_HOME=str(host), OPENAI_API_KEY='fixture-provider-secret')
        model, effort = 'gpt-6-astra', 'medium'
    selection = adapters.resolve(harness, model, effort, env, **({'home': host} if harness == 'zcode' else {}))
    if harness == 'dsh':
        # Fault injection checks one native attempt, not provider backoff timing.
        provider = next(row for row in selection.settings['rows'] if row['id'] == 'llm-deepseek')
        provider.setdefault('config', {}).update(baseURL=url, retryPolicy={'mode': 'normal', 'maxRetries': 0})
        env['DEEPSEEK_BASE_URL'] = 'http://127.0.0.1:9'
    adapters.stage_credentials(harness, root / '.private', env)
    mcp = work / 'mcp.json'; mcp.write_text('{"mcpServers":{}}')
    if harness == 'zcode':
        mcp.write_text(json.dumps({'mcpServers': {'layout': {'command': sys.executable,
            'args': ['-I', str(Path(bridge.__file__))],
            'env': {k: v for k, v in selection.environment.items() if k.startswith('ICLAYOUT_BENCH_')}}}}))
    return LaunchContext(selection, mcp, work, root, Path(bridge.__file__), 'Reply only fixture.')


@pytest.mark.parametrize('effort', ['high', 'max'])
def test_zcode_native_api_uses_selected_model_credentials_and_only_declared_tools(tmp_path, provider, effort):
    provider.update(status=200)
    context = native_context(tmp_path, 'zcode', provider['url'], zcode_effort=effort)
    assert launch(context) == (0, False)
    assert provider['authenticated'] and provider['requests'] >= 1
    assert provider['model'] == 'glm-5.3' and provider['effort'] == effort
    assert provider['tools'] and all(name.startswith('mcp__layout__') for name in provider['tools'])
    events = [json.loads(line) for line in (tmp_path / 'harness.jsonl').read_text().splitlines()]
    assert events[-1]['type'] == 'result' and events[-1]['response'] == 'fixture complete'
    assert adapters.native_traces('zcode', tmp_path)


def test_zcode_native_authentication_failure_is_terminal(tmp_path, provider):
    context = native_context(tmp_path, 'zcode', provider['url'])
    context.selection.environment['ZCODE_MODEL_RETRY_MAX_RETRIES'] = '0'
    exit_code, timed_out = launch(context)
    assert not timed_out
    assert provider['authenticated'] and provider['requests'] >= 1
    assert adapters.harness_failure('zcode', tmp_path, exit_code)['category'] == 'authentication'


def test_zcode_policy_recovery_keeps_delivered_tools_and_same_native_conversation(tmp_path, provider):
    from benchmarking.participants.attempt.recovery import continuation_id

    provider.update(status=200, tool_once=True)
    context = native_context(tmp_path, 'zcode', provider['url'], zcode_effort='max')
    context.selection.environment['ZCODE_MODEL_RETRY_MAX_RETRIES'] = '0'
    assert launch(context) == (1, False)
    assert provider['writes'] == 1
    problem = adapters.harness_failure('zcode', tmp_path, 1)
    assert problem['category'] == 'rate_limit' and problem['retryable']
    original_id = continuation_id(tmp_path, {'harness': 'zcode'}, AttemptState())
    assert original_id
    context.selection.environment['ICLAYOUT_BENCH_RESUME_ID'] = original_id
    provider.update(status=200, resumed=True)
    assert launch(context) == (0, False)
    assert adapters.session_id('zcode', tmp_path, AttemptState()) == original_id
    assert provider['writes'] == 1
    assert provider['model'] == 'glm-5.3' and provider['effort'] == 'max'
    assert all(name.startswith('mcp__layout__') for name in provider['tools'])


def test_zcode_selected_proxy_routes_model_requests_and_keeps_local_mcp(tmp_path, provider):
    provider.update(status=200)
    context = native_context(tmp_path, 'zcode', provider['url'])
    home = tmp_path / 'fixture-host'
    config = json.loads((home / 'config.json').read_text())
    config['provider']['fixture']['options']['baseURL'] = 'http://zcode-provider.invalid'
    config['network'] = {'httpProxy': provider['url'], 'noProxy': '127.0.0.1,localhost'}
    (home / 'config.json').write_text(json.dumps(config))
    selected = adapters.resolve('zcode', 'fixture/glm-5.3', 'high', context.selection.environment, home=home)
    context = LaunchContext(selected, context.mcp, context.directory, context.output, context.bridge, context.prompt)
    assert launch(context) == (0, False)
    assert provider['request_path'] == 'http://zcode-provider.invalid/v1/messages'
    assert provider['authenticated'] and provider['model'] == 'glm-5.3' and provider['effort'] == 'high'
    assert provider['tools'] and all(name.startswith('mcp__layout__') for name in provider['tools'])


def launch(context):
    with adapters.observe_usage(context.selection.condition['harness'], context.output, context.selection.environment):
        dependencies = []
        if context.selection.condition['harness'] == 'zcode':
            # This installation uses a reviewed shell launcher for a separate
            # bundled JS program. Expose that program, never its project root.
            import shlex
            launcher = Path(shutil.which('zcode')).read_text()
            entry = next((word for word in shlex.split(launcher) if word.endswith('.cjs')), None)
            if entry:
                dependencies.append(str(Path(entry).parent))
        with NativeRuntime(context, runtime_paths=dependencies) as runtime:
            return _launch(runtime.context, runtime)


def _launch(context, runtime):
    argv = adapters.prepare(context)
    if context.selection.condition['harness'] == 'codex' and 'codex_connection' not in context.selection.settings:
        # Replace only the provider I/O boundary, leaving the public adapter real.
        config = {'model_provider': 'fixture', 'model_providers.fixture.name': 'fixture',
                  'model_providers.fixture.base_url': context.selection.environment['ICLAYOUT_BENCH_ENDPOINT'] + '/v1',
                  'model_providers.fixture.env_key': 'OPENAI_API_KEY', 'model_providers.fixture.wire_api': 'responses',
                  'model_providers.fixture.request_max_retries': 0, 'model_providers.fixture.stream_max_retries': 0}
        for key, value in config.items():
            argv[-1:-1] = ['-c', key + '=' + json.dumps(value)]
    with (context.output / 'harness.jsonl').open('w') as out, (context.output / 'harness.stderr').open('w') as err:
        argv, env = runtime.command(argv)
        return execute(argv, cwd=context.directory, env=env, stdout=out, stderr=err,
                       timeout=20, prompt=context.prompt if context.selection.condition['harness'] != 'dsh' else None)


@pytest.mark.parametrize('harness', ['codex', 'claude-code', 'dsh', 'kimi-code', 'zcode'])
def test_native_initial_request_excludes_undeclared_host_context(tmp_path, provider, harness):
    provider.update(status=200)
    context = native_context(tmp_path, harness, provider['url'])
    # Both home discovery and walking ancestors of the working directory must
    # be isolated, even if a vendor adds another automatic discovery mechanism.
    canaries = ['undeclared_home_skill_948ad', 'undeclared_project_skill_72bf9']
    host_home = tmp_path / 'unreviewed-home'
    for root, name in zip([host_home, tmp_path], canaries, strict=True):
        skill = root / '.agents/skills' / name
        skill.mkdir(parents=True)
        (skill / 'SKILL.md').write_text(
            f'---\nname: {name}\ndescription: {name} automatic discovery probe\n---\n{name}\n')
    (tmp_path / '.git').mkdir()
    (tmp_path / 'AGENTS.md').write_text('undeclared_project_rule_91fbd\n')
    context.selection.environment.update(HOME=str(host_home),
                                         UNDECLARED_CONTEXT_HINT='undeclared_environment_479ac')
    assert launch(context) == (0, False)
    assert provider.get('payloads'), (tmp_path / 'harness.stderr').read_text()
    payload = json.dumps(provider['payloads'], ensure_ascii=False)
    if harness == 'codex':
        # Newer Responses clients declare tools in input.additional_tools and
        # deferred namespace messages rather than the top-level tools field.
        assert 'mcp__layout' in payload
        assert 'skill-creator' in payload  # This CLI's bundled system skill remains available.
    else:
        assert provider['tools'] and any('layout' in name for name in provider['tools'])
    for value in [*canaries, 'undeclared_project_rule_91fbd', 'undeclared_environment_479ac']:
        assert value not in payload


@pytest.mark.parametrize('harness', ['codex', 'claude-code', 'dsh', 'kimi-code', 'zcode'])
def test_native_usage_is_collected_from_official_cli_outputs_without_paid_requests(tmp_path, provider, harness):
    from benchmarking.results.usage import summarize_usage

    provider.update(status=200)
    if harness == 'codex':
        provider['stream_delay'] = .01
    context = native_context(tmp_path, harness, provider['url'])
    assert launch(context) == (0, False)
    agent = (tmp_path / 'harness.jsonl').read_bytes()
    native = adapters.native_traces(harness, tmp_path)
    report = summarize_usage(adapters.usage(harness, agent, native), model=context.selection.condition['model'])
    assert report['tokens']['input_tokens'] == 100
    assert report['tokens']['cached_input_tokens'] == 60
    assert report['tokens']['output_tokens'] == 20
    assert report['api_seconds'] is not None and report['api_seconds'] > 0
    if harness == 'codex':
        assert report['api_seconds'] >= .03
    assert b'fixture-provider-secret' not in json.dumps(report).encode()


def test_codex_loopback_telemetry_bypasses_inherited_model_proxy(tmp_path, provider):
    from benchmarking.results.usage import summarize_usage

    provider.update(status=200, stream_delay=.01)
    context = native_context(tmp_path, 'codex', provider['url'])
    context.selection.settings['codex_connection'] = {
        'model_provider': 'fixture', 'model_providers': {'fixture': {
            'name': 'fixture', 'base_url': 'http://codex-provider.invalid/v1',
            'env_key': 'OPENAI_API_KEY', 'wire_api': 'responses',
            'request_max_retries': 0, 'stream_max_retries': 0}}}
    env = context.selection.environment
    env.update(HTTP_PROXY=provider['url'], HTTPS_PROXY=provider['url'], ALL_PROXY=provider['url'],
               NO_PROXY='localhost', no_proxy='localhost')
    assert launch(context) == (0, False)
    native = adapters.native_traces('codex', tmp_path)
    report = summarize_usage(adapters.usage('codex', (tmp_path / 'harness.jsonl').read_bytes(), native),
                             model=context.selection.condition['model'])
    assert report['tokens']['output_tokens'] == 20
    assert report['api_seconds'] is not None and report['api_seconds'] >= .03
    assert provider['request_path'] == 'http://codex-provider.invalid/v1/responses'
    assert not provider.get('proxied_telemetry')


@pytest.mark.parametrize('effort', ['high', 'max'])
@pytest.mark.parametrize('credential_source', ['env', 'file'])
def test_dsh_native_uses_explicit_effort_and_isolated_credentials(tmp_path, provider, effort, credential_source):
    provider.update(status=200)
    context = native_context(tmp_path, 'dsh', provider['url'])
    context.selection.condition['effort_resolved'] = effort
    if credential_source == 'file':
        env = context.selection.environment
        credentials = Path(env['DSH_HOME']) / '.credentials.yaml'
        credentials.write_text('version: 1\nrefs:\n  DEEPSEEK_API_KEY: fixture-provider-secret\n')
        credentials.chmod(0o600)
        env.pop('DEEPSEEK_API_KEY')
    assert launch(context) == (0, False)
    assert provider['authenticated']
    assert provider['model'] == 'deepseek-flash'
    assert provider['effort'] == effort
    assert provider['tools'] and all(name.startswith('mcp__layout__') for name in provider['tools'])


def test_claude_custom_model_with_unknown_native_price_uses_explicit_api_price_snapshot(tmp_path, provider):
    from benchmarking.results.usage import summarize_usage

    provider.update(status=200)
    context = native_context(tmp_path, 'claude-code', provider['url'])
    context.selection.condition['model'] = 'glm-5.3'
    assert launch(context) == (0, False)
    evidence = adapters.usage('claude-code', (tmp_path / 'harness.jsonl').read_bytes(),
                              adapters.native_traces('claude-code', tmp_path))
    pricing = {'currency': 'USD', 'source': 'https://docs.z.ai/guides/overview/pricing', 'as_of': '2026-10-16',
               'input_per_million': 1.4, 'cache_read_per_million': .26,
               'cache_write_per_million': 1.4, 'output_per_million': 4.4}
    report = summarize_usage(evidence, model='glm-5.3', pricing=pricing)
    assert report['cost'] == pytest.approx(.0001596)
    assert report['cost_source'] == 'api_token_pricing'


@pytest.mark.parametrize('harness,status,code,message,expected', [
    ('claude-code', 401, 'authentication_error', 'fixture authentication', 'authentication'),
    ('claude-code', 529, 'overloaded_error', 'fixture capacity', 'provider_overloaded'),
    ('claude-code', 400, 'invalid_request_error', 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.', 'quota_exhausted'),
    ('claude-code', 429, 'rate_limit_error', 'fixture rate limit', 'rate_limit'),
    ('dsh', 401, 'authentication_error', 'fixture authentication', 'authentication'),
    ('dsh', 402, 'insufficient_quota', 'fixture insufficient balance', 'quota_exhausted'),
    ('dsh', 429, 'rate_limit_error', 'fixture rate limit', 'rate_limit'),
    ('dsh', 500, 'api_error', 'fixture internal error', 'unknown'),
    ('codex', 401, 'invalid_api_key', 'fixture authentication', 'authentication'),
])
def test_native_provider_failure_has_classification_and_complete_history(tmp_path, provider, harness, status, code, message, expected):
    provider.update(status=status, code=code, message=message)
    context = native_context(tmp_path, harness, provider['url'])
    exit_code, timed_out = launch(context)
    assert exit_code == 1 and not timed_out
    assert provider['requests'] >= 1
    problem = adapters.harness_failure(harness, tmp_path, exit_code, timed_out)
    assert problem['category'] == expected
    assert adapters.session_id(harness, tmp_path, AttemptState(native_id=context.selection.environment['ICLAYOUT_BENCH_NATIVE_ID']))
    (tmp_path / 'conditions.json').write_text(json.dumps({'selection': context.selection.condition}))
    assert read_traces(tmp_path).native
    if harness == 'dsh':
        assert provider['authenticated']
        assert provider['tools'] and all(name.startswith('mcp__layout__') for name in provider['tools'])


@pytest.mark.parametrize('harness', ['codex', 'claude-code', 'dsh', 'zcode'])
def test_native_resume_adopts_original_history_and_private_home(tmp_path, provider, harness):
    context = native_context(tmp_path, harness, provider['url'])
    assert launch(context) == (1, False)
    state = AttemptState(native_id=context.selection.environment['ICLAYOUT_BENCH_NATIVE_ID'])
    original_id = adapters.session_id(harness, tmp_path, state)
    assert original_id
    home_var = adapters.get(harness).METADATA.home_environment
    original_home = context.selection.environment[home_var]
    (tmp_path / 'harness.jsonl').rename(tmp_path / 'launch-1-harness.jsonl')
    (tmp_path / 'harness.stderr').rename(tmp_path / 'launch-1-harness.stderr')
    if harness != 'codex':
        provider.update(status=200)
    context.selection.environment['ICLAYOUT_BENCH_RESUME_ID'] = original_id
    exit_code = 1 if harness == 'codex' else 0
    assert launch(context) == (exit_code, False)
    assert context.selection.environment[home_var] == original_home
    assert adapters.session_id(harness, tmp_path, state) == original_id
    problem = adapters.harness_failure(harness, tmp_path, exit_code=exit_code)
    assert problem['category'] == 'authentication' if harness == 'codex' else problem is None


@pytest.mark.parametrize('file_auth', [False, True])
def test_codex_explicit_home_routes_native_api_auth_to_declared_provider(tmp_path, provider, file_auth):
    import tomli_w

    context = native_context(tmp_path, 'codex', provider['url'])
    home = tmp_path / 'experiment-home'; home.mkdir()
    connection = {'name': 'fixture', 'base_url': provider['url'] + '/v1', 'wire_api': 'responses',
                  'request_max_retries': 0, 'stream_max_retries': 0}
    env = context.selection.environment.copy()
    env.update(CODEX_API_KEY='unrelated-host-key', OPENAI_BASE_URL='http://127.0.0.1:9')
    if file_auth:
        connection['requires_openai_auth'] = True
        (home / 'auth.json').write_text('{"OPENAI_API_KEY":"fixture-provider-secret"}')
    else:
        connection['env_key'] = 'EXPERIMENT_PROVIDER_KEY'
        env['EXPERIMENT_PROVIDER_KEY'] = 'fixture-provider-secret'
    config = {'cli_auth_credentials_store': 'file', 'model_provider': 'fixture',
              'model_providers': {'fixture': connection}}
    (home / 'config.toml').write_text(tomli_w.dumps(config))
    selected = adapters.resolve('codex', 'gpt-6-astra', 'medium', env, home=home)
    adapters.stage_credentials('codex', tmp_path / '.private', selected.environment, selected.settings)
    context = LaunchContext(selected, context.mcp, context.directory, context.output, context.bridge, context.prompt)
    assert launch(context) == (1, False)
    assert provider['authenticated'] and provider['requests'] >= 1
    assert adapters.harness_failure('codex', tmp_path, exit_code=1)['category'] == 'authentication'
    assert adapters.session_id('codex', tmp_path, AttemptState())
    assert 'fixture-provider-secret' not in json.dumps(selected.condition) + str(adapters.prepare(context))
