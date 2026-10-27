from uuid import uuid4

import pytest

from cn_contract import domain as d
from cn_contract.security import ServiceError
from test_task_drafts_bridge import frozen_task, workspace


def test_chat_prepares_once_and_reads_facts_without_navigation(frozen_task):
    from cn_contract.task_drafts import bridge
    database, actors, _, execution, _, _, _ = frozen_task
    value = d.TaskExecutionCreateInput(request_id=uuid4(), matter=d.MatterCreateInput(
        title='聊天内合成案件', contract_type='sales', review_mode='pre_sign',
        position='buyer', objectives=('核对交付和价款',)))
    with database.session() as db:
        prepared = bridge.create_and_prepare(actors['lawyer'], execution.id, value, db=db)
    with database.session() as db:
        assert bridge.create_and_prepare(actors['lawyer'], execution.id, value, db=db) == prepared
        context = bridge.read_context(actors['lawyer'], execution.id, db=db)
        assert context.execution.matter_id == prepared.matter_id
        assert context.facts.facts
        assert context.parses
        assert context.review is None
        assert all(f.confirmation_status == 'unconfirmed' for f in context.facts.facts)
        with pytest.raises(ServiceError):
            bridge.create_and_prepare(actors['lawyer'], execution.id,
                value.model_copy(update={'request_id':uuid4()}), db=db)


def test_completed_execution_keeps_original_fact_snapshot(frozen_task):
    from cn_contract.task_drafts import bridge
    from cn_contract.facts.confirm import confirm_facts
    from test_task_drafts_bridge import prepare, review_input
    database, actors, _, execution, matter_id, _, _ = frozen_task
    prepared, _ = prepare(frozen_task)
    request = review_input(frozen_task, prepared, confirm=True)
    with database.session() as db:
        bridge.review_execution(actors['lawyer'], execution.id, request, db=db)
        first = bridge.read_context(actors['lawyer'], execution.id, db=db)
        fact = first.facts.facts[0]
        confirm_facts(matter_id, first.facts.version, (d.FactDecision(fact_id=fact.id,
            decision='rejected', confirmed_value=fact.typed_value, reason='后续独立虚构核对'),), actors['lawyer'], db=db)
    with database.session() as db:
        later = bridge.read_context(actors['lawyer'], execution.id, db=db)
        assert later.facts == first.facts
        assert later.facts.sha256 == later.review.manifest.fact_snapshot_sha256
