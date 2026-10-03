"""T12 restored service reads, not just archive existence or decryption."""
from pathlib import Path
import pytest
from cn_contract.domain import BackupConfig
from cn_contract.security import ServiceError
from tests.helpers.synthetic_operations import feature, world, keys


def backup_world(tmp_path):
    database, actor, matter, version = world(tmp_path)
    cfg = BackupConfig(storage_ref=str(tmp_path/'archives'), key_ref='synthetic-key-1', retention_days=30)
    result = feature('backup', 'backup_and_verify')(cfg, database=database, actor=actor, key_resolver=keys(), restore_parent=tmp_path/'restores')
    return database, actor, matter, version, result


def test_actual_backup_restores_original_and_revokes_old_session(tmp_path):
    backup = feature('backup', 'backup_and_verify')
    database, actor, matter, version = world(tmp_path)
    cfg = BackupConfig(storage_ref=str(tmp_path/'archives'), key_ref='synthetic-key-1', retention_days=30)
    result = backup(cfg, database=database, actor=actor, key_resolver=keys(), restore_parent=tmp_path/'restores')
    assert result.ok and result.differences == ()
    restored = feature('backup', 'open_restored_database')(result, settings=database.settings)
    from cn_contract.persistence import read_original
    from cn_contract.security import authenticate
    # The read below is through a newly authenticated actual restored identity.
    from cn_contract.security import login
    with restored.session() as db:
        token, _ = login('synthetic-ops-admin', 'local-test-password', db)
        fresh = authenticate(token, db)
        assert read_original(matter.id, version.id, fresh, db) == (database.storage_root/str(matter.id)/str(version.id)/'original.bin').read_bytes()
    from cn_contract.persistence import SessionRow
    with restored.session() as db:
        assert db.get(SessionRow, str(actor.session_id)).revoked
    assert Path(result.backup_ref).is_file() and restored.storage_root != database.storage_root


def test_missing_key_reference_is_blocked_without_archive(tmp_path):
    backup = feature('backup', 'backup_and_verify')
    database, actor, _, _ = world(tmp_path)
    cfg = BackupConfig(storage_ref=str(tmp_path/'archives'), key_ref='unregistered-key', retention_days=30)
    with pytest.raises(ServiceError):
        backup(cfg, database=database, actor=actor, key_resolver=keys(), restore_parent=tmp_path/'restores')
    assert not list((tmp_path/'archives').glob('*'))


def test_restored_original_works_while_source_root_is_unavailable(tmp_path):
    import hashlib
    from cn_contract.persistence import read_original
    from cn_contract.security import login, authenticate
    database, actor, matter, version, result = backup_world(tmp_path)
    restored = feature('backup', 'open_restored_database')(result, settings=database.settings)
    root = database.storage_root
    moved = root.with_name('source-temporarily-unavailable')
    assert root.resolve().is_relative_to(tmp_path.resolve()) and not moved.exists()
    root.rename(moved)
    try:
        with restored.session() as db:
            token, _ = login('synthetic-ops-admin', 'local-test-password', db)
            fresh = authenticate(token, db)
            assert hashlib.sha256(read_original(matter.id, version.id, fresh, db)).hexdigest() == version.sha256
    finally: moved.rename(root)


@pytest.mark.parametrize('corruption', ['tag', 'header', 'wrong-key'])
def test_authenticated_archive_corruption_rejected_without_restore(tmp_path, corruption):
    from cn_contract.ops.backup import SyntheticKeyStore, restore_backup
    database, _, _, _, result = backup_world(tmp_path)
    raw = bytearray(Path(result.backup_ref).read_bytes())
    resolver = keys()
    if corruption == 'tag': raw[-1] ^= 1
    elif corruption == 'header': raw[35] ^= 1
    else: resolver = SyntheticKeyStore({'synthetic-key-1': b'1'*32})
    candidate = tmp_path/'corrupt.cnbak'; candidate.write_bytes(raw)
    new_parent = tmp_path/'never-restored'
    with pytest.raises((ValueError, ServiceError)):
        restore_backup(candidate, key_resolver=resolver, restore_parent=new_parent, settings=database.settings)
    assert not new_parent.exists()


