"""Finite synthetic STDIO test driver, with child cleanup on every path."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
from queue import Queue, Empty
import subprocess
import sys
from threading import Thread


ROOT = Path(__file__).resolve().parents[2]
CANARY = 'INDEPENDENT_FICTIONAL_MCP_CANARY'


@contextmanager
def child(*, launch_code=None):
    # Test-owned environment: no real credential values are inherited here.
    env = {key: os.environ[key] for key in ('SYSTEMROOT', 'PATH', 'TEMP', 'TMP') if key in os.environ}
    env['DEEPSEEK_API_KEY'] = CANARY
    command = [sys.executable, '-X', 'utf8']
    command += ['-c', launch_code] if launch_code is not None else ['-m', 'cn_contract.mcp.offline_server']
    process = subprocess.Popen(command,
        cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding='utf-8')
    replies = Queue()
    stderr = []
    def reader():
        for line in process.stdout:
            replies.put(line)
    def error_reader():
        for line in process.stderr:
            stderr.append(line)
    threads = [Thread(target=reader, daemon=True), Thread(target=error_reader, daemon=True)]
    for thread in threads:
        thread.start()
    try:
        def send(method, params=None, *, request_id=1):
            message = {'jsonrpc': '2.0', 'method': method}
            if params is not None:
                message['params'] = params
            if request_id is not None:
                message['id'] = request_id
            process.stdin.write(json.dumps(message, ensure_ascii=False) + '\n')
            process.stdin.flush()
            if request_id is None:
                return None
            try:
                line = replies.get(timeout=10)
            except Empty:
                raise AssertionError('offline child did not produce a finite reply') from None
            decoded = json.loads(line)  # stdout must contain only protocol frames.
            assert decoded['jsonrpc'] == '2.0' and decoded['id'] == request_id
            return decoded
        yield process, send, stderr
    finally:
        if process.stdin:
            process.stdin.close()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=1)
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()


def initialize(send):
    result = send('initialize', {'protocolVersion': '2025-11-25', 'capabilities': {},
                                'clientInfo': {'name': 'synthetic-offline-test', 'version': '1'}})
    assert 'error' not in result
    send('notifications/initialized', {}, request_id=None)
    return result['result']
