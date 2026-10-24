"""Independent synthetic archive history rejects coherent-looking provenance tampering."""
import importlib
import importlib.util
import json
import sqlite3
from contextlib import closing
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.config import load_settings
from cn_contract.config import canonical_json
from cn_contract.ops import backup
from cn_contract.persistence import Database
from cn_contract.record_codec import sha
from cn_contract.security import ServiceError, authenticate, login, provision_user
from cn_contract.web.local_server import initialize_workspace
from cn_contract.storage_schema import VERSIONS, schema_rows
from tests.helpers.legacy_assistant_backup import PASSWORD, USERNAME
from tests.helpers.synthetic_weixin_inbox import seed_history, snapshot


def validator():
    assert importlib.util.find_spec('cn_contract.weixin_inbox.integrity') is not None, 'D2a needs archive record integrity validation'
    return importlib.import_module('cn_contract.weixin_inbox.integrity').validate_weixin_records


@pytest.fixture
def history(tmp_path):
    root=tmp_path/'独立虚构微信历史'
    initialize_workspace(root,USERNAME,PASSWORD,data_parent=tmp_path)
    database=Database('sqlite:///'+str(root/'workbench.db'),root/'protected',load_settings(),initialize_schema=False)
    backup._mark_storage_flags(database)
    try:
        with database.session() as db:
            token,_=login(USERNAME,PASSWORD,db)
            actor=authenticate(token,db)
            other=provision_user('独立虚构其他律师','synthetic-password', {d.Role.HANDLING_LAWYER},db)
        yield database,seed_history(database,actor),other
    finally:
        database.engine.dispose()


def corrupt(db, sql, values=()):
    triggers=db.execute(text("SELECT name,sql FROM sqlite_master WHERE type='trigger' AND name LIKE '%weixin%'" )).all()
    for name,_ in triggers: db.execute(text('DROP TRIGGER '+name))
    db.execute(text('PRAGMA ignore_check_constraints=ON'))
    try:
        db.execute(text(sql),values)
    finally:
        db.execute(text('PRAGMA ignore_check_constraints=OFF'))
        for _,statement in triggers: db.execute(text(statement))


def rehash_poll(db, identifier):
    poll=dict(db.execute(text('SELECT * FROM weixin_poll_receipts WHERE id=:id'),{'id':str(identifier)}).mappings().one())
    items=[]
    for row in db.execute(text('SELECT * FROM weixin_inbox_descriptors WHERE poll_id=:id ORDER BY ordinal'),{'id':str(identifier)}).mappings():
        item=dict(row); raw=item.pop('payload_json'); item['payload']=json.loads(raw) if raw is not None else None
        items.append(item)
    poll.pop('receipt_sha256'); poll['descriptors']=items
    corrupt(db,'UPDATE weixin_poll_receipts SET receipt_sha256=:sha WHERE id=:id',
        {'sha':sha(poll),'id':str(identifier)})


def test_complete_history_has_exact_outcomes_without_business_dispatch(history):
    database,seed,_=history
    with database.session() as db:
        before=snapshot(db)
        assert validator()(db,allow_inbox=True) == []
        assert snapshot(db)==before
        assert tuple(value.descriptor_count for value in seed['receipts']) == (4,4,0)
        assert db.scalar(text('SELECT count(*) FROM task_inbox_events')) == 0
        assert db.scalar(text('SELECT count(*) FROM task_drafts')) == 0
        assert db.scalar(text('SELECT sum(cursor) FROM task_channel_bindings')) == 0
        assert db.scalar(text('SELECT count(*) FROM assistant_runs')) == 0


def test_nonempty_records_require_whole_workspace_archive(history):
    database,_,_=history
    with database.session() as db:
        with pytest.raises(ServiceError) as denied: validator()(db)
        assert denied.value.code == 'DATA_POLICY_UNAPPROVED' and denied.value.status_code == 409


