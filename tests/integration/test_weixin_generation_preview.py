"""Current persistent generation scope is checked before any synthetic translation."""
import importlib
import importlib.util
import json
import socket
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service as conversations
from cn_contract.security import ServiceError, provision_user
from cn_contract.task_drafts import service as tasks
from cn_contract.weixin_inbox import accounts, generations
from tests.helpers.synthetic_weixin_generation_service import append, request
from tests.helpers.synthetic_weixin_generations import setup_history, state
from tests.integration.test_weixin_dispatch import message
from tests.integration.test_weixin_ingress_atomic import world


def api():
    name='cn_contract.weixin_inbox.generation_preview'
    assert importlib.util.find_spec(name) is not None, 'D2g5a needs current generation offline preview'
    return importlib.import_module(name)


def raw(*messages):
    return json.dumps(dict(ret=0,msgs=messages,get_updates_buf='synthetic-hypothetical-next'),ensure_ascii=False).encode()


def head(h):
    return generations.read_peer_generation_head(h['actor'],h['mapping'].id,database=h['database'])


def preview(h, data, expected=None):
    return api().preview_generation_response(h['actor'],h['mapping'].id,expected or head(h),data,database=h['database'])


def snapshot(database):
    result=state(database)
    with database.session() as db:
        for name in ('audit_events','assistant_messages','assistant_model_attempts','assistant_attachments','task_media_resolutions'):
            result[name]=[tuple(row) for row in db.execute(text('SELECT * FROM '+name+' ORDER BY rowid'))]
    return result


@pytest.mark.parametrize('number',[0,1,2])
def test_zero_last_grant_or_latest_generation_supplies_scope_and_both_distinct_cursors(world,number,monkeypatch):
    h=setup_history(world);latest=None
    for _ in range(number):latest=append(h,request(h,latest))
    target=h['targets'][number-1][1] if number else h['binding']
    with h['database'].session() as db:
        binding=tasks.read_binding(h['actor'],target.id,db)
    before=snapshot(h['database']);expected=head(h)
    def no_network(*args,**kwargs):raise AssertionError('preview must never access network')
    monkeypatch.setattr(socket.socket,'connect',no_network)
    monkeypatch.setattr(socket,'create_connection',no_network)
    value=preview(h,raw(message(91),message(92,file=True)),expected)
    assert value.head==expected and value.state=='preview_only'
    assert value.plan.scope.binding_id==binding.id and value.plan.scope.task_cursor==binding.cursor
    assert value.plan.scope.expected_scope==(latest.scope if latest else h['grant'].scope)
    assert value.plan.scope.upstream_cursor=='opaque:2' and value.head.checkpoint_revision==2
    assert value.plan.next_upstream_cursor=='synthetic-hypothetical-next'
    assert value.plan.batch.expected_cursor==binding.cursor and value.plan.batch.next_cursor==binding.cursor+1
    assert len(value.plan.batch.events)==2 and value.plan.batch.events[1].media[0].status=='pending'
    assert value.plan.scope.owner_id==h['actor'].user_id and value.plan.scope.session_id==h['actor'].session_id
    assert snapshot(h['database'])==before


@pytest.mark.parametrize('cursor_present',[True,False])
def test_empty_poll_is_only_a_cursor_hypothesis_with_no_task_batch(world,cursor_present):
    h=setup_history(world);append(h);before=snapshot(h['database'])
    value=preview(h,raw() if cursor_present else b'{"ret":0,"msgs":[]}')
    assert value.plan.batch is None and value.plan.event_payload_hashes=={}
    assert value.plan.next_upstream_cursor==('synthetic-hypothetical-next' if cursor_present else 'opaque:2')
    assert snapshot(h['database'])==before


@pytest.mark.parametrize('field',['generation','generation_sha256','checkpoint_revision','scope'])
def test_stale_or_forged_complete_head_is_not_current_authority(world,field):
    h=setup_history(world);append(h);value=head(h)
    changes=dict(generation=2,generation_sha256='f'*64,checkpoint_revision=0,
        scope=value.scope.model_copy(update={'conversation_id':uuid4()}))
    if field=='scope':
        from cn_contract.record_codec import sha
        value=value.model_copy(update={'scope':changes[field],'scope_sha256':sha(changes[field].model_dump(mode='json'))})
    else:value=value.model_copy(update={field:changes[field]})
    before=snapshot(h['database'])
    with pytest.raises(ServiceError) as error:preview(h,raw(message(92)),value)
    assert error.value.code=='VERSION_CONFLICT' and snapshot(h['database'])==before


