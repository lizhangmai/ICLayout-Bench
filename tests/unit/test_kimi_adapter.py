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


def native_tool_delivery(output, wire, *, tool='execute', wire_format='messages'):
    from types import SimpleNamespace

    from benchmarking.participants.bridge import Bridge, dispatch

    executed = []

    def execute(sid, command, seconds, *, key):
        executed.append((command, key))
        return {'execution_id': 'fixture-execution', 'state': 'complete'}

    def write(sid, path, content, *, key):
        executed.append((path, key))
        return {'path': path, 'size_bytes': len(content)}

    def submit(sid, path, *, key):
        executed.append((path, key))
        return {'submission_id': 'fixture-submission', 'sequence': 1}

    client = SimpleNamespace(
        session=lambda sid: {'state': 'active', 'remaining_seconds': 600, 'capabilities': ['process-feedback']},
        execute=execute, write=write, submit=submit,
        check=lambda sid, seconds, *, key: execute(sid, 'check', seconds, key=key),
        poll=lambda *args, **kwargs: {'state': 'complete', 'exit_code': 0, 'log_base64': '',
                                     'next_offset': 0, 'truncated': False},
    )
    bridge = Bridge(client, 'fixture-session', output / 'tools.jsonl')
    arguments = {'execute': {'command': 'echo fixture'}, 'write': {'path': 'fixture.py', 'content': 'fixture'},
                 'submit': {'path': 'output/final.gds'}, 'check': {}}[tool]
    response = dispatch(bridge, {'id': 1, 'method': 'tools/call',
                                'params': {'name': tool, 'arguments': arguments}})
    messages = [
        {'role': 'assistant', 'toolCalls': [{'type': 'function', 'id': 'tool_fixture',
            'name': 'mcp__layout__' + tool, 'arguments': json.dumps(arguments)}]},
        {'role': 'tool', 'toolCallId': 'tool_fixture', 'content': response['result']['content']},
    ]
    if wire_format == 'loop':
        records = [{'type': 'context.append_loop_event', 'agentId': 'main', 'event': event}
                   for event in [
                       {'type': 'step.begin', 'uuid': 'step_fixture', 'step': 1,
                        'turnId': 'turn_fixture'},
                       {'type': 'tool.call', 'uuid': 'call_fixture', 'stepUuid': 'step_fixture',
                        'toolCallId': 'tool_fixture', 'name': 'mcp__layout__' + tool,
                        'args': arguments},
                       {'type': 'tool.result', 'parentUuid': 'call_fixture',
                        'toolCallId': 'tool_fixture',
                        'result': {'output': response['result']['content'][0]['text'], 'durationMs': 1}},
                   ]]
    else:
        records = [{'type': 'agent.message.appended',
                    'message': {'message': message, 'meta': {}}} for message in messages]
    with wire.open('a') as stream:
        for record in records:
            stream.write(json.dumps(record) + '\n')
    return bridge, executed


@pytest.mark.parametrize('tool,wire_format', [
    ('execute', 'messages'), ('execute', 'loop'), ('write', 'loop'), ('submit', 'loop'), ('check', 'loop'),
])
def test_persisted_tool_reply_permits_same_session_continuation_without_replay(tmp_path, tool, wire_format):
    from benchmarking.participants.recovery import continuation_id

    _, wire = native_session(tmp_path)
    _, executed = native_tool_delivery(tmp_path, wire, tool=tool, wire_format=wire_format)
    status = {'state': 'active', 'remaining_seconds': 600, 'active_execution_id': None}
    native_id = continuation_id(tmp_path, {'harness': 'kimi-code'}, AttemptState(), status)
    assert native_id == 'session_fixture'
    assert not (tmp_path / 'tools.delivery.json').exists()
    assert len(executed) == 1
    assert continuation_id(tmp_path, {'harness': 'kimi-code'}, AttemptState(), status) == native_id
    assert len(executed) == 1


@pytest.mark.parametrize('wire_format', ['messages', 'loop'])
def test_confirmation_survives_interruption_before_delivery_marker_cleanup(tmp_path, monkeypatch, wire_format):
    from benchmarking.participants.recovery import continuation_id

    _, wire = native_session(tmp_path)
    _, executed = native_tool_delivery(tmp_path, wire, wire_format=wire_format)
    marker = tmp_path / 'tools.delivery.json'
    original_unlink = Path.unlink

    def interrupted_unlink(path, *args, **kwargs):
        if path == marker:
            raise OSError('fixture interruption before cleanup')
        return original_unlink(path, *args, **kwargs)

    status = {'state': 'active', 'remaining_seconds': 600}
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'unlink', interrupted_unlink)
        with pytest.raises(ValueError, match='Unresolved tool operation'):
            continuation_id(tmp_path, {'harness': 'kimi-code'}, AttemptState(), status)
    assert marker.exists()
    assert continuation_id(tmp_path, {'harness': 'kimi-code'}, AttemptState(), status) == 'session_fixture'
    assert not marker.exists() and len(executed) == 1


