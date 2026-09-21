"""HTTP client response, integrity and retry boundaries.

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
    ({'protocol':'layout-http','content_base64':base64.b64encode(b'changed').decode(),
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
        return Response(b'{"protocol":"layout-http","submission_id":"accepted"}')
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
            b'{"protocol":"layout-http","error":{"code":"conflict","message":"Different content","retryable":false}}'))
    monkeypatch.setattr(client._opener,'open',transport)
    with pytest.raises(ClientError) as failure:
        client.submit('session','output.gds',key='used')
    assert failure.value.status == 409
    assert not failure.value.retryable


def test_opt_in_retry_replays_lost_execution_response_once(monkeypatch):
    """Transport loss after commit must not execute a side effect twice."""
    from helpers.service import Simulator

    from benchmarking.participants.recovery import DISABLED
    server = Simulator()
    try:
        client = Client(server.endpoint, 'secret', retry_policy=DISABLED | {'http_attempts': 3})
        original = client._opener.open
        calls = []
        def lost_reply(request, **kwargs):
            response = original(request, **kwargs)
            calls.append(request)
            if len(calls) == 1:
                response.close()
                raise TimeoutError('response lost after server committed execution')
            return response
        monkeypatch.setattr(client._opener, 'open', lost_reply)
        assert client.execute('s', 'generate', 10, key='same')['execution_id'] == 'e'
        assert server.executions == 1
        assert len(calls) == 2
    finally:
        server.stop()


@pytest.mark.parametrize('code,status,retryable,expected', [
    ('transport_error', None, True, 3),
    ('budget_exhausted', 429, False, 1),
])
def test_retry_is_bounded_and_does_not_treat_budget_as_rate_limit(monkeypatch, code, status, retryable, expected):
    from benchmarking.participants.recovery import DISABLED
    client = Client('http://localhost:1', 'secret', retry_policy=DISABLED | {
        'http_attempts': 3, 'backoff_seconds': 1, 'max_backoff_seconds': 2})
    calls, sleeps = [], []
    def fail(*args, **kwargs):
        calls.append(kwargs['key'])
        raise ClientError(code, 'injected', status=status, retryable=retryable)
    monkeypatch.setattr(client, '_request', fail)
    monkeypatch.setattr('benchmarking.client.time.sleep', sleeps.append)
    with pytest.raises(ClientError):
        client.close('s', key='same')
    assert calls == ['same'] * expected
    assert sleeps == ([1, 2] if expected == 3 else [])


def test_creation_wait_covers_service_provisioning_without_extending_other_requests(monkeypatch):
    from benchmarking.protocol import SESSION_STARTUP_TIMEOUT_SECONDS
    client = Client('http://localhost:1', 'access', timeout=2)
    observed = []
    def transport(request, **kwargs):
        observed.append((request.full_url, kwargs['timeout']))
        return Response(b'{"protocol":"layout-http"}')
    monkeypatch.setattr(client._opener, 'open', transport)
    client.create('fixture', {}, key='creation')
    client.session('fixture')
    assert observed[0][1] > SESSION_STARTUP_TIMEOUT_SECONDS
    assert observed[1][1] == client.timeout
