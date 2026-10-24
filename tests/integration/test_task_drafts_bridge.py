"""Frozen synthetic attachments traverse the real case/confirmation/Mock path."""
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.persistence import get_fact_snapshot, read_matter, read_original, transition_matter
from cn_contract.security import ServiceError
from test_assistant_storage import workspace, conversation


def test_task_bridge_exists():
    assert (Path(__file__).parents[2] / 'src/cn_contract/task_drafts/bridge.py').is_file(), \
        'A frozen task needs an authorized attachment-to-case bridge'


@pytest.fixture
def frozen_task(workspace):
    from cn_contract.assistant import attachments
    from cn_contract.documents.ingest import DOCX_MIME
    from cn_contract.matters import create_matter
    from cn_contract.review.synthetic import select_fixture
    from cn_contract.storage_bootstrap import initialize_storage
    from cn_contract.task_drafts import service
    database, actors, _, _ = workspace
    initialize_storage(database)
    actor = actors['lawyer']
    value = conversation(workspace)
    cid = value.scope.conversation_id
    _, _, path, raw = select_fixture('sales')
    receipt = attachments.ingest_attachment(actor, cid, d.AssistantAttachmentInput(
        request_id=uuid4(), expected_scope=value.scope, original_name=path.name, mime=DOCX_MIME,
        policy=d.AssistantMaterialPolicy(local_processing_accepted=True)), BytesIO(raw), database=database)
    current = attachments.read_materials(actor, cid, database=database)
    parsed = attachments.parse_attachment(actor, cid, receipt.attachment.id,
        d.AssistantAttachmentParseInput(request_id=uuid4(), expected_scope=current.scope), database=database)
    with database.session() as db:
        binding = service.create_binding(actor, cid, db)
        received = service.receive_batch(actor, binding.id, d.TaskInboxBatchInput(expected_cursor=0,
            next_cursor=1, events=(d.TaskInboxEventInput(event_id='synthetic-1', text='帮我审查合同',
                media=(d.TaskMediaInput(media_id='file-1', name=path.name, mime=DOCX_MIME, status='ready',
                    attachment_id=receipt.attachment.id, sha256=receipt.attachment.sha256,
                    parse_revision=parsed.parse.revision),)),)), db)
        draft = received.drafts[0]
        execution = service.freeze_draft(actor, draft.id, d.TaskFreezeInput(expected_revision=draft.revision,
            manifest_sha256=draft.manifest_sha256), db)
        matter = create_matter(d.MatterCreateInput(title='独立合成任务桥接', contract_type='sales',
            review_mode='pre_sign', position='buyer', objectives=('核对虚构合同',)), actor, db)
    return database, actors, cid, execution, matter.id, receipt.attachment.id, raw


def prepare(frozen_task):
    from cn_contract.task_drafts import bridge
    database, actors, _, execution, matter_id, _, _ = frozen_task
    value = d.TaskExecutionPrepareInput(request_id=uuid4(), matter_id=matter_id)
    with database.session() as db:
        result = bridge.prepare_execution(actors['lawyer'], execution.id, value, db=db)
    return result, value


def review_input(frozen_task, result, *, confirm):
    from cn_contract.facts.confirm import confirm_facts
    database, actors, _, _, matter_id, _, _ = frozen_task
    actor = actors['lawyer']
    with database.session() as db:
        matter = read_matter(matter_id, actor, db)
        facts = get_fact_snapshot(matter_id, matter.active_fact_version, actor, db)
        if confirm:
            facts = confirm_facts(matter_id, facts.version, tuple(d.FactDecision(fact_id=f.id,
                decision='confirmed', confirmed_value=f.typed_value, reason='人工核对独立虚构原文')
                for f in facts.facts), actor, db=db)
            transition_matter(matter_id, 'ready_for_review', actor, db)
    return d.TaskExecutionReviewInput(request_id=uuid4(), review=d.ReviewStartInput(
        fact_version=facts.version, document_hashes=result.document_versions))


