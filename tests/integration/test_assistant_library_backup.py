"""Synthetic library history remains inspectable without granting restored execution."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.config import load_settings
from cn_contract.ops import backup, workspace_backup
from cn_contract.persistence import Database
from cn_contract.security import authenticate, login, ServiceError
from cn_contract.web import local_server
from tests.helpers.legacy_assistant_backup import USERNAME, PASSWORD, PASSPHRASE
from tests.integration.test_assistant_attachment_backup import corrupt
from tests.integration.test_assistant_library_adapter import library


@pytest.fixture
def ledger(tmp_path):
    root = tmp_path/'合成引用档案'/'main'
    local_server.initialize_workspace(root, USERNAME, PASSWORD, data_parent=tmp_path)
    database = Database('sqlite:///'+str(root/'workbench.db'), root/'protected',
                        load_settings(), initialize_schema=False)
    backup._mark_storage_flags(database)
    with database.session() as db:
        token, _ = login(USERNAME, PASSWORD, db)
        actor = authenticate(token, db)
        view = service.create_conversation(actor, d.AssistantConversationCreateInput(request_id=uuid4()), db)
        run = service.save_message(actor, view.scope.conversation_id, d.AssistantMessageInput(
            request_id=uuid4(), expected_scope=view.scope, expected_composer_revision=view.composer_revision,
            content='独立虚构租赁咨询，仅用于归档验证。'), db)
    yield root, database, actor, run
    database.engine.dispose()


def test_unfinished_tool_event_must_be_valid_before_archiving(ledger, tmp_path):
    root, database, _, run = ledger
    with database.session() as db:
        db.execute(text('''INSERT INTO assistant_run_events
            (run_id,seq,event_type,audience,payload_json,created_at)
            VALUES (:run,2,'tool.before','internal','{}',:at)'''),
            {'run':str(run.id), 'at':run.created_at.isoformat()})
    target = tmp_path/'invalid-unfinished.qxbak'
    with pytest.raises(ValueError, match='ASSISTANT_LIBRARY'):
        workspace_backup.create_workspace_backup(root, target, PASSPHRASE, data_parent=tmp_path)
    assert not target.exists()


def search(ledger, library, *, execute=True):
    from cn_contract.assistant.library_handlers import begin_library_call, execute_library_handler
    from cn_contract.assistant.tools.library import LegalLibraryAdapter
    _, database, actor, run = ledger
    call = begin_library_call(actor, run.id, uuid4(), d.LibraryHandlerRequest(
        tool='legal_library.search', query=d.AssistantLibraryQuery(text='租赁', kind='law_markdown', limit=8)), database)
    return (execute_library_handler(actor, run.id, call.event_seq, database, LegalLibraryAdapter(library[0]))
            if execute else call)


def test_native_roundtrip_preserves_offline_history_and_blocks_execution(ledger, library, tmp_path, monkeypatch):
    from cn_contract.assistant.library_handlers import begin_library_call, execute_library_handler, read_saved_citation
    from cn_contract.assistant.tools.library import LegalLibraryAdapter
    root, database, actor, run = ledger
    first = search(ledger, library)
    saved_id = first.receipt.result.citation_ids[0]
    call = begin_library_call(actor, run.id, uuid4(), d.LibraryHandlerRequest(
        tool='legal_library.read_original', saved_citation_id=saved_id), database)
    second = execute_library_handler(actor, run.id, call.event_seq, database, LegalLibraryAdapter(library[0]))
    with database.session() as db:
        original = read_saved_citation(actor, saved_id, db)
        assert original.citation.support_status == 'unverified'
        assert second.receipt.result.result.citation == original.citation
        assert second.receipt.result.citation_ids != (saved_id,)
    # Neither archiving nor history reads can treat the external library as required archive contents.
    def unavailable(*args, **kwargs):
        pytest.fail('archive/history access must not re-read the external library')
    monkeypatch.setattr(LegalLibraryAdapter, 'search', unavailable)
    monkeypatch.setattr(LegalLibraryAdapter, 'read_original', unavailable)
    with local_server._worker_lock(root):
        pass
    source_before = (root/'workbench.db').read_bytes()
    archive = tmp_path/'library.qxbak'
    workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
    archived = archive.read_bytes()
    result = workspace_backup.restore_workspace_backup(archive, tmp_path/'restored', PASSPHRASE)
    target = Path(result['restored_root'])
    restored = Database('sqlite:///'+str(target/'workbench.db'), target/'protected', database.settings, initialize_schema=False)
    backup._mark_storage_flags(restored)
    try:
        with restored.session() as db:
            assert db.scalar(text('SELECT revoked FROM sessions WHERE id=:id'), {'id':str(actor.session_id)}) == 1
            token, _ = login(USERNAME, PASSWORD, db)
            current = authenticate(token, db)
            assert service.get_run(current, run.id, db).state == 'blocked'
            assert read_saved_citation(current, saved_id, db) == original
            assert backup._file_references(db) == []
        with pytest.raises(ServiceError) as caught:
            execute_library_handler(current, run.id, call.event_seq, restored, LegalLibraryAdapter(None))
        assert caught.value.code == 'BLOCKED_LIVE'
        again = tmp_path/'again.qxbak'
        workspace_backup.create_workspace_backup(target, again, PASSPHRASE, data_parent=tmp_path)
        workspace_backup.restore_workspace_backup(again, tmp_path/'again', PASSPHRASE)
    finally:
        restored.engine.dispose()
    assert archive.read_bytes() == archived and (root/'workbench.db').read_bytes() == source_before


@pytest.mark.parametrize('change', ['revoked', 'new_input', 'new_draft', 'unfinished', 'rebound'])
def test_history_does_not_require_old_current_session_or_revision(ledger, library, change):
    _, database, actor, run = ledger
    search(ledger, library, execute=change != 'unfinished')
    if change == 'rebound':
        from tests.integration.test_assistant_storage import add_matter
        later_matter = add_matter(database, actor)
    with database.session() as db:
        if change == 'revoked':
            db.execute(text('UPDATE sessions SET revoked=1'))
            db.execute(text('UPDATE users SET disabled=1'))
        elif change == 'rebound':
            # A later binding keeps its earlier conversation-scoped citation as history.
            db.execute(text("UPDATE assistant_conversations SET binding_revision=binding_revision+1, scope_kind='matter', scope_ref=:id"),
                       {'id':str(later_matter)})
        elif change in ('new_input', 'new_draft'):
            service.cancel_run(actor, run.id, d.AssistantCancelInput(request_id=uuid4()), db)
            view = service.read_conversation(actor, run.scope.conversation_id, db)
            if change == 'new_input':
                service.save_message(actor, view.scope.conversation_id, d.AssistantMessageInput(
                    request_id=uuid4(), expected_scope=view.scope, expected_composer_revision=view.composer_revision,
                    content='下一轮完全虚构咨询。'), db)
            else:
                service.save_draft(actor, view.scope.conversation_id, d.AssistantDraftInput(
                    expected_scope=view.scope, expected_composer_revision=view.composer_revision,
                    content='新的合成草稿'), db)
        assert backup._file_references(db) == []


@pytest.mark.parametrize('execute', [False, True])
def test_cnbak_refuses_new_tool_events_even_without_completed_receipt(ledger, library, execute):
    _, database, *_ = ledger
    search(ledger, library, execute=execute)
    with database.session() as db, pytest.raises(ValueError, match='ASSISTANT_LIBRARY_REQUIRE_QXBAK'):
        backup._file_references(db, allow_assistant=False)


@pytest.mark.parametrize('fault', ['payload_hash','result_hash','citation_hash','receipt_scope',
    'receipt_time','citation_time','citation_missing','receipt_missing','citation_order','citation_id',
    'event_payload','event_audience','event_version','event_scope','event_composer','event_seq','event_time',
    'event_call_duplicate','event_limit','actor_session','message_revision','message_conversation','event_missing'])
def test_native_references_reject_library_history_corruption(ledger, library, fault):
    from cn_contract.config import canonical_json
    from cn_contract.assistant.library_records import sha
    _, database, _, run = ledger
    first = search(ledger, library)
    with database.session() as db:
        receipt = dict(db.execute(text('SELECT * FROM assistant_handler_receipts')).mappings().one())
        event = dict(db.execute(text("SELECT * FROM assistant_run_events WHERE event_type='tool.before'")).mappings().one())
    if fault in ('payload_hash','result_hash'):
        field = fault.replace('_hash','_sha256')
        corrupt(database, 'assistant_handler_receipts', f'UPDATE assistant_handler_receipts SET {field}=?', ('0'*64,))
    elif fault == 'citation_hash':
        corrupt(database, 'assistant_library_citations', 'UPDATE assistant_library_citations SET citation_sha256=?', ('0'*64,))
    elif fault == 'receipt_scope':
        value = json.loads(receipt['scope_json']); value['input_revision'] += 1
        corrupt(database, 'assistant_handler_receipts', 'UPDATE assistant_handler_receipts SET scope_json=?', (canonical_json(value),))
    elif fault in ('receipt_time','citation_time'):
        table = 'assistant_handler_receipts' if fault == 'receipt_time' else 'assistant_library_citations'
        corrupt(database, table, f'UPDATE {table} SET created_at=?', ('2000-01-01T00:00:00+00:00',))
    elif fault in ('citation_missing','receipt_missing'):
        table = 'assistant_library_citations' if fault == 'citation_missing' else 'assistant_handler_receipts'
        corrupt(database, table, f'DELETE FROM {table}')
    elif fault == 'citation_order':
        corrupt(database, 'assistant_library_citations', 'DELETE FROM assistant_library_citations WHERE ordinal=0')
    elif fault == 'citation_id':
        corrupt(database, 'assistant_library_citations', 'UPDATE assistant_library_citations SET id=? WHERE ordinal=0', (str(uuid4()),))
    elif fault == 'event_audience':
        corrupt(database, 'assistant_run_events', "UPDATE assistant_run_events SET audience='client' WHERE seq=2")
    elif fault in ('event_payload','event_version','event_scope','event_composer'):
        payload = json.loads(event['payload_json'])
        if fault == 'event_payload': payload['unexpected'] = True
        elif fault == 'event_version': payload['handler_version'] = '2'
        elif fault == 'event_scope': payload['scope']['input_revision'] = 100
        else: payload['expected_composer_revision'] = 100
        value = canonical_json(payload)
        corrupt(database, 'assistant_run_events', 'UPDATE assistant_run_events SET payload_json=? WHERE seq=2', (value,))
        corrupt(database, 'assistant_handler_receipts', 'UPDATE assistant_handler_receipts SET payload_sha256=?', (sha(value),))
    elif fault == 'event_seq':
        corrupt(database, 'assistant_run_events', 'UPDATE assistant_run_events SET seq=seq+10')
    elif fault == 'event_time':
        corrupt(database, 'assistant_run_events', "UPDATE assistant_run_events SET created_at='2000-01-01T00:00:00+00:00' WHERE seq=2")
    elif fault in ('event_call_duplicate','event_limit'):
        with database.session() as db:
            for seq in range(3, 4 if fault == 'event_call_duplicate' else 11):
                payload = json.loads(event['payload_json'])
                if fault == 'event_limit': payload['call_id'] = str(uuid4())
                db.execute(text('''INSERT INTO assistant_run_events (run_id,seq,event_type,audience,payload_json,created_at)
                    VALUES (:run,:seq,'tool.before','internal',:payload,:at)'''),
                    {'run':str(run.id), 'seq':seq, 'payload':canonical_json(payload), 'at':event['created_at']})
    elif fault == 'actor_session':
        corrupt(database, 'sessions', 'UPDATE sessions SET user_id=?', (str(uuid4()),))
    elif fault in ('message_revision','message_conversation'):
        field, value = ('source_revision', 100) if fault == 'message_revision' else ('conversation_id',str(uuid4()))
        corrupt(database, 'assistant_messages', f'UPDATE assistant_messages SET {field}=?', (value,))
    elif fault == 'event_missing':
        corrupt(database, 'assistant_run_events', 'DELETE FROM assistant_run_events WHERE seq=2')
    with database.session() as db, pytest.raises(ValueError, match='ASSISTANT_LIBRARY_INTEGRITY'):
        backup._file_references(db)


def test_authenticated_corrupt_archive_rejected_without_publication(ledger, library, tmp_path, monkeypatch):
    root, database, *_ = ledger
    search(ledger, library)
    corrupt(database, 'assistant_handler_receipts', 'UPDATE assistant_handler_receipts SET payload_sha256=?', ('0'*64,))
    target = tmp_path/'bad.qxbak'
    with pytest.raises(ValueError, match='ASSISTANT_LIBRARY'):
        workspace_backup.create_workspace_backup(root, target, PASSPHRASE, data_parent=tmp_path)
    assert not target.exists()
    with monkeypatch.context() as patch:
        patch.setattr(workspace_backup, '_file_references', lambda db: [])
        workspace_backup.create_workspace_backup(root, target, PASSPHRASE, data_parent=tmp_path)
    before, archived = (root/'workbench.db').read_bytes(), target.read_bytes()
    destination = tmp_path/'rejected'
    with pytest.raises(ValueError, match='ASSISTANT_LIBRARY'):
        workspace_backup.restore_workspace_backup(target, destination, PASSPHRASE)
    assert not destination.exists() or not list(destination.iterdir())
    assert (root/'workbench.db').read_bytes() == before and target.read_bytes() == archived


@pytest.mark.parametrize('fault', ['missing_source','cross_run','source_hash','source_time','duplicate_json'])
@pytest.mark.parametrize('execute', [False, True])
def test_original_read_dependency_is_checked_even_for_unfinished_calls(ledger, library, fault, execute):
    from cn_contract.assistant.library_handlers import begin_library_call, execute_library_handler
    from cn_contract.assistant.library_records import sha
    from cn_contract.assistant.tools.library import LegalLibraryAdapter
    from cn_contract.config import canonical_json
    _, database, actor, run = ledger
    first = search(ledger, library)
    saved = first.receipt.result.citation_ids[0]
    if fault == 'cross_run':
        with database.session() as db:
            view = service.create_conversation(actor, d.AssistantConversationCreateInput(request_id=uuid4()), db)
            other = service.save_message(actor, view.scope.conversation_id, d.AssistantMessageInput(
                request_id=uuid4(), expected_scope=view.scope, expected_composer_revision=view.composer_revision,
                content='另一个独立合成事项。'), db)
        other_receipt = search((ledger[0], database, actor, other), library)
        foreign_id = other_receipt.receipt.result.citation_ids[0]
    call = begin_library_call(actor, run.id, uuid4(), d.LibraryHandlerRequest(
        tool='legal_library.read_original', saved_citation_id=saved), database)
    if execute:
        execute_library_handler(actor, run.id, call.event_seq, database, LegalLibraryAdapter(library[0]))
    payload = call.payload.model_dump(mode='json')
    if fault in ('missing_source','cross_run'):
        payload['request']['saved_citation_id'] = str(uuid4() if fault == 'missing_source' else foreign_id)
    elif fault == 'source_hash':
        payload['citation_sha256'] = '0'*64
    elif fault == 'source_time':
        corrupt(database, 'assistant_handler_receipts', 'UPDATE assistant_handler_receipts SET created_at=? WHERE id=?',
            ('2099-01-01T00:00:00+00:00', str(first.receipt.id)))
        corrupt(database, 'assistant_library_citations', 'UPDATE assistant_library_citations SET created_at=? WHERE receipt_id=?',
            ('2099-01-01T00:00:00+00:00', str(first.receipt.id)))
    raw = canonical_json(payload)
    if fault == 'duplicate_json':
        raw = '{"handler_version":"1",' + raw[1:]
    corrupt(database, 'assistant_run_events', 'UPDATE assistant_run_events SET payload_json=? WHERE run_id=? AND seq=?',
        (raw, str(run.id), call.event_seq))
    if execute:
        corrupt(database, 'assistant_handler_receipts',
            'UPDATE assistant_handler_receipts SET payload_sha256=?,request_json=? WHERE run_id=? AND event_seq=?',
            (sha(raw), canonical_json(payload['request']), str(run.id), call.event_seq))
    with database.session() as db, pytest.raises(ValueError, match='ASSISTANT_LIBRARY_INTEGRITY'):
        backup._file_references(db)


def test_cnbak_restore_cannot_smuggle_new_library_history(ledger, library, tmp_path, monkeypatch):
    from tests.helpers.legacy_assistant_backup import write_old_cnbak
    from tests.helpers.synthetic_operations import keys
    root, database, *_ = ledger
    search(ledger, library)
    copied_path = tmp_path/'legacy-container.db'
    with closing(sqlite3.connect(root/'workbench.db')) as source, closing(sqlite3.connect(copied_path)) as copied:
        source.backup(copied)
        copied.execute('DROP TABLE local_workspace_identity')
        copied.commit()
    copied = Database('sqlite:///'+str(copied_path), tmp_path/'legacy-files', database.settings, initialize_schema=False)
    archive = tmp_path/'forbidden.cnbak'
    try:
        with monkeypatch.context() as patch:
            patch.setattr(backup, '_collect_files', lambda db: ({}, []))
            write_old_cnbak(copied, archive)
    finally:
        copied.engine.dispose()
    before, archive_before = (root/'workbench.db').read_bytes(), archive.read_bytes()
    destination = tmp_path/'cnbak-rejected'
    with pytest.raises(ValueError, match='ASSISTANT_LIBRARY_REQUIRE_QXBAK'):
        backup.restore_backup(archive, key_resolver=keys(), restore_parent=destination, settings=database.settings)
    assert not destination.exists() or not list(destination.iterdir())
    assert archive.read_bytes() == archive_before and (root/'workbench.db').read_bytes() == before


@pytest.mark.parametrize('operation', ['create', 'restore'])
def test_rehashed_outer_records_cannot_hide_invalid_citation_identity(ledger, library, tmp_path, monkeypatch, operation):
    from cn_contract.assistant.library_records import sha
    from cn_contract.config import canonical_json
    root, database, *_ = ledger
    search(ledger, library)
    with database.session() as db:
        receipt = dict(db.execute(text('SELECT * FROM assistant_handler_receipts')).mappings().one())
        citation = dict(db.execute(text('SELECT * FROM assistant_library_citations WHERE ordinal=0')).mappings().one())
    value = json.loads(citation['citation_json'])
    value['citation_id'] = '0'*64
    raw = canonical_json(value)
    result = json.loads(receipt['result_json'])
    result['result']['page']['citations'][0] = value
    result_raw = canonical_json(result)
    corrupt(database, 'assistant_library_citations',
        'UPDATE assistant_library_citations SET citation_json=?,citation_sha256=? WHERE id=?',
        (raw, sha(raw), citation['id']))
    corrupt(database, 'assistant_handler_receipts',
        'UPDATE assistant_handler_receipts SET result_json=?,result_sha256=? WHERE id=?',
        (result_raw, sha(result_raw), receipt['id']))
    source_before = (root/'workbench.db').read_bytes()
    archive = tmp_path/'invalid-content-identity.qxbak'
    if operation == 'create':
        with pytest.raises(ValueError, match='ASSISTANT_LIBRARY_INTEGRITY'):
            workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
        assert not archive.exists()
    else:
        # An authenticated hostile archive has both outer hashes recomputed; restore must still reject it.
        with monkeypatch.context() as patch:
            patch.setattr(workspace_backup, '_file_references', lambda db: [])
            workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
        archive_before = archive.read_bytes()
        destination = tmp_path/'must-not-publish'
        with pytest.raises(ValueError, match='ASSISTANT_LIBRARY_INTEGRITY'):
            workspace_backup.restore_workspace_backup(archive, destination, PASSPHRASE)
        assert not destination.exists() or not list(destination.iterdir())
        assert archive.read_bytes() == archive_before
    assert (root/'workbench.db').read_bytes() == source_before
