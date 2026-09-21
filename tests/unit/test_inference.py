import json
import socket
import time
from pathlib import Path

import pytest

from benchmarking.engine.inference import (
    InferenceConfig,
    InferenceGateway,
    load_inference_config,
    validate_request,
)
from benchmarking.files import Asset

pytestmark = pytest.mark.unit


def gateway_config(max_requests=1):
    return InferenceConfig("https://example.invalid/v1", "test-model", "UNUSED",
                           max_requests, 10, Asset(b"profile", "text"), "responses")


@pytest.mark.parametrize("path,extra", [
    ("/files", {}),
    ("/responses", {"model": "another"}),
    ("/responses", {"tools": [{"type": "namespace", "tools": [{"type": "mcp"}]}]}),
    ("/responses", {"input": [{"image_url": "https://elsewhere/a.png"}]}),
])
def test_gateway_rejects_other_destinations_models_and_remote_tools(path, extra):
    with pytest.raises(ValueError):
        validate_request(path, json.dumps({"model": "test-model", **extra}).encode(), "test-model", "responses")


def test_request_bound_usage_and_no_error_body_exposure():
    config = gateway_config(max_requests=1)
    def transport(path, body, timeout):
        assert json.loads(body)["store"] is False
        return 200, "application/json", b'{"status":"completed","usage":{"input_tokens":10,"output_tokens":3}}'
    gateway = InferenceGateway(config, transport=transport)
    gateway.deadline = time.monotonic()+10
    assert gateway.request("/responses", b'{"model":"test-model","store":true}')[0] == 200
    assert gateway.request("/responses", b'{"model":"test-model"}')[0] == 429
    assert gateway.summary()["usage"]["input_tokens"] == 10
    assert gateway.summary()["usage"]["output_tokens"] == 3
    assert gateway.summary()["usage"]["cached_input_tokens"] is None
    assert gateway.summary()["limit_reached"]

    def broken(*args):
        raise OSError("secret-key-in-exception")
    gateway = InferenceGateway(config, transport=broken)
    gateway.deadline = time.monotonic()+10
    status, _, body = gateway.request("/responses", b'{"model":"test-model"}')
    assert status == 502 and b"secret" not in body
    assert "secret" not in json.dumps(gateway.summary())
    assert gateway.summary()["usage"]["input_tokens"] is None


def test_summary_separates_forwarded_denied_failed_and_truncated_requests():
    config = gateway_config(max_requests=3)
    responses = iter([
        b'{"status":"completed","usage":{"input_tokens":2,"output_tokens":1}}',
        b'{"status":"failed","error":{"code":"upstream"}}',
        (b'{"status":"incomplete","incomplete_details":{"reason":"max_output_tokens"},'
         b'"usage":{"input_tokens":3,"output_tokens":4}}'),
    ])
    gateway = InferenceGateway(config, transport=lambda *args: (200, "application/json", next(responses)))
    gateway.deadline = time.monotonic() + 10
    for _ in range(3):
        assert gateway.request("/responses", b'{"model":"test-model"}')[0] == 200
    assert gateway.request("/responses", b'{"model":"test-model"}')[0] == 429
    summary = gateway.summary()
    assert summary["request_counts"] == {
        "forwarded": 3, "denied": 1, "failed": 1, "truncated": 1,
        "content_filtered": 0, "cancelled": 0,
    }
    assert summary["denied_reasons"] == {"request_budget_exhausted": 1}
    assert summary["usage"]["input_tokens"] is None
    assert summary["usage_observed"]["input_tokens"] == {"known": 2, "missing": 1}
    assert summary["wall_seconds"] >= 0
    assert all(event["elapsed_seconds"] >= 0 for event in summary["requests"])