@pytest.mark.parametrize('damage', ['trigger', 'table', 'fk'])
def test_raw_schema_is_checked_before_database_can_repair(tmp_path, damage):
    import sqlite3
    from cn_contract.ops.backup import validate_raw_database
    database, _, _, _, result = backup_world(tmp_path)
    path = Path(result.restored_root)/'database.db'
    with sqlite3.connect(path) as conn:
        if damage == 'trigger': conn.execute('DROP TRIGGER immutable_audit_events_update')
        elif damage == 'table': conn.execute('DROP TABLE ops_file_relocations')
        else:
            conn.execute('PRAGMA foreign_keys=OFF')
            conn.execute("UPDATE sessions SET user_id='no-such-user'")
    with pytest.raises(ValueError): validate_raw_database(path, database.settings)
    with pytest.raises(ValueError): feature('backup', 'open_restored_database')(result, settings=database.settings)


@pytest.mark.parametrize('path', ['../escape', 'C:/absolute', 'files/a:b', 'files/CON.docx', 'files/a\\b', '/root/absolute', 'files/a.'])
def test_archive_path_boundary(path):
    from cn_contract.ops.backup import safe_relative
    with pytest.raises(ValueError): safe_relative(path)


def test_missing_original_blocks_backup_and_keeps_source_database(tmp_path):
    database, actor, matter, version = world(tmp_path)
    original = database.storage_root/str(matter.id)/str(version.id)/'original.bin'
    original.chmod(0o600); original.unlink()
    cfg = BackupConfig(storage_ref=str(tmp_path/'archives'), key_ref='synthetic-key-1', retention_days=30)
    with pytest.raises((ValueError, OSError)):
        feature('backup', 'backup_and_verify')(cfg, database=database, actor=actor, key_resolver=keys(), restore_parent=tmp_path/'restores')
    assert Path(database.engine.url.database).is_file() and not list((tmp_path/'archives').glob('*.cnbak'))


def test_complete_actual_restore_budget_jobs_artifacts_and_new_database_fence(tmp_path):
    import asyncio
    import hashlib
    from decimal import Decimal
    from uuid import UUID
    from tests.helpers.synthetic_operations import seed_operational_world
    from cn_contract.security import login, authenticate
    from cn_contract.ops.storage import read_historical_artifact
    from cn_contract.ops.backup import backup_and_verify, open_restored_database
    from cn_contract.queries import ledger, gateway
    from cn_contract.providers.qcc_mcp import FactoryQccTransport
    from cn_contract.web.jobs import run_next_job
    from cn_contract.web.storage import JobRow
    from cn_contract.exports.approvals import read_bundle, download_artifact
    seed = seed_operational_world(tmp_path)
    source = seed['database']
    cfg = BackupConfig(storage_ref=str(tmp_path/'archives'), key_ref='synthetic-key-1', retention_days=30)
    result = backup_and_verify(cfg, database=source, actor=seed['owner'], key_resolver=keys(), restore_parent=tmp_path/'restores')
    restored = open_restored_database(result, settings=source.settings)
    # Re-open a different Database instance without a process-only fence flag.
    from cn_contract.persistence import Database
    reopened = Database(str(restored.engine.url), restored.storage_root, restored.settings, initialize_schema=False)
    from cn_contract.ops.backup import _mark_storage_flags
    _mark_storage_flags(reopened)
    moved = source.storage_root.with_name('originals-temporarily-unavailable')
    assert source.storage_root.is_relative_to(tmp_path.resolve()) and not moved.exists()
    source.storage_root.rename(moved)
    try:
        with reopened.session() as db:
            token, _ = login('query-lawyer', 'local-test-password', db); query_actor = authenticate(token, db)
            budget = ledger.read_budget(seed['query_matter'].id, query_actor, db=db)
            assert budget['used'] == Decimal('15') and budget['remaining'] == Decimal('5') and budget['calls'] == 1
            extra = seed['extra_plan']
            with pytest.raises(ServiceError) as caught:
                ledger.reserve_call(extra, extra.items[0].id, query_actor, db)
            assert caught.value.code == 'BUDGET_EXCEEDED'
            assert all(db.get(JobRow, str(j)).state == 'blocked' for j in seed['pending_job_ids'])
        with reopened.session() as db:
            token, _ = login('lawyer', 'fictional-pass-12345', db); lawyer = authenticate(token, db)
            for artifact in seed['artifacts']:
                raw = read_historical_artifact(UUID(artifact['id']), lawyer, db=db)
                assert raw == artifact['raw'] and hashlib.sha256(raw).hexdigest() == artifact['sha256']
                with pytest.raises(ServiceError): download_artifact(UUID(artifact['id']), lawyer, db=db)
            for ref in seed['patch_result_refs']:
                raw = read_historical_artifact(UUID(ref), lawyer, db=db)
                from cn_contract.exports.redline_adapter import baseline_texts
                from cn_contract.review.synthetic import select_fixture
                original = select_fixture('sales')[3]
                reject = baseline_texts(raw, accept=False)
                accept = baseline_texts(raw, accept=True)
                expected_reject = baseline_texts(original, accept=False)
                assert reject == expected_reject
                expected_accept = [seed['patch']['new_text'] if t == seed['patch']['old_text'] else t for t in expected_reject]
                assert accept == expected_accept and seed['patch']['new_text'] in accept
            with pytest.raises(ServiceError): read_bundle(UUID(seed['bundles'][0]['id']), lawyer, db=db)
        assert run_next_job(reopened) is None
        transport = FactoryQccTransport(reopened, actor=query_actor, matter_id=seed['query_matter'].id)
        with pytest.raises(ServiceError) as caught:
            asyncio.run(gateway.execute_plan(seed['unknown_plan'].id, query_actor, transport, database=reopened, matter_id=seed['query_matter'].id))
        assert caught.value.code == 'BLOCKED_LIVE' and transport.dispatch_count == 0
    finally: moved.rename(source.storage_root)


