"""Actual desktop process bytes and pipe boundaries, no provider calls."""
import json
import os
from queue import Queue
import subprocess
import sys
from threading import Thread

from cn_contract.web.local_server import initialize_workspace


def test_native_stdout_is_canonical_lf_and_control_uses_same_owned_pipe(tmp_path):
    proc = subprocess.Popen([sys.executable, '-m', 'cn_contract.desktop_entry'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    lines = Queue()
    Thread(target=lambda: [lines.put(line) for line in proc.stdout], daemon=True).start()
    nonce = 'b'*32
    try:
        proc.stdin.write((json.dumps({'data_parent':str(tmp_path/'合成 管道'), 'nonce':nonce,
            'username':'synthetic', 'password':'fixture123'})+'\n').encode('utf-8'))
        proc.stdin.flush()
        raw = lines.get(timeout=30)
        assert raw.endswith(b'\n') and not raw.endswith(b'\r\n')
        ready = json.loads(raw)
        assert ready['control_protocol'] == 'qx-model-control-v1'
        command = dict(event='model-control', protocol=ready['control_protocol'], nonce=nonce,
            sequence=1, operation='disable', payload={})
        proc.stdin.write((json.dumps(command,separators=(',',':'))+'\n').encode());proc.stdin.flush()
        raw = lines.get(timeout=15)
        assert not raw.endswith(b'\r\n')
        assert json.loads(raw)['status'] == 'disabled'
        # Oversize UTF-8 bytes without a terminator must not wait for EOF.
        command.update(sequence=2,payload={'text':'字'*12000})
        proc.stdin.write(json.dumps(command,ensure_ascii=False).encode('utf-8'));proc.stdin.flush()
        assert proc.wait(timeout=5) == 2
        assert proc.stderr.read() == b''
    finally:
        if proc.poll() is None:proc.kill();proc.wait()
        proc.stdin.close();proc.stdout.close();proc.stderr.close()


def test_maintenance_completion_exits_with_parent_pipe_still_open(tmp_path):
    parent = tmp_path/'合成 维护'
    initialize_workspace(parent/'workspaces/main','synthetic','fixture123',data_parent=parent)
    archive = tmp_path/'synthetic.qxbak'
    for operation in ('backup','restore'):
        proc = subprocess.Popen([sys.executable,'-m','cn_contract.desktop_entry'],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        lines = Queue()
        Thread(target=lambda:[lines.put(line) for line in proc.stdout],daemon=True).start()
        try:
            command=dict(data_parent=str(parent),nonce='c'*32,operation=operation,
                         archive=str(archive),passphrase='synthetic-maintenance-password-12345')
            proc.stdin.write((json.dumps(command)+'\n').encode());proc.stdin.flush()
            value=json.loads(lines.get(timeout=30))
            assert value['event']=='complete'
            assert proc.wait(timeout=15)==0
            assert proc.stderr.read()==b''
            if operation=='restore':assert value['report']['quarantined'] is True
        finally:
            if proc.poll() is None:proc.kill();proc.wait()
            proc.stdin.close();proc.stdout.close();proc.stderr.close()
