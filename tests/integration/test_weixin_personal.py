"""Fictional personal-source traffic must share journals without synthetic injection."""
import importlib
import importlib.util
import hashlib
import json
import sqlite3
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from cn_contract import domain as d, schema_migrations, storage_schema
from cn_contract.assistant import service as conversations
from cn_contract.security import ServiceError
from cn_contract.storage_bootstrap import initialize_storage
from cn_contract.task_drafts import service as tasks
from cn_contract.weixin_inbox import accounts, dispatch, ingress, generations, generation_ingress
from tests.integration.test_assistant_storage import workspace
from tests.integration.test_assistant_judge_schema import old_db
from tests.integration.test_weixin_ingress_atomic import world


def personal():
    assert importlib.util.find_spec('cn_contract.weixin_inbox.personal') is not None, 'trusted personal service required'
    return importlib.import_module('cn_contract.weixin_inbox.personal')


def setup(workspace):
    database, actors, _, _ = workspace
    initialize_storage(database)
    actor = actors['lawyer']
    with database.session() as db:
        view = conversations.create_conversation(actor, d.AssistantConversationCreateInput(
            request_id=uuid4(), display_title='本人微信独立虚构测试'), db)
    account, mapping = personal().bind_personal_peer(actor,
        d.WeixinAccountCreateInput(bot_account_id='fictional-personal-bot', initial_cursor='start'),
        sender_peer_id='fictional-personal-peer', expected_scope=view.scope, database=database)
    return database, actors, account, mapping, view


def raw(*ids, peer='fictional-personal-peer', bot='fictional-personal-bot', cursor='next'):
    return json.dumps({'msgs':[dict(message_id=i,from_user_id=peer,to_user_id=bot,
        message_type=1,message_state=2,context_token='FICTIONAL_SECRET_CONTEXT',
        item_list=[dict(type=1,text_item=dict(text='独立虚构审查指令'))]) for i in ids],
        'get_updates_buf':cursor},ensure_ascii=False).encode()


def request(revision=0,cursor='start'):
    return d.WeixinPollInput(request_id=uuid4(),expected_revision=revision,expected_cursor=cursor)


def blocked(callback, code=None):
    with pytest.raises(ServiceError) as error:
        callback()
    if code:
        assert error.value.code == code


def validate(database):
    from cn_contract.ops.backup import _file_references
    with database.session() as db:
        _file_references(db)


@pytest.mark.parametrize('native',[False,True])
def test_schema_expands_only_two_checks_and_preserves_historical_objects(tmp_path,native):
    db=old_db(tmp_path/'old.db','assistant-material-model-v1',native)
    try:
        before=schema_migrations.database_rows(db)
        db.execute("INSERT INTO users VALUES ('fiction','fiction','unused','[]',0)")
        with pytest.raises(sqlite3.IntegrityError,match='CHECK constraint failed'):
            db.execute("INSERT INTO task_channel_bindings VALUES ('binding','conversation','weixin_personal',0,'at')")
        with pytest.raises(sqlite3.IntegrityError,match='CHECK constraint failed'):
            db.execute("INSERT INTO weixin_accounts VALUES ('account','workspace','fiction','bot','weixin_personal','start',0,'start','at',NULL,NULL,NULL)")
        db.commit()
        assert schema_migrations.upgrade_database(db)=='weixin-personal-v1'
        after=schema_migrations.database_rows(db)
        assert storage_schema.identify_schema(after,native=native)=='weixin-personal-v1'
        assert [row for row in before if row[0]!='table' or row[1] not in ('task_channel_bindings','weixin_accounts')]==[
            row for row in after if row[0]!='table' or row[1] not in ('task_channel_bindings','weixin_accounts')]
        assert db.execute('SELECT username FROM users').fetchall()==[('fiction',)]
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
    finally:
        db.close()