def test_source_sqlite_hardlink_is_rejected_before_backup(tmp_path):
    import os
    database, actor, _, _ = world(tmp_path)
    os.link(database.engine.url.database, tmp_path/'same-file-alias.db')
    cfg = BackupConfig(storage_ref=str(tmp_path/'archives'), key_ref='synthetic-key-1', retention_days=30)
    with pytest.raises(ValueError):
        feature('backup', 'backup_and_verify')(cfg, database=database, actor=actor, key_resolver=keys(), restore_parent=tmp_path/'restores')
    assert not list((tmp_path/'archives').glob('*.cnbak'))


def test_failed_materialization_leaves_no_restore_database(tmp_path, monkeypatch):
    from cn_contract.ops.backup import restore_backup
    database, _, _, _, report = backup_world(tmp_path)
    restore_parent = tmp_path/'failed-new-restores'
    actual = Path.write_bytes
    def fail_after_validated_snapshot(self, value):
        if self.name == 'database.db' and self.resolve().is_relative_to(restore_parent.resolve()):
            actual(self, value[:100])
            raise OSError('synthetic disk failure')
        return actual(self, value)
    monkeypatch.setattr(Path, 'write_bytes', fail_after_validated_snapshot)
    with pytest.raises(OSError):
        restore_backup(report.backup_ref, key_resolver=keys(), restore_parent=restore_parent, settings=database.settings)
    assert not list(restore_parent.rglob('database.db'))


def test_restored_new_patch_approval_cannot_reuse_old_current_run(tmp_path):
    from uuid import UUID, uuid4
    from cn_contract.domain import Patch
    from cn_contract.ops.backup import backup_and_verify, open_restored_database
    from cn_contract.security import login, authenticate
    from cn_contract.exports.approvals import approve_patch
    from tests.helpers.synthetic_operations import seed_operational_world
    seed = seed_operational_world(tmp_path)
    source = seed['database']
    cfg = BackupConfig(storage_ref=str(tmp_path/'archives'), key_ref='synthetic-key-1', retention_days=30)
    report = backup_and_verify(cfg, database=source, actor=seed['owner'], key_resolver=keys(), restore_parent=tmp_path/'restores')
    restored = open_restored_database(report, settings=source.settings)
    new_patch = Patch.model_validate({**seed['patch'], 'id': uuid4(), 'status': 'proposed', 'approved_by': None})
    with restored.session() as db:
        token, _ = login('lawyer', 'fictional-pass-12345', db); lawyer = authenticate(token, db)
        with pytest.raises(ServiceError) as caught:
            approve_patch(UUID(seed['matter_id']), UUID(seed['run']['id']), new_patch, lawyer, db=db)
        assert caught.value.code == 'BLOCKED_LIVE'


