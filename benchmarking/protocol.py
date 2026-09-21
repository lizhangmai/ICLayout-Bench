"""Public HTTP protocol identifiers and validation; no execution dependencies."""
import json
import re

PROTOCOL = "layout-http"
# Infrastructure provisioning (including durable resource archival), not solve time.
SESSION_STARTUP_TIMEOUT_SECONDS = 600
SESSION_STARTUP_RESPONSE_GRACE_SECONDS = 30
ID = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")
USAGE_FIELDS = ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_output_tokens", "cost")


def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError("Invalid identifier or idempotency key")
    return value


def json_bytes(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()


def condition(value):
    expected = {"harness_kind", "harness_id", "harness_version", "model", "prompt_sha256", "configuration_sha256"}
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("Invalid measurement condition fields")
    if value["harness_kind"] != "agent":
        raise ValueError("Invalid harness kind")
    for field in ("harness_id", "harness_version", "model"):
        if not isinstance(value[field], str) or not 1 <= len(value[field]) <= 256:
            raise ValueError("Invalid condition text")
    for field in ("prompt_sha256", "configuration_sha256"):
        if value[field] is not None and (not isinstance(value[field], str)
                                       or not re.fullmatch("[0-9a-f]{64}", value[field])):
            raise ValueError("Invalid condition digest")
    return dict(value)


def evaluation_tools(result):
    """Select the evaluator identity independently of participant resources."""
    tool = result.get("tool_identity") or {}
    return tool.get("evaluator")