@pytest.mark.parametrize('damage',[
    'workspace','owner','scope_hash','scope_identity','scope_future_revision','mapping_owner',
    'initial_cursor','checkpoint_revision','checkpoint_cursor','poll_gap','poll_cursor',
    'poll_count','ordinal_gap','receipt_hash','payload_noncanonical','payload_task','payload_file_capability',
    'source_namespace','source_message_id','mapping_peer','duplicate_hash','duplicate_future',
    'prior_chain','conflict_hash','revived_blocked','revoked_accepted','blocked_payload','account_revoked_accepted',
])
def test_corrupt_history_is_rejected_after_rehashing_public_receipts(history,damage):
    database,seed,other=history
    first,second=seed['receipts'][:2]
    accepted=first.descriptors[0]
    with database.session() as db:
        if damage=='workspace':
            corrupt(db,'UPDATE weixin_accounts SET workspace_id=:value',{'value':str(uuid4())})
        elif damage=='owner':
            corrupt(db,'UPDATE weixin_accounts SET owner_id=:value',{'value':str(other)})
        elif damage.startswith('scope_'):
            row=db.execute(text('SELECT * FROM weixin_peer_bindings WHERE id=:id'),{'id':str(seed['mapping_ids'][0])}).mappings().one()
            value=json.loads(row['scope_json'])
            if damage=='scope_hash': value['input_revision']+=1
            elif damage=='scope_identity': value['conversation_id']=str(seed['conversation_ids'][1])
            else: value['binding_revision']+=100
            raw=canonical_json(value)
            corrupt(db,'UPDATE weixin_peer_bindings SET scope_json=:raw,scope_sha256=:sha WHERE id=:id',
                {'raw':raw,'sha':row['scope_sha256'] if damage=='scope_hash' else sha(value),'id':str(seed['mapping_ids'][0])})
        elif damage=='mapping_owner':
            db.execute(text('UPDATE assistant_conversations SET owner_id=:owner WHERE id=:id'),
                {'owner':str(other),'id':str(seed['conversation_ids'][0])})
        elif damage in ('initial_cursor','checkpoint_revision','checkpoint_cursor'):
            column={'initial_cursor':'initial_cursor','checkpoint_revision':'checkpoint_revision','checkpoint_cursor':'upstream_cursor'}[damage]
            corrupt(db,'UPDATE weixin_accounts SET '+column+'=:value',{'value':99 if damage=='checkpoint_revision' else 'opaque:forged'})
        elif damage.startswith('poll_') or damage=='receipt_hash':
            column,value={'poll_gap':('next_revision',9),'poll_cursor':('expected_cursor','opaque:forged'),
                'poll_count':('descriptor_count',0),'receipt_hash':('receipt_sha256','e'*64)}[damage]
            corrupt(db,'UPDATE weixin_poll_receipts SET '+column+'=:value WHERE id=:id',{'value':value,'id':str(second.id)})
        elif damage.startswith('payload_'):
            value=accepted.payload.model_dump(mode='json')
            if damage=='payload_task': value['task_id']=str(uuid4())
            elif damage=='payload_file_capability': value['media'][0]['attachment_id']=str(uuid4())
            raw=json.dumps(value,ensure_ascii=False) if damage=='payload_noncanonical' else canonical_json(value)
            corrupt(db,'UPDATE weixin_inbox_descriptors SET payload_json=:value WHERE id=:id',{'value':raw,'id':str(accepted.id)})
        elif damage in ('source_namespace','source_message_id','mapping_peer','ordinal_gap','blocked_payload'):
            column,value={'source_namespace':('source_event_id','wx1:'+'0'*64),
                'source_message_id':('upstream_message_id','000101'),
                'mapping_peer':('mapping_id',str(seed['mapping_ids'][1])),
                'ordinal_gap':('ordinal',99),
                'blocked_payload':('payload_json','{}')}[damage]
            identifier=first.descriptors[2].id if damage=='blocked_payload' else accepted.id
            corrupt(db,'UPDATE weixin_inbox_descriptors SET '+column+'=:value WHERE id=:id',{'value':value,'id':str(identifier)})
        elif damage in ('duplicate_hash','duplicate_future','prior_chain','conflict_hash'):
            target=second.descriptors[1] if damage=='conflict_hash' else second.descriptors[0]
            column,value={'duplicate_hash':('source_sha256','f'*64),
                'duplicate_future':('prior_descriptor_id',str(second.descriptors[3].id)),
                'prior_chain':('prior_descriptor_id',str(second.descriptors[1].id)),
                'conflict_hash':('source_sha256',accepted.source_sha256)}[damage]
            corrupt(db,'UPDATE weixin_inbox_descriptors SET '+column+'=:value WHERE id=:id',{'value':value,'id':str(target.id)})
        elif damage=='revived_blocked':
            target=second.descriptors[3]
            from cn_contract.weixin_offline import event_id
            peer=accepted.sender_peer_id
            source=event_id(seed['account'].bot_account_id,peer,'105')
            value=accepted.payload.model_dump(mode='json')
            value['event_id']=source
            for index,item in enumerate(value['media']): item['media_id']=source+':'+str(index)
            corrupt(db,"""UPDATE weixin_inbox_descriptors SET status='accepted_pending_dispatch',reason=NULL,
                sender_peer_id=:peer,upstream_message_id='105',source_event_id=:event,mapping_id=:mapping,
                source_sha256=:sha,payload_json=:value WHERE id=:id""",
                {'peer':peer,'event':source,'mapping':str(accepted.mapping_id),
                 'sha':target.source_sha256,'value':canonical_json(value),'id':str(target.id)})
            # This source was blocked in an earlier poll; a later mapping cannot revive it.
            corrupt(db,"""UPDATE weixin_inbox_descriptors SET sender_peer_id=:peer,upstream_message_id='105',
                source_event_id=:event,source_sha256=:sha WHERE id=:id""",
                {'peer':peer,'event':source,'sha':target.source_sha256,'id':str(first.descriptors[2].id)})
        elif damage=='revoked_accepted':
            corrupt(db,'UPDATE weixin_peer_bindings SET revoked_at=:at WHERE id=:id',
                {'at':seed['mappings'][1].created_at.isoformat(),'id':str(seed['mapping_ids'][1])})
        elif damage=='account_revoked_accepted':
            corrupt(db,'UPDATE weixin_accounts SET revoked_at=:at,revoked_by=:by,revoke_reason=:reason',
                {'at':seed['account'].created_at.isoformat(),'by':str(seed['actor'].user_id),'reason':'independent-fiction'})
        if damage!='receipt_hash':
            rehash_poll(db,first.id)
            rehash_poll(db,second.id)
        with pytest.raises(ValueError,match='WEIXIN_INBOX_INTEGRITY'): validator()(db,allow_inbox=True)


