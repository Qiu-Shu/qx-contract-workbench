"""Research dispatch identity is part of offline archive integrity."""
import json
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import research, service
from cn_contract.assistant.tools.library import LegalLibraryAdapter
from cn_contract.config import canonical_json, load_settings
from cn_contract.ops import backup, workspace_backup
from cn_contract.persistence import Database
from cn_contract.security import authenticate, login, ServiceError
from cn_contract.web import local_server
from tests.helpers.legacy_assistant_backup import USERNAME, PASSWORD, PASSPHRASE
from tests.integration.test_assistant_attachment_backup import corrupt
from tests.integration.test_assistant_library_backup import ledger, search
from tests.integration.test_assistant_library_adapter import library


@pytest.fixture
def history(tmp_path):
    root = tmp_path/'合成检索档案'/'main'
    local_server.initialize_workspace(root, USERNAME, PASSWORD, data_parent=tmp_path)
    database = Database('sqlite:///'+str(root/'workbench.db'), root/'protected',
        load_settings(), initialize_schema=False)
    backup._mark_storage_flags(database)
    with database.session() as db:
        token, _ = login(USERNAME, PASSWORD, db)
        actor = authenticate(token, db)
        view = service.create_conversation(actor, d.AssistantConversationCreateInput(request_id=uuid4()), db)
        value = research.enqueue_research(actor, view.scope.conversation_id, d.AssistantMessageInput(
            request_id=uuid4(), expected_scope=view.scope, expected_composer_revision=view.composer_revision,
            content='独立虚构租赁', requested_skill='legal_research'), db)
    result = research.execute_research(actor, value.run.id, database, LegalLibraryAdapter(None))
    yield root, database, actor, result
    database.engine.dispose()


def change_acceptance(database, run_id, field, value):
    with database.session() as db:
        raw = db.scalar(text("SELECT payload_json FROM assistant_run_events WHERE run_id=:run AND event_type='research.accepted'"),
            {'run':str(run_id)})
    payload = json.loads(raw)
    payload[field] = value
    corrupt(database, 'assistant_run_events',
        "UPDATE assistant_run_events SET payload_json=? WHERE run_id=? AND event_type='research.accepted'",
        (canonical_json(payload), str(run_id)))


def test_corrupt_acceptance_rejected_on_create_and_authenticated_restore(history, tmp_path, monkeypatch):
    root, database, _, result = history
    change_acceptance(database, result.run.id, 'call_id', str(uuid4()))
    archive = tmp_path/'bad.qxbak'
    with pytest.raises(ValueError, match='ASSISTANT_LIBRARY_INTEGRITY'):
        workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
    assert not archive.exists()
    # Model an authenticated corrupt archive without weakening restore validation.
    with monkeypatch.context() as patch:
        patch.setattr(workspace_backup, '_file_references', lambda db: [])
        workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
    source, encrypted = (root/'workbench.db').read_bytes(), archive.read_bytes()
    destination = tmp_path/'rejected'
    with pytest.raises(ValueError, match='ASSISTANT_LIBRARY_INTEGRITY'):
        workspace_backup.restore_workspace_backup(archive, destination, PASSPHRASE)
    assert not destination.exists() or not list(destination.iterdir())
    assert (root/'workbench.db').read_bytes() == source and archive.read_bytes() == encrypted


@pytest.mark.parametrize('fault', ['request_hash', 'workflow', 'audience', 'renamed', 'deleted',
    'duplicate', 'missing_receipt', 'marker_only'])
