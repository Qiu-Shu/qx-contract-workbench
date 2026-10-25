"""Read heads select persistent authority without reviving current execution."""
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.ops.storage import RestoreFenceRow
from cn_contract.weixin_inbox import accounts
from tests.helpers.synthetic_weixin_generation_service import api,append,request
from tests.helpers.synthetic_weixin_generations import setup_history,state
from tests.integration.test_weixin_ingress_atomic import world


def head(h):
    assert hasattr(api(),'read_peer_generation_head'),'D2g3 needs a coherent current generation head'
    return api().read_peer_generation_head(h['actor'],h['mapping'].id,database=h['database'])


def snapshot(database):
    result=state(database)
    with database.session() as db:
        result['audit_events']=[tuple(row) for row in db.execute(text('SELECT * FROM audit_events ORDER BY rowid'))]
    return result


def test_zero_generation_without_grant_uses_mapping_scope_and_checkpoint(world):
    root,database,actor,view,binding=world
    account=accounts.create_synthetic_account(actor,d.WeixinAccountCreateInput(bot_account_id='synthetic-head-bot'),database=database)
    mapping=accounts.bind_synthetic_peer(actor,account.id,d.WeixinPeerBindInput(sender_peer_id='synthetic-head-peer',
        task_binding_id=binding.id,expected_scope=view.scope),database=database)
    h=dict(actor=actor,mapping=mapping,database=database);before=snapshot(database)
    value=head(h)
    assert value.generation==0 and value.generation_sha256 is None
    assert value.scope==mapping.scope and value.scope_sha256==mapping.scope_sha256 and value.checkpoint_revision==0
    assert snapshot(database)==before


def test_zero_head_uses_last_authorized_grant_not_current_root_snapshot(world):
    h=setup_history(world)
    with h['database'].session() as db:
        db.execute(text('UPDATE assistant_conversations SET input_revision=3 WHERE id=:id'),{'id':str(h['view'].scope.conversation_id)})
    before=snapshot(h['database']);value=head(h)
    assert value.generation==0 and value.generation_sha256 is None
    assert value.scope==h['grant'].scope and value.scope.input_revision==1
    assert value.scope_sha256==h['grant'].scope_sha256 and value.checkpoint_revision==2
    assert snapshot(h['database'])==before


def test_two_generations_select_latest_head_and_keep_fixed_history(world):
    h=setup_history(world);first=append(h);second=append(h,request(h,first))
    before=snapshot(h['database']);value=head(h)
    assert value.generation==2 and value.generation_sha256==second.generation_sha256
    assert value.scope==second.scope and value.scope_sha256==second.scope_sha256
    assert value.checkpoint_revision==second.checkpoint_revision==2
    assert snapshot(h['database'])==before


@pytest.mark.parametrize('change',['root_archive','target_archive','account_revoke','peer_revoke','fence','target_growth'])
def test_head_remains_fixed_historical_metadata_under_read_only_states(world,change):
    h=setup_history(world);first=append(h);database=h['database']
    if change in ('root_archive','target_archive','target_growth','fence'):
        with database.session() as db:
            cid=h['view'].scope.conversation_id if change=='root_archive' else first.scope.conversation_id
            if change in ('root_archive','target_archive'):
                db.execute(text("UPDATE assistant_conversations SET archived_at='2026-10-25T07:15:00Z' WHERE id=:id"),{'id':str(cid)})
            elif change=='target_growth':
                db.execute(text('UPDATE assistant_conversations SET input_revision=3 WHERE id=:id'),{'id':str(cid)})
            else:db.add(RestoreFenceRow(ref=str(uuid4()),archive_sha256='a'*64,manifest_sha256='b'*64,payload='{}'))
    else:
        function=accounts.revoke_synthetic_account if change=='account_revoke' else accounts.revoke_synthetic_peer
        function(h['actor'],h['account'].id if change=='account_revoke' else h['mapping'].id,
            d.WeixinRevokeInput(reason='独立合成head逻辑撤权'),database=database)
    before=snapshot(database);value=head(h)
    assert value.generation==1 and value.scope==first.scope and value.generation_sha256==first.generation_sha256
    assert snapshot(database)==before