def test_prepare_preserves_original_and_unconfirmed_facts_and_is_idempotent(frozen_task):
    from cn_contract.task_drafts import bridge
    database, actors, _, execution, matter_id, source_id, raw = frozen_task
    result, value = prepare(frozen_task)
    assert result.state == 'awaiting_facts'
    assert set(result.source_versions) == {source_id}
    with database.session() as db:
        version_id = result.source_versions[source_id]
        assert read_original(matter_id, version_id, actors['lawyer'], db) == raw
        facts = get_fact_snapshot(matter_id, read_matter(matter_id, actors['lawyer'], db).active_fact_version,
            actors['lawyer'], db)
        assert facts.facts and all(f.confirmation_status == 'unconfirmed' for f in facts.facts)
        assert bridge.prepare_execution(actors['lawyer'], execution.id, value, db=db) == result
        assert db.scalar(text('SELECT count(*) FROM document_versions')) == 1
        assert db.scalar(text('SELECT count(*) FROM assistant_runs')) == 0


def test_unconfirmed_facts_block_mock_review_without_result(frozen_task):
    from cn_contract.task_drafts import bridge
    database, actors, _, execution, _, _, _ = frozen_task
    result, _ = prepare(frozen_task)
    value = review_input(frozen_task, result, confirm=False)
    with pytest.raises(ServiceError):
        with database.session() as db:
            bridge.review_execution(actors['lawyer'], execution.id, value, db=db)
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM review_runs')) == 0


def test_confirmed_mock_review_commits_result_once(frozen_task):
    from cn_contract.task_drafts import bridge
    from cn_contract.review.storage import read_run
    database, actors, _, execution, matter_id, _, _ = frozen_task
    result, _ = prepare(frozen_task)
    value = review_input(frozen_task, result, confirm=True)
    with database.session() as db:
        completed = bridge.review_execution(actors['lawyer'], execution.id, value, db=db)
        assert completed.state == 'completed'
        assert read_run(matter_id, completed.review_run_id, actors['lawyer'], db=db).status == 'completed'
    with database.session() as db:
        repeated = bridge.review_execution(actors['lawyer'], execution.id, value, db=db)
        assert repeated.review_run_id == completed.review_run_id
        assert db.scalar(text('SELECT count(*) FROM review_runs')) == 1


def test_other_lawyer_cannot_prepare_owned_execution(frozen_task):
    from cn_contract.task_drafts import bridge
    database, actors, _, execution, matter_id, _, _ = frozen_task
    with pytest.raises(ServiceError) as error:
        with database.session() as db:
            bridge.prepare_execution(actors['reviewer'], execution.id,
                d.TaskExecutionPrepareInput(request_id=uuid4(), matter_id=matter_id), db=db)
    assert error.value.status_code == 403


def test_second_request_cannot_rebind_prepared_execution(frozen_task):
    from cn_contract.task_drafts import bridge
    database, actors, _, execution, _, _, _ = frozen_task
    prepare(frozen_task)
    with pytest.raises(ServiceError):
        with database.session() as db:
            bridge.prepare_execution(actors['lawyer'], execution.id,
                d.TaskExecutionPrepareInput(request_id=uuid4(), matter_id=uuid4()), db=db)


def test_failed_prepare_rolls_back_files_documents_and_execution(frozen_task, monkeypatch):
    from cn_contract.task_drafts import bridge, service
    from cn_contract.web import services
    database, actors, _, execution, matter_id, _, _ = frozen_task
    def fail(*args, **kwargs):
        raise ServiceError('FILE_UNSUPPORTED', 400)
    monkeypatch.setattr(services, 'candidate_parse', fail)
    with pytest.raises(ServiceError):
        with database.session() as db:
            bridge.prepare_execution(actors['lawyer'], execution.id,
                d.TaskExecutionPrepareInput(request_id=uuid4(), matter_id=matter_id), db=db)
    with database.session() as db:
        assert service.read_execution(actors['lawyer'], execution.id, db).state == 'prepared'
        assert db.scalar(text('SELECT count(*) FROM document_versions')) == 0
    assert not list((database.storage_root / str(matter_id)).glob('*/original.bin'))