def test_actual_localhost_sdk_counter_does_not_change_after_restore(tmp_path):
    import asyncio
    from tests.helpers.synthetic_queries import setup, bind_loopback, plan, execute
    from tests.helpers.synthetic_qcc import sdk_server
    from cn_contract.web.app import initialize_storage
    from cn_contract.ops.backup import backup_and_verify, open_restored_database
    from cn_contract.providers.qcc_mcp import FactoryQccTransport
    from cn_contract.queries.gateway import execute_plan
    from cn_contract.security import login, authenticate
    context = setup(tmp_path, price='0')
    with sdk_server(state='success') as (cfg, counts, _):
        context = bind_loopback(context, cfg)
        database, owner, _, matter, _, _ = context
        initialize_storage(database)
        value = plan(context)
        receipts, original_transport = execute(context, value)
        assert counts['call'] == 1 and original_transport.dispatch_count == 1
        config = BackupConfig(storage_ref=str(tmp_path/'archives'), key_ref='synthetic-key-1', retention_days=30)
        result = backup_and_verify(config, database=database, actor=owner, key_resolver=keys(), restore_parent=tmp_path/'restores')
        restored = open_restored_database(result, settings=database.settings)
        with restored.session() as db:
            token, _ = login('query-lawyer', 'local-test-password', db); actor = authenticate(token, db)
        transport = FactoryQccTransport(restored, actor=actor, matter_id=matter.id)
        before = dict(counts)
        with pytest.raises(ServiceError): asyncio.run(execute_plan(value.id, actor, transport, database=restored, matter_id=matter.id))
        assert counts == before and transport.dispatch_count == 0
        # The older T07 discovery entrypoint can also contact the SDK. Restored
        # registered endpoints and a fresh admin login cannot remove the fence.
        from cn_contract.providers.qcc_registry import discover_tools
        with restored.session() as db:
            token, _ = login('synthetic-lawyer', 'local-test-password', db); fresh_owner = authenticate(token, db)
            with pytest.raises(ServiceError) as caught:
                asyncio.run(discover_tools(context[-1], actor=fresh_owner, matter_id=matter.id, db=db))
            assert caught.value.code == 'BLOCKED_LIVE'
        assert counts == before


@pytest.mark.parametrize('kind', ['header-bool-version', 'manifest-bool-version', 'float-size', 'list-key-ref', 'int-archive-id'])
def test_archive_metadata_strict_types_are_controlled(tmp_path, kind):
    from tests.helpers.synthetic_operations import rewrite_synthetic_archive
    from cn_contract.ops.backup import restore_backup
    database, _, _, _, report = backup_world(tmp_path)
    header_change, manifest_change = None, None
    if kind == 'header-bool-version': header_change = lambda v: v.update(version=True)
    elif kind == 'manifest-bool-version': manifest_change = lambda v: v.update(version=True)
    elif kind == 'float-size': manifest_change = lambda v: v['files'][0].update(size=float(v['files'][0]['size']))
    elif kind == 'list-key-ref': header_change = lambda v: v.update(key_ref=['synthetic-key-1'])
    else: header_change = lambda v: v.update(archive_id=123)
    candidate = tmp_path/'typed.cnbak'
    rewrite_synthetic_archive(report, candidate, header_change=header_change, manifest_change=manifest_change)
    parent = tmp_path/'rejected-types'
    with pytest.raises(ValueError): restore_backup(candidate, key_resolver=keys(), restore_parent=parent, settings=database.settings)
    assert not parent.exists()


def test_operational_seed_contains_actual_standalone_patch_result(tmp_path):
    from tests.helpers.synthetic_operations import seed_operational_world
    seed = seed_operational_world(tmp_path)
    assert seed['patch_result_refs'], 'standalone apply_patch must actually run; empty iteration is not coverage'
