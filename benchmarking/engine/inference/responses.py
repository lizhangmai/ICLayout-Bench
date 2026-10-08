"""Responses wire-family request validation and response interpretation."""

import json

from .contracts import WireRequest, normalize_usage


def _validate_responses_request(path, body, model):
    if path not in {"/responses", "/responses/compact"}:
        raise ValueError("Only Responses generation and compaction are allowed")
    data = json.loads(body)
    if not isinstance(data, dict) or data.get("model") != model:
        raise ValueError("Request model differs from the fixed profile")
    # Remote resources in the model input bypass the declared tool environment.
    # Do not walk the whole request here: function-tool JSON schemas are ordinary
    # user data and may legitimately use names such as ``file_id`` or
    # ``image_url`` for their own arguments.
    def inspect_input(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"file_id", "file_url", "container_id"}:
                    raise ValueError("Remote resource references are disabled")
                if key == "image_url" and (not isinstance(item, str) or not item.startswith("data:")):
                    raise ValueError("Only inline images are allowed")
                inspect_input(item)
        elif isinstance(value, list):
            for item in value:
                inspect_input(item)

    def check_tools(tools):
        if not isinstance(tools, list):
            raise TypeError("Invalid tools list")
        for tool in tools:
            if not isinstance(tool, dict) or tool.get("type") not in {"function", "custom", "namespace"}:
                raise ValueError("Only client-executed tools are allowed")
            if tool["type"] == "namespace":
                check_tools(tool.get("tools", []))

    inspect_input(data.get("input", []))
    check_tools(data.get("tools", []))
    if data.get("background") or data.get("conversation") or data.get("previous_response_id"):
        raise ValueError("Only stateless foreground inference is allowed")
    if path == "/responses":
        data["store"] = False
    else:
        # Compaction has no declared persistence control.  In particular, do
        # not forward a caller-provided ``store=true`` to an upstream service.
        data.pop("store", None)
    return json.dumps(data, separators=(",", ":")).encode()


def _responses_response_semantics(path, content_type, body):
    """Require a terminal Responses result, independently of HTTP success."""
    messages = []
    media = content_type.split(";", 1)[0].strip().lower()
    if media == "text/event-stream":
        # SSE data fields may span lines; an unterminated frame is not a commit.
        lines, event_name = [], None
        wire = body.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        # Only CR/LF delimit SSE lines; Unicode separators may occur inside JSON strings.
        wire_lines = wire.split("\n")
        for line in wire_lines[:-1] if wire.endswith("\n") else wire_lines:
            if not line:
                if lines:
                    raw = "\n".join(lines)
                    if raw != "[DONE]":
                        message = json.loads(raw)
                        if not isinstance(message, dict) or (event_name and message.get("type") != event_name):
                            raise ValueError("Invalid SSE event")
                        messages.append(message)
                lines, event_name = [], None
            elif line.startswith("data:"):
                lines.append(line[5:].removeprefix(" "))
            elif line.startswith("event:"):
                event_name = line[6:].strip()
        if lines:
            raise ValueError("Truncated SSE frame")
        terminal = [m for m in messages if m.get("type") in {
            "response.completed", "response.failed", "response.incomplete", "error"}]
        if len(terminal) != 1 or terminal[0] is not messages[-1]:
            raise ValueError("Missing or conflicting terminal response")
        final = terminal[0]
        if final["type"] == "error":
            return {"outcome": "service_error", "reason": final.get("code"), "usage": None}
        response = final.get("response")
        if not isinstance(response, dict) or final["type"] != "response." + str(response.get("status")):
            raise ValueError("Inconsistent response terminal status")
    elif media == "application/json":
        response = json.loads(body)
        if not isinstance(response, dict):
            raise ValueError("Invalid response object")
    else:
        raise ValueError("Unsupported response media type")
    if path == "/responses/compact" and response.get("object") == "response.compaction":
        if not isinstance(response.get("output"), list) or response.get("error"):
            raise ValueError("Invalid compaction result")
        outcome, reason = "completed", None
    elif response.get("status") == "failed" or response.get("error"):
        outcome, reason = "service_error", (response.get("error") or {}).get("code")
    elif response.get("status") == "completed":
        outcome, reason = "completed", None
    elif response.get("status") == "incomplete":
        reason = (response.get("incomplete_details") or {}).get("reason")
        outcome = {"max_output_tokens": "budget_truncated", "content_filter": "content_filtered"}.get(
            reason, "incomplete_error")
    else:
        raise ValueError("Missing terminal response status")
    usage = response.get("usage")
    return {"outcome": outcome, "reason": reason,
            "usage": normalize_usage(usage,
                                      input_details=usage.get("input_tokens_details")
                                      if isinstance(usage, dict) else None,
                                      output_details=usage.get("output_tokens_details")
                                      if isinstance(usage, dict) else None)}


class _ResponsesWireAdapter:
    id = "responses"

    def validate_request(self, path, body, model):
        return _validate_responses_request(path, body, model)

    def prepare_request(self, path, body, model, credential):
        return WireRequest("POST", path, {
            "Authorization": f"Bearer {credential}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream, application/json",
        })

    def response_semantics(self, path, content_type, body):
        return _responses_response_semantics(path, content_type, body)
