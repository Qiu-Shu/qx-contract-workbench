"""Independent HTTP generation boundaries, historical reads and lost acknowledgements."""
import importlib
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.ops.storage import RestoreFenceRow
from cn_contract.record_codec import now
from cn_contract.weixin_inbox import accounts, conversation
from test_api import create_case
from test_assistant_routes import chat, native, create, sign_in
from test_weixin_authorization_routes import bind, state


RECEIPT_KEYS = {'mode', 'state', 'generation', 'request_id', 'scope', 'scope_sha256',
    'previous_generation_sha256', 'previous_scope_sha256', 'checkpoint_revision',
    'created_at', 'generation_sha256'}


def endpoint(cid):
    return '/api/assistant/conversations/'+str(cid)+'/weixin-authorization/generations'


def setup(chat, *, target_matter=False):
    client, database, root, headers, view, actor, account, mapping = bind(chat)
    fields = {'scope_kind':'matter', 'scope_ref':create_case(client, headers)} if target_matter else {}
    target = create(client, headers, **fields)
    binding = client.post('/api/assistant/conversations/'+target['scope']['conversation_id']+'/task-bindings',
        headers=headers)
    assert binding.status_code == 200, binding.text
    request = dict(request_id=str(uuid4()), expected_generation=0,
        expected_previous_generation_sha256=None, expected_previous_scope_sha256=mapping.scope_sha256,
        expected_checkpoint_revision=account.checkpoint_revision, task_binding_id=binding.json()['id'],
        expected_scope=target['scope'], reason='独立合成历史记录 HTTP 验收理由，不得出现在回执')
    return dict(client=client, database=database, root=root, headers=headers, view=view, target=target,
        actor=actor, account=account, mapping=mapping, request=request,
        base=endpoint(view['scope']['conversation_id']))


def snapshot(database):
    result = state(database)
    with database.session() as db:
        result['weixin_peer_generations'] = [tuple(row) for row in db.execute(text(
            'SELECT * FROM weixin_peer_generations ORDER BY rowid'))]
        for name in ('assistant_model_attempts', 'review_runs'):
            result[name] = [tuple(row) for row in db.execute(text('SELECT * FROM '+name+' ORDER BY rowid'))]
    return result


def saved(h):
    response = h['client'].post(h['base'], headers=h['headers'], json=h['request'])
    assert response.status_code == 200, response.text
    receipt = response.json()
    assert set(receipt) == RECEIPT_KEYS
    assert receipt['mode'] == 'synthetic' and receipt['state'] == 'history_only'
    assert receipt['generation'] == 1 and receipt['scope'] == h['target']['scope']
    assert receipt['request_id'] == h['request']['request_id']
    for secret in (h['request']['reason'], str(h['actor'].user_id), str(h['mapping'].id),
            str(h['account'].id), h['account'].bot_account_id, h['mapping'].sender_peer_id,
            h['request']['task_binding_id']):
        assert secret not in response.text
    return receipt


def test_generation_receipt_reads_have_an_exact_recovery_path_predicate():
    module = importlib.import_module('cn_contract.web.weixin_authorization')
    predicate = module.is_weixin_authorization_read_path
    base = endpoint(uuid4()); key = '12345678-1234-1234-1234-123456789abc'
    assert predicate(base+'/by-request/'+key)
    for path in (base, base+'/', base+'/by-request', base+'/by-request/bad',
            base+'/by-request/'+key+'/', base+'/by-request/'+key+'/polls',
            base+'/by-request/'+key.upper(), base+'/head/', base+'/polls'):
        assert not predicate(path), path


def test_actual_fenced_app_reads_fixed_generation_and_blocks_writes_and_nearby_paths(native):
    from cn_contract.web import local_server
    original_app, root = native
    with TestClient(original_app) as client:
        h = setup((client, original_app.state.database, root)); receipt = saved(h)
        with h['database'].session() as db:
            db.add(RestoreFenceRow(ref=str(uuid4()), archive_sha256='a'*64,
                manifest_sha256='b'*64, payload='{}'))
    app = local_server.build_local_app(root, data_parent=root.parent.parent)
    try:
        with TestClient(app) as restored:
            headers = sign_in(restored)
            before = snapshot(app.state.database)
            path = h['base']+'/by-request/'+h['request']['request_id']
            found = restored.get(path)
            assert found.status_code == 200 and found.json() == receipt, found.text
            unknown = restored.get(h['base']+'/by-request/'+str(uuid4()))
            assert unknown.status_code == 200 and unknown.json() is None, unknown.text
            assert restored.post(h['base'], headers=headers, json=h['request']).status_code == 409
            for suffix in ('', '/', '/head/', '/polls', '/by-request/bad',
                    '/by-request/'+h['request']['request_id']+'/polls'):
                assert restored.get(h['base']+suffix).status_code == 409
            assert snapshot(app.state.database) == before
    finally:
        app.state.database.engine.dispose()