# Existing budget coverage has complete usage only. The running guide's observed
# token caps must still stop forwarding when known usage alone reaches the cap;
# missing usage keeps the reported total unknown, not the budget unenforceable.
@pytest.mark.parametrize('field', ['input_tokens', 'output_tokens'])
def test_known_usage_enforces_token_budget_despite_missing_responses(field):
    config = InferenceConfig('https://example.invalid/v1', 'test-model', 'UNUSED', 5, 10,
                             Asset(b'profile', 'text'), 'responses', **{f'max_{field}': 10})
    responses = [None, {field: getattr(config, f'max_{field}')}, None]
    forwarded = []

    def transport(*args):
        usage = responses[len(forwarded)]
        forwarded.append(usage)
        return 200, 'application/json', json.dumps({'status': 'completed', 'usage': usage}).encode()

    gateway = InferenceGateway(config, transport=transport)
    gateway.deadline = time.monotonic() + 10
    request = b'{"model":"test-model"}'
    assert gateway.request('/responses', request)[0] == 200
    assert gateway.request('/responses', request)[0] == 200
    assert gateway.request('/responses', request)[0] == 429
    assert len(forwarded) == 2
    summary = gateway.summary()
    assert summary['usage'][field] is None
    assert summary['usage_observed'][field] == {'known': 1, 'missing': 1}
    assert summary['denied_reasons'] == {f'{field[:-7]}_token_budget_exhausted': 1}


def test_no_forwarded_requests_are_not_classified_as_model_usage():
    config = gateway_config(max_requests=1)
    gateway = InferenceGateway(config, transport=lambda *args: pytest.fail("Denied request was forwarded"))
    gateway.deadline = time.monotonic()+10
    assert gateway.request("/responses", b'{"model":"test-model","input":[{"file_id":"remote"}]}')[0] == 400
    assert gateway.summary()["requests"] == []
    assert gateway.summary()["run_kind"] == "offline_cli_development"

    gateway._transport = lambda *args: (200, "application/json", b'{"status":"completed"}')
    assert gateway.request("/responses", b'{"model":"test-model"}')[0] == 200
    assert gateway.summary()["run_kind"] == "model_protocol_test"


def test_credential_stays_out_of_public_identity_and_profile_records_http_or_https(tmp_path, monkeypatch):
    source = Path(tmp_path / "profile.toml")
    source.write_text('''
wire_api = "responses"
base_url = "https://example.invalid/v1"
model = "test-model"
api_key_env = "ICLAYOUT_BENCH_TEST_KEY"
max_requests = 2
request_timeout_seconds = 5
max_input_tokens = 100
max_output_tokens = 50
max_wall_seconds = 120
''')
    config = load_inference_config(source)
    monkeypatch.setenv(config.api_key_env, "unique-secret-value")
    gateway = InferenceGateway(config)
    assert "unique-secret-value" not in json.dumps(gateway.public)
    assert gateway.public["socket"] == "/protocol/inference.sock"
    assert gateway.public["max_input_tokens"] == 100
    assert gateway.public["max_output_tokens"] == 50
    assert gateway.public["max_wall_seconds"] == 120
    # Explicit proxy route is part of the profile; credentials cannot hide in it.
    original = source.read_text()
    for wire in ('wire_api = "unknown"', ""):
        source.write_text(original.replace('wire_api = "responses"', wire))
        with pytest.raises(ValueError, match="wire_api"):
            load_inference_config(source)
    proxy_url = 'http://localhost:8123'
    source.write_text(original + f'\nproxy_url = "{proxy_url}"\n')
    assert InferenceGateway(load_inference_config(source)).public['proxy_url'] == proxy_url
    for invalid in ('socks5://localhost:8123', 'http://user:secret@localhost:8123',
                    'http://localhost:8123/path', 'http://localhost:0'):
        source.write_text(original + f'\nproxy_url = "{invalid}"\n')
        with pytest.raises(ValueError, match='proxy'):
            load_inference_config(source)
    source.write_text(original.replace("https://", "http://"))
    assert InferenceGateway(load_inference_config(source)).public['transport'] == 'http'
    source.write_text(source.read_text().replace("http://", "ftp://"))
    with pytest.raises(ValueError, match=r"HTTP\(S\)"):
        load_inference_config(source)


