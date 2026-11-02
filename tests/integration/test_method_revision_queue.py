"""Queued historical methods survive current defaults in the same task."""
import asyncio
import json

import pytest

from cn_contract.assistant import case_evidence, contract_review, material_attempts, material_preparation, trademark_triage
from cn_contract.assistant.model_integrity import validate_model_records
from cn_contract.assistant.providers import attempts
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.assistant.runner import execute_attempt
from tests.helpers.case_evidence import add_document, response
from tests.helpers.contract_review import draft_for as contract_draft
from tests.helpers.trademark_triage import draft_for as trademark_draft
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_main_provider import KEY, config, server
from tests.integration.test_assistant_material_generation import grant
from tests.integration.test_material_followup_history import followup
from tests.integration.test_trademark_triage_pipeline import trademark_world


@pytest.mark.parametrize('field,hook,module,question,workflow,saved_id,current_id', [
    ('case_method', 'select_method', case_evidence, '请整理材料时间线。', 'case', 'case-evidence-v1', 'case-evidence-v5'),
    ('case_method', 'select_method', case_evidence, '请整理材料时间线。', 'case', 'case-evidence-v2', 'case-evidence-v5'),
    ('case_method', 'select_method', case_evidence, '请整理材料时间线。', 'case', 'case-evidence-v3', 'case-evidence-v5'),
    ('case_method', 'select_method', case_evidence, '请整理材料时间线。', 'case', 'case-evidence-v4', 'case-evidence-v5'),
    ('contract_review', 'contract_review_for', contract_review, '我们是供应方，请审查合同。', 'contract', 'contract-review-v1', 'contract-review-v3'),
    ('contract_review', 'contract_review_for', contract_review, '我们是供应方，请审查合同。', 'contract', 'contract-review-v2', 'contract-review-v3'),
    ('trademark_triage', 'trademark_triage_for', trademark_triage, '请做商标侵权初筛。', 'case', 'trademark-triage-v1', 'trademark-triage-v5'),
    ('trademark_triage', 'trademark_triage_for', trademark_triage, '请做商标侵权初筛。', 'case', 'trademark-triage-v2', 'trademark-triage-v5'),
    ('trademark_triage', 'trademark_triage_for', trademark_triage, '请做商标侵权初筛。', 'case', 'trademark-triage-v3', 'trademark-triage-v5'),
    ('trademark_triage', 'trademark_triage_for', trademark_triage, '请做商标侵权初筛。', 'case', 'trademark-triage-v4', 'trademark-triage-v5'),
])
def test_saved_revision_queue_runs_once_after_default_revision_changes(
        trademark_world, monkeypatch, field, hook, module, question, workflow, saved_id, current_id):
    w = trademark_world
    if workflow == 'contract':
        add_document(w, ['为评估设备服务项目，接收方仅为评估目的使用披露的保密信息。',
            '违反保密义务须支付30万元赔偿。'])
    chosen = followup(w, None, question, new_task=True, workflow=workflow)
    previous = lambda *args: module.select_method(*args, method_id=saved_id)
    with monkeypatch.context() as old:
        old.setattr(material_preparation, hook, previous)
        basis = material_preparation.preview(w[1], chosen, w[0], config())
    assert getattr(basis.manifest, field).method_id == saved_id
    if field == 'contract_review':
        value = contract_draft(basis.manifest)
    elif field == 'trademark_triage':
        value = trademark_draft(basis.manifest)
    else:
        source = next(s for s in basis.manifest.sources if s.reference.kind == 'document')
        quote = source.reference.anchor.quote
        value = dict(format_version='case-evidence-v1',
            quotes=[dict(id='q1', source_id=source.source_id, start=0, end=len(quote), exact_quote=quote)],
            statements=[dict(kind='source_statement', text='材料记录的自述尚待核实。', support=['q1'],
                opposing=[], unresolved=['原件与实际情况尚待核验。'])], timeline=[], gaps=['事件日期未明确。'])
    with server(response(value)) as (url, received, _):
        async def scenario():
            with monkeypatch.context() as old:
                old.setattr(material_preparation, hook, previous)
                _, lease, approved = grant(w, chosen, DeepSeekProvider.for_synthetic_loopback(config(), lambda: KEY, url))
                assert approved == basis
                with w[0].session() as db:
                    queued = material_attempts.enqueue(w[1], chosen, approved, db, lease)
            result = await execute_attempt(w[1], queued.id, w[0], lease)
            assert result.output is not None
            assert getattr(result.output.manifest, field) == getattr(basis.manifest, field)
            assert await execute_attempt(w[1], queued.id, w[0], lease) == result
            with w[0].session() as db:
                assert attempts.read_attempt(w[1], queued.id, db) == result
                validate_model_records(db)
            return result
        result = asyncio.run(scenario())
        assert len(received) == 1
        sent = json.loads(received[0]['body'])
        assert sent['messages'][0]['content'] == module.method_system(getattr(basis.manifest, field))
        assert json.loads(sent['messages'][1]['content']) == basis.manifest.model_dump(mode='json')
    current_selection = followup(w, basis.manifest.stable_task_id, question, workflow=workflow)
    current = material_preparation.preview(w[1], current_selection, w[0], config())
    assert getattr(current.manifest, field).method_id == current_id == module.CURRENT_METHOD_ID
    assert current.manifest.stable_task_id == basis.manifest.stable_task_id
    assert any(item.content == result.output.candidate.text for item in current.manifest.conversation_history)
