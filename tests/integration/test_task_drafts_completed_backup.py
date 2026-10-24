"""A completed native Mock task survives two authenticated archive round trips."""
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.acceptance.assisted_registry import load_seed_policy
from cn_contract.assistant import attachments, service as conversations
from cn_contract.config import load_settings
from cn_contract.ops import backup, workspace_backup
from cn_contract.ops.file_paths import filesystem_path
from cn_contract.persistence import Database, read_original
from cn_contract.review import proposals
from cn_contract.review.storage import read_run
from cn_contract.security import ServiceError, authenticate, login
from cn_contract.task_drafts import bridge, service
from cn_contract.web.local_server import initialize_workspace
from tests.helpers.legacy_assistant_backup import PASSPHRASE, PASSWORD, USERNAME
from test_task_drafts_bridge import frozen_task, prepare, review_input
from test_task_drafts_bridge_review import second_attachment


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path/'已完成任务原生合成库'
    initialize_workspace(root, USERNAME, PASSWORD, data_parent=tmp_path)
    database = Database('sqlite:///'+str(root/'workbench.db'), root/'protected',
                        load_settings(), initialize_schema=False)
    backup._mark_storage_flags(database)
    proposals.configure(database, 'assisted_draft', load_seed_policy())
    try:
        with database.session() as db:
            token, _ = login(USERNAME, PASSWORD, db)
            actor = authenticate(token, db)
            workspace_id = UUID(db.scalar(text('SELECT id FROM local_workspace_identity')))
        yield database, {'lawyer':actor}, workspace_id, conversations
    finally:
        database.engine.dispose()


def records(db):
    tables = ('task_channel_bindings','task_inbox_events','task_drafts','task_draft_events',
        'task_media_resolutions','assistant_attachments','assistant_attachment_parses',
        'assistant_material_snapshots','document_versions','review_runs','review_model_attempts')
    return {table:[tuple(row) for row in db.execute(text('SELECT * FROM '+table+' ORDER BY rowid'))]
            for table in tables}


def protected_files(root):
    protected = filesystem_path(root/'protected')
    return {path.relative_to(protected).as_posix():backup.digest(path.read_bytes())
            for path in protected.rglob('*') if path.is_file()}


def completed_supplement(frozen_task):
    database, actors, cid, parent, matter_id, first_id, raw = frozen_task
    actor = actors['lawyer']
    second = second_attachment(frozen_task)
    resolved = second.model_copy(update={'media_id':'awaiting-source'})
    with database.session() as db:
        binding = service.read_binding(actor, service.create_binding(actor, cid, db).id, db)
        receipt = service.receive_batch(actor, binding.id, d.TaskInboxBatchInput(
            expected_cursor=binding.cursor,next_cursor=binding.cursor+1,
            events=(d.TaskInboxEventInput(event_id='later-with-media', task_id=parent.draft_id,
                text='补充合成材料后一起审查', media=(
                    d.TaskMediaInput(media_id='awaiting-source', name='等待送达.docx', mime=second.mime),
                    d.TaskMediaInput(media_id='excluded-source', name='无关合成说明.pdf',
                        mime='application/pdf', status='unsupported'))),)), db)
        child = receipt.drafts[0]
        updated = service.update_draft(actor, child.id, d.TaskDraftUpdateInput(
            expected_revision=child.revision,main_attachment_id=first_id,media_resolutions=(
                d.TaskMediaResolutionInput(event_id=receipt.events[0].id,media_id='awaiting-source',
                    action='resolve',replacement=resolved),
                d.TaskMediaResolutionInput(event_id=receipt.events[0].id,media_id='excluded-source',
                    action='exclude',reason='独立合成无关材料，经显式排除'))), db)
        execution = service.freeze_draft(actor, child.id, d.TaskFreezeInput(
            expected_revision=updated.revision,manifest_sha256=updated.manifest_sha256), db)
    world = (database, actors, cid, execution, matter_id, first_id, raw)
    prepared, preparation = prepare(world)
    request = review_input(world, prepared, confirm=True)
    with database.session() as db:
        completed = bridge.review_execution(actor, execution.id, request, db=db)
        assert completed.state == 'completed'
        assert set(completed.source_versions) == {first_id, second.attachment_id}
        assert len(set(completed.source_versions.values())) == 2
        assert len(set(completed.document_versions.values())) == 1
        assert db.scalar(text('SELECT COUNT(*) FROM task_media_resolutions')) == 2
        assert json.loads(db.scalar(text('SELECT config_json FROM review_runs')))['task_execution_id'] == str(completed.id)
        history = records(db)
        completed_row = tuple(db.execute(text('SELECT * FROM task_executions WHERE id=:id'),
                             {'id':str(completed.id)}).one())
        saved_run = read_run(matter_id, completed.review_run_id, actor, db=db, current=True)
    return completed, preparation, request, binding.id, history, completed_row, saved_run


