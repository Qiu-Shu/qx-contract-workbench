"""Default native synthetic PDF tasks survive authenticated, fenced qxbak restore."""
import hashlib
import json
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import attachments, service as conversations
from cn_contract.facts.confirm import confirm_facts
from cn_contract.matters import create_matter
from cn_contract.ops import workspace_backup
from cn_contract.persistence import get_fact_snapshot, get_parse_result, read_matter, read_original, transition_matter
from cn_contract.review.storage import read_run
from cn_contract.security import ServiceError, authenticate, login
from cn_contract.task_drafts import bridge, service
from cn_contract.web.local_server import build_local_app, initialize_workspace
from tests.helpers.legacy_assistant_backup import PASSPHRASE, PASSWORD, USERNAME
from test_task_drafts_completed_backup import protected_files, records


def test_completed_pdf_native_backup_preserves_pages_sources_results_and_fences_replay(tmp_path, monkeypatch):
    from cn_contract.web import services

    fixture = Path(__file__).parents[1] / 'fixtures/task-pdf-v1/native-sales.pdf'
    manifest = json.loads(fixture.with_name('manifest.json').read_text(encoding='utf-8'))
    raw = fixture.read_bytes()
    assert len(raw) == manifest['bytes'] and hashlib.sha256(raw).hexdigest() == manifest['sha256']
    source_root = tmp_path / '独立合成PDF原生库'
    initialize_workspace(source_root, USERNAME, PASSWORD, data_parent=tmp_path)
    app = build_local_app(source_root, data_parent=tmp_path)
    database = app.state.database
    restored = None
    try:
        with database.session() as db:
            token, _ = login(USERNAME, PASSWORD, db)
            actor = authenticate(token, db)
            conversation = conversations.create_conversation(actor,
                d.AssistantConversationCreateInput(request_id=uuid4(), display_title='合成PDF备份验收'), db)
        cid = conversation.scope.conversation_id
        uploaded = attachments.ingest_attachment(actor, cid, d.AssistantAttachmentInput(
            request_id=uuid4(), expected_scope=conversation.scope, original_name=fixture.name,
            mime='application/pdf', policy=d.AssistantMaterialPolicy(local_processing_accepted=True)),
            BytesIO(raw), database=database)
        current = attachments.read_materials(actor, cid, database=database)
        parsed = attachments.parse_attachment(actor, cid, uploaded.attachment.id,
            d.AssistantAttachmentParseInput(request_id=uuid4(), expected_scope=current.scope), database=database)
        assert parsed.parse.reading_status == 'readable'
        assert parsed.parse.result.pages == (1, 2)
        assert all(a.bbox and a.kind == 'pdf_span' for a in parsed.parse.result.anchors)
        with database.session() as db:
            binding = service.create_binding(actor, cid, db)
            receipt = service.receive_batch(actor, binding.id, d.TaskInboxBatchInput(expected_cursor=0,
                next_cursor=1, events=(d.TaskInboxEventInput(event_id='pdf-backup-1', text='审查独立合成PDF',
                    media=(d.TaskMediaInput(media_id='pdf-source', name=fixture.name, mime='application/pdf',
                        status='ready', attachment_id=uploaded.attachment.id, sha256=uploaded.attachment.sha256,
                        parse_revision=parsed.parse.revision),)),)), db)
            draft = receipt.drafts[0]
            frozen = service.freeze_draft(actor, draft.id, d.TaskFreezeInput(expected_revision=draft.revision,
                manifest_sha256=draft.manifest_sha256), db)
            matter = create_matter(d.MatterCreateInput(title='独立合成PDF备份案件', contract_type='sales',
                review_mode='pre_sign', position='buyer', objectives=('核对虚构金额及页码',)), actor, db)
            preparation = d.TaskExecutionPrepareInput(request_id=uuid4(), matter_id=matter.id)
            prepared = bridge.prepare_execution(actor, frozen.id, preparation, db=db)
            version_id = prepared.source_versions[uploaded.attachment.id]
            document_parse = get_parse_result(matter.id, version_id, actor, db)
            assert document_parse.pages == (1, 2)
            assert [(a.page, a.bbox, a.quote) for a in document_parse.anchors] == [
                (a.page, a.bbox, a.quote) for a in parsed.parse.result.anchors]
            facts = get_fact_snapshot(matter.id, read_matter(matter.id, actor, db).active_fact_version, actor, db)
            assert facts.facts and all(f.confirmation_status == 'unconfirmed' for f in facts.facts)
            confirmed = confirm_facts(matter.id, facts.version, tuple(d.FactDecision(fact_id=f.id,
                decision='confirmed', confirmed_value=f.typed_value, reason='验收者逐项核对独立虚构PDF')
                for f in facts.facts), actor, db=db)
            transition_matter(matter.id, 'ready_for_review', actor, db)
            request = d.TaskExecutionReviewInput(request_id=uuid4(), review=d.ReviewStartInput(
                fact_version=confirmed.version, document_hashes=prepared.document_versions))
            completed = bridge.review_execution(actor, frozen.id, request, db=db)
            assert completed.state == 'completed'
            saved_run = read_run(matter.id, completed.review_run_id, actor, db=db, current=True)
            assert saved_run.manifest.model_provider == 'mock'
            expected_records = records(db)
            expected_draft = service.read_draft(actor, draft.id, db)
            completed_row = tuple(db.execute(text('SELECT * FROM task_executions WHERE id=:id'),
                {'id': str(completed.id)}).one())
            assert db.scalar(text('SELECT count(*) FROM review_runs')) == 1
            assert db.scalar(text('SELECT count(*) FROM assistant_runs')) == 0
        source_before = (source_root / 'workbench.db').read_bytes()
        files_before = protected_files(source_root)
        archive = tmp_path / 'completed-pdf.qxbak'
        workspace_backup.create_workspace_backup(source_root, archive, PASSPHRASE, data_parent=tmp_path)

        calls = []
        def never_review(*args, **kwargs):
            calls.append(True)
            raise AssertionError('restored PDF must never run review again')
        monkeypatch.setattr(services, 'review', never_review)
        result = workspace_backup.restore_workspace_backup(archive, tmp_path / 'restored-pdf', PASSPHRASE)
        restored_root = Path(result['restored_root'])
        restored = build_local_app(restored_root, data_parent=tmp_path).state.database
        with restored.session() as db:
            token, _ = login(USERNAME, PASSWORD, db)
            restored_actor = authenticate(token, db)
            assert service.read_execution(restored_actor, completed.id, db) == completed
            assert service.read_draft(restored_actor, draft.id, db) == expected_draft
            assert records(db) == expected_records
            assert tuple(db.execute(text('SELECT * FROM task_executions WHERE id=:id'),
                {'id': str(completed.id)}).one()) == completed_row
            assert read_original(matter.id, version_id, restored_actor, db) == raw
            assert get_parse_result(matter.id, version_id, restored_actor, db) == document_parse
            assert read_run(matter.id, completed.review_run_id, restored_actor, db=db, current=False) == saved_run
            assert db.scalar(text('SELECT count(*) FROM ops_restore_fences')) == 1
            operations = (
                lambda: bridge.prepare_execution(restored_actor, completed.id, preparation, db=db),
                lambda: bridge.review_execution(restored_actor, completed.id, request, db=db),
                lambda: service.receive_batch(restored_actor, binding.id, d.TaskInboxBatchInput(
                    expected_cursor=1, next_cursor=2, events=(d.TaskInboxEventInput(event_id='no-replay',
                        text='恢复副本禁止新增收件'),)), db),
            )
            for operation in operations:
                with pytest.raises(ServiceError) as denied:
                    operation()
                assert denied.value.code == 'BLOCKED_LIVE'
            assert records(db) == expected_records and calls == []
        assert attachments.read_original(restored_actor, cid, uploaded.attachment.id, database=restored) == raw
        assert attachments.read_parse(restored_actor, cid, uploaded.attachment.id,
            parsed.parse.revision, database=restored) == parsed.parse
        assert protected_files(restored_root) == files_before
        assert (source_root / 'workbench.db').read_bytes() == source_before
        assert protected_files(source_root) == files_before
    finally:
        if restored is not None:
            restored.engine.dispose()
        database.engine.dispose()
