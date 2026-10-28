"""Fictional persisted replies support follow-ups without widening their scope."""
import asyncio
import json
import stat
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import attachments, business, material_attempts, material_preparation, service
from cn_contract.assistant import material_codec, material_history
from cn_contract.assistant.model_integrity import validate_model_records
from cn_contract.assistant.providers import attempts
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.security import ServiceError
from test_assistant_generation import world
from test_assistant_material_generation import material_world, grant, selection_for
from test_assistant_main_provider import config, KEY


def followup(w, task_id, content='把第二条修改得更简洁。', *, new_task=False, workflow='case'):
    database, actor, cid, _ = w
    with database.session() as db:
        view = service.read_conversation(actor, cid, db)
        parent = business.submit(actor, cid, d.BusinessInput(request_id=uuid4(), expected_scope=view.scope,
            expected_composer_revision=view.composer_revision, content=content, workflow=workflow,
            task_id=None if new_task else task_id, new_task=new_task), db)
        view = service.read_conversation(actor, cid, db)
    return d.MainMaterialSelection(request_id=uuid4(), expected_scope=view.scope,
        expected_composer_revision=view.composer_revision, parent_business_run_id=parent.run_id)


def complete(w, selection, answer='第一条：核对原件。第二条：提供还款记录以核实已偿还款项。', *, state='received', cancel=False):
    return asyncio.run(_complete(w, selection, answer, state=state, cancel=cancel))


async def _complete(w, selection, answer, *, state, cancel):
    database, actor, _, _ = w
    provider = DeepSeekProvider.for_synthetic_loopback(config(), lambda:KEY, 'http://127.0.0.1:1/chat/completions')
    _, lease, basis = grant(w, selection, provider)
    with database.session() as db:
        first = material_attempts.enqueue(actor, selection, basis, db, lease)
        claim = attempts.claim(actor, first.id, db, lease)
        assert claim is not None
        if cancel:
            db.execute(text('UPDATE assistant_runs SET cancel_requested=1 WHERE id=:id'), {'id':str(first.run_id)})
        reply = d.MainMaterialReply(state=state, error_code='BLOCKED_LIVE' if state != 'received' else None,
            output=d.MainMaterialCandidate(text=answer, citations=(basis.manifest.sources[0].source_id,)) if state == 'received' else None)
        material_attempts.settle(actor, first.id, claim[0], reply, db, lease)
        result = attempts.read_attempt(actor, first.id, db)
    return result, basis


def test_followup_reuses_only_saved_question_and_successful_reply_and_replays_archive(material_world):
    w = material_world
    first, basis = complete(w, selection_for(w))
    next_selection = followup(w, basis.manifest.stable_task_id)
    next_basis = material_preparation.preview(w[1], next_selection, w[0], config())
    history = next_basis.manifest.conversation_history
    assert [(item.role, item.content) for item in history] == [
        ('user', basis.manifest.question), ('assistant', first.output.candidate.text)]
    assert history[0].message_id == basis.manifest.sources[0].reference.message_id
    assert history[1].message_id == first.output.id
    assert 'conversation_history' not in basis.manifest.model_dump(mode='json')
    second, _ = complete(w, next_selection, '第二条：请提供还款记录。')
    third_selection = followup(w, basis.manifest.stable_task_id, '继续合并前两次意见。')
    third = material_preparation.preview(w[1], third_selection, w[0], config())
    assert [item.content for item in third.manifest.conversation_history][1::2] == [first.output.candidate.text, second.output.candidate.text]
    with w[0].session() as db:
        validate_model_records(db)


def test_other_task_is_never_included_in_material_history(material_world):
    w = material_world
    first, basis = complete(w, selection_for(w), '同一任务专属回答')
    other = followup(w, basis.manifest.stable_task_id, '新建任务整理另一个争议。', new_task=True)
    unrelated, unrelated_basis = complete(w, other, '另一个任务的私有回答')
    next_selection = followup(w, basis.manifest.stable_task_id)
    next_basis = material_preparation.preview(w[1], next_selection, w[0], config())
    assert [item.content for item in next_basis.manifest.conversation_history][1::2] == [first.output.candidate.text]
    assert unrelated.output.id not in {item.message_id for item in next_basis.manifest.conversation_history}


