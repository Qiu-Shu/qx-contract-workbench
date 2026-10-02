"""Local auth and HTTP dependencies, using only synthetic credentials."""
from datetime import datetime, timedelta, timezone
import importlib

import pytest

from test_matter_access import world


def test_password_hash_argon2_and_bad_password_rejected(tmp_path):
    p, s, database, actor, _, _, _, token, _ = world(tmp_path)
    with database.session() as db:
        row = db.get(p.UserRow, str(actor.user_id))
        assert row.password_hash.startswith('$argon2id$')
        assert 'local-test-password' not in row.password_hash
        with pytest.raises(s.ServiceError) as error:
            s.login('synthetic-lawyer', 'wrong-password', db)
        assert error.value.status_code == 401
        assert db.get(p.SessionRow, str(actor.session_id)).token_hash != token


@pytest.mark.parametrize('mode', ['revoked', 'expired', 'disabled', 'wrong_user'])
def test_invalid_session_cannot_authorize(tmp_path, mode):
    p, s, database, actor, admin, own, *_ = world(tmp_path)
    with database.session() as db:
        if mode == 'revoked':
            s.revoke_session(actor.session_id, db)
        elif mode == 'expired':
            db.get(p.SessionRow, str(actor.session_id)).expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        elif mode == 'disabled':
            db.get(p.UserRow, str(actor.user_id)).disabled = True
        else:
            actor = actor.model_copy(update={'user_id': admin.user_id})
    with database.session() as db:
        with pytest.raises(s.ServiceError) as error:
            s.authorize(actor, own.id, 'read', db)
        assert error.value.status_code == 401


def test_web_cookie_csrf_and_forged_headers(tmp_path):
    p, s, database, actor, _, own, _, token, csrf = world(tmp_path)
    try:
        dependencies = importlib.import_module('cn_contract.web.dependencies')
    except ModuleNotFoundError as exc:
        if exc.name in {'cn_contract.web', 'cn_contract.web.dependencies'}:
            pytest.fail('T02 HTTP writes must use server sessions and CSRF before mutations')
        raise
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    dependencies.configure_app(app, database)
    app.add_exception_handler(s.ServiceError, dependencies.service_error_handler)
    @app.post('/api/matters/{matter_id}/synthetic-title')
    def change_title(principal=Depends(dependencies.require_matter('upload')),
                     db=Depends(dependencies.get_db)):
        db.get(p.MatterRow, str(own.id)).title = 'changed-with-csrf'
        return {'actor_id': str(principal.user_id)}
    with TestClient(app, base_url='https://testserver') as client:
        # Client identity headers never authenticate a request.
        response = client.post(f'/api/matters/{own.id}/synthetic-title',
                               headers={'X-user': str(actor.user_id), 'X-role': 'admin'})
        assert response.status_code == 401
        client.cookies.set('qx_session', token)
        for headers in ({}, {'X-CSRF-Token': 'wrong'}):
            response = client.post(f'/api/matters/{own.id}/synthetic-title', headers=headers)
            assert response.status_code == 403
            assert set(response.json()) == {'code', 'message', 'correlation_id', 'retryable'}
        with database.session() as db:
            assert db.get(p.MatterRow, str(own.id)).title == '虚构案件'
            assert db.query(p.AuditRow).filter_by(action='csrf_denied').count() == 2
        response = client.post(f'/api/matters/{own.id}/synthetic-title', headers={'X-CSRF-Token': csrf})
        assert response.status_code == 200
        assert response.json()['actor_id'] == str(actor.user_id)
    with database.session() as db:
        assert db.get(p.MatterRow, str(own.id)).title == 'changed-with-csrf'


def test_session_and_membership_revocation_refreshes_reused_session(tmp_path):
    p, s, database, actor, _, own, _, token, _ = world(tmp_path)
    with database.session_factory() as reused:
        s.authorize(actor, own.id, 'read', reused)
        # Keep references so the ORM identity map retains prior security records.
        cached_session = reused.get(p.SessionRow, str(actor.session_id))
        cached_membership = reused.get(p.MembershipRow, (str(own.id), str(actor.user_id)))
        reused.commit()
        with database.session() as db:
            s.revoke_session(actor.session_id, db)
        with pytest.raises(s.ServiceError) as error:
            s.authorize(actor, own.id, 'read', reused)
        assert error.value.status_code == 401


def test_database_role_demotion_refreshes_reused_session(tmp_path):
    p, s, database, actor, _, own, *_ = world(tmp_path)
    with database.session_factory() as reused:
        s.authorize(actor, own.id, 'confirm_facts', reused)
        cached_user = reused.get(p.UserRow, str(actor.user_id))
        reused.commit()
        with database.session() as db:
            db.get(p.UserRow, str(actor.user_id)).roles = '["assistant"]'
        with pytest.raises(s.ServiceError) as error:
            s.authorize(actor, own.id, 'confirm_facts', reused)
        assert error.value.status_code == 403
