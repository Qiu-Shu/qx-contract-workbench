"""Synthetic task drafts upgrade and restore without loss or automatic replay."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d, schema_migrations, storage_schema
from cn_contract.assistant import service as conversations
from cn_contract.config import canonical_json, load_settings
from cn_contract.ops import backup, workspace_backup
from cn_contract.persistence import Database
from cn_contract.security import ServiceError, authenticate, login
from cn_contract.storage_bootstrap import initialize_storage
from tests.helpers.legacy_assistant_backup import PASSPHRASE, USERNAME, PASSWORD
from tests.integration.test_assistant_attachment_backup import corrupt, source
from tests.integration.test_assistant_judge_schema import old_db
from test_task_drafts_bridge import frozen_task, prepare, review_input
from test_assistant_storage import workspace


TARGET = 'task-drafts-v1'
FROZEN = json.loads((Path(__file__).parents[1]/'fixtures/task_drafts_schema_predecessors.json').read_text('utf-8'))['signatures']
PREVIOUS = tuple(item['version'] for item in FROZEN if not item['native'])


def digest(rows):
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


@pytest.mark.parametrize('item', FROZEN, ids=lambda item: item['version']+('-native' if item['native'] else ''))
def test_every_predecessor_keeps_exact_raw_and_backup_fingerprints(item):
    rows = storage_schema.schema_rows(item['version'], native=item['native'])
    assert digest(rows) == item['raw']
    assert digest(storage_schema.normalized_schema(item['version'], native=item['native'])) == item['normalized']
    assert storage_schema.identify_schema(rows, native=item['native']) == item['version']


def test_task_family_is_a_named_additive_successor():
    assert storage_schema.VERSIONS[:len(PREVIOUS)+1] == PREVIOUS + (TARGET,)
    before = set(storage_schema.schema_rows(PREVIOUS[-1]))
    after = set(storage_schema.schema_rows(TARGET))
    assert before < after
    assert {row[2] for row in after-before} == {
        'task_channel_bindings', 'task_inbox_events', 'task_drafts',
        'task_draft_events', 'task_executions', 'task_media_resolutions'}


@pytest.mark.parametrize('version', PREVIOUS)
@pytest.mark.parametrize('native', [False, True])
def test_each_historical_schema_upgrades_to_tasks_without_losing_rows(tmp_path, version, native):
    with closing(old_db(tmp_path/'old.db', version, native)) as db:
        db.execute("INSERT INTO users VALUES ('synthetic-user','old-user','unused','[]',0)")
        db.commit()
        assert schema_migrations.upgrade_database(db) == storage_schema.CURRENT_VERSION
        assert schema_migrations.database_rows(db) == storage_schema.schema_rows(storage_schema.CURRENT_VERSION, native=native)
        assert db.execute('SELECT username FROM users').fetchall() == [('old-user',)]
        assert db.execute('SELECT * FROM task_executions').fetchall() == []
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        assert db.execute('PRAGMA foreign_keys').fetchone() == (1,)
        assert schema_migrations.upgrade_database(db) == storage_schema.CURRENT_VERSION


def test_failed_task_migration_leaves_legacy_schema_and_rows_intact(tmp_path, monkeypatch):
    with closing(old_db(tmp_path/'old.db', PREVIOUS[-1], False)) as db:
        before = schema_migrations.database_rows(db)
        original = schema_migrations.statements_for
        monkeypatch.setattr(schema_migrations, 'statements_for', lambda version:
            (*original(version), 'INVALID SQL') if version == TARGET else original(version))
        with pytest.raises(sqlite3.Error):
            schema_migrations.upgrade_database(db)
        assert schema_migrations.database_rows(db) == before
        assert not db.in_transaction


def test_fresh_and_upgraded_tasks_have_same_schema(tmp_path):
    database = Database('sqlite:///'+str(tmp_path/'new.db'), tmp_path/'protected', load_settings())
    try:
        initialize_storage(database)
        initialize_storage(database)
        with closing(sqlite3.connect(database.engine.url.database)) as db:
            actual = schema_migrations.database_rows(db)
        assert actual == storage_schema.schema_rows(storage_schema.CURRENT_VERSION)
        with closing(old_db(tmp_path/'old.db', PREVIOUS[-1], False)) as db:
            schema_migrations.upgrade_database(db)
            assert schema_migrations.database_rows(db) == actual
    finally:
        database.engine.dispose()


@pytest.mark.parametrize('damage', [
    'DROP TABLE task_executions',
    'DROP TRIGGER immutable_task_inbox_update',
    'ALTER TABLE task_drafts ADD COLUMN untrusted TEXT',
    'CREATE INDEX unexpected_task_index ON task_drafts(created_at)',
])
def test_partial_task_family_is_rejected_without_repair(tmp_path, damage):
    from cn_contract.task_drafts import schema
    database = Database('sqlite:///'+str(tmp_path/'new.db'), tmp_path/'protected', load_settings())
    try:
        initialize_storage(database)
        with database.engine.begin() as db:
            db.exec_driver_sql(damage)
        with closing(sqlite3.connect(database.engine.url.database)) as db:
            before = schema_migrations.database_rows(db)
        with pytest.raises(ValueError, match='DATABASE_SCHEMA_MISMATCH'):
            schema.initialize_storage(database)
        with closing(sqlite3.connect(database.engine.url.database)) as db:
            assert schema_migrations.database_rows(db) == before
    finally:
        database.engine.dispose()


def insert(db, table, row):
    db.execute(text('INSERT INTO '+table+' ('+','.join(row)+') VALUES ('+
                    ','.join(':'+key for key in row)+')'), row)


@pytest.fixture
def task_history(source):
    root, database, actor, cid, receipt, parsed, *_ = source
    binding, event, draft, execution = (uuid4() for _ in range(4))
    at = datetime.now(timezone.utc).isoformat()
    media = d.TaskMediaInput(media_id='synthetic-media', name=receipt.attachment.original_name,
        mime=receipt.attachment.mime, status='ready', attachment_id=receipt.attachment.id,
        sha256=receipt.attachment.sha256, parse_revision=parsed.parse.revision)
    payload = d.TaskInboxEventInput(event_id='synthetic-event', text='独立合成合同任务', media=(media,))
    raw = canonical_json(payload.model_dump(mode='json'))
    with database.session() as db:
        scope = conversations.read_conversation(actor, cid, db).scope
    manifest = d.TaskDraftManifest(draft_id=draft, conversation_id=cid, revision=1,
        scope=scope,
        instruction='独立合成合同任务', main_attachment_id=receipt.attachment.id,
        events=(d.TaskManifestEvent(id=event, event_id=payload.event_id,
            payload_sha256=hashlib.sha256(raw.encode()).hexdigest(), text=payload.text,
            media=(d.TaskManifestMedia(**media.model_dump(), result_sha256=parsed.parse.result_sha256,
                reading_status=parsed.parse.reading_status),)),))
    manifest_raw = canonical_json(manifest.model_dump(mode='json'))
    with database.session() as db:
        insert(db, 'task_channel_bindings', dict(id=str(binding), conversation_id=str(cid),
            channel='synthetic', cursor=1, created_at=at))
        insert(db, 'task_inbox_events', dict(id=str(event), binding_id=str(binding),
            event_id=payload.event_id, payload_json=raw, payload_sha256=hashlib.sha256(raw.encode()).hexdigest(), created_at=at))
        insert(db, 'task_drafts', dict(id=str(draft), conversation_id=str(cid), parent_draft_id=None,
            revision=1, state='collecting', instruction=manifest.instruction,
            main_attachment_id=str(receipt.attachment.id), created_at=at, updated_at=at))
        insert(db, 'task_draft_events', dict(draft_id=str(draft), event_id=str(event), ordinal=1))
        db.execute(text("UPDATE task_drafts SET state='frozen'"))
        insert(db, 'task_executions', dict(id=str(execution), draft_id=str(draft), revision=1,
            manifest_json=manifest_raw, manifest_sha256=hashlib.sha256(manifest_raw.encode()).hexdigest(),
            state='prepared', created_at=at, updated_at=at))
    return root, database, actor, cid, binding, draft, execution


@pytest.mark.parametrize('damage', ['payload_digest', 'manifest_digest', 'payload_cross_conversation',
    'draft_cross_conversation', 'manifest_cross_conversation', 'manifest_source_hash',
    'missing_event', 'workspace'])
def test_task_source_corruption_rejects_backup_and_authenticated_restore(task_history, tmp_path, monkeypatch, damage):
    root, database, actor, cid, *_ = task_history
    with database.session() as db:
        other = conversations.create_conversation(actor, d.AssistantConversationCreateInput(request_id=uuid4()), db)
    if damage in ('payload_digest', 'manifest_digest'):
        table, column = ('task_inbox_events', 'payload_sha256') if damage == 'payload_digest' else ('task_executions', 'manifest_sha256')
        corrupt(database, table, 'UPDATE '+table+' SET '+column+'=?', ('0'*64,))
    elif damage == 'draft_cross_conversation':
        corrupt(database, 'task_drafts', 'UPDATE task_drafts SET conversation_id=?', (str(other.scope.conversation_id),))
    elif damage == 'payload_cross_conversation':
        corrupt(database, 'task_channel_bindings', 'UPDATE task_channel_bindings SET conversation_id=?', (str(other.scope.conversation_id),))
    elif damage == 'missing_event':
        corrupt(database, 'task_draft_events', 'DELETE FROM task_draft_events')
    elif damage == 'workspace':
        corrupt(database, 'assistant_conversations', 'UPDATE assistant_conversations SET workspace_id=? WHERE id=?', (str(uuid4()), str(cid)))
    else:
        with database.session() as db:
            value = json.loads(db.scalar(text('SELECT manifest_json FROM task_executions')))
        if damage == 'manifest_cross_conversation':
            value['conversation_id'] = str(other.scope.conversation_id)
        else:
            value['events'][0]['media'][0]['sha256'] = '0'*64
        raw = canonical_json(value)
        corrupt(database, 'task_executions', 'UPDATE task_executions SET manifest_json=?,manifest_sha256=?',
                (raw, hashlib.sha256(raw.encode()).hexdigest()))
    rejected = tmp_path/'rejected.qxbak'
    with pytest.raises(ValueError):
        workspace_backup.create_workspace_backup(root, rejected, PASSPHRASE, data_parent=tmp_path)
    assert not rejected.exists()
    hostile = tmp_path/'authenticated-hostile.qxbak'
    with monkeypatch.context() as patch:
        patch.setattr(workspace_backup, '_file_references', lambda db: [])
        workspace_backup.create_workspace_backup(root, hostile, PASSPHRASE, data_parent=tmp_path)
    original = (root/'workbench.db').read_bytes()
    destination = tmp_path/'must-not-publish'
    with pytest.raises(ValueError):
        workspace_backup.restore_workspace_backup(hostile, destination, PASSPHRASE)
    assert not destination.exists() or not list(destination.iterdir())
    assert (root/'workbench.db').read_bytes() == original


@pytest.mark.parametrize('state', ['prepared','creating_matter','awaiting_facts','queued','running'])
def test_restore_blocks_each_pending_execution_and_all_task_writes(task_history, tmp_path, state):
    from cn_contract.task_drafts import service
    root, database, actor, cid, binding, draft, execution = task_history
    with database.session() as db:
        db.execute(text('UPDATE task_executions SET state=:state'), {'state':state})
        before = {table:[tuple(row) for row in db.execute(text('SELECT * FROM '+table))] for table in
            ('task_channel_bindings','task_inbox_events','task_drafts','task_draft_events')}
    archive = tmp_path/'tasks.qxbak'
    workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
    result = workspace_backup.restore_workspace_backup(archive, tmp_path/'restored', PASSPHRASE)
    restored_root = Path(result['restored_root'])
    restored = Database('sqlite:///'+str(restored_root/'workbench.db'), restored_root/'protected',
                        database.settings, initialize_schema=False)
    backup._mark_storage_flags(restored)
    try:
        with restored.session() as db:
            token, _ = login(USERNAME, PASSWORD, db)
            current_actor = authenticate(token, db)
            view = service.read_execution(current_actor, execution, db)
            assert view.state == 'blocked' and view.error == 'restored_read_only'
            assert service.quarantine_executions(db) == 0
            assert {table:[tuple(row) for row in db.execute(text('SELECT * FROM '+table))] for table in before} == before
            for operation in (
                lambda: service.create_binding(current_actor, cid, db),
                lambda: service.receive_batch(current_actor, binding,
                    d.TaskInboxBatchInput(expected_cursor=1,next_cursor=2,
                        events=(d.TaskInboxEventInput(event_id='new',text='不得重放'),)), db),
                lambda: service.freeze_draft(current_actor, draft,
                    d.TaskFreezeInput(expected_revision=view.revision,manifest_sha256=view.manifest_sha256), db),
                lambda: service.advance_execution(current_actor, execution, 'running', db, expected_state='blocked'),
            ):
                with pytest.raises(ServiceError) as rejected:
                    operation()
                assert rejected.value.code == 'BLOCKED_LIVE'
            backup._file_references(db)
        again = tmp_path/'tasks-again.qxbak'
        workspace_backup.create_workspace_backup(restored_root, again, PASSPHRASE, data_parent=tmp_path)
        workspace_backup.restore_workspace_backup(again, tmp_path/'restored-again', PASSPHRASE)
    finally:
        restored.engine.dispose()


def test_actual_task_service_history_and_late_supplement_pass_archive_checks(source):
    from cn_contract.task_drafts import service
    root, database, actor, cid, receipt, parsed, *_ = source
    ready = d.TaskMediaInput(media_id='ready',name=receipt.attachment.original_name,
        mime=receipt.attachment.mime,status='ready',attachment_id=receipt.attachment.id,
        sha256=receipt.attachment.sha256,parse_revision=parsed.parse.revision)
    pending = d.TaskMediaInput(media_id='pending',name='合成未到附件',mime='application/octet-stream')
    with database.session() as db:
        binding = service.create_binding(actor, cid, db)
        received = service.receive_batch(actor, binding.id,d.TaskInboxBatchInput(expected_cursor=0,next_cursor=1,
            events=(d.TaskInboxEventInput(event_id='actual',text='合成材料完整性测试',media=(ready,pending)),)), db)
        draft = received.drafts[0]
        updated = service.update_draft(actor, draft.id,d.TaskDraftUpdateInput(expected_revision=draft.revision,
            media_resolutions=(d.TaskMediaResolutionInput(event_id=received.events[0].id,media_id='pending',
                action='exclude',reason='独立合成排除记录'),)), db)
        frozen = service.freeze_draft(actor, draft.id,d.TaskFreezeInput(expected_revision=updated.revision,
            manifest_sha256=updated.manifest_sha256),db)
        late = service.receive_batch(actor,binding.id,d.TaskInboxBatchInput(expected_cursor=1,next_cursor=2,
            events=(d.TaskInboxEventInput(event_id='late',task_id=draft.id,text='另存补充草稿'),)), db)
        assert late.drafts[0].parent_draft_id == draft.id
        assert frozen.manifest.main_attachment_id == receipt.attachment.id
        assert backup._file_references(db)


@pytest.mark.parametrize('damage', [None, 'review_digest', 'document_map'])
def test_completed_bridge_provenance_survives_backup_and_rejects_mapping_damage(frozen_task, damage):
    from cn_contract.task_drafts import bridge
    database, actors, _, execution, *_ = frozen_task
    prepared, _ = prepare(frozen_task)
    request = review_input(frozen_task, prepared, confirm=True)
    with database.session() as db:
        completed = bridge.review_execution(actors['lawyer'], execution.id, request, db=db)
        assert completed.state == 'completed'
        assert backup._file_references(db)
    if damage is None:
        return
    if damage == 'review_digest':
        corrupt(database, 'task_executions', 'UPDATE task_executions SET review_input_sha256=?', ('0'*64,))
    else:
        changed = {str(key):'0'*64 for key in completed.document_versions}
        corrupt(database, 'task_executions', 'UPDATE task_executions SET document_versions_json=?', (canonical_json(changed),))
    with database.session() as db, pytest.raises(ValueError, match='TASK_DRAFT_INTEGRITY'):
        backup._file_references(db)


@pytest.mark.parametrize('actual', ['completed', 'failed'])
def test_archive_execution_state_cannot_contradict_real_mock_result(frozen_task, monkeypatch, actual):
    from cn_contract.task_drafts import bridge
    from cn_contract.web import services
    database, actors, _, execution, *_ = frozen_task
    prepared, _ = prepare(frozen_task)
    request = review_input(frozen_task, prepared, confirm=True)
    if actual == 'failed':
        original = services.run_review
        def require_missing_rules(*args, **kwargs):
            return original(*args, **kwargs, require_legal_rules=True)
        monkeypatch.setattr(services, 'run_review', require_missing_rules)
    with database.session() as db:
        result = bridge.review_execution(actors['lawyer'], execution.id, request, db=db)
        assert result.state == actual
        assert backup._file_references(db)
    corrupt(database, 'task_executions', 'UPDATE task_executions SET state=?',
            ('failed' if actual == 'completed' else 'completed',))
    with database.session() as db, pytest.raises(ValueError, match='TASK_DRAFT_INTEGRITY'):
        backup._file_references(db)
