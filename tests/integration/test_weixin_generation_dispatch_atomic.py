"""Real synthetic delivery transactions, races, new process and fenced archive recovery."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
from threading import Barrier

import pytest
from sqlalchemy import event,text

from cn_contract.ops import backup,workspace_backup
from cn_contract.persistence import Database,read_original
from cn_contract.security import ServiceError,authenticate,login
from cn_contract.weixin_inbox import generation_dispatch as service
from tests.helpers.legacy_assistant_backup import USERNAME,PASSWORD,PASSPHRASE
from tests.helpers.synthetic_weixin_generations import setup_history
from tests.helpers.synthetic_weixin_generation_service import append,request as generation_request
from tests.integration.test_weixin_dispatch import message
from tests.integration.test_weixin_generation_ingress import receive
from tests.integration.test_weixin_generation_ingress_atomic import checked_state
from tests.integration.test_weixin_ingress_atomic import world
from tests.integration.test_weixin_provenance_backup import original_material


def history(world):
    h=setup_history(world);h['first']=append(h)
    h['delivery_poll']=receive(h,[message(91),message(92)])
    return h


def dispatch(h,descriptor):
    return service.dispatch_generation_descriptor(h['actor'],descriptor.id,database=h['database'])


@pytest.mark.parametrize('point',['cursor','receipt','commit'])
def test_real_sql_or_precommit_failure_rolls_back_all_task_and_receipt_changes(world,monkeypatch,point):
    h=history(world);database=h['database'];descriptor=h['delivery_poll'].descriptors[0]
    before=checked_state(database);hit=[]
    if point=='commit':
        def fail(session):
            hit.append(point);raise OSError('independent synthetic dispatch precommit failure')
        with monkeypatch.context() as patch:
            patch.setattr(database.session_factory.class_,'commit',fail)
            with pytest.raises(OSError):dispatch(h,descriptor)
    else:
        def fail(connection,cursor,statement,parameters,context,executemany):
            sql=' '.join(statement.lower().split())
            if point=='cursor' and sql.startswith('update task_channel_bindings') or point=='receipt' and sql.startswith('insert into weixin_dispatch_receipts'):
                hit.append(point);raise OSError('independent synthetic dispatch SQL failure')
        event.listen(database.engine,'before_cursor_execute',fail)
        try:
            with pytest.raises(OSError):dispatch(h,descriptor)
        finally:event.remove(database.engine,'before_cursor_execute',fail)
    assert hit==[point] and checked_state(database)==before
    assert service.find_generation_dispatch_receipt(h['actor'],descriptor.id,database=database) is None
    assert dispatch(h,descriptor).expected_task_cursor==0
    checked_state(database)


@pytest.mark.parametrize('same',[True,False])
def test_two_real_dispatch_threads_serialize_receipts_and_cursor_slots(world,same):
    h=history(world);descriptors=h['delivery_poll'].descriptors;barrier=Barrier(2)
    def run(item):
        barrier.wait(timeout=10)
        try:return dispatch(h,item)
        except ServiceError as error:return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(run,descriptors[0]);b=pool.submit(run,descriptors[0] if same else descriptors[1])
        one,two=a.result(timeout=30),b.result(timeout=30)
    if same:assert one==two and one.expected_task_cursor==0
    else:
        assert not isinstance(one,str)
        if isinstance(two,str):assert two=='VERSION_CONFLICT';two=dispatch(h,descriptors[1])
        assert [one.expected_task_cursor,two.expected_task_cursor]==[0,1]
    with h['database'].session() as db:
        slots=db.execute(text('SELECT expected_task_cursor FROM weixin_dispatch_receipts WHERE task_binding_id=:id ORDER BY expected_task_cursor'),
            {'id':str(h['first'].task_binding_id)}).scalars().all()
        assert slots==([0] if same else [0,1])
    checked_state(h['database'])


def test_real_append_racing_delivery_keeps_generation_one_source_fixed(world):
    h=history(world);barrier=Barrier(2);request=generation_request(h,h['first'])
    def deliver():barrier.wait(timeout=10);return dispatch(h,h['delivery_poll'].descriptors[0])
    def change():barrier.wait(timeout=10);return append(h,request)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(deliver);b=pool.submit(change);receipt,later=a.result(timeout=30),b.result(timeout=30)
    assert later.generation==2 and receipt.task_binding_id==h['first'].task_binding_id
    assert receipt.task_binding_id!=later.task_binding_id
    checked_state(h['database'])


def test_new_python_process_finds_committed_fixed_delivery_without_replay(world):
    h=history(world);descriptor=h['delivery_poll'].descriptors[0];receipt=dispatch(h,descriptor)
    before=checked_state(h['database'])
    code="""import sys
