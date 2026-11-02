"""Legacy cnbak restores must cross real Windows path limits without losing guards."""
from contextlib import closing
from pathlib import Path
import json
import sqlite3
from uuid import uuid4

import pytest
from sqlalchemy import select

from cn_contract import domain as d, schema_migrations
from cn_contract.assistant import service
from cn_contract.ops import backup, storage
from cn_contract.ops.file_paths import filesystem_path, sqlite_readonly_uri
from cn_contract.persistence import read_original
from cn_contract.security import authenticate, login, ServiceError
from cn_contract.storage_schema import CURRENT_VERSION, identify_schema
from tests.helpers.legacy_assistant_backup import write_old_cnbak, USERNAME, PASSWORD
from tests.helpers.synthetic_operations import keys
from tests.integration.test_assistant_model_upgrade_backup import old_workspace


def long_destination(tmp_path):
    destination = tmp_path/'独立旧格式恢复'
    while len(str(destination)) <= 300:
        destination /= 'legacy-restore-segment'
    return destination


@pytest.fixture
def legacy_archive(tmp_path):
    root, database, matter, document, raw, _ = old_workspace(tmp_path/'source', False)
    with database.session() as db:
        old_token, _ = login(USERNAME, PASSWORD, db)
    archive = tmp_path/'legacy.cnbak'
    write_old_cnbak(database, archive)
    source_before = {p.relative_to(root).as_posix(): p.read_bytes()
                     for p in root.rglob('*') if p.is_file()}
    archive_before = archive.read_bytes()
    try:
        yield root, database, matter, document, raw, old_token, archive
    finally:
        try:
            assert archive.read_bytes() == archive_before
            assert {p.relative_to(root).as_posix(): p.read_bytes()
                    for p in root.rglob('*') if p.is_file()} == source_before
        finally:
            database.engine.dispose()


def test_long_legacy_restore_opens_original_and_preserves_quarantine(legacy_archive, tmp_path, record_property):
    _, source, matter, document, raw, old_token, archive = legacy_archive
    destination = long_destination(tmp_path)
    report = backup.restore_backup(archive, key_resolver=keys(), restore_parent=destination,
                                   settings=source.settings)
    target = Path(report.restored_root)
    database_path = target/'database.db'
    original = target/'protected'/str(matter.id)/str(document.id)/'original.bin'
    assert target.is_relative_to(destination) and target != source.storage_root.parent
    assert len(str(database_path)) > 300 and len(str(original)) > 300
    assert not report.restored_root.startswith('\\\\?\\')
    assert report.ok and report.quarantine_ref is not None
    assert report.restored_database_sha256 == backup.digest(filesystem_path(database_path).read_bytes())
    assert filesystem_path(original).read_bytes() == raw
    with closing(sqlite3.connect(sqlite_readonly_uri(database_path), uri=True)) as connection:
        assert identify_schema(schema_migrations.database_rows(connection)) == CURRENT_VERSION
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
    restored = backup.open_restored_database(report, settings=source.settings)
    try:
        assert str(restored.engine.url.database) == str(database_path)
        assert restored.storage_root == target/'protected'
        with restored.session() as db:
            with pytest.raises(ServiceError) as unauthorized:
                authenticate(old_token, db)
            assert unauthorized.value.code == 'AUTHORIZATION_REQUIRED'
            token, _ = login(USERNAME, PASSWORD, db)
            actor = authenticate(token, db)
            assert read_original(matter.id, document.id, actor, db) == raw
            with pytest.raises(ServiceError) as blocked:
                service.create_conversation(actor, d.AssistantConversationCreateInput(request_id=uuid4()), db)
            assert blocked.value.code == 'BLOCKED_LIVE'
            fence = db.scalar(select(storage.RestoreFenceRow))
            policy = json.loads(fence.payload)
            assert policy['old_sessions_revoked'] is True
            assert policy['live_egress'] is False and policy['current_approvals_valid'] is False
            assert policy['task_inbox_enabled'] is False and policy['weixin_dispatch_enabled'] is False
            relocations = list(db.scalars(select(storage.FileRelocationRow)))
            assert relocations
            for row in relocations:
                assert not row.logical_ref.startswith('\\\\?\\')
                assert not backup.safe_relative(row.physical_ref).is_absolute()
    finally:
        restored.engine.dispose()
    record_property('restored_database_path_chars', len(str(database_path)))
    record_property('restored_original_path_chars', len(str(original)))


def test_long_legacy_migration_failure_reaches_sql_and_publishes_nothing(legacy_archive, tmp_path, monkeypatch):
    _, source, _, _, _, _, archive = legacy_archive
    from cn_contract.assistant import model_schema
    monkeypatch.setattr(model_schema, 'STATEMENTS', (*model_schema.STATEMENTS, 'INVALID SQL'))
    real_upgrade = schema_migrations.upgrade_database
    observed = []

    def observe_real_migration(connection):
        before = schema_migrations.database_rows(connection)
        assert identify_schema(before) == 'assistant-attachments-v1'
        observed.append('entered')
        try:
            return real_upgrade(connection)
        except sqlite3.Error:
            assert schema_migrations.database_rows(connection) == before
            assert not connection.in_transaction
            assert connection.execute('PRAGMA foreign_keys').fetchone() == (1,)
            observed.append('rolled_back')
            raise

    monkeypatch.setattr(schema_migrations, 'upgrade_database', observe_real_migration)
    destination = long_destination(tmp_path)
    with pytest.raises(sqlite3.Error, match='syntax error'):
        backup.restore_backup(archive, key_resolver=keys(), restore_parent=destination,
                              settings=source.settings)
    assert observed == ['entered', 'rolled_back']
    assert filesystem_path(destination).is_dir()
    assert list(filesystem_path(destination).iterdir()) == []
