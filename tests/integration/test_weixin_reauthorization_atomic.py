"""Real synthetic refresh services survive faults, processes and encrypted backups."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from io import BytesIO
from pathlib import Path
import subprocess
import sys
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import event,text

from cn_contract import domain as d
from cn_contract.assistant import attachments,service as conversations
from cn_contract.ops import backup,workspace_backup
from cn_contract.persistence import Database
from cn_contract.security import ServiceError,authenticate,login
from cn_contract.task_drafts import service as tasks
from cn_contract.weixin_inbox import accounts,dispatch
from tests.helpers.legacy_assistant_backup import USERNAME,PASSWORD,PASSPHRASE
from tests.integration.test_weixin_reauthorization import advance,api,message,poll,request,seed,state,world


@pytest.mark.parametrize('point',['grant_insert','commit'])
def test_refresh_precommit_fault_never_changes_grants_or_account_checkpoint(world,monkeypatch,point):
    service=api();_,database,actor,*_=world
    _,mapping,_=seed(world,[]);scope=advance(world,input_revision=1)
    value=request(mapping,scope);before=state(database);triggered=[]
    def fail(*args):
        triggered.append(point);raise OSError('independent fictional precommit fault')
    if point=='commit':
        with monkeypatch.context() as patch:
            patch.setattr(database.session_factory.class_,'commit',fail)
            with pytest.raises(OSError):service.refresh_synthetic_peer(actor,mapping.id,value,database=database)
    else:
        def insert(connection,cursor,statement,parameters,context,executemany):
            if ' '.join(statement.lower().split()).startswith('insert into weixin_peer_scope_grants'):fail()
        event.listen(database.engine,'before_cursor_execute',insert)
        try:
            with pytest.raises(OSError):service.refresh_synthetic_peer(actor,mapping.id,value,database=database)
        finally:event.remove(database.engine,'before_cursor_execute',insert)
    assert triggered==[point] and state(database)==before
    assert service.refresh_synthetic_peer(actor,mapping.id,value,database=database).revision==1


def test_actual_commit_with_lost_ack_is_queryable_and_never_repeated(world,monkeypatch):
    service=api();_,database,actor,*_=world
    _,mapping,_=seed(world,[]);value=request(mapping,advance(world,input_revision=1))
    commit=database.session_factory.class_.commit;committed=[]
    def lost(db):
        commit(db);committed.append(True);raise OSError('independent fictional lost acknowledgement')
    with monkeypatch.context() as patch:
        patch.setattr(database.session_factory.class_,'commit',lost)
        with pytest.raises(OSError):service.refresh_synthetic_peer(actor,mapping.id,value,database=database)
    assert committed==[True]
    found=service.find_peer_scope_grant(actor,mapping.id,value.request_id,database=database)
    assert found is not None and found.revision==1
    before=state(database)
    assert service.refresh_synthetic_peer(actor,mapping.id,value,database=database)==found
    assert state(database)==before


@pytest.mark.parametrize('same_request',[False,True])
def test_two_sessions_compare_and_swap_the_same_authorization_once(world,same_request):
    service=api();_,database,actor,*_=world
    _,mapping,_=seed(world,[]);scope=advance(world,input_revision=1)
    first=request(mapping,scope);second=first if same_request else request(mapping,scope);barrier=Barrier(2)
    def refresh(value):
        barrier.wait(timeout=10)
        try:return service.refresh_synthetic_peer(actor,mapping.id,value,database=database)
        except ServiceError as error:return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(refresh,value) for value in (first,second)]
        results=[future.result(timeout=30) for future in futures]
    if same_request:assert results[0]==results[1] and isinstance(results[0],d.WeixinPeerScopeGrant)
    else:
        assert sum(isinstance(value,d.WeixinPeerScopeGrant) for value in results)==1
        assert 'VERSION_CONFLICT' in results
    with database.session() as db:assert db.scalar(text('SELECT count(*) FROM weixin_peer_scope_grants'))==1


def test_new_process_finds_fixed_grant_without_refreshing(world):
    service=api();root,database,actor,*_=world
    _,mapping,_=seed(world,[]);value=request(mapping,advance(world,input_revision=1))
    grant=service.refresh_synthetic_peer(actor,mapping.id,value,database=database)
    code='''import sys
from pathlib import Path
from uuid import UUID
from cn_contract import domain as d
from cn_contract.config import load_settings
from cn_contract.persistence import Database
from cn_contract.ops import backup
from cn_contract.weixin_inbox.accounts import find_peer_scope_grant
root=Path(sys.argv[1]);database=Database('sqlite:///'+str(root/'workbench.db'),root/'protected',load_settings(),initialize_schema=False)
backup._mark_storage_flags(database)
try:
 value=find_peer_scope_grant(d.Actor.model_validate_json(sys.argv[2]),UUID(sys.argv[3]),UUID(sys.argv[4]),database=database)
 print(str(value.id)+':'+value.grant_sha256)
finally:database.engine.dispose()
'''
    run=subprocess.run([sys.executable,'-B','-X','utf8','-c',code,str(root),actor.model_dump_json(),
        str(mapping.id),str(value.request_id)],capture_output=True,text=True,timeout=30)
    assert run.returncode==0,run.stderr
    assert run.stdout.strip()==str(grant.id)+':'+grant.grant_sha256


def test_actual_local_docx_upload_then_refresh_allows_prior_pending_material(world):
    from cn_contract.documents.ingest import DOCX_MIME
    from cn_contract.review.synthetic import select_fixture
    service=api();_,database,actor,view,*_=world
    _,mapping,received=seed(world,[message(1,file=True)])
    _,_,path,raw=select_fixture('sales')
    uploaded=attachments.ingest_attachment(actor,view.scope.conversation_id,d.AssistantAttachmentInput(
        request_id=uuid4(),expected_scope=view.scope,original_name=path.name,mime=DOCX_MIME,
        policy=d.AssistantMaterialPolicy(local_processing_accepted=True)),BytesIO(raw),database=database)
    current=attachments.read_materials(actor,view.scope.conversation_id,database=database)
    parsed=attachments.parse_attachment(actor,view.scope.conversation_id,uploaded.attachment.id,
        d.AssistantAttachmentParseInput(request_id=uuid4(),expected_scope=current.scope),database=database)
    current=attachments.read_materials(actor,view.scope.conversation_id,database=database)
    with pytest.raises(ServiceError) as stale:dispatch.dispatch_synthetic_descriptor(actor,received.descriptors[0].id,database=database)
    assert stale.value.code=='VERSION_CONFLICT'
    grant=service.refresh_synthetic_peer(actor,mapping.id,request(mapping,current.scope),database=database)
    assert grant.scope.materials_revision>mapping.scope.materials_revision
    receipt=dispatch.dispatch_synthetic_descriptor(actor,received.descriptors[0].id,database=database)
    with database.session() as db:
        draft=tasks.list_drafts(actor,view.scope.conversation_id,db).items[0]
        assert draft.state=='collecting' and 'media_pending' in draft.blockers
        media=received.descriptors[0].payload.media[0]
        changed=tasks.update_draft(actor,draft.id,d.TaskDraftUpdateInput(expected_revision=draft.revision,
            instruction='独立虚构合同人工审查',media_resolutions=(d.TaskMediaResolutionInput(event_id=receipt.task_event_id,
                media_id=media.media_id,action='resolve',replacement=d.TaskMediaInput(media_id=media.media_id,
                    name=path.name,mime=DOCX_MIME,status='ready',attachment_id=uploaded.attachment.id,
                    sha256=uploaded.attachment.sha256,parse_revision=parsed.parse.revision)),)),db)
        assert changed.state=='collecting' and not changed.blockers
        for table in ('task_executions','assistant_runs','review_runs'):
            assert db.scalar(text('SELECT count(*) FROM '+table))==0


def test_repeated_or_backwards_clock_preserves_grant_poll_dispatch_and_revoke_history(world,monkeypatch):
    from cn_contract.weixin_inbox import ingress
    from cn_contract.weixin_inbox.grant_integrity import validate_peer_scope_grants
    service=api();_,database,actor,*_=world
    account,mapping,received=seed(world,[message(1)])
    clock=mapping.created_at-timedelta(days=1)
    with monkeypatch.context() as patch:
        for module in (accounts,dispatch,ingress):patch.setattr(module,'_at',lambda:clock.isoformat())
        first=service.refresh_synthetic_peer(actor,mapping.id,request(mapping,advance(world,input_revision=1)),database=database)
        receipt=dispatch.dispatch_synthetic_descriptor(actor,received.descriptors[0].id,database=database)
        second=service.refresh_synthetic_peer(actor,mapping.id,request(mapping,advance(world,input_revision=2),first),database=database)
        later=poll(world,account,[message(2)])
        revoked=accounts.revoke_synthetic_peer(actor,mapping.id,d.WeixinRevokeInput(reason='fictional clock revoke'),database=database)
    assert received.created_at<first.created_at<=receipt.created_at<second.created_at<=later.created_at<revoked.revoked_at
    with database.session() as db:assert validate_peer_scope_grants(db,allow_grants=True)==[]


def files(root):return {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_two_qxbak_generations_preserve_grants_and_old_sources_without_reauthorizing(world,tmp_path):
    from cn_contract.weixin_inbox.grant_integrity import validate_peer_scope_grants
    service=api();root,database,actor,*_=world
    account,mapping,received=seed(world,[message(1),message(2,file=True)])
    value=request(mapping,advance(world,input_revision=1))
    grant=service.refresh_synthetic_peer(actor,mapping.id,value,database=database)
    for item in received.descriptors:dispatch.dispatch_synthetic_descriptor(actor,item.id,database=database)
    expected=state(database)
    with database.session() as db:backup._file_references(db)
    original=files(root);archive=tmp_path/'独立虚构重新授权.qxbak'
    workspace_backup.create_workspace_backup(root,archive,PASSPHRASE,data_parent=tmp_path)
    for generation in (1,2):
        result=workspace_backup.restore_workspace_backup(archive,tmp_path/('重新授权恢复'+str(generation)),PASSPHRASE)
        target=Path(result['restored_root']);restored=Database('sqlite:///'+str(target/'workbench.db'),target/'protected',database.settings,initialize_schema=False)
        backup._mark_storage_flags(restored)
        try:
            with restored.session() as db:
                token,_=login(USERNAME,PASSWORD,db);current=authenticate(token,db)
                assert validate_peer_scope_grants(db,allow_grants=True)==[]
                backup._file_references(db)
                payload=db.scalar(text('SELECT payload FROM ops_restore_fences'))
                import json
                assert json.loads(payload)['weixin_reauthorization_enabled'] is False
                for table in ('task_executions','assistant_runs','review_runs'):
                    assert db.scalar(text('SELECT count(*) FROM '+table))==0
            assert state(restored)==expected
            assert service.find_peer_scope_grant(current,mapping.id,value.request_id,database=restored)==grant
            with pytest.raises(ServiceError) as fenced:service.refresh_synthetic_peer(current,mapping.id,value,database=restored)
            assert fenced.value.code=='BLOCKED_LIVE' and state(restored)==expected
            if generation==1:
                archive=tmp_path/'独立虚构重新授权二代.qxbak'
                workspace_backup.create_workspace_backup(target,archive,PASSPHRASE,data_parent=tmp_path)
        finally:restored.engine.dispose()
    assert files(root)==original


@pytest.mark.parametrize('damage',['grant_hash','previous_hash'])
def test_authenticated_damaged_grant_archive_is_not_published(world,tmp_path,monkeypatch,damage):
    service=api();root,database,actor,*_=world
    _,mapping,_=seed(world,[]);value=request(mapping,advance(world,input_revision=1))
    service.refresh_synthetic_peer(actor,mapping.id,value,database=database)
    with database.session() as db:
        triggers=db.execute(text("SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name='weixin_peer_scope_grants'")).all()
        for name,_ in triggers:db.execute(text('DROP TRIGGER '+name))
        column='grant_sha256' if damage=='grant_hash' else 'previous_scope_sha256'
        db.execute(text('UPDATE weixin_peer_scope_grants SET '+column+'=:sha'),{'sha':'0'*64})
        for _,ddl in triggers:db.execute(text(ddl))
    rejected=tmp_path/'拒绝备份.qxbak'
    with pytest.raises(ValueError):workspace_backup.create_workspace_backup(root,rejected,PASSPHRASE,data_parent=tmp_path)
    assert not rejected.exists()
    hostile=tmp_path/'认证但损坏授权.qxbak'
    with monkeypatch.context() as patch:
        patch.setattr(workspace_backup,'_file_references',lambda db:[])
        workspace_backup.create_workspace_backup(root,hostile,PASSPHRASE,data_parent=tmp_path)
    original=files(root);target=tmp_path/'不得发布'
    with pytest.raises(ValueError):workspace_backup.restore_workspace_backup(hostile,target,PASSPHRASE)
    assert not target.exists() or not list(target.iterdir())
    assert files(root)==original