def test_historical_mapping_survives_later_scope_change_and_revocation(history):
    database,seed,_=history
    with database.session() as db:
        db.execute(text('''UPDATE assistant_conversations SET binding_revision=binding_revision+1,
            input_revision=input_revision+1,materials_revision=materials_revision+1,
            archived_at=:at WHERE id=:id'''),
            {'at':seed['account'].created_at.isoformat(),'id':str(seed['conversation_ids'][0])})
        assert validator()(db,allow_inbox=True)==[]


def test_unknown_schema_and_partial_family_fail_closed(history):
    database,_,_=history
    with database.session() as db:
        db.execute(text('CREATE TABLE unexpected_weixin_private (body TEXT)'))
        with pytest.raises(ValueError,match='WEIXIN_INBOX_INTEGRITY'): validator()(db,allow_inbox=True)


@pytest.mark.parametrize('version',VERSIONS)
@pytest.mark.parametrize('native',[False,True])
def test_known_old_schemas_and_empty_current_family_remain_readable(tmp_path,version,native):
    path=tmp_path/'independent-empty.sqlite'
    with closing(sqlite3.connect(path)) as connection:
        connection.execute('BEGIN')
        for kind in ('table','index','trigger'):
            for row in schema_rows(version,native=native):
                if row[0]==kind and row[3] is not None: connection.execute(row[3])
        connection.commit()
    database=Database('sqlite:///'+str(path),tmp_path/'protected',load_settings(),initialize_schema=False)
    try:
        with database.session() as db:
            assert validator()(db)==[]
            assert validator()(db,allow_inbox=True)==[]
    finally:
        database.engine.dispose()


def test_same_poll_repeat_can_only_reference_a_smaller_original_ordinal(history):
    from tests.helpers.synthetic_weixin_inbox import insert
    database,seed,_=history
    first=seed['receipts'][0]
    original=first.descriptors[0]
    repeat=d.WeixinInboxDescriptor(id=uuid4(),poll_id=first.id,ordinal=5,
        sender_peer_id=original.sender_peer_id,upstream_message_id=original.upstream_message_id,
        source_event_id=original.source_event_id,source_sha256=original.source_sha256,
        status='duplicate',reason='replayed',prior_descriptor_id=original.id)
    with database.session() as db:
        row=repeat.model_dump(mode='json',exclude={'payload'}); row['payload_json']=None
        insert(db,'weixin_inbox_descriptors',row)
        corrupt(db,'UPDATE weixin_poll_receipts SET descriptor_count=5 WHERE id=:id',{'id':str(first.id)})
        rehash_poll(db,first.id)
        assert validator()(db,allow_inbox=True)==[]


@pytest.mark.parametrize('reference_kind',['cross_peer_future','cross_account','same_peer','unknown'])
def test_known_reply_sources_stay_in_the_exact_account_peer_mapping(history,reference_kind):
    from cn_contract.weixin_offline import event_id
    database,seed,_=history
    if reference_kind=='cross_account':
        other=seed_history(database,seed['actor'],bot_account_id='synthetic-d2a-other-bot')
        reference=other['receipts'][0].descriptors[0].source_event_id
    elif reference_kind=='cross_peer_future':
        # The different peer comes later in this same poll, beyond a seen-only index.
        reference=seed['receipts'][0].descriptors[1].source_event_id
    elif reference_kind=='same_peer':
        reference=seed['receipts'][0].descriptors[0].source_event_id
    else:
        reference=event_id(seed['account'].bot_account_id,'synthetic-d2a-peer-1','999')
    accepted=seed['receipts'][0].descriptors[0]
    payload=accepted.payload.model_dump(mode='json'); payload['reply_to_event_id']=reference
    with database.session() as db:
        corrupt(db,'UPDATE weixin_inbox_descriptors SET payload_json=:raw WHERE id=:id',
            {'raw':canonical_json(payload),'id':str(accepted.id)})
        rehash_poll(db,accepted.poll_id)
        if reference_kind.startswith('cross_'):
            with pytest.raises(ValueError,match='WEIXIN_INBOX_INTEGRITY'): validator()(db,allow_inbox=True)
        else:
            assert validator()(db,allow_inbox=True)==[]
