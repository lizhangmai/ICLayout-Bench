"""Minimal session responses and durable result files for participant tests."""

import json

from benchmarking.client import ClientError
from benchmarking.protocol import PROTOCOL, USAGE_FIELDS


class ServiceFixture:
    endpoint = 'http://127.0.0.1:8765'

    def __init__(self):
        self.remaining = 120
        self.active = True
        self.closed = []
        self.condition = None

    def create(self, task, condition, *, key):
        self.condition = condition
        return {'session_id': 'fixture-session', 'session_token': 'scoped-fixture-token',
                'limits': {'wall_seconds': self.remaining, 'max_command_seconds': self.remaining},
                'task': {'problem': '# Fixture problem\n',
                         'description': {'hours': self.remaining / 3600, 'output': {'path': '/workspace/output/final.gds'}}}}

    def session(self, sid):
        return {'state': 'active' if self.active else 'complete', 'remaining_seconds': self.remaining}

    def submit(self, *args, **kwargs):
        raise ClientError('invalid_request', 'No candidate', status=400)

    def close(self, sid, *, key):
        self.closed.append(sid)
        self.active = False

    def observations(self, sid, *, offset=0):
        return {'session_id': sid, 'provenance': 'server_observed', 'available': True,
                'events': [], 'next_offset': 0, 'has_more': False}

    def result(self, sid):
        return {
            'protocol': PROTOCOL, 'state': 'complete', 'session_id': sid,
            'task_id': 'fixture', 'task_sha256': '0' * 64,
            'condition': self.condition, 'submission': None,
            'outcome': 'no_submission', 'task_success': False, 'failure_reason': None,
            'score': None, 'metrics': {}, 'usage': dict.fromkeys(USAGE_FIELDS),
            'tool_identity': {}, 'limits': {}, 'provenance': {},
            'evaluation_mode': 'self_run',
        }


def terminal_files(output, outcome='no_submission'):
    (output / 'analysis').mkdir(parents=True, exist_ok=True)
    result = ServiceFixture().result('fixture-session')
    result['outcome'] = outcome
    (output / 'analysis/result.json').write_text(json.dumps(result))
    return {'outcome': outcome, 'result': 'analysis/result.json'}


class InFlightService(ServiceFixture):
    """A protocol execution survives the participant; enforce the real service guard."""
    def __init__(self, *, race=False, conflict=False):
        super().__init__()
        self.busy = not race
        self.race, self.conflict = race, conflict
        self.submitted = []

    def session(self, sid):
        return dict(super().session(sid), active_execution_id='in-flight' if self.busy else None)

    def poll(self, sid, eid, *, offset=0):
        import base64
        assert eid == 'in-flight'
        if self.conflict:
            raise ClientError('conflict', 'Execution status conflict', status=409)
        self.busy = False
        raw = b'execution finished scoped-fixture-token\n' if offset == 0 else b''
        return {'execution_id': eid, 'state': 'complete', 'exit_code': 0,
                'log_base64': base64.b64encode(raw).decode(), 'next_offset': offset + len(raw), 'truncated': False}

    def submit(self, sid, path, *, key):
        self.submitted.append((path, key))
        raise AssertionError("Session settlement must never submit workspace output")


