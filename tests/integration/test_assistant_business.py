"""Unified local business actions use only fictional input and existing records."""
from uuid import uuid4

import pytest

from test_assistant_routes import chat, native, sign_in, create
from test_assistant_attachment_routes import attachments, upload


def submit(client, headers, view, content, **extra):
    body = dict(request_id=str(uuid4()), expected_scope=view['scope'],
                expected_composer_revision=view['composer_revision'], content=content, **extra)
    url = '/api/assistant/conversations/' + view['scope']['conversation_id'] + '/business'
    return client.post(url, headers=headers, json=body), url, body


@pytest.mark.parametrize('content, workflow', [
    ('我是甲方，帮我审查并给出最小修改建议', 'contract'),
    ('整理这个案件并起草起诉状', 'case'),
    ('根据现有材料模拟开庭', 'court'),
])
def test_mvp_natural_commands_select_existing_workflow(chat, content, workflow):
    client, _, _ = chat
    headers = sign_in(client)
    result, _, _ = submit(client, headers, create(client, headers), content)
    assert result.status_code == 200
    assert result.json()['workflow'] == workflow
    assert result.json()['task_id']


def test_reception_is_saved_in_chat_with_one_receipt_and_source(chat):
    client, _, _ = chat
    headers = sign_in(client)
    view = create(client, headers)
    result, url, body = submit(client, headers, view, '客户咨询：虚构张先生称借给朋友三万元，想了解需要准备什么材料。')
    assert result.status_code == 200, result.text
    saved = result.json()
    assert saved['workflow'] == 'sales'
    assert saved['state'] == 'completed'
    assert saved['intake_id']
    assert saved['review_status'] == 'unverified'
    assert saved['mode'] == 'local_preparation'
    assert '客户诉求' in saved['text'] and '待补' in saved['text']
    assert client.post(url, headers=headers, json=body).json() == saved
    assert client.get(url + '/by-request/' + body['request_id']).json() == saved
    messages = client.get(url.removesuffix('/business')).json()['messages']
    assert [message['role'] for message in messages] == ['user', 'assistant']
    assert messages[-1]['content'] == saved['text']
    assert client.get('/api/intakes').json()['items'][0]['id'] == saved['intake_id']


def test_business_checks_owner_before_body_and_retains_idempotency(chat):
    client, _, _ = chat
    headers = sign_in(client)
    view = create(client, headers)
    result, url, body = submit(client, headers, view, '客户咨询：虚构合同款尚未收到。')
    assert result.status_code == 200
    assert client.post(url, headers=headers, json={**body, 'content':'不同指令'}).status_code == 409
    other = sign_in(client, '另一合成律师')
    assert client.post(url, headers=other, content='not-json').status_code == 403
    assert client.get(url + '/by-request/' + body['request_id']).status_code == 403


def test_contract_input_then_material_keeps_one_task_and_old_result(attachments):
    client, _, headers, base, _, _, _ = attachments
    first, url, _ = submit(client, headers, client.get(base).json(), '帮我审查这个合同')
    assert first.status_code == 200
    assert first.json()['contract_draft_id']
    assert first.json()['state'] == 'awaiting_input'
    original = upload(attachments, value={**attachments[4], 'expected_scope':client.get(base).json()['scope']})
    assert original.status_code == 201
    second, _, _ = submit(client, headers, client.get(base).json(), '补充主合同，请继续审查')
    assert second.status_code == 200, second.text
    assert second.json()['task_id'] == first.json()['task_id']
    assert second.json()['contract_draft_id'] == first.json()['contract_draft_id']
    draft = client.get('/api/task-drafts/' + first.json()['contract_draft_id']).json()
    assert len(draft['events']) == 2
    assert draft['events'][1]['media'][0]['attachment_id'] == original.json()['attachment']['id']
    assert client.get(url + '/by-request/' + first.json()['request_id']).json() == first.json()


