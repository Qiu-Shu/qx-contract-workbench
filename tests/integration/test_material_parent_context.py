"""Cancelled parents and same-case user corrections at the material boundary."""
import asyncio
import json
from hashlib import sha256
from io import BytesIO
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import attachments, business, material_attempts, material_preparation, material_history, service
from cn_contract.assistant.runner import execute_attempt
from cn_contract.assistant.model_integrity import validate_model_records
from cn_contract.assistant.providers import attempts
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.security import ServiceError
from test_assistant_generation import world
from test_assistant_main_provider import config, KEY, server
from test_assistant_material_generation import material_world, grant, selection_for, response
from test_material_followup_history import followup, complete
from test_assistant_attachments import sample


def cancel_parent(w, selection):
    with w[0].session() as db:
        return service.cancel_run(w[1], selection.parent_business_run_id,
            d.AssistantCancelInput(request_id=uuid4()), db)


@pytest.mark.parametrize('moment', ['preview', 'enqueue', 'claim', 'settle'])
def test_cancelled_business_parent_cannot_start_or_adopt_material_generation(material_world, moment):
    w = material_world
    selection = selection_for(w, 'contract')

    async def scenario():
        provider = DeepSeekProvider.for_synthetic_loopback(config(), lambda:KEY, 'http://127.0.0.1:1/chat/completions')
        if moment == 'preview':
            cancel_parent(w, selection)
            with pytest.raises(ServiceError):
                material_preparation.preview(w[1], selection, w[0], config())
            return
        _, lease, basis = grant(w, selection, provider)
        if moment == 'enqueue':
            cancel_parent(w, selection)
            with w[0].session() as db, pytest.raises(ServiceError):
                material_attempts.enqueue(w[1], selection, basis, db, lease)
            return
        with w[0].session() as db:
            queued = material_attempts.enqueue(w[1], selection, basis, db, lease)
        if moment == 'claim':
            cancel_parent(w, selection)
            with w[0].session() as db:
                assert attempts.claim(w[1], queued.id, db, lease) is None
                result = attempts.read_attempt(w[1], queued.id, db)
                assert result.state == 'failed_before_send' and result.receipt.cost_status == 'not_sent'
                validate_model_records(db)
            return
        with w[0].session() as db:
            claimed = attempts.claim(w[1], queued.id, db, lease)
        assert claimed is not None
        cancel_parent(w, selection)
        with w[0].session() as db:
            reply = d.MainMaterialReply(state='received', usage=d.MainUsage(prompt_tokens=20, completion_tokens=10, total_tokens=30),
                output=d.MainMaterialCandidate(text='已取消任务的迟到回复', citations=(basis.manifest.sources[0].source_id,)))
            material_attempts.settle(w[1], queued.id, claimed[0], reply, db, lease)
            result = attempts.read_attempt(w[1], queued.id, db)
            assert result.output is None and result.receipt.cost_status == 'estimated'
            validate_model_records(db)

    asyncio.run(scenario())


def case_and_court(w):
    correction = followup(w, None, '整理这个案件。更正：实际交付25000元，附件写30000元，两种说法须分别保留。', new_task=True)
    with w[0].session() as db:
        parent = service._owned_run(w[1], correction.parent_business_run_id, db)
        case_result = business._record(parent, db)[1]
    court = followup(w, None, '根据当前案件模拟开庭。', workflow='court', new_task=True)
    return correction, case_result, court


def test_court_uses_same_case_user_correction_as_traceable_source_without_model_inference(material_world):
    w = material_world
    correction, case_result, court = case_and_court(w)
    basis = material_preparation.preview(w[1], court, w[0], config())
    assert basis.manifest.stable_task_id != case_result.task_id
    refs = [source.reference for source in basis.manifest.sources if source.reference.kind == 'message']
    assert len(refs) == 2
    assert refs[1].message_id == case_result.message_id
    assert refs[1].source_revision == case_result.scope.input_revision
    assert '实际交付25000元' in refs[1].quote and '附件写30000元' in refs[1].quote
    assert not basis.manifest.conversation_history
    result, _ = complete(w, court)
    with w[0].session() as db:
        validate_model_records(db)
        assert attempts.read_attempt(w[1], result.id, db) == result