def test_completed_native_task_rebackup_preserves_sources_results_and_never_replays(frozen_task, tmp_path, monkeypatch):
    from cn_contract.web import services
    database, _, cid, parent, matter_id, _, raw = frozen_task
    completed, preparation, request, binding_id, expected, completed_row, saved_run = completed_supplement(frozen_task)
    source_root = Path(database.engine.url.database).parent
    source_before = (source_root/'workbench.db').read_bytes()
    files_before = protected_files(source_root)
    archive = tmp_path/'completed.qxbak'
    workspace_backup.create_workspace_backup(source_root, archive, PASSPHRASE, data_parent=tmp_path)

    calls = []
    def never_review(*args, **kwargs):
        calls.append(True)
        raise AssertionError('restored tasks must not replay the review')
    monkeypatch.setattr(services, 'review', never_review)
    for generation in (1, 2):
        result = workspace_backup.restore_workspace_backup(archive, tmp_path/f'restored-{generation}', PASSPHRASE)
        root = Path(result['restored_root'])
        restored = Database('sqlite:///'+str(root/'workbench.db'), root/'protected',
                            database.settings, initialize_schema=False)
        backup._mark_storage_flags(restored)
        proposals.configure(restored, 'assisted_draft', load_seed_policy())
        try:
            with restored.session() as db:
                token, _ = login(USERNAME, PASSWORD, db)
                actor = authenticate(token, db)
                assert service.read_execution(actor, completed.id, db) == completed
                assert service.read_execution(actor, parent.id, db).state == 'blocked'
                assert records(db) == expected
                assert tuple(db.execute(text('SELECT * FROM task_executions WHERE id=:id'),
                             {'id':str(completed.id)}).one()) == completed_row
                assert read_run(matter_id, completed.review_run_id, actor, db=db, current=False) == saved_run
                draft = service.read_draft(actor, completed.draft_id, db)
                assert len(draft.media_resolutions) == 2 and len(draft.events) == 2
                for source_id, version_id in completed.source_versions.items():
                    assert read_original(matter_id, version_id, actor, db) == raw
                assert db.scalar(text('SELECT COUNT(*) FROM ops_restore_fences')) == generation
                assert backup._file_references(db)
                operations = (
                    lambda: bridge.prepare_execution(actor, completed.id, preparation, db=db),
                    lambda: bridge.review_execution(actor, completed.id, request, db=db),
                    lambda: service.create_binding(actor, cid, db),
                    lambda: service.receive_batch(actor, binding_id, d.TaskInboxBatchInput(
                        expected_cursor=2,next_cursor=3,events=(d.TaskInboxEventInput(event_id='restored-new',
                            text='恢复副本禁止新增收件'),)), db),
                    lambda: service.freeze_draft(actor, completed.draft_id,d.TaskFreezeInput(
                        expected_revision=completed.revision,manifest_sha256=completed.manifest_sha256), db),
                )
                for operation in operations:
                    with pytest.raises(ServiceError) as denied:
                        operation()
                    assert denied.value.code == 'BLOCKED_LIVE'
                assert records(db) == expected and calls == []
            for source_id in completed.source_versions:
                assert attachments.read_original(actor, cid, source_id, database=restored) == raw
            assert protected_files(root) == files_before
            if generation == 1:
                archive = tmp_path/'completed-again.qxbak'
                workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
        finally:
            restored.engine.dispose()
    assert (source_root/'workbench.db').read_bytes() == source_before
    assert protected_files(source_root) == files_before
