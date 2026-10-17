"""Bounded history and read-only task discovery in independent native workspaces."""
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text

from cn_contract.ops import storage
from cn_contract.web import local_server
from tests.integration.test_assistant_routes import native, chat, sign_in, create, sent


def seed_history(database, identifier, count=101):
    identifiers = [str(uuid4()) for _ in range(count)]
    with database.session() as db:
        db.execute(text('''INSERT INTO assistant_messages
            (id,conversation_id,role,content,source_revision,created_at)
            VALUES (:id,:conversation,'user',:content,:revision,:at)'''),
            [{'id': value, 'conversation': identifier, 'content': f'合成原话 {index+1}',
              'revision': index+1, 'at': '2026-10-17T00:00:00+00:00'}
             for index, value in enumerate(identifiers)])
        db.execute(text('UPDATE assistant_conversations SET input_revision=:revision WHERE id=:id'),
                   {'revision': count, 'id': identifier})
    return identifiers


def test_http_pages_and_write_responses_never_load_full_history(chat, monkeypatch):
    from cn_contract.assistant import service
    client, database, _ = chat
    headers = sign_in(client)
    key = str(uuid4())
    first = create(client, headers, request_id=key)
    identifier = first['scope']['conversation_id']
    identifiers = seed_history(database, identifier)
    url = '/api/assistant/conversations/'+identifier
    page = client.get(url).json()
    assert [m['id'] for m in page['messages']] == identifiers[-50:]
    assert page['latest_run'] is None and page['next_before'] == identifiers[-50]
    def forbidden(*args, **kwargs):
        raise AssertionError('new HTTP responses must not load legacy full history')
    monkeypatch.setattr(service, 'read_conversation', forbidden)
    second = client.get(url, params={'before':page['next_before']}).json()
    third = client.get(url, params={'before':second['next_before']}).json()
    assert [m['id'] for p in (third, second, page) for m in p['messages']] == identifiers
    assert third['next_before'] is None
    repeated = create(client, headers, request_id=key)
    assert len(repeated['messages']) == 50
    result = client.put(url+'/draft', headers=headers, json={'content':'未发送的新草稿',
        'expected_scope':page['scope'], 'expected_composer_revision':page['composer_revision']})
    assert result.status_code == 200, result.text
    assert len(result.json()['messages']) == 50
    assert result.json()['draft_input'] == '未发送的新草稿'
    with database.session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_conversations')) == 1
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_messages')) == 101


def test_history_query_bounds_and_cross_conversation_cursors(chat):
    client, database, _ = chat
    headers = sign_in(client)
    first = create(client, headers); second = create(client, headers)
    own_id = first['scope']['conversation_id']
    other_ids = seed_history(database, second['scope']['conversation_id'], count=1)
    url = '/api/assistant/conversations/'+own_id
    for parameters in ({'limit':0}, {'limit':51}, {'limit':'no'}, {'before':'bad'}):
        assert client.get(url, params=parameters).status_code == 422
    assert client.get(url, params={'before':other_ids[0]}).status_code == 403
    assert client.get(url, params={'before':str(uuid4())}).status_code == 403
    empty = client.get(url, params={'limit':1}).json()
    assert empty['messages'] == [] and empty['next_before'] is None
    sign_in(client, '另一合成律师')
    assert client.get(url).status_code == 403
    client.cookies.clear()
    assert client.get(url).status_code == 401


def test_reopen_finds_original_request_without_recreating_task(native):
    original, root = native
    with TestClient(original) as client:
        headers = sign_in(client)
        first = create(client, headers)
        run, request = sent(client, headers, first)
    reopened = local_server.build_local_app(root, data_parent=root.parent.parent)
    with TestClient(reopened) as client:
        headers = sign_in(client)
        url = '/api/assistant/conversations/'+first['scope']['conversation_id']
        view = client.get(url).json()
        summary = view['latest_run']
        assert summary['id'] == run['id'] and summary['state'] == 'queued'
        assert summary['request_id'] == request['request_id']
        assert summary['request_sha256'] == run['request_sha256']
        assert summary['last_event_seq'] == 1 and 'events' not in summary
        lookup = url+'/runs/by-request/'+request['request_id']
        assert client.get(lookup).json() == summary
        assert client.get(url+'/runs/by-request/'+str(uuid4())).json() is None
        assert client.get(url+'/runs/by-request/bad').status_code == 422
        assert client.post(url+'/messages', headers=headers, json=request).json()['id'] == run['id']
        cancelled = client.post('/api/assistant/runs/'+run['id']+'/cancel', headers=headers,
                                json={'request_id':str(uuid4())})
        assert cancelled.status_code == 200
        later = client.get(lookup).json()
        assert later['state'] == 'cancelled' and later['last_event_seq'] == 2
        with reopened.state.database.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_messages')) == 1
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_runs')) == 1
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_run_events')) == 2
        sign_in(client, '另一合成律师')
        assert client.get(lookup).status_code == 403
        client.cookies.clear()
        assert client.get(lookup).status_code == 401


def test_lookup_checks_session_and_is_scoped_to_conversation(chat):
    client, database, _ = chat
    headers = sign_in(client)
    first = create(client, headers); second = create(client, headers)
    run, request = sent(client, headers, first)
    base = '/api/assistant/conversations/'
    assert client.get(base+second['scope']['conversation_id']+'/runs/by-request/'+request['request_id']).json() is None
    lookup = base+first['scope']['conversation_id']+'/runs/by-request/'+request['request_id']
    assert client.get(lookup).json()['id'] == run['id']
    with database.session() as db:
        db.execute(text('UPDATE sessions SET revoked=1'))
    assert client.get(lookup).status_code == 401


def test_recovery_only_allows_exact_history_and_task_lookup(native):
    original, root = native
    with TestClient(original) as client:
        headers = sign_in(client); first = create(client, headers)
        run, request = sent(client, headers, first)
    with original.state.database.session() as db:
        db.execute(text("UPDATE assistant_runs SET state='blocked'"))
        db.add(storage.RestoreFenceRow(ref=str(uuid4()), archive_sha256='c'*64,
                                      manifest_sha256='d'*64, payload='{}'))
    recovered = local_server.build_local_app(root, data_parent=root.parent.parent)
    with TestClient(recovered) as client:
        headers = sign_in(client)
        base = '/api/assistant/conversations/'+first['scope']['conversation_id']
        lookup = base+'/runs/by-request/'+request['request_id']
        assert client.get(base, params={'limit':1}).json()['latest_run']['state'] == 'blocked'
        assert client.get(lookup).json()['state'] == 'blocked'
        for path in (lookup+'/unsafe', base+'/runs', base+'/runs/by-request/'+request['request_id']+'x'):
            assert client.get(path).status_code == 409
        assert client.post(lookup, headers=headers, json={}).status_code == 409
        assert client.put(base+'/draft', headers=headers, json={}).status_code == 409
        assert client.post(base+'/messages', headers=headers, json=request).status_code == 409
