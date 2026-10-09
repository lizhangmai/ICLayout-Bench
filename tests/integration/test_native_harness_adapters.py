"""Installed native CLIs against a local provider fixture; no paid model calls."""

import json
import os
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from benchmarking.participants import adapters, bridge
from benchmarking.participants.adapters.contracts import LaunchContext
from benchmarking.participants.attempt import AttemptState
from benchmarking.participants.evidence import read_traces
from benchmarking.participants.process import execute

pytestmark = pytest.mark.integration


@pytest.fixture
def provider():
    state = {'status': 401, 'code': 'authentication_error', 'message': 'fixture authentication', 'requests': 0}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
            state['authenticated'] = any('fixture-provider-secret' in self.headers.get(name, '')
                                         for name in ('Authorization', 'x-api-key'))
            state['tools'] = [tool.get('name') for tool in request.get('tools', [])]
            state['requests'] += 1
            self.send_response(state['status'])
            if state['status'] == 200:
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                events = [
                    {'type': 'message_start', 'message': {'id': 'msg_fixture', 'type': 'message', 'role': 'assistant',
                     'model': request['model'], 'content': [], 'stop_reason': None, 'stop_sequence': None,
                     'usage': {'input_tokens': 1, 'output_tokens': 0}}},
                    {'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}},
                    {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': 'fixture complete'}},
                    {'type': 'content_block_stop', 'index': 0},
                    {'type': 'message_delta', 'delta': {'stop_reason': 'end_turn', 'stop_sequence': None}, 'usage': {'output_tokens': 2}},
                    {'type': 'message_stop'},
                ]
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


def native_context(root, harness, url):
    if shutil.which(adapters.get(harness).METADATA.executable) is None:
        pytest.skip('native CLI is not installed: ' + harness)
    work = root / '.private/workspace'; work.mkdir(parents=True)
    host = root / 'fixture-host'; host.mkdir()
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(('CODEX_', 'OPENAI_', 'ANTHROPIC_', 'CLAUDE_', 'DEEPSEEK_', 'DSH_', 'ICLAYOUT_BENCH_'))
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
    else:
        env.update(CODEX_HOME=str(host), OPENAI_API_KEY='fixture-provider-secret')
        model, effort = 'gpt-6-astra', 'medium'
    selection = adapters.resolve(harness, model, effort, env)
    if harness == 'dsh':
        # Fault injection checks one native attempt, not provider backoff timing.
        provider = next(row for row in selection.settings['rows'] if row['id'] == 'llm-deepseek')
        provider.setdefault('config', {}).update(baseURL=url, retryPolicy={'mode': 'normal', 'maxRetries': 0})
        env['DEEPSEEK_BASE_URL'] = 'http://127.0.0.1:9'
    adapters.stage_credentials(harness, root / '.private', env)
    mcp = work / 'mcp.json'; mcp.write_text('{"mcpServers":{}}')
    return LaunchContext(selection, mcp, work, root, Path(bridge.__file__), 'Reply only fixture.')


def launch(context):
    argv = adapters.prepare(context)
    if context.selection.condition['harness'] == 'codex':
        # Replace only the provider I/O boundary, leaving the public adapter real.
        config = {'model_provider': 'fixture', 'model_providers.fixture.name': 'fixture',
                  'model_providers.fixture.base_url': context.selection.environment['ICLAYOUT_BENCH_ENDPOINT'] + '/v1',
                  'model_providers.fixture.env_key': 'OPENAI_API_KEY', 'model_providers.fixture.wire_api': 'responses',
                  'model_providers.fixture.request_max_retries': 0, 'model_providers.fixture.stream_max_retries': 0}
        for key, value in config.items():
            argv[-1:-1] = ['-c', key + '=' + json.dumps(value)]
    with (context.output / 'harness.jsonl').open('w') as out, (context.output / 'harness.stderr').open('w') as err:
        return execute(argv, cwd=context.directory, env=context.selection.environment, stdout=out, stderr=err,
                       timeout=20, prompt=context.prompt if context.selection.condition['harness'] != 'dsh' else None)


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


@pytest.mark.parametrize('harness', ['codex', 'claude-code', 'dsh'])
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
