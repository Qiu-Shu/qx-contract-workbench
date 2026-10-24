"""Service-created generations retain fixed metadata across native recovery."""
import json
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import attachments,service
from cn_contract.ops import backup,workspace_backup
from cn_contract.persistence import Database
from cn_contract.security import ServiceError,authenticate,login
from cn_contract.weixin_inbox import accounts
from tests.helpers.legacy_assistant_backup import USERNAME,PASSWORD,PASSPHRASE
from tests.helpers.synthetic_weixin_generation_service import api,chain,find,request
from tests.helpers.synthetic_weixin_generations import state
from tests.integration.test_weixin_ingress_atomic import world


def files(root):
    return {path.relative_to(root).as_posix():path.read_bytes() for path in root.rglob('*') if path.is_file()}


def test_real_service_generations_survive_two_qxbak_restores_with_find_only(world,tmp_path):
    h,first,second=chain(world);database=h['database'];root=h['root'];expected=state(database)
    with database.session() as db:backup._file_references(db)
    original=files(root);archive=tmp_path/'服务追加代际.qxbak'
    workspace_backup.create_workspace_backup(root,archive,PASSPHRASE,data_parent=tmp_path)
    for number in (1,2):
        result=workspace_backup.restore_workspace_backup(archive,tmp_path/('服务代际恢复'+str(number)),PASSPHRASE)
        target=Path(result['restored_root']);restored=Database('sqlite:///'+str(target/'workbench.db'),target/'protected',
            database.settings,initialize_schema=False)
        backup._mark_storage_flags(restored)
        try:
            with restored.session() as db:
                token,_=login(USERNAME,PASSWORD,db);actor=authenticate(token,db)
                backup._file_references(db)
                fence=json.loads(db.scalar(text('SELECT payload FROM ops_restore_fences')))
                assert fence['weixin_generation_enabled'] is False
                assert db.scalar(text('SELECT count(*) FROM assistant_runs'))==0
                for name in ('assistant_model_attempts','review_runs','task_executions'):
                    assert db.scalar(text('SELECT count(*) FROM '+name))==0
            for saved in (first,second):
                before=state(restored)
                assert api().find_peer_generation(actor,h['mapping'].id,saved.request_id,database=restored)==saved
                assert state(restored)==before==expected
            value=request(h,first)
            with pytest.raises(ServiceError) as failure:
                api().append_synthetic_generation(actor,h['mapping'].id,value,database=restored)
            assert failure.value.code=='BLOCKED_LIVE' and state(restored)==expected
            if number==1:
                archive=tmp_path/'服务追加代际二代.qxbak'
                workspace_backup.create_workspace_backup(target,archive,PASSPHRASE,data_parent=tmp_path)
        finally:restored.engine.dispose()
    assert files(root)==original


@pytest.mark.parametrize('revoke',['peer','account'])
def test_find_after_scope_growth_archive_and_logical_revocation_is_read_only(world,revoke):
    h,first,second=chain(world);database=h['database'];actor=h['actor']
    for cid in (h['view'].scope.conversation_id,first.scope.conversation_id):
        with database.session() as db:current=service.read_conversation(actor,cid,db)
        assert attachments.select_materials(actor,cid,d.AssistantMaterialSelectionInput(
            request_id=uuid4(),expected_scope=current.scope,items=()),database=database)==1
    function=accounts.revoke_synthetic_peer if revoke=='peer' else accounts.revoke_synthetic_account
    function(actor,h['mapping'].id if revoke=='peer' else h['account'].id,
        d.WeixinRevokeInput(reason='独立合成固定记录查询撤权'),database=database)
    with database.session() as db:
        for cid in (h['view'].scope.conversation_id,first.scope.conversation_id):
            db.execute(text('UPDATE assistant_conversations SET archived_at=:at WHERE id=:id'),
                {'at':accounts._at(),'id':str(cid)})
        audit_count=db.scalar(text('SELECT count(*) FROM audit_events'))
    before=state(database)
    assert find(h,first.request_id)==first and find(h,second.request_id)==second
    assert state(database)==before
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM audit_events'))==audit_count
        for name in ('assistant_runs','assistant_model_attempts','review_runs','task_executions'):
            assert db.scalar(text('SELECT count(*) FROM '+name))==0


def test_find_ignores_later_public_user_source_revision_without_running_queued_work(world):
    h,first,second=chain(world);database=h['database'];actor=h['actor'];target=h['targets'][0][0]
    with database.session() as db:
        queued=service.save_message(actor,target.scope.conversation_id,d.AssistantMessageInput(
            request_id=uuid4(),expected_scope=target.scope,expected_composer_revision=target.composer_revision,
            content='独立合成后续消息；仅保存来源，不执行模型'),db)
        assert queued.state=='queued' and queued.scope.input_revision==1
    before=state(database)
    assert find(h,first.request_id)==first and find(h,second.request_id)==second
    assert state(database)==before
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM assistant_runs'))==1
        assert db.scalar(text('SELECT state FROM assistant_runs'))=='queued'
        for name in ('assistant_model_attempts','review_runs','task_executions'):
            assert db.scalar(text('SELECT count(*) FROM '+name))==0
