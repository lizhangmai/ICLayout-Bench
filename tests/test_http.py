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
from pathlib import Path

import pytest

from benchmarking.bundles import load_bundle
from benchmarking.client import Client, ClientError
from benchmarking.files import Asset
from benchmarking.tasks import load_task
from layout_eval.toolchains import load_toolchain
from layout_service.server import LocalService, serve

PREPARED = Path(os.environ.get('ICLAYOUT_BENCH_PREPARED', 'build/prepared-cell6t-http')).resolve()
CONDITION = {'harness_kind': 'custom', 'harness_id': 'protocol-test', 'harness_version': '1',
                 'model': 'none', 'prompt_sha256': None, 'configuration_sha256': None}


@pytest.fixture
def host(tmp_path):
    case = PREPARED/'case/case.toml'
    bundle = load_bundle(PREPARED/'agent-resources')
    service = LocalService(tmp_path/'store',load_task(case),dict(bundle.files)|{'manifest.json':Asset(bundle.manifest.content,'json')},
                           load_toolchain(case),os.environ.get('ICLAYOUT_BENCH_TEST_IMAGE','iclayout-bench-tools:dev'), 'operator-test',seconds=60)
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


def test_remote_snapshot_retry_and_independent_evaluation(host):
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
    with pytest.raises(ClientError) as conflict:
        client.submit(sid,'different.gds',key='candidate')
    assert conflict.value.status == 409
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
    # Reopen the same store: receipt replay must survive process-local state loss.
    service.shutdown()
    recovered = LocalService(service.root, service.task, service.resources, service.backends,
                             service.image, service.token)
    try:
        status, replay = recovered.handle('POST', f'/v1/sessions/{sid}/submissions', {},
                                          client.token, {'path': path}, 'candidate')
        assert status == 200
        assert replay == first
    finally:
        recovered.shutdown()


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
