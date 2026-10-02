"""Original versions and audits are immutable, including direct SQL writes."""
import importlib
from datetime import datetime, timezone
from io import BytesIO
from uuid import uuid4

import pytest

from cn_contract.config import load_settings
from cn_contract.domain import AuditEvent, Matter, Role, VersionInput


def api():
    try:
        return (importlib.import_module('cn_contract.persistence'),
                importlib.import_module('cn_contract.security'),
                importlib.import_module('cn_contract.audit'))
    except ModuleNotFoundError as exc:
        if exc.name in {'cn_contract.persistence', 'cn_contract.security', 'cn_contract.audit'}:
            pytest.fail('T02 must persist immutable original versions and redacted append-only audits')
        raise


def world(tmp_path, settings=None):
    p, s, a = api()
    database = p.Database(f'sqlite:///{tmp_path / "test.db"}', tmp_path / 'originals', settings or load_settings())
    with database.session() as db:
        user_id = s.provision_user('synthetic-lawyer', 'local-test-password', {Role.HANDLING_LAWYER}, db)
        token, _ = s.login('synthetic-lawyer', 'local-test-password', db)
        actor = s.authenticate(token, db)
        matter = Matter(id=uuid4(), client_ref='SYNTHETIC', title='虚构案件',
                        jurisdiction='CN-mainland', contract_type='sales', review_mode='pre_sign',
                        position='buyer', objectives=(), member_ids={user_id}, status='intake',
                        active_fact_version=None, active_policy_version=None, gate_issues=())
        p.provision_matter(matter, db)
    return p, s, a, database, actor, matter


def meta(matter_id, **changes):
    values = dict(matter_id=matter_id, original_name='../../虚构.pdf', mime='application/pdf',
                  baseline_view='original', supersedes_id=None)
    values.update(changes)
    return VersionInput(**values)


def test_version_immutable(tmp_path):
    p, s, a, database, actor, matter = world(tmp_path)
    with database.session() as db:
        version = p.create_version(meta(matter.id), actor, db, content=BytesIO(b'%PDF-SYNTHETIC'))
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    for statement in ('UPDATE document_versions SET sha256=:hash WHERE id=:id',
                      'DELETE FROM document_versions WHERE id=:id'):
        with database.session() as db:
            with pytest.raises(IntegrityError):
                db.execute(text(statement), {'id': str(version.id), 'hash': '0' * 64})
    with database.session() as db:
        assert p.read_original(matter.id, version.id, actor, db) == b'%PDF-SYNTHETIC'


def test_event_redaction(tmp_path):
    p, s, a, database, actor, matter = world(tmp_path)
    secret = 'SYNTHETIC-API-KEY-MUST-NOT-LOG'
    body = '虚构完整合同正文，不得被复制进审计日志'
    event = AuditEvent(id=uuid4(), matter_id=matter.id, actor_id=actor.user_id,
                       action='document_created', entity_type='document', entity_id=uuid4(),
                       before_hash=None, after_hash=None, timestamp=datetime.now(timezone.utc),
                       reason=secret + body, correlation_id=uuid4())
    with database.session() as db:
        identifier = a.append_event(event, db)
    with database.session() as db:
        row = db.get(p.AuditRow, str(identifier))
        assert secret not in row.payload
        assert body not in row.payload
        assert 'reason_sha256' in row.payload


def test_audit_direct_update_and_delete_denied(tmp_path):
    p, s, a, database, actor, matter = world(tmp_path)
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    with database.session() as db:
        p.create_version(meta(matter.id), actor, db, content=BytesIO(b'%PDF-SYNTHETIC'))
        identifier = db.query(p.AuditRow).first().id
    for statement in ('UPDATE audit_events SET payload=:payload WHERE id=:id',
                      'DELETE FROM audit_events WHERE id=:id'):
        with database.session() as db:
            with pytest.raises(IntegrityError):
                db.execute(text(statement), {'id': identifier, 'payload': '{}'})


def test_missing_or_empty_content_does_not_create_fake_version(tmp_path):
    p, s, a, database, actor, matter = world(tmp_path)
    with database.session() as db:
        for kwargs in ({}, {'content': BytesIO(b'')}):
            with pytest.raises(s.ServiceError):
                p.create_version(meta(matter.id), actor, db, **kwargs)
        assert db.query(p.DocumentRow).count() == 0


