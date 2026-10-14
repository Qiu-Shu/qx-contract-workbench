"""Local library shares authentication and never grants authority to source text."""
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from cn_contract.web import local_server
from cn_contract.library.law_sections import import_laws
from cn_contract.library.index import build_generation, activate_generation
from tests.integration.test_local_workbench import login, PASSWORD


@pytest.fixture
def library_client(tmp_path, monkeypatch):
    monkeypatch.setattr(local_server, 'PROJECT_ROOT', tmp_path)
    laws = tmp_path / 'laws'
    laws.mkdir()
    (laws / '虚构租赁法规.md').write_text('第一条 虚构租赁。<script>alert(1)</script> ![x](javascript:alert(1))', encoding='utf-8')
    root = tmp_path / 'library'
    import_laws(root, laws, 'fiction')
    activate_generation(root, build_generation(root))
    workspace = tmp_path / '.local' / 'workbench'
    local_server.initialize_workspace(workspace, 'local-lawyer', PASSWORD)
    from cn_contract.domain import Role
    local_server.add_local_user(workspace, 'library-reader', PASSWORD, Role.ASSISTANT)
    with TestClient(local_server.build_local_app(workspace, library_root=root)) as client:
        yield client


def test_library_requires_login_csrf_and_same_origin(library_client):
    client = library_client
    for path in ('/library', '/api/library/status', '/api/library/records/abc?version_id=abc', '/api/library/fragments/abc'):
        assert client.get(path).status_code == 401
    assert client.post('/api/library/search', json={'text': '租赁'}).status_code == 401
    headers = login(client)
    assert client.post('/api/library/search', json={'text': '租赁'}).status_code == 403
    assert client.post('/api/library/search', json={'text': '租赁'}, headers={**headers, 'Origin': 'https://other.example'}).status_code == 403
    assert client.post('/api/library/search', json={'text': '租赁'}, headers=headers).status_code == 200
    client.post('/api/logout', headers=headers)
    assert client.get('/api/library/status').status_code == 401
    headers = login(client, username='library-reader')
    assert client.post('/api/library/search', json={'text': '租赁'}, headers=headers).status_code == 200


def test_library_versions_paths_and_passive_text(library_client):
    client = library_client
    headers = login(client)
    page = client.get('/library')
    assert page.status_code == 200 and '待核验' in page.text
    assert "script-src 'self'" in page.headers['Content-Security-Policy']
    assert '法律资料库' in client.get('/').text
    assert client.get('/static/library.js').status_code == 200
    js = client.get('/static/library.js').text
    assert '.innerHTML' not in js and '.textContent' in js
    assert '<script>alert' not in page.text
    result = client.post('/api/library/search', json={'text': '租赁'}, headers=headers).json()
    hit = result['hits'][0]
    original = client.get(f"/api/library/records/{hit['record_id']}?version_id={hit['version_id']}")
    assert original.status_code == 200 and '<script>' in original.json()['text']
    assert client.get(f"/api/library/fragments/{hit['fragment_id']}").status_code == 200
    assert client.get(f"/api/library/records/{hit['record_id']}?version_id=" + 'f' * 64).status_code == 409
    assert client.get('/api/library/records/file?version_id=file').status_code == 422
    assert client.post('/api/library/search', json={'text': '租赁', 'path': 'C:/Windows'}, headers=headers).status_code == 422
    assert client.get('/api/library/status').json()['coverage']['law_markdown'] == 1
    assert client.get('/api/matters').json() == []


def test_library_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(local_server, 'PROJECT_ROOT', tmp_path)
    workspace = tmp_path / '.local' / 'workbench'
    local_server.initialize_workspace(workspace, 'local-lawyer', PASSWORD)
    with TestClient(local_server.build_local_app(workspace)) as client:
        login(client)
        assert client.get('/api/library/status').status_code == 404
        assert 'href="/library"' not in client.get('/').text
