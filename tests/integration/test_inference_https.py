"""Real local TLS transport: fixed destination, host auth and no redirect/secret reflection."""

import http.server
import json
import select
import socket
import ssl
import subprocess
import threading
import time
from dataclasses import replace

import pytest

from benchmarking.engine.inference import InferenceConfig, InferenceGateway
from benchmarking.engine.recorder import RunRecorder
from benchmarking.files import Asset

pytestmark = [pytest.mark.integration, pytest.mark.acceptance, pytest.mark.acceptance_fast]


# Extend the real transport contract to explicit CONNECT routes. The proxy is
# external I/O and forwards only the independently configured local endpoint.
@pytest.mark.parametrize('use_proxy', [False, True])
@pytest.mark.parametrize('scheme', ['http', 'https'])
def test_http_and_https_auth_redirects_and_secret_reflection(tmp_path, monkeypatch, scheme, use_proxy):
    cert, key = tmp_path/"cert.pem", tmp_path/"key.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                    "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost",
                    "-keyout", str(key), "-out", str(cert)], check=True, capture_output=True)
    secret = "synthetic-test-credential"
    received = []
    waiting, release = threading.Event(), threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            received.append((self.path, self.headers.get("Authorization"),
                             json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            if len(received) == 1:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status":"completed","usage":{"input_tokens":1,"output_tokens":2}}')
            elif len(received) == 2:
                self.send_response(307)
                self.send_header("Location", "https://must-not-follow.invalid/secrets")
                self.end_headers()
                self.wfile.write(secret.encode())
            elif len(received) == 3:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"secret": secret}).encode())
            else:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                waiting.set()
                release.wait(5)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    if scheme == 'https':
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("LB_TEST_INFERENCE_KEY", secret)
    monkeypatch.setenv("SSL_CERT_FILE", str(cert))
    profile = InferenceConfig(f"{scheme}://localhost:{server.server_port}/v1", "test-model", "LB_TEST_INFERENCE_KEY",
                              4, 5, Asset(b"test-profile", "text"), "responses")
    tunnel_targets = []

    class Proxy(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_CONNECT(self):
            tunnel_targets.append((self.path, self.headers.get('Authorization')))
            if self.path != f'localhost:{server.server_port}':
                self.send_error(403)
                return
            with socket.create_connection(('127.0.0.1', server.server_port), timeout=3) as upstream:
                self.send_response(200)
                self.end_headers()
                sockets = [self.connection, upstream]
                while True:
                    ready, _, _ = select.select(sockets, [], [], 3)
                    if not ready:
                        return
                    for source in ready:
                        data = source.recv(65536)
                        if not data:
                            return
                        sockets[1 - sockets.index(source)].sendall(data)

    proxy = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Proxy) if use_proxy else None
    if proxy:
        proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
        proxy_thread.start()
        profile = replace(profile, proxy_url=f'http://127.0.0.1:{proxy.server_port}')
    gateway = InferenceGateway(profile)
    assert gateway.public['transport'] == scheme
    gateway.recorder = RunRecorder(tmp_path / "run")
    gateway.deadline = time.monotonic()+20
    try:
        first = gateway.request("/responses", b'{"model":"test-model"}')
        redirect = gateway.request("/responses", b'{"model":"test-model"}')
        reflected = gateway.request("/responses", b'{"model":"test-model"}')
        assert [first[0], redirect[0], reflected[0]] == [200, 307, 502]
        assert len(received) == 3
        if use_proxy:
            assert len(tunnel_targets) == len(received)
            assert all(target == f'localhost:{server.server_port}' and auth is None
                       for target, auth in tunnel_targets)
            assert gateway.public['proxy_url'] == profile.proxy_url
        assert all(path == "/v1/responses" and auth == f"Bearer {secret}" and body["store"] is False
                   for path, auth, body in received)
        assert secret not in json.dumps(gateway.summary())
        assert all(secret.encode() not in response[2] for response in (first, redirect, reflected))
        pending = threading.Thread(target=gateway.request, args=("/responses", b'{"model":"test-model"}'))
        pending.start()
        assert waiting.wait(2)
        gateway.stop()
        pending.join(timeout=2)
        assert not pending.is_alive(), "Stopping a session must cancel the active response read"
        assert gateway.summary()["requests"][-1]["cancelled"]
        assert all(secret.encode() not in p.read_bytes() for p in gateway.recorder.root.rglob("*") if p.is_file())
    finally:
        release.set()
        gateway.stop()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        if proxy:
            proxy.shutdown()
            proxy.server_close()
            proxy_thread.join(timeout=2)
