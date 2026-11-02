"""Trademark factor candidates on synthetic files and loopback transport only."""
import asyncio
import json
from io import BytesIO
from pathlib import Path

import pytest
from docx import Document
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import material_attempts, material_preparation
from cn_contract.assistant.model_integrity import validate_model_records
from cn_contract.assistant.providers import attempts
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.assistant.providers.policy import encoded
from cn_contract.assistant.runner import execute_attempt
from cn_contract.ops import backup, workspace_backup
from cn_contract.persistence import Database
from cn_contract.security import ServiceError, authenticate, login
from tests.helpers.case_evidence import add_document, response
from tests.helpers.legacy_assistant_backup import PASSPHRASE
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_material_generation import grant
from tests.integration.test_assistant_material_routes import boot
from tests.integration.test_assistant_main_provider import config, KEY, server
from tests.integration.test_material_followup_history import followup


@pytest.fixture
def trademark_world(world):
    database, actor, conversation, _, _ = world
    database._assistant_synthetic_hashes = frozenset()
    w = (database, actor, conversation.scope.conversation_id, None)
    add_document(w, ['独立虚构材料：[权利主张方甲]称拥有“合成甲标”，登记、许可与有效状态均未核实。',
        '独立虚构材料：[被控方乙]称使用“合成甲记”销售水杯，双方标识、商品和相关公众待比较。',
        '独立虚构材料：乙称独立设计，无销售地域或实际混淆记录；标识图片未提供。'
        '页面 https://example.invalid/synthetic-brand 仅为原文链接，尚未读取。'])
    return w


def selection_for(w, task_id=None, question='请做商标侵权初筛。'):
    return followup(w, task_id, question, new_task=task_id is None)


def execute(w, selection, value=None):
    basis = material_preparation.preview(w[1], selection, w[0], config())
    assert getattr(basis.manifest, 'trademark_triage', None) is not None
    from tests.helpers.trademark_triage import draft_for
    body = response(draft_for(basis.manifest) if value is None else value)
    with server(body) as (url, received, _):
        async def scenario():
            _, lease, approved = grant(w, selection,
                DeepSeekProvider.for_synthetic_loopback(config(), lambda: KEY, url))
            assert approved == basis
            with w[0].session() as db:
                queued = material_attempts.enqueue(w[1], selection, approved, db, lease)
            result = await execute_attempt(w[1], queued.id, w[0], lease)
            assert await execute_attempt(w[1], queued.id, w[0], lease) == result
            with w[0].session() as db:
                assert attempts.read_attempt(w[1], queued.id, db) == result
                validate_model_records(db)
            return result
        result = asyncio.run(scenario())
        assert len(received) == 1
        assert json.loads(json.loads(received[0]['body'])['messages'][1]['content']) == basis.manifest.model_dump(mode='json')
    return result, basis


def neutral_reply(w, selection):
    from tests.helpers.trademark_triage import draft_for
    manifest = material_preparation.preview(w[1], selection, w[0], config()).manifest
    value = draft_for(manifest)
    sources = [s for s in manifest.sources if s.reference.kind == 'document' and s.reference.anchor.quote]
    value['quotes'] = [dict(id=f'q{i+1}', source_id=s.source_id, start=0,
        end=len(s.reference.anchor.quote), exact_quote=s.reference.anchor.quote)
        for i, s in enumerate((sources[0], sources[-1]))]
    for factor in value['factors']:
        factor.update(holder=[], respondent=[], neutral=[])
    value['factors'][0]['neutral'] = [dict(text='两份材料仅为虚构的待核记载，未确定任何一方角色。', quote_ids=['q1', 'q2'])]
    return value


