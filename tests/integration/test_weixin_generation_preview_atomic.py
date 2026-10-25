"""Independent real-SQL previews never publish intake or mix target generations."""
import importlib
import importlib.util
import json
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.ops import backup
from cn_contract.ops.storage import RestoreFenceRow
from cn_contract.persistence import Database
from cn_contract.security import ServiceError
from cn_contract.weixin_inbox import accounts, ingress
from tests.helpers.synthetic_weixin_generation_service import api, append, request
from tests.helpers.synthetic_weixin_generations import setup_history, state
from tests.integration.test_weixin_dispatch import message
from tests.integration.test_weixin_dispatch_integrity import corrupt
from tests.integration.test_weixin_generation_head_atomic import ordered_transactions
from tests.integration.test_weixin_ingress_atomic import world


def service():
    name='cn_contract.weixin_inbox.generation_preview'
    assert importlib.util.find_spec(name) is not None, 'D2g5a needs a read-only generation preview service'
    operation=getattr(importlib.import_module(name), 'preview_generation_response', None)
    assert callable(operation), 'D2g5a needs the bounded explicit generation preview entry'
    return operation


def setup(world):
    h=setup_history(world)
    first=append(h)
    h['head']=api().read_peer_generation_head(h['actor'],h['mapping'].id,database=h['database'])
    h['first']=first
    incoming=message(91,content='独立虚构代际预览；不能写入任务或开启收件')
    incoming['context_token']='synthetic-preview-secret-not-to-persist'
    h['raw']=json.dumps({'ret':0,'msgs':[incoming],'get_updates_buf':'preview-opaque:next'},ensure_ascii=False).encode('utf-8')
    return h


def preview(h, *, database=None):
    return service()(h['actor'],h['mapping'].id,h['head'],h['raw'],
        database=database if database is not None else h['database'])


def fixed_state(database):
    result=state(database)
    with database.session() as db:
        for table in ('audit_events','assistant_conversations','assistant_messages',
                'assistant_material_snapshots','assistant_model_attempts','ops_restore_fences'):
            result[table]=[tuple(row) for row in db.execute(text('SELECT * FROM '+table+' ORDER BY rowid'))]
    return result


def outcome(call):
    try:
        return call()
    except ServiceError as error:
        return error.code,error.status_code


@pytest.mark.parametrize('winner',['preview','append'])
def test_preview_and_new_generation_serialize_complete_snapshot_or_stale_head_conflict(world,winner):
    service()
    h=setup(world)
    second_request=request(h,h['first'])
    before=fixed_state(h['database'])
    operations={'preview':lambda:outcome(lambda:preview(h)),
        'append':lambda:append(h,second_request)}
    other='append' if winner=='preview' else 'preview'
    first,second=ordered_transactions(h['database'],operations[winner],operations[other],
        first_mutation='insert into weixin_peer_generations' if winner=='append' else None)
    shown,saved=(first,second) if winner=='preview' else (second,first)
    assert saved.generation==2
    if winner=='preview':
        assert shown.mode=='synthetic' and shown.state=='preview_only'
        assert shown.head==h['head'] and shown.head.generation==1
        assert shown.plan.scope.expected_scope==h['first'].scope
        assert shown.plan.scope.binding_id==h['targets'][0][1].id
        assert shown.plan.scope.task_cursor==0 and shown.plan.scope.upstream_cursor=='opaque:2'
        assert shown.plan.batch.expected_cursor==0 and shown.plan.batch.next_cursor==1
    else:
        assert shown==('VERSION_CONFLICT',409)
    after=fixed_state(h['database'])
    assert {name:rows for name,rows in after.items() if name!='weixin_peer_generations'}=={
        name:rows for name,rows in before.items() if name!='weixin_peer_generations'}
    assert len(after['weixin_peer_generations'])==len(before['weixin_peer_generations'])+1
    assert outcome(lambda:preview(h))==('VERSION_CONFLICT',409)
    assert fixed_state(h['database'])==after


