"""HTTP framing for the local development service.

The public ``LocalService`` and ``serve`` entry points stay here for callers.
Application behavior and durable request state live in neighboring modules.
"""

import json
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from benchmarking.files import EvidenceError, append_event
from benchmarking.protocol import PROTOCOL, json_bytes

from .application import LocalService
from .contracts import APIError, session_limits

__all__ = ['APIError', 'Handler', 'LocalService', 'serve', 'session_limits']


def operation(path):
    """Project routes to fixed verbs, excluding IDs, filenames and query data."""
    parts = urlsplit(path).path.strip('/').split('/')
    if parts == ['sessions']:
        return 'create'
    if len(parts) < 2 or parts[0] != 'sessions':
        return 'unknown'
    tail = parts[2:]
    if not tail:
        return 'status'
    if len(tail) == 1 and tail[0] in {'close', 'files', 'file', 'submissions', 'executions', 'result', 'observations'}:
        return tail[0]
    if len(tail) == 2 and tail[0] in {'executions', 'submissions', 'reports'}:
        return {'executions': 'execution', 'submissions': 'submission', 'reports': 'report'}[tail[0]]
    if len(tail) == 3 and tail[0] == 'executions' and tail[2] == 'cancel':
        return 'cancel'
    return 'unknown'


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Avoid credentials, query paths and candidate data in access logs.

    def do_GET(self):
        self._dispatch()

    def do_POST(self):
        self._dispatch()

    def _dispatch(self):
        started = time.monotonic()
        exception_type = None
        exception_frames = []
        self.connection.settimeout(30)
        try:
            url = urlsplit(self.path)
            body = None
            if self.command == 'POST':
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 6 * 1024 * 1024:
                    raise APIError(413, 'too_large', 'Request size exceeds limit')
                body = json.loads(self.rfile.read(size))
            auth = self.headers.get('Authorization', '')
            token = auth[7:] if auth.startswith('Bearer ') else ''
            status, result = self.server.service.handle(
                self.command, url.path, parse_qs(url.query), token, body,
                self.headers.get('Idempotency-Key'),
            )
        except APIError as error:
            status, result = error.status, {
                'error': {'code': error.code, 'message': str(error),
                          'retryable': error.status == 503},
            }
        except EvidenceError:
            status, result = 500, {
                'error': {'code': 'infrastructure_error',
                          'message': 'Service evidence is invalid', 'retryable': False},
            }
        except (ValueError, TypeError, KeyError):
            status, result = 400, {
                'error': {'code': 'invalid_request', 'message': 'Invalid request',
                          'retryable': False},
            }
        except Exception as error:  # noqa: BLE001 -- sanitize unexpected service failures
            exception_type = type(error).__name__
            exception_frames = [{'file': Path(frame.filename).name, 'function': frame.name, 'line': frame.lineno}
                                for frame in traceback.extract_tb(error.__traceback__)[-12:]]
            status, result = 500, {
                'error': {'code': 'infrastructure_error',
                          'message': 'Service operation failed', 'retryable': False},
            }
        audit = getattr(self.server, 'audit', None)
        if audit is not None:
            code = (result.get('error') or {}).get('code')
            safe_codes = {'too_large', 'unauthorized', 'not_found', 'session_closed', 'conflict',
                          'infrastructure_error', 'invalid_request', 'budget_exhausted', 'unavailable'}
            try:
                event = append_event(audit, 'http_request', method=self.command, operation=operation(self.path),
                                     status=status, elapsed_seconds=time.monotonic() - started,
                                     error_code=code if code in safe_codes else 'unknown' if code else None,
                                     exception_type=exception_type, exception_frames=exception_frames)
            except OSError:
                event = {'event': 'http_audit_unavailable', 'status': status}
            print(json.dumps(event), file=sys.stderr, flush=True)
        raw = json_bytes(result | {'protocol': PROTOCOL})
        try:
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            if status == 503:
                self.send_header('Retry-After', '1')
            self.end_headers()
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Durable mutations can be replayed with the same idempotency key.


def serve(service, port=0, *, audit=None):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.service = service
    server.audit = audit
    return server
