"""Session settlement, bounded drains and result waits on the accepted snapshot."""

import json
import sys
import time
from types import SimpleNamespace

import pytest
from helpers.participant import (
    FakeClock,
    InFlightService,
    attempt_boundaries,
    case_run,
    host_probes,
    in_process,
    write_dataset,
)

from benchmarking.client import ClientError
from benchmarking.participants.attempt.runner import finalize_session, run_participant
from benchmarking.participants.attempt.settlement import settle_session, wait_result
from benchmarking.participants.cli import main
from benchmarking.participants.harnesses.contracts import ParticipantSelection

pytestmark = pytest.mark.unit


def test_finalization_retains_only_participant_accepted_snapshot(tmp_path):
    fixture = InFlightService(race=True)
    fixture.condition = {}
    (tmp_path / '.private').mkdir()
    (tmp_path / '.private/recovery.json').write_text('{"redactions": []}')
    receipt = {'submission_id': 'explicit', 'sequence': 1, 'candidate_sha256': 'a' * 64}
    session, result = fixture.session, fixture.result
    fixture.session = lambda sid: dict(session(sid), last_submission=receipt)
    fixture.result = lambda sid: dict(result(sid), submission=receipt)
    outcome = finalize_session(fixture, 'fixture-session', tmp_path)
    assert outcome['submission'] == receipt
    assert not fixture.submitted
    assert fixture.closed == ['fixture-session']
    record = json.loads((tmp_path / 'finalization.json').read_text())
    assert record['receipt'] == receipt and record['submission'] == 'retained'


@pytest.mark.parametrize('state', ['evaluating', 'complete', 'error'])
@pytest.mark.parametrize('close_race', [False, True])
def test_finalization_collects_a_session_closed_by_the_service(tmp_path, state, close_race):
    fixture = InFlightService(race=True)
    fixture.condition = {}
    receipt = {'submission_id': 'accepted', 'sequence': 21, 'candidate_sha256': 'a' * 64}
    observed = {'state': 'active' if close_race else state}
    fixture.session = lambda _: {
        'state': observed['state'], 'remaining_seconds': 0,
        'active_execution_id': None, 'last_submission': receipt,
    }

    def close(*args, **kwargs):
        observed['state'] = state
        raise ClientError('session_closed', 'Session closed', status=410)

    fixture.close = close
    original_result = fixture.result
    fixture.result = lambda sid: dict(original_result(sid), submission=receipt)
    (tmp_path / '.private').mkdir()
    (tmp_path / '.private/recovery.json').write_text('{"redactions": []}')
    (tmp_path / 'harness-summary.json').write_text(json.dumps({
        'finalization_error': {'error': 'ClientError', 'failure': {'code': 'session_closed'}},
    }))

    result = finalize_session(fixture, 'fixture-session', tmp_path)

    assert result['submission'] == receipt and result['state'] == 'complete'
    assert (tmp_path / 'observation/manifest.json').is_file()
    record = json.loads((tmp_path / 'finalization.json').read_text())
    assert record['closed'] and record['receipt'] == receipt and record['close_error'] is None
    assert 'finalization_error' not in json.loads((tmp_path / 'harness-summary.json').read_text())
    assert not fixture.submitted


def test_finalization_does_not_hide_session_closed_without_a_closed_state(tmp_path):
    fixture = InFlightService(race=True)
    def close(*args, **kwargs):
        raise ClientError('session_closed', 'Workspace is unavailable', status=410)
    fixture.close = close
    with pytest.raises(ClientError, match='Workspace is unavailable'):
        settle_session(fixture, 'fixture-session', tmp_path)
    record = json.loads((tmp_path / 'finalization.json').read_text())
    assert not record['closed'] and record['close_error']['code'] == 'session_closed'


def test_finalization_command_expiry_retains_accepted_candidate(tmp_path):
    fixture = InFlightService()
    fixture.condition = {}
    receipt = {'submission_id': 'earlier', 'sequence': 1, 'candidate_sha256': 'a' * 64}
    old_session = fixture.session
    fixture.session = lambda sid: dict(old_session(sid), last_submission=receipt,
        budget={'command_remaining_seconds': 1})
    fixture.poll = lambda sid, eid, offset=0: {'execution_id': eid, 'state': 'running', 'exit_code': None,
                                            'log_base64': '', 'next_offset': offset, 'truncated': False}
    (tmp_path / '.private').mkdir()
    (tmp_path / '.private/recovery.json').write_text('{"redactions": []}')
    result = fixture.result
    fixture.result = lambda sid: dict(
        result(sid), submission=receipt, outcome='fail',
        score={'method': 'layout', 'maximum': 100, 'reference': 100, 'value': 0.0})
    observed = finalize_session(fixture, 'fixture-session', tmp_path, clock=FakeClock())
    assert observed['submission'] == receipt and observed['score']['value'] == 0.0
    evidence = json.loads((tmp_path / 'finalization.json').read_text())
    assert evidence['receipt'] == receipt and evidence['closed']
    assert evidence['error']['error'] == 'TimeoutError'
    assert fixture.closed == ['fixture-session'] and not fixture.submitted


