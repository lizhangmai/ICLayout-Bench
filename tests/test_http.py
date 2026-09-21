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
    runtime = load_case(dataset.case(CASE), image=os.environ.get('ICLAYOUT_BENCH_TEST_IMAGE', 'iclayout-bench-tools:local'))
    service = LocalService(tmp_path/'store', runtime.task, runtime.agent_resources(), runtime.backends,
                           os.environ.get('ICLAYOUT_BENCH_TEST_IMAGE','iclayout-bench-tools:local'), 'operator-test')
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
    response = Client(endpoint,'operator-test',timeout=50).create(service.task.id,CONDITION,key='create')
    return Client(endpoint,response['session_token']),response['session_id']


def complete(client,sid,eid):
    deadline = time.monotonic()+30
    while time.monotonic()<deadline:
        result = client.poll(sid,eid)
        if result['state'] != 'running':
            return result
        time.sleep(.05)
    pytest.fail('Execution did not finish')


def test_remote_snapshot_retry_and_independent_evaluation(host, tmp_path):
    service, endpoint = host
    client,sid = create(host)
    path = service.task.output.path
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
    assert feedback['tool_identity'] == service.evaluator_identity
    after = client.session(sid)
    assert after['last_submission'] == before['last_submission']
    assert after['diagnostics_remaining'] == before['diagnostics_remaining'] - 1
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
    assert client.token not in serialized and str(service.root) not in serialized
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
    assert result['submission']['candidate_sha256'] == first['candidate_sha256']
    assert all(value is None for value in result['usage'].values())
    assert client.submit(sid,path,key='candidate') == first
    report = json.loads((service.root/sid/'run/run.json').read_bytes())
    assert report['candidate']['sha256'] == first['candidate_sha256']
    assert (service.root/sid/'run'/report['candidate']['path']).read_bytes() == b'first'
    from benchmarking.observe import export_observation
    manifest = export_observation(client, sid, tmp_path / 'observation')
    assert manifest['service']['verification_level'] == 'local_development'
    assert all(value is None for value in manifest['usage'].values())
    observed = client.observations(sid)
    # Reopen the same store: receipt replay must survive process-local state loss.
    service.shutdown()
    recovered = LocalService(service.root, service.task, service.resources, service.backends,
                             service.image, service.token)
    try:
        status, replay = recovered.handle('POST', f'/sessions/{sid}/submissions', {},
                                          client.token, {'path': path}, 'candidate')
        assert status == 200
        assert replay == first
        _, replayed_events = recovered.handle('GET', f'/sessions/{sid}/observations', {}, client.token, None, None)
        assert replayed_events == observed
    finally:
        recovered.shutdown()


