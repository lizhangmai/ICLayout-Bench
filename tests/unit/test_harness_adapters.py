"""Native failure, persisted recovery and credential-safe evidence contracts."""

import json

import pytest
from helpers.harness import native_session

from benchmarking.participants import adapters
from benchmarking.participants.attempt import AttemptState
from benchmarking.participants.evidence import read_traces
from benchmarking.participants.recovery import continuation_id

pytestmark = pytest.mark.unit


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
    path.unlink()
    with pytest.raises(ValueError, match='persisted native'):
        continuation_id(tmp_path, {'harness': harness}, state, {})


@pytest.mark.parametrize('harness', ['codex', 'claude-code'])
def test_resume_rejects_duplicate_history_and_external_symlinks(tmp_path, harness):
    sid = 'e0b0bd21-c1bf-4d09-909e-01063f03105e'
    write_events(tmp_path, [{'type': 'thread.started', 'thread_id': sid}])
    state = AttemptState(native_id=sid)
    path = native_session(tmp_path, harness, sid)
    other = path.parent / 'duplicate' / path.name
    # Claude only discovers one project-directory level.
    if harness == 'claude-code':
        other = path.parent.parent / 'other-project' / path.name
    other.parent.mkdir(parents=True); other.write_bytes(path.read_bytes())
    with pytest.raises(ValueError, match='persisted native'):
        continuation_id(tmp_path, {'harness': harness}, state, {})
    other.unlink()
    outside = tmp_path / 'outside.jsonl'; outside.write_bytes(path.read_bytes())
    path.unlink(); path.symlink_to(outside)
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
