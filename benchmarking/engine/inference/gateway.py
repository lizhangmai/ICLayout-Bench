"""Host-owned provider-neutral inference gateway."""

import copy
import hashlib
import http.client
import json
import math
import os
import socket
import socketserver
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from benchmarking.files import Asset
from benchmarking.protocol import json_bytes

from ..sessions.recorder import RecordingError
from .contracts import (
    FAILED_OUTCOMES,
    GENERIC_HTTP_ERROR,
    GENERIC_RESPONSE_ERROR,
    INFERENCE_SOCKET,
    MAX_BODY,
    MAX_RESPONSE,
    USAGE_FIELDS,
    WireRequest,
)
from .registry import wire_adapter

INFERENCE_SOURCE_FILES = (
    "__init__.py",
    "config.py",
    "contracts.py",
    "gateway.py",
    "messages.py",
    "registry.py",
    "responses.py",
)


def _inference_source_sha256(package_dir=None):
    """Hash the ordered, declared source set that implements inference."""
    root = Path(package_dir) if package_dir is not None else Path(__file__).parent
    sources = {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in INFERENCE_SOURCE_FILES
    }
    return hashlib.sha256(json_bytes(sources)).hexdigest()


class InferenceGateway:
    """Provider-neutral gateway backed by one registered wire adapter."""

    def __init__(self, config, *, transport=None):
        self.config = config
        self.wire_adapter = wire_adapter(config.wire_api)
        self.is_test = transport is not None
        self._key = None if self.is_test else os.environ.get(config.api_key_env)
        if not self.is_test and not self._key:
            raise ValueError(f"Missing host credential environment variable: {config.api_key_env}")
        if self._key and ("\r" in self._key or "\n" in self._key):
            raise ValueError("Invalid host credential")
        self._transport = transport or self._http
        self._lock = threading.Lock()
        self._connection = None
        self._socket = None
        self.events = []
        self.denied = 0
        self.denied_events = []
        self.limit_reached = False
        self.deadline = 0
        self._started_monotonic = None
        self._stopped_monotonic = None
        self.server = None
        self.recorder = None
        self.shutdown_incomplete = False
        self._stopped = False

    @property
    def public(self):
        return {"model": self.config.model, "base_url": self.config.base_url,
                "wire_api": self.config.wire_api,
                "socket": INFERENCE_SOCKET,
                "max_requests": self.config.max_requests,
                "max_request_bytes": MAX_BODY, "max_response_bytes": MAX_RESPONSE,
                "request_timeout_seconds": self.config.request_timeout_seconds,
                "max_input_tokens": self.config.max_input_tokens,
                "max_output_tokens": self.config.max_output_tokens,
                "max_wall_seconds": self.config.max_wall_seconds,
                "transport": "test" if self.is_test else urlsplit(self.config.base_url).scheme,
                "proxy_url": self.config.proxy_url,
                "source_sha256": _inference_source_sha256()}

    def _http(self, path, body, timeout):
        url = urlsplit(self.config.base_url)
        request_deadline = min(self.deadline, time.monotonic() + timeout)
        prepared = self.wire_adapter.prepare_request(path, body, self.config.model, self._key)
        if not isinstance(prepared, WireRequest):
            raise TypeError("Wire adapter returned an invalid HTTP request")
        relative = urlsplit(prepared.path)
        if (prepared.method.upper() != prepared.method or not prepared.method.isalpha()
                or relative.scheme or relative.netloc or not relative.path.startswith("/")):
            raise ValueError("Wire adapter returned an unsafe HTTP request")
        headers = dict(prepared.headers)
        if (any(not isinstance(name, str) or not name or "\r" in name or "\n" in name for name in headers)
                or any(not isinstance(value, str) or "\r" in value or "\n" in value for value in headers.values())):
            raise ValueError("Wire adapter returned unsafe HTTP headers")
        connection_class = {"https": http.client.HTTPSConnection, "http": http.client.HTTPConnection}[url.scheme]
        if self.config.proxy_url:
            proxy = urlsplit(self.config.proxy_url)
            connection = connection_class(proxy.hostname, proxy.port or 80, timeout=timeout)
            connection.set_tunnel(url.hostname, url.port or (443 if url.scheme == 'https' else 80))
        else:
            connection = connection_class(url.hostname, url.port, timeout=timeout)
        self._connection = connection
        try:
            connection.connect()
            self._socket = connection.sock
            remaining = min(self.deadline, request_deadline) - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Inference deadline exceeded before sending")
            self._socket.settimeout(remaining)
            connection.request(prepared.method, url.path.rstrip("/") + prepared.path, body=body,
                               headers=headers)
            response = connection.getresponse()
            if not 200 <= response.status < 300:
                return response.status, "application/json", b'{"error":"Inference upstream rejected request"}'
            result = bytearray()
            while True:
                remaining = min(self.deadline, request_deadline) - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Inference deadline exceeded")
                if self._socket:
                    self._socket.settimeout(min(timeout, remaining))
                chunk = response.read1(min(65536, MAX_RESPONSE + 1 - len(result)))
                if not chunk:
                    break
                result.extend(chunk)
                if len(result) > MAX_RESPONSE:
                    raise ValueError("Inference response exceeds size limit")
            content = bytes(result)
            if any(value in content for value in (self._key.encode(),
                    json.dumps(self._key)[1:-1].encode(), json.dumps(self._key, ensure_ascii=False)[1:-1].encode())):
                raise ValueError("Upstream response contained credential material")
            return response.status, response.getheader("Content-Type", "application/json"), content
        finally:
            connection.close()
            self._connection = None
            self._socket = None

    def _record(self, kind, **data):
        if self.recorder:
            self.recorder.event(kind, **data)

    def _deny(self, reason):
        self.denied += 1
        event = {"reason": reason, "sequence": len(self.denied_events) + 1}
        self.denied_events.append(event)
        self._record("inference.denied", **event)

    def _token_budget_reason(self):
        for field, limit in (("input_tokens", self.config.max_input_tokens),
                             ("output_tokens", self.config.max_output_tokens)):
            if limit is None:
                continue
            values = [event["usage"].get(field) if isinstance(event.get("usage"), dict) else None
                      for event in self.events]
            # Known usage is a lower bound even when another response omitted
            # counters. Missing usage keeps the reported total unknown, but
            # cannot erase an already-observed budget exhaustion.
            known = sum(value for value in values if type(value) is int and value >= 0)
            if known >= limit:
                return f"{field[:-7]}_token_budget_exhausted"
        return None

    def request(self, path, body):
        if self._stopped:
            self._deny("session_stopped")
            return 429, "application/json", b'{"error":"Inference session stopped"}'
        if not self._lock.acquire(blocking=False):
            self._deny("concurrent_request")
            return 429, "application/json", b'{"error":"Concurrent inference is disabled"}'
        try:
            if self._stopped:
                self._deny("session_stopped")
                return 429, "application/json", b'{"error":"Inference session stopped"}'
            if len(body) > MAX_BODY:
                self._deny("request_too_large")
                return 413, "application/json", b'{"error":"Request too large"}'
            if time.monotonic() >= self.deadline:
                self.limit_reached = True
                self._deny("wall_time_budget_exhausted")
                return 429, "application/json", b'{"error":"Inference budget exhausted"}'
            if len(self.events) >= self.config.max_requests:
                self.limit_reached = True
                self._deny("request_budget_exhausted")
                return 429, "application/json", b'{"error":"Inference budget exhausted"}'
            token_reason = self._token_budget_reason()
            if token_reason:
                self.limit_reached = True
                self._deny(token_reason)
                return 429, "application/json", b'{"error":"Inference budget exhausted"}'
            try:
                payload = self.wire_adapter.validate_request(path, body, self.config.model)
            except (ValueError, TypeError, RecursionError):
                self._deny("invalid_request")
                return 400, "application/json", b'{"error":"Request violates inference profile"}'
            request_started = time.monotonic()
            event = {"path": path, "request_sha256": hashlib.sha256(payload).hexdigest(),
                     "request_bytes": len(payload), "status": None, "usage": None,
                     "sequence": len(self.events) + 1, "outcome": "pending", "started_at": time.time()}
            self.events.append(event)
            if self.recorder:
                event["request"] = self.recorder.archive(Asset(payload, "json"))
            self._record("inference.request", **event)
            try:
                status, content_type, response = self._transport(path, payload, min(
                    self.config.request_timeout_seconds, self.deadline - time.monotonic()))
                if len(response) > MAX_RESPONSE or time.monotonic() >= self.deadline:
                    raise ValueError("Response exceeded session limits")
                event.update(status=status, response_bytes=len(response), response_sha256=hashlib.sha256(response).hexdigest())
                if self.recorder:
                    event["response"] = self.recorder.archive(Asset(response, "text"))
                if 200 <= status < 300:
                    try:
                        semantics = self.wire_adapter.response_semantics(path, content_type, response)
                    except Exception:  # noqa: BLE001 -- keep the upstream status and hide malformed bodies
                        event["outcome"] = "protocol_or_transport_error"
                        result = status, "application/json", GENERIC_RESPONSE_ERROR
                    else:
                        event.update(semantics)
                        result = status, content_type, response
                else:
                    event["outcome"] = "http_error"
                    result = status, "application/json", GENERIC_HTTP_ERROR
                event["content_type"] = content_type
            except RecordingError:
                raise
            except Exception:  # noqa: BLE001 -- never expose transport exceptions or credential-bearing bodies
                event["cancelled"] = time.monotonic() >= self.deadline
                event["status"] = 499 if event["cancelled"] else 502
                event["outcome"] = "cancelled" if event["cancelled"] else "protocol_or_transport_error"
                result = 502, "application/json", b'{"error":"Inference transport failed"}'
            event["elapsed_seconds"] = max(0.0, time.monotonic() - request_started)
            if self._token_budget_reason():
                event["budget_exceeded"] = True
                self.limit_reached = True
            event["finished_at"] = time.time()
            self._record("inference.result", **event)
            return result
        finally:
            self._lock.release()

    def start(self, path, deadline, *, uid=None):
        self._started_monotonic = time.monotonic()
        self._stopped_monotonic = None
        self.deadline = deadline
        if self.config.max_wall_seconds is not None:
            self.deadline = min(self.deadline, self._started_monotonic + self.config.max_wall_seconds)
        gateway = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                self.connection.settimeout(2)
                try:
                    header = json.loads(self.rfile.readline(1025))
                    size = header["bytes"]
                    if type(size) is not int or not 0 <= size <= MAX_BODY:
                        return
                    body = self.rfile.read(size)
                    if len(body) != size:
                        return
                    status, kind, response = gateway.request(header["path"], body)
                    self.wfile.write(json.dumps({"status": status, "type": kind, "bytes": len(response)}).encode()+b"\n")
                    self.wfile.write(response)
                except (OSError, ValueError, KeyError, TypeError, RecursionError):
                    return

        class Server(socketserver.ThreadingUnixStreamServer):
            daemon_threads = True
            slots = threading.BoundedSemaphore(2)

            def process_request(self, request, client_address):
                if not self.slots.acquire(blocking=False):
                    self.shutdown_request(request)
                    return
                super().process_request(request, client_address)

            def process_request_thread(self, request, client_address):
                try:
                    super().process_request_thread(request, client_address)
                finally:
                    self.slots.release()

        self.server = Server(str(path), Handler)
        if uid is not None and os.getuid() == 0:
            os.chown(path, uid, -1)
        Path(path).chmod(0o600)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
        self.thread.start()

    def stop(self):
        self._stopped = True
        self._stopped_monotonic = time.monotonic()
        self.deadline = 0
        if self._socket:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=2)
        # Join the request owner before reading its final semantic verdict.
        if self._lock.acquire(timeout=2):
            self._lock.release()
        else:
            self.shutdown_incomplete = True

    def summary(self):
        usage, usage_observed = {}, {}
        for field in USAGE_FIELDS:
            values = [e["usage"].get(field) if isinstance(e["usage"], dict) else None for e in self.events]
            known = sum(value is not None for value in values)
            usage_observed[field] = {"known": known, "missing": len(values) - known}
            if not values or any(value is None for value in values):
                usage[field] = None
            elif field == "cost":
                usage[field] = sum(values) if all(type(value) in {int, float} and math.isfinite(value)
                                                  and value >= 0 for value in values) else None
            else:
                usage[field] = sum(values) if all(type(value) is int and value >= 0 for value in values) else None
        # A configured profile is not evidence that a model was contacted.
        # Denied requests never enter ``events``; only a forwarded request is
        # enough to classify a run as a model/protocol run.
        run_kind = ("offline_cli_development" if not self.events else
                    "model_protocol_test" if self.is_test else "model_cli_development")
        wall_seconds = ((self._stopped_monotonic - self._started_monotonic)
                        if self._started_monotonic is not None and self._stopped_monotonic is not None
                        else sum(event.get("elapsed_seconds", 0.0) for event in self.events))
        outcomes = [event.get("outcome") for event in self.events]
        counts = {
            "forwarded": len(self.events), "denied": self.denied,
            "failed": sum(outcome in FAILED_OUTCOMES for outcome in outcomes),
            "truncated": sum(outcome == "budget_truncated" for outcome in outcomes),
            "content_filtered": sum(outcome == "content_filtered" for outcome in outcomes),
            "cancelled": sum(outcome == "cancelled" for outcome in outcomes),
        }
        denied_reasons = {}
        for event in self.denied_events:
            denied_reasons[event["reason"]] = denied_reasons.get(event["reason"], 0) + 1
        return {**self.public, "run_kind": run_kind, "requests": copy.deepcopy(self.events), "usage": usage,
                "usage_observed": usage_observed, "wall_seconds": wall_seconds,
                "request_counts": counts, "denied_requests": self.denied,
                "denied_reasons": denied_reasons, "denied": copy.deepcopy(self.denied_events),
                "budget": {"max_requests": self.config.max_requests,
                           "max_input_tokens": self.config.max_input_tokens,
                           "max_output_tokens": self.config.max_output_tokens,
                           "max_wall_seconds": self.config.max_wall_seconds},
                "limit_reached": self.limit_reached,
                "shutdown_incomplete": self.shutdown_incomplete,
                "infrastructure_error": self.shutdown_incomplete or any(e["outcome"] not in {"completed", "budget_truncated",
                                                                  "content_filtered", "cancelled"}
                                            for e in self.events)}
