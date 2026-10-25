"""Existing HTTP replacement contract for independently synthetic pending files."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from uuid import uuid4

from docx import Document
import pytest
from sqlalchemy import text

from cn_contract.ops.storage import RestoreFenceRow
from test_api import create_case
from test_assistant_routes import chat, native, create, sign_in
from tests.helpers.synthetic_documents import pdf


DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
TABLES = ('task_channel_bindings', 'task_inbox_events', 'task_drafts', 'task_draft_events',
          'task_media_resolutions', 'task_executions', 'assistant_attachments',
          'assistant_attachment_parses', 'assistant_material_snapshots')


def pending(client, headers, *, matter_id=None):
    fields = {'scope_kind': 'matter', 'scope_ref': matter_id} if matter_id else {}
    view = create(client, headers, **fields)
    base = '/api/assistant/conversations/' + view['scope']['conversation_id']
    binding = client.post(base + '/task-bindings', headers=headers)
    assert binding.status_code == 200, binding.text
    original = {'media_id': 'synthetic-pending-file', 'name': '待人工核对的收件.docx',
                'mime': DOCX, 'status': 'pending'}
    response = client.post('/api/task-bindings/' + binding.json()['id'] + '/batches', headers=headers,
        json={'expected_cursor': 0, 'next_cursor': 1, 'events': [{
            'event_id': 'synthetic-pending-source', 'text': '核对本机独立虚构合同，事实待确认。',
            'media': [original]}]})
    assert response.status_code == 200, response.text
    draft = response.json()['drafts'][0]
    assert draft['events'][0]['media'][0]['attachment_id'] is None
    assert 'media_pending' in draft['blockers']
    return base, draft


def save_and_parse(client, database, headers, base, *, kind='docx', partial=False):
    if kind == 'docx':
        document = Document()
        document.add_paragraph('独立虚构材料：本机合成买方支付测试货款，未确认事实。')
        stream = BytesIO(); document.save(stream); raw = stream.getvalue()
        name, mime = '另行上传的独立虚构原件.docx', DOCX
    else:
        raw = pdf(['SYNTHETIC independent buyer owes CNY 13750', None] if partial else
                  ['SYNTHETIC independent buyer owes CNY 13750'])
        name, mime = '另行上传的独立虚构原件.pdf', 'application/pdf'
    database._assistant_synthetic_hashes = set(getattr(database, '_assistant_synthetic_hashes', ())) | {sha256(raw).hexdigest()}
    metadata = {'request_id': str(uuid4()), 'expected_scope': client.get(base + '/materials').json()['scope'],
                'original_name': name, 'mime': mime, 'policy': {'policy_id': 'assistant-local-files-v2',
                    'material_mode': 'synthetic', 'local_processing_accepted': True, 'external_processing': False}}
    uploaded = client.post(base + '/attachments', headers=headers,
        files=[('file', (name, raw, mime)), ('metadata', (None, json.dumps(metadata, ensure_ascii=False), 'application/json'))])
    assert uploaded.status_code == 201, uploaded.text
    file = uploaded.json()['attachment']
    parsed = client.post(base + '/attachments/' + file['id'] + '/parses', headers=headers,
        json={'request_id': str(uuid4()), 'expected_scope': client.get(base + '/materials').json()['scope']})
    assert parsed.status_code == 200, parsed.text
    assert parsed.json()['parse']['reading_status'] == ('partial' if partial else 'readable')
    replacement = {'media_id': 'synthetic-pending-file', 'name': file['original_name'], 'mime': file['mime'],
                   'status': 'ready', 'attachment_id': file['id'], 'sha256': file['sha256'],
                   'parse_revision': parsed.json()['parse']['revision']}
    return replacement, raw


def body(draft, replacement):
    return {'expected_revision': draft['revision'], 'media_resolutions': [{
        'event_id': draft['events'][0]['id'], 'media_id': 'synthetic-pending-file',
        'action': 'resolve', 'replacement': deepcopy(replacement)}]}


def snapshot(database):
    with database.session() as db:
        rows = {name: tuple(tuple(row) for row in db.execute(text('SELECT * FROM ' + name + ' ORDER BY rowid')))
                for name in TABLES}
    originals = {path.relative_to(database.storage_root).as_posix(): path.read_bytes()
                 for path in database.storage_root.rglob('original.bin')}
    return rows, originals


def assert_no_execution(database):
    with database.session() as db:
        for name in ('task_executions', 'assistant_runs', 'review_runs', 'weixin_accounts'):
            assert db.scalar(text('SELECT COUNT(*) FROM ' + name)) == 0


@pytest.mark.parametrize('kind', ['docx', 'pdf'])
def test_pending_without_attachment_resolves_to_explicit_same_cid_original_over_http(chat, kind):
    client, database, _ = chat; headers = sign_in(client)
    base, draft = pending(client, headers)
    replacement, raw = save_and_parse(client, database, headers, base, kind=kind)
    before = snapshot(database)
    response = client.patch('/api/task-drafts/' + draft['id'], headers=headers, json=body(draft, replacement))
    assert response.status_code == 200, response.text
    changed = response.json()
    assert changed['revision'] == draft['revision'] + 1 and changed['state'] == 'collecting'
    assert changed['events'] == draft['events'] and not changed['blockers']
    assert changed['main_attachment_id'] == replacement['attachment_id']
    resolution = changed['media_resolutions'][0]
    assert resolution['event_id'] == draft['events'][0]['id'] and resolution['replacement'] == replacement
    assert resolution['revision'] == changed['revision'] and resolution['action'] == 'resolve'
    assert client.get('/api/task-drafts/' + draft['id']).json() == changed
    after = snapshot(database)
    for name in TABLES:
        if name not in ('task_drafts', 'task_media_resolutions'):
            assert after[0][name] == before[0][name]
    assert after[1] == before[1]
    assert client.get(base + '/attachments/' + replacement['attachment_id'] + '/original').content == raw
    assert_no_execution(database)


@pytest.mark.parametrize('damage', ['event', 'media', 'hash', 'name', 'mime', 'parse', 'foreign_cid'])
def test_http_resolution_rejects_forged_or_foreign_references_atomically(chat, damage):
    client, database, _ = chat; headers = sign_in(client)
    base, draft = pending(client, headers)
    replacement, _ = save_and_parse(client, database, headers, base)
    request = body(draft, replacement); item = request['media_resolutions'][0]
    if damage == 'event': item['event_id'] = str(uuid4())
    elif damage == 'media': item['media_id'] = item['replacement']['media_id'] = 'absent-media'
    elif damage == 'hash': item['replacement']['sha256'] = '0' * 64
    elif damage == 'name': item['replacement']['name'] = '伪造文件名.docx'
    elif damage == 'mime': item['replacement']['mime'] = 'application/pdf'
    elif damage == 'parse': item['replacement']['parse_revision'] += 1
    else:
        foreign_base, _ = pending(client, headers)
        item['replacement'], _ = save_and_parse(client, database, headers, foreign_base)
    before = snapshot(database)
    response = client.patch('/api/task-drafts/' + draft['id'], headers=headers, json=request)
    assert response.status_code == (403 if damage == 'foreign_cid' else 409), response.text
    assert response.json()['code'] == ('CROSS_MATTER_DENIED' if damage == 'foreign_cid' else 'VERSION_CONFLICT')
    assert snapshot(database) == before
    saved = client.get('/api/task-drafts/' + draft['id']).json()
    assert saved['events'] == draft['events'] and saved['revision'] == draft['revision']
    assert saved['media_resolutions'] == []
    assert_no_execution(database)


def test_http_late_bad_resolution_rolls_back_an_earlier_valid_resolution(chat):
    client, database, _ = chat; headers = sign_in(client)
    base, draft = pending(client, headers)
    replacement, _ = save_and_parse(client, database, headers, base)
    request = body(draft, replacement)
    bad = deepcopy(request['media_resolutions'][0])
    bad['media_id'] = bad['replacement']['media_id'] = 'absent-after-valid'
    request['media_resolutions'].append(bad)
    before = snapshot(database)
    response = client.patch('/api/task-drafts/' + draft['id'], headers=headers, json=request)
    assert response.status_code == 409 and response.json()['code'] == 'VERSION_CONFLICT'
    assert snapshot(database) == before


@pytest.mark.parametrize('state', ['stale', 'frozen', 'paused', 'cancelled'])
def test_http_resolution_honors_revision_and_task_state(chat, state):
    client, database, _ = chat; headers = sign_in(client)
    base, draft = pending(client, headers)
    replacement, _ = save_and_parse(client, database, headers, base)
    path = '/api/task-drafts/' + draft['id']; request = body(draft, replacement)
    if state in ('stale', 'frozen'):
        changed = client.patch(path, headers=headers, json=request)
        assert changed.status_code == 200, changed.text
        if state == 'frozen':
            saved = changed.json()
            response = client.post(path + '/freeze', headers=headers,
                json={'expected_revision': saved['revision'], 'manifest_sha256': saved['manifest_sha256']})
            assert response.status_code == 200, response.text
            request['expected_revision'] = saved['revision']
    else:
        changed = client.patch(path, headers=headers,
            json={'expected_revision': draft['revision'], 'action': 'pause' if state == 'paused' else 'cancel'})
        assert changed.status_code == 200, changed.text
        request['expected_revision'] = changed.json()['revision']
    before = snapshot(database)
    response = client.patch(path, headers=headers, json=request)
    assert response.status_code == 409, response.text
    assert response.json()['code'] == ('STATE_CONFLICT' if state in ('paused', 'cancelled') else 'VERSION_CONFLICT')
    assert snapshot(database) == before


@pytest.mark.parametrize('guard', ['csrf', 'origin', 'owner', 'session'])
def test_http_resolution_authenticates_before_consuming_json(chat, monkeypatch, guard):
    from cn_contract.web import task_drafts
    client, database, _ = chat; headers = sign_in(client)
    base, draft = pending(client, headers)
    save_and_parse(client, database, headers, base)
    if guard == 'csrf': headers = {}
    elif guard == 'origin': headers = {**headers, 'Origin': 'https://independent.invalid'}
    elif guard == 'owner': headers = sign_in(client, '另一合成律师')
    else: client.cookies.clear()
    async def unread(*args):
        raise AssertionError('unauthorized replacement body must not be consumed')
    monkeypatch.setattr(task_drafts, 'body_input', unread)
    before = snapshot(database)
    response = client.patch('/api/task-drafts/' + draft['id'], headers=headers, content='not-json')
    assert response.status_code == (401 if guard == 'session' else 403), response.text
    assert snapshot(database) == before


@pytest.mark.parametrize('after_body', [False, True])
def test_http_resolution_rechecks_current_matter_acl(chat, monkeypatch, after_body):
    from cn_contract.web import task_drafts
    client, database, _ = chat; headers = sign_in(client)
    matter_id = create_case(client, headers)
    base, draft = pending(client, headers, matter_id=matter_id)
    replacement, _ = save_and_parse(client, database, headers, base)
    def revoke():
        with database.session() as db:
            db.execute(text('DELETE FROM matter_memberships WHERE matter_id=:id'), {'id': matter_id})
    if after_body:
        read = task_drafts.body_input
        async def revoke_after_read(*args):
            value = await read(*args); revoke(); return value
        monkeypatch.setattr(task_drafts, 'body_input', revoke_after_read)
    else:
        revoke()
        async def unread(*args):
            raise AssertionError('current ACL must be checked before consuming replacement')
        monkeypatch.setattr(task_drafts, 'body_input', unread)
    before = snapshot(database)
    response = client.patch('/api/task-drafts/' + draft['id'], headers=headers, json=body(draft, replacement))
    assert response.status_code == 403 and response.json()['code'] == 'CROSS_MATTER_DENIED'
    assert snapshot(database) == before
    assert_no_execution(database)


def test_recovery_fence_blocks_http_resolution_and_keeps_saved_pending_history(chat):
    client, database, _ = chat; headers = sign_in(client)
    base, draft = pending(client, headers)
    replacement, raw = save_and_parse(client, database, headers, base)
    with database.session() as db:
        db.add(RestoreFenceRow(ref=str(uuid4()), archive_sha256='a' * 64, manifest_sha256='b' * 64, payload='{}'))
    before = snapshot(database)
    response = client.patch('/api/task-drafts/' + draft['id'], headers=headers, json=body(draft, replacement))
    assert response.status_code == 409 and response.json()['code'] == 'BLOCKED_LIVE'
    assert snapshot(database) == before
    saved = client.get('/api/task-drafts/' + draft['id']).json()
    assert saved['events'] == draft['events'] and saved['revision'] == draft['revision']
    assert saved['media_resolutions'] == [] and raw in before[1].values()
    assert_no_execution(database)


def test_http_ready_reference_to_partial_pdf_keeps_blocker_and_cannot_freeze(chat):
    client, database, _ = chat; headers = sign_in(client)
    base, draft = pending(client, headers)
    replacement, raw = save_and_parse(client, database, headers, base, kind='pdf', partial=True)
    path = '/api/task-drafts/' + draft['id']
    response = client.patch(path, headers=headers, json=body(draft, replacement))
    assert response.status_code == 200, response.text
    changed = response.json()
    assert 'media_not_readable' in changed['blockers'] and changed['events'] == draft['events']
    before = snapshot(database)
    frozen = client.post(path + '/freeze', headers=headers,
        json={'expected_revision': changed['revision'], 'manifest_sha256': changed['manifest_sha256']})
    assert frozen.status_code == 409 and frozen.json()['code'] == 'STATE_CONFLICT'
    assert snapshot(database) == before
    assert client.get(base + '/attachments/' + replacement['attachment_id'] + '/original').content == raw
    assert_no_execution(database)
