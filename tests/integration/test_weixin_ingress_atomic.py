"""Real synthetic services: commit faults, concurrent CAS, process recovery and qxbak."""
from concurrent.futures import ThreadPoolExecutor
import importlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import event, text

from cn_contract import domain as d
from cn_contract.assistant import service as conversations
from cn_contract.config import load_settings
from cn_contract.ops import backup, workspace_backup
from cn_contract.persistence import Database
from cn_contract.security import ServiceError, authenticate, login
from cn_contract.task_drafts import service as tasks
from cn_contract.web.local_server import _worker_lock, initialize_workspace
from cn_contract.weixin_inbox.integrity import validate_weixin_records
from tests.helpers.legacy_assistant_backup import USERNAME, PASSWORD, PASSPHRASE
from tests.helpers.synthetic_weixin_inbox import snapshot


@pytest.fixture
def world(tmp_path):
    root=tmp_path/'独立虚构原子收件'
    initialize_workspace(root,USERNAME,PASSWORD,data_parent=tmp_path)
    database=Database('sqlite:///'+str(root/'workbench.db'),root/'protected',load_settings(),initialize_schema=False)
    backup._mark_storage_flags(database)
    with database.session() as db:
        token,_=login(USERNAME,PASSWORD,db)
        actor=authenticate(token,db)
        view=conversations.create_conversation(actor,d.AssistantConversationCreateInput(request_id=uuid4()),db)
        binding=tasks.create_binding(actor,view.scope.conversation_id,db)
    with _worker_lock(root): pass
    try:
        yield root,database,actor,view,binding
    finally:
        database.engine.dispose()


def setup(world):
    assert importlib.util.find_spec('cn_contract.weixin_inbox.ingress'), 'D2b needs atomic durable poll ingestion'
    accounts=importlib.import_module('cn_contract.weixin_inbox.accounts')
    ingress=importlib.import_module('cn_contract.weixin_inbox.ingress')
    _,database,actor,view,binding=world
    account=accounts.create_synthetic_account(actor,d.WeixinAccountCreateInput(
        bot_account_id='synthetic-atomic-bot',initial_cursor='opaque:0'),database=database)
    accounts.bind_synthetic_peer(actor,account.id,d.WeixinPeerBindInput(sender_peer_id='synthetic-peer',
        task_binding_id=binding.id,expected_scope=view.scope),database=database)
    request=d.WeixinPollInput(request_id=uuid4(),expected_revision=0,expected_cursor='opaque:0')
    raw=json.dumps({'ret':0,'msgs':[{'message_id':1,'from_user_id':'synthetic-peer',
        'to_user_id':account.bot_account_id,'message_type':1,'message_state':2,
        'item_list':[{'type':1,'text_item':{'text':'仅为独立虚构原子提交说明'}}]}],
        'get_updates_buf':'opaque:1'},ensure_ascii=False).encode()
    return ingress,account,request,raw


def state(database):
    with database.session() as db:
        validate_weixin_records(db,allow_inbox=True)
        for table in ('task_inbox_events','task_drafts','task_executions','assistant_runs'):
            assert db.scalar(text('SELECT count(*) FROM '+table))==0
        return snapshot(db)


@pytest.mark.parametrize('point',['descriptor','checkpoint','commit'])
def test_failure_before_commit_has_no_partial_poll_or_cursor(world,monkeypatch,point):
    ingress,account,request,raw=setup(world)
    _,database,actor,*_=world
    before=state(database)
    triggered=[]
    if point=='commit':
        def fail(db):
            triggered.append(point)
            raise OSError('independent synthetic pre-commit failure')
        with monkeypatch.context() as patch:
            patch.setattr(database.session_factory.class_,'commit',fail)
            with pytest.raises(OSError):
                ingress.record_synthetic_poll(actor,account.id,request,raw,database=database)
    else:
        def fail(connection,cursor,statement,parameters,context,executemany):
            normalized=' '.join(statement.lower().split())
            if ((point=='descriptor' and normalized.startswith('insert into weixin_inbox_descriptors'))
                    or (point=='checkpoint' and normalized.startswith('update weixin_accounts'))):
                triggered.append(point)
                raise OSError('independent synthetic write failure')
        event.listen(database.engine,'before_cursor_execute',fail)
        try:
            with pytest.raises(OSError):
                ingress.record_synthetic_poll(actor,account.id,request,raw,database=database)
        finally:
            event.remove(database.engine,'before_cursor_execute',fail)
    assert triggered==[point]
    assert state(database)==before
    assert ingress.find_poll_receipt(actor,account.id,request.request_id,database=database) is None
    result=ingress.record_synthetic_poll(actor,account.id,request,raw,database=database)
    assert result.next_revision==1 and result.descriptor_count==1
    state(database)


