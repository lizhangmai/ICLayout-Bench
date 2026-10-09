"""Harness-neutral structured evidence and failure classification.

Adapters interpret their own native protocols. This module does not recognize
provider prose, reconnect messages, turn completion or tool approval policies.
"""

import json
import math
from dataclasses import dataclass
from pathlib import Path

from ..failures import failure

CAPACITY_CODES = {"model_at_capacity", "overloaded_error", "server_overloaded", "server_is_overloaded"}


@dataclass(frozen=True)
class ErrorEvidence:
    codes: tuple = ()
    retry_after: float | None = None
    tool_failure: dict | None = None


def read_events(output):
    for line in Path(output, "harness.jsonl").read_text(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            yield event


def harness_failure(output, exit_code=None, timed_out=False):
    """Fallback for structured error codes; messages never authorize recovery."""
    if timed_out:
        return classify_evidence(ErrorEvidence(), exit_code, timed_out)
    codes = []
    retry_after = None
    for event in read_events(output):
        if event.get("type") not in {"error", "turn.failed"} and event.get("is_error") is not True:
            continue
        detail = event.get("error")
        explicit = [event.get("code")]
        if isinstance(detail, dict):
            explicit.append(detail.get("code") or detail.get("type"))
        codes.extend([code for code in explicit if code is not None] or [None])
        hint = event.get("retry_after", detail.get("retry_after") if isinstance(detail, dict) else None)
        if type(hint) in (int, float) and math.isfinite(hint) and hint >= 0:
            retry_after = max(retry_after or 0, hint)
    return classify_evidence(ErrorEvidence(tuple(codes), retry_after), exit_code, timed_out)


def classify_evidence(evidence, exit_code=None, timed_out=False):
    """Apply common precedence and recovery categories to normalized evidence."""
    if timed_out:
        return failure("budget_exhausted", "deadline")
    codes = evidence.codes
    mapping = {"insufficient_quota": "quota_exhausted", "billing_error": "quota_exhausted",
               "billing_hard_limit_reached": "quota_exhausted", "insufficient_balance": "quota_exhausted",
               "authentication_error": "authentication", "invalid_api_key": "authentication",
               "rate_limit_error": "rate_limit", "rate_limit_exceeded": "rate_limit",
               "connection_error": "network_transient", **dict.fromkeys(CAPACITY_CODES, "provider_overloaded")}
    for category in ("quota_exhausted", "authentication", "rate_limit", "network_transient"):
        for code in codes:
            if isinstance(code, str) and mapping.get(code) == category:
                return failure(category, "harness_event", code)
    if evidence.tool_failure:
        return evidence.tool_failure
    if exit_code is not None and exit_code < 0:
        return failure("harness_crash", "process_signal", str(-exit_code))
    # Mixed or unrecognized failures cannot authorize an automatic continuation.
    if codes and all(isinstance(code, str) and mapping.get(code) == "provider_overloaded" for code in codes):
        result = failure("provider_overloaded", "harness_event", codes[-1])
        if evidence.retry_after is not None:
            result["retry_after"] = evidence.retry_after
        return result
    if exit_code or codes:
        return failure("unknown", "harness_exit", str(exit_code))
    return None
