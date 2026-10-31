"""Harness-independent session settlement through the evaluation HTTP protocol."""

import base64
import json
import time

from benchmarking.client import ClientError
from benchmarking.execution.budgets import PhaseBudgets
from benchmarking.files import atomic_write

ERRORS = (OSError, ValueError, RuntimeError, ClientError)


def error_detail(error):
    """Retain protocol evidence without exception text, request bodies or credentials."""
    detail = {"error": type(error).__name__}
    if isinstance(error, ClientError):
        detail.update(code=error.code, status=error.status)
    elif isinstance(error, KeyboardInterrupt):
        detail['code'] = 'operator_interrupted'
    return detail


def settle_session(client, sid, output):
    """Drain existing executions and close on the participant's accepted snapshot.

    Never submit mutable workspace output. Uses only service state and execution IDs. Waiting
    consumes the original deadline. No execution or participant is launched here.
    """
    journal = output / "finalization.json"
    record = json.loads(journal.read_text()) if journal.exists() else {"executions": {}, "errors": []}
    record.update(phase="draining", error=None, close_error=None, closed=False)
    start = time.monotonic()
    session_path = output / "session.json"
    limits = json.loads(session_path.read_text()).get("limits", {}) if session_path.exists() else {}
    budgets = PhaseBudgets.from_limits(limits)

    def persist():
        record["elapsed_seconds"] = round(time.monotonic() - start, 3)
        atomic_write(journal, (json.dumps(record, indent=2, allow_nan=False) + "\n").encode())

    def idle():
        while True:
            status = client.session(sid)
            record['receipt'] = status.get('last_submission')
            if status['state'] != 'active':
                return status
            eid = status.get('active_execution_id')
            if not eid:
                return status
            remaining = status.get('budget', {}).get('command_remaining_seconds', budgets.command_seconds)
            # Freeze an absolute expiry in the journal: explicit collection may
            # resume after transport loss but never reissues the command budget.
            if remaining is None:
                record['drain_deadline_epoch'] = None
            elif record.get('drain_deadline_epoch') is None:
                record['drain_deadline_epoch'] = time.time() + remaining
            deadline = (time.monotonic() + max(0, record['drain_deadline_epoch']-time.time())
                        if record['drain_deadline_epoch'] is not None else None)
            execution = record['executions'].setdefault(eid, {'next_offset': 0})
            record['phase'] = 'draining'
            persist()
            while deadline is None or time.monotonic() < deadline:
                polled = client.poll(sid, eid, offset=execution['next_offset'])
                raw = base64.b64decode(polled['log_base64'], validate=True)
                if raw:
                    with (output / f'finalization-{eid}.log').open('ab') as stream:
                        stream.write(raw)
                execution.update({key: polled[key] for key in ('state', 'exit_code', 'truncated', 'next_offset')})
                persist()
                if polled['state'] != 'running' and not raw:
                    break
                if not raw:
                    time.sleep(.5 if deadline is None else min(.5, max(0, deadline-time.monotonic())))
            else:
                raise TimeoutError('Session settlement: active command deadline expired; execution evidence retained')

    primary, status = None, None
    persist()
    try:
        status = idle()
        record["receipt"] = status.get("last_submission")
        if record.get("submission") != "deadline":
            record["submission"] = "retained" if record["receipt"] else "none"
    except BaseException as exc:
        primary = exc
        record["error"] = error_detail(exc)
        record["errors"].append(record["error"])
        raise
    finally:
        record["phase"] = "settling"
        persist()
        try:
            closed_states = {"evaluating", "complete", "error"}
            if status is None or status["state"] not in closed_states:
                try:
                    client.close(sid, key="runner-close")
                except ClientError as exc:
                    if exc.status != 410 or exc.code != "session_closed":
                        raise
                    # The service can expire the workspace between our status
                    # read and close. Confirm that transition before collecting.
                    status = client.session(sid)
                    if status["state"] not in closed_states:
                        raise
                    record["receipt"] = status.get("last_submission")
                    record["submission"] = "retained" if record["receipt"] else "none"
            record.update(closed=True, phase="closed")
        except ERRORS as exc:
            record["close_error"] = error_detail(exc)
            record["errors"].append(record["close_error"])
            if primary is None:
                raise
        finally:
            persist()
    return record.get("receipt")


def participant_timeout(created, status):
    """The model may observe draining/settlement, but cannot outlive those phases."""
    if 'phase_budgets' not in created['limits']:
        return max(0, status['remaining_seconds'])
    budgets = PhaseBudgets.from_limits(created['limits'])
    if budgets.command_seconds is None:
        return None
    return max(0, status['remaining_seconds']) + budgets.command_seconds + budgets.settlement_seconds


def participant_expiry(client, sid, remaining):
    """Stop model work at service expiry while allowing an active EDA job to drain."""
    solve_deadline = time.monotonic() + max(0, remaining)

    def expired():
        if time.monotonic() < solve_deadline:
            return False
        status = client.session(sid)
        return status['state'] != 'active' or status.get('phase', status.get('budget', {}).get('phase')) == 'expired'

    return expired


def wait_result(client, sid, output=None):
    """Wait for independent evaluation; honor only an explicitly bounded service."""
    journal = output / 'collection.json' if output is not None else None
    record = json.loads(journal.read_text()) if journal is not None and journal.exists() else {}
    retained_deadline = record.get('evaluation_deadline_epoch')
    deadline = (time.monotonic() + max(0, retained_deadline-time.time())
                if retained_deadline is not None else None)
    while True:
        result = client.result(sid)
        if result['state'] in {'complete', 'error'}:
            return result
        budgets = PhaseBudgets.from_limits(result.get('limits', {}))
        remaining = result.get('budget', {}).get('evaluation_remaining_seconds', budgets.evaluation_seconds)
        if remaining is None:
            deadline = None
            # A saved deadline from an older collection attempt must not cut off
            # a service that now explicitly permits its EDA jobs to finish.
            if journal is not None and ('evaluation_deadline_epoch' not in record
                                        or record['evaluation_deadline_epoch'] is not None):
                record['evaluation_deadline_epoch'] = None
                atomic_write(journal, (json.dumps(record, indent=2) + '\n').encode())
        elif deadline is None:
            deadline = time.monotonic() + remaining
            if journal is not None:
                record['evaluation_deadline_epoch'] = time.time() + remaining
                atomic_write(journal, (json.dumps(record, indent=2) + '\n').encode())
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError('Evaluation remains pending; session ID retained in session.json')
        time.sleep(.5)
