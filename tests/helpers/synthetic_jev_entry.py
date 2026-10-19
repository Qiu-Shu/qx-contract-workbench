"""Standalone source/frozen protocol probe. Only fictional text and localhost I/O."""
import asyncio
import json
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from time import perf_counter
from uuid import uuid4


def main():
    started = perf_counter()
    from cn_contract import domain as d
    domain_ms = (perf_counter() - started) * 1000
    started = perf_counter()
    from cn_contract.assistant.providers.jev import JevProvider
    from cn_contract.assistant.routing import choose_workflow
    provider_ms = (perf_counter() - started) * 1000
    assert 'httpx2' not in sys.modules
    request = d.JudgeRequest(local_request_id=uuid4(),
        scope=d.ScopeSnapshot(workspace_id=uuid4(), conversation_id=uuid4(), binding_revision=1,
                              input_revision=0, materials_revision=0),
        purpose='primary_intent', text='合成咨询：先回复虚构客户，再整理全部合成附件。')
    secret_reads, posts, external_attempts = [], [], []
    def secret():
        secret_reads.append(True)
        return 'synthetic-jev-frozen-key-only'
    original_connect, original_connect_ex, original_lookup = socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo
    def allowed(address):
        if not isinstance(address, tuple) or address[0] != '127.0.0.1':
            external_attempts.append(True)
            raise AssertionError('EXTERNAL_NETWORK_FORBIDDEN')
    def connect(self, address):
        allowed(address)
        return original_connect(self, address)
    def connect_ex(self, address):
        allowed(address)
        return original_connect_ex(self, address)
    def lookup(host, *args, **kwargs):
        if host not in ('127.0.0.1', b'127.0.0.1'):
            external_attempts.append(True)
            raise AssertionError('EXTERNAL_DNS_FORBIDDEN')
        return original_lookup(host, *args, **kwargs)
    socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo = connect, connect_ex, lookup
    server = None
    try:
        async def skipped():
            disabled = await JevProvider(d.JevConfig(), secret).judge(request)
            denied = await JevProvider(d.JevConfig(enabled=True), secret).judge(request)
            assert (disabled.status, disabled.reason_code) == ('skipped', 'unconfigured')
            assert (denied.status, denied.reason_code) == ('skipped', 'no_egress')
            assert not secret_reads and 'httpx2' not in sys.modules
        asyncio.run(skipped())
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                assert self.path == '/v1/systemone'
                assert self.headers['Authorization'] == 'Bearer synthetic-jev-frozen-key-only'
                assert body['model'] == 'jev-1.13.0'
                assert set(body) == {'model', 'state', 'questions'}
                assert body['state']['latest_request'] == request.text
                assert str(request.scope.workspace_id) not in json.dumps(body)
                options = body['questions']['primary_intent']['criteria']
                posts.append({'question_ids': list(body['questions'])})
                response = {'model': 'jev-1.13.0', 'answers': {'primary_intent': {
                    'type': 'choice', 'choice': 'client_reply',
                    'probabilities': {k: int(k == 'client_reply') for k in options}, 'confidence': 1}},
                    'usage': {'input_tokens': 10, 'output_tokens': None}}
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('x-typesafe-request-id', 'synthetic-jev-frozen-receipt')
                self.end_headers()
                self.wfile.write(json.dumps(response).encode())
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        Thread(target=server.serve_forever, daemon=True).start()
        async def sent():
            provider = JevProvider.for_synthetic_loopback(d.JevConfig(enabled=True), secret,
                f'http://127.0.0.1:{server.server_port}/v1/systemone', preflight=lambda *_: None)
            before = request.model_dump_json()
            reply = await provider.judge(request)
            assert reply.status == 'ok', (reply.status, reply.reason_code)
            assert reply.evidence == 'received' and reply.usage.output_tokens is None
            assert reply.provider_request_id == 'synthetic-jev-frozen-receipt'
            assert choose_workflow(None, reply, {'client_reply'}).workflow == 'client_reply'
            assert choose_workflow('material_organize', reply, {'client_reply', 'material_organize'}).workflow == 'material_organize'
            assert request.model_dump_json() == before
            return reply.elapsed_ms
        elapsed = asyncio.run(sent())
        assert len(posts) == 1 and len(secret_reads) == 1 and not external_attempts
        print(json.dumps({'status': 'passed', 'frozen': bool(getattr(sys, 'frozen', False)),
            'groups': 4, 'disabled_and_unapproved_skip_before_http_import': True,
            'loopback_posts': len(posts), 'external_network_attempts': len(external_attempts),
            'domain_import_ms': round(domain_ms, 3), 'provider_import_ms': round(provider_ms, 3),
            'cold_judge_elapsed_ms': elapsed, 'whole_desktop_startup_measured': False,
            'real_model_calls': 0, 'installed_app_changed': False}))
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo = original_connect, original_connect_ex, original_lookup


if __name__ == '__main__':
    main()
