"""Actual Windows backend against fictional Jev records; no production installation."""
import asyncio, hashlib, json, os, sqlite3, subprocess, sys, time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Queue
from threading import Thread
from uuid import uuid4
import httpx
from sqlalchemy import text
from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.assistant.providers import judge_attempts as ledger, jev_codec
from cn_contract.assistant.providers.judge_policy import JudgeRuntime, encoded, sha
from cn_contract.assistant.providers.jev import JevProvider
from cn_contract.assistant.providers.judge_execution import execute_attempt
from cn_contract.security import login, authenticate
from cn_contract.web import local_server
from cn_contract.storage_schema import CURRENT_VERSION, identify_schema

ROOT=Path.cwd(); OUT=ROOT/'.local/jev-ledger-20261020'; MODE=sys.argv[1]
COMMAND=([str(ROOT/'.venv/Scripts/python.exe'),'-X','utf8','-m','cn_contract.desktop_entry'] if MODE=='source' else [str(OUT/'frozen-backend/qx-backend/qx-backend.exe')])
parent=OUT/(MODE+' 合成工作区 '+uuid4().hex[:8]); parent.mkdir()
report={'mode':MODE,'groups':[],'child_exits':[],'whole_app_ui_tested':False,'installed_app_changed':False,'real_model_calls':0,'command':COMMAND,
 'loopback_execution_process':'host Python seed; the child verifies recovery, encrypted backup and restore',
 'external_network_tripwire':False}
posts=[]
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*_): pass
 def do_POST(self):
  payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
  assert self.path=='/v1/systemone' and payload['state']['latest_request'].startswith('独立合成')
  options=payload['questions']['primary_intent']['criteria']; posts.append(payload)
  body={'model':'jev-1.13.0','answers':{'primary_intent':{'type':'choice','choice':'client_reply','confidence':1,'probabilities':{k:int(k=='client_reply') for k in options}}},'usage':{'input_tokens':12,'output_tokens':None}}
  self.send_response(200); self.send_header('Content-Type','application/json'); self.end_headers();self.wfile.write(json.dumps(body).encode())

async def seed(root,endpoint):
 local_server.initialize_workspace(root,'合成律师','fixture123',data_parent=parent)
 database=local_server._database(root); expected={}
 try:
  with database.session() as db:
   token,_=login('合成律师','fixture123',db);actor=authenticate(token,db)
  for kind in ('received','sending','reserved'):
   with database.session() as db:
    chat=service.create_conversation(actor,d.AssistantConversationCreateInput(request_id=uuid4()),db)
    run=service.save_message(actor,chat.scope.conversation_id,d.AssistantMessageInput(request_id=uuid4(),expected_scope=chat.scope,expected_composer_revision=0,content='独立合成咨询：请回复虚构客户，并完整保留后续整理需求。'+kind),db)
   config=d.JevConfig(enabled=True); runtime=JudgeRuntime(JevProvider.for_synthetic_loopback(config,lambda:'synthetic-ledger-key',endpoint))
   with database.session() as db: request=ledger.request_for_run(actor,run.id,db,config)
   policy=d.JudgePolicy(policy_id=uuid4(),workspace_id=run.scope.workspace_id,actor_id=actor.user_id,session_id=actor.session_id,config_sha256=sha(encoded(config)),permissions=(d.JudgePermission(local_request_id=request.local_request_id,purpose=request.purpose,input_hash=jev_codec.input_hash(request,config)),),reserved_usd='0.02',max_total_usd='0.02',max_calls=1,expires_at=datetime.now(timezone.utc)+timedelta(minutes=10))
   runtime.grant(policy)
   with database.session() as db: attempt=ledger.reserve(actor,run.id,db,runtime)
   if kind=='received':
    value=await execute_attempt(actor,attempt.id,database,runtime)
    assert value.state=='received' and value.decision is not None
    assert value.receipt.result.usage.output_tokens is None and value.receipt.cost_status=='unknown'
    assert await execute_attempt(actor,attempt.id,database,runtime)==value
   elif kind=='sending':
    with database.session() as db: assert ledger.claim(actor,attempt.id,db,runtime)
   expected[str(attempt.id)]={'state':{'received':'received','sending':'sent_unknown','reserved':'not_sent'}[kind],'run_id':str(run.id)}
  with database.session() as db:
   assert db.scalar(text('SELECT count(*) FROM assistant_model_attempts'))==0
   original={r['id']:dict(r) for r in db.execute(text('SELECT * FROM assistant_runs')).mappings()}
  return expected,original
 finally: database.engine.dispose()

