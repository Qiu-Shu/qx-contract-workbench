"""Selected fictional case access uses real auth, versions and original checks."""
import importlib
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from cn_contract.persistence import MembershipRow, SessionRow, UserRow, AuditRow
from cn_contract.security import remove_membership, set_membership
from tests.integration.test_assisted_review import assisted_api, ready_case
from tests.integration.test_api import sign_in, create_case


@pytest.fixture
def selected(assisted_api, tmp_path):
    client, database, ids, _ = assisted_api
    assert importlib.util.find_spec('cn_contract.web.case_bridge'), 'case bridge is not implemented'
    module = importlib.import_module('cn_contract.web.case_bridge')
    path = tmp_path / 'selected-case.json'
    bridge = module.attach_case_bridge(client.app, database, path)
    matter, sent, parsed, facts, context, headers = ready_case(assisted_api)
    return client, database, ids, bridge, path, matter, context, headers


def grant(selected):
    client, _, _, _, path, matter, context, headers = selected
    response = client.post(f'/api/matters/{matter}/case-bridge', headers=headers,
        json={'context_sha256': context['context_sha256'], 'share_with_chat': True})
    assert response.status_code == 201, response.text
    secret = json.loads(path.read_text('utf-8'))
    assert set(secret) == {'token', 'grant_id'}
    assert secret['token'] not in response.text
    return response.json(), {'Authorization': 'Bearer ' + secret['token']}