def test_actual_hash_safe_path_and_pending_parse(tmp_path):
    p, s, a, database, actor, matter = world(tmp_path)
    with database.session() as db:
        version = p.create_version(meta(matter.id), actor, db, content=BytesIO(b'abc'))
        assert version.sha256 == 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
        assert version.byte_size == 3
        assert version.parse_status == 'pending'
        assert version.storage_ref == f'{matter.id}/{version.id}/original.bin'
        assert version.created_at.tzinfo is timezone.utc


def test_stream_failure_and_transaction_rollback_remove_only_new_file(tmp_path):
    p, s, a, database, actor, matter = world(tmp_path)
    with database.session() as db:
        original = p.create_version(meta(matter.id), actor, db, content=BytesIO(b'original'))
    class BrokenStream:
        def read(self, size=-1):
            raise OSError('synthetic read failure')
    with pytest.raises(OSError):
        with database.session() as db:
            p.create_version(meta(matter.id), actor, db, content=BrokenStream())
    with pytest.raises(RuntimeError):
        with database.session() as db:
            p.create_version(meta(matter.id), actor, db, content=BytesIO(b'rollback'))
            raise RuntimeError('synthetic transaction failure')
    assert list(database.storage_root.rglob('original.bin')) == [database.storage_root / original.storage_ref]
    with database.session() as db:
        assert db.query(p.DocumentRow).count() == 1
        assert p.read_original(matter.id, original.id, actor, db) == b'original'


def test_supersedes_must_belong_to_same_matter(tmp_path):
    p, s, a, database, actor, matter = world(tmp_path)
    with database.session() as db:
        original = p.create_version(meta(matter.id), actor, db, content=BytesIO(b'first'))
        second = matter.model_copy(update={'id': uuid4()})
        p.provision_matter(second, db)
    with database.session() as db:
        with pytest.raises(s.ServiceError) as error:
            p.create_version(meta(second.id, supersedes_id=original.id), actor, db, content=BytesIO(b'second'))
        assert error.value.code == 'VERSION_CONFLICT'
        assert db.query(p.DocumentRow).count() == 1


def test_foreign_keys_enforced_for_document_owner(tmp_path):
    p, s, a, database, actor, matter = world(tmp_path)
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    with database.session() as db:
        version = p.create_version(meta(matter.id), actor, db, content=BytesIO(b'first'))
    with database.session() as db:
        with pytest.raises(IntegrityError):
            db.execute(text('DELETE FROM users WHERE id=:id'), {'id': str(actor.user_id)})


def test_concurrent_matter_file_limit(tmp_path):
    settings = load_settings().model_copy(update={'upload_max_matter_files': 1})
    p, s, a, database, actor, matter = world(tmp_path, settings)
    from concurrent.futures import ThreadPoolExecutor
    def upload():
        try:
            with database.session() as db:
                p.create_version(meta(matter.id), actor, db, content=BytesIO(b'synthetic'))
            return 'created'
        except s.ServiceError as exc:
            return str(exc.code)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: upload(), range(2)))
    assert sorted(results) == ['FILE_LIMIT', 'created']
    with database.session() as db:
        assert db.query(p.DocumentRow).count() == 1
        assert db.get(p.MatterRow, str(matter.id)).file_count == 1
    assert len(list(database.storage_root.rglob('original.bin'))) == 1


def test_concurrent_total_byte_limit(tmp_path):
    settings = load_settings().model_copy(update={'upload_max_matter_mib': 1})
    p, s, a, database, actor, matter = world(tmp_path, settings)
    from concurrent.futures import ThreadPoolExecutor
    def upload():
        try:
            with database.session() as db:
                p.create_version(meta(matter.id), actor, db, content=BytesIO(b'x' * 600_000))
            return 'created'
        except s.ServiceError as exc:
            return str(exc.code)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: upload(), range(2)))
    assert sorted(results) == ['FILE_LIMIT', 'created']
    with database.session() as db:
        assert db.get(p.MatterRow, str(matter.id)).total_bytes == 600_000


