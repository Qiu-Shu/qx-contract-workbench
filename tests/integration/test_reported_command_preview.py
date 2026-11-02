"""Fresh routing must not silently select a fallback unsupported by a frozen method."""
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import business, material_preparation, service
from cn_contract.assistant.model_integrity import validate_model_records
from cn_contract.security import ServiceError
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_material_generation import material_world
from tests.integration.test_assistant_main_provider import config


def selected(w, question):
    with w[0].session() as db:
        view = service.read_conversation(w[1], w[2], db)
        parent = business.submit(w[1], w[2], d.BusinessInput(request_id=uuid4(),
            expected_scope=view.scope, expected_composer_revision=view.composer_revision, content=question), db)
        current = service.read_conversation(w[1], w[2], db)
    assert parent.workflow == 'case' and parent.task_id is not None
    return d.MainMaterialSelection(request_id=uuid4(), expected_scope=current.scope,
        expected_composer_revision=current.composer_revision, parent_business_run_id=parent.run_id)


@pytest.mark.parametrize('question,code', [
    ('请做商标初筛：客户说明已收款。', 'MATERIAL_INSTRUCTION_CONFLICT'),
    ('请做商标初筛和专利侵权分析：客户说明已收款。', 'IP_SCOPE_UNSUPPORTED'),
])
def test_fresh_reported_prefix_preview_rejects_before_model_ledger(material_world, question, code):
    w = material_world
    selection = selected(w, question)
    tables = ('assistant_messages', 'assistant_runs', 'assistant_run_events',
        'assistant_model_attempts', 'assistant_model_receipts', 'assistant_model_outputs')
    with w[0].session() as db:
        before = [db.scalar(text('SELECT COUNT(*) FROM ' + table)) for table in tables]
        conversation = service.read_conversation(w[1], w[2], db)
    assert before[3:] == [0, 0, 0]
    with pytest.raises(ServiceError) as caught:
        material_preparation.preview(w[1], selection, w[0], config())
    assert caught.value.code == code
    with w[0].session() as db:
        assert [db.scalar(text('SELECT COUNT(*) FROM ' + table)) for table in tables] == before
        assert service.read_conversation(w[1], w[2], db) == conversation
        validate_model_records(db)


def test_later_trademark_denial_preserves_separate_case_preview(material_world):
    w = material_world
    selection = selected(w, '请做商标初筛：客户说明已收款。不做商标初筛。现在请整理案件。')
    basis = material_preparation.preview(w[1], selection, w[0], config())
    assert basis.manifest.workflow == 'case'
    assert basis.manifest.trademark_triage is None
    with w[0].session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0
        validate_model_records(db)
