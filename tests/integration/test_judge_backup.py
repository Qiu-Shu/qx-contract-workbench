"""Jev records survive real encrypted backups without resuming execution."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from typing import get_args

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.assistant.providers import jev_codec
from cn_contract.ops import backup, workspace_backup
from cn_contract.security import authenticate, login, ServiceError
from cn_contract.web import local_server
from tests.helpers.legacy_assistant_backup import PASSPHRASE
from tests.integration.test_assistant_attachment_backup import corrupt
from tests.integration.test_judge_attempts import world, setup, api


def stage(world, state):
    database, actor, run, request, runtime = setup(world)
    with database.session() as db:
        attempt = api().reserve(actor, run.id, db, runtime)
    if state != 'reserved':
        with database.session() as db:
            token, _, config = api().claim(actor, attempt.id, db, runtime)
        if state != 'sending':
            values = dict(status='failed', reason_code='provider_error', evidence=state,
                local_request_id=request.local_request_id, scope=request.scope,
                input_hash=jev_codec.input_hash(request, config), elapsed_ms=1)
            if state == 'received':
                values.update(status='ok', reason_code=None, model='jev-1.13.0',
                    usage=d.JudgeUsage(input_tokens=9, output_tokens=None),
                    answers={'primary_intent':d.JudgeChoice(choice='client_reply', confidence=1,
                        probabilities={k:int(k=='client_reply') for k in (*get_args(d.AssistantSkill),'unknown')})})
            with database.session() as db:
                api().settle(actor, attempt.id, token, d.JudgeResult(**values), db, runtime)
    return database, actor, run, request, runtime, attempt


@pytest.mark.parametrize('state', ['reserved', 'sending', 'not_sent', 'sent_unknown', 'received'])
def test_judge_qxbak_roundtrip_preserves_receipts_and_restores_read_only(world, tmp_path, state):
    database, actor, run, request, runtime, attempt = stage(world, state)
    root = Path(database.engine.url.database).parent
    archive = tmp_path/'独立辅助合成备份.qxbak'
    with local_server._worker_lock(root):
        pass
    with database.session() as db:
        original_view = api().read_attempt(actor, attempt.id, db)
        original_run = dict(db.execute(text('SELECT * FROM assistant_runs')).mappings().one())
    before = (root/'workbench.db').read_bytes()
    workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
    archived = archive.read_bytes()
    result = workspace_backup.restore_workspace_backup(archive, tmp_path/'恢复副本', PASSPHRASE)
    restored = local_server._database(Path(result['restored_root']))
    try:
        with restored.session() as db:
            token, _ = login('lawyer','fixture123',db)
            current_actor = authenticate(token,db)
            current = api().read_attempt(current_actor, attempt.id, db)
            assert current.state == {'reserved':'not_sent','sending':'sent_unknown'}.get(state,state)
            assert current.scope == request.scope and current.message_id == attempt.message_id
            assert current.receipt.cost_status == ('not_sent' if current.state=='not_sent' else 'unknown')
            assert current.receipt.occupied_usd == (0 if current.state=='not_sent' else attempt.reserved_usd)
            if state not in ('reserved','sending'):
                assert current.receipt == original_view.receipt and current.decision == original_view.decision
            if state == 'received':
                assert current.receipt.result.usage.output_tokens is None
            with pytest.raises(ServiceError):
                api().claim(current_actor, attempt.id, db, runtime)
        with TestClient(local_server.build_local_app(Path(result['restored_root']),data_parent=tmp_path)) as client:
            assert client.get('/login').status_code==200
        with restored.session() as db:
            assert api().read_attempt(current_actor,attempt.id,db)==current
    finally:
        restored.engine.dispose()
    assert archive.read_bytes()==archived
    assert (root/'workbench.db').read_bytes()==before
    with database.session() as db:
        assert dict(db.execute(text('SELECT * FROM assistant_runs')).mappings().one())==original_run


@pytest.mark.parametrize('claimed', [False,True])
def test_native_restart_closes_pending_judge_only_without_retransmission(world,tmp_path,monkeypatch,claimed):
    from cn_contract.assistant.providers.jev import JevProvider
    database,actor,run,request,runtime,attempt=stage(world,'sending' if claimed else 'reserved')
    root=Path(database.engine.url.database).parent
    async def no_send(*args,**kwargs): pytest.fail('startup must never send Jev')
    monkeypatch.setattr(JevProvider,'judge',no_send)
    with database.session() as db:
        before=dict(db.execute(text('SELECT * FROM assistant_runs')).mappings().one())
    for _ in range(2):
        with TestClient(local_server.build_local_app(root,data_parent=tmp_path)) as client:
            assert client.get('/login').status_code==200
        with database.session() as db:
            result=api().read_attempt(actor,attempt.id,db)
            assert result.state==('sent_unknown' if claimed else 'not_sent')
            assert dict(db.execute(text('SELECT * FROM assistant_runs')).mappings().one())==before
            assert db.scalar(text('SELECT count(*) FROM assistant_judge_receipts'))==1


@pytest.mark.parametrize('table,sql,params', [
    ('assistant_judge_attempts','UPDATE assistant_judge_attempts SET input_hash=?',('0'*64,)),
    ('assistant_judge_receipts','UPDATE assistant_judge_receipts SET receipt_json=?',('{"fake":true}',)),
    ('assistant_judge_decisions','UPDATE assistant_judge_decisions SET decision_json=?',('{"fake":true}',)),
])
def test_authenticated_invalid_judge_archive_is_rejected_before_publication(world,tmp_path,monkeypatch,table,sql,params):
    database,*_=stage(world,'received')
    root=Path(database.engine.url.database).parent
    corrupt(database,table,sql,params)
    with database.session() as db,pytest.raises(ValueError,match='ASSISTANT_JUDGE'):
        backup._file_references(db)
    bad=tmp_path/'invalid-fixture.qxbak'
    with monkeypatch.context() as patch:
        patch.setattr(workspace_backup,'_file_references',lambda db:[])
        workspace_backup.create_workspace_backup(root,bad,PASSPHRASE,data_parent=tmp_path)
    before=(root/'workbench.db').read_bytes()
    destination=tmp_path/'must-not-publish'
    with pytest.raises(ValueError,match='ASSISTANT_JUDGE'):
        workspace_backup.restore_workspace_backup(bad,destination,PASSPHRASE)
    assert not destination.exists() or not list(destination.iterdir())
    assert (root/'workbench.db').read_bytes()==before
