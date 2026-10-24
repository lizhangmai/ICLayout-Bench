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


def test_stuck_command_cannot_extend_settlement_when_polled_late():
    now = [9]
    clock = SessionBudget(PhaseBudgets(10, command_seconds=2, settlement_seconds=3), 10, clock=lambda: now[0])
    assert clock.begin_operation(100) == 2
    now[0] = 100
    clock.end_operation()
    assert clock.phase == 'expired' and clock.settlement_deadline == 14


def test_no_active_command_enters_only_submission_grace():
    now = [10]
    clock = SessionBudget(PhaseBudgets(10, settlement_seconds=3), 10, clock=lambda: now[0])
    assert clock.phase == 'settling'
    now[0] = 13
    assert clock.phase == 'expired'


def test_evaluation_budget_comes_from_tools_not_solve_duration():
    backend = SimpleNamespace(tool=SimpleNamespace(timeout_seconds=12))
    plan = SimpleNamespace(jobs=[SimpleNamespace(operation='check'), SimpleNamespace(operation='check')])
    first = PhaseBudgets.for_evaluation(10, plan, {'check': backend})
    second = PhaseBudgets.for_evaluation(1000, plan, {'check': backend})
    assert first.evaluation_seconds == second.evaluation_seconds == 84
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
def test_phase_budgets_reject_unbounded_command_duration(value):
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