@pytest.mark.parametrize('score', [0.0, 87.5])
def test_finalization_collects_accepted_candidate_after_drain_timeout(tmp_path, score):
    fixture = InFlightService()
    fixture.condition = {}
    receipt = {'submission_id': 'final', 'sequence': 4, 'candidate_sha256': 'a' * 64}
    session, result = fixture.session, fixture.result
    fixture.session = lambda sid: dict(session(sid), last_submission=receipt)
    fixture.result = lambda sid: dict(
        result(sid), submission=receipt, outcome='pass' if score else 'fail',
        score={'method': 'layout', 'maximum': 100, 'reference': 100, 'value': score})

    def poll(*args, **kwargs):
        raise TimeoutError('execution polling timed out')

    fixture.poll = poll
    (tmp_path / '.private').mkdir()
    (tmp_path / '.private/recovery.json').write_text('{"redactions": []}')

    observed = finalize_session(fixture, 'fixture-session', tmp_path)

    assert observed['state'] == 'complete' and observed['score']['value'] == score
    assert observed['submission'] == receipt and not fixture.submitted
    assert (tmp_path / 'observation/manifest.json').is_file()
    record = json.loads((tmp_path / 'finalization.json').read_text())
    assert record['closed'] and record['error']['error'] == 'TimeoutError'


def test_finalization_keeps_primary_error_when_close_also_fails(tmp_path):
    fixture = InFlightService(conflict=True)
    def close(*a, **kw):
        raise ClientError('transport_error', 'response lost')
    fixture.close = close
    with pytest.raises(ClientError) as caught:
        finalize_session(fixture, 'fixture-session', tmp_path)
    assert caught.value.code == 'conflict'
    evidence = json.loads((tmp_path / 'finalization.json').read_text())
    assert evidence['error']['code'] == 'conflict'
    assert evidence['close_error']['code'] == 'transport_error'
    assert not evidence['closed']


def test_operator_interruption_is_not_replaced_by_transport_failure_during_close(tmp_path):
    fixture = InFlightService()
    def interrupted(*a, **kw):
        raise KeyboardInterrupt
    def close(*a, **kw):
        raise ClientError('transport_error', 'service shutting down')
    fixture.session = interrupted
    fixture.close = close
    with pytest.raises(KeyboardInterrupt):
        settle_session(fixture, 'fixture-session', tmp_path)
    record = json.loads((tmp_path / 'finalization.json').read_text())
    assert record['error']['code'] == 'operator_interrupted'
    assert record['close_error']['code'] == 'transport_error'


@pytest.mark.parametrize('failure_code', ['conflict', 'infrastructure_error', 'result_transport'])
def test_unrelated_finalization_conflict_retains_original_harness_failure(tmp_path, failure_code):
    fixture = InFlightService(conflict=failure_code != 'result_transport')
    tasks = ['fixture', 'untouched'] if failure_code == 'infrastructure_error' else ['fixture']
    if failure_code == 'infrastructure_error':
        def poll(sid, eid, *, offset=0):
            raise ClientError(failure_code, 'service unavailable', status=500)
        fixture.poll = poll
    if failure_code == 'result_transport':
        def result(sid):
            raise ClientError('transport_error', 'response lost')
        fixture.result = result
    config = tmp_path / 'trial.toml'
    config.write_text('harness="claude-code"\nmodel="fixture"\neffort="high"\n'
                      f'tasks={json.dumps(tasks)}\nconcurrency=1\nrepetitions=1\n'
                      '[recovery]\nhttp_attempts=1\nbackoff_seconds=0\nmax_backoff_seconds=0\nresume_session=false\n')
    selected = {'harness': 'claude-code', 'model': 'fixture', 'effort_resolved': 'high', 'effort_requested': 'high'}
    attempt = attempt_boundaries(fixture, native_command=lambda context: [sys.executable, '-c', 'import sys; sys.exit(7)'])
    dataset = write_dataset(tmp_path / 'dataset', tasks)
    output = tmp_path / 'batch'
    assert main(['--config', str(config), '--dataset', str(dataset), '--output', str(output)],
                probes=host_probes(ParticipantSelection(selected, {}, {})),
                boundaries=in_process(attempt=attempt)) == 1
    result = json.loads((case_run(output, 'fixture') / 'result.json').read_text())
    assert result['summary']['harness_error'] == 'cli_exit_7'
    assert result['summary']['failure']['source'] == 'harness_exit'
    assert result['summary']['finalization_error']['failure']['code'] == ('transport_error' if failure_code == 'result_transport' else failure_code)
    assert not fixture.submitted
    assert fixture.closed == ['fixture-session']
    if len(tasks) > 1:
        assert json.loads((case_run(output, 'untouched') / 'result.json').read_text())['state'] == 'finished'