def test_expected_head_is_revalidated_against_model_copy_bypass(world):
    h=setup_history(world);append(h);bad=head(h).model_copy(update={'checkpoint_revision':True})
    from pydantic import ValidationError
    before=snapshot(h['database'])
    with pytest.raises(ValidationError):preview(h,raw(message(93)),bad)
    assert snapshot(h['database'])==before


@pytest.mark.parametrize('revision',['binding_revision','input_revision','materials_revision'])
def test_current_target_full_scope_must_still_equal_persistent_authorized_scope(world,revision):
    h=setup_history(world);append(h);expected=head(h);cid=h['targets'][0][0].scope.conversation_id
    with h['database'].session() as db:
        db.execute(text('UPDATE assistant_conversations SET '+revision+'='+revision+'+1 WHERE id=:cid'),{'cid':str(cid)})
    before=snapshot(h['database'])
    with pytest.raises(ServiceError) as error:preview(h,raw(message(94)),expected)
    assert error.value.code=='VERSION_CONFLICT' and snapshot(h['database'])==before


@pytest.mark.parametrize('change',['session','role','root_archive','target_archive','account','peer','owner','workspace'])
def test_current_identity_root_target_and_permanent_revoke_guards_precede_translation(world,change):
    h=setup_history(world);append(h);expected=head(h)
    with h['database'].session() as db:
        if change=='session':db.execute(text('UPDATE sessions SET revoked=1'))
        elif change=='role':db.execute(text("UPDATE users SET roles='[\"assistant\"]'"))
        elif change in ('root_archive','target_archive'):
            cid=h['view'].scope.conversation_id if change=='root_archive' else h['targets'][0][0].scope.conversation_id
            db.execute(text("UPDATE assistant_conversations SET archived_at='2026-10-25T00:00:00Z' WHERE id=:id"),{'id':str(cid)})
        elif change=='owner':
            other=provision_user('fiction-preview-other','fiction-preview-password',{d.Role.HANDLING_LAWYER},db)
            db.execute(text('UPDATE assistant_conversations SET owner_id=:owner WHERE id=:id'),
                {'owner':str(other),'id':str(h['targets'][0][0].scope.conversation_id)})
        elif change=='workspace':
            db.execute(text('UPDATE assistant_conversations SET workspace_id=:workspace WHERE id=:id'),
                {'workspace':str(uuid4()),'id':str(h['targets'][0][0].scope.conversation_id)})
    if change in ('account','peer'):
        function=accounts.revoke_synthetic_account if change=='account' else accounts.revoke_synthetic_peer
        function(h['actor'],h['account'].id if change=='account' else h['mapping'].id,
            d.WeixinRevokeInput(reason='独立合成预览撤权'),database=h['database'])
    before=snapshot(h['database'])
    with pytest.raises(ServiceError) as error:preview(h,b'invalid protocol must not be reached',expected)
    code,status=('AUTHORIZATION_REQUIRED',401) if change=='session' else ('CROSS_MATTER_DENIED',403) if change=='role' else (
        ('VERSION_CONFLICT',409) if change in ('owner','workspace') else ('STATE_CONFLICT',409))
    assert (error.value.code,error.value.status_code)==(code,status)
    assert snapshot(h['database'])==before


@pytest.mark.parametrize('data',[b'{',b'{"ret":0,"ret":0}',
    raw(message(96,peer='synthetic-peer-two')),raw(message(96),message(96)),raw(message(96),message(97,peer='unknown'))])
def test_invalid_or_mixed_peer_poll_is_wholly_rejected_without_a_partial_preview(world,data):
    h=setup_history(world);append(h);before=snapshot(h['database'])
    with pytest.raises(ServiceError):preview(h,data)
    assert snapshot(h['database'])==before


