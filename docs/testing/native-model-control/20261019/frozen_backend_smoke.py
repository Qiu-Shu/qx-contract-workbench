"""Final production executable: private control, no provider transmission."""
import hashlib
import json
from pathlib import Path
from queue import Queue
import sqlite3
import subprocess
from threading import Thread
import time
from uuid import uuid4

import httpx

BASE = Path(__file__).resolve().parent


def main():
    executable = BASE/'frozen-backend/qx-backend/qx-backend.exe'
    parent = BASE/('冻结 合成 '+uuid4().hex[:8])
    nonce = uuid4().hex
    report = {'scope':'actual final production backend, not installer or real model approval',
              'exe_sha256':hashlib.sha256(executable.read_bytes()).hexdigest(),
              'real_model_calls':0, 'checks':[], 'workspace_parent':str(parent)}
    lines = Queue()
    process = subprocess.Popen([str(executable)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
    Thread(target=lambda:[lines.put(line) for line in process.stdout],daemon=True).start()
    output = []
    sequence = 0
    def write(value):
        process.stdin.write((json.dumps(value,separators=(',',':'))+'\n').encode());process.stdin.flush()
    def read():
        line = lines.get(timeout=90)
        assert line.endswith(b'\n') and not line.endswith(b'\r\n')
        output.append(line)
        return json.loads(line)
    def control(operation,payload):
        nonlocal sequence
        sequence += 1
        write(dict(event='model-control',protocol='qx-model-control-v1',nonce=nonce,
                   sequence=sequence,operation=operation,payload=payload))
        value=read()
        assert value['nonce']==nonce and value['sequence']==sequence
        return value
    secret='SYNTHETIC_FROZEN_PIPE_NOT_A_REAL_KEY'
    token=''
    try:
        started=time.perf_counter()
        write(dict(data_parent=str(parent),nonce=nonce,username='合成冻结律师',password='fixture123'))
        ready=read();assert ready['event']=='ready' and ready['control_protocol']=='qx-model-control-v1'
        report['ready_seconds']=round(time.perf_counter()-started,3)
        address=f'http://127.0.0.1:{ready["port"]}'
        with httpx.Client(base_url=address,trust_env=False,timeout=10) as client:
            assert client.get('/api/assistant/conversations').status_code==401
            response=client.post('/api/login',json={'username':'合成冻结律师','password':'fixture123'})
            assert response.status_code==200
            headers={'X-CSRF-Token':response.json()['csrf_token']}
            token=client.cookies['qx_session']
            view=client.post('/api/assistant/conversations',headers=headers,json={'request_id':str(uuid4())}).json()
            url='/api/assistant/conversations/'+view['scope']['conversation_id']
            content='独立合成冻结验证，绝不提交给真实供应商。'
            view=client.put(url+'/draft',headers=headers,json={'expected_scope':view['scope'],
                'expected_composer_revision':view['composer_revision'],'content':content}).json()
            assert client.get(url+'/generation-capability').json()['state']=='unconfigured'
            report['checks'].append('canonical_ready_login_empty_registry')
            config=dict(enabled=True,model='deepseek-flash',input_usd_per_million='0.3',
                        output_usd_per_million='1.2',price_reference='synthetic-only')
            configured=control('configure',dict(config=config,secret=secret));assert configured['ok']
            assert client.get(url+'/generation-capability').json()['state']=='unapproved'
            request=dict(request_id=str(uuid4()),expected_scope=view['scope'],
                         expected_composer_revision=view['composer_revision'],content=content)
            payload=dict(session_token=token,expected_config_version=configured['config_version'],
                basis=dict(request_id=request['request_id'],expected_scope=view['scope'],
                    expected_composer_revision=view['composer_revision'],content_sha256=hashlib.sha256(content.encode()).hexdigest()),
                max_total_usd='1',valid_for_seconds=60)
            assert control('authorize',payload)['status']=='authorized'
            assert client.get(url+'/generation-capability').json()['state']=='ready'
            # Do not POST any generation until authority is disabled.
            assert control('disable',{})['status']=='disabled'
            assert client.post(url+'/generations',headers=headers,json=request).status_code==403
            report['checks'].append('private_config_authorize_then_disable_before_any_generation')
        process.stdin.close();assert process.wait(30)==0
        assert process.stderr.read()==b''
        report['checks'].append('normal_eof_clean_exit')
        with sqlite3.connect(parent/'workspaces/main/workbench.db') as db:
            assert db.execute('PRAGMA quick_check').fetchall()==[('ok',)]
            assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
            report['counts']={t:db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in
                ('assistant_model_attempts','assistant_model_receipts','assistant_model_outputs')}
            assert not any(report['counts'].values())
        raw=(parent/'workspaces/main/workbench.db').read_bytes()+b''.join(output)
        assert secret.encode() not in raw and token.encode() not in raw
        report['checks'].append('zero_attempts_integrity_no_plaintext_secret_or_token')
        report['status']='passed'
    except BaseException as error:
        report.update(status='failed',error_type=type(error).__name__)
        raise
    finally:
        if process.poll() is None:process.kill();process.wait(10)
        (BASE/'frozen-backend-smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True))


if __name__=='__main__':main()