def test_lost_ack_after_actual_commit_is_recovered_by_query_without_reexecution(world,monkeypatch):
    ingress,account,request,raw=setup(world)
    _,database,actor,*_=world
    commit=database.session_factory.class_.commit
    committed=[]
    def lose_ack(db):
        commit(db)
        committed.append(True)
        raise OSError('independent synthetic acknowledgement lost after commit')
    with monkeypatch.context() as patch:
        patch.setattr(database.session_factory.class_,'commit',lose_ack)
        with pytest.raises(OSError):
            ingress.record_synthetic_poll(actor,account.id,request,raw,database=database)
    assert committed==[True]
    stored=ingress.find_poll_receipt(actor,account.id,request.request_id,database=database)
    assert stored is not None and stored.next_revision==1
    before=state(database)
    replay=ingress.record_synthetic_poll(actor,account.id,request,raw,database=database)
    assert replay==stored and state(database)==before


@pytest.mark.parametrize('same_request',[False,True])
def test_two_independent_sessions_serialize_checkpoint_and_request_replay(world,same_request):
    ingress,account,request,raw=setup(world)
    _,database,actor,*_=world
    barrier=Barrier(2)
    def send(index):
        candidate=request if same_request or index==0 else d.WeixinPollInput(
            request_id=uuid4(),expected_revision=0,expected_cursor='opaque:0')
        barrier.wait(timeout=10)
        try:
            return ingress.record_synthetic_poll(actor,account.id,candidate,raw,database=database)
        except ServiceError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(send,index) for index in range(2)]
        results=[future.result(timeout=30) for future in futures]
    accepted=[value for value in results if isinstance(value,d.WeixinPollReceipt)]
    if same_request:
        assert len(accepted)==2 and accepted[0]==accepted[1]
    else:
        assert len(accepted)==1 and results.count('VERSION_CONFLICT')==1
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM weixin_poll_receipts'))==1
        assert db.scalar(text('SELECT count(*) FROM weixin_inbox_descriptors'))==1
        assert db.scalar(text('SELECT checkpoint_revision FROM weixin_accounts'))==1
    state(database)


def test_a_new_python_process_can_find_the_committed_complete_receipt(world):
    ingress,account,request,raw=setup(world)
    root,database,actor,*_=world
    result=ingress.record_synthetic_poll(actor,account.id,request,raw,database=database)
    code='''import sys
from pathlib import Path
from uuid import UUID
from cn_contract import domain as d
from cn_contract.config import load_settings
from cn_contract.persistence import Database
from cn_contract.ops import backup
from cn_contract.weixin_inbox.ingress import find_poll_receipt
root=Path(sys.argv[1]); db=Database('sqlite:///'+str(root/'workbench.db'),root/'protected',load_settings(),initialize_schema=False)
backup._mark_storage_flags(db)
try:
    receipt=find_poll_receipt(d.Actor.model_validate_json(sys.argv[2]),UUID(sys.argv[3]),UUID(sys.argv[4]),database=db)
    print(str(receipt.id)+':'+receipt.receipt_sha256)
finally: db.engine.dispose()
'''
    run=subprocess.run([sys.executable,'-B','-X','utf8','-c',code,str(root),actor.model_dump_json(),
        str(account.id),str(request.request_id)],capture_output=True,text=True,timeout=30)
    assert run.returncode==0, run.stderr
    assert run.stdout.strip()==str(result.id)+':'+result.receipt_sha256
    state(database)


def test_service_created_history_roundtrips_and_restore_cannot_ingest_even_a_replay(world,tmp_path):
    ingress,account,request,raw=setup(world)
    root,database,actor,*_=world
    receipt=ingress.record_synthetic_poll(actor,account.id,request,raw,database=database)
    before=state(database)
    original={p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}
    archive=tmp_path/'实际合成服务.qxbak'
    workspace_backup.create_workspace_backup(root,archive,PASSPHRASE,data_parent=tmp_path)
    result=workspace_backup.restore_workspace_backup(archive,tmp_path/'合成恢复',PASSPHRASE)
    restored_root=Path(result['restored_root'])
    restored=Database('sqlite:///'+str(restored_root/'workbench.db'),restored_root/'protected',
        database.settings,initialize_schema=False)
    backup._mark_storage_flags(restored)
    try:
        with restored.session() as db:
            token,_=login(USERNAME,PASSWORD,db)
            current=authenticate(token,db)
        assert state(restored)==before
        assert ingress.find_poll_receipt(current,account.id,request.request_id,database=restored)==receipt
        with pytest.raises(ServiceError) as denied:
            ingress.record_synthetic_poll(current,account.id,request,raw,database=restored)
        assert denied.value.code=='BLOCKED_LIVE'
        assert state(restored)==before
    finally:
        restored.engine.dispose()
    assert {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}==original
