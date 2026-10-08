"""Structured native CLI events; assistant prose never establishes recovery."""

import json
import math
import re
from pathlib import Path

from ..failures import failure

CAPACITY_MESSAGE = "Selected model is at capacity. Please try a different model."
CAPACITY_CODES = {"model_at_capacity", "overloaded_error", "server_overloaded", "server_is_overloaded"}


def harness_failure(output, exit_code=None, timed_out=False):
    """Only structured error events count; free-form model text is not evidence."""
    if timed_out:
        return failure("budget_exhausted", "deadline")
    codes = []
    reconnect_codes = []
    in_turn = False
    tool_errors = {}
    retry_after = None
    for line in Path(output, "harness.jsonl").read_text(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get("type")
        if kind in {"thread.started", "turn.started", "turn.failed", "turn.completed"}:
            # Recovery belongs only to this turn, never to a later successful one.
            if not (kind == "turn.completed" and in_turn and exit_code == 0):
                codes.extend(reconnect_codes)
            reconnect_codes.clear()
            in_turn = kind == "turn.started"
        item = event.get("item")
        if (event.get("type") == "item.completed" and isinstance(item, dict)
                and item.get("type") == "mcp_tool_call" and item.get("server") == "layout"):
            tool = item.get("tool")
            detail = item.get("error")
            if isinstance(tool, str):
                if item.get("status") == "completed":
                    tool_errors.pop(tool, None)
                elif item.get("status") == "failed" and isinstance(detail, dict):
                    tool_errors[tool] = detail.get("message")
        if kind in {"error", "turn.failed"} or event.get("is_error") is True:
            detail = event.get("error", {})
            event_codes = [event.get("code")]
            if isinstance(detail, dict):
                event_codes.append(detail.get("code") or detail.get("type"))
            explicit = [code for code in event_codes if code is not None]
            if explicit:
                event_codes = explicit
            message = event.get("message") or (detail.get("message") if isinstance(detail, dict) else None)
            # This exact message is emitted by the native CLI, not assistant/tool prose.
            if kind in {"error", "turn.failed"} and not explicit and message == CAPACITY_MESSAGE:
                event_codes = ["model_at_capacity"]
            hint = event.get("retry_after", detail.get("retry_after") if isinstance(detail, dict) else None)
            if type(hint) in (int, float) and math.isfinite(hint) and hint >= 0:
                retry_after = max(retry_after or 0, hint)
            # Codex emits these native error events during its own reconnect loop.
            # Never infer recovery from assistant text or arbitrary error messages.
            connection = (all(code == "connection_error" for code in explicit) if explicit else
                          isinstance(message, str) and re.fullmatch(
                              r"Reconnecting\.\.\. [1-9][0-9]*/[1-9][0-9]* "
                              r"\(stream disconnected before completion: [^\r\n]+\)", message) is not None)
            capacity = all(isinstance(code, str) and code in CAPACITY_CODES for code in event_codes)
            target = reconnect_codes if kind == "error" and in_turn and (connection or capacity) and event.get("is_error") is not True else codes
            target.extend(event_codes)
    codes.extend(reconnect_codes)
    mapping = {"insufficient_quota": "quota_exhausted", "billing_error": "quota_exhausted",
               "billing_hard_limit_reached": "quota_exhausted", "insufficient_balance": "quota_exhausted",
               "authentication_error": "authentication", "invalid_api_key": "authentication",
               "rate_limit_error": "rate_limit", "rate_limit_exceeded": "rate_limit",
               "connection_error": "network_transient", **dict.fromkeys(CAPACITY_CODES, "provider_overloaded")}
    for category in ("quota_exhausted", "authentication", "rate_limit", "network_transient"):
        for code in codes:
            if isinstance(code, str) and mapping.get(code) == category:
                return failure(category, "harness_event", code)
    # Match a native MCP error field exactly, never model prose or tool output.
    if any(message == "MCP tool call requires approval, but approval policy is never"
           for message in tool_errors.values()):
        return failure("harness_configuration", "harness_tool_event", "mcp_approval_required")
    if tool_errors:
        return failure("unknown", "harness_tool_event", "mcp_tool_call_failed")
    if exit_code is not None and exit_code < 0:
        return failure("harness_crash", "process_signal", str(-exit_code))
    # Mixed or unrecognized failures cannot authorize an automatic continuation.
    if codes and all(isinstance(code, str) and mapping.get(code) == "provider_overloaded" for code in codes):
        result = failure("provider_overloaded", "harness_event", codes[-1])
        if retry_after is not None:
            result["retry_after"] = retry_after
        return result
    if exit_code or codes:
        return failure("unknown", "harness_exit", str(exit_code))
    return None
