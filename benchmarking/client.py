"""Generic layout-http.v1 client; no Docker, model SDK or Private dependency."""

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .protocol import PROTOCOL

MAX_RESPONSE_BYTES = 16 * 1024 * 1024
_KEY = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")


def _reject_constant(value):
    raise ValueError("Non-finite JSON number")


class ClientError(Exception):
    """A structured service error or a locally rejected response."""

    def __init__(self, code, message, *, status=None, retryable=False):
        super().__init__(message)
        self.code, self.status, self.retryable = code, status, retryable


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward a session credential to a redirected endpoint.


def _identifier(value):
    if not isinstance(value, str) or not _KEY.fullmatch(value):
        raise ValueError("Invalid opaque identifier or idempotency key")
    return value


class Client:
    """Explicit retries: retain and replay the same key after uncertain delivery.

    The client never retries mutations automatically and never invents model usage.
    Construct a new instance with the returned session token after creation.
    """

    def __init__(self, endpoint, token, *, timeout=30, max_response_bytes=MAX_RESPONSE_BYTES):
        parsed = urlsplit(endpoint)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError("Expected a service URL without credentials, query or fragment")
        if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Non-loopback service endpoints require HTTPS")
        if not isinstance(token, str) or not token or any(ord(c) < 33 or ord(c) > 126 for c in token):
            raise ValueError("Expected a nonempty bearer token")
        if timeout <= 0 or max_response_bytes <= 0:
            raise ValueError("Timeout and response limit must be positive")
        self.endpoint = endpoint.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.max_response_bytes = max_response_bytes
        self._opener = build_opener(ProxyHandler({}), _NoRedirect())

    def request(self, method, path, body=None, *, key=None):
        if not path.startswith("/v1/") or path.startswith("//") or "#" in path:
            raise ValueError("Expected a /v1/ service path")
        if method not in {"GET", "POST"}:
            raise ValueError("Only GET and POST are supported")
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        data = None
        if method == "POST":
            headers["Idempotency-Key"] = _identifier(key)
            headers["Content-Type"] = "application/json"
            data = json.dumps(body, allow_nan=False, separators=(",", ":")).encode()
        elif body is not None or key is not None:
            raise ValueError("GET does not accept a body or idempotency key")
        req = Request(self.endpoint + path, data=data, headers=headers, method=method)
        try:
            try:
                response = self._opener.open(req, timeout=self.timeout)
            except HTTPError as error:
                response = error
            with response:
                status = response.code
                raw = response.read(self.max_response_bytes + 1)
        except (URLError, TimeoutError, OSError) as error:
            raise ClientError("transport_error", "Delivery unknown; query status or replay the same key",
                              retryable=True) from error
        if len(raw) > self.max_response_bytes:
            raise ClientError("invalid_response", "Service response exceeds client limit", status=status)
        try:
            result = json.loads(raw, parse_constant=_reject_constant)
        except (ValueError, UnicodeDecodeError) as error:
            raise ClientError("invalid_response", "Service returned invalid JSON", status=status) from error
        if not isinstance(result, dict) or result.get("protocol") != PROTOCOL:
            raise ClientError("incompatible_protocol", "Unsupported service response", status=status)
        if not 200 <= status < 300:
            detail = result.get("error", {})
            if not isinstance(detail, dict):
                detail = {}
            raise ClientError(detail.get("code", "invalid_response"),
                              str(detail.get("message", "Service request failed")), status=status,
                              retryable=detail.get("retryable") is True)
        return result

    def create(self, task_id, condition, *, key):
        return self.request("POST", "/v1/sessions", {"task_id": task_id, "condition": condition}, key=key)

    def session(self, session_id, operation="", body=None, *, key=None):
        path = f"/v1/sessions/{_identifier(session_id)}"
        if operation:
            path += "/" + operation
        return self.request("POST" if key is not None else "GET", path, body, key=key)

    def read(self, session_id, path):
        result = self.session(session_id, "file?" + urlencode({"path": path}))
        try:
            content = base64.b64decode(result["content_base64"], validate=True)
            if len(content) != result["size_bytes"] or hashlib.sha256(content).hexdigest() != result["sha256"]:
                raise ValueError("Content digest mismatch")
        except (KeyError, ValueError, TypeError) as error:
            raise ClientError("invalid_response", "File integrity check failed") from error
        return content

    def write(self, session_id, path, content, *, key):
        return self.session(session_id, "files", {
            "path": path, "content_base64": base64.b64encode(content).decode("ascii")}, key=key)

    def execute(self, session_id, command, timeout_seconds, *, key):
        return self.session(session_id, "executions", {
            "command": command, "timeout_seconds": timeout_seconds}, key=key)

    def poll(self, session_id, execution_id, *, offset=0):
        if type(offset) is not int or offset < 0:
            raise ValueError("Offset must be a nonnegative integer")
        return self.session(session_id, f"executions/{_identifier(execution_id)}?offset={offset}")

    def submit(self, session_id, path, *, key):
        return self.session(session_id, "submissions", {"path": path}, key=key)

    def close(self, session_id, *, key):
        return self.session(session_id, "close", {}, key=key)

    def result(self, session_id):
        return self.session(session_id, "result")