def test_old_source_reply_and_media_secrets_do_not_become_redirected_durable_messages(world):
    h=setup_history(world);append(h);old=h['received'].descriptors[0];item=message(1,reply=1)
    item['context_token']='SYNTHETIC_PREVIEW_CONTEXT_SECRET'
    file=message(98,file=True);file['item_list'][0]['file_item']['media']={
        'aes_key':'SYNTHETIC_PREVIEW_AES_SECRET','full_url':'https://example.invalid/not-downloaded'}
    before=snapshot(h['database']);value=preview(h,raw(item,file))
    first=value.plan.batch.events[0]
    assert first.event_id==old.source_event_id and first.reply_to_event_id==old.source_event_id
    serialized=value.model_dump_json()
    for secret in ('SYNTHETIC_PREVIEW_CONTEXT_SECRET','SYNTHETIC_PREVIEW_AES_SECRET','example.invalid'):
        assert secret not in serialized
    assert snapshot(h['database'])==before


def test_zero_generation_old_head_cannot_hide_a_new_explicit_same_target_grant(world):
    from tests.integration.test_weixin_reauthorization import advance, request as grant_request
    h=setup_history(world);old=head(h)
    scope=advance(world,input_revision=2)
    grant=accounts.refresh_synthetic_peer(h['actor'],h['mapping'].id,
        grant_request(h['mapping'],scope,h['grant']),database=h['database'])
    expected=head(h);assert expected.generation==0 and expected.scope==grant.scope and expected!=old
    before=snapshot(h['database'])
    with pytest.raises(ServiceError) as error:preview(h,raw(message(99)),old)
    assert error.value.code=='VERSION_CONFLICT'
    assert preview(h,raw(message(99)),expected).plan.scope.expected_scope==scope
    assert snapshot(h['database'])==before


def test_target_task_cursor_is_read_fresh_without_treating_head_as_a_consumption_token(world):
    h=setup_history(world);append(h);expected=head(h);target=h['targets'][0][1]
    with h['database'].session() as db:
        tasks.receive_batch(h['actor'],target.id,d.TaskInboxBatchInput(expected_cursor=0,next_cursor=1,
            events=(d.TaskInboxEventInput(event_id='independent-local-event',text='独立合成本地补充'),)),db)
    before=snapshot(h['database']);value=preview(h,raw(message(100)),expected)
    assert value.head==expected and value.plan.scope.task_cursor==1
    assert value.plan.batch.expected_cursor==1 and value.plan.batch.next_cursor==2
    assert snapshot(h['database'])==before


def test_actual_qxbak_restored_copy_cannot_preview_or_consume_generation(world,tmp_path):
    from cn_contract.ops import backup, workspace_backup
    from cn_contract.persistence import Database
    from tests.helpers.legacy_assistant_backup import USERNAME, PASSWORD, PASSPHRASE
    from cn_contract.security import authenticate, login
    h=setup_history(world);append(h);expected=head(h);source_before=snapshot(h['database'])
    archive=tmp_path/'independent-generation-preview.qxbak'
    workspace_backup.create_workspace_backup(h['root'],archive,PASSPHRASE,data_parent=tmp_path)
    info=workspace_backup.restore_workspace_backup(archive,tmp_path/'restored-preview',PASSPHRASE)
    from pathlib import Path
    root=Path(info['restored_root'])
    restored=Database('sqlite:///'+str(root/'workbench.db'),root/'protected',h['database'].settings,initialize_schema=False)
    backup._mark_storage_flags(restored)
    try:
        before=snapshot(restored)
        with pytest.raises(ServiceError) as error:
            api().preview_generation_response(h['actor'],h['mapping'].id,expected,raw(message(101)),database=restored)
        assert error.value.code=='AUTHORIZATION_REQUIRED'
        assert snapshot(restored)==before
        with restored.session() as db:
            token,_=login(USERNAME,PASSWORD,db)
            actor=authenticate(token,db)
        before=snapshot(restored)
        with pytest.raises(ServiceError) as error:
            api().preview_generation_response(actor,h['mapping'].id,expected,raw(message(101)),database=restored)
        assert error.value.code=='BLOCKED_LIVE' and snapshot(restored)==before
    finally:
        restored.engine.dispose()
    assert snapshot(h['database'])==source_before
