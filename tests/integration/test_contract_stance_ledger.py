"""Contract continuation uses verified user declarations, without model output."""
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import business, service
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_material_generation import material_world


DECLARATION = '我代表乙方恒岳仓储设备工程有限公司（供应方）。请审查合同。'
CONTINUATION = '继续上一个任务，立场不变，仍代表乙方恒岳仓储设备工程有限公司。'


def submit(w, question, task_id=None, *, workflow='contract', new_task=False):
    database, actor, cid, _ = w
    with database.session() as db:
        view = service.read_conversation(actor, cid, db)
        return business.submit(actor, cid, d.BusinessInput(request_id=uuid4(), expected_scope=view.scope,
            expected_composer_revision=view.composer_revision, content=question, workflow=workflow,
            task_id=task_id, new_task=new_task), db)


def sources(w, current, question=CONTINUATION):
    from cn_contract.assistant.material_stance import contract_stance_sources
    with w[0].session() as db:
        return contract_stance_sources(db, current, question)


def test_continuation_uses_accepted_user_declaration_without_a_model_reply(material_world):
    first = submit(material_world, DECLARATION)
    current = submit(material_world, CONTINUATION, first.task_id)
    assert first.state == 'awaiting_input'
    result = sources(material_world, current)
    assert len(result) == 1
    assert result[0].reference.message_id == first.message_id
    assert result[0].reference.source_revision == first.scope.input_revision
    assert result[0].reference.quote == DECLARATION


def test_negative_request_without_result_task_still_revokes_explicit_task_stance(material_world):
    first = submit(material_world, DECLARATION)
    withdrawn = submit(material_world, '不再审查合同，不再代表乙方恒岳仓储设备工程有限公司。', first.task_id)
    assert withdrawn.task_id is None
    assert withdrawn.workflow is None
    current = submit(material_world, CONTINUATION, first.task_id)
    assert sources(material_world, current) == ()


def test_cancelling_a_withdrawal_run_does_not_restore_the_earlier_declaration(material_world):
    first = submit(material_world, DECLARATION)
    withdrawn = submit(material_world, '不再审查合同，不再代表乙方恒岳仓储设备工程有限公司。', first.task_id)
    with material_world[0].session() as db:
        cancelled = service.cancel_run(material_world[1], withdrawn.run_id,
            d.AssistantCancelInput(request_id=uuid4()), db)
    assert cancelled.state == 'cancelled'
    current = submit(material_world, CONTINUATION, first.task_id)
    assert sources(material_world, current) == ()


def test_unbound_withdrawal_stops_inference_in_the_same_scope(material_world):
    first = submit(material_world, DECLARATION)
    withdrawn = submit(material_world, '不再审查合同，不再代表乙方恒岳仓储设备工程有限公司。')
    assert withdrawn.task_id is None
    current = submit(material_world, CONTINUATION, first.task_id)
    assert sources(material_world, current) == ()


def test_ambiguous_task_declaration_cannot_grant_a_new_stance(material_world):
    first = submit(material_world, DECLARATION)
    submit(material_world, '我代表乙方启越测试设备有限公司（供应方）。', new_task=True)
    ambiguous = submit(material_world, '我代表乙方恒岳仓储设备工程有限公司（采购方）。')
    assert ambiguous.task_id is None
    current = submit(material_world, CONTINUATION, first.task_id)
    assert sources(material_world, current) == ()


@pytest.mark.parametrize('later', [
    '我方是供应方，我们是采购方。',
    '我代表乙方启越测试设备有限公司（供应方）。',
    '我们是供应方。',
    '我代表乙方恒岳仓储设备工程有限公司。',
    '立场尚未确定，请先保持中立。',
    '我 不再代表乙方恒岳仓储设备工程有限公司。',
    '请不要再代表乙方恒岳仓储设备工程有限公司。',
    '请不再代理乙方恒岳仓储设备工程有限公司。',
    '当前不代表供应方。',
    '当前我代表乙方启越测试设备有限公司。',
    '我公司现代表乙方启越测试设备有限公司（采购方）。',
    '我们站在采购方立场。',
    '收到更新后我方已经转为采购方。',
    '请先保持中立。',
    '本人现代表乙方启越测试设备有限公司（采购方）。',
    "单价见 buyer's 报价，我方不再代表供应方。",
    '对方说：“请收件。我方不再代表供应方。',
    '我方今后不再代表供应方。',
    '我方已于上月改为采购方。',
    '我方从下个月起是采购方。',
])
def test_later_conflict_changed_company_or_unclear_declaration_clears_old_stance(material_world, later):
    first = submit(material_world, DECLARATION)
    submit(material_world, later, first.task_id)
    current = submit(material_world, CONTINUATION, first.task_id)
    assert sources(material_world, current) == ()


def test_latest_explicit_role_for_the_same_company_replaces_prior_role(material_world):
    first = submit(material_world, DECLARATION)
    later_question = '我代表乙方恒岳仓储设备工程有限公司（采购方）。'
    latest = submit(material_world, later_question, first.task_id)
    current = submit(material_world, CONTINUATION, first.task_id)
    result = sources(material_world, current)
    assert len(result) == 1
    assert result[0].reference.message_id == latest.message_id
    assert result[0].reference.quote == later_question


