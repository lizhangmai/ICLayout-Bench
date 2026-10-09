"""Codex native event semantics, including reconnects and layout MCP errors."""

import math
import re

from ..failures import failure
from .events import CAPACITY_CODES, ErrorEvidence, classify_evidence, read_events

CAPACITY_MESSAGE = "Selected model is at capacity. Please try a different model."

RECONNECT_MESSAGE = re.compile(
    r"Reconnecting\.\.\. (?:[1-9][0-9]*/[1-9][0-9]* \("
    r"(?:stream disconnected before completion: [^\r\n]+|request timed out|"
    r"workspace routing discovery timed out|unexpected status 503 Service Unavailable: "
    r"upstream connect error[^\r\n]*)\)|"
    r"waiting for network \(Connection failed: error sending request\))")


def native_error(event):
    detail = event.get("error", {})
    explicit = [event.get("code")]
    if isinstance(detail, dict):
        explicit.append(detail.get("code") or detail.get("type"))
    explicit = [code for code in explicit if code is not None]
    message = event.get("message") or (detail.get("message") if isinstance(detail, dict) else None)
    codes = explicit or [None]
    if event.get("type") in {"error", "turn.failed"} and not explicit and message == CAPACITY_MESSAGE:
        codes = ["model_at_capacity"]
    return codes, explicit, message, detail


def harness_failure(output, exit_code=None, timed_out=False):
    """Only structured error events count; free-form model text is not evidence."""
    if timed_out:
        return failure("budget_exhausted", "deadline")
    codes = []
    reconnect_codes = []
    in_turn = False
    tool_errors = {}
    retry_after = None
    for event in read_events(output):
        kind = event.get("type")
        event_codes, explicit, message, detail = native_error(event)
        if kind in {"thread.started", "turn.started", "turn.failed", "turn.completed"}:
            # Recovery belongs only to this turn, never to a later successful one.
            completed = kind == "turn.completed" and in_turn and exit_code == 0
            # A definitive capacity response ends this same native reconnect loop.
            # Earlier turns, unknown errors, fatal codes and MCP failures stay intact.
            capacity_terminal = (kind == "turn.failed" and in_turn and exit_code is not None
                                 and exit_code > 0 and all(isinstance(code, str) and code in CAPACITY_CODES
                                                          for code in event_codes))
            if not (completed or capacity_terminal):
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
            hint = event.get("retry_after", detail.get("retry_after") if isinstance(detail, dict) else None)
            if type(hint) in (int, float) and math.isfinite(hint) and hint >= 0:
                retry_after = max(retry_after or 0, hint)
            # Codex emits these native error events during its own reconnect loop.
            # Never infer recovery from assistant text or arbitrary error messages.
            connection = (all(code == "connection_error" for code in explicit) if explicit else
                          isinstance(message, str) and RECONNECT_MESSAGE.fullmatch(message) is not None)
            capacity = all(isinstance(code, str) and code in CAPACITY_CODES for code in event_codes)
            target = reconnect_codes if kind == "error" and in_turn and (connection or capacity) and event.get("is_error") is not True else codes
            target.extend(event_codes)
    codes.extend(reconnect_codes)
    tool_failure = None
    # These native layout MCP error fields belong to Codex's event protocol.
    if any(message == "MCP tool call requires approval, but approval policy is never"
           for message in tool_errors.values()):
        tool_failure = failure("harness_configuration", "harness_tool_event", "mcp_approval_required")
    elif tool_errors:
        tool_failure = failure("unknown", "harness_tool_event", "mcp_tool_call_failed")
    return classify_evidence(ErrorEvidence(tuple(codes), retry_after, tool_failure), exit_code, timed_out)