def command_main(argv):
    """Small shell-friendly view of the same client, useful to any local harness."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "exec", "submit", "close", "result", "read", "write"))
    parser.add_argument("value", nargs="?")
    parser.add_argument("--key")
    parser.add_argument("--seconds", type=float, default=120)
    parser.add_argument("--export", help="Export a terminal result to a new directory")
    args = parser.parse_args(argv)
    client = Client(os.environ.get("ICLAYOUT_BENCH_ENDPOINT", ""), os.environ.get("ICLAYOUT_BENCH_TOKEN", ""))
    sid = os.environ.get("ICLAYOUT_BENCH_SESSION", "")
    if args.action == "exec":
        started = client.execute(sid, args.value, args.seconds, key=args.key)
        offset = 0
        while True:
            status = client.poll(sid, started["execution_id"], offset=offset)
            raw = base64.b64decode(status["log_base64"], validate=True)
            sys.stdout.buffer.write(raw)
            sys.stdout.buffer.flush()
            offset = status["next_offset"]
            if status["state"] != "running" and not raw:
                print(json.dumps({k: status[k] for k in ("state", "exit_code", "truncated")}), file=sys.stderr)
                return 0 if status["exit_code"] == 0 else 1
            time.sleep(.2)
    elif args.action == "submit":
        result = client.submit(sid, args.value, key=args.key)
    elif args.action == "close":
        result = client.close(sid, key=args.key)
    elif args.action == "read":
        sys.stdout.buffer.write(client.read(sid, args.value))
        return 0
    elif args.action == "write":
        result = client.write(sid, args.value, sys.stdin.buffer.read(MAX_RESPONSE_BYTES), key=args.key)
    elif args.action == "result":
        result = client.result(sid)
        if args.export:
            from .analysis import export_session_result
            export_session_result(result, args.export)
    else:
        result = client.session(sid)
    print(json.dumps(result, allow_nan=False))
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in {"status", "exec", "submit", "close", "result", "read", "write"}:
        try:
            return command_main(argv)
        except (ClientError, ValueError, OSError) as error:
            print(str(error), file=sys.stderr)
            return 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default=os.environ.get("ICLAYOUT_BENCH_ENDPOINT"))
    parser.add_argument("--token-env", default="ICLAYOUT_BENCH_TOKEN")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--session", default=os.environ.get("ICLAYOUT_BENCH_SESSION"))
    parser.add_argument("--key", help="Required for POST; retain this value for retries")
    parser.add_argument("method", choices=("GET", "POST"))
    parser.add_argument("operation", help="Session-relative route, or sessions for creation")
    parser.add_argument("--json", default="-", help="POST body file; default reads stdin")
    args = parser.parse_args(argv)
    try:
        if not args.endpoint:
            raise ValueError("Set --endpoint or ICLAYOUT_BENCH_ENDPOINT")
        client = Client(args.endpoint, os.environ.get(args.token_env, ""), timeout=args.timeout)
        body = None
        if args.method == "POST":
            if args.json == "-":
                body = json.load(sys.stdin)
            else:
                with open(args.json) as stream:
                    body = json.load(stream)
        if args.session:
            path = f"/v1/sessions/{_identifier(args.session)}"
            if args.operation != "status":
                path += "/" + args.operation
        else:
            if args.operation != "sessions":
                raise ValueError("Set --session for session operations")
            path = "/v1/sessions"
        result = client.request(args.method, path, body, key=args.key)
        print(json.dumps(result, allow_nan=False))
    except (ClientError, ValueError, OSError) as error:
        code = error.code if isinstance(error, ClientError) else "invalid_request"
        print(json.dumps({"error": {"code": code, "message": str(error)}}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
