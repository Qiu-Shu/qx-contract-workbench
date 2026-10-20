"""Independent synthetic Spec probes, WIN-PATH-01 only."""
from io import BytesIO
from uuid import uuid4

import pytest
from sqlalchemy import event

from cn_contract.ops.file_paths import filesystem_path
from tests.unit.test_contract_long_paths import long_world, assert_originals
from tests.unit.test_versions import meta


@pytest.mark.parametrize('operation', ['read','create'])
def test_reauthorization_precedes_long_path_access(long_world, monkeypatch, operation):
    p, security, _, database, actor, matter = long_world
    with database.session() as db:
        original = p.create_version(meta(matter.id), actor, db, content=BytesIO(b'previous synthetic original'))
        security.remove_membership(matter.id, actor.user_id, db)
    def forbidden(*args, **kwargs):
        pytest.fail('filesystem access before authorization')
    monkeypatch.setattr(p, 'filesystem_path', forbidden)
    class NeverRead:
        def read(self, size=-1):
            pytest.fail('stream read before authorization')
    with database.session() as db:
        with pytest.raises(security.ServiceError) as exc:
            if operation == 'read':
                p.read_original(matter.id, original.id, actor, db)
            else:
                p.create_version(meta(matter.id), actor, db, content=NeverRead())
        assert exc.value.code == 'CROSS_MATTER_DENIED'


def test_preexisting_uuid_directory_is_never_claimed_for_cleanup(long_world, monkeypatch):
    p, _, _, database, actor, matter = long_world
    identifier=uuid4()
    collision=filesystem_path(database.storage_root/str(matter.id)/str(identifier))
    collision.mkdir(parents=True)
    marker=collision/'preexisting.bin'; marker.write_bytes(b'prior independent marker')
    monkeypatch.setattr(p,'uuid4',lambda:identifier)
    with pytest.raises(FileExistsError):
        with database.session() as db:
            p.create_version(meta(matter.id), actor, db, content=BytesIO(b'not admitted'))
    assert marker.read_bytes()==b'prior independent marker'
    assert not (collision/'original.bin').exists()
    with database.session() as db:
        assert db.query(p.DocumentRow).count()==0
        assert db.get(p.MatterRow,str(matter.id)).file_count==0


def test_nested_release_then_outer_commit_failure_removes_only_new_long_files(long_world):
    p, _, _, database, actor, matter = long_world
    content=b'previously committed'
    with database.session() as db:
        original=p.create_version(meta(matter.id),actor,db,content=BytesIO(content))
        audit_count=db.query(p.AuditRow).count()
    def fail(*args):
        raise OSError('independent synthetic commit failure')
    with pytest.raises(OSError,match='independent synthetic commit failure'):
        with database.session() as db:
            p.create_version(meta(matter.id),actor,db,content=BytesIO(b'new parent'))
            with db.begin_nested():
                p.create_version(meta(matter.id),actor,db,content=BytesIO(b'new nested'))
            event.listen(db,'before_commit',fail,once=True)
    assert_originals(p,database,actor,matter,[(original,content)])
    with database.session() as db:
        assert db.query(p.AuditRow).count()==audit_count
