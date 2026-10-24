"""Faults and recovery never separate TaskInbox delivery from its fixed receipt."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from pathlib import Path
import subprocess
import sys
from threading import Barrier

import pytest
from sqlalchemy import event,text

from cn_contract import domain as d
from cn_contract.assistant import service as conversations
from cn_contract.ops import backup,workspace_backup
from cn_contract.persistence import Database
from cn_contract.security import ServiceError,authenticate,login
from cn_contract.weixin_inbox.dispatch_integrity import validate_dispatch_records
from tests.helpers.legacy_assistant_backup import USERNAME,PASSWORD,PASSPHRASE
from tests.integration.test_weixin_dispatch import api,message,seed,state,world


@pytest.mark.parametrize('point',['task_event','dispatch_receipt','commit'])
def test_precommit_failure_rolls_back_all_task_rows_and_fixed_receipt(world,monkeypatch,point):
    module=api();_,database,actor,*_=world
    account,mapping,received=seed(world,[message(1)])
    descriptor=received.descriptors[0]
    before=state(database); triggered=[]
    if point=='commit':
        def fail(db):
            triggered.append(point)
            raise OSError('independent synthetic commit failure')
        with monkeypatch.context() as patch:
            patch.setattr(database.session_factory.class_,'commit',fail)
            with pytest.raises(OSError):module.dispatch_synthetic_descriptor(actor,descriptor.id,database=database)
    else:
        def fail(connection,cursor,statement,parameters,context,executemany):
            normalized=' '.join(statement.lower().split())
            table='task_inbox_events' if point=='task_event' else 'weixin_dispatch_receipts'
            if normalized.startswith('insert into '+table):
                triggered.append(point)
                raise OSError('independent synthetic write failure')
        event.listen(database.engine,'before_cursor_execute',fail)
        try:
            with pytest.raises(OSError):module.dispatch_synthetic_descriptor(actor,descriptor.id,database=database)
        finally:event.remove(database.engine,'before_cursor_execute',fail)
    assert triggered==[point] and state(database)==before
    assert module.find_dispatch_receipt(actor,descriptor.id,database=database) is None
    receipt=module.dispatch_synthetic_descriptor(actor,descriptor.id,database=database)
    assert receipt.next_task_cursor==1
    with database.session() as db:assert validate_dispatch_records(db,allow_dispatch=True)==[]


def test_commit_succeeded_but_ack_was_lost_can_be_queried_and_replayed(world,monkeypatch):
    module=api();_,database,actor,*_=world
    _,_,received=seed(world,[message(1)])
    descriptor=received.descriptors[0];commit=database.session_factory.class_.commit;committed=[]
    def lost(db):
        commit(db);committed.append(True)
        raise OSError('independent synthetic acknowledgement loss')
    with monkeypatch.context() as patch:
        patch.setattr(database.session_factory.class_,'commit',lost)
        with pytest.raises(OSError):module.dispatch_synthetic_descriptor(actor,descriptor.id,database=database)
    assert committed==[True]
    found=module.find_dispatch_receipt(actor,descriptor.id,database=database)
    assert found is not None and found.next_task_cursor==1
    before=state(database)
    assert module.dispatch_synthetic_descriptor(actor,descriptor.id,database=database)==found
    assert state(database)==before


def test_two_sessions_dispatch_the_same_source_once(world):
    module=api();_,database,actor,*_=world
    _,_,received=seed(world,[message(1)])
    descriptor=received.descriptors[0];barrier=Barrier(2)
    def send():
        barrier.wait(timeout=10)
        return module.dispatch_synthetic_descriptor(actor,descriptor.id,database=database)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(send) for _ in range(2)]
        receipts=[future.result(timeout=30) for future in futures]
    assert receipts[0]==receipts[1]
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM task_inbox_events'))==1
        assert db.scalar(text('SELECT count(*) FROM weixin_dispatch_receipts'))==1
        assert db.scalar(text('SELECT cursor FROM task_channel_bindings'))==1
        assert validate_dispatch_records(db,allow_dispatch=True)==[]


@pytest.mark.parametrize('kind',['peer','account'])
def test_same_clock_tick_dispatch_then_revocation_preserves_valid_history(world,monkeypatch,kind):
    module=api();_,database,actor,*_=world
    from cn_contract.weixin_inbox import accounts
    account,mapping,received=seed(world,[message(1)])
    if kind=='peer':
        from cn_contract.task_drafts import service as tasks
        from uuid import uuid4
        with database.session() as db:
            view=conversations.create_conversation(actor,d.AssistantConversationCreateInput(request_id=uuid4()),db)
            binding=tasks.create_binding(actor,view.scope.conversation_id,db)
        accounts.bind_synthetic_peer(actor,account.id,d.WeixinPeerBindInput(sender_peer_id='peer-2',
            task_binding_id=binding.id,expected_scope=view.scope),database=database)
    fixed=(datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat()
    with monkeypatch.context() as patch:
        patch.setattr(module,'_at',lambda:fixed)
        patch.setattr(accounts,'_at',lambda:fixed)
        receipt=module.dispatch_synthetic_descriptor(actor,received.descriptors[0].id,database=database)
        revoke=accounts.revoke_synthetic_peer if kind=='peer' else accounts.revoke_synthetic_account
        revoked=revoke(actor,mapping.id if kind=='peer' else account.id,
            d.WeixinRevokeInput(reason='独立虚构同刻度撤权'),database=database)
    with database.session() as db:
        assert validate_dispatch_records(db,allow_dispatch=True)==[]
        backup._file_references(db)
    assert revoked.revoked_at>receipt.created_at
    if kind=='peer':
        from cn_contract.weixin_inbox import ingress
        from tests.integration.test_weixin_dispatch import poll
        with monkeypatch.context() as patch:
            patch.setattr(ingress,'_at',lambda:fixed)
            subsequent=poll(world,account,[message(2),message(3,peer='peer-2')])
        assert subsequent.descriptors[0].reason=='binding_revoked'
        assert subsequent.created_at>=revoked.revoked_at
        assert subsequent.descriptors[1].status=='accepted_pending_dispatch'
        module.dispatch_synthetic_descriptor(actor,subsequent.descriptors[1].id,database=database)
        with database.session() as db:backup._file_references(db)


def test_new_process_finds_committed_dispatch_without_mutable_draft_state(world):
    module=api();root,database,actor,*_=world
    _,_,received=seed(world,[message(1)])
    receipt=module.dispatch_synthetic_descriptor(actor,received.descriptors[0].id,database=database)
    code='''import sys
from pathlib import Path
from uuid import UUID
from cn_contract import domain as d
from cn_contract.config import load_settings
from cn_contract.persistence import Database
from cn_contract.ops import backup
from cn_contract.weixin_inbox.dispatch import find_dispatch_receipt
root=Path(sys.argv[1]);database=Database('sqlite:///'+str(root/'workbench.db'),root/'protected',load_settings(),initialize_schema=False)
backup._mark_storage_flags(database)
try:
 receipt=find_dispatch_receipt(d.Actor.model_validate_json(sys.argv[2]),UUID(sys.argv[3]),database=database)
 print(str(receipt.id)+':'+receipt.receipt_sha256)
finally:database.engine.dispose()
'''
    run=subprocess.run([sys.executable,'-B','-X','utf8','-c',code,str(root),actor.model_dump_json(),
        str(receipt.descriptor_id)],capture_output=True,text=True,timeout=30)
    assert run.returncode==0,run.stderr
    assert run.stdout.strip()==str(receipt.id)+':'+receipt.receipt_sha256


def files(root):return {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_actual_shared_history_survives_two_qxbak_generations_and_never_replays(world,tmp_path):
    module=api();root,database,actor,view,*_=world
    _,_,received=seed(world,[message(1),message(2,file=True)])
    receipts=[module.dispatch_synthetic_descriptor(actor,value.id,database=database) for value in received.descriptors]
    expected=state(database)
    with database.session() as db:
        assert validate_dispatch_records(db,allow_dispatch=True)==[]
        backup._file_references(db)
    original=files(root);archive=tmp_path/'实际合成分发.qxbak'
    workspace_backup.create_workspace_backup(root,archive,PASSPHRASE,data_parent=tmp_path)
    for generation in (1,2):
        result=workspace_backup.restore_workspace_backup(archive,tmp_path/('分发恢复'+str(generation)),PASSPHRASE)
        target=Path(result['restored_root'])
        restored=Database('sqlite:///'+str(target/'workbench.db'),target/'protected',database.settings,initialize_schema=False)
        backup._mark_storage_flags(restored)
        try:
            with restored.session() as db:
                token,_=login(USERNAME,PASSWORD,db);current=authenticate(token,db)
                assert validate_dispatch_records(db,allow_dispatch=True)==[]
                backup._file_references(db)
                assert db.scalar(text('SELECT count(*) FROM task_inbox_events'))==2
                for table in ('task_executions','assistant_runs','review_runs'):
                    assert db.scalar(text('SELECT count(*) FROM '+table))==0
            assert state(restored)==expected
            for receipt in receipts:
                assert module.find_dispatch_receipt(current,receipt.descriptor_id,database=restored)==receipt
                with pytest.raises(ServiceError) as denied:
                    module.dispatch_synthetic_descriptor(current,receipt.descriptor_id,database=restored)
                assert denied.value.code=='BLOCKED_LIVE'
            assert state(restored)==expected
            if generation==1:
                archive=tmp_path/'再次分发备份.qxbak'
                workspace_backup.create_workspace_backup(target,archive,PASSPHRASE,data_parent=tmp_path)
        finally:restored.engine.dispose()
    assert files(root)==original


@pytest.mark.parametrize('damage',['receipt_hash','event_hash'])
def test_authenticated_corrupt_dispatch_archive_is_rejected_without_publication(world,tmp_path,monkeypatch,damage):
    module=api();root,database,actor,*_=world
    _,_,received=seed(world,[message(1)])
    module.dispatch_synthetic_descriptor(actor,received.descriptors[0].id,database=database)
    table='weixin_dispatch_receipts' if damage=='receipt_hash' else 'task_inbox_events'
    column='receipt_sha256' if damage=='receipt_hash' else 'payload_sha256'
    with database.session() as db:
        triggers=db.execute(text("SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name=:table"),{'table':table}).all()
        for name,_ in triggers:db.execute(text('DROP TRIGGER '+name))
        db.execute(text('UPDATE '+table+' SET '+column+'=:sha'),{'sha':'0'*64})
        for _,ddl in triggers:db.execute(text(ddl))
    rejected=tmp_path/'拒绝备份.qxbak'
    with pytest.raises(ValueError):workspace_backup.create_workspace_backup(root,rejected,PASSPHRASE,data_parent=tmp_path)
    assert not rejected.exists()
    hostile=tmp_path/'认证但来源损坏.qxbak'
    with monkeypatch.context() as patch:
        patch.setattr(workspace_backup,'_file_references',lambda db:[])
        workspace_backup.create_workspace_backup(root,hostile,PASSPHRASE,data_parent=tmp_path)
    original=files(root);target=tmp_path/'不得发布'
    with pytest.raises(ValueError):workspace_backup.restore_workspace_backup(hostile,target,PASSPHRASE)
    assert not target.exists() or not list(target.iterdir())
    assert files(root)==original