@pytest.mark.parametrize('boundary', ['step_end', 'next_step', 'repeated_call', 'after_error', 'after_undo', 'mirrored_messages'])
def test_kimi_loop_delivery_accepts_the_latest_reply_across_step_boundaries(tmp_path, boundary):
    from benchmarking.participants.recovery import continuation_id

    _, wire = native_session(tmp_path)
    bridge, executed = native_tool_delivery(tmp_path, wire, wire_format='loop')
    events = [json.loads(line) for line in wire.read_text().splitlines()]
    if boundary == 'step_end':
        events.insert(-1, {'type': 'context.append_loop_event', 'agentId': 'main',
                           'event': {'type': 'step.end', 'uuid': 'step_fixture'}})
    elif boundary == 'next_step':
        events.append({'type': 'context.append_loop_event', 'agentId': 'main',
                       'event': {'type': 'step.begin', 'uuid': 'next_step'}})
    elif boundary == 'mirrored_messages':
        call, reply = events[-2]['event'], events[-1]['event']
        events.extend([{'type': 'agent.message.appended', 'kind': 'event',
                        'message': {'message': message, 'meta': {}}} for message in [
                            {'role': 'assistant', 'toolCalls': [{'type': 'function', 'id': call['toolCallId'],
                                'name': call['name'], 'arguments': json.dumps(call['args'])}]},
                            {'role': 'tool', 'toolCallId': reply['toolCallId'],
                             'content': [{'type': 'text', 'text': reply['result']['output']}]},
                        ]])
    else:
        if boundary == 'after_error':
            events[-1]['event']['result']['isError'] = True
        elif boundary == 'after_undo':
            events.append({'type': 'context.undo', 'agentId': 'main'})
        second = bridge.call('execute', {'command': 'echo fixture'})
        events.extend([{'type': 'context.append_loop_event', 'agentId': 'main', 'event': event}
                       for event in [
                           {'type': 'step.begin', 'uuid': 'second_step'},
                           {'type': 'tool.call', 'uuid': 'second_call', 'stepUuid': 'second_step',
                            'toolCallId': 'second_tool', 'name': 'mcp__layout__execute',
                            'args': {'command': 'echo fixture'}},
                           {'type': 'tool.result', 'parentUuid': 'second_call', 'toolCallId': 'second_tool',
                            'result': {'output': json.dumps(second)}},
                       ]])
    wire.write_text(''.join(json.dumps(event) + '\n' for event in events))
    assert continuation_id(tmp_path, {'harness': 'kimi-code'}, AttemptState(),
                           {'state': 'active', 'remaining_seconds': 600}) == 'session_fixture'
    assert not (tmp_path / 'tools.delivery.json').exists()
    assert len(executed) == (1 if boundary in {'step_end', 'next_step', 'mirrored_messages'} else 2)