@pytest.mark.parametrize('neutral', [False, True])
def test_trademark_supplement_stays_in_one_task_and_roundtrips_word_and_archive(trademark_world, tmp_path, neutral):
    w = trademark_world
    chosen = selection_for(w)
    first, basis = execute(w, chosen, neutral_reply(w, chosen) if neutral else None)
    assert first.output is not None and first.output.review_status == 'unverified'
    assert basis.manifest.trademark_triage.method_id == 'trademark-triage-v5'
    assert basis.manifest.case_method is None and basis.manifest.criminal_analysis is None
    assert basis.manifest.contract_review is None and basis.manifest.hearing is None
    candidate = first.output.candidate.trademark_triage
    assert candidate.format_version == 'trademark-triage-v2'
    assert tuple(f.kind for f in candidate.factors) == ('rights_basis', 'sign_similarity',
        'goods_services', 'relevant_public', 'distinctiveness', 'intent', 'actual_confusion',
        'market_overlap')
    assert all(f.unresolved for f in candidate.factors)
    sources = {s.source_id: s.reference for s in basis.manifest.sources}
    for quote in candidate.quotes:
        source = sources[quote.source_id]
        assert source.kind == 'document'
        assert source.anchor.quote[quote.start:quote.end] == quote.exact_quote
        assert quote.exact_quote in first.output.candidate.text
    with w[0].session() as db:
        old_input = db.scalar(text('SELECT input_json FROM assistant_model_attempts WHERE id=:id'), {'id': str(first.id)})
        old_output = db.scalar(text('SELECT output_json FROM assistant_model_outputs WHERE attempt_id=:id'), {'id': str(first.id)})
    add_document(w, ['独立虚构补充材料：[客户丁]称曾将两个名称混淆，身份、时间、场景和原始记录待核。'])
    chosen = selection_for(w, basis.manifest.stable_task_id)
    second, updated = execute(w, chosen, neutral_reply(w, chosen) if neutral else None)
    assert second.output is not None and second.output.review_status == 'unverified'
    assert updated.manifest.stable_task_id == basis.manifest.stable_task_id
    assert len(updated.manifest.materials) == len(basis.manifest.materials) + 1
    assert updated.manifest.conversation_history[1].content == first.output.candidate.text
    if neutral:
        observation = second.output.candidate.trademark_triage.factors[0]
        assert not observation.holder and not observation.respondent
        assert observation.neutral[0].quote_ids == ('q1', 'q2')
        assert '待核观察：两份材料仅为虚构的待核记载' in second.output.candidate.text
        quote = second.output.candidate.trademark_triage.quotes[1]
        assert quote.source_id not in {s.source_id for s in basis.manifest.sources}
        assert '客户丁' in quote.exact_quote
    with w[0].session() as db:
        assert db.scalar(text('SELECT input_json FROM assistant_model_attempts WHERE id=:id'), {'id': str(first.id)}) == old_input
        assert db.scalar(text('SELECT output_json FROM assistant_model_outputs WHERE attempt_id=:id'), {'id': str(first.id)}) == old_output
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 2
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_evidence_revisions')) == 0
    with boot(w, tmp_path) as http:
        exported = http.client.get(http.url + '/material-generations/' + str(second.id) + '/document')
        assert exported.status_code == 200, exported.text
        body = '\n'.join(p.text for p in Document(BytesIO(exported.content)).paragraphs)
        assert second.output.candidate.text in body and '待律师核对' in body
        assert '合成甲标' in body and ('客户丁' if neutral else '合成甲记') in body
    root = Path(w[0].engine.url.database).parent
    archive = tmp_path / 'trademark-synthetic.qxbak'
    workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
    restored_info = workspace_backup.restore_workspace_backup(archive, tmp_path / 'trademark-restored', PASSPHRASE)
    target = Path(restored_info['restored_root'])
    restored = Database('sqlite:///' + str(target / 'workbench.db'), target / 'protected',
        w[0].settings, initialize_schema=False)
    backup._mark_storage_flags(restored)
    try:
        with restored.session() as db:
            token, _ = login('lawyer', 'fixture123', db)
            actor = authenticate(token, db)
            assert attempts.read_attempt(actor, first.id, db) == first
            assert attempts.read_attempt(actor, second.id, db) == second
            validate_model_records(db)
    finally:
        restored.engine.dispose()


@pytest.mark.parametrize('damage', ['old_format', 'unknown_source', 'message_quote'])
def test_invalid_trademark_reply_preserves_usage_and_never_resends(trademark_world, damage):
    from tests.helpers.trademark_triage import draft_for
    w = trademark_world
    selection = selection_for(w)
    basis = material_preparation.preview(w[1], selection, w[0], config())
    value = draft_for(basis.manifest)
    if damage == 'old_format':
        value = {'text': '旧格式不得替代商标八组因素校验。', 'citations': [basis.manifest.sources[0].source_id]}
    elif damage == 'unknown_source':
        value['quotes'][0]['source_id'] = 'f' * 64
    else:
        source = basis.manifest.sources[0]
        value['quotes'][0].update(source_id=source.source_id, start=0,
            end=len(source.reference.quote), exact_quote=source.reference.quote)
    result, _ = execute(w, selection, value)
    assert result.state == 'received' and result.output is None
    assert result.receipt.error_code == 'MODEL_OUTPUT_INVALID'
    assert result.receipt.usage.total_tokens == 42 and result.receipt.cost_status == 'estimated'
    with w[0].session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_outputs')) == 0
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 1
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_receipts')) == 1


