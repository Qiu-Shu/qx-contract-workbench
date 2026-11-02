import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract.assistant import material_preparation, business, service
from cn_contract.assistant import material_attempts
from cn_contract.assistant.runner import execute_attempt
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.security import ServiceError
from tests.integration.test_criminal_analysis_pipeline import criminal_world, world, execute, selection_for
from tests.integration.test_assistant_material_generation import grant
from tests.integration.test_assistant_main_provider import config, KEY, server
from tests.helpers.case_evidence import response
from tests.integration.test_material_followup_history import followup


@pytest.mark.parametrize('new_task', [False, True])
def test_plain_followup_or_reusing_criminal_material_cannot_escape_local_policy(criminal_world, new_task):
    w = criminal_world
    _, first = execute(w, selection_for(w))
    selection = followup(w, first.manifest.stable_task_id, '继续整理材料。', new_task=new_task)
    keys = []
    provider = DeepSeekProvider(config(), lambda: keys.append('unexpected') or KEY)
    async def scenario():
        with pytest.raises(ServiceError) as error:
            grant(w, selection, provider)
        assert error.value.code == 'CRIMINAL_SCOPE_REQUIRED'
    asyncio.run(scenario())
    assert keys == []
    with w[0].session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 1


def test_explicit_criminal_court_cannot_use_civil_hearing_packet(criminal_world):
    w = criminal_world
    selection = followup(w, None, '请模拟刑事案件庭审。\n我是被告代理律师', new_task=True, workflow='court')
    with pytest.raises(ServiceError) as error:
        material_preparation.preview(w[1], selection, w[0], config())
    assert error.value.code == 'CRIMINAL_HEARING_UNAVAILABLE'


def test_previously_queued_plain_followup_is_rechecked_before_transport(criminal_world, monkeypatch):
    w = criminal_world
    _, first = execute(w, selection_for(w))
    selection = followup(w, first.manifest.stable_task_id, '继续整理材料。')
    with server(response({'text':'不能外发', 'citations':[first.manifest.sources[0].source_id]})) as (url, received, _):
        async def scenario():
            with monkeypatch.context() as old:
                old.setattr(material_preparation, 'require_criminal_scope', lambda *args: None)
                _, lease, basis = grant(w, selection, DeepSeekProvider.for_synthetic_loopback(config(), lambda:KEY, url))
                with w[0].session() as db:
                    queued = material_attempts.enqueue(w[1], selection, basis, db, lease)
            result = await execute_attempt(w[1], queued.id, w[0], lease)
            assert result.state == 'failed_before_send' and result.receipt.cost_status == 'not_sent'
        asyncio.run(scenario())
        assert received == []


def test_declined_strategy_stays_out_of_saved_analysis(criminal_world):
    w = criminal_world
    selection = followup(w, None, '请做刑事证据分析，不需要辩护策略。', new_task=True)
    result, basis = execute(w, selection)
    assert result.output is not None
    assert [s.method_id for s in basis.manifest.criminal_analysis.method_sources] == ['case_analysis']
    assert result.output.candidate.criminal_analysis.elements == ()
    assert result.output.candidate.criminal_analysis.strategies == ()


def test_older_parent_with_current_scope_cannot_hide_a_later_criminal_request(criminal_world):
    w = criminal_world
    original = followup(w, None, '请整理材料。', new_task=True)
    old_basis = material_preparation.preview(w[1], original, w[0], config())
    execute(w, selection_for(w, old_basis.manifest.stable_task_id))
    with w[0].session() as db:
        view = service.read_conversation(w[1], w[2], db)
    reused = original.model_copy(update={'request_id':uuid4(), 'expected_scope':view.scope,
        'expected_composer_revision':view.composer_revision})
    with pytest.raises(ServiceError) as error:
        material_preparation.preview(w[1], reused, w[0], config())
    assert error.value.code == 'CRIMINAL_SCOPE_REQUIRED'


def test_policy_denial_before_model_enqueue_still_protects_followup(criminal_world):
    w = criminal_world
    selection = selection_for(w)
    w[0]._assistant_synthetic_hashes = frozenset()
    with pytest.raises(ServiceError) as error:
        material_preparation.preview(w[1], selection, w[0], config())
    assert error.value.code == 'DATA_POLICY_UNAPPROVED'
    with w[0].session() as db:
        parent = service._owned_run(w[1], selection.parent_business_run_id, db)
        task = business._record(parent, db)[1].task_id
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0
    ordinary = followup(w, task, '继续整理材料。')
    with pytest.raises(ServiceError) as error:
        material_preparation.preview(w[1], ordinary, w[0], config())
    assert error.value.code == 'CRIMINAL_SCOPE_REQUIRED'