@pytest.mark.parametrize('problem', [
    'missing_reply', 'assistant_text', 'invalid_content', 'wrong_arguments', 'missing_call_id',
    'corrupt_wire', 'stale_reply', 'new_unanswered_call', 'reused_call_id', 'changed_marker',
    'missing_bridge_result', 'corrupt_bridge_row', 'pending_tool', 'active_execution',
])
def test_unproven_tool_delivery_never_authorizes_continuation(tmp_path, problem):
    """Legacy messages retain parsing and bridge guard coverage.

    Shared call/result matching counterexamples are owned by the current loop
    protocol test below, whose successful normalized exchange is checked above.
    """
    from benchmarking.participants.recovery import continuation_id

    _, wire = native_session(tmp_path)
    bridge, executed = native_tool_delivery(tmp_path, wire)
    events = [json.loads(line) for line in wire.read_text().splitlines()]
    call = events[-2]['message']['message']['toolCalls'][0]
    reply = events[-1]['message']['message']
    status = {'state': 'active', 'remaining_seconds': 600, 'active_execution_id': None}
    if problem == 'missing_reply':
        events.pop()
    elif problem == 'assistant_text':
        reply['role'] = 'assistant'
    elif problem == 'invalid_content':
        reply['content'][0]['text'] = 'not JSON'
    elif problem == 'wrong_arguments':
        call['arguments'] = '{"command":"different"}'
    elif problem == 'missing_call_id':
        call.pop('id')
    elif problem == 'stale_reply':
        # A second identical execution can return identical bytes. Its older
        # persisted reply must not acknowledge the newer delivery marker.
        bridge.call('execute', {'command': 'echo fixture'})
    elif problem == 'new_unanswered_call':
        events.append({'type': 'agent.message.appended', 'message': {'message': {
            'role': 'assistant', 'toolCalls': [dict(call, id='new-call')]}}})
    elif problem == 'reused_call_id':
        bridge.call('execute', {'command': 'echo fixture'})
        events.append({'type': 'agent.message.appended', 'message': {'message': {
            'role': 'assistant', 'toolCalls': [dict(call)]}}})
    elif problem == 'changed_marker':
        marker = tmp_path / 'tools.delivery.json'
        entry = json.loads(marker.read_text())
        entry['result'] = {'output': 'different'}
        marker.write_text(json.dumps(entry))
    elif problem == 'missing_bridge_result':
        log = tmp_path / 'tools.jsonl'
        log.write_text(log.read_text().splitlines()[0] + '\n')
    elif problem == 'corrupt_bridge_row':
        with (tmp_path / 'tools.jsonl').open('a') as stream:
            stream.write('["arguments"]\n')
    elif problem == 'pending_tool':
        (tmp_path / 'tools.pending.json').write_text('{}')
    elif problem == 'active_execution':
        status['active_execution_id'] = 'still-running'
    wire.write_text(''.join(json.dumps(event) + '\n' for event in events))
    if problem == 'corrupt_wire':
        with wire.open('a') as stream:
            stream.write('{')
    with pytest.raises(ValueError, match='Unresolved tool operation'):
        continuation_id(tmp_path, {'harness': 'kimi-code'}, AttemptState(), status)
    assert (tmp_path / 'tools.delivery.json').exists()
    assert len(executed) == (2 if problem in {'stale_reply', 'reused_call_id'} else 1)


@pytest.mark.parametrize('problem', [
    'missing_reply', 'assistant_text', 'changed_result', 'invalid_content', 'wrong_tool',
    'wrong_arguments', 'wrong_reply_id', 'missing_call_id', 'wrong_parent_uuid',
    'missing_call_uuid', 'foreign_call', 'foreign_reply', 'missing_step', 'closed_step',
    'new_step_before_reply', 'stale_reply', 'new_unanswered_call', 'reused_call_id',
    'reply_before_call', 'error_result', 'annotated_result', 'clear', 'undo', 'compaction',
    'mirrored_reply_only',
])
def test_kimi_loop_delivery_requires_a_complete_main_agent_exchange(tmp_path, problem):
    from benchmarking.participants.recovery import continuation_id

    _, wire = native_session(tmp_path)
    bridge, executed = native_tool_delivery(tmp_path, wire, wire_format='loop')
    events = [json.loads(line) for line in wire.read_text().splitlines()]
    call = events[-2]['event']
    reply = events[-1]['event']
    if problem == 'missing_reply':
        events.pop()
    elif problem == 'assistant_text':
        events[-1]['event'] = {'type': 'content.part', 'stepUuid': 'step_fixture',
                               'part': {'type': 'text', 'text': reply['result']['output']}}
    elif problem == 'changed_result':
        reply['result']['output'] = '{"output":"different"}'
    elif problem == 'invalid_content':
        reply['result']['output'] = 'not JSON'
    elif problem == 'wrong_tool':
        call['name'] = 'mcp__other__execute'
    elif problem == 'wrong_arguments':
        call['args'] = {'command': 'different'}
    elif problem == 'wrong_reply_id':
        reply['toolCallId'] = 'different'
    elif problem == 'missing_call_id':
        call.pop('toolCallId')
    elif problem == 'wrong_parent_uuid':
        reply['parentUuid'] = 'different'
    elif problem == 'missing_call_uuid':
        call.pop('uuid')
    elif problem == 'foreign_call':
        events[-2]['agentId'] = 'other-agent'
    elif problem == 'foreign_reply':
        events[-1]['agentId'] = 'other-agent'
    elif problem == 'missing_step':
        events.pop(-3)
    elif problem == 'closed_step':
        events.insert(-2, {'type': 'context.append_loop_event', 'agentId': 'main',
                           'event': {'type': 'step.end', 'uuid': 'step_fixture'}})
    elif problem == 'new_step_before_reply':
        events.insert(-1, {'type': 'context.append_loop_event', 'agentId': 'main',
                           'event': {'type': 'step.begin', 'uuid': 'next_step'}})
    elif problem == 'stale_reply':
        bridge.call('execute', {'command': 'echo fixture'})
    elif problem in {'new_unanswered_call', 'reused_call_id'}:
        events.append({'type': 'context.append_loop_event', 'agentId': 'main', 'event':
                       dict(call, uuid='second_call', toolCallId=(
                           'second_tool' if problem == 'new_unanswered_call' else 'tool_fixture'))})
    elif problem == 'reply_before_call':
        events[-2:] = events[-1:] + events[-2:-1]
    elif problem == 'error_result':
        reply['result']['isError'] = True
    elif problem == 'annotated_result':
        reply['result']['note'] = 'different model-facing result'
    elif problem in {'clear', 'undo', 'compaction'}:
        events.append({'type': {'clear': 'context.clear', 'undo': 'context.undo',
                               'compaction': 'context.apply_compaction'}[problem],
                       'agentId': 'main'})
    elif problem == 'mirrored_reply_only':
        events[-1] = {'type': 'agent.message.appended', 'message': {'message': {
            'role': 'tool', 'toolCallId': reply['toolCallId'],
            'content': [{'type': 'text', 'text': reply['result']['output']}]}}}
    wire.write_text(''.join(json.dumps(event) + '\n' for event in events))
    with pytest.raises(ValueError, match='Unresolved tool operation'):
        continuation_id(tmp_path, {'harness': 'kimi-code'}, AttemptState(),
                        {'state': 'active', 'remaining_seconds': 600, 'active_execution_id': None})
    assert (tmp_path / 'tools.delivery.json').exists()
    assert len(executed) == (2 if problem == 'stale_reply' else 1)


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