@pytest.mark.parametrize('damage', ['derived_text', 'exact_quote', 'neutral_refs', 'neutral_text'])
def test_saved_trademark_tampering_blocks_read_export_and_followup(trademark_world, tmp_path, damage):
    w = trademark_world
    chosen = selection_for(w)
    result, basis = execute(w, chosen, neutral_reply(w, chosen) if damage.startswith('neutral') else None)
    assert result.output is not None
    with w[0].session() as db:
        value = json.loads(db.scalar(text('SELECT output_json FROM assistant_model_outputs WHERE attempt_id=:id'),
            {'id': str(result.id)}))
        if damage == 'derived_text':
            value['candidate']['text'] += '\n擅改为侵权已经成立。'
        elif damage == 'exact_quote':
            quote = value['candidate']['trademark_triage']['quotes'][0]
            quote['exact_quote'] = '篡' + quote['exact_quote'][1:]
        else:
            observation = value['candidate']['trademark_triage']['factors'][0]['neutral'][0]
            if damage == 'neutral_refs':
                observation['quote_ids'] = ['q1']
            else:
                observation['text'] += '篡改观察。'
        changed = encoded(d.MainMaterialOutputView.model_validate(value))
        triggers = db.execute(text("SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name='assistant_model_outputs'")).all()
        for name, _ in triggers:
            db.execute(text('DROP TRIGGER "' + name.replace('"', '""') + '"'))
        db.execute(text('UPDATE assistant_model_outputs SET output_json=:value WHERE attempt_id=:id'),
            {'value': changed, 'id': str(result.id)})
        for _, sql in triggers:
            db.execute(text(sql))
    with w[0].session() as db:
        with pytest.raises(ValueError):
            attempts.read_attempt(w[1], result.id, db)
        with pytest.raises(ValueError):
            validate_model_records(db)
    with boot(w, tmp_path) as http:
        rejected = http.client.get(http.url + '/material-generations/' + str(result.id) + '/document')
        assert rejected.status_code == 409, rejected.text
    next_selection = selection_for(w, basis.manifest.stable_task_id)
    with pytest.raises(ValueError):
        material_preparation.preview(w[1], next_selection, w[0], config())


def test_preupgrade_ordinary_case_keeps_original_queued_bytes(trademark_world, monkeypatch):
    w = trademark_world
    selection = selection_for(w, question='请整理材料。')
    with monkeypatch.context() as legacy:
        legacy.setattr(material_preparation, 'trademark_triage_for', lambda *args: None)
        basis = material_preparation.preview(w[1], selection, w[0], config())
    value = {'text': '普通案件旧版待核候选。', 'citations': [basis.manifest.sources[0].source_id]}
    with server(response(value)) as (url, received, _):
        async def scenario():
            with monkeypatch.context() as legacy:
                legacy.setattr(material_preparation, 'trademark_triage_for', lambda *args: None)
                _, lease, approved = grant(w, selection,
                    DeepSeekProvider.for_synthetic_loopback(config(), lambda: KEY, url))
                with w[0].session() as db:
                    queued = material_attempts.enqueue(w[1], selection, approved, db, lease)
                    saved = db.scalar(text('SELECT input_json FROM assistant_model_attempts WHERE id=:id'), {'id': str(queued.id)})
            assert 'trademark_triage' not in approved.manifest.model_dump(mode='json')
            result = await execute_attempt(w[1], queued.id, w[0], lease)
            assert result.output is not None and result.output.candidate.text == value['text']
            assert 'trademark_triage' not in result.output.candidate.model_dump(mode='json')
            assert await execute_attempt(w[1], queued.id, w[0], lease) == result
            with w[0].session() as db:
                assert db.scalar(text('SELECT input_json FROM assistant_model_attempts WHERE id=:id'), {'id': str(queued.id)}) == saved
                validate_model_records(db)
        asyncio.run(scenario())
        assert len(received) == 1
    current = material_preparation.preview(w[1], selection_for(w, basis.manifest.stable_task_id), w[0], config())
    assert current.manifest.trademark_triage.method_id == 'trademark-triage-v5'
    assert current.manifest.conversation_history[1].content == value['text']


