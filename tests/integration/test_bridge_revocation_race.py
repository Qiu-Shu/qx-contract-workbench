"""Revocation must cancel unpublished consent without affecting other owners."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event, current_thread
from uuid import UUID

import pytest

from cn_contract.domain import CaseBridgeConsent
from cn_contract.security import ServiceError, authenticate
from tests.integration.test_assisted_review import assisted_api
from tests.integration.test_case_bridge import selected, grant
from tests.integration.test_api import create_case


@pytest.mark.parametrize('allow_submission', [False, True])
@pytest.mark.parametrize('action', ['revoke', 'other_matter', 'revoke_then_reselect'])
def test_pending_consent_cancellation(selected, monkeypatch, allow_submission, action):
    client, database, _, bridge, path, matter, context, csrf = selected
    other = create_case(client, csrf, title='独立虚构另一案件')
    committed, publish = Event(), Event()
    original_commit = database.session_factory.class_.commit
    token = client.cookies['qx_session']

    def delayed_commit(db):
        result = original_commit(db)
        if current_thread().name.startswith('pending_selector') and not committed.is_set():
            committed.set()
            assert publish.wait(10)
        return result

    monkeypatch.setattr(database.session_factory.class_, 'commit', delayed_commit)

    def select_once():
        with database.session() as db:
            return bridge.select(UUID(matter), CaseBridgeConsent(
                context_sha256=context['context_sha256'], share_with_chat=True,
                allow_candidate_submission=allow_submission), authenticate(token, db), db)

    with ThreadPoolExecutor(max_workers=1, thread_name_prefix='pending_selector') as pool:
        pending = pool.submit(select_once)
        assert committed.wait(10)
        try:
            target = other if action == 'other_matter' else matter
            response = client.delete(f'/api/matters/{target}/case-bridge', headers=csrf)
            assert response.status_code in (204, 409)
            if action != 'other_matter':
                assert response.status_code == 204
            if action == 'revoke_then_reselect':
                newer, auth = grant(selected)
        finally:
            publish.set()
        if action == 'other_matter':
            assert pending.result(timeout=10).matter_id == UUID(matter)
        else:
            with pytest.raises(ServiceError) as caught:
                pending.result(timeout=10)
            assert caught.value.status_code == 401
    if action == 'revoke':
        assert bridge.active is None and not path.exists()
    elif action == 'revoke_then_reselect':
        response = client.get('/api/case-bridge/context', headers=auth)
        assert response.status_code == 200
        assert response.json()['grant'] == newer


def test_expired_old_read_does_not_cancel_unpublished_new_selection(selected,monkeypatch):
    from datetime import timedelta
    client,database,_,bridge,path,matter,context,csrf=selected
    _,old_auth=grant(selected)
    future=bridge.active[0].expires_at+timedelta(seconds=1)
    bridge.now=lambda:future
    committed,publish=Event(),Event()
    original=database.session_factory.class_.commit
    token=client.cookies['qx_session']
    def delayed(db):
        result=original(db)
        if current_thread().name.startswith('new_pending') and not committed.is_set():
            committed.set();assert publish.wait(10)
        return result
    monkeypatch.setattr(database.session_factory.class_,'commit',delayed)
    def select_new():
        with database.session() as db:
            return bridge.select(UUID(matter),CaseBridgeConsent(context_sha256=context['context_sha256'],
                share_with_chat=True),authenticate(token,db),db)
    with ThreadPoolExecutor(max_workers=1,thread_name_prefix='new_pending') as pool:
        selection=pool.submit(select_new)
        assert committed.wait(10)
        try:
            assert client.get('/api/case-bridge/context',headers=old_auth).status_code==401
        finally:publish.set()
        new_grant=selection.result(timeout=10)
    import json
    auth={'Authorization':'Bearer '+json.loads(path.read_text('utf-8'))['token']}
    assert client.get('/api/case-bridge/context',headers=auth).json()['grant']['id']==str(new_grant.id)
