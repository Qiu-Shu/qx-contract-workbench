"""Actual generation transactions keep fixed metadata and historical payloads atomic."""
from concurrent.futures import ThreadPoolExecutor
import subprocess
import sys
from threading import Barrier, Event, current_thread
from uuid import uuid4

import pytest
from sqlalchemy import event,text

from cn_contract import domain as d
from cn_contract.ops import backup
from cn_contract.persistence import Database
from cn_contract.security import ServiceError
from tests.helpers.synthetic_weixin_generation_service import api,append,find,request
from tests.helpers.synthetic_weixin_generations import setup_history,state
from tests.integration.test_weixin_dispatch import message,poll
from tests.integration.test_weixin_ingress_atomic import world


def test_atomic_generation_module_exists_without_starting_any_worker():
    assert callable(api().append_synthetic_generation) and callable(api().find_peer_generation)


@pytest.mark.parametrize('point',['insert','after_insert','commit'])
def test_precommit_generation_fault_rolls_back_all_rows_and_checkpoint(world,monkeypatch,point):
    h=setup_history(world);value=request(h);before=state(h['database']);triggered=[]
    def fail(*args):
        triggered.append(point)
        raise OSError('independent fictional generation precommit failure')
    if point=='commit':
        with monkeypatch.context() as patch:
            patch.setattr(h['database'].session_factory.class_,'commit',fail)
            with pytest.raises(OSError):append(h,value)
    else:
        def insert(connection,cursor,statement,parameters,context,executemany):
            if ' '.join(statement.lower().split()).startswith('insert into weixin_peer_generations'):fail()
        phase='after_cursor_execute' if point=='after_insert' else 'before_cursor_execute'
        event.listen(h['database'].engine,phase,insert)
        try:
            with pytest.raises(OSError):append(h,value)
        finally:event.remove(h['database'].engine,phase,insert)
    assert triggered==[point] and state(h['database'])==before
    assert find(h,value.request_id) is None
    assert append(h,value).generation==1


def test_actual_commit_with_lost_ack_is_only_queried_not_resent(world,monkeypatch):
    h=setup_history(world);value=request(h);before=state(h['database'],generations=False)
    original=h['database'].session_factory.class_.commit;committed=[]
    def lose(db):
        original(db);committed.append(True)
        raise OSError('independent fictional generation acknowledgement lost after actual commit')
    with monkeypatch.context() as patch:
        patch.setattr(h['database'].session_factory.class_,'commit',lose)
        with pytest.raises(OSError):append(h,value)
    assert committed==[True]
    found=find(h,value.request_id)
    assert found is not None and found.request_id==value.request_id and found.generation==1
    stable=state(h['database'])
    assert find(h,value.request_id)==found and state(h['database'])==stable
    assert state(h['database'],generations=False)==before
    with h['database'].session() as db:
        assert db.execute(text('SELECT id,generation_sha256 FROM weixin_peer_generations')).one()==(str(found.id),found.generation_sha256)


@pytest.mark.parametrize('kind',['database','process'])
def test_fixed_generation_lookup_survives_new_database_or_process(world,kind):
    h=setup_history(world);value=request(h);saved=append(h,value);before=state(h['database'])
    if kind=='database':
        database=Database('sqlite:///'+str(h['root']/'workbench.db'),h['root']/'protected',h['database'].settings,initialize_schema=False)
        backup._mark_storage_flags(database)
        try:
            assert api().find_peer_generation(h['actor'],h['mapping'].id,value.request_id,database=database)==saved
        finally:database.engine.dispose()
    else:
        code='''import sys
from pathlib import Path
from uuid import UUID
from cn_contract import domain as d
from cn_contract.config import load_settings
from cn_contract.persistence import Database
from cn_contract.ops import backup
from cn_contract.weixin_inbox.generations import find_peer_generation
root=Path(sys.argv[1]);db=Database('sqlite:///'+str(root/'workbench.db'),root/'protected',load_settings(),initialize_schema=False)
backup._mark_storage_flags(db)
try:
 value=find_peer_generation(d.Actor.model_validate_json(sys.argv[2]),UUID(sys.argv[3]),UUID(sys.argv[4]),database=db)
 print(str(value.id)+':'+value.generation_sha256)
finally:db.engine.dispose()
'''
        result=subprocess.run([sys.executable,'-B','-X','utf8','-c',code,str(h['root']),h['actor'].model_dump_json(),
            str(h['mapping'].id),str(value.request_id)],capture_output=True,text=True,timeout=30)
        assert result.returncode==0,result.stderr
        assert result.stdout.strip()==str(saved.id)+':'+saved.generation_sha256
    assert state(h['database'])==before