@pytest.mark.parametrize("stream,state,details,outcome,infra", [
    (False, "completed", {}, "completed", False),
    (True, "completed", {}, "completed", False),
    (True, "failed", {"error": {"code": "server_error"}}, "service_error", True),
    (False, "incomplete", {"incomplete_details": {"reason": "max_output_tokens"}}, "budget_truncated", False),
    (False, "incomplete", {"incomplete_details": {"reason": "content_filter"}}, "content_filtered", False),
])
def test_response_semantics_and_usage(stream, state, details, outcome, infra):
    response = {"status": state, **details, "usage": {"input_tokens": 9, "output_tokens": 2}}
    body = json.dumps(response).encode()
    content_type = "application/json"
    if stream:
        body = b'data: ' + json.dumps({"type": f"response.{state}", "response": response}).encode() + b'\n\n'
        content_type = "text/event-stream; charset=utf-8"
    config = gateway_config(max_requests=1)
    gateway = InferenceGateway(config, transport=lambda *args: (200, content_type, body))
    gateway.deadline = time.monotonic() + 10
    gateway.request("/responses", b'{"model":"test-model"}')
    gateway.stop()
    summary = gateway.summary()
    assert summary["infrastructure_error"] is infra
    assert summary["requests"][0]["outcome"] == outcome
    assert summary["usage"]["input_tokens"] == 9


@pytest.mark.parametrize("body", [
    b'data: {"type":"response.created"}\n\n',
    b'data: {"type":"response.completed","response":{"status":"completed"}}\n',
    b'data: not-json\n\n',
])
def test_non_success_sse_cannot_be_scored_as_a_model_failure(body):
    config = gateway_config(max_requests=1)
    gateway = InferenceGateway(config, transport=lambda *args: (200, "text/event-stream", body))
    gateway.deadline = time.monotonic() + 10
    gateway.request("/responses", b'{"model":"test-model"}')
    assert gateway.summary()["infrastructure_error"]


def test_multiline_sse_and_standalone_compaction():
    from benchmarking.engine.inference import response_semantics

    body = b': keepalive\r\nevent: response.completed\r\ndata: {"type":"response.completed",\r\ndata: "response":{"status":"completed"}}\r\n\r\n'
    assert response_semantics("/responses", "text/event-stream", body, "responses")["outcome"] == "completed"
    request = validate_request("/responses/compact", b'{"model":"test-model","input":[],"store":true}',
                               "test-model", "responses")
    assert "store" not in json.loads(request)
    result = response_semantics("/responses/compact", "application/json",
                                b'{"object":"response.compaction","output":[],"usage":{"input_tokens":1}}',
                                "responses")
    assert result["outcome"] == "completed" and result["usage"]["input_tokens"] == 1


def test_malformed_http_200_response_keeps_upstream_status_and_hides_body():
    config = gateway_config(max_requests=1)
    gateway = InferenceGateway(config, transport=lambda *args: (
        200, "application/json", b'{"status":"in_progress","secret":"must-not-forward"}'))
    gateway.deadline = time.monotonic() + 10
    status, content_type, body = gateway.request("/responses", b'{"model":"test-model"}')
    assert status == 200
    assert content_type == "application/json"
    assert body == b'{"error":"Inference response failed validation"}'
    event = gateway.summary()["requests"][0]
    assert event["status"] == 200
    assert event["outcome"] == "protocol_or_transport_error"
    assert gateway.summary()["infrastructure_error"]


def test_request_and_response_persist_before_forwarding(tmp_path, monkeypatch):
    from benchmarking.engine.recorder import RecordingError, RunRecorder

    recorder = RunRecorder(tmp_path / "run")
    def transport(path, body, timeout):
        journal = [json.loads(line) for line in (recorder.root / "events.jsonl").read_text().splitlines()]
        request = journal[-1]
        assert request["kind"] == "inference.request"
        assert (recorder.root / request["data"]["request"]["path"]).read_bytes() == body
        return 200, "application/json", b'{"status":"completed","output":[]}'
    config = gateway_config(max_requests=2)
    gateway = InferenceGateway(config, transport=transport)
    gateway.recorder = recorder
    gateway.deadline = time.monotonic() + 10
    result = gateway.request("/responses", b'{"model":"test-model"}')
    journal = [json.loads(line) for line in (recorder.root / "events.jsonl").read_text().splitlines()]
    assert journal[-1]["kind"] == "inference.result"
    assert (recorder.root / journal[-1]["data"]["response"]["path"]).read_bytes() == result[2]
    # A failure to record the next request must prevent any transport call.
    monkeypatch.setattr(recorder, "event", lambda *a, **kw: (_ for _ in ()).throw(RecordingError("disk full")))
    monkeypatch.setattr(gateway, "_transport", lambda *a: pytest.fail("Unrecorded request was sent"))
    with pytest.raises(RecordingError):
        gateway.request("/responses", b'{"model":"test-model"}')


