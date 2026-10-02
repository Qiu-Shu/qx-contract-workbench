"""Synthetic SQLite integration cases: membership precedes content access."""
import importlib
from io import BytesIO
from uuid import uuid4

import pytest

from cn_contract.config import load_settings
from cn_contract.domain import Actor, Matter, Role, VersionInput


def api():
    try:
        return (importlib.import_module('cn_contract.persistence'),
                importlib.import_module('cn_contract.security'))
    except ModuleNotFoundError as exc:
        if exc.name in {'cn_contract.persistence', 'cn_contract.security'}:
            pytest.fail('T02 must enforce persistent matter membership before accessing documents')
        raise


def matter(member_ids=()):
    return Matter(id=uuid4(), client_ref='SYNTHETIC', title='虚构案件',
                  jurisdiction='CN-mainland', contract_type='sales', review_mode='pre_sign',
                  position='buyer', objectives=(), member_ids=frozenset(member_ids),
                  status='intake', active_fact_version=None, active_policy_version=None, gate_issues=())


def world(tmp_path):
    p, s = api()
    database = p.Database(f'sqlite:///{tmp_path / "test.db"}', tmp_path / 'originals', load_settings())
    with database.session() as db:
        user_id = s.provision_user('synthetic-lawyer', 'local-test-password', {Role.HANDLING_LAWYER}, db)
        admin_id = s.provision_user('synthetic-admin', 'local-test-password', {Role.ADMIN}, db)
        token, csrf = s.login('synthetic-lawyer', 'local-test-password', db)
        admin_token, _ = s.login('synthetic-admin', 'local-test-password', db)
        actor = s.authenticate(token, db)
        admin = s.authenticate(admin_token, db)
        own = matter([user_id])
        other = matter([admin_id])
        p.provision_matter(own, db)
        p.provision_matter(other, db)
    return p, s, database, actor, admin, own, other, token, csrf


def meta(matter_id):
    return VersionInput(matter_id=matter_id, original_name='虚构.pdf', mime='application/pdf',
                        baseline_view='original', supersedes_id=None)


def test_cross_matter_same_hash(tmp_path):
    p, s, database, actor, admin, own, other, _, _ = world(tmp_path)
    with database.session() as db:
        first = p.create_version(meta(own.id), actor, db, content=BytesIO(b'%PDF-SYNTHETIC'))
        # Provision a member lawyer in the second matter; administrator alone cannot upload.
        s.set_membership(other.id, actor.user_id, db)
        second = p.create_version(meta(other.id), actor, db, content=BytesIO(b'%PDF-SYNTHETIC'))
        s.remove_membership(other.id, actor.user_id, db)
    assert first.sha256 == second.sha256
    assert first.storage_ref != second.storage_ref
    with database.session() as db:
        with pytest.raises(s.ServiceError) as error:
            p.read_version(other.id, second.id, actor, db)
        assert error.value.status_code == 403
        assert error.value.code == 'CROSS_MATTER_DENIED'


def test_admin_not_member(tmp_path):
    p, s, database, actor, admin, own, *_ = world(tmp_path)
    with database.session() as db:
        with pytest.raises(s.ServiceError) as error:
            s.authorize(admin, own.id, 'read', db)
        assert error.value.status_code == 403


def test_forged_roles_do_not_grant_fact_confirmation(tmp_path):
    p, s, database, actor, _, own, *_ = world(tmp_path)
    with database.session() as db:
        assistant_id = s.provision_user('synthetic-assistant', 'local-test-password', {Role.ASSISTANT}, db)
        s.set_membership(own.id, assistant_id, db)
        token, _ = s.login('synthetic-assistant', 'local-test-password', db)
        assistant = s.authenticate(token, db)
        forged = Actor(user_id=assistant.user_id, session_id=assistant.session_id,
                       roles={Role.HANDLING_LAWYER, Role.REVIEWING_LAWYER})
    with database.session() as db:
        with pytest.raises(s.ServiceError):
            s.authorize(forged, own.id, 'confirm_facts', db)
        s.authorize(assistant, own.id, 'upload', db)


def test_unknown_action_denied(tmp_path):
    _, s, database, actor, _, own, *_ = world(tmp_path)
    with database.session() as db:
        with pytest.raises(s.ServiceError):
            s.authorize(actor, own.id, 'invented_action', db)


def test_unknown_and_nonmember_matter_same_error(tmp_path):
    _, s, database, actor, _, _, other, *_ = world(tmp_path)
    errors = []
    with database.session() as db:
        for identifier in (other.id, uuid4()):
            with pytest.raises(s.ServiceError) as caught:
                s.authorize(actor, identifier, 'read', db)
            errors.append((caught.value.status_code, caught.value.code, str(caught.value)))
    assert errors[0] == errors[1]


def test_denial_rolls_back_pending_business_and_keeps_audit(tmp_path):
    p, s, database, actor, _, own, other, *_ = world(tmp_path)
    with database.session() as db:
        db.get(p.MatterRow, str(own.id)).title = 'must-not-commit'
        with pytest.raises(s.ServiceError):
            s.authorize(actor, other.id, 'read', db)
        db.rollback()  # Simulate the outer web request error transaction.
    with database.session() as db:
        assert p.read_matter(own.id, actor, db).title == '虚构案件'
        events = list(db.query(p.AuditRow).all())
        assert any(row.action == 'authorization_denied' for row in events)


def test_membership_precedes_content_stream(tmp_path):
    p, s, database, actor, _, _, other, *_ = world(tmp_path)
    class NeverRead:
        def read(self, size=-1):
            pytest.fail('unauthorized stream must never be read or hashed')
    with database.session() as db:
        with pytest.raises(s.ServiceError):
            p.create_version(meta(other.id), actor, db, content=NeverRead())


def test_confirm_baseline_requires_real_lawyer_member(tmp_path):
    p, s, database, actor, _, own, *_ = world(tmp_path)
    with database.session() as db:
        # A legitimate lawyer member must be able to choose the review baseline.
        s.authorize(actor, own.id, 'confirm_baseline', db)


def test_cross_matter_version_target_rejection_keeps_audit(tmp_path):
    p, s, database, actor, _, own, other, *_ = world(tmp_path)
    with database.session() as db:
        s.set_membership(other.id, actor.user_id, db)
        hidden = p.create_version(meta(other.id), actor, db, content=BytesIO(b'synthetic-other'))
        s.remove_membership(other.id, actor.user_id, db)
    with database.session() as db:
        for target in (hidden.id, uuid4()):
            with pytest.raises(s.ServiceError) as error:
                p.read_version(own.id, target, actor, db)
            assert error.value.status_code == 403
        assert db.query(p.AuditRow).filter_by(action='authorization_denied').count() == 2