def test_selected_read_contains_bound_sources_and_no_credentials(selected):
    client, db, _, _, path, matter, context, _ = selected
    saved, headers = grant(selected)
    response = client.get('/api/case-bridge/context', headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['grant'] == saved and body['context'] == context
    assert {a['id'] for a in body['anchors']} == set(context['eligible_anchor_ids'])
    assert body['facts'] and all(f['confirmation_status'] in ('confirmed', 'corrected') for f in body['facts'])
    assert body['read_only'] is True and body['synthetic'] is True
    for private in ('password_hash', 'storage_key', 'qx_session', str(path), headers['Authorization']):
        assert private not in response.text
    with db.session() as session:
        actions = [r.action for r in session.scalars(select(AuditRow).where(AuditRow.matter_id == matter))]
    assert 'case_bridge_granted' in actions and 'case_bridge_read' in actions


@pytest.mark.parametrize('change', ['logout', 'membership', 'membership_restore', 'disabled', 'role', 'expired', 'version', 'revoke', 'restart'])
def test_grant_cannot_survive_authority_or_context_change(selected, change):
    client, database, ids, bridge, path, matter, _, csrf = selected
    _, auth = grant(selected)
    if change == 'logout':
        assert client.post('/api/logout', headers=csrf).status_code == 200
    elif change in ('membership', 'membership_restore'):
        with database.session() as db:
            remove_membership(UUID(matter), ids['lawyer'], db)
        if change.endswith('restore'):
            with database.session() as db:
                set_membership(UUID(matter), ids['lawyer'], db)
    elif change in ('disabled', 'role'):
        with database.session() as db:
            row = db.get(UserRow, str(ids['lawyer']))
            if change == 'disabled': row.disabled = True
            else: row.roles = '["assistant"]'
    elif change == 'expired':
        bridge.now = lambda: datetime.now(timezone.utc) + timedelta(minutes=16)
    elif change == 'version':
        from cn_contract.persistence import set_position
        from cn_contract.security import authenticate
        from cn_contract.domain import Position
        with database.session() as db:
            set_position(UUID(matter), Position.SELLER, authenticate(client.cookies['qx_session'], db), db)
    elif change == 'revoke':
        assert client.delete(f'/api/matters/{matter}/case-bridge', headers=csrf).status_code == 204
    else:
        bridge.close()
    response = client.get('/api/case-bridge/context', headers=auth)
    assert response.status_code in (401, 403, 409), response.text
    assert 'anchors' not in response.json()


@pytest.mark.parametrize('bad', ['no_csrf', 'origin', 'consent', 'context', 'unknown', 'assistant'])
def test_selection_requires_explicit_current_authority(selected, bad):
    client, _, _, _, path, matter, context, headers = selected
    body = {'context_sha256': context['context_sha256'], 'share_with_chat': True}
    if bad == 'no_csrf': headers = {}
    if bad == 'origin': headers = {**headers, 'Origin': 'https://untrusted.invalid'}
    if bad == 'consent': body['share_with_chat'] = False
    if bad == 'context': body['context_sha256'] = '0' * 64
    if bad == 'unknown': body['url'] = 'https://untrusted.invalid'
    if bad == 'assistant': headers = sign_in(client, 'assistant')
    response = client.post(f'/api/matters/{matter}/case-bridge', headers=headers, json=body)
    assert response.status_code in (403, 409, 422), response.text
    assert not path.exists()


def test_no_cookie_fallback_or_case_override(selected):
    client, _, _, _, _, matter, _, csrf = selected
    other = create_case(client, csrf, title='另案不应被撤销入口选中')
    saved, auth = grant(selected)
    assert client.get('/api/case-bridge/context').status_code == 401
    assert client.get('/api/case-bridge/context', headers={'Authorization': 'Bearer wrong'}).status_code == 401
    assert client.get('/api/case-bridge/context?matter_id=' + str(uuid4()), headers=auth).status_code == 422
    assert client.delete(f'/api/matters/{other}/case-bridge', headers=csrf).status_code == 409
    assert client.get('/api/case-bridge/context', headers=auth).json()['grant'] == saved


def test_reselect_replaces_token_and_template_has_explicit_consent(selected):
    client, _, _, _, _, matter, _, _ = selected
    _, old = grant(selected)
    _, current = grant(selected)
    assert client.get('/api/case-bridge/context', headers=old).status_code == 401
    assert client.get('/api/case-bridge/context', headers=current).status_code == 200
    page = client.get(f'/matters/{matter}/review')
    assert 'case-bridge-form' in page.text and '进入调用插件的聊天' in page.text


def test_actual_loopback_mcp_read_and_revocation(selected, monkeypatch):
    """Real TCP to the fixed port, real MCP dispatch; no remote model turn."""
    import socket
    import time
    from threading import Thread
    import anyio
    import uvicorn
    from cn_contract.mcp import case_client, offline_server
    from mcp.server.mcpserver.exceptions import UnexpectedToolError
    client, _, _, _, path, matter, _, csrf = selected
    _, _ = grant(selected)
    monkeypatch.setattr(case_client, 'CREDENTIAL_PATH', path)
    sock = socket.socket()
    # Never disturb a user's running server. An occupied port is a test failure.
    sock.bind(('127.0.0.1', 8767))
    config = uvicorn.Config(client.app, host='127.0.0.1', port=8767,
                            lifespan='off', access_log=False, log_level='error')
    server = uvicorn.Server(config)
    thread = Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline: time.sleep(.02)
        assert server.started
        async def invoke():
            return await offline_server.create_server().call_tool('read_selected_case', {})
        result = anyio.run(invoke)
        body = result.model_dump(mode='json', by_alias=True)
        assert body['isError'] is False
        assert body['structuredContent']['grant']['matter_id'] == matter
        assert body['structuredContent']['anchors']
        from tests.helpers.offline_mcp_child import child, initialize
        code = ('from pathlib import Path; from cn_contract.mcp import case_client, offline_server; '
                f'case_client.CREDENTIAL_PATH = Path({str(path)!r}); offline_server.main()')
        with child(launch_code=code) as (process, send, stderr):
            initialize(send)
            reply = send('tools/call', {'name': 'read_selected_case', 'arguments': {}}, request_id=2)
            assert reply['result']['structuredContent']['grant']['matter_id'] == matter
            refused = send('tools/call', {'name': 'read_selected_case', 'arguments': {'matter_id': matter}}, request_id=3)
            assert refused['error']['message'] == 'OFFLINE_REQUEST_REJECTED'
            assert client.delete(f'/api/matters/{matter}/case-bridge', headers=csrf).status_code == 204
            refused = send('tools/call', {'name': 'read_selected_case', 'arguments': {}}, request_id=4)
            assert refused['error']['message'] == 'OFFLINE_REQUEST_REJECTED'
        assert process.returncode == 0 and stderr == []
        with pytest.raises(UnexpectedToolError): anyio.run(invoke)
    finally:
        server.should_exit = True
        thread.join(10)
        sock.close()
        assert not thread.is_alive()


def test_oversize_rejected_without_truncation(selected, monkeypatch):
    client, _, _, bridge, _, _, _, _ = selected
    _, auth = grant(selected)
    module = importlib.import_module('cn_contract.web.case_bridge')
    monkeypatch.setattr(module, 'MAX_RESPONSE_BYTES', 10)
    response = client.get('/api/case-bridge/context', headers=auth)
    assert response.status_code == 413
    assert 'anchors' not in response.text and bridge.active is None


def test_original_tampering_invalidates_read(selected):
    from cn_contract.persistence import DocumentRow
    client, database, _, bridge, _, matter, _, _ = selected
    _, auth = grant(selected)
    with database.session() as db:
        row = db.scalar(select(DocumentRow).where(DocumentRow.matter_id == matter))
        original = database.storage_root / json.loads(row.payload)['storage_ref']
    original.chmod(0o600)  # Explicitly corrupt only this disposable test original.
    original.write_bytes(b'fictional altered original')
    response = client.get('/api/case-bridge/context', headers=auth)
    assert response.status_code == 409 and bridge.active is None


def test_pdf_transcription_is_separate_from_eligible_text(assisted_api, tmp_path):
    from cn_contract.web.case_bridge import attach_case_bridge
    from tests.integration.test_pdf_proofreading import setup, submit
    client, database, _, headers, matter, _, value = setup(assisted_api)
    value['observed_text'] = '独立虚构人工转录；SYNTHETIC no automatic acceptance；非PDF文字层'
    record = submit(client, headers, matter, value).json()
    facts = client.get(f'/api/matters/{matter}/facts').json()
    confirmed = client.post(f'/api/matters/{matter}/facts/confirm', headers=headers,
        json={'fact_version': facts['version'], 'decisions': [{'fact_id': f['id'],
            'decision': 'confirmed', 'confirmed_value': f['typed_value'], 'reason': '独立虚构PDF人工核对'} for f in facts['facts']]})
    assert confirmed.status_code == 200, confirmed.text
    path = tmp_path / 'pdf-selected.json'
    attach_case_bridge(client.app, database, path)
    context = client.get(f'/api/matters/{matter}/review-context').json()
    response = client.post(f'/api/matters/{matter}/case-bridge', headers=headers,
        json={'context_sha256': context['context_sha256'], 'share_with_chat': True})
    assert response.status_code == 201, response.text
    token = json.loads(path.read_text('utf-8'))['token']
    body = client.get('/api/case-bridge/context', headers={'Authorization': 'Bearer ' + token}).json()
    assert body['source_verifications'] == [record]
    assert body['facts'][0]['provenance_type'] == 'source_verification'
    assert body['facts'][0]['anchor_ids'] == []
    assert all(a['quote'] != value['observed_text'] for a in body['anchors'])
    assert body['reading_scope'] and all('quality_issues' in s and 'unsupported_parts' in s for s in body['reading_scope'])


@pytest.mark.parametrize('kind', ['membership', 'roles', 'session'])
def test_bulk_authority_restore_must_not_restore_consent(selected, kind):
    from sqlalchemy import delete, insert, update
    client, database, ids, bridge, path, matter, _, _ = selected
    _, auth = grant(selected)
    with database.session() as db:
        from cn_contract.security import authenticate
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