def test_personal_roundtrip_deduplicates_and_dispatches_in_order(workspace):
    database,actors,account,mapping,view=setup(workspace)
    service=personal();actor=actors['lawyer']
    assert account.mode=='weixin_personal'
    assert service.bind_personal_peer(actor,d.WeixinAccountCreateInput(
        bot_account_id=account.bot_account_id,initial_cursor='start'),sender_peer_id=mapping.sender_peer_id,
        expected_scope=view.scope,database=database)==(account,mapping)
    first=request();response=raw('1','2')
    poll=service.record_personal_poll(actor,account.id,first,response,database=database)
    assert [v.status for v in poll.descriptors]==['accepted_pending_dispatch']*2
    assert service.record_personal_poll(actor,account.id,first,response,database=database)==poll
    blocked(lambda:service.record_personal_poll(actor,account.id,request(),raw('3'),database=database),'VERSION_CONFLICT')
    blocked(lambda:service.dispatch_personal_descriptor(actor,account.id,poll.descriptors[1].id,database=database),'VERSION_CONFLICT')
    saved=service.dispatch_personal_descriptor(actor,account.id,poll.descriptors[0].id,database=database)
    assert saved.expected_task_cursor==0 and saved.next_task_cursor==1
    assert service.dispatch_personal_descriptor(actor,account.id,poll.descriptors[0].id,database=database)==saved
    service.dispatch_personal_descriptor(actor,account.id,poll.descriptors[1].id,database=database)
    replay=service.record_personal_poll(actor,account.id,request(1,'next'),raw('1'),database=database)
    assert replay.descriptors[0].status=='duplicate'
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM task_drafts'))==1
        assert db.scalar(text('SELECT cursor FROM task_channel_bindings'))==2
        assert 'FICTIONAL_SECRET_CONTEXT' not in str(db.execute(text('SELECT * FROM weixin_inbox_descriptors')).all())
    validate(database)


@pytest.mark.parametrize('operation',['create','bind','refresh','poll','generation_poll','dispatch','generation_dispatch','receive','offline','generation','revoke'])
def test_synthetic_write_paths_reject_personal_sources(workspace,operation):
    database,actors,account,mapping,view=setup(workspace)
    actor=actors['lawyer'];service=personal()
    poll=service.record_personal_poll(actor,account.id,request(),raw('1'),database=database)
    def attempt():
        if operation=='create':
            accounts.create_synthetic_account(actor,d.WeixinAccountCreateInput(bot_account_id=account.bot_account_id,initial_cursor='start'),database=database)
        elif operation=='bind':
            accounts.bind_synthetic_peer(actor,account.id,d.WeixinPeerBindInput(sender_peer_id=mapping.sender_peer_id,
                task_binding_id=mapping.task_binding_id,expected_scope=view.scope),database=database)
        elif operation=='refresh':
            accounts.refresh_synthetic_peer(actor,mapping.id,d.WeixinPeerRefreshInput(request_id=uuid4(),expected_grant_revision=0,
                expected_scope_sha256=mapping.scope_sha256,expected_scope=view.scope,reason='虚构更新'),database=database)
        elif operation in ('poll','generation_poll'):
            (ingress.record_synthetic_poll if operation=='poll' else generation_ingress.record_generation_poll)(
                actor,account.id,request(1,'next'),raw('2'),database=database)
        elif operation=='dispatch':
            dispatch.dispatch_synthetic_descriptor(actor,poll.descriptors[0].id,database=database)
        elif operation=='generation_dispatch':
            from cn_contract.weixin_inbox.generation_dispatch import dispatch_generation_descriptor
            dispatch_generation_descriptor(actor,poll.descriptors[0].id,database=database)
        elif operation=='revoke':
            accounts.revoke_synthetic_account(actor,account.id,d.WeixinRevokeInput(reason='虚构撤销'),database=database)
        elif operation=='generation':
            generations.append_synthetic_generation(actor,mapping.id,d.WeixinPeerGenerationInput(request_id=uuid4(),
                expected_generation=0,expected_previous_generation_sha256=None,expected_previous_scope_sha256=mapping.scope_sha256,
                expected_checkpoint_revision=1,task_binding_id=mapping.task_binding_id,expected_scope=view.scope,
                reason='虚构更新'),database=database)
        else:
            with database.session() as db:
                if operation=='receive':
                    tasks.receive_batch(actor,mapping.task_binding_id,d.TaskInboxBatchInput(
                        expected_cursor=0,next_cursor=1,events=(d.TaskInboxEventInput(event_id='fictional-injected',text='虚构'),)),db)
                else:
                    from cn_contract.weixin_offline import create_offline_scope
                    create_offline_scope(actor,mapping.task_binding_id,bot_account_id=account.bot_account_id,
                        sender_peer_id=mapping.sender_peer_id,upstream_cursor='next',db=db)
    blocked(attempt)
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM task_inbox_events'))==0
        assert db.scalar(text('SELECT checkpoint_revision FROM weixin_accounts'))==1
        assert db.scalar(text('SELECT count(*) FROM weixin_peer_generations'))==0