@pytest.mark.parametrize('later', [
    '补充附件，请核对付款日期。',
    '请核对供应方的验收期限。',
    '请核对对方采购方的立场意见。',
    '我方不同意以采购方名义签署。',
    '我方不认可供应方的验收方式。',
    '我方不接受采购方的付款安排。',
    '我方认为采购方的付款期限过长。',
    '我方建议供应方作为资料接收方时记录收件日期。',
    '我方与供应方是同一集团。',
    '我方已委托代理律师处理后续事宜。',
    '我方不认可代理人的意见。',
    '我方已核对乙方代表签字页。',
    '我方接受中立第三方评估。',
    '合同写着“我方是采购方”，请核对这句原文。',
    CONTINUATION,
])
def test_unrelated_request_or_same_continuation_preserves_original_declaration(material_world, later):
    first = submit(material_world, DECLARATION)
    submit(material_world, later, first.task_id)
    current = submit(material_world, CONTINUATION, first.task_id)
    result = sources(material_world, current)
    assert len(result) == 1
    assert result[0].reference.message_id == first.message_id


def test_other_task_cannot_change_stance_and_new_task_cannot_inherit_it(material_world):
    first = submit(material_world, DECLARATION)
    other = submit(material_world, '我代表乙方启越测试设备有限公司（采购方）。', new_task=True)
    submit(material_world, '不再审查合同，不再代表乙方恒岳仓储设备工程有限公司。', other.task_id)
    current = submit(material_world, CONTINUATION, first.task_id)
    assert sources(material_world, current)[0].reference.message_id == first.message_id
    fresh = submit(material_world, CONTINUATION, new_task=True)
    assert sources(material_world, fresh) == ()


@pytest.mark.parametrize('new_task', [False, True])
def test_explicit_new_task_withdrawal_cannot_revoke_the_previous_task(material_world, new_task):
    first = submit(material_world, DECLARATION)
    unrelated = submit(material_world, '开始新任务，不再审查合同，不再代表乙方恒岳仓储设备工程有限公司。',
        None if new_task else first.task_id, new_task=new_task)
    assert unrelated.task_id is None
    current = submit(material_world, CONTINUATION, first.task_id)
    result = sources(material_world, current)
    assert len(result) == 1
    assert result[0].reference.message_id == first.message_id


def test_later_withdrawal_does_not_rewrite_earlier_selection(material_world):
    first = submit(material_world, DECLARATION)
    earlier = submit(material_world, CONTINUATION, first.task_id)
    original = sources(material_world, earlier)
    submit(material_world, '不再审查合同，不再代表乙方恒岳仓储设备工程有限公司。', first.task_id)
    latest = submit(material_world, CONTINUATION, first.task_id)
    assert sources(material_world, earlier) == original
    assert sources(material_world, latest) == ()


def test_declaration_after_saved_creation_cutoff_is_not_used(material_world):
    first = submit(material_world, DECLARATION)
    current = submit(material_world, CONTINUATION, first.task_id)
    before_declaration = current.model_copy(update={'created_at':first.created_at - timedelta(microseconds=1)})
    assert sources(material_world, before_declaration) == ()
    equal_cutoff = current.model_copy(update={'created_at':first.created_at})
    assert sources(material_world, equal_cutoff)[0].reference.message_id == first.message_id


@pytest.mark.parametrize('field,value', [
    ('workspace_id', uuid4()), ('conversation_id', uuid4()), ('scope_kind', 'matter'),
    ('scope_ref', uuid4()), ('binding_revision', 2),
])
def test_another_scope_cannot_supply_a_stance(material_world, field, value):
    first = submit(material_world, DECLARATION)
    current = submit(material_world, CONTINUATION, first.task_id)
    changed = current.model_copy(update={'scope':current.scope.model_copy(update={field:value})})
    assert sources(material_world, changed) == ()


@pytest.mark.parametrize('question', [
    DECLARATION,
    '我方是采购方。',
    '立场不变。',
    '不再代表乙方恒岳仓储设备工程有限公司。',
    '仍代表甲方恒岳仓储设备工程有限公司。',
])
def test_current_direct_unclear_revoked_or_different_identity_never_gets_old_source(material_world, question):
    first = submit(material_world, DECLARATION)
    current = submit(material_world, question, first.task_id)
    assert sources(material_world, current, question) == ()


def test_historical_source_is_revalidated_against_immutable_user_message(material_world):
    first = submit(material_world, DECLARATION)
    current = submit(material_world, CONTINUATION, first.task_id)
    with material_world[0].session() as db:
        for name in db.scalars(text("SELECT name FROM sqlite_master WHERE type='trigger'")).all():
            db.execute(text('DROP TRIGGER "' + name.replace('"', '""') + '"'))
        db.execute(text('UPDATE assistant_messages SET content=:content WHERE id=:id'),
            {'content':'未提交的伪造用户立场', 'id':str(first.message_id)})
    with pytest.raises(ValueError):
        sources(material_world, current)
