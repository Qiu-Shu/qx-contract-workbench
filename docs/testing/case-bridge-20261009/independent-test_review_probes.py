import hashlib
import json
from uuid import UUID

import pytest

from cn_contract.persistence import UserRow, SessionRow, MembershipRow
from cn_contract.security import authenticate, remove_membership, set_membership
from tests.integration.test_assisted_review import assisted_api
from tests.integration.test_case_bridge import selected, grant


@pytest.mark.parametrize('kind', ['disabled', 'roles', 'session', 'membership'])
@pytest.mark.parametrize('rollback', [False, True])
def test_authority_restoration_never_restores_grant(selected, kind, rollback):
    client, database, ids, bridge, path, matter, _, _ = selected
    _, auth = grant(selected)
    with database.session() as db:
        actor = authenticate(client.cookies['qx_session'], db)
        if kind == 'membership':
            remove_membership(UUID(matter), ids['lawyer'], db)
            if not rollback:
                set_membership(UUID(matter), ids['lawyer'], db)
        else:
            row = db.get(SessionRow if kind == 'session' else UserRow,
                         str(actor.session_id if kind == 'session' else ids['lawyer']))
            field = {'disabled': 'disabled', 'roles': 'roles', 'session': 'revoked'}[kind]
            original = getattr(row, field)
            setattr(row, field, '["assistant"]' if kind == 'roles' else True)
            db.flush()
            if not rollback:
                setattr(row, field, original)
                db.flush()
        if rollback:
            db.rollback()
    assert bridge.active is None
    assert client.get('/api/case-bridge/context', headers=auth).status_code == 401


def test_pdf_uncertainty_remains_excluded_from_bridge(assisted_api, tmp_path):
    from tests.integration.test_pdf_visual_trust import visual_pdf, VISIBLE, SECOND
    raw = visual_pdf(VISIBLE + b'1 g\n' + SECOND)
    digest = hashlib.sha256(raw).hexdigest()
    assisted_api.setup((digest,))
    current = selected.__wrapped__(assisted_api, tmp_path)
    client, database, _, _, _, matter, _, csrf = current
    sent = client.post(f'/api/matters/{matter}/documents', headers={**csrf, 'Idempotency-Key': 'review-extra-pdf'},
        files={'file': ('synthetic-risk.pdf', raw, 'application/pdf')}, data={'baseline_view': 'original'})
    assert sent.status_code == 202, sent.text
    from cn_contract.web.app import run_next_job
    assert run_next_job(database).state == 'completed'
    facts = client.get(f'/api/matters/{matter}/facts').json()
    confirmed = client.post(f'/api/matters/{matter}/facts/confirm', headers=csrf,
        json={'fact_version': facts['version'], 'decisions': [{'fact_id': f['id'],
            'decision': 'confirmed', 'confirmed_value': f['typed_value'], 'reason': 'synthetic existing source rechecked'}
            for f in facts['facts']]})
    assert confirmed.status_code == 200, confirmed.text
    context = client.get(f'/api/matters/{matter}/review-context').json()
    current = (*current[:6], context, csrf)
    _, auth = grant(current)
    response = client.get('/api/case-bridge/context', headers=auth)
    assert response.status_code == 200, response.text
    body = response.json()
    scope = next(s for s in body['reading_scope'] if s['version_id'] == sent.json()['version_id'])
    assert scope['excluded_anchor_count'] > 0 and scope['quality_issues'] and scope['unsupported_parts']
    assert not any(a['document_version_id'] == sent.json()['version_id'] for a in body['anchors'])
    assert 'SYNTHETIC Hidden' not in response.text


def test_authority_interleaved_after_grant_commit_cannot_publish(selected, monkeypatch):
    from cn_contract.domain import CaseBridgeConsent
    from cn_contract.security import ServiceError
    client, database, ids, bridge, path, matter, context, _ = selected
    with database.session() as db:
        actor = authenticate(client.cookies['qx_session'], db)
        commit = db.commit
        def interleaved_commit():
            commit()
            with database.session() as other:
                remove_membership(UUID(matter), ids['lawyer'], other)
                set_membership(UUID(matter), ids['lawyer'], other)
        monkeypatch.setattr(db, 'commit', interleaved_commit)
        with pytest.raises(ServiceError) as caught:
            bridge.select(UUID(matter), CaseBridgeConsent(
                context_sha256=context['context_sha256'], share_with_chat=True), actor, db)
        assert caught.value.status_code == 401
        monkeypatch.setattr(db, 'commit', commit)
    assert bridge.active is None and not path.exists()


@pytest.mark.parametrize('kind', ['membership', 'roles', 'session'])
def test_bulk_authority_restore_must_not_restore_consent(selected, kind):
    from sqlalchemy import delete, insert, update
    client, database, ids, bridge, path, matter, _, _ = selected
    _, auth = grant(selected)
    with database.session() as db:
        actor = authenticate(client.cookies['qx_session'], db)
        if kind == 'membership':
            db.execute(delete(MembershipRow).where(MembershipRow.matter_id == matter,
                MembershipRow.user_id == str(ids['lawyer'])))
            db.execute(insert(MembershipRow).values(matter_id=matter,
                user_id=str(ids['lawyer']), can_sign=False))
        elif kind == 'roles':
            db.execute(update(UserRow).where(UserRow.id == str(ids['lawyer'])).values(roles='["assistant"]'))
            db.execute(update(UserRow).where(UserRow.id == str(ids['lawyer'])).values(roles='["handling_lawyer"]'))
        else:
            db.execute(update(SessionRow).where(SessionRow.id == str(actor.session_id)).values(revoked=True))
            db.execute(update(SessionRow).where(SessionRow.id == str(actor.session_id)).values(revoked=False))
    response = client.get('/api/case-bridge/context', headers=auth)
    assert response.status_code == 401, 'bulk authority restore reused consent: ' + str(response.status_code)


def test_old_read_cleanup_must_not_erase_new_grant(selected, monkeypatch):
    from datetime import datetime, timedelta, timezone
    client, _, _, bridge, path, matter, _, _ = selected
    _, old_auth = grant(selected)
    bridge.now = lambda: datetime.now(timezone.utc) + timedelta(minutes=16)
    close = bridge.close
    newer = []
    def interleaved_close(**kwargs):
        monkeypatch.setattr(bridge, 'close', close)
        newer.append(grant(selected))
        close(**kwargs)
    monkeypatch.setattr(bridge, 'close', interleaved_close)
    assert client.get('/api/case-bridge/context', headers=old_auth).status_code == 401
    assert len(newer) == 1
    response = client.get('/api/case-bridge/context', headers=newer[0][1])
    assert response.status_code == 200, 'older read cleared freshly granted consent: ' + str(response.status_code)