def test_actual_peer_revocation_wins_lock_before_preview_and_no_raw_candidate_is_returned(world):
    service()
    h=setup(world)
    before=fixed_state(h['database'])
    revoked,shown=ordered_transactions(h['database'],lambda:accounts.revoke_synthetic_peer(h['actor'],
        h['mapping'].id,d.WeixinRevokeInput(reason='独立虚构预览前撤权'),database=h['database']),
        lambda:outcome(lambda:preview(h)),first_mutation='update weixin_peer_bindings')
    assert revoked.revoked_at is not None and shown==('STATE_CONFLICT',409)
    after=fixed_state(h['database'])
    assert {name:rows for name,rows in after.items() if name!='weixin_peer_bindings'}=={
        name:rows for name,rows in before.items() if name!='weixin_peer_bindings'}


def test_restored_fence_rejects_preview_without_reactivating_or_changing_source_history(world):
    service()
    h=setup(world)
    with h['database'].session() as db:
        db.add(RestoreFenceRow(ref=str(uuid4()),archive_sha256='a'*64,manifest_sha256='b'*64,payload='{}'))
    before=fixed_state(h['database'])
    assert outcome(lambda:preview(h))==('BLOCKED_LIVE',409)
    assert fixed_state(h['database'])==before


def test_corrupt_generation_history_rejects_preview_instead_of_trusting_a_well_formed_head(world):
    service()
    h=setup(world)
    with h['database'].session() as db:
        corrupt(db,'UPDATE weixin_peer_generations SET generation_sha256=:sha',{'sha':'f'*64})
    before=fixed_state(h['database'])
    assert outcome(lambda:preview(h))==('VERSION_CONFLICT',409)
    assert fixed_state(h['database'])==before


def test_preview_survives_reopened_database_with_no_rows_written_and_runtime_pause_still_enforced(world):
    service()
    h=setup(world)
    before=fixed_state(h['database'])
    database=Database('sqlite:///'+str(h['root']/'workbench.db'),h['root']/'protected',
        h['database'].settings,initialize_schema=False)
    backup._mark_storage_flags(database)
    try:
        shown=preview(h,database=database)
        assert shown.head==h['head'] and shown.state=='preview_only'
        assert shown.plan.scope.expected_scope==h['first'].scope
        assert shown.plan.next_upstream_cursor=='preview-opaque:next'
        assert 'synthetic-preview-secret-not-to-persist' not in shown.model_dump_json()
    finally:
        database.engine.dispose()
    assert fixed_state(h['database'])==before
    poll_input=d.WeixinPollInput(request_id=uuid4(),expected_revision=2,expected_cursor='opaque:2')
    assert outcome(lambda:ingress.record_synthetic_poll(h['actor'],h['account'].id,poll_input,
        h['raw'],database=h['database']))==('STATE_CONFLICT',409)
    assert fixed_state(h['database'])==before


def test_current_projected_matter_denial_keeps_business_fixed_and_preserves_security_audit(world):
    from cn_contract.matters import create_matter
    from cn_contract.persistence import MembershipRow
    service()
    h=setup(world)
    with h['database'].session() as db:
        matter=create_matter(d.MatterCreateInput(title='独立虚构预览权限案件',contract_type='sales',
            review_mode='pre_sign',position='buyer',objectives=('仅当前权限验收',)),h['actor'],db)
        intake=uuid4()
        db.execute(text('''INSERT INTO intake_cases(id,owner_id,request_id,request_sha256,current_revision,matter_id)
            VALUES(:id,:owner,:request,:sha,1,:matter)'''),dict(id=str(intake),owner=str(h['actor'].user_id),
                request=str(uuid4()),sha='a'*64,matter=str(matter.id)))
        db.execute(text('UPDATE assistant_conversations SET projection_intake_id=:intake WHERE id=:id'),
            {'intake':str(intake),'id':str(h['first'].scope.conversation_id)})
        db.delete(db.get(MembershipRow,(str(matter.id),str(h['actor'].user_id))))
    before=fixed_state(h['database'])
    assert outcome(lambda:preview(h))==('CROSS_MATTER_DENIED',403)
    after=fixed_state(h['database'])
    assert {name:rows for name,rows in after.items() if name!='audit_events'}=={
        name:rows for name,rows in before.items() if name!='audit_events'}
    assert after['audit_events'][:len(before['audit_events'])]==before['audit_events']
    assert len(after['audit_events'])==len(before['audit_events'])+1
    with h['database'].session() as db:
        action,matter_id,actor_id=db.execute(text('''SELECT action,matter_id,actor_id FROM audit_events
            ORDER BY rowid DESC LIMIT 1''')).one()
    assert (action,matter_id,actor_id)==('authorization_denied',str(matter.id),str(h['actor'].user_id))
