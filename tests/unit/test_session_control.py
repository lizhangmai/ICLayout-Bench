"""Small synthetic checks for the engine's live-session supervisor."""

import threading
import time
from types import SimpleNamespace

import pytest

from benchmarking.service.supervisor import SessionControl

pytestmark = pytest.mark.unit


class FakeWorkspace:
    def __init__(self, process=None):
        self.process = process
        self.active = True
        self.requests = []
        self.cancelled = []
        self.closed = threading.Event()

    def remaining(self):
        return 60

    def execute(self, eid, command, timeout):
        return self.process

    def cancel(self, eid):
        self.cancelled.append(eid)
        self.process.cancel()

    def request(self, action):
        self.requests.append(action)
        if action == {'action': 'close'}:
            self.active = False
            self.closed.set()


def _session_factory(image, ready, *, runtime=None):
    return SimpleNamespace(image_id='synthetic-image', ready=ready)


def test_resume_rejects_changed_image_before_provisioning(monkeypatch):
    import json

    from benchmarking.execution.workspace.docker import DockerSession

    calls = []
    def inspect(command, **kwargs):
        calls.append(command)
        return json.dumps([{'Id': 'changed-image', 'Config': {}}])
    monkeypatch.setattr('benchmarking.execution.workspace.docker.subprocess.check_output', inspect)
    checkpoint = {'state': {'tool_identity': {'image_id': 'original-image'}}}
    with pytest.raises(ValueError, match='changed solver image'):
        DockerSession('image', resume=checkpoint)
    assert all(command[:3] == ['docker', 'image', 'inspect'] for command in calls)


def test_session_control_passes_attached_session_and_reports_readiness():
    workspace = FakeWorkspace()
    completed = threading.Event()
    observed = {}
    errors = []

    def runner(task, config, resources, backends, destination, *, session, execution):
        observed['session'] = session
        session.ready(workspace, object())
        return {'outcome': 'no_submission'}

    control = SessionControl(runner=runner, session_factory=_session_factory)
    callbacks = []
    handle = control.start(
        'sid', task=object(), config=object(), resources={}, backends={},
        destination='unused', image='unused', execution={},
        on_ready=lambda current, recorder, session: callbacks.append((current, session)),
        on_complete=lambda report: (callbacks.append(report), completed.set()),
        on_error=errors.append,
    )

    signaled, attached = control.await_ready(handle, 1)
    assert signaled and attached
    assert control.workspace('sid') is workspace
    assert callbacks[0] == (workspace, observed['session'])
    assert completed.wait(1)
    control.join('sid', timeout=1)
    assert callbacks[1] == {'outcome': 'no_submission'}
    assert errors == []


def test_timed_out_startup_abandons_late_workspace_attachment():
    release = threading.Event()
    workspace = FakeWorkspace()
    errors = []

    def runner(task, config, resources, backends, destination, *, session, execution):
        assert release.wait(1)
        session.ready(workspace, object())

    control = SessionControl(runner=runner, session_factory=_session_factory)
    handle = control.start(
        'late', task=object(), config=object(), resources={}, backends={},
        destination='unused', image='unused', execution={},
        on_ready=lambda *_args: None,
        on_complete=lambda _report: None,
        on_error=errors.append,
    )

    signaled, attached = control.await_ready(handle, 0.01)
    assert not signaled and not attached
    release.set()
    control.join('late', timeout=1)
    assert control.workspace('late') is None
    assert handle.startup_exception_type == 'RuntimeError'
    assert errors == []


class BlockingOutput:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.started = threading.Event()
        self.release = threading.Event()

    def read1(self, _size):
        self.started.set()
        self.release.wait(1)
        return self.chunks.pop(0) if self.chunks else b''


class FakeProcess:
    def __init__(self, output):
        self.stdin = SimpleNamespace(write=lambda _raw: None, close=lambda: None)
        self.stdout = output
        self.cancelled = False

    def poll(self):
        return None if not self.cancelled else 125

    def cancel(self):
        self.cancelled = True
        self.stdout.release.set()

    def wait(self):
        return 125 if self.cancelled else 0


