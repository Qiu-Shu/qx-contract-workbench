"""Versioned archive provenance never reassigns old sources or resumes runtime."""
import importlib
import importlib.util
from datetime import timedelta

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.config import canonical_json
from cn_contract.ops import backup
from cn_contract.record_codec import sha
from cn_contract.security import ServiceError
from cn_contract.weixin_inbox import dispatch, generations, ingress
from tests.helpers.synthetic_weixin_provenance import chain,poll_sample,snapshot
from tests.helpers.synthetic_weixin_generation_service import append
from tests.helpers.synthetic_weixin_generations import setup_history
from tests.integration.test_weixin_dispatch_integrity import corrupt,rehash_receipt
from tests.integration.test_weixin_ingress_atomic import world


def api():
    name='cn_contract.weixin_inbox.provenance_integrity'
    assert importlib.util.find_spec(name) is not None,'D2g5b needs historical descriptor target validation'
    return importlib.import_module(name)


def validate(h):
    with h['database'].session() as db:
        assert api().validate_descriptor_generations(db,allow_provenance=True)==[]
        backup._file_references(db)


def rewrite(db,identifier,**changes):
    row=dict(db.execute(text('SELECT * FROM weixin_descriptor_generations WHERE descriptor_id=:id'),{'id':str(identifier)}).mappings().one())
    row.pop('provenance_sha256');row.update(changes);row['provenance_sha256']=sha(row)
    corrupt(db,'UPDATE weixin_descriptor_generations SET '+','.join(key+'=:'+key for key in row)+' WHERE descriptor_id=:lookup',dict(**row,lookup=str(identifier)))


def test_two_actual_poll_prefixes_resolve_then_backup_without_rewriting_old_history(world):
    api();h=chain(world);before=snapshot(h['database']);validate(h)
    assert snapshot(h['database'])==before
    current=generations.read_peer_generation_head(h['actor'],h['mapping'].id,database=h['database'])
    assert current.generation==2 and current.checkpoint_revision==4
    assert h['first'].checkpoint_revision==2 and h['second'].checkpoint_revision==3
    for action in (
        lambda:ingress.record_synthetic_poll(h['actor'],h['account'].id,d.WeixinPollInput(
            request_id=h['received'].request_id,expected_revision=4,expected_cursor='opaque:4'),b'{}',database=h['database']),
        lambda:dispatch.dispatch_synthetic_descriptor(h['actor'],h['one'][1].id,database=h['database'])):
        with pytest.raises(ServiceError) as error:action()
        assert error.value.code=='STATE_CONFLICT'
    assert snapshot(h['database'])==before


@pytest.mark.parametrize('damage',['missing','future_generation','old_generation','binding','scope','payload','digest'])
def test_recomputed_metadata_cannot_change_historical_target(world,damage):
    api();h=chain(world);one,two=h['one'][1],h['two'][1]
    with h['database'].session() as db:
        if damage=='missing':corrupt(db,'DELETE FROM weixin_descriptor_generations WHERE descriptor_id=:id',{'id':str(one.id)})
        elif damage=='future_generation':rewrite(db,one.id,generation_id=str(h['second'].id),generation_sha256=h['second'].generation_sha256,
            task_binding_id=str(h['second'].task_binding_id),scope_sha256=h['second'].scope_sha256)
        elif damage=='old_generation':rewrite(db,two.id,generation_id=str(h['first'].id),generation_sha256=h['first'].generation_sha256,
            task_binding_id=str(h['first'].task_binding_id),scope_sha256=h['first'].scope_sha256)
        elif damage=='binding':rewrite(db,one.id,task_binding_id=str(h['binding'].id))
        elif damage in ('scope','payload'):rewrite(db,one.id,**{damage+'_sha256':'f'*64})
        else:corrupt(db,'UPDATE weixin_descriptor_generations SET provenance_sha256=:sha WHERE descriptor_id=:id',{'id':str(one.id),'sha':'f'*64})
    with h['database'].session() as db,pytest.raises(ValueError,match='WEIXIN_PROVENANCE_INTEGRITY'):
        api().validate_descriptor_generations(db,allow_provenance=True)