@pytest.mark.parametrize('state,cancel', [('sent_unknown', False), ('received', True)])
def test_unknown_and_cancelled_attempts_do_not_become_history(material_world, state, cancel):
    w = material_world
    failed, basis = complete(w, selection_for(w), state=state, cancel=cancel)
    assert failed.output is None
    selection = followup(w, basis.manifest.stable_task_id)
    assert not material_preparation.preview(w[1], selection, w[0], config()).manifest.conversation_history


@pytest.mark.parametrize('change', ['wire', 'receipt', 'event', 'source'])
def test_saved_history_is_revalidated_before_disclosure(material_world, change):
    w = material_world
    first, basis = complete(w, selection_for(w))
    selection = followup(w, basis.manifest.stable_task_id)
    with w[0].session() as db:
        triggers = db.scalars(text("SELECT name FROM sqlite_master WHERE type='trigger'")).all()
        for name in triggers:
            db.execute(text('DROP TRIGGER "' + name.replace('"', '""') + '"'))
        if change == 'wire':
            db.execute(text("UPDATE assistant_model_attempts SET request_sha256=:sha WHERE id=:id"), {'sha':'a'*64, 'id':str(first.id)})
        elif change == 'receipt':
            row = db.scalar(text('SELECT receipt_json FROM assistant_model_receipts WHERE attempt_id=:id'), {'id':str(first.id)})
            value = json.loads(row); value['error_code'] = 'MODEL_OUTPUT_INVALID'
            db.execute(text('UPDATE assistant_model_receipts SET receipt_json=:value WHERE attempt_id=:id'), {'value':json.dumps(value), 'id':str(first.id)})
        elif change == 'event':
            db.execute(text("DELETE FROM assistant_run_events WHERE run_id=:id AND event_type='model.finished'"), {'id':str(first.run_id)})
        else:
            db.execute(text('UPDATE assistant_messages SET content=:value WHERE id=:id'), {'value':'未保存的伪造问题', 'id':str(basis.manifest.sources[0].reference.message_id)})
    with pytest.raises((ValueError, ServiceError)):
        material_preparation.preview(w[1], selection, w[0], config())


def test_history_is_bounded_to_eight_complete_recent_turns(material_world):
    w = material_world
    selection = selection_for(w)
    first = None
    for number in range(10):
        result, basis = complete(w, selection, f'第{number}次虚构回答。')
        first = first or result
        selection = followup(w, basis.manifest.stable_task_id, f'继续第{number + 1}轮。')
    history = material_preparation.preview(w[1], selection, w[0], config()).manifest.conversation_history
    assert len(history) == 16
    assert [item.content for item in history][1::2] == [f'第{number}次虚构回答。' for number in range(2, 10)]
    with w[0].session() as db:
        validate_model_records(db)
        for name in db.scalars(text("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='assistant_model_attempts'")).all():
            db.execute(text('DROP TRIGGER "' + name.replace('"', '""') + '"'))
        db.execute(text('UPDATE assistant_model_attempts SET request_sha256=:sha WHERE id=:id'),
            {'sha':'a'*64, 'id':str(first.id)})
    # The visible window is bounded, but accepted replies still verify their dependencies.
    with pytest.raises(ValueError):
        material_preparation.preview(w[1], selection, w[0], config())


def test_history_byte_bound_omits_whole_old_turns_without_truncating_answers(material_world):
    w = material_world
    answer = '独立虚构答复。' * 500
    selection = selection_for(w)
    for _ in range(4):
        result, basis = complete(w, selection, answer)
        selection = followup(w, basis.manifest.stable_task_id)
    history = material_preparation.preview(w[1], selection, w[0], config()).manifest.conversation_history
    assert len(history) == 6
    assert all(item.content == answer for item in history if item.role == 'assistant')
    assert len(json.dumps([item.model_dump(mode='json') for item in history], ensure_ascii=False).encode()) <= 32768


