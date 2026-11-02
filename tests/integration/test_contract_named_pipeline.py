"""Named user stance survives real saves; witness omission and revival fail closed."""
import asyncio
from io import BytesIO
from pathlib import Path

import pytest
from docx import Document
from sqlalchemy import text

from cn_contract.assistant import material_attempts, material_preparation, material_stance
from cn_contract.assistant.model_integrity import validate_model_records
from cn_contract.assistant.providers import attempts
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.assistant.runner import execute_attempt
from cn_contract.ops import backup, workspace_backup
from cn_contract.persistence import Database
from cn_contract.security import authenticate, login
from tests.helpers.case_evidence import add_document
from tests.helpers.contract_review import draft_for
from tests.helpers.legacy_assistant_backup import PASSPHRASE
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_main_provider import config, KEY, server
from tests.integration.test_assistant_material_generation import material_world, grant
from tests.integration.test_assistant_material_routes import boot
from tests.integration.test_contract_review_pipeline import execute
from tests.integration.test_material_followup_history import followup
from tests.unit.test_contract_named_stance import COMPANY, FIRST_QUESTION, FOLLOWUP_QUESTION


def named_candidate(manifest):
    value = draft_for(manifest)
    identifiers = []
    for index, source in enumerate(item for item in manifest.sources if item.reference.kind == 'message'):
        identifier = 'stance_current' if index == 0 else 'stance_prior'
        quote = source.reference.quote
        value['quotes'].append(dict(id=identifier, source_id=source.source_id,
            start=0, end=len(quote), exact_quote=quote))
        identifiers.append(identifier)
    value.update(stance='supplier', stance_quote_ids=identifiers)
    return value


@pytest.fixture
def first_named(material_world):
    w = material_world
    chosen = followup(w, None, FIRST_QUESTION, new_task=True, workflow='contract')
    basis = material_preparation.preview(w[1], chosen, w[0], config())
    first, basis = execute(w, chosen, named_candidate(basis.manifest))
    assert first.output is not None and first.output.candidate.contract_review.stance == 'supplier'
    return w, first, basis


def test_named_stance_followup_saves_two_complete_rounds_exports_and_restores(first_named, tmp_path, record_property):
    w, first, basis = first_named
    with w[0].session() as db:
        original = db.scalar(text('SELECT output_json FROM assistant_model_outputs WHERE attempt_id=:id'),
            {'id': str(first.id)})
    add_document(w, ['独立虚构补充材料：供应方服务期限、付款和验收安排仍待核对。'])
    chosen = followup(w, basis.manifest.stable_task_id, FOLLOWUP_QUESTION, workflow='contract')
    current = material_preparation.preview(w[1], chosen, w[0], config())
    witnesses = [item for item in current.manifest.sources if item.reference.kind == 'message']
    assert len(witnesses) == 2
    assert witnesses[0].reference.quote == FOLLOWUP_QUESTION
    assert witnesses[1] == basis.manifest.sources[0]
    assert [(item.role, item.content) for item in current.manifest.conversation_history] == [
        ('user', FIRST_QUESTION), ('assistant', first.output.candidate.text)]
    second, current = execute(w, chosen, named_candidate(current.manifest))
    assert current.manifest.stable_task_id == basis.manifest.stable_task_id
    assert len(current.manifest.materials) == len(basis.manifest.materials) + 1
    assert second.output is not None and second.output.candidate.contract_review.stance == 'supplier'
    assert second.output.candidate.contract_review.stance_quote_ids == ('stance_current', 'stance_prior')
    record_property('continuation_wire_utf8_bytes', current.wire_bytes)
    with w[0].session() as db:
        assert attempts.read_attempt(w[1], first.id, db) == first
        assert attempts.read_attempt(w[1], second.id, db) == second
        validate_model_records(db)
        assert db.scalar(text('SELECT output_json FROM assistant_model_outputs WHERE attempt_id=:id'),
            {'id': str(first.id)}) == original
        attempt_count = db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts'))
        output_count = db.scalar(text('SELECT COUNT(*) FROM assistant_model_outputs'))
        record_property('attempt_count', attempt_count)
        record_property('output_count', output_count)
        assert attempt_count == output_count == 2
    with boot(w, tmp_path) as http:
        exported = http.client.get(http.url + '/material-generations/' + str(second.id) + '/document')
        assert exported.status_code == 200, exported.text
        assert second.output.candidate.text in '\n'.join(
            paragraph.text for paragraph in Document(BytesIO(exported.content)).paragraphs)
    root = Path(w[0].engine.url.database).parent
    archive = tmp_path / 'named-stance.qxbak'
    workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
    target = Path(workspace_backup.restore_workspace_backup(
        archive, tmp_path / 'named-restored', PASSPHRASE)['restored_root'])
    restored = Database('sqlite:///' + str(target / 'workbench.db'), target / 'protected',
        w[0].settings, initialize_schema=False)
    backup._mark_storage_flags(restored)
    try:
        with restored.session() as db:
            token, _ = login('lawyer', 'fixture123', db)
            actor = authenticate(token, db)
            assert attempts.read_attempt(actor, first.id, db) == first
            assert attempts.read_attempt(actor, second.id, db) == second
            assert db.scalar(text('SELECT output_json FROM assistant_model_outputs WHERE attempt_id=:id'),
                {'id': str(first.id)}) == original
            validate_model_records(db)
    finally:
        restored.engine.dispose()


