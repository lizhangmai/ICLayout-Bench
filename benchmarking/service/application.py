"""Translate HTTP routes into atomic local session operations."""

from benchmarking.protocol import identifier, json_bytes

from .contracts import APIError
from .controller import SessionController


class LocalService:
    """HTTP adapter with controller-owned state and an optional dedicated runtime supervisor."""

    def __init__(self, root, task, resources, backends, image, token, *, seconds=None,
                 revision='unknown', solver_runtime=None, session_control=None):
        self.controller = SessionController(root, task, resources, backends, image, token,
                                            seconds=seconds, revision=revision,
                                            solver_runtime=solver_runtime, session_control=session_control)

    def shutdown(self):
        self.controller.shutdown()

    def handle(self, method, path, query, token, body, key):
        parts = path.strip('/').split('/')
        if parts[:1] != ['sessions']:
            raise APIError(404, 'not_found', 'Route not found')
        if not token:
            raise APIError(401, 'unauthorized', 'Bearer token required')
        if method == 'POST':
            identifier(key)
            json_bytes(body)
        if parts == ['sessions']:
            if method != 'POST' or query:
                raise APIError(404, 'not_found', 'Route not found')
            return self.controller.create(token, body, key)
        sid, tail = parts[1], parts[2:]
        if method == 'POST':
            if query:
                raise ValueError('POST does not accept query parameters')
            operation, target = None, None
            if tail in [['close'], ['files'], ['submissions'], ['executions']]:
                operation = tail[0]
            elif len(tail) == 3 and tail[0] == 'executions' and tail[2] == 'cancel':
                operation, target = 'cancel', tail[1]
            return self.controller.mutate(sid, token, operation, body, key, target=target)
        if method != 'GET':
            raise ValueError('Unsupported method')
        operation, target, offset = self._read_route(tail, query)
        return self.controller.read(sid, token, operation, target=target, offset=offset)

    @staticmethod
    def _read_route(tail, query):
        if not tail and not query:
            return 'status', None, 0
        if tail == ['result'] and not query:
            return 'result', None, 0
        if tail == ['file'] and set(query) == {'path'} and len(query['path']) == 1:
            return 'file', query['path'][0], 0
        if len(tail) == 2 and tail[0] == 'submissions' and not query:
            return 'submission', tail[1], 0
        if (tail == ['observations'] or len(tail) == 2 and tail[0] in {'reports', 'executions'}) and set(query) <= {'offset'}:
            values = query.get('offset', ['0'])
            if len(values) != 1:
                raise ValueError('Expected one offset')
            names = {'observations': 'observations', 'reports': 'report', 'executions': 'execution'}
            return names[tail[0]], tail[1] if len(tail) == 2 else None, int(values[0])
        return None, None, 0
