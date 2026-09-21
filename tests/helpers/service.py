"""Protocol-only simulator: its verdict is always error, never an EDA score."""

import base64
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from benchmarking.protocol import PROTOCOL, USAGE_FIELDS


class Simulator:
    def __init__(self):
        self.requests = {}
        self.files = {}
        self.executions = 0
        self.closed = False
        self.receipt = None
        self.remaining = 600
        self.condition = None
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.dispatch(None)

            def do_POST(self):
                self.dispatch(
                    json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                )

            def dispatch(self, body):
                key = (self.path, self.headers.get("Idempotency-Key"))
                if body is not None and key in owner.requests:
                    old, status, result = owner.requests[key]
                    assert old == body
                else:
                    status, result = owner.handle(self.command, self.path, body)
                    if body is not None:
                        owner.requests[key] = (body, status, result)
                raw = json.dumps(result | {"protocol": PROTOCOL}).encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.endpoint = f"http://127.0.0.1:{self.server.server_port}"

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def handle(self, method, path, body):
        if path == "/sessions":
            self.condition = body["condition"]
            return 201, {
                "session_id": "s",
                "session_token": "session-token",
                "task": {
                    "id": "synthetic",
                    "description": {"output": {"path": "/workspace/output.gds"}},
                },
                "limits": {},
                "tool_identity": {},
            }
        route = path.removeprefix("/sessions/s").strip("/")
        if route == "":
            return 200, {
                "state": "complete" if self.closed else "active",
                "remaining_seconds": self.remaining,
            }
        if route == "files":
            self.files[body["path"]] = base64.b64decode(body["content_base64"])
            return 200, {"path": body["path"]}
        if route == "executions":
            self.executions += 1
            self.files["output.gds"] = b"protocol fixture, not a layout"
            return 202, {"execution_id": "e", "state": "running"}
        if route.startswith("executions/e"):
            return 200, {
                "execution_id": "e",
                "state": "complete",
                "exit_code": 0,
                "truncated": False,
                "log_base64": "",
                "next_offset": 0,
            }
        if route == "submissions":
            if body["path"] not in self.files:
                return 400, {
                    "error": {"code": "invalid_request", "message": "Missing candidate"}
                }
            self.receipt = {
                "submission_id": "r",
                "sequence": len(self.requests),
                "candidate_sha256": hashlib.sha256(
                    self.files[body["path"]]
                ).hexdigest(),
            }
            return 200, self.receipt
        if route == "close":
            self.closed = True
            return 202, {"state": "evaluating"}
        if route == "result":
            return 200, {
                "session_id": "s",
                "state": "error",
                "task_id": "synthetic",
                "task_sha256": "0" * 64,
                "condition": self.condition,
                "limits": {},
                "tool_identity": {},
                "verification_level": "local_development",
                "provenance": {"usage": "unknown"},
                "usage": dict.fromkeys(USAGE_FIELDS),
                "submission": self.receipt,
                "outcome": "error",
                "score": None,
                "task_success": None,
                "metrics": {},
                "failure_reason": "protocol_simulator",
                "test_only": True,
            }
        return 404, {"error": {"code": "not_found", "message": "Unknown route"}}