@pytest.mark.parametrize('change',['owner','workspace','scope','revoked','restore','account'])
def test_personal_identity_scope_and_restore_guards(workspace,change):
    database,actors,account,mapping,view=setup(workspace)
    actor=actors['lawyer'];service=personal()
    if change=='owner':
        actor=actors['reviewer']
    elif change=='workspace':
        with database.session() as db:
            db.execute(text('UPDATE local_workspace_identity SET id=:id'),{'id':str(uuid4())})
    elif change=='scope':
        with database.session() as db:
            db.execute(text('UPDATE assistant_conversations SET binding_revision=binding_revision+1'))
    elif change=='revoked':
        service.revoke_personal_account(actor,account.id,d.WeixinRevokeInput(reason='虚构撤销'),database=database)
    elif change=='restore':
        with database.session() as db:
            db.execute(text("INSERT INTO ops_restore_fences (ref,archive_sha256,manifest_sha256,payload) VALUES (:id,:hash,:hash,'{}')"),
                {'id':str(uuid4()),'hash':'a'*64})
    elif change=='account':
        account=accounts.create_synthetic_account(actor,d.WeixinAccountCreateInput(bot_account_id='other-fictional-bot'),database=database)
    blocked(lambda:service.record_personal_poll(actor,account.id,request(),raw('1'),database=database))
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM weixin_poll_receipts'))==0


def test_personal_coexists_with_existing_synthetic_channel_and_task(workspace):
    database,actors,_,_=workspace
    initialize_storage(database)
    actor=actors['lawyer']
    with database.session() as db:
        view=conversations.create_conversation(actor,d.AssistantConversationCreateInput(request_id=uuid4()),db)
        binding=tasks.create_binding(actor,view.scope.conversation_id,db)
        initial=tasks.receive_batch(actor,binding.id,d.TaskInboxBatchInput(expected_cursor=0,next_cursor=1,
            events=(d.TaskInboxEventInput(event_id='fictional-before',text='独立虚构指令'),)),db)
    account,mapping=personal().bind_personal_peer(actor,d.WeixinAccountCreateInput(
        bot_account_id='fictional-personal-bot',initial_cursor='start'),sender_peer_id='fictional-personal-peer',
        expected_scope=view.scope,database=database)
    poll=personal().record_personal_poll(actor,account.id,request(),raw('1'),database=database)
    saved=personal().dispatch_personal_descriptor(actor,account.id,poll.descriptors[0].id,database=database)
    with database.session() as db:
        assert tasks.create_binding(actor,view.scope.conversation_id,db).id==binding.id
        listing=tasks.list_drafts(actor,view.scope.conversation_id,db)
        assert listing.binding.id==binding.id
        assert len(listing.items)==1 and listing.items[0].id==initial.drafts[0].id
        assert len(listing.items[0].events)==2
        assert saved.task_binding_id!=binding.id
        assert db.scalar(text('SELECT count(*) FROM task_channel_bindings'))==2
    validate(database)


