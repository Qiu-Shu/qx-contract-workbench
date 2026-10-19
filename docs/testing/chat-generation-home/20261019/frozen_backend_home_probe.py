"""Actual newly frozen backend startup, homepage assets, closed runtime and history."""
import hashlib
import json
from pathlib import Path
from queue import Queue
import socket
import sqlite3
import subprocess
import sys
from threading import Thread
import time
from uuid import uuid4
import httpx
from cn_contract.storage_schema import CURRENT_VERSION,identify_schema

BASE=Path(__file__).resolve().parent
PROJECT=BASE.parents[1]

def main():
    executable=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else BASE/'frozen-backend-verified/qx-backend/qx-backend.exe'
    parent=BASE/('frozen-home-workspace-'+uuid4().hex[:8]);parent.mkdir()
    report={'scope':'actual newly frozen EXE; default model runtime None; not installer acceptance',
        'checks':[],'exe_sha256':hashlib.sha256(executable.read_bytes()).hexdigest(),'real_model_calls':0,
        'workspace_parent':str(parent),'command':[str(executable)],'exit_code':1}
    started=time.perf_counter()
    process=subprocess.Popen([str(executable)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        text=True,encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW)
    lines=Queue();Thread(target=lambda:[lines.put(line) for line in process.stdout],daemon=True).start()
    def passed(name):report['checks'].append(name);print('PASS '+name,flush=True)
    try:
        credentials={'username':'合成冻结首页律师','password':'fixture123'};nonce=uuid4().hex
        process.stdin.write(json.dumps({'data_parent':str(parent),'nonce':nonce,**credentials})+'\n');process.stdin.flush()
        ready=json.loads(lines.get(timeout=120));assert ready['event']=='ready' and ready['nonce']==nonce
        report['ready_seconds']=round(time.perf_counter()-started,3);report['pid']=process.pid
        address=f'http://127.0.0.1:{ready["port"]}'
        with httpx.Client(base_url=address,trust_env=False,timeout=15) as client:
            assert client.get('/login').status_code==200
            assert client.get('/api/assistant/conversations').status_code==401
            login=client.post('/api/login',json=credentials);assert login.status_code==200
            headers={'X-CSRF-Token':login.json()['csrf_token']}
            home=client.get('/assistant');assert home.status_code==200 and 'generation-note' in home.text
            for name in ('assistant.mjs','assistant-generation.mjs','assistant-state.mjs','assistant-render.mjs'):
                response=client.get('/static/'+name);assert response.status_code==200
                assert hashlib.sha256(response.content).digest()==hashlib.sha256((PROJECT/'src/cn_contract/web/static'/name).read_bytes()).digest()
            passed('new_exe_login_home_and_exact_current_generation_assets')
            view=client.post('/api/assistant/conversations',headers=headers,json={'request_id':str(uuid4())}).json()
            base='/api/assistant/conversations/'+view['scope']['conversation_id']
            content='独立合成冻结首页文字：验证默认关闭并保留草稿。'
            saved=client.put(base+'/draft',headers=headers,json={'expected_scope':view['scope'],
                'expected_composer_revision':view['composer_revision'],'content':content})
            assert saved.status_code==200;view=saved.json()
            cap=client.get(base+'/generation-capability').json()
            assert cap['state']=='unconfigured' and cap['content_sha256']==hashlib.sha256(content.encode()).hexdigest()
            body={'request_id':str(uuid4()),'expected_scope':view['scope'],
                'expected_composer_revision':view['composer_revision'],'content':content}
            rejected=client.post(base+'/generations',headers=headers,json=body)
            assert rejected.status_code==403 and rejected.json()['code']=='BLOCKED_LIVE'
            assert client.get(base).json()['draft_input']==content
            passed('new_exe_default_generation_rejected_and_saved_text_retained')
            queued=client.post(base+'/messages',headers=headers,json=body)
            assert queued.status_code==202,queued.text
            message_id=queued.json()['message_id']
            history=client.get(base+'/generation-history',params={'message_id':message_id})
            assert history.status_code==200 and history.json()['items']==[]
            assert history.json()['scope']['conversation_id']==view['scope']['conversation_id']
            assert client.get(base+'/generation-history',params={'message_id':str(uuid4())}).status_code==403
            passed('new_exe_history_current_ownership_and_legacy_message_has_no_attempt')
        process.stdin.close();report['backend_exit']=process.wait(timeout=35)
        stderr=process.stderr.read();assert report['backend_exit']==0 and stderr==''
        with socket.socket() as sock:assert sock.connect_ex(('127.0.0.1',ready['port']))!=0
        root=parent/'workspaces/main'
        with sqlite3.connect(root/'workbench.db') as db:
            rows=db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
            assert identify_schema(rows,native=True)==CURRENT_VERSION
            assert db.execute('PRAGMA quick_check').fetchall()==[('ok',)]
            assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
            counts={name:db.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in
                ('assistant_messages','assistant_model_attempts','assistant_model_receipts','assistant_model_outputs')}
            assert list(counts.values())==[1,0,0,0],counts
        marker=json.loads((root/'workspace.json').read_text('utf-8'))
        assert marker['schema_sha256']==hashlib.sha256(json.dumps(rows,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        report['counts']=counts;report['schema_version']=CURRENT_VERSION
        passed('new_exe_clean_pipe_exit_port_release_and_database_integrity')
        report.update(status='passed',exit_code=0)
    except BaseException as error:
        report.update(status='failed',error_type=type(error).__name__,error=str(error));raise
    finally:
        if process.poll() is None:process.kill();process.wait(timeout=10)
        (BASE/'frozen-backend-home-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'checks':len(report['checks']),'exe_sha256':report['exe_sha256']}))

if __name__=='__main__':main()