def test_unbound_conversation_with_two_case_tasks_never_guesses_correction_owner(material_world):
    w = material_world
    followup(w, None, '整理案件甲，实际交付25000元。', new_task=True)
    followup(w, None, '整理案件乙，实际交付17000元。', new_task=True)
    court = followup(w, None, '根据当前案件模拟开庭。', workflow='court', new_task=True)
    basis = material_preparation.preview(w[1], court, w[0], config())
    assert [source.reference.quote for source in basis.manifest.sources if source.reference.kind == 'message'] == [basis.manifest.question]


def test_cancelled_parent_is_rechecked_after_secret_resolution_before_any_http(material_world):
    w = material_world
    selection = selection_for(w, 'contract')
    basis = material_preparation.preview(w[1], selection, w[0], config())
    with server(response(basis)) as (url, received, _):
        async def scenario():
            def resolve_secret():
                cancel_parent(w, selection)
                return KEY
            _, lease, approved = grant(w, selection,
                DeepSeekProvider.for_synthetic_loopback(config(), resolve_secret, url))
            with w[0].session() as db:
                queued = material_attempts.enqueue(w[1], selection, approved, db, lease)
            result = await execute_attempt(w[1], queued.id, w[0], lease)
            assert result.state == 'failed_before_send' and result.receipt.cost_status == 'not_sent'
            with w[0].session() as db:
                validate_model_records(db)
        asyncio.run(scenario())
        assert received == []


def test_cancelling_parent_preserves_completed_reply_and_historical_validation(material_world):
    w = material_world
    selection = selection_for(w, 'contract')
    completed, basis = complete(w, selection)
    cancel_parent(w, selection)
    with w[0].session() as db:
        assert attempts.read_attempt(w[1], completed.id, db) == completed
        validate_model_records(db)
    with pytest.raises(ServiceError):
        material_preparation.preview(w[1], selection, w[0], config())


@pytest.mark.parametrize('field,value', [('workspace_id', uuid4()), ('conversation_id', uuid4()),
    ('scope_kind', 'matter'), ('scope_ref', uuid4()), ('binding_revision', 2)])
def test_case_statement_context_never_crosses_a_fixed_binding(material_world, field, value):
    w = material_world
    _, _, court = case_and_court(w)
    with w[0].session() as db:
        from cn_contract.assistant import attachment_records
        conversation = service._owned(w[1], w[2], db)
        parent = service._owned_run(w[1], court.parent_business_run_id, db)
        result = business._record(parent, db)[1]
        changed = result.model_copy(update={'scope':result.scope.model_copy(update={field:value})})
        assert not material_history.statement_sources(db, changed, attachment_records.items(conversation, db))


def test_case_statement_context_is_bounded_to_eight_original_messages(material_world):
    w = material_world
    previous = None
    for number in range(10):
        selection = followup(w, previous, f'整理案件，补充第{number}条客户原话。', new_task=previous is None)
        with w[0].session() as db:
            parent = service._owned_run(w[1], selection.parent_business_run_id, db)
            previous = business._record(parent, db)[1].task_id
    court = followup(w, None, '根据当前案件模拟开庭。', workflow='court', new_task=True)
    basis = material_preparation.preview(w[1], court, w[0], config())
    statements = [source.reference.quote for source in basis.manifest.sources if source.reference.kind == 'message'][1:]
    assert statements == [f'整理案件，补充第{number}条客户原话。' for number in range(2, 10)]


def test_unbound_case_statement_requires_the_exact_current_material_set(material_world):
    w = material_world
    _, _, court = case_and_court(w)
    with w[0].session() as db:
        from cn_contract.assistant import attachment_records
        conversation = service._owned(w[1], w[2], db)
        parent = service._owned_run(w[1], court.parent_business_run_id, db)
        result = business._record(parent, db)[1]
        selected = attachment_records.items(conversation, db)
        assert material_history.statement_sources(db, result, selected)
        assert not material_history.statement_sources(db, result, ())
        assert not material_history.statement_sources(db, result,
            (selected[0].model_copy(update={'attachment_id':uuid4()}),))


def test_case_statement_is_revalidated_from_original_saved_message(material_world):
    w = material_world
    _, case, court = case_and_court(w)
    with w[0].session() as db:
        for name in db.scalars(text("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='assistant_messages'")).all():
            db.execute(text('DROP TRIGGER "' + name.replace('"', '""') + '"'))
        db.execute(text('UPDATE assistant_messages SET content=:content WHERE id=:id'),
            {'content':'篡改的客户说法', 'id':str(case.message_id)})
    with pytest.raises(ValueError):
        material_preparation.preview(w[1], court, w[0], config())


