"""Real qxbak round trips of independent SQL fixtures, without runtime ingress."""
import json
from pathlib import Path

import pytest
from sqlalchemy import text

from cn_contract.config import load_settings
from cn_contract.ops import backup, workspace_backup
from cn_contract.ops.storage import require_active
from cn_contract.persistence import Database
from cn_contract.security import ServiceError, authenticate, login
from cn_contract.web.local_server import _worker_lock, initialize_workspace
from cn_contract.weixin_inbox.integrity import validate_weixin_records
from tests.helpers.legacy_assistant_backup import PASSWORD, PASSPHRASE, USERNAME
from tests.helpers.synthetic_weixin_inbox import seed_history, snapshot


@pytest.fixture
def source(tmp_path):
    root = tmp_path/'独立虚构收件备份'
    initialize_workspace(root, USERNAME, PASSWORD, data_parent=tmp_path)
    database = Database('sqlite:///'+str(root/'workbench.db'), root/'protected',
                        load_settings(), initialize_schema=False)
    backup._mark_storage_flags(database)
    try:
        with database.session() as db:
            token, _ = login(USERNAME, PASSWORD, db)
            actor = authenticate(token, db)
        seed = seed_history(database, actor)
        # Maintenance's persistent coordination file is not a business mutation.
        with _worker_lock(root):
            pass
        yield root, database, seed
    finally:
        database.engine.dispose()


def files(root):
    return {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_complete_inbox_history_survives_two_qxbak_generations_without_dispatch(source, tmp_path):
    root, database, seed = source
    with database.session() as db:
        expected = snapshot(db)
        assert validate_weixin_records(db, allow_inbox=True) == []
        with pytest.raises(ServiceError) as denied:
            validate_weixin_records(db)
        assert denied.value.code == 'DATA_POLICY_UNAPPROVED'
        # Existing task bindings can reject a partial archive before the inbox gate.
        with pytest.raises((ValueError, ServiceError)):
            backup._file_references(db, allow_assistant=False)
    original = files(root)
    archive = tmp_path/'收件历史.qxbak'
    workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
    assert '独立虚构收件'.encode() not in archive.read_bytes()
    for generation in (1, 2):
        result = workspace_backup.restore_workspace_backup(archive, tmp_path/('恢复'+str(generation)), PASSPHRASE)
        restored_root = Path(result['restored_root'])
        assert result['quarantined'] is True and restored_root != root
        restored = Database('sqlite:///'+str(restored_root/'workbench.db'), restored_root/'protected',
                            database.settings, initialize_schema=False)
        backup._mark_storage_flags(restored)
        try:
            with restored.session() as db:
                assert snapshot(db) == expected
                assert validate_weixin_records(db, allow_inbox=True) == []
                backup._file_references(db)
                fences = db.scalars(text('SELECT payload FROM ops_restore_fences')).all()
                assert len(fences) == generation
                assert all(json.loads(raw)['weixin_inbox_enabled'] is False for raw in fences)
                with pytest.raises(ServiceError) as fenced:
                    require_active(db)
                assert fenced.value.code == 'BLOCKED_LIVE'
                for table in ('task_inbox_events','task_drafts','task_executions','assistant_runs'):
                    assert db.scalar(text('SELECT count(*) FROM '+table)) == 0
                assert db.scalar(text('SELECT sum(cursor) FROM task_channel_bindings')) == 0
                assert db.scalar(text('SELECT checkpoint_revision FROM weixin_accounts')) == 3
                assert db.scalar(text('SELECT upstream_cursor FROM weixin_accounts')) == seed['receipts'][-1].next_cursor
                assert db.scalar(text('SELECT count(*) FROM weixin_peer_bindings WHERE revoked_at IS NOT NULL')) == 1
                assert snapshot(db) == expected
            if generation == 1:
                archive = tmp_path/'恢复后再次备份.qxbak'
                workspace_backup.create_workspace_backup(restored_root, archive, PASSPHRASE, data_parent=tmp_path)
        finally:
            restored.engine.dispose()
    assert files(root) == original


def corrupt(database, statement):
    """Restore exact trigger text so rejection exercises record integrity, not DDL."""
    with database.session() as db:
        triggers = db.execute(text("SELECT name,sql FROM sqlite_master WHERE type='trigger' AND name LIKE '%weixin%'")).all()
        for name, _ in triggers:
            db.execute(text('DROP TRIGGER '+name))
        db.execute(text(statement))
        for _, ddl in triggers:
            db.execute(text(ddl))


@pytest.mark.parametrize('statement', [
    "UPDATE weixin_accounts SET upstream_cursor='synthetic-broken-checkpoint'",
    "UPDATE weixin_poll_receipts SET receipt_sha256='"+'0'*64+"'",
    "UPDATE weixin_inbox_descriptors SET source_event_id='wx1:"+'0'*64+"' WHERE ordinal=1",
])
def test_authenticated_corrupt_inbox_archive_never_publishes_restore(source, tmp_path, monkeypatch, statement):
    root, database, _ = source
    corrupt(database, statement)
    destination = tmp_path/'不应发布.qxbak'
    with pytest.raises(ValueError):
        workspace_backup.create_workspace_backup(root, destination, PASSPHRASE, data_parent=tmp_path)
    assert not destination.exists()
    # A valid encryption tag cannot turn corrupt database provenance into valid history.
    archive = tmp_path/'认证但损坏.qxbak'
    with monkeypatch.context() as patch:
        patch.setattr(workspace_backup, '_file_references', lambda db: [])
        workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
    original = files(root)
    target = tmp_path/'拒绝恢复'
    with pytest.raises(ValueError):
        workspace_backup.restore_workspace_backup(archive, target, PASSPHRASE)
    assert not target.exists() or not list(target.iterdir())
    assert files(root) == original