def test_witness_qualification_uses_participant_check_and_final_evaluation(tmp_path, monkeypatch):
    """A qualified witness must survive the same HTTP/MCP path as a participant.

    Existing snapshot tests use invalid bytes and cannot detect drift between a
    passing direct evaluation and full participant checks. The Dataset contract
    supplies both the witness and all expectations; no model is invoked.
    """
    from dataclasses import replace
    from types import SimpleNamespace

    from benchmarking.engine.qualification import (
        acceptance_summary,
        repeatability,
        run,
        verify,
    )

    image = os.environ.get('ICLAYOUT_BENCH_TEST_IMAGE', 'iclayout-bench-tools:local')
    runtime = load_case(load_dataset(DATASET).case(CASE), image=image)
    output = tmp_path / 'qualification'
    run(runtime, output, image)
    verify(runtime, output)
    portable = tmp_path / 'portable'
    portable.mkdir()
    for name in ('qualification.json', 'direct.json', 'check.json', 'final.json'):
        (portable / name).write_bytes((output / name).read_bytes())
    verify(runtime, portable)  # Neither the service store nor raw waveforms are needed.
    summary = acceptance_summary(runtime, portable, 'a' * 40)
    assert summary['task_sha256'] == runtime.task.digest
    assert summary['passed'] is True and summary['scope'] == 'direct/check/final'
    assert summary['evidence_sha256'] == hashlib.sha256((portable / 'qualification.json').read_bytes()).hexdigest()
    assert str(portable) not in json.dumps(summary)
    with pytest.raises(ValueError, match='Git commit'):
        acceptance_summary(runtime, portable, 'not-a-commit')
    # The publication gate consumes explicit author evidence, without a Dataset ledger.
    from benchmarking.engine import qualification

    evidence_map = tmp_path / 'evidence.json'
    summaries = tmp_path / 'summaries.json'
    evidence_map.write_text(json.dumps({runtime.task.id: 'portable'}))
    summaries.write_text(json.dumps({runtime.task.id: summary}))
    with monkeypatch.context() as patch:
        patch.setattr(qualification, 'load_dataset', lambda *a, **k: SimpleNamespace(
            native_cases=lambda *a: (None, {runtime.task.id: runtime.config})))
        patch.setattr(qualification, 'load_case', lambda *a, **k: runtime)
        arguments = ['verify-core', '--dataset', DATASET, '--evidence', str(evidence_map),
                     '--summaries', str(summaries)]
        qualification.main(arguments)
        summaries.write_text(json.dumps({runtime.task.id: {**summary, 'passed': False}}))
        with pytest.raises(SystemExit) as rejected:
            qualification.main(arguments)
        assert rejected.value.code == 1
    changed = dict(runtime.backends)
    operation = next(iter(changed))
    changed[operation] = SimpleNamespace(identity={**changed[operation].identity, 'changed': True})
    with pytest.raises(ValueError, match='bindings changed'):
        verify(replace(runtime, backends=changed), output)
    report = output / 'check.json'
    report.write_bytes(report.read_bytes() + b' ')
    with pytest.raises(ValueError, match='digest mismatch'):
        verify(runtime, output)
    # A synthetic numerical change must be disclosed, never silently described
    # as bit-identical. It does not change the task's acceptance requirements.
    report = portable / 'check.json'
    observed = json.loads(report.read_bytes())
    observed['score']['value'] += 0.000001
    report.write_text(json.dumps(observed))
    record_path = portable / 'qualification.json'
    record = json.loads(record_path.read_bytes())
    record['reports']['check']['sha256'] = hashlib.sha256(report.read_bytes()).hexdigest()
    record_path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match='repeatability disclosure'):
        verify(runtime, portable)
    record['repeatability'] = repeatability([json.loads((portable / f'{s}.json').read_bytes())
                                            for s in ('direct', 'check', 'final')], runtime.task.evaluation)
    record_path.write_text(json.dumps(record))
    assert verify(runtime, portable)['repeatability']['observations_identical'] is False
    assert verify(runtime, portable)['repeatability']['within_limits'] is True
    observed['score']['value'] += 2 * record['repeatability']['policy']['score_spread']
    report.write_text(json.dumps(observed))
    record['reports']['check']['sha256'] = hashlib.sha256(report.read_bytes()).hexdigest()
    record['repeatability'] = repeatability([json.loads((portable / f'{s}.json').read_bytes())
                                            for s in ('direct', 'check', 'final')], runtime.task.evaluation)
    record_path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match='repeatability exceeds'):
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

    from benchmarking.engine.session import DockerSession
    from benchmarking.participants.config import resolve
    from benchmarking.participants.runner import run_participant
    from benchmarking.participants.scheme import resolve_scheme

    baseline, endpoint = host
    base_image = DockerSession(baseline.image).image_id
    context = tmp_path / 'image'
    context.mkdir()
    (context / 'tool_a.py').write_text('AVAILABLE = True\n')
    (context / 'Dockerfile').write_text('FROM ' + baseline.image + '\nCOPY tool_a.py /opt/tool_a/tool_a.py\nENV PYTHONPATH=/opt/tool_a\n')
    augmented = subprocess.check_output(['docker', 'build', '--network=none', '-q', str(context)], text=True).strip()
    assert DockerSession(baseline.image).image_id == base_image
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
    modified = LocalService(tmp_path / 'augmented-service', baseline.task, baseline.resources,
                            baseline.backends, augmented, 'operator-test')
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
            selection, env, settings = resolve('command', 'none', 'off')
            result, error = run_participant(Client(address, 'operator-test', timeout=60),
                {'harness': 'command', 'task': baseline.task.id, 'scheme': scheme},
                tmp_path / f'participant-{index}', selection, env, settings)
            assert error is None
            assert result['submission'] is not None
            assert result['outcome'] in {'fail', 'error'}
            assert result['verification_level'] == 'local_development'
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