def test_command_log_is_bounded_and_close_waits_for_command_drain(tmp_path):
    output = BlockingOutput([b'first', b'-extra'])
    process = FakeProcess(output)
    workspace = FakeWorkspace(process)
    from benchmarking.execution.budgets import PhaseBudgets, SessionBudget
    workspace.budget = SessionBudget(PhaseBudgets(60), time.monotonic()+60)
    workspace.budget.begin_operation(10)
    command_completed = threading.Event()
    order = []
    closing = {}

    def runner(task, config, resources, backends, destination, *, session, execution):
        session.ready(workspace, object())
        assert workspace.closed.wait(1)
        return {'outcome': 'no_submission'}

    control = SessionControl(runner=runner, session_factory=_session_factory)
    handle = control.start(
        'commands', task=object(), config=object(), resources={}, backends={},
        destination='unused', image='unused', execution={},
        on_ready=lambda *_args: None,
        on_complete=lambda _report: None,
        on_error=lambda error: (_ for _ in ()).throw(error),
    )
    assert control.await_ready(handle, 1) == (True, True)
    path = tmp_path / 'bounded.log'
    state = {}

    def completed(code, size, truncated):
        # Publishing command completion must release its budget before a caller
        # can begin another operation; late cleanup must not clear a new budget.
        workspace.budget.begin_operation(5)
        order.append(('complete', code, size, truncated))
        command_completed.set()

    control.start_execution(
        'commands', 'exec', 'sleep fixture', 10, path, 5,
        should_close=lambda: closing.get('value', False),
        on_started=lambda: state.update(started=True),
        on_progress=lambda size, truncated: state.update(size=size, truncated=truncated),
        on_complete=completed,
    )
    assert state['started']
    assert output.started.wait(1)
    closing['value'] = True
    control.close_session('commands', 'exec')

    assert command_completed.wait(1)
    assert workspace.closed.wait(1)
    order.append(('closed',))
    control.join('commands', timeout=1)
    assert workspace.cancelled == ['exec']
    assert path.read_bytes() == b'first'
    assert state['size'] == 5 and state['truncated'] is True
    assert order == [('complete', 125, 5, True), ('closed',)]


def test_startup_failure_is_durable_and_same_key_never_starts_another_worker(tmp_path, executable_case):
    import json

    from benchmarking.service.server import APIError, LocalService
    from benchmarking.tasks.contract import load_task
    task = load_task(executable_case)
    attempts = []
    def broken_startup(*args, **kwargs):
        attempts.append(1)
        raise OSError('resource archive unavailable')
    body = {'task_id': task.id, 'condition': {'harness_kind': 'agent', 'harness_id': 'startup-test',
            'harness_version': '1', 'model': 'none', 'prompt_sha256': None, 'configuration_sha256': None}}
    root = tmp_path / 'service'
    for _ in range(2):
        control = SessionControl(runner=broken_startup, session_factory=lambda *args, **kwargs: object())
        service = LocalService(root, task, {}, {}, 'unused', 'access', seconds=60, session_control=control)
        try:
            for _ in range(2):
                with pytest.raises(APIError):
                    service.handle('POST', '/sessions', {}, 'access', body, 'same-create')
            assert len(attempts) == 1
            metadata = list(root.glob('*/http.json'))
            assert len(metadata) == 1
            data = json.loads(metadata[0].read_text())
            assert data['interrupted'] is True
            assert data['creation_key'] == 'same-create'
            assert (metadata[0].parent / 'startup.json').is_file()
        finally:
            service.shutdown()


def test_slow_resource_provisioning_has_separate_startup_and_solve_budgets(tmp_path, executable_case):
    from benchmarking.service.server import LocalService
    from benchmarking.tasks.contract import load_task
    task = load_task(executable_case)
    release = threading.Event()
    observed = []
    class ProvisioningEvent(threading.Event):
        def wait(self, timeout=None):
            observed.append(timeout)
            # Simulate 90 seconds of durable resource staging without a slow test.
            # The former 45-second window abandons this otherwise healthy startup.
            if timeout is not None and timeout < 90:
                return False
            release.set()
            return super().wait(2)
    events = iter([ProvisioningEvent(), threading.Event()])
    def provision(task, config, resources, backends, destination, *, session, **kwargs):
        assert release.wait(2)
        destination.mkdir()
        (destination / 'events.jsonl').write_text('')
        session.ready(SimpleNamespace(remaining=lambda: config.wall_seconds, active=False), None)
        return {'outcome': 'no_submission'}
    control = SessionControl(
        runner=provision,
        session_factory=lambda image, callback, **kwargs: SimpleNamespace(image_id='fixture-image', ready=callback),
        threading_provider=lambda: SimpleNamespace(Event=lambda: next(events), Lock=threading.Lock,
                                                   Thread=threading.Thread))
    service = LocalService(tmp_path / 'service', task, {}, {}, 'unused', 'access', seconds=60,
                           recoverable=False, session_control=control)
    body = {'task_id': task.id, 'condition': {'harness_kind': 'agent', 'harness_id': 'startup-test',
            'harness_version': '1', 'model': 'none', 'prompt_sha256': None, 'configuration_sha256': None}}
    try:
        status, created = service.handle('POST', '/sessions', {}, 'access', body, 'creation')
        assert status == 201
        assert created['limits']['wall_seconds'] == service.controller.limits['wall_seconds']
        assert observed and observed[0] > service.controller.limits['wall_seconds']
        assert service.handle('POST', '/sessions', {}, 'access', body, 'creation') == (status, created)
        assert len(service.controller.state.runs) == 1
    finally:
        release.set()
        service.shutdown()
