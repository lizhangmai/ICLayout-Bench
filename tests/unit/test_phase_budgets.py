"""Phase transitions keep solve, command, submission and judging allowances separate."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from benchmarking.execution.budgets import PhaseBudgets, SessionBudget
from benchmarking.execution.tools import budget as tools

pytestmark = pytest.mark.unit


def test_started_command_drains_then_settles_without_renewing_solve():
    now = [0]
    budgets = PhaseBudgets(10, command_seconds=20, settlement_seconds=3, evaluation_seconds=40)
    clock = SessionBudget(budgets, 10, clock=lambda: now[0])
    now[0] = 9
    assert clock.begin_operation() == 20
    now[0] = 11
    assert clock.phase == 'draining'
    with pytest.raises(TimeoutError):
        clock.begin_operation()
    now[0] = 27
    clock.end_operation()
    assert clock.phase == 'settling'
    assert clock.snapshot()['solve_remaining_seconds'] == 0
    now[0] = 30
    assert clock.phase == 'expired'
    now[0] = 100
    assert clock.phase == 'expired' and clock.settlement_deadline == 30


@pytest.mark.parametrize('maximum,requested', [(2, 100), (None, 2)])
def test_stuck_command_cannot_extend_settlement_when_polled_late(maximum, requested):
    now = [9]
    clock = SessionBudget(PhaseBudgets(10, command_seconds=maximum, settlement_seconds=3), 10, clock=lambda: now[0])
    assert clock.begin_operation(requested) == 2
    now[0] = 100
    clock.end_operation()
    assert clock.phase == 'expired' and clock.settlement_deadline == 14


def test_no_active_command_enters_only_submission_grace():
    now = [10]
    clock = SessionBudget(PhaseBudgets(10, settlement_seconds=3), 10, clock=lambda: now[0])
    assert clock.phase == 'settling'
    now[0] = 13
    assert clock.phase == 'expired'


def test_default_command_can_drain_without_renewing_the_solve_budget():
    now = [9]
    clock = SessionBudget(PhaseBudgets(10, settlement_seconds=3), 10, clock=lambda: now[0])
    assert clock.begin_operation() is None
    now[0] = 10000
    assert clock.phase == 'draining'
    assert clock.snapshot()['solve_remaining_seconds'] == 0
    assert clock.snapshot()['command_remaining_seconds'] is None
    with pytest.raises(TimeoutError):
        clock.begin_operation()
    clock.end_operation()
    assert clock.phase == 'settling'
    now[0] += 3
    assert clock.phase == 'expired'


def test_process_check_does_not_reintroduce_an_automatic_eda_deadline(monkeypatch):
    from benchmarking.execution.harness import PROCESS_FEEDBACK_CAPABILITY, HarnessSpec
    from benchmarking.execution.workspace.protocol import SessionProtocol

    now = [9]
    monkeypatch.setattr(tools.time, 'monotonic', lambda: now[0])
    task = SimpleNamespace(output=SimpleNamespace(path='output/final.gds', max_bytes=1024))
    config = SimpleNamespace(harness=HarnessSpec(capabilities=(PROCESS_FEEDBACK_CAPABILITY,)))
    workspace = SimpleNamespace(read=lambda *args: b'frozen candidate',
                                budget=SessionBudget(PhaseBudgets(10), 10, clock=lambda: now[0]))

    def feedback(candidate, sequence):
        assert tools.tool_timeout(1800) is None
        now[0] = 10000
        assert workspace.budget.phase == 'draining'
        return {'report': {'outcome': 'passed'}}

    protocol = SessionProtocol(task, config, workspace, 0, 10, recorder=None,
                               record=lambda *args, **kwargs: None, feedback=feedback, on_ready=None)
    try:
        receipt = protocol.check()
        assert receipt['accepted'] and receipt['feedback']['outcome'] == 'passed'
        assert workspace.budget.phase == 'settling'
    finally:
        protocol.close()


def test_settlement_waits_for_unlimited_command_after_a_retained_deadline(tmp_path, monkeypatch):
    import json

    from benchmarking.participants.attempt import settlement

    (tmp_path/'finalization.json').write_text(json.dumps({
        'executions': {}, 'errors': [], 'drain_deadline_epoch': 1}))
    now = [10000]
    monkeypatch.setattr(settlement.time, 'time', lambda: now[0])
    monkeypatch.setattr(settlement.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(settlement.time, 'sleep', lambda _: None)
    state = {'active': True}
    receipt = {'submission_id': '3', 'candidate_sha256': 'a'*64}
    closed = []

    def poll(*args, **kwargs):
        now[0] += 10000
        state['active'] = False
        return {'log_base64': '', 'next_offset': 0, 'state': 'complete',
                'exit_code': 0, 'truncated': False}

    client = SimpleNamespace(session=lambda _: {
        'state': 'active', 'active_execution_id': 'check' if state['active'] else None,
        'last_submission': receipt, 'budget': {'command_remaining_seconds': None}},
        poll=poll, close=lambda *args, **kwargs: closed.append(True))
    assert settlement.settle_session(client, 'session', tmp_path) == receipt
    record = json.loads((tmp_path/'finalization.json').read_text())
    assert record['drain_deadline_epoch'] is None and record['error'] is None
    assert closed and record['closed']


def test_participant_expiry_tracks_service_phase_without_ending_active_eda(monkeypatch):
    from benchmarking.participants.attempt import settlement

    now = [0]
    monkeypatch.setattr(settlement.time, 'monotonic', lambda: now[0])
    status = {'state': 'active', 'phase': 'draining'}
    client = SimpleNamespace(session=lambda _: status)
    expired = settlement.participant_expiry(client, 'session', 10)
    assert not expired()
    now[0] = 10000
    assert not expired()
    status['phase'] = 'settling'
    assert not expired()
    status['phase'] = 'expired'
    assert expired()


def test_evaluation_has_no_automatic_budget_from_tool_or_solve_limits():
    backend = SimpleNamespace(tool=SimpleNamespace(timeout_seconds=12))
    plan = SimpleNamespace(jobs=[SimpleNamespace(operation='check'), SimpleNamespace(operation='check')])
    first = PhaseBudgets.for_evaluation(10, plan, {'check': backend})
    second = PhaseBudgets.for_evaluation(1000, plan, {'check': backend})
    assert first.evaluation_seconds is second.evaluation_seconds is None
    assert PhaseBudgets(10).evaluation_seconds is None
    assert replace(first, settlement_seconds=1).command_seconds == first.command_seconds


def test_evaluation_phase_deadline_survives_tool_threads(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setattr(tools.time, 'monotonic', lambda: 10)
    with tools.tool_deadline(15):
        frozen = tools.current_tool_deadline()
        def worker():
            with tools.tool_deadline(frozen), tools.tool_time_limits(True):
                return tools.tool_timeout(100)
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(worker).result() == 5
    assert tools.current_tool_deadline() is None


@pytest.mark.parametrize('value', [0, -1, float('inf'), float('nan')])
def test_phase_budgets_reject_invalid_explicit_command_duration(value):
    with pytest.raises(ValueError):
        PhaseBudgets(10, command_seconds=value)


def test_collection_restart_does_not_renew_evaluation_budget(tmp_path, monkeypatch):
    import json

    from benchmarking.participants.attempt import settlement

    now = [100]
    monkeypatch.setattr(settlement.time, 'time', lambda: now[0])
    monkeypatch.setattr(settlement.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(settlement.time, 'sleep', lambda seconds: now.__setitem__(0, now[0]+seconds))
    pending = {'state': 'evaluating', 'budget': {'evaluation_remaining_seconds': 1}}
    client = SimpleNamespace(result=lambda _: pending)
    with pytest.raises(TimeoutError):
        settlement.wait_result(client, 'session', tmp_path)
    assert json.loads((tmp_path/'collection.json').read_text())['evaluation_deadline_epoch'] == 101
    # Reconnecting to a stale service response cannot grant another second.
    with pytest.raises(TimeoutError):
        settlement.wait_result(client, 'session', tmp_path)
    assert now[0] == 101


@pytest.mark.parametrize('retained_deadline', [False, True])
def test_collection_waits_for_unlimited_evaluation_after_old_deadline(tmp_path, monkeypatch, retained_deadline):
    import json

    from benchmarking.participants.attempt import settlement

    journal = tmp_path / 'collection.json'
    if retained_deadline:
        journal.write_text(json.dumps({'evaluation_deadline_epoch': 1}))
    now = [10000]
    monkeypatch.setattr(settlement.time, 'time', lambda: now[0])
    monkeypatch.setattr(settlement.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(settlement.time, 'sleep', lambda _: now.__setitem__(0, now[0] + 10000))
    pending = {'state': 'evaluating', 'budget': {'evaluation_remaining_seconds': None},
               'limits': {'phase_budgets': {'solve_seconds': 10, 'evaluation_seconds': None}}}
    terminal = {'state': 'complete'}
    responses = iter([pending, pending, terminal])
    client = SimpleNamespace(result=lambda _: next(responses))
    assert settlement.wait_result(client, 'session', tmp_path) == terminal
    assert json.loads(journal.read_text())['evaluation_deadline_epoch'] is None


def test_evaluation_deadline_bounds_real_native_process():
    import sys
    import time

    from benchmarking.eda.environment import ExternalRuntime
    from benchmarking.execution.tools.native import NativeTool

    runtime = ExternalRuntime('test', {'image': 'unused', 'environment': {}, 'mounts': []})
    tool = NativeTool(runtime, timeout_seconds=30)
    started = time.monotonic()
    with tools.tool_deadline(started+.2):
        result = tool.run([sys.executable, '-c', 'import time; time.sleep(30)'], {}, {})
    assert time.monotonic()-started < 5
    assert result.reason and 'execution_error' in result.evidence


@pytest.mark.parametrize('limited', [False, True])
def test_process_feedback_worker_inherits_shared_tool_policy(limited):
    import sys
    import time

    from benchmarking.eda.environment import ExternalRuntime
    from benchmarking.execution.harness import PROCESS_FEEDBACK_CAPABILITY, HarnessSpec
    from benchmarking.execution.tools.native import NativeTool
    from benchmarking.execution.workspace.protocol import SessionProtocol

    started = time.monotonic()
    deadline = started + 10
    task = SimpleNamespace(output=SimpleNamespace(path='output/final.gds', max_bytes=1024))
    config = SimpleNamespace(harness=HarnessSpec(capabilities=(PROCESS_FEEDBACK_CAPABILITY,)))
    workspace = SimpleNamespace(read=lambda *args: b'frozen candidate',
                                budget=SessionBudget(PhaseBudgets(10), deadline))
    tool = NativeTool(ExternalRuntime('test', {'image': 'unused', 'environment': {}, 'mounts': []}),
                      timeout_seconds=.02)

    def feedback(candidate, sequence):
        result = tool.run([sys.executable, '-c', 'import time; time.sleep(.1)'], {}, {})
        return {'report': {'outcome': 'pass' if result.returncode == 0 else 'error'}}

    protocol = SessionProtocol(task, config, workspace, started, deadline, recorder=None,
                               record=lambda *args, **kwargs: None, feedback=feedback, on_ready=None)
    try:
        with tools.tool_time_limits(limited):
            receipt = protocol.check()
        assert receipt['accepted']
        assert receipt['feedback']['outcome'] == ('error' if limited else 'pass')
    finally:
        protocol.close()


def test_terminal_result_budget_is_stable_across_polls():
    from benchmarking.service.views import status

    now = [0]
    budgets = PhaseBudgets(100)
    workspace = SimpleNamespace(active=False, budget=SessionBudget(budgets, 100, clock=lambda: now[0]))
    data = {'session_id': 's', 'report': {'outcome': 'passed'}, 'submissions': {},
            'executions': {}, 'created_at': 'start', 'deadline_epoch': 100,
            'deadline': 'end', 'limits': {'phase_budgets': budgets.identity()}}
    first = status(data, workspace, [], 1)
    now[0] = 5
    assert status(data, workspace, [], 5)['budget'] == first['budget']
    assert first['phase'] == 'complete'