def test_case_and_court_reuse_exact_material_sources(attachments):
    client, _, headers, base, _, _, _ = attachments
    original = upload(attachments).json()['attachment']
    parsed = client.post(base + '/attachments/' + original['id'] + '/parses', headers=headers,
        json={'request_id':str(uuid4()), 'expected_scope':client.get(base).json()['scope']})
    assert parsed.status_code == 200
    case, _, _ = submit(client, headers, client.get(base).json(), '整理这个案件')
    assert case.status_code == 200, case.text
    assert case.json()['workflow'] == 'case'
    assert case.json()['source_refs'][0]['attachment_id'] == original['id']
    assert '材料目录' in case.json()['text'] and '时间线' in case.json()['text']
    court, _, _ = submit(client, headers, client.get(base).json(), '站在对方律师和法官角度模拟')
    assert court.status_code == 200, court.text
    assert court.json()['workflow'] == 'court'
    assert court.json()['source_refs'] == case.json()['source_refs']
    assert '对方律师' in court.json()['text'] and '法官追问' in court.json()['text']
    assert '通用准备提纲' in court.json()['text']


def test_new_contract_task_does_not_overwrite_previous_and_ambiguity_stops(chat):
    client, _, _ = chat
    headers = sign_in(client)
    view = create(client, headers)
    first, url, _ = submit(client, headers, view, '帮我审查这个合同')
    second, _, _ = submit(client, headers, client.get(url.removesuffix('/business')).json(), '重新审查合同')
    assert first.json()['task_id'] != second.json()['task_id']
    third, _, _ = submit(client, headers, client.get(url.removesuffix('/business')).json(), '再补充一份材料')
    assert third.json()['task_id'] is None
    assert third.json()['state'] == 'awaiting_input'
    assert '哪个' in third.json()['text']


def test_business_history_survives_cancel_and_restore_quarantine(chat):
    from cn_contract.assistant import business, service
    client, database, _ = chat
    headers = sign_in(client)
    first, url, _ = submit(client, headers, create(client, headers), '帮我审查这个合同')
    assert client.post('/api/assistant/runs/' + first.json()['run_id'] + '/cancel', headers=headers,
        json={'request_id':str(uuid4())}).status_code == 200
    assert client.get(url).status_code == 200
    second, _, _ = submit(client, headers, client.get(url.removesuffix('/business')).json(), '重新审查合同')
    with database.session() as db:
        service.quarantine_runs(db)
        business.validate_business_records(db, allowed=True)
    assert client.get(url + '/by-request/' + second.json()['request_id']).status_code == 200


def test_business_validator_rejects_unrecognized_event(chat):
    from cn_contract.assistant import business
    from sqlalchemy import text
    client, database, _ = chat
    headers = sign_in(client)
    result, _, _ = submit(client, headers, create(client, headers), '客户咨询：虚构事项。')
    with database.session() as db:
        business.validate_business_records(db, allowed=True)
        db.execute(text("INSERT INTO assistant_run_events VALUES(:id,4,'business.extra','internal','{}',:at)"),
            {'id':result.json()['run_id'], 'at':result.json()['created_at']})
        with pytest.raises(ValueError):
            business.validate_business_records(db, allowed=True)


def test_multiple_intents_never_inherit_previous_sales_task(chat):
    client, _, _ = chat
    headers = sign_in(client)
    first, url, _ = submit(client, headers, create(client, headers), '客户咨询：虚构事项。')
    result, _, _ = submit(client, headers, client.get(url.removesuffix('/business')).json(),
                         '整理这个案件并进行模拟法庭')
    assert result.status_code == 200
    assert result.json()['workflow'] is None
    assert result.json()['task_id'] is None
    assert result.json()['state'] == 'awaiting_input'


