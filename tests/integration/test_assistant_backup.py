"""Old archive bytes remain readable after the conversation storage extension."""
from contextlib import closing
from pathlib import Path
import sqlite3
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from cn_contract.ops import backup, workspace_backup
from cn_contract.persistence import Database, read_original
from cn_contract.security import ServiceError, login, authenticate
from cn_contract.web import local_server
from tests.helpers.legacy_assistant_backup import legacy_world, write_old_cnbak, USERNAME, PASSWORD, PASSPHRASE
from tests.helpers.synthetic_operations import keys


def assert_assistant_schema(path):
    with closing(sqlite3.connect(path)) as connection:
        tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {'assistant_conversations', 'assistant_messages', 'assistant_runs', 'assistant_run_events'} <= tables


@pytest.mark.parametrize('version', ['pre-intake', 'intake-v1'])
def test_old_qxbak_restores_current_schema_and_original(tmp_path, version):
    root, database, _, matter, document, intake, raw = legacy_world(tmp_path, native=True, version=version)
    database.engine.dispose()
    archive = tmp_path/'old.qxbak'
    workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
    before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    archive_before = archive.read_bytes()
    result = workspace_backup.restore_workspace_backup(archive, tmp_path/'restored', PASSPHRASE)
    target = Path(result['restored_root'])
    assert_assistant_schema(target/'workbench.db')
    with TestClient(local_server.build_local_app(target, data_parent=tmp_path)) as client:
        assert client.post('/api/login', json={'username': USERNAME, 'password': PASSWORD}).status_code == 200
        response = client.get(f'/api/recovery/matters/{matter.id}/originals/{document.id}')
        assert response.content == raw
        if intake:
            assert client.get('/api/intakes/'+str(intake.id)).json()['consultation'] == intake.consultation
        assert client.post('/api/intakes', json={}).status_code == 409
    assert archive.read_bytes() == archive_before
    assert {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()} == before


@pytest.mark.parametrize('version', ['pre-intake', 'intake-v1'])
def test_old_cnbak_restores_current_schema_and_original(tmp_path, version):
    root, database, _, matter, document, intake, raw = legacy_world(tmp_path, native=False, version=version)
    archive = tmp_path/'old.cnbak'
    write_old_cnbak(database, archive)
    before = (root/'database.db').read_bytes()
    result = backup.restore_backup(archive, key_resolver=keys(), restore_parent=tmp_path/'restored', settings=database.settings)
    assert_assistant_schema(Path(result.restored_root)/'database.db')
    restored = backup.open_restored_database(result, settings=database.settings)
    try:
        with restored.session() as db:
            token, _ = login(USERNAME, PASSWORD, db)
            actor = authenticate(token, db)
            assert read_original(matter.id, document.id, actor, db) == raw
            if intake:
                from cn_contract.intake.service import read
                assert read(intake.id, actor, db).consultation == intake.consultation
        assert (root/'database.db').read_bytes() == before
    finally:
        restored.engine.dispose()
        database.engine.dispose()


@pytest.mark.parametrize('state', ['queued', 'awaiting_input'])
def test_current_native_restore_quarantines_runs_and_all_service_writes(tmp_path, state):
    from cn_contract import domain as d
    from cn_contract.assistant import service
    from cn_contract.web.workspace_upgrade import upgrade
    root, database, actor, _, _, _, _ = legacy_world(tmp_path, native=True)
    try:
        with local_server._worker_lock(root):
            upgrade(root)
        with database.session() as db:
            conversation = service.create_conversation(actor,
                d.AssistantConversationCreateInput(request_id=uuid4()), db)
            request = d.AssistantMessageInput(request_id=uuid4(), expected_scope=conversation.scope,
                expected_composer_revision=0, content='独立合成咨询，恢复时不得自动重新执行。')
            run = service.save_message(actor, conversation.scope.conversation_id, request, db)
            db.execute(text('UPDATE assistant_runs SET state=:state WHERE id=:id'),
                       {'id':str(run.id), 'state':state})
        archive = tmp_path/'current.qxbak'
        workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
        result = workspace_backup.restore_workspace_backup(archive, tmp_path/'restored', PASSPHRASE)
        target = Path(result['restored_root'])
        restored = Database('sqlite:///'+str(target/'workbench.db'), target/'protected',
                            database.settings, initialize_schema=False)
        backup._mark_storage_flags(restored)
        try:
            with restored.session() as db:
                with pytest.raises(ServiceError) as error:
                    service.get_run(actor, run.id, db)
                assert error.value.code == 'AUTHORIZATION_REQUIRED'
                token, _ = login(USERNAME, PASSWORD, db)
                current = authenticate(token, db)
                saved = service.get_run(current, run.id, db)
                assert saved.state == 'blocked'
                assert [(e.seq,e.event_type) for e in saved.events] == [(1,'message.accepted'),(2,'restore.quarantined')]
                assert saved.events[-1].payload['previous_state'] == state
                assert saved.selected_provider is saved.selected_model is None
                view = service.read_conversation(current, conversation.scope.conversation_id, db)
                assert view.messages[0].content == request.content
                writes = [
                    (service.create_conversation, (d.AssistantConversationCreateInput(request_id=uuid4()),)),
                    (service.save_draft, (view.scope.conversation_id, d.AssistantDraftInput(
                        expected_scope=view.scope, expected_composer_revision=view.composer_revision, content='新草稿'))),
                    (service.save_message, (view.scope.conversation_id, request)),
                ]
                for operation, arguments in writes:
                    with pytest.raises(ServiceError) as error:
                        operation(current, *arguments, db)
                    assert error.value.code == 'BLOCKED_LIVE'
                assert service.quarantine_runs(db) == 0
                assert len(service.get_run(current, run.id, db).events) == 2
        finally:
            restored.engine.dispose()
        with database.session() as db:
            assert service.get_run(actor, run.id, db).state == state
    finally:
        database.engine.dispose()


@pytest.mark.parametrize('native', [False, True])
@pytest.mark.parametrize('failure', ['ciphertext', 'migration'])
def test_legacy_restore_failure_never_publishes_or_changes_source(tmp_path, monkeypatch, native, failure):
    from cn_contract import schema_migrations
    from cn_contract.web import workspace_upgrade
    root, database, _, _, _, _, _ = legacy_world(tmp_path, native=native)
    try:
        archive = tmp_path/('old.qxbak' if native else 'old.cnbak')
        if native:
            workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
        else:
            write_old_cnbak(database, archive)
        before = {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}
        calls = []
        def fail_upgrade(*args, **kwargs):
            calls.append(True)
            raise RuntimeError('synthetic migration failure')
        monkeypatch.setattr(workspace_upgrade if native else schema_migrations,
                            'upgrade' if native else 'upgrade_database', fail_upgrade)
        if failure == 'ciphertext':
            raw = bytearray(archive.read_bytes()); raw[-1] ^= 1; archive.write_bytes(raw)
        archive_before = archive.read_bytes()
        destination = tmp_path/'restored'
        with pytest.raises(RuntimeError if failure == 'migration' else (ValueError, ServiceError)):
            if native:
                workspace_backup.restore_workspace_backup(archive, destination, PASSPHRASE)
            else:
                backup.restore_backup(archive, key_resolver=keys(), restore_parent=destination, settings=database.settings)
        assert calls == ([True] if failure == 'migration' else [])
        assert not destination.exists() or not list(destination.iterdir())
        assert archive.read_bytes() == archive_before
        assert {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()} == before
    finally:
        database.engine.dispose()
