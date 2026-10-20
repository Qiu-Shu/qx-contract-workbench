"""Desktop keeps existing access controls while moving data outside installation."""
import importlib.util
import json
import os
from pathlib import Path
from queue import Queue, Empty
import subprocess
import sys
from threading import Thread

from fastapi.testclient import TestClient
import httpx
import pytest

from cn_contract.web import local_server


def test_external_user_data_round_trip_and_default_boundary(tmp_path):
    parent = tmp_path / '中文 用户资料'
    root = parent / 'workspaces' / 'main'
    local_server.initialize_workspace(root, '桌面律师', 'fiction123', data_parent=parent)
    before = (root / 'workbench.db').read_bytes()
    with pytest.raises(ValueError, match='WORKSPACE_ALREADY_EXISTS'):
        local_server.initialize_workspace(root, '其他账户', 'fiction123', data_parent=parent)
    assert (root / 'workbench.db').read_bytes() == before
    with pytest.raises(ValueError, match='PROJECT_LOCAL_DIRECTORY_REQUIRED'):
        local_server.build_local_app(root)
    for _ in range(2):
        with TestClient(local_server.build_local_app(root, data_parent=parent, port=18933)) as client:
            assert client.get('/api/matters').status_code == 401
            assert client.post('/api/login', json={'username':'桌面律师', 'password':'fiction123'},
                headers={'Origin':'https://untrusted.invalid'}).status_code == 403
            assert client.post('/api/login', json={'username':'桌面律师', 'password':'fiction123'}).status_code == 200
            assert client.get('/api/matters').status_code == 200
            assert not hasattr(client.app.state, 'case_bridge')


@pytest.mark.parametrize('escape', ['..', '../outside', '.'])
def test_explicit_data_parent_still_rejects_escape(tmp_path, escape):
    parent = tmp_path / 'user-data'
    with pytest.raises(ValueError, match='PROJECT_LOCAL_DIRECTORY_REQUIRED'):
        local_server.initialize_workspace(parent / escape, 'user', 'fiction123', data_parent=parent)


def test_desktop_protocol_readiness_auth_restart_and_eof(tmp_path):
    assert importlib.util.find_spec('cn_contract.desktop_entry'), 'desktop entry missing'
    parent = tmp_path / '桌面 资料'
    for first in (True, False):
        proc = subprocess.Popen([sys.executable, '-m', 'cn_contract.desktop_entry'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', env={**os.environ, 'PYTHONIOENCODING':'utf-8'})
        messages = Queue()
        Thread(target=lambda: [messages.put(line) for line in proc.stdout], daemon=True).start()
        try:
            config = {'data_parent':str(parent), 'nonce':'a' * 32}
            if first: config.update(username='桌面律师', password='fiction123')
            proc.stdin.write(json.dumps(config) + '\n'); proc.stdin.flush()
            message = json.loads(messages.get(timeout=30))
            assert message['event'] == 'ready', message
            assert message['nonce'] == 'a' * 32
            assert message['control_protocol'] == 'qx-model-control-v1'
            assert message['judge_control_protocol'] == 'qx-judge-control-v1'
            configured = []
            for sequence, operation in enumerate(('configure_judge', 'disable', 'configure_judge', 'disable_judge'), 1):
                payload = ({'config': {'enabled': True}, 'secret': 'SYNTHETIC_TYPESAFE_PIPE_TOKEN_ONLY'}
                           if operation == 'configure_judge' else {})
                proc.stdin.write(json.dumps({'event': 'model-control', 'protocol': 'qx-model-control-v1',
                    'nonce': 'a'*32, 'sequence': sequence, 'operation': operation, 'payload': payload})+'\n')
                proc.stdin.flush()
                reply = json.loads(messages.get(timeout=10))
                assert reply['sequence'] == sequence and reply['ok'] is True
                assert reply['protocol'] == 'qx-model-control-v1' and reply['nonce'] == 'a'*32
                assert reply['event'] == 'model-control-result'
                if operation == 'configure_judge':
                    assert reply['status'] == 'configured'
                    configured.append(reply)
                else:
                    assert reply['status'] == 'disabled'
            assert configured[0]['config_sha256'] == configured[1]['config_sha256']
            assert configured[0]['config_version'] != configured[1]['config_version']
            assert 'SYNTHETIC_TYPESAFE' not in repr(configured)
            with httpx.Client(base_url=f"http://127.0.0.1:{message['port']}", trust_env=False) as client:
                assert client.get('/api/matters').status_code == 401
                assert client.post('/api/login', json={'username':'桌面律师','password':'fiction123'}).status_code == 200
                assert client.get('/api/matters').status_code == 200
            proc.stdin.close()
            assert proc.wait(timeout=25) == 0
            assert 'fiction123' not in proc.stderr.read()
        finally:
            if proc.poll() is None: proc.kill(); proc.wait()


def test_desktop_rejects_partial_workspace_without_repair(tmp_path):
    assert importlib.util.find_spec('cn_contract.desktop_entry'), 'desktop entry missing'
    parent = tmp_path / 'partial'
    root = parent / 'workspaces' / 'main'
    root.mkdir(parents=True)
    sentinel = root / 'keep.txt'; sentinel.write_text('untouched')
    result = subprocess.run([sys.executable, '-m', 'cn_contract.desktop_entry'],
        input=json.dumps({'data_parent':str(parent),'nonce':'b'*32,'username':'user','password':'fiction123'})+'\n',
        capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert result.returncode == 1
    assert json.loads(result.stdout)['event'] == 'error'
    assert sentinel.read_text() == 'untouched'
    assert not (root / 'workbench.db').exists()
    assert 'fiction123' not in result.stdout + result.stderr


def test_frozen_rules_resolve_from_same_asset_root_as_settings(tmp_path):
    code = """import sys
from pathlib import Path
sys.frozen = True
sys._MEIPASS = sys.argv[1]
from cn_contract.config import PROJECT_ROOT
from cn_contract.rules.loader import DEFAULT_CARDS
assert DEFAULT_CARDS == PROJECT_ROOT / 'rules/default-draft-cards.json'
"""
    result = subprocess.run([sys.executable, '-c', code, str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_parent_eof_during_initialization_has_bounded_exit(tmp_path):
    code = """import sys,time,types
stub = types.ModuleType('cn_contract.web.local_server')
def initialize(*args,**kwargs):
 print('initializing',flush=True)
 time.sleep(60)
stub.initialize_workspace=initialize
stub.build_local_app=lambda *a,**k:None
sys.modules['cn_contract.web.local_server']=stub
from cn_contract.desktop_entry import main
raise SystemExit(main())
"""
    proc = subprocess.Popen([sys.executable,'-c',code],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,text=True,encoding='utf-8')
    messages = Queue()
    Thread(target=lambda:[messages.put(line) for line in proc.stdout],daemon=True).start()
    try:
        proc.stdin.write(json.dumps({'data_parent':str(tmp_path),'nonce':'c'*32,'username':'user','password':'fiction123'})+'\n')
        proc.stdin.flush(); assert messages.get(timeout=10).strip() == 'initializing'
        proc.stdin.close()
        try: result=proc.wait(timeout=18)
        except subprocess.TimeoutExpired: pytest.fail('child survives parent EOF during initialization')
        assert result == 2
    finally:
        if proc.poll() is None: proc.kill();proc.wait()