def test_caller_catching_parse_failure_cannot_commit_partial_preparation(frozen_task, monkeypatch):
    from cn_contract.task_drafts import bridge, service
    from cn_contract.web import services
    database, actors, _, execution, matter_id, _, _ = frozen_task
    monkeypatch.setattr(services, 'candidate_parse', lambda *args, **kwargs: (_ for _ in ()).throw(
        ServiceError('FILE_UNSUPPORTED', 400)))
    with database.session() as db:
        with pytest.raises(ServiceError):
            bridge.prepare_execution(actors['lawyer'], execution.id,
                d.TaskExecutionPrepareInput(request_id=uuid4(), matter_id=matter_id), db=db)
    with database.session() as db:
        assert service.read_execution(actors['lawyer'], execution.id, db).state == 'prepared'
        assert db.scalar(text('SELECT count(*) FROM document_versions')) == 0
    assert not list((database.storage_root / str(matter_id)).glob('*/original.bin'))


def test_result_mapping_failure_rolls_back_mock_run_and_can_retry(frozen_task, monkeypatch):
    from cn_contract.task_drafts import bridge, service
    database, actors, _, execution, _, _, _ = frozen_task
    prepared, _ = prepare(frozen_task)
    value = review_input(frozen_task, prepared, confirm=True)
    original = service.advance_execution
    def fail_result(actor, identifier, state, db, **kwargs):
        if state == 'completed':
            raise ServiceError('STATE_CONFLICT', 409)
        return original(actor, identifier, state, db, **kwargs)
    monkeypatch.setattr(service, 'advance_execution', fail_result)
    with database.session() as db:
        with pytest.raises(ServiceError):
            bridge.review_execution(actors['lawyer'], execution.id, value, db=db)
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM review_runs')) == 0
        assert service.read_execution(actors['lawyer'], execution.id, db).state == 'awaiting_facts'
    monkeypatch.setattr(service, 'advance_execution', original)
    with database.session() as db:
        assert bridge.review_execution(actors['lawyer'], execution.id, value, db=db).state == 'completed'


def test_changed_material_manifest_cannot_enter_review(frozen_task):
    from cn_contract.task_drafts import bridge
    database, actors, _, execution, _, _, _ = frozen_task
    prepared, _ = prepare(frozen_task)
    value = review_input(frozen_task, prepared, confirm=True)
    changed = value.model_copy(update={'review': value.review.model_copy(update={'document_hashes': {}})})
    with pytest.raises(ServiceError) as error:
        with database.session() as db:
            bridge.review_execution(actors['lawyer'], execution.id, changed, db=db)
    assert error.value.code == 'VERSION_CONFLICT'


def test_revoked_case_membership_blocks_even_idempotent_preparation(frozen_task):
    from cn_contract.task_drafts import bridge
    from cn_contract.security import remove_membership
    database, actors, _, execution, matter_id, _, _ = frozen_task
    _, value = prepare(frozen_task)
    with database.session() as db:
        remove_membership(matter_id, actors['lawyer'].user_id, db)
    with pytest.raises(ServiceError) as error:
        with database.session() as db:
            bridge.prepare_execution(actors['lawyer'], execution.id, value, db=db)
    assert error.value.status_code == 403


def test_registered_synthetic_task_completes_in_assisted_desktop_without_changing_mode(frozen_task):
    from cn_contract.acceptance.assisted_registry import load_seed_policy
    from cn_contract.review import proposals
    from cn_contract.task_drafts import bridge
    from cn_contract.web import services
    database, actors, _, execution, matter_id, _, _ = frozen_task
    proposals.configure(database, 'assisted_draft', load_seed_policy())
    prepared, _ = prepare(frozen_task)
    assert prepared.state == 'awaiting_facts'
    value = review_input(frozen_task, prepared, confirm=True)
    with database.session() as db:
        assert proposals.is_assisted(db)
        with pytest.raises(ServiceError):
            services.review(matter_id, value.review, actors['lawyer'], db)
        result = bridge.review_execution(actors['lawyer'], execution.id, value, db=db)
        assert result.state == 'completed'
        assert proposals.is_assisted(db)
