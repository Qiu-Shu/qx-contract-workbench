"""Saved audience projections over synthetic workspaces; no model/network calls."""
from io import BytesIO
from uuid import uuid4
from zipfile import ZipFile

from docx import Document
import pytest
from sqlalchemy import text

from test_assistant_routes import native, chat, create, sign_in
from test_assistant_profile_routes import command, commit

PRIVATE = '内部哨兵：最低和解底线777元，不得发客户'
PUBLIC = '您好，请补充付款凭证，我们核对后回复。'


def seed(client, headers):
    url, value = command(client, headers, project_intake=False)
    value['manual_edits'] = [
        {'field':'client_reply','value':{'kind':'text','value':PUBLIC}},
        {'field':'internal_notes','value':{'kind':'text','value':PRIVATE}},
        {'field':'title','value':{'kind':'text','value':PRIVATE}},
    ]
    commit(client, headers, url, value)
    return url.removesuffix('/profile')+'/outputs'


def selection(audience='client', revision=1):
    return {'source':{'kind':'profile','profile_revision':revision},'audience':audience}


def preview(client, headers, base, selected=None):
    result = client.post(base+'/preview', headers=headers, json=selected or selection())
    assert result.status_code == 200, result.text
    return result.json()


def test_client_preview_copy_and_entire_word_package_exclude_internal_data(chat):
    client, database, _ = chat
    headers = sign_in(client)
    base = seed(client, headers)
    listing = client.get(base).json()
    assert listing['items'][0]['audiences'] == ['client','internal']
    public = preview(client, headers, base)
    internal = preview(client, headers, base, selection('internal'))
    assert PUBLIC in public['text'] and PRIVATE not in str(public)
    assert PRIVATE in internal['text']
    assert public['id'] != internal['id']
    assert public['content_sha256'] != internal['content_sha256']
    body = {**selection(),'expected_content_sha256':public['content_sha256']}
    copied = client.post(base+'/copy', headers=headers, json=body)
    assert copied.status_code == 200 and copied.json() == public
    response = client.post(base+'/docx', headers=headers, json=body)
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    assert 'attachment;' in response.headers['content-disposition']
    doc = Document(BytesIO(response.content))
    assert PUBLIC in '\n'.join(p.text for p in doc.paragraphs)
    with ZipFile(BytesIO(response.content)) as package:
        all_xml = '\n'.join(package.read(n).decode() for n in package.namelist() if n.endswith(('.xml','.rels')))
    assert PRIVATE not in all_xml
    assert '未经律师审核' in all_xml
    with database.session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0


@pytest.mark.parametrize('action', ['copy','docx'])
def test_digest_and_audience_mismatch_cannot_export(chat, action):
    client, _, _ = chat
    headers = sign_in(client)
    base = seed(client, headers)
    internal = preview(client, headers, base, selection('internal'))
    body = {**selection(),'expected_content_sha256':internal['content_sha256']}
    assert client.post(base+'/'+action, headers=headers, json=body).status_code == 409
    body['expected_content_sha256'] = '0'*64
    assert client.post(base+'/'+action, headers=headers, json=body).status_code == 409


def test_exact_old_revision_survives_new_manual_edit_and_explicit_clear(chat):
    client, _, _ = chat
    headers = sign_in(client)
    base = seed(client, headers)
    old = preview(client, headers, base)
    profile_url = base.removesuffix('/outputs')+'/profile'
    current = client.get(profile_url).json()
    value = {'request_id':str(uuid4()),'patch':{'scope':current['scope'],'base_profile_revision':1,'changes':[]},
             'manual_edits':[{'field':'client_reply','value':{'kind':'null','value':None}}], 'project_intake':False}
    commit(client, headers, profile_url, value)
    assert preview(client, headers, base) == old
    assert client.post(base+'/preview', headers=headers,json=selection(revision=2)).status_code == 409
    assert client.get(base).json()['items'][0]['audiences'] == ['internal']


