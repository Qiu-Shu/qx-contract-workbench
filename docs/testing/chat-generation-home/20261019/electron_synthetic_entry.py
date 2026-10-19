"""Test-only desktop bootstrap: real stdin protocol and real app, trusted loopback runtime."""
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from threading import Thread
from uuid import UUID, uuid4

from sqlalchemy import select
from cn_contract import domain as d
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.assistant.providers.policy import MainModelRuntime, encoded, sha
from cn_contract.persistence import UserRow
from cn_contract.web import local_server
from cn_contract.desktop_entry import main

TEXT='独立合成Electron验收：请列出虚构交货日期的待核事项。'
OUTPUT='独立合成Electron候选：交货日期仍需律师核对消息原文。'
evidence=Path(os.environ['QX_PROBE_EVIDENCE'])
report={'scope':'test-only trusted loopback runtime injected before actual desktop_entry.main',
    'received':[],'errors':[],'real_model_calls':0}
secret='SYNTHETIC_ELECTRON_FIXTURE_NOT_A_REAL_KEY'

def save():
    (evidence/'synthetic-runtime.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*_):
        pass
    def do_POST(self):
        try:
            assert self.path=='/chat/completions'
            assert self.headers.get('Authorization')=='Bearer '+secret
            payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            source=json.loads(payload['messages'][1]['content'])
            assert source['content']==TEXT,'source must match approved synthetic text'
            report['received'].append({'message_id':source['message_id'],'source_sha256':sha(TEXT)})
            save()
            candidate={'text':OUTPUT,'citations':[{'message_id':source['message_id'],
                'quote_sha256':source['quote_sha256']}]}
            body=json.dumps({'id':'synthetic-electron','model':'deepseek-flash',
                'object':'chat.completion','created':1,'choices':[{'index':0,'finish_reason':'stop',
                'message':{'role':'assistant','content':json.dumps(candidate,ensure_ascii=False)}}],
                'usage':{'prompt_tokens':30,'completion_tokens':12,'total_tokens':42}},ensure_ascii=False).encode()
            self.send_response(200);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        except Exception as error:
            report['errors'].append(type(error).__name__);save();self.send_error(500,'synthetic probe failed')

upstream=ThreadingHTTPServer(('127.0.0.1',0),Handler)
upstream.daemon_threads=True
Thread(target=upstream.serve_forever,daemon=True).start()
original=local_server.build_local_app

def build(root,**kwargs):
    database=local_server._database(root)
    try:
        with database.session() as db:actor=UUID(db.scalar(select(UserRow.id)))
    finally:
        database.engine.dispose()
    workspace=json.loads((Path(root)/'workspace.json').read_text('utf-8'))['workspace_id']
    config=d.MainModelConfig(enabled=True,model='deepseek-flash',input_usd_per_million='0.3',
        output_usd_per_million='1.2',price_reference='synthetic-electron-only',timeout_seconds=30)
    policy=d.MainModelPolicy(policy_id=uuid4(),workspace_id=workspace,actor_id=actor,
        config_sha256=sha(encoded(config)),allowed_content_sha256s=(sha(TEXT),),
        max_total_usd='1',max_calls=2,expires_at=datetime.now(timezone.utc)+timedelta(hours=1))
    runtime=MainModelRuntime(DeepSeekProvider.for_synthetic_loopback(config,lambda:secret,
        f'http://127.0.0.1:{upstream.server_port}/chat/completions'),policy)
    report['allowed_content_sha256']=sha(TEXT);report['runtime_injected']=True;save()
    return original(root,**kwargs,assistant_model_runtime=runtime)

local_server.build_local_app=build
try:
    result=main()
finally:
    upstream.shutdown();upstream.server_close();report['clean_runtime_shutdown']=True;save()
raise SystemExit(result)
