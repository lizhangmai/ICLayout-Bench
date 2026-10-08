"""Harness-independent session settlement through the evaluation HTTP protocol."""

import base64
import json
import time

from benchmarking.client import ClientError
from benchmarking.files import atomic_write

ERRORS = (OSError, ValueError, RuntimeError, ClientError)


def error_detail(error):
    """Retain protocol evidence without exception text, request bodies or credentials."""
    detail = {"error": type(error).__name__}
    if isinstance(error, ClientError):
        detail.update(code=error.code, status=error.status)
    return detail


def settle_session(client, sid, path, output, *, snapshot=True):
    """Drain existing executions, snapshot a candidate, then close the same session.

    With snapshot=False, retain the last accepted candidate without submitting
    mutable workspace output. Uses only service state and execution IDs. Waiting
    consumes the original deadline. No execution or participant is launched here.
    """
    journal = output / "finalization.json"
    record = json.loads(journal.read_text()) if journal.exists() else {"executions": {}, "errors": []}
    record.update(phase="waiting", error=None, close_error=None, closed=False)
    start = time.monotonic()

    def persist():
        record["elapsed_seconds"] = round(time.monotonic() - start, 3)
        atomic_write(journal, (json.dumps(record, indent=2, allow_nan=False) + "\n").encode())

    deadline = None

    def idle():
        nonlocal deadline
        while True:
            status = client.session(sid)
            if status["state"] != "active":
                return status
            deadline = min(deadline or float("inf"), time.monotonic() + status["remaining_seconds"])
            remaining = deadline - time.monotonic()
            soft = status.get('budget', {}).get('policy') == 'soft'
            if remaining <= 0 and not soft:
                record["submission"] = "deadline"
                return dict(status, remaining_seconds=0)
            eid = status.get("active_execution_id")
            if not eid:
                return status
            execution = record["executions"].setdefault(eid, {"next_offset": 0})
            record["phase"] = "waiting"
            persist()
            while soft or time.monotonic() < deadline:
                polled = client.poll(sid, eid, offset=execution["next_offset"])
                raw = base64.b64decode(polled["log_base64"], validate=True)
                if raw:
                    with (output / f"finalization-{eid}.log").open("ab") as stream:
                        stream.write(raw)
                execution.update({key: polled[key] for key in ("state", "exit_code", "truncated", "next_offset")})
                persist()
                if polled["state"] != "running" and not raw:
                    break
                if not raw:
                    time.sleep(.5 if soft else min(.5, max(0, deadline - time.monotonic())))

    primary = None
    persist()
    try:
        while True:
            status = idle()
            if not snapshot:
                record["receipt"] = status.get("last_submission")
                record["submission"] = "retained"
                break
            if status["state"] != "active" or (status["remaining_seconds"] <= 0 and status.get('budget', {}).get('policy') != 'soft'):
                record.setdefault("submission", "session_closed")
                break
            record["phase"] = "submitting"
            persist()
            try:
                record["receipt"] = client.submit(sid, path, key="runner-final-submit")
                record["submission"] = "accepted"
                break
            except ClientError as exc:
                if exc.status == 400:
                    record["submission"] = "rejected"
                    break
                if exc.status == 410 and exc.code == "session_closed":
                    record["submission"] = "session_closed"
                    break
                # Reconcile a new execution between the idle query and submission.
                # An unrelated 409 never authorizes a replay or a new request key.
                if exc.status == 409 and exc.code == "conflict" and client.session(sid).get("active_execution_id"):
                    continue
                raise
    except ERRORS as exc:
        primary = exc
        record["error"] = error_detail(exc)
        record["errors"].append(record["error"])
        raise
    finally:
        record["phase"] = "closing"
        persist()
        try:
            client.close(sid, key="runner-close")
            record.update(closed=True, phase="closed")
        except ERRORS as exc:
            record["close_error"] = error_detail(exc)
            record["errors"].append(record["close_error"])
            if primary is None:
                raise
        finally:
            persist()
    return record.get("receipt")