from pathlib import Path
from uuid import UUID
from cn_contract.domain import Actor
from cn_contract.config import load_settings
from cn_contract.ops import backup
from cn_contract.persistence import Database
from cn_contract.weixin_inbox.generation_dispatch import find_generation_dispatch_receipt
root=Path(sys.argv[1]);database=Database('sqlite:///'+str(root/'workbench.db'),root/'protected',load_settings(),initialize_schema=False)
backup._mark_storage_flags(database)
try:
 result=find_generation_dispatch_receipt(Actor.model_validate_json(sys.argv[2]),UUID(sys.argv[3]),database=database)
 with database.session() as db:backup._file_references(db)
 print(result.model_dump_json())
finally:database.engine.dispose()
"""
    result=subprocess.run([sys.executable,'-B','-X','utf8','-c',code,str(h['root']),h['actor'].model_dump_json(),str(descriptor.id)],
        capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)==receipt.model_dump(mode='json')
    assert checked_state(h['database'])==before


def test_two_real_qxbak_roundtrips_preserve_fixed_receipt_original_and_read_only_fences(world,tmp_path):
    h=history(world);database=h['database'];root=h['root']
    matter,version,material=original_material(h)
    descriptor=h['delivery_poll'].descriptors[0];receipt=dispatch(h,descriptor)
    append(h,generation_request(h,h['first']))
    before=checked_state(database)
    original={p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}
    archive=tmp_path/'独立虚构固定代际分发.qxbak'
    workspace_backup.create_workspace_backup(root,archive,PASSPHRASE,data_parent=tmp_path)
    for index in (1,2):
        archive_bytes=archive.read_bytes()
        report=workspace_backup.restore_workspace_backup(archive,tmp_path/('独立恢复'+str(index)),PASSPHRASE)
        target=Path(report['restored_root']);restored=Database('sqlite:///'+str(target/'workbench.db'),target/'protected',database.settings,initialize_schema=False)
        backup._mark_storage_flags(restored)
        try:
            with pytest.raises(ServiceError) as error:service.find_generation_dispatch_receipt(h['actor'],descriptor.id,database=restored)
            assert error.value.code=='AUTHORIZATION_REQUIRED'
            with restored.session() as db:
                token,_=login(USERNAME,PASSWORD,db);actor=authenticate(token,db)
                assert read_original(matter.id,version.id,actor,db)==material
                fence=json.loads(db.scalar(text('SELECT payload FROM ops_restore_fences ORDER BY rowid DESC LIMIT 1')))
                for flag in ('task_inbox_enabled','weixin_inbox_enabled','weixin_dispatch_enabled','weixin_generation_enabled','live_egress','current_approvals_valid'):assert fence[flag] is False
            restored_before=checked_state(restored)
            assert service.find_generation_dispatch_receipt(actor,descriptor.id,database=restored)==receipt
            with pytest.raises(ServiceError) as error:service.dispatch_generation_descriptor(actor,descriptor.id,database=restored)
            assert error.value.code=='BLOCKED_LIVE' and checked_state(restored)==restored_before
        finally:restored.engine.dispose()
        assert archive.read_bytes()==archive_bytes
        if index==1:
            archive=tmp_path/'独立虚构再次备份.qxbak'
            workspace_backup.create_workspace_backup(target,archive,PASSPHRASE,data_parent=tmp_path)
    assert checked_state(database)==before
    assert {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}==original
