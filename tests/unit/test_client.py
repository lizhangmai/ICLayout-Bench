"""HTTP client boundary checks absent from legacy socket-client coverage.

Public wire fixtures specify independent responses. Protect secret-bearing
redirects, response integrity and mutation keys; these are protocol tests only.
"""
import base64
import io
import json
from urllib.error import HTTPError

import pytest

from benchmarking.client import Client, ClientError

pytestmark = pytest.mark.unit


class Response(io.BytesIO):
    code = 200


@pytest.mark.parametrize('response,code', [
    ({'protocol':'other'}, 'incompatible_protocol'),
    ({'protocol':'layout-http.v1','content_base64':base64.b64encode(b'changed').decode(),
      'size_bytes':7,'sha256':'0'*64}, 'invalid_response'),
])
def test_read_rejects_incompatible_or_tampered_service_content(response,code,monkeypatch):
    client = Client('http://127.0.0.1:8000','secret')
    monkeypatch.setattr(client._opener,'open',lambda *a,**k:Response(json.dumps(response).encode()))
    with pytest.raises(ClientError) as failure:
        client.read('session','file.txt')
    assert failure.value.code == code


def test_explicit_retry_preserves_key_and_body_without_automatic_mutation_retry(monkeypatch):
    client = Client('http://127.0.0.1:8000','secret')
    requests = []
    def transport(request,**kwargs):
        requests.append(request)
        if len(requests)==1:
            raise TimeoutError('reply lost')
        return Response(b'{"protocol":"layout-http.v1","submission_id":"accepted"}')
    monkeypatch.setattr(client._opener,'open',transport)
    with pytest.raises(ClientError) as failure:
        client.submit('session','output.gds',key='stable')
    assert failure.value.code == 'transport_error'
    assert len(requests)==1
    assert client.submit('session','output.gds',key='stable')['submission_id']=='accepted'
    assert requests[0].data == requests[1].data
    assert requests[0].get_header('Idempotency-key') == requests[1].get_header('Idempotency-key') == 'stable'


def test_redirect_does_not_forward_credentials():
    from urllib.request import Request

    from benchmarking.client import _NoRedirect
    request = Request('http://127.0.0.1/session',headers={'Authorization':'Bearer secret'})
    assert _NoRedirect().redirect_request(request,None,302,'',{},'https://other.invalid') is None


def test_error_retains_service_status(monkeypatch):
    client = Client('http://127.0.0.1:8000','secret')
    def transport(*args,**kwargs):
        raise HTTPError('http://127.0.0.1',409,'Conflict',{},io.BytesIO(
            b'{"protocol":"layout-http.v1","error":{"code":"conflict","message":"Different content","retryable":false}}'))
    monkeypatch.setattr(client._opener,'open',transport)
    with pytest.raises(ClientError) as failure:
        client.submit('session','output.gds',key='used')
    assert failure.value.status == 409
    assert not failure.value.retryable