def test_revoked_trademark_lease_never_resolves_key_or_sends(trademark_world):
    from tests.helpers.trademark_triage import draft_for
    w = trademark_world
    selection = selection_for(w)
    basis = material_preparation.preview(w[1], selection, w[0], config())
    keys = []
    with server(response(draft_for(basis.manifest))) as (url, received, _):
        async def scenario():
            registry, lease, approved = grant(w, selection, DeepSeekProvider.for_synthetic_loopback(
                config(), lambda: keys.append('unexpected') or KEY, url))
            with w[0].session() as db:
                queued = material_attempts.enqueue(w[1], selection, approved, db, lease)
            registry.revoke(w[1].session_id)
            result = await execute_attempt(w[1], queued.id, w[0], lease)
            assert result.state == 'failed_before_send' and result.output is None
            assert result.receipt.cost_status == 'not_sent'
            assert await execute_attempt(w[1], queued.id, w[0], lease) == result
            with w[0].session() as db:
                validate_model_records(db)
        asyncio.run(scenario())
        assert received == [] and keys == []


@pytest.mark.parametrize('question', ['请做知识产权侵权初筛。',
    '请做商标与著作权侵权初筛。', '请做商标和专利侵权分析。'])
def test_unsupported_or_mixed_ip_is_rejected_before_a_model_attempt(trademark_world, question):
    w = trademark_world
    selection = selection_for(w, question=question)
    with pytest.raises(ServiceError) as rejected:
        material_preparation.preview(w[1], selection, w[0], config())
    assert rejected.value.code == 'IP_SCOPE_UNSUPPORTED'
    with w[0].session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0


def test_trademark_request_cannot_drop_existing_criminal_material_policy(trademark_world):
    w = trademark_world
    selection_for(w, question='请做刑事证据分析。')
    request = selection_for(w)
    with pytest.raises(ServiceError) as rejected:
        material_preparation.preview(w[1], request, w[0], config())
    assert rejected.value.code == 'CRIMINAL_SCOPE_REQUIRED'
    with w[0].session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0


def test_empty_docx_requires_readable_text_before_trademark_model_attempt(world):
    database, actor, conversation, _, _ = world
    database._assistant_synthetic_hashes = frozenset()
    w = (database, actor, conversation.scope.conversation_id, None)
    add_document(w, [])
    selection = selection_for(w)
    with pytest.raises(ServiceError) as rejected:
        material_preparation.preview(actor, selection, database, config())
    assert rejected.value.code == 'MATERIAL_NOT_READABLE'
    with database.session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0


def test_old_criminal_hold_resume_request_keeps_policy_without_model_attempt(trademark_world, monkeypatch):
    from cn_contract.assistant import business
    w = trademark_world
    with monkeypatch.context() as previous:
        previous.setitem(business._WORKFLOW_WORDS, 'case', tuple(
            word for word in business._WORKFLOW_WORDS['case'] if word not in business._IP_WORDS))
        selection_for(w, question='不要分析\n请整理案件，但不做商标侵权\n刑事证据分析')
    selection = selection_for(w)
    with pytest.raises(ServiceError) as rejected:
        material_preparation.preview(w[1], selection, w[0], config())
    assert rejected.value.code == 'CRIMINAL_SCOPE_REQUIRED'
    with w[0].session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0


@pytest.mark.parametrize('question', [
    '请整理案件，不做刑事分析，继续整理材料。',
    '不做辩护策略，仅整理刑事证据分析。',
])
def test_current_mixed_denial_cannot_trigger_frozen_criminal_method(trademark_world, question):
    w = trademark_world
    selection = selection_for(w, question=question)
    with pytest.raises(ServiceError) as rejected:
        material_preparation.preview(w[1], selection, w[0], config())
    assert rejected.value.code == 'MATERIAL_INSTRUCTION_CONFLICT'
    with w[0].session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0
