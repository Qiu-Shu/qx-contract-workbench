"""Smoke the actual backend entry in an isolated synthetic Windows workspace."""
import hashlib
import json
from pathlib import Path
from queue import Queue
import sqlite3
import subprocess
import sys
from threading import Thread
import time
from uuid import uuid4
import httpx

from cn_contract.storage_schema import identify_schema, CURRENT_VERSION


def main():
    base = Path(__file__).resolve().parent
    executable = base/'frozen-backend/qx-backend/qx-backend.exe'
    parent = base/('冻结 后端合成 '+uuid4().hex[:8])
    parent.mkdir()
    report = {'scope':'actual newly frozen backend startup/auth/schema; not installer acceptance',
              'exe_sha256':hashlib.sha256(executable.read_bytes()).hexdigest(), 'checks':[], 'workspace_parent':str(parent)}
    started = time.perf_counter()
    process = subprocess.Popen([str(executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
    lines = Queue()
    Thread(target=lambda:[lines.put(line) for line in process.stdout],daemon=True).start()
    try:
        nonce = uuid4().hex
        credentials = {'username':'合成冻结律师','password':'fixture123'}
        process.stdin.write(json.dumps({'data_parent':str(parent),'nonce':nonce,**credentials})+'\n')
        process.stdin.flush()
        ready = json.loads(lines.get(timeout=120))
        assert ready['event'] == 'ready' and ready['nonce'] == nonce, ready
        report.update(ready_seconds=round(time.perf_counter()-started,3), pid=process.pid)
        address = f'http://127.0.0.1:{ready["port"]}'
        with httpx.Client(base_url=address, trust_env=False, timeout=15) as client:
            assert client.get('/login').status_code == 200
            assert client.get('/api/assistant/conversations').status_code == 401
            response = client.post('/api/login', json=credentials)
            assert response.status_code == 200
            assert client.get('/api/session').json()['home_url'] == '/assistant'
            assert client.get('/assistant').status_code == 200
            view=client.post('/api/assistant/conversations',headers={'X-CSRF-Token':response.json()['csrf_token']},json={'request_id':str(uuid4())}).json()
            chat_url='/api/assistant/conversations/'+view['scope']['conversation_id']
            assert client.get(chat_url+'/generation-capability').json()['state']=='unconfigured'
            rejected=client.post(chat_url+'/generations',headers={'X-CSRF-Token':response.json()['csrf_token']},json={'request_id':str(uuid4()),'content':'独立合成未获准消息','expected_scope':view['scope'],'expected_composer_revision':0})
            assert rejected.status_code==403 and rejected.json()['code']=='BLOCKED_LIVE'
            report['checks'].append('ready_login_assistant_and_unconfigured_generation_denied')
        process.stdin.close()
        report['exit_code'] = process.wait(timeout=30)
        stderr = process.stderr.read()
        assert report['exit_code'] == 0 and stderr == ''
        try:
            httpx.get(address+'/login', trust_env=False, timeout=2)
        except httpx.TransportError:
            report['checks'].append('clean_parent_pipe_shutdown_and_closed_port')
        else:
            raise AssertionError('owned process left backend port open')
        root = parent/'workspaces/main'
        with sqlite3.connect(root/'workbench.db') as connection:
            rows = connection.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
            version = identify_schema(rows, native=True)
            assert version == CURRENT_VERSION == 'assistant-model-v1'
            assert connection.execute('PRAGMA quick_check').fetchall() == [('ok',)]
            assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
            counts = {name:connection.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in
                ('assistant_model_attempts','assistant_model_receipts','assistant_model_outputs')}
            assert counts == dict.fromkeys(counts,0)
        marker = json.loads((root/'workspace.json').read_text('utf-8'))
        actual_hash = hashlib.sha256(json.dumps(rows,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        assert marker['schema_sha256'] == actual_hash
        report['checks'].append('exact_current_model_schema_marker_and_sqlite_integrity')
        report.update(status='passed', schema_version=version, model_counts=counts)
    except BaseException as failure:
        report.update(status='failed', error_type=type(failure).__name__, error=str(failure))
        raise
    finally:
        if process.poll() is None:
            process.kill(); process.wait(timeout=10)
        (base/'frozen-backend-smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True))


if __name__ == '__main__':
    main()
