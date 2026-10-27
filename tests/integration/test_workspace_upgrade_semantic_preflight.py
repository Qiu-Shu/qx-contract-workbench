"""Native upgrade must reject invalid old business history before any publication."""
from contextlib import closing
from datetime import timedelta
import hashlib
import json
import sqlite3

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from cn_contract.ops import backup
from cn_contract.persistence import read_original
from cn_contract.storage_schema import CURRENT_VERSION, identify_schema, schema_rows
from cn_contract.web import local_server, workspace_upgrade
from cn_contract.weixin_inbox.generation_integrity import validate_peer_generations
from tests.helpers.synthetic_weixin_generations import append_generation, setup_history
from tests.helpers.synthetic_weixin_inbox import insert, poll_receipt
from tests.integration.test_weixin_dispatch_integrity import corrupt, rehash_receipt
from tests.integration.test_weixin_ingress_atomic import world
from tests.integration.test_weixin_provenance_backup import original_material


PREVIOUS = 'weixin-generations-v1'
NEXT = 'weixin-target-provenance-v1'


def old_history(world):
    history = setup_history(world)
    history['original'] = original_material(history)
    history['generation'] = append_generation(history)
    root, database = history['root'], history['database']
    with database.session() as db:
        db.execute(text('DROP TABLE assistant_followup_revisions'))
        db.execute(text('DROP TABLE assistant_evidence_revisions'))
        db.execute(text('DROP INDEX weixin_dispatch_binding_cursor'))
        db.execute(text('DROP TABLE weixin_descriptor_generations'))
    with closing(sqlite3.connect(root/'workbench.db')) as db:
        from tests.helpers.legacy_material_model import downgrade_material_model
        downgrade_material_model(db)
        assert identify_schema(db.execute(
            'SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall(), native=True) == PREVIOUS
    with database.session() as db:
        assert validate_peer_generations(db, allow_generations=True) == []
    with closing(sqlite3.connect(root/'workbench.db')) as db:
        marker = json.loads((root/'workspace.json').read_text('utf-8'))
        marker['schema_sha256'] = local_server._schema_hash(db)
    (root/'workspace.json').write_text(json.dumps(marker), encoding='utf-8')
    return history


def disk_state(root, *, skip=()):
    return {
        'files': {path.relative_to(root).as_posix(): path.read_bytes()
                  for path in root.rglob('*') if path.is_file() and path.relative_to(root).as_posix() not in skip},
        'directories': sorted(path.relative_to(root).as_posix()
                              for path in root.rglob('*') if path.is_dir()),
    }


def old_rows(root):
    with closing(sqlite3.connect(root/'workbench.db')) as db:
        names = [row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return {name: db.execute('SELECT * FROM "'+name+'" ORDER BY rowid').fetchall() for name in names}


@pytest.mark.parametrize('damage', ['later_poll', 'later_dispatch', 'generation_hash'])
def test_native_upgrade_rejects_old_semantics_before_db_marker_or_backup_changes(world, damage):
    history = old_history(world)
    database, generation = history['database'], history['generation']
    with database.session() as db:
        if damage == 'later_poll':
            revision, cursor = db.execute(text('''SELECT checkpoint_revision,upstream_cursor
                FROM weixin_accounts WHERE id=:id'''), {'id': str(history['account'].id)}).one()
            receipt = poll_receipt(history['account'].id, revision, cursor, cursor, (),
                                   generation.created_at+timedelta(microseconds=1))
            insert(db, 'weixin_poll_receipts', receipt.model_dump(mode='json', exclude={'descriptors'}))
            db.execute(text('UPDATE weixin_accounts SET checkpoint_revision=:next WHERE id=:id'),
                       {'next': receipt.next_revision, 'id': str(history['account'].id)})
        elif damage == 'later_dispatch':
            corrupt(db, 'UPDATE weixin_dispatch_receipts SET created_at=:at WHERE id=:id', {
                'at': (generation.created_at+timedelta(microseconds=1)).isoformat(),
                'id': str(history['dispatched'].id)})
            rehash_receipt(db, history['dispatched'].id)
        else:
            corrupt(db, 'UPDATE weixin_peer_generations SET generation_sha256=:hash WHERE id=:id',
                    {'hash': 'f'*64, 'id': str(generation.id)})
    with database.session() as db, pytest.raises(ValueError, match='WEIXIN_GENERATION_INTEGRITY'):
        validate_peer_generations(db, allow_generations=True)
    database.engine.dispose()
    root = history['root']
    before = disk_state(root)
    caught = None
    with local_server._worker_lock(root):
        try:
            workspace_upgrade.upgrade(root)
        except ValueError as error:
            caught = error
    if caught is None and damage == 'later_poll':
        # This genuinely invalid v17 history passes v18's intentionally broader poll policy.
        with database.session() as db:
            assert validate_peer_generations(db, allow_generations=True) == []
    assert caught is not None, 'native upgrade published old history which its own schema validator rejects'
    assert str(caught) == 'WORKSPACE_DATABASE_MISMATCH'
    assert disk_state(root) == before, 'rejection must precede DB, marker, receipt or backup-candidate writes'
    with closing(sqlite3.connect(root/'workbench.db')) as db:
        assert workspace_upgrade._rows(db) == schema_rows(PREVIOUS, native=True)


def test_valid_old_history_upgrades_once_preserving_rows_identity_and_originals(world):
    history = old_history(world)
    root, database = history['root'], history['database']
    database.engine.dispose()
    before = old_rows(root)
    marker = json.loads((root/'workspace.json').read_text('utf-8'))
    protected = disk_state(root/'protected')
    with local_server._worker_lock(root):
        workspace_upgrade.upgrade(root)
    assert {name: value for name, value in old_rows(root).items() if name in before} == before
    assert disk_state(root/'protected') == protected
    with closing(sqlite3.connect(root/'workbench.db')) as db:
        assert workspace_upgrade._rows(db) == schema_rows(CURRENT_VERSION, native=True)
    assert json.loads((root/'workspace.json').read_text('utf-8'))['workspace_id'] == marker['workspace_id']
    matter, version, raw = history['original']
    with database.session() as db:
        assert validate_peer_generations(db, allow_generations=True) == []
        assert read_original(matter.id, version.id, history['actor'], db) == raw
    database.engine.dispose()
    committed = disk_state(root)
    with local_server._worker_lock(root):
        workspace_upgrade.upgrade(root)
    assert disk_state(root) == committed


def marker_gap(history, monkeypatch):
    root, database = history['root'], history['database']
    database.engine.dispose()
    marker = (root/'workspace.json').read_bytes()
    def interrupted(*args):
        raise OSError('independent synthetic interrupted marker finalization')
    with monkeypatch.context() as patch:
        patch.setattr(workspace_upgrade, 'VERSIONS', workspace_upgrade.VERSIONS[:18])
        patch.setattr(workspace_upgrade, '_write_marker', interrupted)
        with local_server._worker_lock(root), pytest.raises(OSError, match='interrupted marker'):
            workspace_upgrade.upgrade(root)
    assert (root/'workspace.json').read_bytes() == marker
    with closing(sqlite3.connect(root/'workbench.db')) as db:
        assert workspace_upgrade._rows(db) == schema_rows(NEXT, native=True)
    return root/('upgrade-'+NEXT+'.json')


def corrupt_generation_file(path, identifier):
    with closing(sqlite3.connect(path)) as db:
        trigger = db.execute("SELECT sql FROM sqlite_master WHERE name='immutable_weixin_peer_generations_update'").fetchone()[0]
        db.execute('DROP TRIGGER immutable_weixin_peer_generations_update')
        db.execute('UPDATE weixin_peer_generations SET generation_sha256=? WHERE id=?', ('f'*64, str(identifier)))
        db.execute(trigger)
        db.commit()


def test_pending_current_database_corruption_cannot_finalize_old_marker(world, monkeypatch):
    history = old_history(world)
    marker_gap(history, monkeypatch)
    root = history['root']
    corrupt_generation_file(root/'workbench.db', history['generation'].id)
    before = disk_state(root)
    with local_server._worker_lock(root), pytest.raises(ValueError, match='WORKSPACE_DATABASE_MISMATCH'):
        workspace_upgrade.upgrade(root)
    assert disk_state(root) == before


def test_pending_backup_semantics_are_checked_even_after_its_outer_hash_is_recomputed(world, monkeypatch):
    history = old_history(world)
    receipt_path = marker_gap(history, monkeypatch)
    root, database = history['root'], history['database']
    receipt = json.loads(receipt_path.read_text('utf-8'))
    saved = root/receipt['backup']
    corrupt_generation_file(saved, history['generation'].id)
    receipt['backup_sha256'] = hashlib.sha256(saved.read_bytes()).hexdigest()
    receipt_path.write_text(json.dumps(receipt), encoding='utf-8')
    with closing(sqlite3.connect(saved)) as db:
        assert workspace_upgrade._rows(db) == schema_rows(PREVIOUS, native=True)
        assert db.execute('PRAGMA quick_check').fetchall() == [('ok',)]
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        assert db.execute('SELECT id FROM local_workspace_identity').fetchall() == [(
            json.loads((root/'workspace.json').read_text('utf-8'))['workspace_id'],)]
    with database.session() as db:
        assert validate_peer_generations(db, allow_generations=True) == []
    database.engine.dispose()
    before = disk_state(root)
    with local_server._worker_lock(root), pytest.raises(ValueError, match='WORKSPACE_DATABASE_MISMATCH'):
        workspace_upgrade.upgrade(root)
    assert disk_state(root) == before


def test_business_change_after_upgrade_receipt_is_rechecked_before_ddl(world, monkeypatch):
    history = old_history(world)
    root, database = history['root'], history['database']
    database.engine.dispose()
    atomic = workspace_upgrade._atomic_json
    lock_bytes = (root/'worker.lock').read_bytes()
    injected = []
    def publish_then_corrupt(path, value):
        atomic(path, value)
        if path.name == 'upgrade-'+NEXT+'.json':
            corrupt_generation_file(root/'workbench.db', history['generation'].id)
            # Windows byte-range locking prevents reading worker.lock while it is held.
            injected.append(disk_state(root, skip=('worker.lock',)))
    monkeypatch.setattr(workspace_upgrade, '_atomic_json', publish_then_corrupt)
    with local_server._worker_lock(root), pytest.raises(ValueError, match='WORKSPACE_DATABASE_MISMATCH'):
        workspace_upgrade.upgrade(root)
    assert len(injected) == 1
    assert disk_state(root, skip=('worker.lock',)) == injected[0]
    assert (root/'worker.lock').read_bytes() == lock_bytes
    with closing(sqlite3.connect(root/'workbench.db')) as db:
        assert workspace_upgrade._rows(db) == schema_rows(PREVIOUS, native=True)


def test_preflight_file_reference_reader_cannot_write_the_source_database(world, monkeypatch):
    history = old_history(world)
    root, database = history['root'], history['database']
    database.engine.dispose()
    before = disk_state(root)
    blocked = []
    def attempt_write(records, **kwargs):
        try:
            records.execute(text('UPDATE users SET username=username'))
        except OperationalError as error:
            blocked.append(error.orig.sqlite_errorcode)
            raise
    monkeypatch.setattr(backup, '_file_references', attempt_write)
    with local_server._worker_lock(root), pytest.raises(ValueError, match='WORKSPACE_DATABASE_MISMATCH'):
        workspace_upgrade.upgrade(root)
    assert blocked == [sqlite3.SQLITE_READONLY]
    assert disk_state(root) == before


def test_locked_preflight_prevents_an_independent_writer_changing_its_snapshot(world, monkeypatch):
    history = old_history(world)
    root, database = history['root'], history['database']
    database.engine.dispose()
    before = old_rows(root)
    references = backup._file_references
    probes = []
    def probe_writer(records, **kwargs):
        with closing(sqlite3.connect(root/'workbench.db', timeout=0)) as writer:
            try:
                writer.execute('UPDATE users SET username=username')
                probes.append('writer acquired; rolled back')
                writer.rollback()
            except sqlite3.OperationalError as error:
                assert error.sqlite_errorcode == sqlite3.SQLITE_BUSY
                probes.append('writer blocked')
        return references(records, **kwargs)
    monkeypatch.setattr(backup, '_file_references', probe_writer)
    with local_server._worker_lock(root):
        workspace_upgrade.upgrade(root)
    assert 'writer blocked' in probes
    assert {name: value for name, value in old_rows(root).items() if name in before} == before