def test_historical_evidence_retains_fixed_revision_and_source(chat):
    from test_evidence_worksheet import material, request
    from cn_contract.assistant import business
    client, database, _ = chat
    headers = sign_in(client)
    view = create(client, headers)
    base = '/api/assistant/conversations/' + view['scope']['conversation_id']
    _, _, source = material(client, headers, base, database)
    fact = dict(id=str(uuid4()), category='other', content='虚构交付待核',
                event_date='2026-01-01', review_state='pending', source=source)
    assert client.post(base + '/evidence/commits', headers=headers,
        json=request(client.get(base + '/evidence').json(), [fact])).status_code == 200
    assert client.put(base + '/materials', headers=headers, json={'request_id':str(uuid4()),
        'expected_scope':client.get(base).json()['scope'], 'items':[]}).status_code == 200
    result, _, _ = submit(client, headers, client.get(base).json(), '整理这个案件')
    assert result.status_code == 200, result.text
    assert result.json()['evidence']['revision'] == 1
    assert result.json()['evidence']['fact_ids'] == [fact['id']]
    assert result.json()['evidence']['historical_ids'] == [fact['id']]
    assert '历史来源' in result.json()['text']
    with database.session() as db:
        business.validate_business_records(db, allowed=True)


def test_forged_session_owner_is_rejected(chat):
    from cn_contract.assistant import business
    from sqlalchemy import text
    client, database, _ = chat
    headers = sign_in(client)
    result, _, _ = submit(client, headers, create(client, headers), '客户咨询：虚构事项。')
    sign_in(client, '另一合成律师')
    with database.session() as db:
        other = db.scalar(text('SELECT s.id FROM sessions s JOIN users u ON u.id=s.user_id WHERE u.username=:name'), {'name':'另一合成律师'})
        triggers = list(db.execute(text("SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name='assistant_runs'")))
        for name, _ in triggers:
            db.execute(text('DROP TRIGGER "'+name+'"'))
        db.execute(text('UPDATE assistant_runs SET session_id=:session WHERE id=:id'), {'session':other,'id':result.json()['run_id']})
        for _, sql in triggers:
            db.execute(text(sql))
        with pytest.raises(ValueError):
            business.validate_business_records(db, allowed=True)


def test_business_round_trip_is_readonly_and_preserves_receipts(native, tmp_path):
    from pathlib import Path
    from fastapi.testclient import TestClient
    from cn_contract.ops import workspace_backup
    from cn_contract.web.local_server import build_local_app
    from tests.helpers.legacy_assistant_backup import PASSPHRASE
    app, root = native
    with TestClient(app) as client:
        headers = sign_in(client)
        first, url, body = submit(client, headers, create(client, headers), '客户咨询：独立虚构资料。')
        second, _, _ = submit(client, headers, client.get(url.removesuffix('/business')).json(), '帮我审查合同')
        assert second.status_code == 200
    archive = tmp_path/'合成统一业务.qxbak'
    workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
    restored = workspace_backup.restore_workspace_backup(archive, tmp_path/'restored', PASSPHRASE)
    restored_root = Path(restored['restored_root'])
    restored_app = build_local_app(restored_root, data_parent=restored_root.parent.parent)
    try:
        with TestClient(restored_app) as client:
            headers = sign_in(client)
            assert client.get(url + '/by-request/' + body['request_id']).json() == first.json()
            assert len(client.get(url).json()) == 2
            assert client.post(url, headers=headers, json=body).status_code == 409
    finally:
        restored_app.state.database.engine.dispose()


def test_explicit_restart_overrides_selected_task_and_wrong_workflow_is_not_revocation(chat):
    client, _, _ = chat
    headers = sign_in(client)
    first, url, _ = submit(client, headers, create(client, headers), '帮我审查合同')
    base = url.removesuffix('/business')
    second, _, _ = submit(client, headers, client.get(base).json(), '重新审查合同', task_id=first.json()['task_id'])
    assert second.status_code == 200
    assert second.json()['task_id'] != first.json()['task_id']
    assert second.json()['contract_draft_id'] != first.json()['contract_draft_id']
    mismatch, _, _ = submit(client, headers, client.get(base).json(), '模拟法庭',
                            workflow='court', task_id=first.json()['task_id'])
    assert mismatch.status_code == 409
    assert client.get(base).status_code == 200