@pytest.mark.parametrize('damage', ['archive', 'scope_growth', 'account_revoked'])
def test_fixed_generation_metadata_survives_target_growth_archive_and_logical_revocation(chat, damage):
    h = setup(chat); receipt = saved(h); client = h['client']; database = h['database']
    target_cid = h['target']['scope']['conversation_id']
    if damage == 'archive':
        with database.session() as db:
            db.execute(text('UPDATE assistant_conversations SET archived_at=:at WHERE id=:id'),
                {'id':target_cid, 'at':now().isoformat()})
    elif damage == 'scope_growth':
        response = client.put('/api/assistant/conversations/'+target_cid+'/materials', headers=h['headers'],
            json={'request_id':str(uuid4()), 'expected_scope':h['target']['scope'], 'items':[]})
        assert response.status_code == 200 and response.json()['materials_revision'] == 1, response.text
    else:
        accounts.revoke_synthetic_account(h['actor'], h['account'].id,
            d.WeixinRevokeInput(reason='独立合成历史查询撤权'), database=database)
    before = snapshot(database)
    found = client.get(h['base']+'/by-request/'+h['request']['request_id'])
    assert found.status_code == 200 and found.json() == receipt, found.text
    assert snapshot(database) == before


def test_recorded_target_current_matter_acl_is_required_before_history_is_disclosed(chat):
    h = setup(chat, target_matter=True); saved(h)
    with h['database'].session() as db:
        db.execute(text('DELETE FROM matter_memberships WHERE matter_id=:matter AND user_id=:user'),
            {'matter':h['target']['scope']['scope_ref'], 'user':str(h['actor'].user_id)})
    before = snapshot(h['database'])
    found = h['client'].get(h['base']+'/by-request/'+h['request']['request_id'])
    assert found.status_code == 403, found.text
    after = snapshot(h['database'])
    assert {key:value for key,value in after.items() if key != 'audit_events'} == {
        key:value for key,value in before.items() if key != 'audit_events'}
    assert h['request']['reason'] not in found.text


@pytest.mark.parametrize('when', ['before_body', 'after_body'])
@pytest.mark.parametrize('damage,expected', [('owner',403), ('archive',409), ('account_revoked',409)])
def test_current_root_authority_is_checked_before_and_after_reading_body(chat, monkeypatch, when, damage, expected):
    h = setup(chat); route = importlib.import_module('cn_contract.web.weixin_authorization')
    original = route.body_input; read = []
    def change():
        if damage == 'account_revoked':
            accounts.revoke_synthetic_account(h['actor'], h['account'].id,
                d.WeixinRevokeInput(reason='独立合成读取请求时撤权'), database=h['database'])
        else:
            with h['database'].session() as db:
                if damage == 'owner':
                    db.execute(text('''UPDATE assistant_conversations SET owner_id=(
                        SELECT id FROM users WHERE username=:name) WHERE id=:id'''),
                        {'id':h['view']['scope']['conversation_id'], 'name':'另一合成律师'})
                else:
                    db.execute(text('UPDATE assistant_conversations SET archived_at=:at WHERE id=:id'),
                        {'id':h['view']['scope']['conversation_id'], 'at':now().isoformat()})
    async def changed(request, model):
        assert when == 'after_body', 'root authority must be checked before body parsing'
        value = await original(request, model); read.append(True); change()
        return value
    if when == 'before_body':
        change()
    monkeypatch.setattr(route, 'body_input', changed)
    response = h['client'].post(h['base'], headers=h['headers'], json=h['request'])
    assert response.status_code == expected, response.text
    assert read == ([True] if when == 'after_body' else [])
    with h['database'].session() as db:
        assert db.scalar(text('SELECT count(*) FROM weixin_peer_generations')) == 0


def test_http_commit_with_lost_ack_is_recovered_by_get_without_resubmitting(chat, monkeypatch):
    h = setup(chat)
    assert hasattr(conversation, 'append_generation'), 'D2g2 needs the CID-owned generation wrapper'
    original = conversation.append_generation; committed = []
    before = snapshot(h['database'])
    def lose(*args, **kwargs):
        result = original(*args, **kwargs); committed.append(result)
        raise RuntimeError('独立合成不可泄露丢回执内部错误')
    with monkeypatch.context() as patch:
        patch.setattr(conversation, 'append_generation', lose)
        patch.setattr(h['client']._transport, 'raise_server_exceptions', False)
        response = h['client'].post(h['base'], headers=h['headers'], json=h['request'])
    assert response.status_code == 500 and len(committed) == 1, response.text
    assert '不可泄露' not in response.text and h['request']['reason'] not in response.text
    found = h['client'].get(h['base']+'/by-request/'+h['request']['request_id'])
    assert found.status_code == 200, found.text
    receipt = found.json()
    assert set(receipt) == RECEIPT_KEYS and receipt['generation'] == 1
    assert receipt['scope'] == h['target']['scope'] and receipt['request_id'] == h['request']['request_id']
    stable = snapshot(h['database'])
    assert len(stable['weixin_peer_generations']) == 1
    assert {key:value for key,value in stable.items() if key != 'weixin_peer_generations'} == {
        key:value for key,value in before.items() if key != 'weixin_peer_generations'}
    assert h['client'].get(h['base']+'/by-request/'+h['request']['request_id']).json() == receipt
    assert snapshot(h['database']) == stable and len(committed) == 1


def test_target_cid_cannot_reverse_resolve_the_original_mapping(chat):
    h = setup(chat); saved(h); target_base = endpoint(h['target']['scope']['conversation_id'])
    before = snapshot(h['database'])
    found = h['client'].get(target_base+'/by-request/'+h['request']['request_id'])
    assert found.status_code == 200 and found.json() is None, found.text
    assert h['client'].post(target_base, headers=h['headers'], json=h['request']).status_code == 409
    assert snapshot(h['database']) == before