def test_research_identity_corruption_rejected_by_archive_and_reader(history, fault):
    _, database, actor, result = history
    run_id = str(result.run.id)
    if fault in {'request_hash', 'workflow'}:
        field, value = ('request_sha256', '0'*64) if fault == 'request_hash' else ('workflow', 'future-unknown-v9')
        change_acceptance(database, result.run.id, field, value)
    elif fault == 'audience':
        corrupt(database, 'assistant_run_events', "UPDATE assistant_run_events SET audience='client' WHERE run_id=? AND seq=2", (run_id,))
    elif fault == 'renamed':
        # Keep the payload but remove every research event-name clue.
        corrupt(database, 'assistant_run_events', "UPDATE assistant_run_events SET event_type=replace(event_type,'research.','legacy.') WHERE run_id=?", (run_id,))
    elif fault == 'deleted':
        corrupt(database, 'assistant_run_events', 'DELETE FROM assistant_run_events WHERE run_id=? AND seq=2', (run_id,))
        corrupt(database, 'assistant_run_events', 'UPDATE assistant_run_events SET seq=seq-1 WHERE run_id=? AND seq>2', (run_id,))
        corrupt(database, 'assistant_handler_receipts', 'UPDATE assistant_handler_receipts SET event_seq=event_seq-1 WHERE run_id=?', (run_id,))
    elif fault == 'duplicate':
        with database.session() as db:
            db.execute(text('''INSERT INTO assistant_run_events (run_id,seq,event_type,audience,payload_json,created_at)
                SELECT run_id,6,event_type,audience,payload_json,
                    (SELECT MAX(created_at) FROM assistant_run_events WHERE run_id=:id)
                FROM assistant_run_events WHERE run_id=:id AND seq=2'''), {'id':run_id})
    elif fault in {'missing_receipt', 'marker_only'}:
        corrupt(database, 'assistant_handler_receipts', 'DELETE FROM assistant_handler_receipts WHERE run_id=?', (run_id,))
        if fault == 'marker_only':
            corrupt(database, 'assistant_run_events', 'DELETE FROM assistant_run_events WHERE run_id=? AND seq>=3', (run_id,))
            with database.session() as db:
                db.execute(text("UPDATE assistant_runs SET state='queued' WHERE id=:id"), {'id':run_id})
    with database.session() as db:
        with pytest.raises(ValueError, match='ASSISTANT_LIBRARY_INTEGRITY'):
            backup._file_references(db)
        with pytest.raises(ServiceError) as error:
            research.read_research(actor, result.run.id, db)
        assert error.value.code == 'LIBRARY_RECORD_INVALID'


def test_legacy_legal_research_skill_with_b1_call_does_not_need_new_marker(ledger, library):
    _, database, _, run = ledger
    corrupt(database, 'assistant_runs', "UPDATE assistant_runs SET requested_skill='legal_research' WHERE id=?", (str(run.id),))
    search(ledger, library)
    with database.session() as db:
        assert backup._file_references(db) == []


def test_legacy_query_text_cannot_impersonate_workflow_discriminator(ledger):
    from cn_contract.assistant.library_handlers import begin_library_call
    _, database, actor, run = ledger
    begin_library_call(actor, run.id, uuid4(), d.LibraryHandlerRequest(
        tool='legal_library.search', query=d.AssistantLibraryQuery(text='local-research-v1')), database)
    with database.session() as db:
        current = service._owned(actor, run.scope.conversation_id, db)
        assert research.read_history(actor, current,
            d.MainGenerationHistoryQuery(message_ids=(run.message_id,)), db).items == ()
        assert backup._file_references(db) == []


@pytest.mark.parametrize('queued', [False, True])
def test_old_revoked_session_and_newer_draft_remain_offline_restorable(history, tmp_path, monkeypatch, queued):
    root, database, actor, result = history
    with database.session() as db:
        if queued:
            view = service.create_conversation(actor, d.AssistantConversationCreateInput(request_id=uuid4()), db)
            result = research.enqueue_research(actor, view.scope.conversation_id, d.AssistantMessageInput(
                request_id=uuid4(), expected_scope=view.scope, expected_composer_revision=view.composer_revision,
                content='另一个待执行的合成检索', requested_skill='legal_research'), db)
        current = service.read_conversation(actor, result.run.scope.conversation_id, db)
        service.save_draft(actor, current.scope.conversation_id, d.AssistantDraftInput(
            expected_scope=current.scope, expected_composer_revision=current.composer_revision, content='较新的独立合成草稿'), db)
        db.execute(text('UPDATE sessions SET revoked=1'))
    def forbidden(*args, **kwargs):
        pytest.fail('offline archival or history performed library I/O')
    monkeypatch.setattr(LegalLibraryAdapter, 'search', forbidden)
    monkeypatch.setattr(LegalLibraryAdapter, 'read_original', forbidden)
    archive = tmp_path/'valid.qxbak'
    workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
    restored = workspace_backup.restore_workspace_backup(archive, tmp_path/'restored', PASSPHRASE)
    target = Path(restored['restored_root'])
    recovered = Database('sqlite:///'+str(target/'workbench.db'), target/'protected', database.settings, initialize_schema=False)
    backup._mark_storage_flags(recovered)
    try:
        with recovered.session() as db:
            token, _ = login(USERNAME, PASSWORD, db)
            fresh = authenticate(token, db)
            saved = research.read_research(fresh, result.run.id, db)
            if queued:
                assert saved.run.id == result.run.id and saved.run.state == 'blocked' and saved.receipts == ()
            else:
                assert saved == result
            assert backup._file_references(db) == []
    finally:
        recovered.engine.dispose()