# Messages is a second real wire family. Expectations follow the published
# message_start -> cumulative message_delta -> message_stop contract; transport
# is the only fake. Protect terminal validation, usage accounting and isolation.
@pytest.mark.parametrize('streaming', [False, True])
def test_messages_terminal_usage_and_client_tool_isolation(streaming):
    from benchmarking.engine.messages import MessagesWireAdapter

    adapter = MessagesWireAdapter()
    request = {'model': 'test-model', 'max_tokens': 32,
               'messages': [{'role': 'user', 'content': 'hello'}],
               'tools': [{'name': 'run_command', 'input_schema': {'type': 'object'}}]}
    validated = adapter.validate_request('/v1/messages', json.dumps(request).encode(), request['model'])
    assert json.loads(validated) == request
    wire = adapter.prepare_request('/v1/messages', validated, request['model'], 'fixture-secret')
    assert wire.headers['x-api-key'] == 'fixture-secret' and wire.path == '/v1/messages'
    message = {'type': 'message', 'role': 'assistant', 'content': [], 'stop_reason': 'end_turn',
               'usage': {'input_tokens': 5, 'output_tokens': 7,
                         'cache_read_input_tokens': 3, 'cache_creation_input_tokens': 2}}
    if streaming:
        initial = {**message, 'stop_reason': None, 'usage': {**message['usage'], 'output_tokens': 1}}
        events = [{'type': 'message_start', 'message': initial},
                  {'type': 'message_delta', 'delta': {}, 'usage': {'output_tokens': 4}},
                  {'type': 'message_delta', 'delta': {'stop_reason': 'end_turn'}, 'usage': {'output_tokens': 7}},
                  {'type': 'message_stop'}]
        body = ''.join('event: ' + event['type'] + '\ndata: ' + json.dumps(event) + '\n\n' for event in events).encode()
        media = 'text/event-stream'
        with pytest.raises(ValueError, match='Truncated'):
            adapter.response_semantics('/v1/messages', media, body[:-1])
    else:
        body, media = json.dumps(message).encode(), 'application/json'
    verdict = adapter.response_semantics('/v1/messages', media, body)
    assert verdict['outcome'] == 'completed'
    assert verdict['usage']['input_tokens'] == 5 + 3 + 2
    assert verdict['usage']['output_tokens'] == 7
    assert verdict['usage']['cached_input_tokens'] == 3
    assert verdict['usage']['cost'] is None
    request['tools'] = [{'type': 'web_search_20250305', 'name': 'web_search'}]
    with pytest.raises(ValueError, match='client-executed'):
        adapter.validate_request('/v1/messages', json.dumps(request).encode(), request['model'])
    request['tools'] = []
    request['messages'][0]['content'] = [{'type': 'image', 'source': {'type': 'url', 'url': 'https://remote.invalid/a'}}]
    with pytest.raises(ValueError, match='inline'):
        adapter.validate_request('/v1/messages', json.dumps(request).encode(), request['model'])


@pytest.mark.parametrize(('reason', 'outcome'), [
    ('max_tokens', 'budget_truncated'),
    ('tool_use', 'completed'),
])
def test_messages_stop_reason_is_independent_of_http_success(reason, outcome):
    from benchmarking.engine.messages import MessagesWireAdapter

    body = json.dumps({'type': 'message', 'stop_reason': reason}).encode()
    assert MessagesWireAdapter().response_semantics('/v1/messages', 'application/json', body)['outcome'] == outcome




def test_gateway_socket_transmits_a_complete_response(tmp_path):
    """Check the public framing directly, without a second maintained client."""
    expected = b'{"status":"completed","usage":{"input_tokens":3}}'
    gateway = InferenceGateway(gateway_config(), transport=lambda *a: (200, "application/json", expected))
    path = tmp_path / "inference.sock"
    gateway.start(path, time.monotonic() + 10)
    try:
        body = b'{"model":"test-model"}'
        header = json.dumps({"path": "/responses", "bytes": len(body)}).encode() + b'\n'
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(2)
            client.connect(str(path))
            client.sendall(header + body)
            with client.makefile("rb") as response:
                frame = json.loads(response.readline())
                assert frame["status"] == 200 and frame["bytes"] == len(expected)
                assert response.read(frame["bytes"]) == expected
        assert gateway.summary()["usage"]["input_tokens"] == 3
    finally:
        gateway.stop()