def test_pre_context_court_basis_and_reply_remain_readable(material_world, monkeypatch):
    w = material_world
    _, _, court = case_and_court(w)
    with monkeypatch.context() as old:
        old.setattr(material_history, 'statement_sources', lambda *args:())
        completed, basis = complete(w, court)
    assert len([source for source in basis.manifest.sources if source.reference.kind == 'message']) == 1
    with w[0].session() as db:
        validate_model_records(db)
        assert attempts.read_attempt(w[1], completed.id, db) == completed
    follow = followup(w, basis.manifest.stable_task_id, workflow='court')
    current = material_preparation.preview(w[1], follow, w[0], config())
    assert len([source for source in current.manifest.sources if source.reference.kind == 'message']) == 2
    assert current.manifest.conversation_history[1].content == completed.output.candidate.text


def test_correction_sources_and_prior_answers_share_the_32k_history_budget(material_world):
    w = material_world
    followup(w, None, '更正实际交付25000元。' + '客户说法待核。' * 800, new_task=True)
    selection = followup(w, None, '根据当前案件模拟开庭。', workflow='court', new_task=True)
    for number in range(2):
        completed, basis = complete(w, selection, f'第{number}轮。' + '演练草稿。' * 700)
        selection = followup(w, basis.manifest.stable_task_id, workflow='court')
    basis = material_preparation.preview(w[1], selection, w[0], config())
    context = [source for source in basis.manifest.sources if source.reference.kind == 'message'][1:]
    assert context and '25000' in context[0].reference.quote
    assert len(basis.manifest.conversation_history) == 2
    assert basis.manifest.conversation_history[1].message_id == completed.output.id
    raw = lambda values:json.dumps([item.model_dump(mode='json') for item in values], ensure_ascii=False, separators=(',', ':')).encode()
    assert len(raw(context)) + len(raw(basis.manifest.conversation_history)) <= 32768
    with w[0].session() as db:
        validate_model_records(db)


def append_material(w):
    raw = sample('第二份独立虚构附件：交货及收款记录待核。')
    w[0]._assistant_synthetic_hashes = w[0]._assistant_synthetic_hashes | {sha256(raw).hexdigest()}
    current = attachments.read_materials(w[1], w[2], database=w[0])
    uploaded = attachments.ingest_attachment(w[1], w[2], d.AssistantAttachmentInput(
        request_id=uuid4(), expected_scope=current.scope, original_name='虚构补充附件.docx',
        mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        policy=d.AssistantMaterialPolicy(local_processing_accepted=True)), BytesIO(raw), database=w[0])
    current = attachments.read_materials(w[1], w[2], database=w[0])
    attachments.parse_attachment(w[1], w[2], uploaded.attachment.id,
        d.AssistantAttachmentParseInput(request_id=uuid4(), expected_scope=current.scope), database=w[0])
    return uploaded.attachment.id


@pytest.mark.parametrize('change', ['added', 'removed', 'reparsed'])
def test_case_correction_survives_added_materials_but_not_removed_or_changed_sources(material_world, change):
    w = material_world
    first = followup(w, None, '整理案件，更正实际交付25000元，附件仍写30000元。', new_task=True)
    with w[0].session() as db:
        original = business._record(service._owned_run(w[1], first.parent_business_run_id, db), db)[1]
    added = append_material(w)
    current = attachments.read_materials(w[1], w[2], database=w[0])
    if change == 'removed':
        attachments.select_materials(w[1], w[2], d.AssistantMaterialSelectionInput(request_id=uuid4(),
            expected_scope=current.scope, items=tuple(item for item in current.items if item.attachment_id == added)), database=w[0])
    elif change == 'reparsed':
        attachments.parse_attachment(w[1], w[2], next(item.attachment_id for item in current.items if item.attachment_id != added),
            d.AssistantAttachmentParseInput(request_id=uuid4(), expected_scope=current.scope), database=w[0])
    followup(w, original.task_id, '继续整理，已补充新的附件。')
    court = followup(w, None, '根据当前案件模拟开庭。', workflow='court', new_task=True)
    basis = material_preparation.preview(w[1], court, w[0], config())
    context = [source.reference for source in basis.manifest.sources if source.reference.kind == 'message'][1:]
    assert any(source.message_id == original.message_id and '25000' in source.quote for source in context) == (change == 'added')
    if change == 'added':
        result, _ = complete(w, court)
        with w[0].session() as db:
            validate_model_records(db)
