"""Remote seam regressions; synthetic bytes never establish model performance.

Public session tests cover in-container clients, not the HTTP boundary. These
checks independently compare archived bytes/digests, access denial and process
exit. They protect replay and path isolation, not layout qualification.
"""
import hashlib
import json
import os
import threading
import time

import pytest

from benchmarking.client import Client, ClientError
from benchmarking.dataset import load_dataset
from benchmarking.engine.runtime import load_case
from benchmarking.service.server import LocalService, serve

DATASET = os.environ.get('ICLAYOUT_BENCH_DATASET')
CASE = os.environ.get('ICLAYOUT_BENCH_CASE', 'freepdk45.nangate45-pdk.NAND2_X1')
CONDITION = {'harness_kind': 'agent', 'harness_id': 'protocol-test', 'harness_version': '1',
                 'model': 'none', 'prompt_sha256': None, 'configuration_sha256': None}


@pytest.fixture
def host(tmp_path):
    dataset = load_dataset(DATASET)
    runtime = load_case(dataset.case(CASE), image=os.environ.get('ICLAYOUT_BENCH_TEST_IMAGE', 'iclayout-eda-open:local'))
    service = LocalService(tmp_path/'store', runtime.task, runtime.agent_resources(), runtime.backends,
                           os.environ.get('ICLAYOUT_BENCH_TEST_IMAGE','iclayout-eda-open:local'), 'operator-test')
    server = serve(service)
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    endpoint = f'http://127.0.0.1:{server.server_port}'
    yield service, endpoint
    server.shutdown()
    server.server_close()
    thread.join()
    service.shutdown()


def create(host):
    service, endpoint = host
    response = Client(endpoint,'operator-test',timeout=50).create(service.controller.task.id,CONDITION,key='create')
    return Client(endpoint,response['session_token']),response['session_id']


def complete(client,sid,eid):
    deadline = time.monotonic()+30
    while time.monotonic()<deadline:
        result = client.poll(sid,eid)
        if result['state'] != 'running':
            return result
        time.sleep(.05)
    pytest.fail('Execution did not finish')


def test_soft_budget_drains_work_reminds_and_accepts_final_submission(host):
    service, _ = host
    client, sid = create(host)
    execution = client.execute(sid, 'sleep .5; mkdir -p output; printf final > output/final.gds', None, key='work')
    # Advance only this session's clock to exercise the expiry boundary without
    # changing task hours, or waiting through a real multi-hour solve budget.
    with service.controller.lock:
        service.controller.state.runs[sid]['deadline_epoch'] = time.time() - 1
    status = client.session(sid)
    assert status['remaining_seconds'] == 0
    assert status['budget']['policy'] == 'soft'
    assert 'submit immediately' in status['budget']['message']
    for action in ('execute', 'write', 'check'):
        with pytest.raises(ClientError) as caught:
            if action == 'execute':
                client.execute(sid, 'echo optimization', None, key='late-work')
            elif action == 'write':
                client.write(sid, 'late.py', b'optimization', key='late-write')
            else:
                client.check(sid, key='late-check')
        assert caught.value.code == 'budget_exhausted'
    assert complete(client, sid, execution['execution_id'])['exit_code'] == 0
    receipt = client.submit(sid, 'output/final.gds', key='final')
    assert receipt['size_bytes'] == len(b'final')
    client.close(sid, key='close')


