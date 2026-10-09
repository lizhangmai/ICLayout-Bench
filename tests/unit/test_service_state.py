"""Recover HTTP receipts when report completion precedes their projection."""

import json
from types import SimpleNamespace

import pytest

from benchmarking.files import write_json
from benchmarking.service.state import ServiceState

pytestmark = pytest.mark.unit


def test_finished_report_replays_committed_submission_before_http_projection(tmp_path):
    run = tmp_path / 'session' / 'run'
    run.mkdir(parents=True)
    creation = {'body': {'task_id': 'task'}, 'status': 201, 'response': {'session_id': 'session'}}
    write_json(run.parent / 'http.json', {
        'session_id': 'session', 'requests': {'create:original': creation},
        'submissions': {}, 'executions': {}, 'deadline': 123,
    })
    report = {'phase': 'finished', 'outcome': 'pass'}
    write_json(run / 'run.json', report)
    receipt = {'accepted': True, 'sequence': 1, 'sha256': 'a' * 64,
               'bytes': 7, 'idempotency_key': 'submission-key'}
    events = [
        {'kind': 'session.created', 'data': {'container_id': 'finished-container'}},
        {'kind': 'submission', 'time': '2026-01-01T00:00:00Z', 'data': {'receipt': receipt}},
    ]
    (run / 'events.jsonl').write_text(''.join(json.dumps(dict(event, sequence=i)) + '\n'
                                           for i, event in enumerate(events, 1)))

    task = SimpleNamespace(output=SimpleNamespace(path='output/final.gds'))
    state = ServiceState(tmp_path, task)
    assert not state.abandoned_containers
    recovered = state.runs['session']
    assert recovered['report'] == report
    assert recovered['submissions']['1']['candidate_sha256'] == 'a' * 64
    replay = recovered['requests']['submissions:submission-key']
    assert replay['body'] == {'path': 'output/final.gds'}
    assert replay['response']['sequence'] == 1
    assert recovered['requests']['create:original'] == creation
    assert recovered['deadline'] == 123 and not recovered.get('interrupted')
    assert json.loads((run.parent / 'http.json').read_text()) == recovered
    assert ServiceState(tmp_path, task).runs['session'] == recovered


def test_interrupted_recovery_retains_receipts_and_marks_commands_unknown(tmp_path):
    run = tmp_path / 'session' / 'run'
    run.mkdir(parents=True)
    write_json(run.parent / 'http.json', {
        'session_id': 'session', 'requests': {}, 'submissions': {},
        'executions': {'command': {'state': 'running'}},
    })
    events = [
        {'kind': 'session.created', 'data': {'container_id': 'abandoned-container'}},
        {'kind': 'submission', 'time': '2026-01-01T00:00:00Z', 'data': {'receipt': {
            'accepted': True, 'sequence': 1, 'sha256': 'b' * 64,
            'bytes': 7, 'idempotency_key': 'submission-key',
        }}},
    ]
    (run / 'events.jsonl').write_text(''.join(json.dumps(dict(event, sequence=i)) + '\n'
                                           for i, event in enumerate(events, 1)) + '{')
    task = SimpleNamespace(output=SimpleNamespace(path='output/final.gds'))
    state = ServiceState(tmp_path, task)
    recovered = state.runs['session']
    assert state.abandoned_containers == ['abandoned-container']
    assert recovered['interrupted']
    assert recovered['executions']['command'] == {'state': 'error', 'exit_code': None}
    assert recovered['submissions']['1']['candidate_sha256'] == 'b' * 64
    assert recovered['requests']['submissions:submission-key']['response']['sequence'] == 1


