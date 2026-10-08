"""Small synthetic checks for the engine's live-session supervisor."""

import threading
from types import SimpleNamespace

import pytest

from benchmarking.engine.sessions.control import SessionControl

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

    control.start_execution(
        'commands', 'exec', 'sleep fixture', 10, path, 5,
        should_close=lambda: closing.get('value', False),
        on_started=lambda: state.update(started=True),
        on_progress=lambda size, truncated: state.update(size=size, truncated=truncated),
        on_complete=lambda code, size, truncated: (
            order.append(('complete', code, size, truncated)),
            command_completed.set(),
        ),
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