def test_read_only_original_and_no_overwrite(tmp_path):
    p, s, a, database, actor, matter = world(tmp_path)
    import stat
    with database.session() as db:
        first = p.create_version(meta(matter.id), actor, db, content=BytesIO(b'first'))
        second = p.create_version(meta(matter.id, supersedes_id=first.id), actor, db, content=BytesIO(b'second'))
    assert not (database.storage_root / first.storage_ref).stat().st_mode & stat.S_IWRITE
    with database.session() as db:
        assert p.read_original(matter.id, first.id, actor, db) == b'first'
        assert p.read_original(matter.id, second.id, actor, db) == b'second'


def test_unknown_audit_action_does_not_log_free_text(tmp_path):
    p, s, a, database, actor, matter = world(tmp_path)
    event = AuditEvent(id=uuid4(), matter_id=matter.id, actor_id=actor.user_id,
                       action='synthetic-secret-in-action', entity_type='document', entity_id=uuid4(),
                       before_hash=None, after_hash=None, timestamp=datetime.now(timezone.utc),
                       reason='synthetic-secret-in-reason', correlation_id=uuid4())
    with database.session() as db:
        with pytest.raises(ValueError):
            a.append_event(event, db)
        assert db.query(p.AuditRow).count() == 0


def test_archived_case_cannot_receive_new_original(tmp_path):
    p, s, a, database, actor, matter = world(tmp_path)
    with database.session() as db:
        p.transition_matter(matter.id, 'archived', actor, db)
    with database.session() as db:
        with pytest.raises(s.ServiceError) as error:
            p.create_version(meta(matter.id), actor, db, content=BytesIO(b'synthetic'))
        assert error.value.code == 'STATE_CONFLICT'
        assert db.query(p.DocumentRow).count() == 0


def test_missing_original_reports_generic_integrity_conflict(tmp_path):
    p, s, a, database, actor, matter = world(tmp_path)
    with database.session() as db:
        original = p.create_version(meta(matter.id), actor, db, content=BytesIO(b'synthetic'))
    import stat
    path = database.storage_root / original.storage_ref
    path.chmod(stat.S_IREAD | stat.S_IWRITE)
    path.unlink()
    with database.session() as db:
        with pytest.raises(s.ServiceError) as error:
            p.read_original(matter.id, original.id, actor, db)
        assert error.value.code == 'VERSION_CONFLICT'
        assert str(path) not in str(error.value)


def test_session_factory_close_removes_uncommitted_original(tmp_path):
    p, s, a, database, actor, matter = world(tmp_path)
    with database.session_factory() as db:
        p.create_version(meta(matter.id), actor, db, content=BytesIO(b'uncommitted'))
    with database.session() as db:
        assert db.query(p.DocumentRow).count() == 0
    assert list(database.storage_root.rglob('original.bin')) == []


def test_nested_commit_does_not_skip_outer_rollback_cleanup(tmp_path):
    p, s, a, database, actor, matter = world(tmp_path)
    with database.session_factory() as db:
        p.create_version(meta(matter.id), actor, db, content=BytesIO(b'parent'))
        with db.begin_nested():
            p.create_version(meta(matter.id), actor, db, content=BytesIO(b'child'))
        db.rollback()
    with database.session() as db:
        assert db.query(p.DocumentRow).count() == 0
    assert list(database.storage_root.rglob('original.bin')) == []


def test_nested_rollback_removes_only_child_original_and_parent_commits(tmp_path):
    p, s, a, database, actor, matter = world(tmp_path)
    with database.session_factory() as db:
        parent = p.create_version(meta(matter.id), actor, db, content=BytesIO(b'parent'))
        nested = db.begin_nested()
        p.create_version(meta(matter.id), actor, db, content=BytesIO(b'child'))
        nested.rollback()
        assert (database.storage_root / parent.storage_ref).read_bytes() == b'parent'
        db.commit()
    assert list(database.storage_root.rglob('original.bin')) == [database.storage_root / parent.storage_ref]
    with database.session() as db:
        assert db.query(p.DocumentRow).count() == 1
        assert p.read_original(matter.id, parent.id, actor, db) == b'parent'