def test_concurrent_mutation_replay_is_atomic_and_survives_restart(tmp_path, executable_case):
    import base64
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    from benchmarking.engine.sessions.control import SessionControl
    from benchmarking.service.application import LocalService
    from benchmarking.service.contracts import APIError
    from benchmarking.tasks import load_task

    task = load_task(executable_case)
    writes = []
    class Workspace:
        active = True
        def write(self, path, raw, limit):
            time.sleep(.02)
            writes.append((path, raw))
    class Control(SessionControl):
        def workspace(self, sid):
            return Workspace()
    service = LocalService(tmp_path, task, {}, {}, 'unused', 'operator', seconds=60,
                           session_control=Control())
    sid = 'session'
    (tmp_path / sid).mkdir()
    service.controller.state.register({
        'session_id': sid, 'token': 'scoped', 'deadline_epoch': time.time() + 60,
        'retained_epoch': time.time() + 600, 'created_at': 'start', 'deadline': 'deadline',
        'requests': {}, 'submissions': {}, 'executions': {}, 'limits': service.controller.limits,
    })
    body = {'path': 'output/candidate.gds', 'content_base64': base64.b64encode(b'candidate').decode()}
    barrier = threading.Barrier(2)
    def write():
        barrier.wait()
        return service.handle('POST', f'/sessions/{sid}/files', {}, 'scoped', body, 'write')
    try:
        with ThreadPoolExecutor(2) as pool:
            first, second = [future.result() for future in [pool.submit(write), pool.submit(write)]]
        assert first == second and first[0] == 200
        assert writes == [('output/candidate.gds', b'candidate')]
        with pytest.raises(APIError) as conflict:
            service.handle('POST', f'/sessions/{sid}/files', {}, 'scoped', dict(body, path='different'), 'write')
        assert conflict.value.status == 409
        with pytest.raises(APIError) as denied:
            service.handle('POST', f'/sessions/{sid}/files', {}, 'operator', body, 'new')
        assert denied.value.status == 404
        durable = json.loads((tmp_path / sid / 'http.json').read_text())
        assert durable['requests']['files:write']['response'] == first[1]
        assert len(durable['observations']) == 1
    finally:
        service.shutdown()
    recovered = LocalService(tmp_path, task, {}, {}, 'unused', 'operator', seconds=60)
    try:
        assert recovered.handle('POST', f'/sessions/{sid}/files', {}, 'scoped', body, 'write') == first
    finally:
        recovered.shutdown()