def test_unknown_source_foreign_output_and_forged_body_rejected(chat):
    client, _, _ = chat
    headers = sign_in(client)
    base = seed(client, headers)
    assert client.post(base+'/preview',headers=headers,json=selection(revision=99)).status_code == 409
    for changes in ({'text':PRIVATE}, {'audience':'counterparty'}, {'source':{'kind':'model','output_id':str(uuid4()),'profile_revision':1}}):
        assert client.post(base+'/preview',headers=headers,json={**selection(),**changes}).status_code == 422
    assert client.post(base+'/preview',headers=headers,json={'source':{'kind':'model','output_id':str(uuid4())},'audience':'internal'}).status_code == 403


@pytest.mark.parametrize('action', ['preview','copy','docx'])
def test_owner_csrf_origin_and_auth_checked_before_body(chat, monkeypatch, action):
    from cn_contract.web import assistant_outputs
    client, _, _ = chat
    headers = sign_in(client)
    base = seed(client, headers)
    assert client.post(base+'/'+action,json={}).status_code == 403
    assert client.post(base+'/'+action,headers={**headers,'Origin':'https://evil.invalid'},json={}).status_code == 403
    async def unread(*args):
        pytest.fail('unauthorized body read')
    monkeypatch.setattr(assistant_outputs,'body_input',unread)
    other = sign_in(client,'另一合成律师')
    assert client.get(base).status_code == 403
    assert client.post(base+'/'+action,headers=other,content='invalid').status_code == 403
    client.cookies.clear()
    assert client.post(base+'/'+action,content='invalid').status_code == 401


@pytest.mark.parametrize('action', ['preview','copy','docx'])
def test_revocation_after_body_read_returns_no_content(chat, monkeypatch, action):
    from cn_contract.web import assistant_outputs
    client, database, _ = chat
    headers = sign_in(client)
    base = seed(client, headers)
    result = preview(client, headers, base)
    original = assistant_outputs.body_input
    async def revoke(request, model):
        value = await original(request, model)
        with database.session() as db:
            db.execute(text('UPDATE sessions SET revoked=1'))
        return value
    monkeypatch.setattr(assistant_outputs,'body_input',revoke)
    body = selection() if action == 'preview' else {**selection(),'expected_content_sha256':result['content_sha256']}
    response = client.post(base+'/'+action,headers=headers,json=body)
    assert response.status_code == 401
    assert PUBLIC not in response.text and PRIVATE not in response.text


def test_readonly_fence_denies_new_exports(chat):
    client, database, _ = chat
    headers = sign_in(client)
    base = seed(client, headers)
    value = preview(client, headers, base)
    from cn_contract.ops.storage import RestoreFenceRow
    with database.session() as db:
        db.add(RestoreFenceRow(ref=str(uuid4()),archive_sha256='a'*64,manifest_sha256='b'*64,payload='{}'))
    for action in ('preview','copy','docx'):
        body = selection() if action == 'preview' else {**selection(),'expected_content_sha256':value['content_sha256']}
        assert client.post(base+'/'+action,headers=headers,json=body).status_code == 409


def test_conflicting_client_candidates_are_not_guessed(chat):
    client, _, _ = chat
    headers = sign_in(client)
    url, value = command(client,headers,project_intake=False)
    change = value['patch']['changes'][0]
    value['patch']['changes'] = [{**change,'field':'client_reply','value':{'kind':'text','value':v}} for v in ('候选甲','候选乙')]
    commit(client,headers,url,value)
    base = url.removesuffix('/profile')+'/outputs'
    assert client.post(base+'/preview',headers=headers,json=selection()).status_code == 409
    internal = preview(client,headers,base,selection('internal'))
    assert '候选甲' not in internal['text'] and '候选乙' not in internal['text']
    assert '多个候选' in internal['text']


