"""Conservative failure evidence and explicit participant recovery policy."""
import json
from pathlib import Path

from benchmarking.client import ClientError

DISABLED = {"http_attempts": 1, "backoff_seconds": 0, "max_backoff_seconds": 0,
            "resume_session": False}


def policy(value=None):
    if value is None:
        return dict(DISABLED)
    if not isinstance(value, dict) or set(value) != set(DISABLED):
        raise ValueError("recovery requires http_attempts, backoff_seconds, max_backoff_seconds, resume_session")
    if type(value["http_attempts"]) is not int or not 1 <= value["http_attempts"] <= 10:
        raise ValueError("http_attempts must be between 1 and 10")
    for key in ("backoff_seconds", "max_backoff_seconds"):
        if type(value[key]) not in (int, float) or not 0 <= value[key] <= 60:
            raise ValueError(key + " must be finite and between 0 and 60")
    if value["max_backoff_seconds"] < value["backoff_seconds"] or type(value["resume_session"]) is not bool:
        raise ValueError("Invalid recovery backoff or resume_session")
    return dict(value)


def failure(category, source, code=None):
    return {"category": category, "source": source, "code": code,
            "retryable": category in {"network_transient", "rate_limit"},
            "stop_dispatch": category in {"quota_exhausted", "authentication", "service_failure", "harness_configuration"}}


def classify(error):
    if isinstance(error, ClientError):
        category = {"transport_error": "network_transient", "unauthorized": "authentication",
                    "budget_exhausted": "budget_exhausted", "unavailable": "service_failure",
                    "infrastructure_error": "service_failure"}.get(error.code, "unknown")
        return failure(category, "http", error.code)
    return failure("unknown", "runner", type(error).__name__)


def harness_failure(output, exit_code=None, timed_out=False):
    """Only structured error events count; free-form model text is not evidence."""
    if timed_out:
        return failure("budget_exhausted", "deadline")
    codes = []
    tool_errors = {}
    for line in Path(output, "harness.jsonl").read_text(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
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
        if event.get("type") in {"error", "turn.failed"} or event.get("is_error") is True:
            detail = event.get("error", {})
            if isinstance(detail, dict):
                codes.append(detail.get("code") or detail.get("type"))
            codes.append(event.get("code"))
    mapping = {"insufficient_quota": "quota_exhausted", "billing_error": "quota_exhausted",
               "billing_hard_limit_reached": "quota_exhausted", "insufficient_balance": "quota_exhausted",
               "authentication_error": "authentication", "invalid_api_key": "authentication",
               "rate_limit_error": "rate_limit", "rate_limit_exceeded": "rate_limit",
               "connection_error": "network_transient", "overloaded_error": "rate_limit"}
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
    if exit_code or codes:
        return failure("unknown", "harness_exit", str(exit_code))
    return None


def credential_values(value):
    """Known runtime secrets for report redaction; retained only in private state."""
    found = set()
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).lower().replace("_", "").replace("-", "")
            if (isinstance(item, str) and len(item) >= 4
                    and (normalized.endswith("token") or any(word in normalized for word in
                         ("apikey", "password", "secret", "authorization")))):
                found.add(item)
            if isinstance(item, (dict, list)):
                found.update(credential_values(item))
    elif isinstance(value, list):
        for item in value:
            found.update(credential_values(item))
    return found
