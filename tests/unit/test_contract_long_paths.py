"""Legacy contract originals keep portable refs at Windows long I/O paths."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import stat

import pytest

from cn_contract.ops.file_paths import application_path, filesystem_path
from tests.unit.test_versions import meta, world


@pytest.fixture
def long_world(tmp_path):
    result = deep_world(tmp_path)
    yield result
    result[3].engine.dispose()


def deep_world(tmp_path, length=210, *, extended=False):
    p, s, a, original_database, actor, matter = world(tmp_path)
    original_database.engine.dispose()
    root = tmp_path / '合同原件'
    while len(str(root)) < length:
        root /= '中文资料' + '合成' * 12
    database = p.Database(f'sqlite:///{tmp_path / "test.db"}',
                          filesystem_path(root) if extended else root,
                          original_database.settings)
    return p, s, a, database, actor, matter


@pytest.mark.parametrize('length,extended', [(210, False), (285, False), (285, True)])
def test_long_original_create_read_preserves_portable_reference(tmp_path, length, extended):
    p, _, _, database, actor, matter = deep_world(tmp_path, length, extended=extended)
    content = '独立合成合同原件，不包含真实客户资料。'.encode('utf-8')
    with database.session() as db:
        version = p.create_version(meta(matter.id), actor, db, content=BytesIO(content))
    path = database.storage_root / version.storage_ref
    assert len(str(path.parent)) > 260
    assert database.storage_root == application_path(database.storage_root)
    assert version.storage_ref == f'{matter.id}/{version.id}/original.bin'
    assert version.sha256 == sha256(content).hexdigest()
    assert version.byte_size == len(content)
    assert not filesystem_path(path).stat().st_mode & stat.S_IWRITE
    with database.session() as db:
        assert p.read_original(matter.id, version.id, actor, db) == content
    database.engine.dispose()


def assert_originals(p, database, actor, matter, expected):
    """Observe bytes, SQL quota and version directories after transaction cleanup."""
    root = filesystem_path(database.storage_root)
    assert set(root.rglob('original.bin')) == {root / version.storage_ref for version, _ in expected}
    assert set((root / str(matter.id)).iterdir()) == {
        (root / version.storage_ref).parent for version, _ in expected}
    with database.session() as db:
        row = db.get(p.MatterRow, str(matter.id))
        assert row.file_count == len(expected)
        assert row.total_bytes == sum(len(content) for _, content in expected)
        assert db.query(p.DocumentRow).count() == len(expected)
        for version, content in expected:
            assert p.read_original(matter.id, version.id, actor, db) == content


@pytest.mark.parametrize('failure', ['stream', 'write', 'flush', 'fsync', 'chmod', 'audit', 'commit'])
def test_long_failure_removes_only_transaction_owned_original(long_world, monkeypatch, failure):
    p, _, audit, database, actor, matter = long_world
    content = b'previously committed synthetic original'
    with database.session() as db:
        original = p.create_version(meta(matter.id), actor, db, content=BytesIO(content))
        audit_count = db.query(p.AuditRow).count()

    def fail(*args, **kwargs):
        raise OSError('synthetic original I/O failure')

    class BrokenStream(BytesIO):
        def read(self, size=-1):
            if self.tell():
                fail()
            return super().read(size)

    content_stream = BrokenStream(b'partial') if failure == 'stream' else BytesIO(b'new original')
    if failure in {'write', 'flush'}:
        real_open = Path.open

        class BrokenTarget:
            def __init__(self, handle):
                self.handle = handle

            def __enter__(self):
                self.handle.__enter__()
                return self

            def __exit__(self, *args):
                return self.handle.__exit__(*args)

            def write(self, data):
                result = self.handle.write(data)
                if failure == 'write':
                    fail()
                return result

            def flush(self):
                fail()

        def failing_open(path, mode='r', *args, **kwargs):
            handle = real_open(path, mode, *args, **kwargs)
            return BrokenTarget(handle) if path.name == 'original.bin' and mode == 'xb' else handle

        monkeypatch.setattr(Path, 'open', failing_open)
    elif failure == 'fsync':
        monkeypatch.setattr(p.os, 'fsync', fail)
    elif failure == 'chmod':
        real_chmod = Path.chmod

        def failing_chmod(path, mode, *args, **kwargs):
            if path.name == 'original.bin' and mode == stat.S_IREAD:
                fail()
            return real_chmod(path, mode, *args, **kwargs)

        monkeypatch.setattr(Path, 'chmod', failing_chmod)
    elif failure == 'audit':
        monkeypatch.setattr(audit, 'append_event', fail)
    with pytest.raises(OSError, match='synthetic original I/O failure'):
        with database.session() as db:
            p.create_version(meta(matter.id), actor, db, content=content_stream)
            if failure == 'commit':
                from sqlalchemy import event
                event.listen(db, 'before_commit', fail, once=True)
    assert_originals(p, database, actor, matter, [(original, content)])
    with database.session() as db:
        assert db.query(p.AuditRow).count() == audit_count


@pytest.mark.parametrize('ending', ['rollback', 'close', 'nested_commit_outer_rollback'])
def test_long_uncommitted_originals_follow_transaction_lifetime(long_world, ending):
    p, _, _, database, actor, matter = long_world
    with database.session_factory() as db:
        p.create_version(meta(matter.id), actor, db, content=BytesIO(b'parent'))
        if ending == 'nested_commit_outer_rollback':
            with db.begin_nested():
                p.create_version(meta(matter.id), actor, db, content=BytesIO(b'child'))
        if ending != 'close':
            db.rollback()
    assert_originals(p, database, actor, matter, [])


def test_long_nested_rollback_preserves_parent_original(long_world):
    p, _, _, database, actor, matter = long_world
    with database.session_factory() as db:
        parent = p.create_version(meta(matter.id), actor, db, content=BytesIO(b'parent'))
        nested = db.begin_nested()
        p.create_version(meta(matter.id), actor, db, content=BytesIO(b'child'))
        nested.rollback()
        db.commit()
    assert_originals(p, database, actor, matter, [(parent, b'parent')])


def test_long_uuid_collision_does_not_clean_up_preexisting_original(long_world, monkeypatch):
    p, _, _, database, actor, matter = long_world
    with database.session() as db:
        original = p.create_version(meta(matter.id), actor, db, content=BytesIO(b'owned by prior transaction'))
    monkeypatch.setattr(p, 'uuid4', lambda: original.id)
    with pytest.raises(FileExistsError):
        with database.session() as db:
            p.create_version(meta(matter.id), actor, db, content=BytesIO(b'never overwrite'))
    assert_originals(p, database, actor, matter, [(original, b'owned by prior transaction')])


def test_long_directory_creation_failure_never_claims_an_original(long_world, monkeypatch):
    p, _, _, database, actor, matter = long_world
    with database.session() as db:
        original = p.create_version(meta(matter.id), actor, db, content=BytesIO(b'prior original'))
    real_mkdir = Path.mkdir

    def failing_mkdir(path, *args, **kwargs):
        if path.parent.name == str(matter.id):
            raise OSError('synthetic directory creation failure')
        return real_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'mkdir', failing_mkdir)
    with pytest.raises(OSError, match='synthetic directory creation failure'):
        with database.session() as db:
            p.create_version(meta(matter.id), actor, db, content=BytesIO(b'never created'))
    assert_originals(p, database, actor, matter, [(original, b'prior original')])


@pytest.mark.parametrize('damage', ['missing', 'size', 'digest'])
def test_long_missing_or_changed_original_reports_generic_conflict(long_world, damage):
    p, security, _, database, actor, matter = long_world
    with database.session() as db:
        original = p.create_version(meta(matter.id), actor, db, content=BytesIO(b'original'))
    path = filesystem_path(database.storage_root / original.storage_ref)
    path.chmod(stat.S_IREAD | stat.S_IWRITE)
    if damage == 'missing':
        path.unlink()
    else:
        path.write_bytes(b'tampered' if damage == 'digest' else b'x')
    with database.session() as db:
        with pytest.raises(security.ServiceError) as error:
            p.read_original(matter.id, original.id, actor, db)
        assert error.value.code == 'VERSION_CONFLICT'
        assert str(database.storage_root) not in str(error.value)


def test_long_cleanup_refuses_outside_root(long_world, tmp_path):
    p, _, _, database, _, _ = long_world
    outside = filesystem_path(tmp_path / 'outside.bin')
    outside.write_bytes(b'synthetic outside file')
    with pytest.raises(RuntimeError, match='unsafe original cleanup path'):
        p._remove_created(outside, database.storage_root)
    assert outside.read_bytes() == b'synthetic outside file'