@pytest.mark.parametrize('lost_owner', [False, True])
def test_case_worker_submits_evaluates_and_archives_after_scheduler_exit(host, tmp_path, lost_owner):
    """Kill the actual batch process while an opaque command is solving."""
    import signal
    import subprocess
    import sys
    from pathlib import Path

    import tomli_w

    from benchmarking.locking import BatchLeaseError
    from benchmarking.participants.local_service import process_start
    from benchmarking.participants.storage import CaseLease

    service, endpoint = host
    # Local services use isolated installed-package imports. A development
    # worktree can select another existing formal environment for that process.
    test_python = os.environ.get('ICLAYOUT_BENCH_TEST_PYTHON', sys.executable)
    ready, release = tmp_path / 'ready', tmp_path / 'release'
    script = '''import os, time
from pathlib import Path
from benchmarking.client import Client
c = Client(os.environ['ICLAYOUT_BENCH_ENDPOINT'], os.environ['ICLAYOUT_BENCH_TOKEN'])
sid = os.environ['ICLAYOUT_BENCH_SESSION']
c.write(sid, 'output/final.gds', b'synthetic protocol candidate', key='write')
c.submit(sid, 'output/final.gds', key='participant-submit')
MUTATE
Path(READY).write_text(str(os.getpid()))
deadline = time.monotonic() + 60
while not Path(RELEASE).exists() and time.monotonic() < deadline:
    time.sleep(.05)
print('Opaque participant finished')
'''.replace('READY', repr(str(ready))).replace('RELEASE', repr(str(release)))
    script = script.replace('MUTATE', "c.write(sid, 'output/final.gds', b'unsubmitted mutable output', key='mutate')" if lost_owner else '')
    config = tmp_path / 'command.toml'
    config.write_text(tomli_w.dumps({'harness': 'command', 'model': 'protocol-fixture',
                                    'effort': 'off',
                                    'tasks': [service.controller.task.id], 'concurrency': 1, 'repetitions': 1,
                                    'scheme': {'version': 'fixture', 'launch': {
                                        'command': [test_python, '-c', script], 'files': []}}}))
    batch = tmp_path / 'batch'
    if lost_owner:
        from benchmarking.dataset import dataset_root
        config_path = load_dataset(DATASET).case(service.controller.task.id)
        case = batch / Path(config_path).parent.relative_to(dataset_root(config_path) / 'tasks')
    else:
        case = batch / service.controller.task.id
    worker_pid = None
    native_pid, local_owner = None, None
    with (tmp_path / 'scheduler.log').open('w') as log:
        mode = ['--dataset', DATASET] if lost_owner else ['--endpoint', endpoint]
        process = subprocess.Popen([test_python, '-m', 'benchmarking.run', '--config', str(config),
                                    *mode, '--output', str(batch)],
                                   cwd=Path(__file__).resolve().parents[1],
                                   env=dict(os.environ, ICLAYOUT_BENCH_TOKEN='operator-test'),
                                   stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 60
            while not ready.exists() and time.monotonic() < deadline and process.poll() is None:
                time.sleep(.05)
            assert ready.exists(), (tmp_path / 'scheduler.log').read_text()
            worker_pid = json.loads((case / '.runtime/worker.json').read_text())['pid']
            native_pid = int(ready.read_text())
            if lost_owner:
                local_owner = json.loads((case / '.runtime/service/.private/owner.json').read_text())
            process.terminate()
            process.wait(timeout=10)
            with pytest.raises(BatchLeaseError), CaseLease(case):
                pytest.fail('Recovery must not take ownership from a live worker')
            if lost_owner:
                os.killpg(worker_pid, signal.SIGKILL)
            release.touch()
            if lost_owner:
                deadline = time.monotonic() + 10
                while process_start(native_pid) is not None and time.monotonic() < deadline:
                    time.sleep(.05)
                collected = subprocess.run([test_python, '-m', 'benchmarking.run', '--collect-only',
                                            '--output', str(batch)], cwd=Path(__file__).resolve().parents[1],
                                           capture_output=True, text=True, timeout=60, check=False)
                assert collected.returncode == 1, collected.stderr  # Unknown owner exit, independent score retained.
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                record = json.loads((case / 'result.json').read_text())
                if record['state'] == 'finished' and not (case / '.runtime').exists():
                    break
                time.sleep(.05)
            assert record['state'] == 'finished'
            assert record['summary']['harness_error'] == ('runner_interrupted' if lost_owner else None)
            if not lost_owner:
                assert record['execution']['exit_code'] == 0
            assert record['evaluation']['submission']['candidate_sha256'] == hashlib.sha256(b'synthetic protocol candidate').hexdigest()
            assert record['evaluation']['state'] in {'complete', 'error'}
            assert not (case / '.runtime').exists()
            if lost_owner:
                assert (case / 'final.gds').read_bytes() == b'synthetic protocol candidate'
                assert record['execution']['final_receipt']['submission_id'] == record['evaluation']['submission']['submission_id']
                assert process_start(local_owner['pid']) is None
            else:
                assert service.controller.state.runs[record['evaluation']['session_id']]['closing']
        finally:
            release.touch()
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
            if worker_pid and (case / '.runtime').exists():
                try:
                    os.killpg(worker_pid, signal.SIGINT)
                except ProcessLookupError:
                    pass
            if native_pid and process_start(native_pid) is not None:
                os.killpg(native_pid, signal.SIGINT)
            if local_owner and process_start(local_owner['pid']) == local_owner['start']:
                os.killpg(local_owner['pid'], signal.SIGINT)


def test_remote_snapshot_retry_and_independent_evaluation(host, tmp_path):
    service, endpoint = host
    client,sid = create(host)
    path = service.controller.task.output.path
    with pytest.raises(ClientError) as denied:
        Client(endpoint,'another-session').result(sid)
    assert denied.value.status == 404
    result = client.execute(sid, 'mkdir -p output; printf first > '+path, 10,key='command')
    assert complete(client,sid,result['execution_id'])['exit_code'] == 0
    first = client.submit(sid,path,key='candidate')
    client.write(sid,path,b'second',key='rewrite')
    assert client.submit(sid,path,key='candidate') == first
    assert first['candidate_sha256'] == hashlib.sha256(b'first').hexdigest()
    from benchmarking.participants.bridge import Bridge
    bridge = Bridge(client, sid, tmp_path / 'bridge.jsonl')
    before = client.session(sid)
    checked = bridge.call('check', {})
    assert checked['exit_code'] == 0
    feedback = json.loads(checked['output'])['feedback']
    assert feedback['candidate']['sha256'] == hashlib.sha256(b'second').hexdigest()
    assert feedback['outcome'] in ('failed', 'error')
    assert feedback['details']['jobs']['artifact']['status'] in ('failed', 'error')
    assert feedback['tool_identity'] == service.controller.evaluator_identity
    after = client.session(sid)
    assert after['last_submission'] == before['last_submission']
    assert after['diagnostics']['requests'] == before['diagnostics']['requests'] + 1
    assert after['diagnostics']['completed'] == after['diagnostics']['requests']
    assert after['diagnostics']['elapsed_seconds'] == pytest.approx(feedback['elapsed_seconds'])
    chunks, offset = [], 0
    while True:
        page = bridge.call('report', {'report_id': feedback['report_id'], 'offset': offset})
        chunks.append(page['content'])
        offset = page['next_offset']
        if not page['has_more']:
            break
    diagnostic = json.loads(''.join(chunks))
    assert diagnostic['candidate_sha256'] == feedback['candidate']['sha256']
    assert diagnostic['details']['metrics']
    for details in (feedback['details'], diagnostic['details']):
        assert set(details) == {'jobs', 'metrics', 'omitted_jobs', 'omitted_metrics'}
    assert client.result(sid)['score'] is None
    assert 'report_path' not in feedback
    with pytest.raises(ClientError) as denied:
        Client(endpoint, 'another-session').report(sid, feedback['report_id'])
    assert denied.value.status == 404
    assert client.report(sid, feedback['report_id'], offset=offset)['content'] == ''
    assert client.report(sid, feedback['report_id'], offset=1)['content'] == ''.join(chunks)[1:16001]
    with pytest.raises(ClientError):
        client.report(sid, 'check-invalid')
    with pytest.raises(ValueError):
        bridge.call('report', {'report_id': feedback['report_id'], 'offset': True})
    with pytest.raises(ClientError) as conflict:
        client.submit(sid,'different.gds',key='candidate')
    assert conflict.value.status == 409
    observations = client.observations(sid)
    assert client.session(sid)['state'] == 'active'
    assert sum(e['kind'] == 'submissions' for e in observations['events']) == 1
    assert any(e['kind'] == 'execution.completed' for e in observations['events'])
    assert client.observations(sid, offset=1)['events'] == observations['events'][1:]
    with pytest.raises(ClientError):
        Client(endpoint, 'another-session').observations(sid)
    serialized = json.dumps(observations)
    assert client.token not in serialized and str(service.controller.root) not in serialized
    assert 'evaluation_inputs' not in serialized
    client.close(sid,key='finish')
    deadline = time.monotonic()+30
    while time.monotonic()<deadline:
        result = client.result(sid)
        if result['state'] in ('complete','error'):
            break
        time.sleep(.1)
    assert result['state'] in ('complete','error')
    assert result['outcome'] in ('fail','error')
    if result['outcome'] == 'fail':
        assert result['score']['value'] == 0
        assert result['score']['reference'] == 100
    assert result['submission']['candidate_sha256'] == first['candidate_sha256']
    assert all(value is None for value in result['usage'].values())
    assert result['diagnostics'] == after['diagnostics']
    retained_page = client.report(sid, feedback['report_id'])
    assert retained_page['content'] == chunks[0]
    assert client.submit(sid,path,key='candidate') == first
    report = json.loads((service.controller.root/sid/'run/run.json').read_bytes())
    assert report['candidate']['sha256'] == first['candidate_sha256']
    assert (service.controller.root/sid/'run'/report['candidate']['path']).read_bytes() == b'first'
    from benchmarking.observe import export_observation
    manifest = export_observation(client, sid, tmp_path / 'observation')
    assert manifest['service']['evaluation_mode'] == 'self_run'
    assert all(value is None for value in manifest['usage'].values())
    observed = client.observations(sid)
    # Reopen the same store: receipt replay must survive process-local state loss.
    service.shutdown()
    recovered = LocalService(service.controller.root, service.controller.task, service.controller.resources, service.controller.backends,
                             service.controller.image, service.controller.token)
    try:
        status, replay = recovered.handle('POST', f'/sessions/{sid}/submissions', {},
                                          client.token, {'path': path}, 'candidate')
        assert status == 200
        assert replay == first
        _, replayed_events = recovered.handle('GET', f'/sessions/{sid}/observations', {}, client.token, None, None)
        assert replayed_events == observed
        _, replayed_report = recovered.handle('GET', f"/sessions/{sid}/reports/{feedback['report_id']}",
                                              {}, client.token, None, None)
        assert replayed_report == retained_page
    finally:
        recovered.shutdown()


def test_shared_finalizer_waits_for_workspace_execution_before_submission(host, tmp_path):
    from benchmarking.participants.runner import finalize_session
    service, _ = host
    client, sid = create(host)
    path = service.controller.task.output.path
    started = client.execute(sid, f'sleep 1; mkdir -p output; printf candidate > {path}', 10, key='in-flight')
    assert client.session(sid)['active_execution_id'] == started['execution_id']
    output = tmp_path / 'participant'
    (output / '.private').mkdir(parents=True)
    (output / '.private/recovery.json').write_text(json.dumps({'redactions': [client.token]}))
    (output / 'harness-summary.json').write_text(json.dumps({'error': 'fixture_exit'}))
    created = {'task': {'description': {'output': {'path': '/workspace/' + path}}}}
    result = finalize_session(client, sid, created, output)
    assert result['state'] in {'complete', 'error'}
    assert result['submission']['candidate_sha256'] == hashlib.sha256(b'candidate').hexdigest()
    evidence = json.loads((output / 'finalization.json').read_text())
    assert evidence['executions'][started['execution_id']]['exit_code'] == 0
    assert evidence['closed'] and evidence['error'] is None
    assert (output / 'analysis/manifest.json').exists()
    assert json.loads((output / 'harness-summary.json').read_text())['error'] == 'fixture_exit'


def test_witness_qualification_uses_one_portable_evaluation(tmp_path):
    """The current contract and reference pass one complete evaluator run."""
    from dataclasses import replace
    from types import SimpleNamespace

    from benchmarking.engine.qualification import (
        run,
        verify,
    )

    image = os.environ.get('ICLAYOUT_BENCH_TEST_IMAGE', 'iclayout-eda-open:local')
    runtime = load_case(load_dataset(DATASET).case(CASE), image=image)
    output = tmp_path / 'qualification'
    run(runtime, output)
    verify(runtime, output)
    portable = tmp_path / 'portable'
    portable.mkdir()
    (portable / 'qualification.json').write_bytes((output / 'qualification.json').read_bytes())
    verify(runtime, portable)  # Raw waveforms are disposable.
    changed = dict(runtime.backends)
    operation = next(iter(changed))
    changed[operation] = SimpleNamespace(identity={**changed[operation].identity, 'changed': True})
    # Portable verification binds reference/evaluation input bytes, not tool identities.
    verify(replace(runtime, backends=changed), output)
    # Presentation and selection can change without rerunning the circuit.
    revised = replace(runtime.task, title='Revised title', status='qualified', digest='0' * 64)
    verify(replace(runtime, task=revised), portable)
    # A changed evaluation input or an unsuccessful job cannot be qualified.
    original = next(item for item in runtime.task.inputs
                    if 'input:' + item.role in runtime.task.evaluation.external_inputs())
    content = original.content + b'\n'
    changed_input = replace(original, content=content, sha256=hashlib.sha256(content).hexdigest())
    changed_task = replace(runtime.task, inputs=tuple(changed_input if item is original else item
                                                    for item in runtime.task.inputs))
    with pytest.raises(ValueError, match='Qualification input changed'):
        verify(replace(runtime, task=changed_task), portable)
    record = json.loads((portable / 'qualification.json').read_bytes())
    next(iter(record['report']['jobs'].values()))['status'] = 'failed'
    (portable / 'qualification.json').write_text(json.dumps(record))
    with pytest.raises(ValueError, match='did not pass'):
        verify(runtime, portable)


def test_workspace_links_background_cleanup_and_cancellation(host):
    client,sid = create(host)
    client.write(sid,'nested/code.txt',b'hello',key='write')
    assert client.read(sid,'nested/code.txt') == b'hello'
    executed = client.execute(sid,'ln -s /task /workspace/escape; sleep 30 &',10,key='links')
    assert complete(client,sid,executed['execution_id'])['exit_code'] == 0
    with pytest.raises(ClientError):
        client.write(sid,'escape/new.txt',b'bad',key='escape')
    with pytest.raises(ClientError):
        client.read(sid,'../task/new.txt')
    executed = client.execute(sid,'sleep 30',20,key='long')
    with pytest.raises(ClientError) as busy:
        client.write(sid,'busy.txt',b'bad',key='busy')
    assert busy.value.status == 409
    client.session(sid,f'executions/{executed["execution_id"]}/cancel',{},key='cancel')
    assert complete(client,sid,executed['execution_id'])['state'] == 'cancelled'
    executed = client.execute(sid,'sleep 30',20,key='close-running')
    client.close(sid,key='close')
    assert complete(client,sid,executed['execution_id'])['state'] == 'cancelled'
    deadline = time.monotonic()+30
    while time.monotonic()<deadline:
        result = client.result(sid)
        if result['state'] in ('complete','error'):
            break
        time.sleep(.1)
    assert result['state'] == 'complete'
    assert result['outcome'] == 'no_submission'
    assert result['submission'] is None


def test_participant_tool_image_changes_solver_without_changing_judge(host, tmp_path):
    """Public A/B seam: an installed Python module is available only to scheme A.

    Existing HTTP tests do not vary the solver image. A tiny import-only module
    is the independent availability oracle; invalid GDS exercises trusted EDA
    without claiming a layout score or model capability. No network build needed.
    """
    import subprocess
    import sys

    from benchmarking.engine.sessions.docker import DockerSession
    from benchmarking.participants.config import resolve
    from benchmarking.participants.runner import run_participant
    from benchmarking.participants.scheme import resolve_scheme

    baseline, endpoint = host
    base_image = DockerSession(baseline.controller.image).image_id
    context = tmp_path / 'image'
    context.mkdir()
    (context / 'tool_a.py').write_text('AVAILABLE = True\n')
    (context / 'Dockerfile').write_text('FROM ' + baseline.controller.image + '\nCOPY tool_a.py /opt/tool_a/tool_a.py\nENV PYTHONPATH=/opt/tool_a\n')
    augmented = subprocess.check_output(['docker', 'build', '--network=none', '-q', str(context)], text=True).strip()
    assert DockerSession(baseline.controller.image).image_id == base_image
    script = tmp_path / 'participant.py'
    script.write_text('''import os, sys, time
from benchmarking.client import Client
client = Client(os.environ['ICLAYOUT_BENCH_ENDPOINT'], os.environ['ICLAYOUT_BENCH_TOKEN'])
sid = os.environ['ICLAYOUT_BENCH_SESSION']
operation = client.execute(sid, "python -c 'import tool_a; assert tool_a.AVAILABLE'", 10, key='import-a')
while True:
    execution = client.poll(sid, operation['execution_id'])
    if execution['state'] != 'running':
        break
    time.sleep(.05)
assert (execution['exit_code'] == 0) == (sys.argv[1] == 'available')
client.write(sid, 'output/final.gds', b'invalid-regression-gds', key='candidate')
client.submit(sid, 'output/final.gds', key='submission')
print('tool availability verified')
''')
    modified = LocalService(tmp_path / 'augmented-service', baseline.controller.task, baseline.controller.resources,
                            baseline.controller.backends, augmented, 'operator-test')
    server = serve(modified)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    results = []
    try:
        for index, (image, address, expected) in enumerate([
            (base_image, endpoint, 'absent'),
            (augmented, f'http://127.0.0.1:{server.server_port}', 'available'),
        ]):
            scheme = resolve_scheme({'version': 'regression', 'solver_image': image,
                'launch': {'command': [sys.executable, str(script), expected], 'files': [script.name]}}, tmp_path, 'command')
            selection = resolve('command', 'none', 'off')
            result, error = run_participant(
                Client(address, 'operator-test', timeout=60),
                {'harness': 'command', 'task': baseline.controller.task.id, 'scheme': scheme},
                tmp_path / f'participant-{index}', selection)
            assert error is None
            assert result['submission'] is not None
            assert result['outcome'] in {'fail', 'error'}
            assert result['evaluation_mode'] == 'self_run'
            assert all(value is None for value in result['usage'].values())
            results.append(result)
        assert results[0]['tool_identity']['image_id'] != results[1]['tool_identity']['image_id']
        assert results[0]['tool_identity']['evaluator'] == results[1]['tool_identity']['evaluator']
        assert results[0]['condition']['configuration_sha256'] != results[1]['condition']['configuration_sha256']
        assert results[0]['limits'] == results[1]['limits']
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        modified.shutdown()


def test_local_service_records_ownership_before_announcing_readiness(tmp_path):
    """The child records its endpoint even when no launcher persists its reply."""
    import subprocess
    import sys
    from pathlib import Path

    from benchmarking.participants.local_service import (
        local_service_client,
        local_service_owner,
        stop,
    )

    output = tmp_path / 'service'
    owner = output / '.private/owner.json'
    env = dict(os.environ, ICLAYOUT_BENCH_LOCAL_TOKEN='startup-test')
    process = subprocess.Popen([
        sys.executable, '-I', '-m', 'benchmarking.service', '--dataset', DATASET,
        '--case', CASE, '--data', str(output / 'service-store'), '--port', '0',
        '--image', os.environ.get('ICLAYOUT_BENCH_TEST_IMAGE', 'iclayout-eda-open:local'),
        '--token-env', 'ICLAYOUT_BENCH_LOCAL_TOKEN', '--owner-record', str(owner),
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, start_new_session=True)
    try:
        line = process.stdout.readline()
        assert line.startswith('Local development service: '), process.stderr.read() if process.poll() is not None else line
        recorded = local_service_owner(output)
        assert recorded['pid'] == process.pid
        assert recorded['endpoint'] == line.strip().removeprefix('Local development service: ')
        # An unrelated collector can locate this child without a parent-written record.
        from benchmarking.files import write_json
        write_json(owner.with_name('access.json'), {'token': 'startup-test'})
        client = local_service_client(output)
        assert client.endpoint == recorded['endpoint']
        assert Path(owner).is_file()
    finally:
        stop(process)
        process.stdout.close()
        process.stderr.close()


def test_detached_coordinator_refills_slots_after_the_launcher_exits(host, tmp_path):
    """Real installed coordinator/workers refill while another native solve is gated."""
    import signal
    import subprocess
    import sys
    from pathlib import Path

    import tomli_w

    from benchmarking.service.process import process_start

    service, _ = host
    test_python = os.environ.get('ICLAYOUT_BENCH_TEST_PYTHON', sys.executable)
    ready, release = tmp_path / 'ready', tmp_path / 'release'
    ready.mkdir()
    release.mkdir()
    script = '''import os, time
from pathlib import Path
sid = os.environ['ICLAYOUT_BENCH_SESSION']
Path(READY, sid).write_text(str(os.getpid()))
deadline = time.monotonic() + 60
while not Path(RELEASE, sid).exists() and time.monotonic() < deadline:
    time.sleep(.05)
'''.replace('READY', repr(str(ready))).replace('RELEASE', repr(str(release)))
    config = tmp_path / 'command.toml'
    config.write_text(tomli_w.dumps({'harness': 'command', 'model': 'protocol-fixture', 'effort': 'off',
        'tasks': [service.controller.task.id], 'concurrency': 2, 'repetitions': 3,
        'scheme': {'version': 'fixture', 'launch': {'command': [test_python, '-c', script], 'files': []}}}))
    output = tmp_path / 'batch'
    launcher = subprocess.run([test_python, '-I', '-m', 'benchmarking.run', '--config', str(config),
        '--dataset', DATASET, '--image', os.environ.get('ICLAYOUT_BENCH_TEST_IMAGE', 'iclayout-eda-open:local'),
        '--output', str(output), '--detach'],
        env=dict(os.environ, ICLAYOUT_BENCH_TOKEN='operator-test'), capture_output=True, text=True,
        timeout=30, check=False, umask=0o077)
    assert launcher.returncode == 0, launcher.stderr
    receipt = json.loads(launcher.stdout)
    try:
        assert process_start(receipt['pid']) == receipt['start']
        deadline = time.monotonic() + 30
        while len(list(ready.iterdir())) < 2 and time.monotonic() < deadline:
            time.sleep(.05)
        first = sorted(ready.iterdir())
        assert len(first) == 2, Path(receipt['log']).read_text()
        (release / first[0].name).touch()
        while len(list(ready.iterdir())) < 3 and time.monotonic() < deadline:
            time.sleep(.05)
        assert len(list(ready.iterdir())) == 3, Path(receipt['log']).read_text()
        assert not (release / first[1].name).exists()
        status = subprocess.run([test_python, '-I', '-m', 'benchmarking.run', '--status', '--output', str(output)],
                                capture_output=True, text=True, timeout=10, check=False)
        assert status.returncode == 0, status.stderr
        assert json.loads(status.stdout)['scheduler_alive']
        for native in ready.iterdir():
            (release / native.name).touch()
        deadline = time.monotonic() + 30
        while process_start(receipt['pid']) is not None and time.monotonic() < deadline:
            time.sleep(.05)
        assert process_start(receipt['pid']) is None, Path(receipt['log']).read_text()
        records = list(output.rglob('result.json'))
        assert len(records) == 3
        assert all(json.loads(path.read_text())['state'] == 'finished' for path in records)
        for path in records:
            record = json.loads(path.read_text())
            assert {'worker-events.jsonl', 'service-http.jsonl', 'service-lifecycle.jsonl', 'service-launch.jsonl'} <= set(record['files'])
            lifecycle = [json.loads(line)['event'] for line in (path.parent / 'service-lifecycle.jsonl').read_text().splitlines()]
            assert lifecycle == ['service_started', 'service_stopped']
            assert 'operator-test' not in (path.parent / 'service-http.jsonl').read_text()
        events = (output / '.scheduler/events.jsonl').read_text()
        assert 'operator-test' not in events
        assert json.loads((output / '.scheduler/owner.json').read_text())['exit_code'] == 0
    finally:
        for native in ready.iterdir():
            (release / native.name).touch()
        if process_start(receipt['pid']) == receipt['start']:
            os.kill(receipt['pid'], signal.SIGTERM)