@pytest.mark.parametrize('same_request',[False,True])
def test_two_sessions_compete_for_one_generation_cas(world,same_request):
    h=setup_history(world);first=request(h)
    other_view,other_binding=h['targets'][1]
    second=first if same_request else request(h,request_id=uuid4(),task_binding_id=other_binding.id,expected_scope=other_view.scope)
    before=state(h['database'],generations=False);barrier=Barrier(2)
    def compete(value):
        barrier.wait(timeout=10)
        try:return append(h,value)
        except ServiceError as error:return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(compete,value) for value in (first,second)]
        results=[future.result(timeout=30) for future in futures]
    if same_request:assert isinstance(results[0],d.WeixinPeerGeneration) and results[0]==results[1]
    else:
        assert sum(isinstance(value,d.WeixinPeerGeneration) for value in results)==1
        assert 'VERSION_CONFLICT' in results
    assert state(h['database'],generations=False)==before
    with h['database'].session() as db:assert db.scalar(text('SELECT count(*) FROM weixin_peer_generations'))==1


@pytest.mark.parametrize('winner',['poll','append'])
def test_poll_and_generation_serialize_with_explicit_checkpoint_cas(world,winner):
    h=setup_history(world);value=request(h);before=state(h['database']);locked=Event();second_began=Event()
    first_name=[]
    def observe(connection,cursor,statement,parameters,context,executemany):
        normalized=' '.join(statement.lower().split());name=current_thread().name
        if normalized=='begin immediate' and first_name and name!=first_name[0]:second_began.set()
        target='update weixin_accounts' if winner=='poll' else 'insert into weixin_peer_generations'
        if normalized.startswith(target) and not locked.is_set():
            first_name.append(name);locked.set()
            assert second_began.wait(timeout=10),'second actual SQLite transaction did not contend'
    def call(operation):
        try:return operation()
        except ServiceError as error:return error.code
    operations=dict(poll=lambda:poll(world,h['account'],[message(90)]),append=lambda:append(h,value))
    loser='append' if winner=='poll' else 'poll'
    event.listen(h['database'].engine,'before_cursor_execute',observe)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(call,operations[winner])
            assert locked.wait(timeout=10),'winning writer did not reach its real SQL mutation'
            second=pool.submit(call,operations[loser])
            won,lost=first.result(timeout=30),second.result(timeout=30)
    finally:event.remove(h['database'].engine,'before_cursor_execute',observe)
    assert second_began.is_set()
    after=state(h['database'])
    if winner=='append':
        assert isinstance(won,d.WeixinPeerGeneration) and lost=='STATE_CONFLICT'
        assert state(h['database'],generations=False)=={name:rows for name,rows in before.items() if name!='weixin_peer_generations'}
    else:
        assert isinstance(won,d.WeixinPollReceipt) and lost=='VERSION_CONFLICT'
        assert not after['weixin_peer_generations']
        for name in before:
            if name in ('weixin_accounts','weixin_poll_receipts','weixin_inbox_descriptors'):continue
            assert after[name]==before[name],name
        for name in ('weixin_poll_receipts','weixin_inbox_descriptors'):
            assert after[name][:len(before[name])]==before[name]
            assert len(after[name])==len(before[name])+1
        with h['database'].session() as db:
            assert db.scalar(text('SELECT checkpoint_revision FROM weixin_accounts WHERE id=:id'),{'id':str(h['account'].id)})==value.expected_checkpoint_revision+1
            columns=[row[1] for row in db.execute(text('PRAGMA table_info(weixin_accounts)'))]
        for old,new in zip(before['weixin_accounts'],after['weixin_accounts'],strict=True):
            for column,prior,current in zip(columns,old,new,strict=True):
                if column not in ('checkpoint_revision','upstream_cursor'):assert prior==current,column


def test_unknown_request_lookup_is_read_only(world):
    h=setup_history(world);before=state(h['database'])
    assert find(h,uuid4()) is None and state(h['database'])==before