def test_oauth_refresh_survives_continuation_and_the_next_case(tmp_path, kimi_config):
    import shutil

    from benchmarking.files import atomic_write
    from benchmarking.participants.recovery import continuation_id, policy

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
    native_id = continuation_id(output, {'harness': 'kimi-code'}, AttemptState(), {'state': 'active'})
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


@pytest.mark.parametrize('terminal_error,stop', [
    ('provider.rate_limit: 429 The engine is currently overloaded', 'success'),
    (CONCURRENT_REQUEST_LIMIT, 'success'),
    (CONCURRENT_REQUEST_LIMIT, 'delivered_tool'),
    *[(CONCURRENT_REQUEST_LIMIT, stop) for stop in ('pause_-15', 'pause_130')],
    ("provider.rate_limit: 429 We're receiving too many requests", 'success'),
    *[(CONCURRENT_REQUEST_LIMIT, stop) for stop in
      ('mixed_failure', 'signal', 'resume_disabled', 'quota', 'retry_after')],
])
def test_runner_continues_kimi_capacity_failure_in_the_same_session_and_exports_wire(tmp_path, kimi_config, monkeypatch, terminal_error, stop):
    import zipfile
    from unittest.mock import patch

    from test_participant_runner import ServiceFixture

    from benchmarking.participants.runner import run_participant

    home, config = kimi_config
    selected = selection(home, config)
    service = ServiceFixture()
    service.remaining = 1000
    monkeypatch.setattr('benchmarking.participants.runner.Client', lambda *a, **kw: service)
    monkeypatch.setattr('benchmarking.participants.adapters.cli_version', lambda *a: 'kimi 2.1.1')
    monkeypatch.setattr('benchmarking.participants.recovery.capacity_delay', lambda settings, n: 30 * 2 ** n)
    launches, delays, timeouts = [], [], []
    output = tmp_path / 'result'
    row = {'harness': 'kimi-code', 'task': 'fixture'}
    if stop == 'resume_disabled':
        row['recovery'] = {'resume_session': False}

    def sleep(seconds):
        delays.append(seconds)
        service.remaining -= seconds

    monkeypatch.setattr('benchmarking.participants.runner.time.sleep', sleep)

    def execute(argv, *, stdout, stderr, **kwargs):
        launches.append(argv)
        timeouts.append(kwargs['timeout'])
        stdout.write('{"role":"meta","type":"system.version","version":"2.1.1"}\n')
        if stop == 'retry_after':
            stdout.write('{"type":"error","code":"rate_limit_error","retry_after":400}\n')
        if len(launches) == 1:
            _, wire = native_session(output)
            if stop == 'delivered_tool':
                native_tool_delivery(output, wire, wire_format='loop')
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

    monkeypatch.setattr('benchmarking.participants.runner.execute', execute)
    with patch.object(service, 'create', wraps=service.create) as create:
        result, error = run_participant(service, row, output, selected)
        assert create.call_count == 1
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
        if stop not in {'success', 'delivered_tool'}:
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
