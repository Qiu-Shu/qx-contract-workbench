"""Real authenticated synthetic archives preserve generations but never resume them."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3

import pytest
from sqlalchemy import text

from cn_contract.config import canonical_json
from cn_contract.ops import backup, workspace_backup
from cn_contract.persistence import Database
from cn_contract.record_codec import sha
from cn_contract.security import ServiceError, authenticate, login
from cn_contract.weixin_inbox import accounts, conversation, dispatch
from cn_contract.weixin_inbox.generation_integrity import validate_peer_generations
from tests.helpers.legacy_assistant_backup import USERNAME, PASSWORD, PASSPHRASE, write_old_cnbak
from tests.helpers.synthetic_operations import keys
from tests.helpers.synthetic_weixin_generations import append_generation, setup_history, state
from tests.integration.test_weixin_dispatch import message, poll
from tests.integration.test_weixin_dispatch_integrity import corrupt
from tests.integration.test_weixin_ingress_atomic import world


def files(root):
    return {path.relative_to(root).as_posix():path.read_bytes() for path in root.rglob('*') if path.is_file()}


def chain(world):
    history=setup_history(world)
    old=state(history['database'],generations=False)
    first=append_generation(history)
    second=append_generation(history,first)
    assert state(history['database'],generations=False)==old
    return history,first,second


def test_two_actual_qxbak_generations_preserve_old_receipts_and_never_resume(world,tmp_path):
    h,first,second=chain(world);root=h['root'];database=h['database']
    expected=state(database)
    with database.session() as db:
        assert validate_peer_generations(db,allow_generations=True)==[]
        backup._file_references(db)
    original=files(root);archive=tmp_path/'独立合成目标代际.qxbak'
    workspace_backup.create_workspace_backup(root,archive,PASSPHRASE,data_parent=tmp_path)
    for number in (1,2):
        result=workspace_backup.restore_workspace_backup(archive,tmp_path/('代际恢复'+str(number)),PASSPHRASE)
        target=Path(result['restored_root'])
        restored=Database('sqlite:///'+str(target/'workbench.db'),target/'protected',database.settings,initialize_schema=False)
        backup._mark_storage_flags(restored)
        try:
            with restored.session() as db:
                token,_=login(USERNAME,PASSWORD,db);actor=authenticate(token,db)
                assert validate_peer_generations(db,allow_generations=True)==[]
                backup._file_references(db)
                fence=json.loads(db.scalar(text('SELECT payload FROM ops_restore_fences')))
                assert fence['weixin_generation_enabled'] is False
                for name in ('assistant_runs','review_runs','task_executions'):
                    assert db.scalar(text('SELECT count(*) FROM '+name))==0
                saved=db.execute(text('SELECT scope_json,generation_sha256 FROM weixin_peer_generations ORDER BY generation')).all()
                assert saved==[(canonical_json(value.scope.model_dump(mode='json')),value.generation_sha256) for value in (first,second)]
            assert state(restored)==expected
            projection=conversation.read_authorization(actor,h['view'].scope.conversation_id,database=restored)
            assert projection.state=='restored_blocked'
            restored_world=(target,restored,actor,h['view'],h['binding'])
            actions=(lambda:poll(restored_world,h['account'],[message(10)]),
                lambda:dispatch.dispatch_synthetic_descriptor(actor,h['received'].descriptors[1].id,database=restored),
                lambda:accounts.refresh_synthetic_peer(actor,h['mapping'].id,h['grant_request'],database=restored))
            for operation in actions:
                with pytest.raises(ServiceError) as failure:operation()
                assert failure.value.code=='BLOCKED_LIVE'
                assert state(restored)==expected
            if number==1:
                archive=tmp_path/'独立合成目标代际二代.qxbak'
                workspace_backup.create_workspace_backup(target,archive,PASSPHRASE,data_parent=tmp_path)
        finally:restored.engine.dispose()
    assert files(root)==original


def test_nonempty_generations_require_full_native_archive(world,tmp_path):
    h,_,_=chain(world);database=h['database']
    with database.session() as db,pytest.raises(ServiceError) as failure:
        validate_peer_generations(db)
    assert failure.value.code=='DATA_POLICY_UNAPPROVED'
    candidate=tmp_path/'nonnative.db'
    with closing(sqlite3.connect(database.engine.url.database)) as source,closing(sqlite3.connect(candidate)) as copy:
        source.backup(copy);copy.execute('DROP TABLE local_workspace_identity');copy.commit()
    ordinary=Database('sqlite:///'+str(candidate),tmp_path/'ordinary-protected',database.settings,initialize_schema=False)
    try:
        with ordinary.session() as db,pytest.raises(ValueError,match='WEIXIN_GENERATION_INTEGRITY'):
            validate_peer_generations(db,allow_generations=True)
    finally:ordinary.engine.dispose()


def test_authenticated_ordinary_archive_cannot_smuggle_generations(world,tmp_path,monkeypatch):
    h,_,_=chain(world);database=h['database'];candidate=tmp_path/'ordinary.db'
    with closing(sqlite3.connect(database.engine.url.database)) as source,closing(sqlite3.connect(candidate)) as copy:
        source.backup(copy);copy.execute('DROP TABLE local_workspace_identity');copy.commit()
    ordinary=Database('sqlite:///'+str(candidate),tmp_path/'ordinary-protected',database.settings,initialize_schema=False)
    backup._mark_storage_flags(ordinary)
    archive=tmp_path/'认证但非原生.cnbak'
    try:
        # Only hostile fixture assembly bypasses validation. Restore is the real boundary.
        with monkeypatch.context() as patch:
            patch.setattr(backup,'_collect_files',lambda db:({},[]))
            write_old_cnbak(ordinary,archive)
    finally:ordinary.engine.dispose()
    before=archive.read_bytes();destination=tmp_path/'不应发布普通恢复'
    with pytest.raises((ValueError,ServiceError)):
        backup.restore_backup(archive,key_resolver=keys(),restore_parent=destination,settings=database.settings)
    assert not destination.exists() or not list(destination.iterdir())
    assert archive.read_bytes()==before


def rehash_chain(db):
    previous=None
    for original in db.execute(text('SELECT * FROM weixin_peer_generations ORDER BY generation')).mappings().all():
        value=dict(original);value.pop('generation_sha256');value['scope']=json.loads(value.pop('scope_json'))
        value['scope_sha256']=sha(value['scope'])
        if previous is not None:value['previous_generation_sha256']=previous
        previous=sha(value)
        corrupt(db,'UPDATE weixin_peer_generations SET scope_sha256=:scope,previous_generation_sha256=:prior,generation_sha256=:hash WHERE id=:id',
            {'scope':value['scope_sha256'],'prior':value['previous_generation_sha256'],'hash':previous,'id':value['id']})


@pytest.mark.parametrize('damage',['previous_scope','checkpoint','root_target'])
def test_rehashed_hostile_generation_archive_is_rejected_without_publication(world,tmp_path,monkeypatch,damage):
    h,first,_=chain(world);database=h['database'];root=h['root']
    with database.session() as db:
        if damage=='previous_scope':
            corrupt(db,'UPDATE weixin_peer_generations SET previous_scope_sha256=:value WHERE generation=1',{'value':'0'*64})
        elif damage=='checkpoint':
            corrupt(db,'UPDATE weixin_peer_generations SET checkpoint_revision=1')
        else:
            corrupt(db,'UPDATE weixin_peer_generations SET task_binding_id=:binding,scope_json=:scope WHERE generation=1',
                {'binding':str(h['binding'].id),'scope':canonical_json(h['grant'].scope.model_dump(mode='json'))})
        rehash_chain(db)
    refused=tmp_path/'不得创建损坏备份.qxbak'
    with pytest.raises(ValueError,match='WEIXIN_GENERATION_INTEGRITY'):
        workspace_backup.create_workspace_backup(root,refused,PASSPHRASE,data_parent=tmp_path)
    assert not refused.exists()
    hostile=tmp_path/'认证但损坏代际.qxbak'
    with monkeypatch.context() as patch:
        patch.setattr(workspace_backup,'_file_references',lambda db:[])
        workspace_backup.create_workspace_backup(root,hostile,PASSPHRASE,data_parent=tmp_path)
    original=files(root);raw=hostile.read_bytes();destination=tmp_path/'不得发布目标代际'
    with pytest.raises(ValueError,match='WEIXIN_GENERATION_INTEGRITY'):
        workspace_backup.restore_workspace_backup(hostile,destination,PASSPHRASE)
    assert not destination.exists() or not list(destination.iterdir())
    assert hostile.read_bytes()==raw and files(root)==original