@pytest.mark.parametrize('source',['root_zero','blocked','duplicate'])
def test_sidecar_cannot_adopt_or_revive_non_target_originals(world,source):
    api();h=chain(world)
    with h['database'].session() as db:
        old=h['received'].descriptors[0]
        row=dict(descriptor_id=str(old.id),generation_id=str(h['first'].id),generation_sha256=h['first'].generation_sha256,
            task_binding_id=str(h['first'].task_binding_id),scope_sha256=h['first'].scope_sha256,payload_sha256=sha(old.payload.model_dump(mode='json')))
        if source!='root_zero':
            identifier=h['one'][1].id
            if source=='blocked':
                corrupt(db,"UPDATE weixin_inbox_descriptors SET status='blocked',reason='message_invalid',payload_json=NULL WHERE id=:id",{'id':str(identifier)})
            else:
                corrupt(db,"UPDATE weixin_inbox_descriptors SET status='duplicate',reason='replayed',payload_json=NULL,prior_descriptor_id=:prior WHERE id=:id",{'id':str(identifier),'prior':str(old.id)})
        else:
            from tests.helpers.synthetic_weixin_provenance import insert
            insert(db,'weixin_descriptor_generations',dict(**row,provenance_sha256=sha(row)))
    with h['database'].session() as db,pytest.raises(ValueError,match='WEIXIN_PROVENANCE_INTEGRITY'):
        api().validate_descriptor_generations(db,allow_provenance=True)


@pytest.mark.parametrize('reply',[1,91])
def test_known_accepted_reply_cannot_cross_a_generation_boundary(world,reply):
    api();h=setup_history(world);first=append(h)
    if reply==91:
        poll_sample(h,first,91)
        from tests.helpers.synthetic_weixin_generation_service import request
        target=append(h,request(h,first))
    else:target=first
    poll_sample(h,target,92,reply=reply)
    with h['database'].session() as db,pytest.raises(ValueError,match='WEIXIN_PROVENANCE_INTEGRITY'):
        api().validate_descriptor_generations(db,allow_provenance=True)


def test_unknown_reply_stays_unknown_and_other_zero_generation_peer_has_no_sidecar(world):
    api();h=setup_history(world);first=append(h)
    poll_sample(h,first,91,reply=999)
    poll_sample(h,first,92,sidecar=False,peer=h['peer'])
    validate(h)


@pytest.mark.parametrize('damage',['checkpoint','same_utc_boundary'])
def test_complete_account_prefix_and_strict_utc_time_boundary_still_hold(world,damage):
    api();h=chain(world)
    with h['database'].session() as db:
        if damage=='checkpoint':
            from tests.integration.test_weixin_generation_backup import rehash_chain
            corrupt(db,'UPDATE weixin_peer_generations SET checkpoint_revision=4 WHERE id=:id',{'id':str(h['second'].id)})
            rehash_chain(db)
        else:
            value=h['first'].created_at.isoformat()
            corrupt(db,'UPDATE weixin_poll_receipts SET created_at=:at WHERE id=:id',{'id':str(h['one'][0].id),'at':value})
    with pytest.raises(ValueError):validate(h)


def test_schema18_empty_later_poll_preserves_the_generation_prefix(world):
    from tests.helpers.synthetic_weixin_inbox import insert,poll_receipt
    api();h=setup_history(world);generation=append(h)
    with h['database'].session() as db:
        db.execute(text('DROP TABLE assistant_followup_revisions'))
        db.execute(text('DROP TABLE assistant_evidence_revisions'))
        db.execute(text('DROP INDEX weixin_dispatch_binding_cursor'))
        from tests.helpers.legacy_material_model import downgrade_material_model_session
        downgrade_material_model_session(db)
        account=db.execute(text('SELECT * FROM weixin_accounts WHERE id=:id'),{'id':str(h['account'].id)}).mappings().one()
        at=generation.created_at+timedelta(microseconds=1)
        poll=poll_receipt(h['account'].id,account['checkpoint_revision'],account['upstream_cursor'],account['upstream_cursor'],(),at)
        insert(db,'weixin_poll_receipts',poll.model_dump(mode='json',exclude={'descriptors'}))
        db.execute(text('UPDATE weixin_accounts SET checkpoint_revision=:revision WHERE id=:id'),
            {'id':str(h['account'].id),'revision':poll.next_revision})
    validate(h)
