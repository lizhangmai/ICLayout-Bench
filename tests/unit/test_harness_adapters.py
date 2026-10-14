"""Native failure, persisted recovery and credential-safe evidence contracts."""

import json

import pytest
from helpers.harness import native_session

from benchmarking.participants import adapters
from benchmarking.participants.attempt import AttemptState
from benchmarking.participants.evidence import read_traces
from benchmarking.participants.recovery import continuation_id

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('harness,filename', [('codex', 'auth.json'), ('claude-code', '.credentials.json'),
                                           ('dsh', '.credentials.yaml')])
def test_selected_native_credentials_refresh_without_overwriting_competing_sources(tmp_path, harness, filename):
    home = tmp_path / 'authentication'; home.mkdir()
    source = home / filename
    source.write_text('{"access_token":"original-fixture-token"}')
    settings = {'native_home': str(home)}
    metadata = adapters.get(harness).METADATA
    first = tmp_path / 'first/.private'; first.mkdir(parents=True)
    second = tmp_path / 'second/.private'; second.mkdir(parents=True)
    for private in (first, second):
        env = {metadata.home_environment: str(home)}
        assert 'original-fixture-token' in adapters.stage_credentials(harness, private, env, settings)
        assert env[metadata.home_environment] == str(private / 'native-home')
    refreshed = first / 'native-home' / filename
    refreshed.write_text('{"access_token":"first-refreshed-token"}')
    adapters.sync_credentials(harness, first, {}, settings)
    assert source.read_bytes() == refreshed.read_bytes()
    # Native refreshes are reusable in the next case, independent of this case's history.
    third = tmp_path / 'third/.private'; third.mkdir(parents=True)
    adapters.stage_credentials(harness, third, {metadata.home_environment: str(home)}, settings)
    assert (third / 'native-home' / filename).read_bytes() == refreshed.read_bytes()
    competing = second / 'native-home' / filename
    competing.write_text('{"access_token":"competing-refreshed-token"}')
    adapters.sync_credentials(harness, second, {}, settings)
    assert source.read_bytes() == refreshed.read_bytes()
    assert json.loads((second / 'credential-sources.json').read_text())['native-home/' + filename]['status'] == 'refresh_conflict'
    # Reentry must preserve the case's private credentials, not reseed the source.
    assert 'competing-refreshed-token' in adapters.stage_credentials(
        harness, second, {metadata.home_environment: str(home)}, settings)
    assert 'competing-refreshed-token' in competing.read_text()
    assert source.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('harness,filename', [('codex', 'auth.json'), ('claude-code', '.credentials.json')])
def test_selected_native_authentication_cannot_copy_a_symlink(tmp_path, harness, filename):
    home = tmp_path / 'chosen'; home.mkdir()
    outside = tmp_path / 'host-auth.json'; outside.write_text('{"access_token":"host-fixture-token"}')
    (home / filename).symlink_to(outside)
    private = tmp_path / 'participant/.private'; private.mkdir(parents=True)
    with pytest.raises(ValueError, match='regular file'):
        adapters.stage_credentials(harness, private, {}, {'native_home': str(home)})
    assert not (private / 'native-home' / filename).exists()


def test_native_credential_retry_binds_the_snapshot_actually_staged(tmp_path):
    import hashlib

    from benchmarking.participants.native_home import stage_file, sync_files

    home = tmp_path / 'chosen'; home.mkdir()
    source = home / 'auth.json'; source.write_text('{"access_token":"new-login-token"}')
    private = tmp_path / 'participant/.private'; target = private / 'native-home/auth.json'
    target.parent.mkdir(parents=True)
    # Simulate interruption after the old source was recorded, before its file was staged.
    (private / 'credential-sources.json').write_text(json.dumps({'native-home/auth.json': {
        'source': str(source), 'sha256': hashlib.sha256(b'old-login').hexdigest(), 'status': 'seeded'}}))
    stage_file(source, target, private)
    target.write_text('{"access_token":"refreshed-new-login-token"}')
    sync_files(private)
    assert source.read_bytes() == target.read_bytes()


