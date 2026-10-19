"""Independent source/frozen native HTTP probe; synthetic loopback only."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import sqlite3
import sys
from threading import Event, Thread
import time
from uuid import UUID, uuid4

import httpx2
from sqlalchemy import select
import uvicorn

from cn_contract import domain as d
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.assistant.providers.policy import MainModelRuntime, encoded, sha
from cn_contract.persistence import UserRow
from cn_contract.web.local_server import initialize_workspace, build_local_app, _database


@contextmanager
def serve(app):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); sock.listen(32)
        server = uvicorn.Server(uvicorn.Config(app, log_level='critical', access_log=False))
        thread = Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
        thread.start()
        deadline = time.monotonic()+30
        try:
            while not server.started:
                assert thread.is_alive() and time.monotonic() < deadline, 'native startup failed'
                time.sleep(.02)
            yield 'http://127.0.0.1:'+str(sock.getsockname()[1])
        finally:
            server.should_exit = True
            thread.join(30)
            assert not thread.is_alive(), 'native shutdown failed'


def main():
    target = Path(sys.argv[1]).resolve()
    target.mkdir(parents=True, exist_ok=False)
    root = target/'合成 中文 工作区'
    report = {'scope':'native HTTP and separate frozen synthetic entry; not installed application',
              'frozen':bool(getattr(sys, 'frozen', False)), 'real_model_calls':0, 'checks':[]}
    received = []
    entered, release = Event(), Event()
    text_input = '独立合成咨询：请整理虚构客户提出的交货问题。'
    secret = 'SYNTHETIC_HTTP_PROBE_NOT_A_REAL_KEY'

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers['Content-Length']))
            payload = json.loads(raw)
            assert self.path == '/chat/completions'
            assert self.headers.get('Authorization') == 'Bearer '+secret
            source = json.loads(payload['messages'][1]['content'])
            assert source['content'] == text_input
            received.append(sha(raw.decode('utf-8')))
            entered.set()
            assert release.wait(25), 'probe response gate timed out'
            candidate = {'text':'独立合成候选：交货事项仍需律师核对。', 'citations':[
                {'message_id':source['message_id'], 'quote_sha256':source['quote_sha256']}]}
            body = json.dumps({'id':'synthetic-http-response','model':'deepseek-flash',
                'object':'chat.completion','created':1,
                'choices':[{'index':0,'finish_reason':'stop','message':{
                    'role':'assistant','content':json.dumps(candidate,ensure_ascii=False)}}],
                'usage':{'prompt_tokens':30,'completion_tokens':12,'total_tokens':42}},
                ensure_ascii=False).encode('utf-8')
            try:
                self.send_response(200); self.send_header('Content-Length',str(len(body)))
                self.end_headers(); self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

    upstream = ThreadingHTTPServer(('127.0.0.1',0),Handler)
    upstream.daemon_threads = True
    Thread(target=upstream.serve_forever,daemon=True).start()
    try:
        credentials = {'username':'合成接口律师','password':'fixture123'}
        initialize_workspace(root, **credentials, data_parent=target)
        database = _database(root)
        try:
            with database.session() as db:
                actor_id = UUID(db.scalar(select(UserRow.id)))
        finally:
            database.engine.dispose()
        workspace_id = json.loads((root/'workspace.json').read_text('utf-8'))['workspace_id']
        config = d.MainModelConfig(enabled=True, model='deepseek-flash', input_usd_per_million='0.3',
            output_usd_per_million='1.2',price_reference='synthetic-only',timeout_seconds=30)
        policy = d.MainModelPolicy(policy_id=uuid4(), workspace_id=workspace_id,actor_id=actor_id,
            config_sha256=sha(encoded(config)),allowed_content_sha256s=(sha(text_input),),
            max_total_usd='1',max_calls=5,expires_at=datetime.now(timezone.utc)+timedelta(hours=1))
        runtime = MainModelRuntime(DeepSeekProvider.for_synthetic_loopback(config,lambda:secret,
            f'http://127.0.0.1:{upstream.server_port}/chat/completions'),policy)

        def login(client):
            response = client.post('/api/login',json=credentials)
            assert response.status_code == 200, response.text
            return {'X-CSRF-Token':response.json()['csrf_token']}

        def submit(client, headers):
            response = client.post('/api/assistant/conversations',headers=headers,
                json={'request_id':str(uuid4())})
            assert response.status_code == 201, response.text
            view = response.json()
            url = '/api/assistant/conversations/'+view['scope']['conversation_id']
            response = client.put(url+'/draft',headers=headers,json={'expected_scope':view['scope'],
                'expected_composer_revision':view['composer_revision'],'content':text_input})
            assert response.status_code == 200, response.text
            view = response.json()
            assert client.get(url+'/generation-capability').json()['state'] == 'ready'
            payload = {'request_id':str(uuid4()),'expected_scope':view['scope'],
                'expected_composer_revision':view['composer_revision'],'content':text_input}
            started = time.monotonic()
            response = client.post(url+'/generations',headers=headers,json=payload)
            assert response.status_code == 202, response.text
            elapsed = time.monotonic()-started
            assert not release.is_set(), 'submit waited for provider reply'
            assert entered.wait(10), 'provider was not started'
            return url, payload, response.json(), elapsed

        def settled(client, attempt):
            deadline = time.monotonic()+10
            while time.monotonic() < deadline:
                response = client.get('/api/assistant/attempts/'+attempt['id'])
                assert response.status_code == 200, response.text
                value = response.json()
                if value['receipt'] is not None:
                    return value
                time.sleep(.02)
            raise AssertionError('receipt not persisted')

        app = build_local_app(root,data_parent=target,assistant_model_runtime=runtime)
        with serve(app) as address, httpx2.Client(base_url=address,trust_env=False,timeout=5) as client:
            assert client.get('/api/assistant/attempts/'+str(uuid4())).status_code == 401
            headers = login(client)
            url,payload,first,elapsed = submit(client,headers)
            report['fast_accept_seconds'] = elapsed
            with httpx2.Client(base_url=address,cookies=client.cookies,trust_env=False,timeout=3) as other:
                view = other.get(url).json()
                response = other.put(url+'/draft',headers=headers,json={
                    'expected_scope':view['scope'],'expected_composer_revision':view['composer_revision'],
                    'content':'另一连接在模型等待期间保存的下一句草稿。'})
                assert response.status_code == 200, response.text
            assert client.post(url+'/generations',headers=headers,json=payload).json()['id'] == first['id']
            assert client.get(url+'/generations/by-request/'+payload['request_id']).json()['id'] == first['id']
            assert len(received) == 1
            report['checks'].append('fast_durable_accept_concurrent_draft_and_replay_one_post')
            release.set()
            result = settled(client,first)
            assert result['state'] == 'received' and result['receipt']['cost_status'] == 'estimated'
            assert result['output']['review_status'] == 'unverified' and result['output']['audience'] == 'internal'
            assert result['output']['candidate']['citations'][0]['quote_sha256'] == sha(text_input)
            assert client.get(url).json()['draft_input'].startswith('另一连接')
            assert client.post(url+'/generations',headers=headers,json=payload).json()['id'] == first['id']
            assert len(received) == 1
            report['checks'].append('receipt_candidate_citation_and_current_draft_preserved')
            assert client.post('/api/logout',headers=headers).status_code == 200
            assert client.get('/api/assistant/attempts/'+first['id']).status_code == 401
            headers = login(client)
            release.clear(); entered.clear()
            second_url,second_payload,second,_ = submit(client,headers)
            assert len(received) == 2
            response = client.post('/api/assistant/runs/'+second['run_id']+'/cancel',headers=headers,
                json={'request_id':str(uuid4())})
            assert response.status_code == 200, response.text
            release.set()
            cancelled = settled(client,second)
            assert cancelled['output'] is None and cancelled['receipt'] is not None
            report['checks'].append('logout_rechecks_read_and_cancelled_reply_keeps_receipt_without_output')
            release.clear(); entered.clear()
            third_url,third_payload,third,_ = submit(client,headers)
            assert len(received) == 3
            # Leave provider waiting; native lifespan must cancel and settle before DB disposal.
        release.set()
        report['checks'].append('shutdown_while_provider_pending_exits_cleanly')
        app = build_local_app(root,data_parent=target,assistant_model_runtime=runtime)
        with serve(app) as address, httpx2.Client(base_url=address,trust_env=False,timeout=5) as client:
            headers = login(client)
            found = client.get(third_url+'/generations/by-request/'+third_payload['request_id']).json()
            assert found['id'] == third['id'] and found['receipt']['cost_status'] == 'unknown'
            assert found['state'] == 'sent_unknown' and found['output'] is None
            assert client.post(third_url+'/generations',headers=headers,json=third_payload).json()['id'] == third['id']
            assert len(received) == 3
            assert client.get('/api/assistant/attempts/'+first['id']).json()['output'] == result['output']
            report['checks'].append('restart_reads_receipts_and_replay_does_not_resend')
        with sqlite3.connect(root/'workbench.db') as db:
            assert db.execute('PRAGMA quick_check').fetchall() == [('ok',)]
            assert db.execute('PRAGMA foreign_key_check').fetchall() == []
            report['counts'] = {name:db.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in (
                'assistant_model_attempts','assistant_model_receipts','assistant_model_outputs')}
            assert list(report['counts'].values()) == [3,3,1]
        report.update(status='passed',upstream_posts=len(received),upstream_payload_hashes=received)
    except BaseException as error:
        report.update(status='failed',error_type=type(error).__name__,error=str(error))
        raise
    finally:
        release.set(); upstream.shutdown(); upstream.server_close()
        (target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True))


if __name__ == '__main__':
    main()