class Child:
 def __init__(self,config):
  self.started=time.perf_counter();self.lines=Queue();self.nonce=uuid4().hex
  self.p=subprocess.Popen(COMMAND,cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW)
  Thread(target=lambda:[self.lines.put(line) for line in self.p.stdout],daemon=True).start()
  self.p.stdin.write(json.dumps({'data_parent':str(parent),'nonce':self.nonce,**config})+'\n');self.p.stdin.flush()
 def first(self):
  value=json.loads(self.lines.get(timeout=90));assert value['event']!='error',value
  assert value['nonce']==self.nonce
  return value
 def close(self):
  try:
   if not self.p.stdin.closed:self.p.stdin.close()
   code=self.p.wait(timeout=30);stderr=self.p.stderr.read()
   assert code==0 and stderr=='',(code,stderr)
   report['child_exits'].append(code)
  finally:
   if self.p.poll() is None:self.p.kill();self.p.wait(timeout=10)

def start_check(workspace='main',restored=False):
 child=Child({'workspace':workspace})
 try:
  ready=child.first();assert ready['event']=='ready'
  report.setdefault('ready_seconds',[]).append(round(time.perf_counter()-child.started,3))
  with httpx.Client(base_url=f'http://127.0.0.1:{ready["port"]}',trust_env=False,timeout=15) as client:
   assert client.get('/login').status_code==200
   response=client.post('/api/login',json={'username':'合成律师','password':'fixture123'});assert response.status_code==200
   assert client.get('/assistant').status_code==200
   if restored:
    rejected=client.post('/api/assistant/conversations',headers={'X-CSRF-Token':response.json()['csrf_token']},json={'request_id':str(uuid4())})
    assert rejected.status_code in (403,409),rejected.text
 finally: child.close()

def rows(root):
 with sqlite3.connect(root/'workbench.db') as db:
  db.row_factory=sqlite3.Row
  return {name:[dict(r) for r in db.execute('SELECT * FROM '+name+' ORDER BY '+('id' if name in ('assistant_runs','assistant_judge_attempts') else 'attempt_id'))] for name in ('assistant_runs','assistant_judge_attempts','assistant_judge_receipts','assistant_judge_decisions')}

server=ThreadingHTTPServer(('127.0.0.1',0),Handler);Thread(target=server.serve_forever,daemon=True).start()
try:
 root=parent/'workspaces/main'; expected,original=asyncio.run(seed(root,f'http://127.0.0.1:{server.server_port}/v1/systemone'))
 assert len(posts)==1;report['groups'].append('single_loopback_execution_unknown_usage_and_no_replay')
 start_check(); after=rows(root)
 assert {r['id']:r['state'] for r in after['assistant_judge_attempts']}=={k:v['state'] for k,v in expected.items()}
 assert len(after['assistant_judge_receipts'])==3 and len(after['assistant_judge_decisions'])==1
 assert {r['id']:r for r in after['assistant_runs']}==original
 start_check();assert rows(root)==after and len(posts)==1
 report['groups'].append('actual_backend_recovery_once_without_replay_or_main_run_change')
 with sqlite3.connect(root/'workbench.db') as db:
  assert identify_schema(db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall(),native=True)==CURRENT_VERSION=='assistant-judge-v1'
  assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
 report['groups'].append('actual_backend_exact_current_schema')
 archive=parent/'Jev 合成资料.qxbak'; source_before=(root/'workbench.db').read_bytes()
 child=Child({'operation':'backup','archive':str(archive),'passphrase':'synthetic-ledger-passphrase'})
 try: assert child.first()['report']['verified'] is True
 finally: child.close()
 child=Child({'operation':'restore','archive':str(archive),'passphrase':'synthetic-ledger-passphrase'})
 try: restored=Path(child.first()['report']['restored_root'])
 finally: child.close()
 assert (root/'workbench.db').read_bytes()==source_before
 restored_rows=rows(restored)
 for name in ('assistant_judge_attempts','assistant_judge_receipts','assistant_judge_decisions'):assert restored_rows[name]==after[name]
 report['groups'].append('actual_backend_encrypted_backup_restore_retains_judge_receipts')
 start_check(restored.relative_to(parent/'workspaces').as_posix(),restored=True)
 assert rows(restored)==restored_rows and len(posts)==1
 report['groups'].append('restored_startup_is_read_only_and_does_not_resume')
 report.update(status='passed',loopback_posts=len(posts),workspace=str(parent),schema=CURRENT_VERSION)
 if MODE=='frozen':report['exe_sha256']=hashlib.sha256(Path(COMMAND[0]).read_bytes()).hexdigest()
except BaseException as exc:
 report.update(status='failed',error_type=type(exc).__name__,error=str(exc));raise
finally:
 server.shutdown();server.server_close()
 (OUT/(MODE+'-backend-report.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=True))