def write_events(output, events):
    (output / 'harness.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in events))


@pytest.mark.parametrize('harness', adapters.HARNESSES)
def test_deadline_does_not_require_stdout(harness, tmp_path):
    assert adapters.harness_failure(harness, tmp_path, timed_out=True)['category'] == 'budget_exhausted'


@pytest.mark.parametrize('code,message,category', [
    ('authentication_failed', 'Failed to authenticate. API Error: 401 fixture authentication', 'authentication'),
    ('server_error', 'API Error: 529 fixture overloaded. This is a server-side issue, usually temporary', 'provider_overloaded'),
    ('server_error', 'API Error: 500 fixture internal error', 'unknown'),
    ('rate_limit', 'API Error: Request rejected (429) · fixture rate limit', 'rate_limit'),
    ('billing_error', 'Credit balance is too low', 'quota_exhausted'),
])
def test_claude_native_terminal_errors(tmp_path, code, message, category):
    events = [{'type': 'assistant', 'error': code, 'message': {'content': [{'type': 'text', 'text': message}]}},
              {'type': 'result', 'subtype': 'success', 'is_error': True, 'result': message}]
    write_events(tmp_path, events)
    assert adapters.harness_failure('claude-code', tmp_path, exit_code=1)['category'] == category


def test_claude_retry_and_assistant_prose_are_not_terminal_failures(tmp_path):
    write_events(tmp_path, [{'type': 'system', 'subtype': 'api_retry', 'error': 'server_error'},
                            {'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'API Error: 529 overloaded'}]}},
                            {'type': 'result', 'subtype': 'success', 'is_error': False, 'result': 'done'}])
    assert adapters.harness_failure('claude-code', tmp_path, exit_code=0) is None
    write_events(tmp_path, [{'type': 'assistant', 'error': 'server_error', 'message': {'content': [{'type': 'text', 'text': 'API Error: 529 overloaded'}]}},
                            {'type': 'result', 'subtype': 'success', 'is_error': False, 'result': 'done'}])
    assert adapters.harness_failure('claude-code', tmp_path, exit_code=0) is None


@pytest.mark.parametrize('additional', [{'type': 'error', 'error': {'code': 'invalid_api_key'}},
                                       {'type': 'error', 'message': 'unrecognized native error'},
                                       {'type': 'result', 'subtype': 'error_during_execution', 'is_error': True, 'errors': ['unknown failure']}])
def test_claude_unknown_or_fatal_errors_block_capacity(tmp_path, additional):
    message = 'API Error: 529 fixture overloaded'
    write_events(tmp_path, [{'type': 'assistant', 'error': 'server_error', 'message': {'content': [{'type': 'text', 'text': message}]}},
                            {'type': 'result', 'subtype': 'success', 'is_error': True, 'result': message}, additional])
    assert adapters.harness_failure('claude-code', tmp_path, exit_code=1)['category'] != 'provider_overloaded'


def test_claude_success_does_not_hide_unrelated_structured_failure(tmp_path):
    write_events(tmp_path, [{'type': 'error', 'code': 'invalid_api_key'},
                            {'type': 'result', 'subtype': 'success', 'is_error': False, 'result': 'done'}])
    assert adapters.harness_failure('claude-code', tmp_path, exit_code=0)['category'] == 'authentication'


@pytest.mark.parametrize('code,category', [('AUTH', 'authentication'), ('QUOTA', 'quota_exhausted'),
                                         ('RATE_LIMIT', 'rate_limit'), ('TRANSPORT', 'network_transient'),
                                         ('SERVER', 'unknown'), ('INVALID_REQUEST', 'unknown')])
def test_dsh_native_terminal_error_codes(tmp_path, code, category):
    write_events(tmp_path, [{'type': 'status', 'phase': 'turn_end', 'turn': 1,
                            'reason': {'kind': 'error', 'error': {'code': code, 'message': 'fixture'}}}])
    assert adapters.harness_failure('dsh', tmp_path, exit_code=1)['category'] == category


@pytest.mark.parametrize('harness', ['codex', 'kimi-code', 'command'])
def test_other_harnesses_do_not_borrow_claude_or_dsh_protocols(tmp_path, harness):
    write_events(tmp_path, [{'type': 'assistant', 'error': 'server_error', 'message': {'content': [{'type': 'text', 'text': 'API Error: 529 overloaded'}]}},
                            {'type': 'status', 'phase': 'turn_end', 'reason': {'kind': 'error', 'error': {'code': 'AUTH'}}}])
    assert adapters.harness_failure(harness, tmp_path, exit_code=1)['category'] == 'unknown'


@pytest.mark.parametrize('harness,category', [('codex', 'authentication'), ('claude-code', 'unknown'),
                                            ('dsh', 'unknown'), ('kimi-code', 'unknown'), ('command', 'unknown')])
def test_codex_provider_http_status_is_vendor_owned(tmp_path, harness, category):
    message = 'unexpected status 401 Unauthorized: fixture authentication, url: http://127.0.0.1:1234/v1/responses'
    write_events(tmp_path, [{'type': 'error', 'message': message}, {'type': 'turn.failed', 'error': {'message': message}}])
    assert adapters.harness_failure(harness, tmp_path, exit_code=1)['category'] == category
    write_events(tmp_path, [{'type': 'item.completed', 'item': {'type': 'agent_message', 'text': message}}])
    assert adapters.harness_failure(harness, tmp_path, exit_code=1)['category'] == 'unknown'


@pytest.mark.parametrize('harness', ['codex', 'claude-code'])
def test_resume_requires_persisted_main_history_in_original_workspace(tmp_path, harness):
    sid = 'e0b0bd21-c1bf-4d09-909e-01063f03105e'
    write_events(tmp_path, [{'type': 'thread.started', 'thread_id': sid}])
    state = AttemptState(native_id=sid)
    with pytest.raises(ValueError, match='persisted native'):
        continuation_id(tmp_path, {'harness': harness}, state, {})
    path = native_session(tmp_path, harness, sid, cwd='/other/workspace')
    with pytest.raises(ValueError, match='persisted native'):
        continuation_id(tmp_path, {'harness': harness}, state, {})
    native_session(tmp_path, harness, sid)
    assert continuation_id(tmp_path, {'harness': harness}, state, {}) == sid
    other = path.parent / 'duplicate' / path.name
    # Claude only discovers one project-directory level.
    if harness == 'claude-code':
        other = path.parent.parent / 'other-project' / path.name
    other.parent.mkdir(parents=True); other.write_bytes(path.read_bytes())
    with pytest.raises(ValueError, match='persisted native'):
        continuation_id(tmp_path, {'harness': harness}, state, {})
    other.unlink()
    outside = tmp_path / 'outside.jsonl'; outside.write_bytes(path.read_bytes())
    path.unlink()
    with pytest.raises(ValueError, match='persisted native'):
        continuation_id(tmp_path, {'harness': harness}, state, {})
    path.symlink_to(outside)
    with pytest.raises(ValueError, match='persisted native'):
        continuation_id(tmp_path, {'harness': harness}, state, {})
    assert not adapters.native_traces(harness, tmp_path)


@pytest.mark.parametrize('harness,home_env,filename', [('codex', 'CODEX_HOME', 'auth.json'),
                                                   ('claude-code', 'CLAUDE_CONFIG_DIR', '.credentials.json')])
def test_private_refreshed_credentials_survive_reentry_and_redact_all_traces(tmp_path, harness, home_env, filename):
    host = tmp_path / 'host'; host.mkdir()
    (host / filename).write_text('{"access_token":"original-fixture-secret"}')
    output = tmp_path / 'participant'; private = output / '.private'; private.mkdir(parents=True)
    adapters.stage_credentials(harness, private, {home_env: str(host)})
    staged = private / 'native-home' / filename
    staged.write_text('{"access_token":"rotated-fixture-secret"}')
    redactions = adapters.stage_credentials(harness, private, {home_env: str(host)})
    assert json.loads(staged.read_text())['access_token'] == 'rotated-fixture-secret'
    assert {'original-fixture-secret', 'rotated-fixture-secret'} <= redactions
    native = native_session(output, harness, 'e0b0bd21-c1bf-4d09-909e-01063f03105e', content='thinking rotated-fixture-secret')
    (output / 'conditions.json').write_text(json.dumps({'selection': {'harness': harness}}))
    write_events(output, [{'message': 'rotated-fixture-secret'}])
    (output / 'harness.stderr').write_text('rotated-fixture-secret')
    traces = read_traces(output)
    assert traces.native
    assert b'thinking <REDACTED>' in b''.join(traces.native.values())
    assert b'rotated-fixture-secret' not in traces.agent + traces.stderr.encode() + b''.join(traces.native.values())
    assert b'rotated-fixture-secret' in native.read_bytes()
    assert all(filename not in name for name in traces.native)


@pytest.mark.parametrize('harness,prefix', [('codex', 'codex'), ('claude-code', 'claude')])
def test_terminal_cleanup_preserves_native_reasoning_and_logs(tmp_path, harness, prefix):
    from test_participant_runner import terminal_files

    from benchmarking.participants.storage import CaseRecord
    from benchmarking.participants.terminal import finish_case

    record = CaseRecord(tmp_path)
    record.initialize({'endpoint': 'https://fixture', 'plan': [{'model': 'fixture', 'effort': 'high'}]})
    record.begin()
    summary = terminal_files(record.participant)
    summary.update(state='finished', task='fixture', score=None)
    record.record_summary(summary)
    wire = native_session(record.participant, harness, 'e0b0bd21-c1bf-4d09-909e-01063f03105e')
    home = record.participant / '.private/native-home'
    log = home / ('log' if harness == 'codex' else 'debug') / 'native.log'
    log.parent.mkdir(parents=True); log.write_text('retained diagnostic log')
    (record.participant / 'conditions.json').write_text(json.dumps({'selection': {'harness': harness}}))
    original = wire.read_bytes()
    relative = wire.relative_to(home)
    finish_case(tmp_path)
    assert not record.runtime.exists()
    assert (tmp_path / 'native' / prefix / relative).read_bytes() == original
    assert (tmp_path / 'native' / prefix / log.relative_to(home)).read_text() == 'retained diagnostic log'


@pytest.mark.parametrize('event,exit_code,category', [
    ({'type': 'error', 'error': {'code': 'insufficient_quota'}}, 1, 'quota_exhausted'),
    ({'type': 'error', 'error': {'type': 'authentication_error'}}, 1, 'authentication'),
    ({'type': 'turn.failed', 'error': {'code': 'rate_limit_exceeded'}}, 1, 'rate_limit'),
    ({'type': 'error', 'message': 'Selected model is at capacity. Please try a different model.'}, 1, 'provider_overloaded'),
    ({'type': 'turn.failed', 'error': {'message': 'Selected model is at capacity. Please try a different model.'}}, 1, 'provider_overloaded'),
    ({'type': 'turn.failed', 'error': {'code': 'server_is_overloaded', 'retry_after': 45}}, 1, 'provider_overloaded'),
    ({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'Selected model is at capacity. Please try a different model.'}}, 1, 'unknown'),
    ({'type': 'error', 'message': 'Selected model is at capacity. Please try a different model.',
      'error': {'code': 'invalid_api_key'}}, 1, 'authentication'),
    ({'type': 'assistant', 'text': 'insufficient_quota'}, 3, 'unknown'),
    ({}, -9, 'harness_crash'),
])
def test_failure_uses_evidence_not_exit_code_or_assistant_text(tmp_path, event, exit_code, category):
    from benchmarking.participants.adapters.codex import harness_failure
    (tmp_path / 'harness.jsonl').write_text(json.dumps(event) + '\n')
    assert harness_failure(tmp_path, exit_code)['category'] == category


@pytest.mark.parametrize('ending, exit_code, timed_out, category', [
    ([{'type': 'turn.completed'}], 0, False, None),
    ([{'type': 'turn.failed'}], 0, False, 'unknown'),
    ([], 0, False, 'unknown'),
    ([{'type': 'turn.completed'}], 1, False, 'unknown'),
    ([{'type': 'turn.completed'}], 0, True, 'budget_exhausted'),
    ([{'type': 'turn.started'}, {'type': 'turn.completed'}], 0, False, 'unknown'),
    ([{'type': 'turn.completed'}, {'type': 'error', 'message': 'unrecognized failure'}], 0, False, 'unknown'),
    ([{'type': 'error', 'error': {'code': 'invalid_api_key'}}, {'type': 'turn.completed'}], 0, False, 'authentication'),
    ([{'type': 'error', 'error': {'code': 'insufficient_quota'}}, {'type': 'turn.completed'}], 0, False, 'quota_exhausted'),
    ([{'type': 'item.completed', 'item': {'type': 'mcp_tool_call', 'server': 'layout',
                                       'tool': 'execute', 'status': 'failed', 'error': {'message': 'transport failed'}}},
      {'type': 'turn.completed'}], 0, False, 'unknown'),
])
def test_reconnect_recovery_requires_successful_same_turn(tmp_path, ending, exit_code, timed_out, category):
    """Observed Codex reconnect events are diagnostic after successful recovery.

    Existing single-error tests miss recovered sequences. The real classifier
    consumes minimized native events; unrelated failures and turn boundaries
    must retain failure evidence. No model or EDA behavior is asserted.
    """
    from benchmarking.participants.adapters.codex import harness_failure

    events = [{'type': 'turn.started'}, {'type': 'error',
              'message': 'Reconnecting... 2/5 (stream disconnected before completion: tls handshake eof)'}] + ending
    trace = tmp_path / 'harness.jsonl'
    original = '\n'.join(json.dumps(e) for e in events)
    trace.write_text(original)
    problem = harness_failure(tmp_path, exit_code=exit_code, timed_out=timed_out)
    assert (problem['category'] if problem else None) == category
    assert trace.read_text() == original


@pytest.mark.parametrize('event, recovered', [
    ({'type': 'error', 'error': {'code': 'connection_error'}}, True),
    ({'type': 'error', 'message': 'Selected model is at capacity. Please try a different model.'}, True),
    ({'type': 'error', 'message': 'unrecognized failure'}, False),
    ({'type': 'error', 'message': 'Reconnecting... 2/5 (stream disconnected before completion: tls handshake eof)',
      'error': {'code': 'insufficient_quota'}}, False),
])
def test_reconnect_recognition_preserves_other_error_evidence(tmp_path, event, recovered):
    from benchmarking.participants.adapters.codex import harness_failure

    events = [{'type': 'turn.started'}, event, {'type': 'turn.completed'}]
    (tmp_path / 'harness.jsonl').write_text('\n'.join(json.dumps(e) for e in events))
    assert (harness_failure(tmp_path, exit_code=0) is None) == recovered


def test_capacity_error_cannot_hide_another_failure(tmp_path):
    from benchmarking.participants.adapters.codex_events import (
        CAPACITY_MESSAGE,
        harness_failure,
    )

    events = [{'type': 'error', 'message': 'unrecognized failure'},
              {'type': 'turn.failed', 'error': {'message': CAPACITY_MESSAGE}}]
    (tmp_path / 'harness.jsonl').write_text('\n'.join(json.dumps(event) for event in events))
    assert harness_failure(tmp_path, exit_code=1)['category'] == 'unknown'


@pytest.mark.parametrize('message', [
    'Reconnecting... 2/5 (request timed out)',
    'Reconnecting... 2/5 (workspace routing discovery timed out)',
    'Reconnecting... waiting for network (Connection failed: error sending request)',
    'Reconnecting... 2/5 (unexpected status 503 Service Unavailable: upstream connect error)',
])
@pytest.mark.parametrize('completed', [False, True])
def test_observed_reconnect_variants_require_successful_completion(tmp_path, message, completed):
    from benchmarking.participants.adapters.codex import harness_failure

    events = [{'type': 'turn.started'}, {'type': 'error', 'message': message},
              {'type': 'turn.completed' if completed else 'turn.failed'}]
    raw = '\n'.join(json.dumps(e) for e in events)
    (tmp_path / 'harness.jsonl').write_text(raw)
    problem = harness_failure(tmp_path, exit_code=0 if completed else 1)
    assert (problem is None) == completed
    assert (tmp_path / 'harness.jsonl').read_text() == raw


@pytest.mark.parametrize("harness", adapters.HARNESSES)
@pytest.mark.parametrize("structured", [False, True])
def test_capacity_messages_are_interpreted_only_by_the_owning_adapter(tmp_path, harness, structured):
    from benchmarking.participants import adapters

    event = {"type": "error", "message": "Selected model is at capacity. Please try a different model."}
    if structured:
        event["error"] = {"type": "overloaded_error", "retry_after": 45}
    (tmp_path / "harness.jsonl").write_text(json.dumps(event))
    problem = adapters.harness_failure(harness, tmp_path, exit_code=1)
    assert problem["category"] == ("provider_overloaded" if structured or harness == "codex" else "unknown")
    if structured:
        assert problem["retry_after"] == 45


@pytest.mark.parametrize("harness", adapters.HARNESSES)
def test_reconnect_turn_semantics_are_specific_to_codex(tmp_path, harness):
    from benchmarking.participants import adapters

    events = [{"type": "turn.started"},
              {"type": "error", "message": "Reconnecting... 2/5 (request timed out)"},
              {"type": "turn.completed"}]
    (tmp_path / "harness.jsonl").write_text("\n".join(json.dumps(event) for event in events))
    problem = adapters.harness_failure(harness, tmp_path, exit_code=0)
    assert (problem is None) == (harness == "codex")
