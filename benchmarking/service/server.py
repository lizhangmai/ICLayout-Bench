"""HTTP framing for the local development service.

The public ``LocalService`` and ``serve`` entry points stay here for callers.
Application behavior and durable request state live in neighboring modules.
"""

import json
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from benchmarking.files import EvidenceError
from benchmarking.protocol import PROTOCOL, json_bytes

from .application import LocalService
from .contracts import APIError, session_limits

__all__ = ['APIError', 'Handler', 'LocalService', 'serve', 'session_limits']


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Avoid credentials, query paths and candidate data in access logs.

    def do_GET(self):
        self._dispatch()

    def do_POST(self):
        self._dispatch()

    def _dispatch(self):
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
        except Exception:  # noqa: BLE001 -- sanitize unexpected service failures
            traceback.print_exc()
            status, result = 500, {
                'error': {'code': 'infrastructure_error',
                          'message': 'Service operation failed', 'retryable': False},
            }
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


def serve(service, port=0):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.service = service
    return server