def test_injected_runtime_serves_a_scoped_session_over_http(tmp_path, executable_case):
    import threading

    from benchmarking.client import Client, ClientError
    from benchmarking.engine.sessions.control import SessionControl
    from benchmarking.engine.sessions.recorder import RunRecorder
    from benchmarking.service.application import LocalService
    from benchmarking.service.server import serve
    from benchmarking.tasks import load_task

    class Workspace:
        active = True

        def __init__(self):
            self.closed = threading.Event()
            self.files = {}

        def remaining(self):
            return 60

        def write(self, path, raw, limit):
            self.files[path] = raw

        def read(self, path, limit):
            return self.files[path]

        def request(self, body):
            assert body == {'action': 'close'}
            self.active = False
            self.closed.set()

    workspace = Workspace()

    def runner(task, config, resources, backends, destination, *, session, execution):
        recorder = RunRecorder(destination)
        session.ready(workspace, recorder)
        assert workspace.closed.wait(5)
        report = {'termination': 'closed', 'outcome': 'no_submission',
                  'task_success': False, 'events': {}}
        recorder.finish(report)
        return report

    control = SessionControl(
        runner=runner,
        session_factory=lambda image, ready, **kwargs: SimpleNamespace(image_id='synthetic-image', ready=ready))
    task = load_task(executable_case)
    service = LocalService(tmp_path, task, {}, {}, 'unused', 'operator', seconds=60,
                           session_control=control)
    server = serve(service)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
    thread.start()
    try:
        access = Client(f'http://127.0.0.1:{server.server_port}', 'operator')
        condition = {'harness_kind': 'agent', 'harness_id': 'synthetic', 'harness_version': '1',
                     'model': 'none', 'prompt_sha256': None, 'configuration_sha256': None}
        created = access.create(task.id, condition, key='create')
        sid = created['session_id']
        client = Client(access.endpoint, created['session_token'])
        assert created['tool_identity']['image_id'] == 'synthetic-image'
        first = client.write(sid, 'candidate.txt', b'candidate', key='write')
        assert client.write(sid, 'candidate.txt', b'candidate', key='write') == first
        assert client.read(sid, 'candidate.txt') == b'candidate'
        with pytest.raises(ClientError) as denied:
            access.read(sid, 'candidate.txt')
        assert denied.value.status == 404
        client.close(sid, key='close')
        control.join(sid, timeout=1)
        result = client.result(sid)
        assert result['state'] == 'complete' and result['outcome'] == 'no_submission'
        assert result['evaluation_mode'] == 'self_run'
        assert all(value is None for value in result['usage'].values())
        with pytest.raises(ClientError) as invalid:
            client.request('GET', f'/sessions/{sid}/reports/invalid')
        assert invalid.value.status == 400
        report = tmp_path / sid / 'run/feedback/check-1/participant-report.json'
        with pytest.raises(ClientError) as missing:
            client.request('GET', f'/sessions/{sid}/reports/check-1')
        assert missing.value.status == 404
        report.parent.mkdir(parents=True)
        report.write_bytes(b'\xff')
        with pytest.raises(ClientError) as damaged_report:
            client.request('GET', f'/sessions/{sid}/reports/check-1')
        assert damaged_report.value.status == 500 and damaged_report.value.code == 'infrastructure_error'
        journal = tmp_path / sid / 'run/events.jsonl'
        backup = journal.with_name('saved-events.jsonl')
        journal.replace(backup)
        journal.symlink_to(backup.name)
        with pytest.raises(ClientError) as linked_journal:
            client.session(sid)
        assert linked_journal.value.status == 500 and linked_journal.value.code == 'infrastructure_error'
        journal.unlink()
        backup.replace(journal)
        with journal.open('a') as stream:
            stream.write(json.dumps({'sequence': 3, 'kind': 'test', 'data': {}}) + '\n')
        with pytest.raises(ClientError) as damaged:
            client.session(sid)
        assert damaged.value.status == 500 and damaged.value.code == 'infrastructure_error'
    finally:
        server.shutdown()
        server.server_close()
        service.shutdown()
        thread.join(timeout=1)


@pytest.mark.parametrize('response_status', [200, 503, 500])
def test_http_audit_retains_diagnostics_without_request_or_response_secrets(tmp_path, response_status):
    import threading
    import urllib.error
    import urllib.request

    from benchmarking.service.server import serve

    secret = 'private-audit-regression-secret'

    def handle(*args):
        if response_status == 500:
            raise RuntimeError(secret)
        return response_status, {'error': {'code': 'unavailable', 'message': secret}, 'candidate': secret}

    journal = tmp_path / 'http.jsonl'
    server = serve(SimpleNamespace(handle=handle), audit=journal)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = urllib.request.Request(
            f'http://127.0.0.1:{server.server_port}/sessions/{secret}/files?path={secret}',
            data=json.dumps({'candidate': secret}).encode(),
            headers={'Authorization': 'Bearer ' + secret, 'Idempotency-Key': secret}, method='POST')
        try:
            response = urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=3)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            assert response.status == response_status
            assert (secret in response.read().decode()) == (response_status != 500)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)
    raw = journal.read_text()
    assert secret not in raw
    event, = [json.loads(line) for line in raw.splitlines()]
    assert event['operation'] == 'files' and event['method'] == 'POST'
    assert event['status'] == response_status
    assert event['error_code'] == ('infrastructure_error' if response_status == 500 else 'unavailable')
    if response_status == 500:
        assert event['exception_type'] == 'RuntimeError'
        assert event['exception_frames'][-1]['function'] == 'handle'
    assert event['elapsed_seconds'] >= 0 and event['timestamp']
    assert journal.stat().st_mode & 0o777 == 0o600