def test_evaluation_uses_its_own_declared_budget():
    ticks = iter([0, 1, 601, 602])
    terminal = {'state': 'complete', 'limits': {'phase_budgets': {'solve_seconds': 10, 'evaluation_seconds': 7200}}}
    results = iter([{'state': 'evaluating', 'limits': {'phase_budgets': {'solve_seconds': 10, 'evaluation_seconds': 7200}}}, terminal])
    clock = SimpleNamespace(monotonic=lambda: next(ticks), time=time.time, sleep=lambda _: None)
    assert wait_result(SimpleNamespace(result=lambda _: next(results)), 'session', clock=clock) == terminal


def test_pending_evaluation_has_bounded_collection_wait():
    ticks = iter([0, 1, 601, 602, 1201])
    clock = SimpleNamespace(monotonic=lambda: next(ticks), time=time.time, sleep=lambda _: None)
    calls = []
    def result(sid):
        calls.append(sid)
        assert len(calls) < 3, "Collection kept waiting after its timeout"
        return {"state": "evaluating", "limits": {"phase_budgets": {"solve_seconds": 3600, "evaluation_seconds": 600}}}
    with pytest.raises(TimeoutError, match="Evaluation remains pending"):
        wait_result(SimpleNamespace(result=result), "session", clock=clock)


def test_command_deadline_closes_stuck_execution_and_retains_receipt(tmp_path):
    receipt = {"submission_id": "10", "candidate_sha256": "a"*64}
    ticks = iter([0, 0, 0, 601, 602, 603, 604, 605, 606, 607, 608])
    clock = SimpleNamespace(monotonic=lambda: next(ticks), time=time.time, sleep=lambda _: None)
    closed = []
    polls = []
    def poll(*args, **kwargs):
        polls.append(args)
        assert len(polls) < 3, "Stuck execution was drained without a bound"
        return {"log_base64": "", "state": "running", "exit_code": None,
                "truncated": False, "next_offset": 0}
    client = SimpleNamespace(session=lambda _: {"state": "active", "remaining_seconds": 0,
        "budget": {"command_remaining_seconds": 60}, "active_execution_id": "in-flight", "last_submission": receipt},
        poll=poll, close=lambda sid, **kw: closed.append(sid))
    with pytest.raises(TimeoutError, match="settlement"):
        settle_session(client, "session", tmp_path, clock=clock)
    record = json.loads((tmp_path/"finalization.json").read_text())
    assert closed == ["session"] and record["closed"]
    assert record["receipt"] == receipt and record["error"]["error"] == "TimeoutError"


def test_settlement_respects_independent_command_allowance(tmp_path):
    fixture = InFlightService()
    original_session = fixture.session
    fixture.session = lambda sid: dict(original_session(sid), budget={"command_remaining_seconds": 1200})
    (tmp_path/"session.json").write_text(json.dumps({"limits": {"phase_budgets": {"solve_seconds": 10, "command_seconds": 1200}}}))
    clock = FakeClock()
    original_poll = fixture.poll
    def poll(*args, **kwargs):
        clock.now = 700
        return original_poll(*args, **kwargs)
    fixture.poll = poll
    settle_session(fixture, "fixture-session", tmp_path, clock=clock)
    record = json.loads((tmp_path/"finalization.json").read_text())
    assert record["closed"] and record["error"] is None


def test_resume_after_solve_expiry_drains_existing_command_without_model_call(tmp_path):
    fixture = InFlightService()
    create = fixture.create
    def created(*args, **kwargs):
        value = create(*args, **kwargs)
        fixture.remaining = 0
        return value
    fixture.create = created
    def launch(*args, **kwargs):
        raise AssertionError('No model may launch after solve expiry')
    selected = ParticipantSelection({'model': 'fixture', 'effort_resolved': 'low'}, {}, {})
    result, error = run_participant(fixture, {'harness': 'command', 'task': 'fixture'}, tmp_path, selected,
                                    boundaries=attempt_boundaries(fixture, native_command=launch))
    assert error == 'harness_timeout' and result['state'] == 'complete'
    evidence = json.loads((tmp_path/'finalization.json').read_text())
    assert evidence['executions']['in-flight']['state'] == 'complete'
    assert evidence['closed'] and not fixture.submitted
