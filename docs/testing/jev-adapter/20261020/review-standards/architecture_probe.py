"""Cold import and pure-advice boundary checks; no real credentials or network."""
import asyncio
import builtins
import json
from pathlib import Path
import socket
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'src'))
from cn_contract import domain as d
from cn_contract.assistant.providers.jev import JevProvider
from cn_contract.assistant.routing import choose_workflow

assert 'httpx2' not in sys.modules
assert not any(name.startswith(('typesafe_sdk', 'cn_contract.assistant.providers.main',
    'cn_contract.persistence', 'cn_contract.web', 'fastapi', 'sqlalchemy')) for name in sys.modules)
value = d.JudgeRequest(local_request_id=uuid4(), scope=d.ScopeSnapshot(
    workspace_id=uuid4(), conversation_id=uuid4(), binding_revision=1,
    input_revision=1, materials_revision=1), purpose='primary_intent',
    text='独立虚构边界文本，先整理全部材料，再回复客户。')
before = value.model_dump_json()
secret_reads = []
imports = []
external = []
original_import = builtins.__import__
original_connect, original_connect_ex = socket.socket.connect, socket.socket.connect_ex
original_lookup = socket.getaddrinfo

def secret():
    secret_reads.append(True)
    raise AssertionError('Secret lookup is not allowed on local skip')

def importing(name, *args, **kwargs):
    if name.startswith(('httpx2', 'typesafe_sdk')):
        imports.append(name)
        raise AssertionError('Network dependencies must remain lazy')
    return original_import(name, *args, **kwargs)

def connect_wrapper(method):
    def connect(sock, address):
        if isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1'):
            return method(sock, address)
        external.append(True)
        raise AssertionError('External network prohibited')
    return connect

def lookup(*args, **kwargs):
    external.append(True)
    raise AssertionError('DNS prohibited')

async def scenario():
    for enabled, expected_reason in ((False, 'unconfigured'), (True, 'no_egress')):
        result = await JevProvider(d.JevConfig(enabled=enabled), secret).judge(value)
        assert (result.status, result.reason_code, result.evidence) == ('skipped', expected_reason, 'not_sent')
        assert result.usage is None and not result.answers
    allowed = {'client_reply', 'material_organize'}
    decision = choose_workflow('material_organize', None, allowed)
    assert decision.workflow == 'material_organize'
    assert set(decision.model_dump()) == {'workflow', 'source', 'reason_code'}
    assert allowed == {'client_reply', 'material_organize'} and value.model_dump_json() == before
    assert secret_reads == [] and imports == [] and external == []

try:
    builtins.__import__ = importing
    socket.socket.connect = connect_wrapper(original_connect)
    socket.socket.connect_ex = connect_wrapper(original_connect_ex)
    socket.getaddrinfo = lookup
    asyncio.run(scenario())
    print(json.dumps({'status': 'passed', 'groups': 3, 'secret_reads': 0,
        'http_dependency_imports': 0, 'external_network_attempts': 0,
        'new_sdk_imports': 0, 'cross_provider_imports': 0,
        'request_and_allowed_set_unchanged': True}))
finally:
    builtins.__import__ = original_import
    socket.socket.connect, socket.socket.connect_ex = original_connect, original_connect_ex
    socket.getaddrinfo = original_lookup