def test_personal_refresh_preserves_scope_history_and_reconnects_same_peer(workspace):
    database,actors,account,mapping,view=setup(workspace)
    actor=actors['lawyer'];service=personal()
    with database.session() as db:
        updated=conversations.save_message(actor,view.scope.conversation_id,d.AssistantMessageInput(
            expected_scope=view.scope,expected_composer_revision=view.composer_revision,
            request_id=uuid4(),content='独立虚构的更新指令'),db)
    blocked(lambda:service.record_personal_poll(actor,account.id,request(),raw('1'),database=database),'VERSION_CONFLICT')
    refresh=d.WeixinPeerRefreshInput(request_id=uuid4(),expected_grant_revision=0,
        expected_scope_sha256=mapping.scope_sha256,expected_scope=updated.scope,reason='本人虚构同目标更新')
    grant=service.refresh_personal_peer(actor,mapping.id,refresh,database=database)
    assert grant.revision==1 and grant.scope.input_revision==1
    assert service.refresh_personal_peer(actor,mapping.id,refresh,database=database)==grant
    assert service.bind_personal_peer(actor,d.WeixinAccountCreateInput(bot_account_id=account.bot_account_id,
        initial_cursor='start'),sender_peer_id=mapping.sender_peer_id,expected_scope=updated.scope,
        database=database)==(account,mapping)
    service.record_personal_poll(actor,account.id,request(),raw('1'),database=database)
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM weixin_peer_scope_grants'))==1
        assert db.scalar(text('SELECT scope_sha256 FROM weixin_peer_bindings'))==mapping.scope_sha256
    validate(database)


@pytest.mark.parametrize('change',['peer','conversation','binding_revision','owner'])
def test_personal_rebind_never_replaces_account_or_fixed_target(workspace,change):
    database,actors,account,mapping,view=setup(workspace)
    actor=actors['lawyer'];scope=view.scope;peer=mapping.sender_peer_id
    if change=='peer':
        peer='other-fictional-peer'
    elif change=='owner':
        actor=actors['reviewer']
    elif change=='conversation':
        with database.session() as db:
            scope=conversations.create_conversation(actor,d.AssistantConversationCreateInput(request_id=uuid4()),db).scope
    else:
        scope=scope.model_copy(update={'binding_revision':scope.binding_revision+1})
    blocked(lambda:personal().bind_personal_peer(actor,d.WeixinAccountCreateInput(
        bot_account_id=account.bot_account_id,initial_cursor='start'),sender_peer_id=peer,
        expected_scope=scope,database=database))
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM weixin_peer_bindings'))==1
        assert db.scalar(text('SELECT count(*) FROM task_channel_bindings'))==1


def test_personal_backup_restore_retains_journals_and_quarantines_writes(tmp_path):
    from pathlib import Path
    from cn_contract.config import load_settings
    from cn_contract.ops import backup, workspace_backup
    from cn_contract.persistence import Database
    from cn_contract.security import authenticate,login
    from cn_contract.web.local_server import initialize_workspace,_worker_lock
    root=tmp_path/'source'
    initialize_workspace(root,'lawyer','fiction123',data_parent=tmp_path)
    database=Database('sqlite:///'+str(root/'workbench.db'),root/'protected',load_settings(),initialize_schema=False)
    backup._mark_storage_flags(database)
    try:
        with database.session() as db:
            token,_=login('lawyer','fiction123',db);actor=authenticate(token,db)
            view=conversations.create_conversation(actor,d.AssistantConversationCreateInput(request_id=uuid4()),db)
        account,mapping=personal().bind_personal_peer(actor,d.WeixinAccountCreateInput(
            bot_account_id='fictional-personal-bot',initial_cursor='start'),sender_peer_id='fictional-personal-peer',
            expected_scope=view.scope,database=database)
        poll=personal().record_personal_poll(actor,account.id,request(),raw('1'),database=database)
        personal().dispatch_personal_descriptor(actor,account.id,poll.descriptors[0].id,database=database)
        with _worker_lock(root):pass
        archive=tmp_path/'personal.qxbak'
        workspace_backup.create_workspace_backup(root,archive,'fictional-long-passphrase',data_parent=tmp_path)
        restored=workspace_backup.restore_workspace_backup(archive,tmp_path/'restored','fictional-long-passphrase')
        restored_root=Path(restored['restored_root'])
        copy=Database('sqlite:///'+str(restored_root/'workbench.db'),restored_root/'protected',database.settings,initialize_schema=False)
        backup._mark_storage_flags(copy)
        try:
            validate(copy)
            with copy.session() as db:
                assert db.scalar(text('SELECT mode FROM weixin_accounts'))=='weixin_personal'
                assert db.scalar(text('SELECT channel FROM task_channel_bindings'))=='weixin_personal'
                assert db.scalar(text('SELECT count(*) FROM weixin_dispatch_receipts'))==1
                token,_=login('lawyer','fiction123',db);actor=authenticate(token,db)
            blocked(lambda:personal().record_personal_poll(actor,account.id,request(1,'next'),raw('2'),database=copy),'BLOCKED_LIVE')
        finally:copy.engine.dispose()
    finally:database.engine.dispose()