@pytest.mark.parametrize('damage', ['omitted_witness', 'revived_after_withdrawal'])
def test_saved_stance_sources_are_rebuilt_before_send_and_archive(first_named, monkeypatch, damage):
    w, first, basis = first_named
    if damage == 'revived_after_withdrawal':
        followup(w, basis.manifest.stable_task_id,
            f'不再代表乙方{COMPANY}，请中立核对。', workflow='contract')
    chosen = followup(w, basis.manifest.stable_task_id, FOLLOWUP_QUESTION, workflow='contract')
    actual = material_preparation.preview(w[1], chosen, w[0], config())
    actual_sources = [item for item in actual.manifest.sources if item.reference.kind == 'message']
    assert len(actual_sources) == (2 if damage == 'omitted_witness' else 1)
    real_selector = material_stance.contract_stance_sources

    def altered_witnesses(db, current, question):
        if current.run_id == chosen.parent_business_run_id:
            return () if damage == 'omitted_witness' else (basis.manifest.sources[0],)
        return real_selector(db, current, question)

    async def scenario(url):
        provider = DeepSeekProvider.for_synthetic_loopback(config(), lambda: KEY, url)
        with monkeypatch.context() as altered:
            altered.setattr(material_stance, 'contract_stance_sources', altered_witnesses)
            _, lease, forged = grant(w, chosen, provider)
            with w[0].session() as db:
                queued = material_attempts.enqueue(w[1], chosen, forged, db, lease)
                assert queued.state == 'reserved' and queued.output is None
                validate_model_records(db)
                frozen = attempts._row(queued.id, db)['input_json']
        with w[0].session() as db:
            assert attempts.read_attempt(w[1], first.id, db) == first
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 2
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_outputs')) == 1
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_receipts')) == 1
            # No second candidate or quotes exist: rejection must come from its input sources.
            with pytest.raises(ValueError, match='ASSISTANT_MODEL_INTEGRITY'):
                validate_model_records(db)
        refused = await execute_attempt(w[1], queued.id, w[0], lease)
        assert refused.state == 'failed_before_send'
        assert refused.receipt.cost_status == 'not_sent' and refused.output is None
        assert await execute_attempt(w[1], queued.id, w[0], lease) == refused
        with w[0].session() as db:
            assert attempts._row(queued.id, db)['input_json'] == frozen
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_outputs')) == 1
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_receipts')) == 2

    with server() as (url, received, _):
        asyncio.run(scenario(url))
    assert received == []
