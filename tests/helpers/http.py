"""HTTP clients and checkpoint round trips shared by protocol and capacity checks."""

import hashlib
import json
import time

import pytest

from benchmarking.client import Client

CONDITION = {'harness_kind': 'agent', 'harness_id': 'protocol-test', 'harness_version': '1',
             'model': 'none', 'prompt_sha256': None, 'configuration_sha256': None}


def create(host):
    service, endpoint = host
    response = Client(endpoint,'operator-test',timeout=50).create(service.controller.task.id,CONDITION,key='create')
    return Client(endpoint,response['session_token']),response['session_id']


def complete(client,sid,eid, *, seconds=30):
    deadline = time.monotonic()+seconds
    while time.monotonic()<deadline:
        result = client.poll(sid,eid)
        if result['state'] != 'running':
            return result
        time.sleep(.05)
    pytest.fail('Execution did not finish')


def checkpoint_roundtrip(host, blocks):
    import base64

    service, _ = host
    client, sid = create(host)
    limits = service.controller.limits
    mib = 1024*1024
    command = (
        "python -I - <<'PY'\nimport hashlib,random\n"
        f"block=random.Random(0).randbytes({mib})\n"
        "digest=hashlib.sha256()\n"
        "with open('large.log','wb') as stream:\n"
        f" for _ in range({blocks}):\n  stream.write(block);digest.update(block)\n"
        "print(digest.hexdigest())\nPY"
    )
    try:
        started = client.execute(sid, command, 60, key='large-workspace')
        result = complete(client, sid, started['execution_id'], seconds=limits['checkpoint']['total_seconds']+90)
        assert result['exit_code'] == 0
        expected = base64.b64decode(result['log_base64']).decode().strip()
        manifest = json.loads((service.controller.root/sid/'.private/checkpoint.json').read_text())
        assert manifest['metrics']['workspace_bytes'] == blocks*mib
        import tarfile
        with (tarfile.open(service.controller.root/sid/'.private'/manifest['archive']) as archive,
              archive.extractfile('large.log') as stream):
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == expected
        unchanged = client.execute(sid, 'true', 10, key='unchanged-workspace')
        assert complete(client, sid, unchanged['execution_id'], seconds=limits['checkpoint']['total_seconds']+30)['exit_code'] == 0
        latest = json.loads((service.controller.root/sid/'.private/checkpoint.json').read_text())
        assert latest['archive'] == manifest['archive']
    finally:
        client.close(sid, key='close-large-workspace')


