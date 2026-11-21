"""Synthetic sessions, result files and explicit seams for participant tests."""

import json
import time
from contextlib import nullcontext

from benchmarking.client import ClientError
from benchmarking.protocol import PROTOCOL, USAGE_FIELDS


class ServiceFixture:
    endpoint = 'http://127.0.0.1:8765'

    def __init__(self):
        self.remaining = 120
        self.active = True
        self.closed = []
        self.condition = None
        self.creations = []

    def create(self, task, condition, *, key):
        self.creations.append(key)
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




class FakeClock:
    """Deterministic monotonic and wall clock; ``sleep`` advances both and records the delay."""

    def __init__(self, now=0, *, on_sleep=None):
        self.now, self.delays, self.on_sleep = now, [], on_sleep

    def monotonic(self):
        return self.now

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.delays.append(seconds)
        self.now += seconds
        if self.on_sleep is not None:
            self.on_sleep(seconds)


def unavailable_local_service(*args):
    raise AssertionError('This test supplies no local evaluation service')


def attempt_boundaries(service=None, **overrides):
    """Attempt effects for synthetic sessions, without Docker, vendor CLIs or isolation.

    With ``service``, HTTP clients and local services reach that synthetic service.
    Native commands still run as real child processes unless ``execute`` is replaced.
    """
    from benchmarking.participants.attempt.boundaries import AttemptBoundaries
    from helpers.harness import FixtureRuntime

    defaults = {'isolation': FixtureRuntime, 'cli_version': lambda *args: 'fixture-cli',
                'local_service': unavailable_local_service}
    if service is not None:
        defaults.update(client=lambda *args, **kwargs: service,
                        local_service=lambda *args: nullcontext(service))
    return AttemptBoundaries(**(defaults | overrides))


def host_probes(selection=None, **overrides):
    """Planning probes with a fixed native selection, CLI version and unpinned images."""
    from benchmarking.participants.batch.plan import HostProbes
    from benchmarking.participants.harnesses.contracts import ParticipantSelection
    from benchmarking.version import package_version

    selection = selection or ParticipantSelection({}, {}, {})
    defaults = {'resolve': lambda *args, **kwargs: selection,
                'harness_version': lambda harness: ('1.2.3', 'fixture-cli 1.2.3'),
                'package_version': package_version, 'image_id': lambda image: image}
    return HostProbes(**(defaults | overrides))


def in_process(solve=None, *, attempt=None, clock=time):
    """Batch boundaries that run each slot's owned worker in this process.

    Production starts one worker process per slot. ``solve(access, row, output,
    selection)`` optionally replaces the participant attempt inside that worker.
    """
    from benchmarking.participants.attempt.worker import execute_owned_slot
    from benchmarking.participants.batch.runner import BatchBoundaries, slot_request

    attempt = attempt or attempt_boundaries()

    def run_slot(options, row, selection, repetition, name, output, lease):
        return execute_owned_slot(slot_request(options), row, selection, repetition, name, output, lease,
                                  boundaries=attempt, solve=solve)

    return BatchBoundaries(run_slot=run_slot, clock=clock, attempt=attempt)


def write_dataset(root, names):
    """Minimal local Dataset with one protocol task and process manifest per case."""
    from helpers.protocol import write_protocol_task

    for name in names:
        config = write_protocol_task(root / 'tasks' / name.split('.')[0] / 'fixture/cases' / name)
        (config.parent / 'case.toml').write_text(config.read_text().replace('protocol-test', name))
        process = root / 'tasks' / name.split('.')[0]
        process.mkdir(parents=True, exist_ok=True)
        (process / 'pdk.toml').write_text('id="fixture"\n')
    return root


def case_run(root, task):
    """The only timestamped run directory recorded for ``task``."""
    directory, = (root / task).iterdir()
    return directory