def test_permission_is_rechecked_after_word_render(chat, monkeypatch):
    from cn_contract.web import assistant_outputs
    client, database, _ = chat
    headers = sign_in(client)
    base = seed(client,headers)
    public = preview(client,headers,base)
    original = assistant_outputs.build
    def revoke(value):
        content = original(value)
        with database.session() as db:
            db.execute(text('UPDATE sessions SET revoked=1'))
        return content
    monkeypatch.setattr(assistant_outputs,'build',revoke)
    result = client.post(base+'/docx',headers=headers,json={**selection(),'expected_content_sha256':public['content_sha256']})
    assert result.status_code == 401 and PUBLIC not in result.text


def test_profile_history_is_selectable_through_bounded_source_pages(chat):
    import json
    client, _, _ = chat
    headers = sign_in(client)
    base = seed(client,headers)
    url = base.removesuffix('/outputs')+'/profile'
    for revision in range(1,22):
        current = client.get(url).json()
        commit(client,headers,url,{'request_id':str(uuid4()),'patch':{'scope':current['scope'],
            'base_profile_revision':revision,'changes':[]},'manual_edits':[{'field':'client_reply',
            'value':{'kind':'text','value':f'独立合成回复版本{revision+1}'}}],'project_intake':False})
    first = client.get(base).json()
    assert len(first['items']) == 20
    assert [i['source']['profile_revision'] for i in first['items']] == list(range(22,2,-1))
    second = client.get(base,params={'before':json.dumps(first['next_before'])}).json()
    assert [i['source']['profile_revision'] for i in second['items']] == [2,1]
    assert second['next_before'] is None
    old = preview(client,headers,base,{'source':second['items'][-1]['source'],'audience':'client'})
    assert old['text'] == PUBLIC
    assert client.get(base,params={'before':'invalid'}).status_code == 422


def test_old_binding_profile_not_offered_or_exported(chat):
    client, database, _ = chat
    headers = sign_in(client)
    base = seed(client,headers)
    cid = base.split('/')[-2]
    with database.session() as db:
        db.execute(text('UPDATE assistant_conversations SET binding_revision=2 WHERE id=:id'),{'id':cid})
    assert client.get(base).json()['items'] == []
    assert client.post(base+'/preview',headers=headers,json=selection()).status_code == 409


def test_revision_is_bounded_before_sql_binding(chat):
    client, _, _ = chat
    headers = sign_in(client)
    base = seed(client,headers)
    assert client.post(base+'/preview',headers=headers,json=selection(revision=2**80)).status_code == 422


def test_saved_source_survives_real_backup_and_restored_http_denies_new_exports(native, tmp_path):
    from pathlib import Path
    from fastapi.testclient import TestClient
    from cn_contract.ops import workspace_backup
    from cn_contract.web.local_server import build_local_app
    from tests.helpers.legacy_assistant_backup import PASSPHRASE
    app, root = native
    with TestClient(app) as client:
        headers = sign_in(client)
        base = seed(client,headers)
        public = preview(client,headers,base)
        original = client.get(base.removesuffix('/outputs')+'/profile/revisions/1').json()
    archive = tmp_path/'合成成果.qxbak'
    workspace_backup.create_workspace_backup(root,archive,PASSPHRASE,data_parent=tmp_path)
    restored = workspace_backup.restore_workspace_backup(archive,tmp_path/'restored',PASSPHRASE)
    restored_root = Path(restored['restored_root'])
    recovered = build_local_app(restored_root,data_parent=restored_root.parent.parent)
    try:
        with TestClient(recovered) as client:
            headers = sign_in(client)
            assert client.get(base.removesuffix('/outputs')+'/profile/revisions/1').json() == original
            assert client.get(base).status_code == 409
            for action in ('preview','copy','docx'):
                body = selection() if action == 'preview' else {**selection(),'expected_content_sha256':public['content_sha256']}
                assert client.post(base+'/'+action,headers=headers,json=body).status_code == 409
    finally:
        recovered.state.database.engine.dispose()