@pytest.mark.parametrize('native,expected',[(False,'ecb7e67c9a9d9a99361278be1d90b3fb7a7bd64de017e98e043e6c50775902b3'),
    (True,'84b285cfae564f8678a8cb2d13c142198209c7857813afd82cf8ac8ea06dfe74')])
def test_immediate_predecessor_fingerprint_remains_frozen(native,expected):
    rows=storage_schema.schema_rows('assistant-material-model-v1',native=native)
    assert hashlib.sha256(json.dumps(rows,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()==expected


@pytest.mark.parametrize('change',['drop_trigger','unknown_column'])
def test_personal_services_and_initialization_refuse_damaged_schema(workspace,change):
    database,actors,account,_,_=setup(workspace)
    with database.session() as db:
        db.execute(text('DROP TRIGGER immutable_weixin_inbox_descriptors_update' if change=='drop_trigger'
            else 'ALTER TABLE weixin_poll_receipts ADD COLUMN unexpected TEXT'))
    blocked(lambda:personal().record_personal_poll(actors['lawyer'],account.id,request(),raw('1'),database=database),'VERSION_CONFLICT')
    with pytest.raises(ValueError,match='DATABASE_SCHEMA_MISMATCH'):
        initialize_storage(database)


def test_personal_migration_failure_rolls_back_every_object(tmp_path,monkeypatch):
    db=old_db(tmp_path/'rollback.db','assistant-material-model-v1',True)
    before=schema_migrations.database_rows(db)
    original=schema_migrations.statements_for
    monkeypatch.setattr(schema_migrations,'statements_for',lambda version:
        (*original(version),'INVALID SQL') if version=='weixin-personal-v1' else original(version))
    try:
        with pytest.raises(sqlite3.Error):schema_migrations.upgrade_database(db)
        assert schema_migrations.database_rows(db)==before
        assert db.execute('PRAGMA foreign_keys').fetchone()==(1,)
        assert not db.in_transaction
    finally:db.close()


def test_personal_migration_preserves_complete_legacy_synthetic_journals(tmp_path):
    from cn_contract.config import load_settings
    from cn_contract.persistence import Database
    from cn_contract.security import provision_user,login,authenticate
    from cn_contract.storage_bootstrap import mark_storage_initialized
    from tests.helpers.synthetic_weixin_inbox import seed_history
    path=tmp_path/'old.sqlite'
    old_db(path,'assistant-material-model-v1',True).close()
    database=Database('sqlite:///'+str(path),tmp_path/'protected',load_settings(),initialize_schema=False)
    mark_storage_initialized(database)
    try:
        with database.session() as db:
            db.execute(text('INSERT INTO local_workspace_identity VALUES (:id)'),{'id':str(uuid4())})
            provision_user('lawyer','fiction123',{d.Role.HANDLING_LAWYER},db,local_workbench_password=True)
            token,_=login('lawyer','fiction123',db);actor=authenticate(token,db)
        seed_history(database,actor)
        names=('task_channel_bindings','weixin_accounts','weixin_peer_bindings','weixin_poll_receipts','weixin_inbox_descriptors')
        with database.session() as db:
            before={name:db.execute(text('SELECT * FROM '+name+' ORDER BY rowid')).all() for name in names}
        connection=sqlite3.connect(path)
        try:assert schema_migrations.upgrade_database(connection)=='weixin-personal-v1'
        finally:connection.close()
        with database.session() as db:
            assert {name:db.execute(text('SELECT * FROM '+name+' ORDER BY rowid')).all() for name in names}==before
            with pytest.raises(IntegrityError,match='IMMUTABLE_RECORD'):
                db.execute(text('DELETE FROM weixin_accounts'))
        validate(database)
    finally:database.engine.dispose()


def test_task_list_collects_unassigned_sources_from_both_channels(workspace):
    database,actors,account,mapping,view=setup(workspace);actor=actors['lawyer']
    with database.session() as db:
        binding=tasks.create_binding(actor,view.scope.conversation_id,db)
        tasks.receive_batch(actor,binding.id,d.TaskInboxBatchInput(expected_cursor=0,next_cursor=1,events=(
            d.TaskInboxEventInput(event_id='fictional-a',text='虚构任务甲',start_new=True),
            d.TaskInboxEventInput(event_id='fictional-b',text='虚构任务乙',start_new=True),
            d.TaskInboxEventInput(event_id='fictional-ambiguous',text='虚构归属不明'))),db)
    poll=personal().record_personal_poll(actor,account.id,request(),raw('1'),database=database)
    personal().dispatch_personal_descriptor(actor,account.id,poll.descriptors[0].id,database=database)
    with database.session() as db:
        listing=tasks.list_drafts(actor,view.scope.conversation_id,db)
        assert listing.binding.id==binding.id
        assert len(listing.items)==2
        assert {event.binding_id for event in listing.unassigned_events}=={binding.id,mapping.task_binding_id}
    validate(database)


def test_personal_dispatch_cannot_use_another_personal_account(workspace):
    database,actors,account,_,view=setup(workspace);actor=actors['lawyer']
    poll=personal().record_personal_poll(actor,account.id,request(),raw('1'),database=database)
    with database.session() as db:
        other=conversations.create_conversation(actor,d.AssistantConversationCreateInput(request_id=uuid4()),db)
    second,_=personal().bind_personal_peer(actor,d.WeixinAccountCreateInput(bot_account_id='fictional-second-bot'),
        sender_peer_id='fictional-personal-peer',expected_scope=other.scope,database=database)
    blocked(lambda:personal().dispatch_personal_descriptor(actor,second.id,poll.descriptors[0].id,database=database),'CROSS_MATTER_DENIED')
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM task_inbox_events'))==0


@pytest.mark.parametrize('damage',['personal_generation','personal_target'])
def test_personal_sources_cannot_hide_in_coherent_synthetic_generation_history(world,damage):
    from cn_contract.weixin_inbox.generation_integrity import validate_peer_generations
    from tests.helpers.synthetic_weixin_provenance import chain
    from tests.integration.test_weixin_dispatch_integrity import corrupt
    h=chain(world);database=h['database']
    with database.session() as db:
        assert validate_peer_generations(db,allow_generations=True)==[]
        original=db.execute(text('SELECT * FROM weixin_peer_generations ORDER BY generation')).all()
        if damage=='personal_generation':
            corrupt(db,"UPDATE weixin_accounts SET mode='weixin_personal'")
            corrupt(db,"UPDATE task_channel_bindings SET channel='weixin_personal'")
        else:
            corrupt(db,"UPDATE task_channel_bindings SET channel='weixin_personal' WHERE id=:id",
                {'id':str(h['first'].task_binding_id)})
        # Source-mode/channel fields are outside the generation payload: all its
        # valid hashes and predecessor links deliberately remain byte-for-byte intact.
        assert db.execute(text('SELECT * FROM weixin_peer_generations ORDER BY generation')).all()==original
        with pytest.raises(ValueError,match='WEIXIN_GENERATION_INTEGRITY'):
            validate_peer_generations(db,allow_generations=True)