@pytest.mark.parametrize('field,value', [('workspace_id', uuid4()), ('conversation_id', uuid4()),
    ('scope_kind', 'matter'), ('scope_ref', uuid4()), ('binding_revision', 2)])
def test_history_never_uses_another_binding(material_world, field, value):
    w = material_world
    first, basis = complete(w, selection_for(w))
    selection = followup(w, basis.manifest.stable_task_id)
    with w[0].session() as db:
        parent = service._owned_run(w[1], selection.parent_business_run_id, db)
        result = business._record(parent, db)[1]
        scope = result.scope.model_copy(update={field:value})
        assert not material_history.select_history(db, scope, basis.manifest.stable_task_id, before_at=result.created_at)


@pytest.mark.parametrize('workflow,system', [('case', material_codec.SYSTEM), ('court', material_codec.SYSTEM),
    ('court', material_codec.SYSTEM + material_codec.WORKFLOW_OUTPUT_V1)])
def test_prior_workflow_prompt_history_preserves_its_exact_saved_bytes(material_world, monkeypatch, workflow, system):
    w = material_world
    with monkeypatch.context() as legacy:
        legacy.setattr(material_codec, 'system_for', lambda workflow:system)
        result, basis = complete(w, selection_for(w, workflow))
    selection = followup(w, basis.manifest.stable_task_id, workflow=workflow)
    current = material_preparation.preview(w[1], selection, w[0], config())
    assert current.manifest.conversation_history[1].content == result.output.candidate.text
    assert ('court-output-v2' if workflow == 'court' else 'task-output-v1') in material_codec.system_for(workflow)
    with w[0].session() as db:
        validate_model_records(db)
        row = attempts._row(result.id, db)
        prepared = attempts._input(row)
        assert material_codec.prepare(prepared.request, config()) == prepared


def test_repeated_analysis_of_one_saved_question_uses_its_latest_accepted_answer(material_world):
    w = material_world
    first, basis = complete(w, selection_for(w), '首次回答')
    with w[0].session() as db:
        view = service.read_conversation(w[1], w[2], db)
    repeated = d.MainMaterialSelection(request_id=uuid4(), expected_scope=view.scope,
        expected_composer_revision=view.composer_revision, parent_business_run_id=basis.parent_business_run_id)
    latest, _ = complete(w, repeated, '同一问题的再次回答')
    selection = followup(w, basis.manifest.stable_task_id)
    current = material_preparation.preview(w[1], selection, w[0], config())
    assert len(current.manifest.conversation_history) == 2
    assert current.manifest.conversation_history[1].message_id == latest.output.id


def test_renderer_cannot_submit_its_own_material_history(material_world):
    selection = selection_for(material_world)
    with pytest.raises(ValueError):
        d.MainMaterialSelection.model_validate(selection.model_dump() | {'conversation_history':[]})


def test_history_rechecks_originals_even_when_no_longer_in_current_material_selection(material_world):
    w = material_world
    first, basis = complete(w, selection_for(w, 'sales'))
    current = attachments.read_materials(w[1], w[2], database=w[0])
    attachments.select_materials(w[1], w[2], d.AssistantMaterialSelectionInput(
        request_id=uuid4(), expected_scope=current.scope, items=()), database=w[0])
    selection = followup(w, basis.manifest.stable_task_id, workflow='sales')
    assert not material_preparation.preview(w[1], selection, w[0], config()).manifest.materials
    path = next(w[0].storage_root.rglob('original.bin'))
    path.chmod(stat.S_IREAD | stat.S_IWRITE)
    path.write_bytes(path.read_bytes() + b'synthetic history source corruption')
    with pytest.raises(ServiceError):
        material_preparation.preview(w[1], selection, w[0], config())
