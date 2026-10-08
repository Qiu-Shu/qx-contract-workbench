"""Persistent local startup reuses the actual application, auth and case store."""
import importlib
import importlib.util
import json
from pathlib import Path
import time
import sqlite3
from threading import Event, Thread
from uuid import UUID

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from cn_contract.domain import Role
from cn_contract.persistence import UserRow
from tests.integration.test_api import create_case


PASSWORD = 'fictional-local-account-12345'


@pytest.fixture
def local(tmp_path, monkeypatch):
    assert importlib.util.find_spec('cn_contract.web.local_server'), 'persistent startup is missing'
    module = importlib.import_module('cn_contract.web.local_server')
    monkeypatch.setattr(module, 'PROJECT_ROOT', tmp_path)
    return module, tmp_path / '.local' / 'workbench'


def login(client, username='local-lawyer', password=PASSWORD):
    response = client.post('/api/login', json={'username': username, 'password': password})
    assert response.status_code == 200, response.text
    return {'X-CSRF-Token': response.json()['csrf_token']}


def test_restart_preserves_accounts_cases_and_current_session(local):
    module, root = local
    module.initialize_workspace(root, 'local-lawyer', PASSWORD)
    app = module.build_local_app(root)
    with TestClient(app) as client:
        headers = login(client)
        matter = create_case(client, headers, title='持久化虚构案件')
        cookies = dict(client.cookies)
        with app.state.database.session() as db:
            before = [(r.id, r.username, r.password_hash) for r in db.scalars(select(UserRow))]
        assert [r[1] for r in before] == ['local-lawyer']
        assert client.post('/api/login', json={'username': 'lawyer',
            'password': 'synthetic-only-12345'}).status_code == 401
    app2 = module.build_local_app(root)
    with TestClient(app2) as resumed:
        resumed.cookies.update(cookies)
        data = resumed.get('/api/matters').json()
        assert [r['id'] for r in data] == [matter]
        assert data[0]['title'] == '持久化虚构案件'
        login(resumed)
        with app2.state.database.session() as db:
            assert [(r.id, r.username, r.password_hash) for r in db.scalars(select(UserRow))] == before
        assert app2.state.purpose == 'assisted_draft'


def test_document_worker_original_and_anchors_survive_restart(local):
    from cn_contract.documents.ingest import DOCX_MIME
    from cn_contract.persistence import read_original
    from cn_contract.security import authenticate
    from tests.integration.test_assisted_review import CASES, source
    module, root = local
    module.initialize_workspace(root, 'local-lawyer', PASSWORD)
    raw = source(CASES[0])
    with TestClient(module.build_local_app(root)) as client:
        headers = login(client)
        matter = create_case(client, headers)
        url = f'/api/matters/{matter}/documents'
        denied = client.post(url, headers=headers, files={'file': ('unknown.docx', b'unregistered', DOCX_MIME)},
                             data={'baseline_view': 'original'})
        assert denied.status_code == 409 and denied.json()['code'] == 'DATA_POLICY_UNAPPROVED'
        uploaded = client.post(url, headers={**headers, 'Idempotency-Key': 'persist-upload'}, files={'file': ('fiction.docx', raw, DOCX_MIME)},
                               data={'baseline_view': 'original'})
        assert uploaded.status_code == 202, uploaded.text
        version = uploaded.json()['version_id']
        job = uploaded.json()['job_id']
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            state = client.get(f'/api/jobs/{job}').json()['state']
            if state == 'completed':
                break
            time.sleep(.02)
        assert state == 'completed'
        anchors_url = f'{url}/{version}/anchors'
        anchors = client.get(anchors_url).json()
        assert anchors['anchors']
    app = module.build_local_app(root)
    with TestClient(app) as client:
        login(client)
        assert client.get(anchors_url).json() == anchors
        assert client.get(f'/api/jobs/{job}').json()['state'] == 'completed'
        with app.state.database.session() as db:
            actor = authenticate(client.cookies.get('qx_session'), db)
            assert read_original(UUID(matter), UUID(version), actor, db) == raw


def test_initialization_never_overwrites_existing_workspace(local):
    module, root = local
    module.initialize_workspace(root, 'local-lawyer', PASSWORD)
    before = (root / 'workbench.db').read_bytes()
    with pytest.raises(ValueError):
        module.initialize_workspace(root, 'someone-else', PASSWORD)
    assert (root / 'workbench.db').read_bytes() == before


def test_account_maintenance_requires_stopped_workspace(local):
    module, root = local
    module.initialize_workspace(root, 'local-lawyer', PASSWORD)
    with TestClient(module.build_local_app(root)):
        with pytest.raises(ValueError, match='WORKSPACE_IN_USE'):
            module.add_local_user(root, 'new-assistant', PASSWORD, Role.ASSISTANT)
    module.add_local_user(root, 'new-assistant', PASSWORD, Role.ASSISTANT)


def test_bridge_only_attaches_to_default_port_and_directory(local):
    module, root = local
    module.initialize_workspace(root, 'local-lawyer', PASSWORD)
    with TestClient(module.build_local_app(root, port=18767)) as client:
        assert not hasattr(client.app.state, 'case_bridge')
    custom = root.parent / 'other-workspace'
    module.initialize_workspace(custom, 'other-lawyer', PASSWORD)
    with TestClient(module.build_local_app(custom)) as client:
        assert not hasattr(client.app.state, 'case_bridge')
    with TestClient(module.build_local_app(root)) as client:
        assert hasattr(client.app.state, 'case_bridge')
        # Stale credentials from an earlier server are never carried forward.
        path = root / 'selected-case.json'
        path.write_text('{}', encoding='utf8')
    assert not path.exists()


@pytest.mark.parametrize('username,password', [('', PASSWORD), ('x' * 129, PASSWORD),
    ('new\nline', PASSWORD), ('local-lawyer', 'short'), ('local-lawyer', 'x' * 257)])
def test_invalid_initial_credentials_leave_no_partial_workspace(local, username, password):
    module, root = local
    with pytest.raises(ValueError):
        module.initialize_workspace(root, username, password)
    assert not root.exists()


def test_foreign_or_incomplete_workspace_is_not_created_or_repaired(local):
    module, root = local
    with pytest.raises(ValueError):
        module.build_local_app(root)
    assert not root.exists()
    root.mkdir(parents=True)
    (root / 'workbench.db').write_bytes(b'foreign bytes')
    with pytest.raises(ValueError):
        module.build_local_app(root)
    assert (root / 'workbench.db').read_bytes() == b'foreign bytes'


def test_policy_marker_tamper_is_rejected_before_database_open(local):
    module, root = local
    module.initialize_workspace(root, 'local-lawyer', PASSWORD)
    before = (root / 'workbench.db').read_bytes()
    marker = root / 'workspace.json'
    payload = json.loads(marker.read_text(encoding='utf-8'))
    payload['purpose'] = 'formal_release'
    marker.write_text(json.dumps(payload), encoding='utf-8')
    with pytest.raises(ValueError):
        module.build_local_app(root)
    assert (root / 'workbench.db').read_bytes() == before


def test_add_explicit_account_preserves_least_privilege_and_duplicate_password(local):
    module, root = local
    module.initialize_workspace(root, 'local-lawyer', PASSWORD)
    module.add_local_user(root, 'local-assistant', PASSWORD, Role.ASSISTANT)
    with pytest.raises(ValueError):
        module.add_local_user(root, 'local-assistant', 'another-fictional-password', Role.ADMIN)
    with TestClient(module.build_local_app(root)) as client:
        headers = login(client, 'local-assistant')
        assert client.get('/api/session').json()['roles'] == ['assistant']
        assert client.get('/api/matters').json() == []
        assert client.post('/api/matters', headers=headers, json={}).status_code == 403


def test_second_running_workspace_is_rejected_and_lock_released(local):
    module, root = local
    module.initialize_workspace(root, 'local-lawyer', PASSWORD)
    with TestClient(module.build_local_app(root)):
        with pytest.raises(ValueError, match='WORKSPACE_IN_USE'):
            with TestClient(module.build_local_app(root)):
                pass
    with TestClient(module.build_local_app(root)) as client:
        login(client)


def test_outside_project_and_local_root_are_rejected(local, tmp_path):
    module, root = local
    for path in [tmp_path / 'outside', tmp_path / '.local', root / '..' / '..' / 'escape']:
        with pytest.raises(ValueError):
            module.initialize_workspace(path, 'local-lawyer', PASSWORD)


def test_cli_password_never_accepted_as_argument_or_noninteractive_input(local, monkeypatch, capsys):
    module, root = local
    with pytest.raises(SystemExit) as result:
        module.main(['init', '--directory', str(root), '--username', 'local-lawyer', '--password', PASSWORD])
    assert result.value.code == 2
    output = capsys.readouterr()
    assert PASSWORD not in output.out + output.err
    monkeypatch.setattr(module.sys.stdin, 'isatty', lambda: False)
    assert module.main(['init', '--directory', str(root), '--username', 'local-lawyer']) == 1
    output = capsys.readouterr()
    assert PASSWORD not in output.out + output.err
    assert not root.exists()


@pytest.mark.parametrize('corruption', ['empty', 'missing-table', 'different-workspace'])
def test_corrupt_or_replaced_database_never_rebuilt_on_start(local, corruption):
    module, root = local
    module.initialize_workspace(root, 'local-lawyer', PASSWORD)
    database_path = root / 'workbench.db'
    if corruption == 'empty':
        database_path.write_bytes(b'')
    elif corruption == 'missing-table':
        with sqlite3.connect(database_path) as db:
            db.execute('DROP TABLE web_http_writes')
    else:
        other = root.with_name('other')
        module.initialize_workspace(other, 'local-lawyer', PASSWORD)
        database_path.write_bytes((other / 'workbench.db').read_bytes())
    before = database_path.read_bytes()
    with pytest.raises(ValueError):
        module.build_local_app(root)
    assert database_path.read_bytes() == before


def test_shutdown_retains_lock_until_active_worker_finishes(local, monkeypatch):
    from cn_contract.web import demo_server
    module, root = local
    module.initialize_workspace(root, 'local-lawyer', PASSWORD)
    running, release, closing, joining, exited = (Event() for _ in range(5))
    errors = []

    def work(database):
        running.set()
        release.wait(5)

    class FastTimeoutThread(Thread):
        def join(self, timeout=None):
            joining.set()
            return super().join(.02 if timeout is not None else None)

    monkeypatch.setattr(demo_server, 'run_next_job', work)
    monkeypatch.setattr(demo_server, 'Thread', FastTimeoutThread)

    def host():
        try:
            with TestClient(module.build_local_app(root)):
                closing.wait(5)
        except BaseException as error:
            errors.append(error)
        finally:
            exited.set()

    process = Thread(target=host)
    process.start()
    try:
        assert running.wait(3)
        closing.set()
        assert joining.wait(3)
        assert not exited.wait(.1), 'host exited while its worker was still running'
        with pytest.raises(ValueError, match='WORKSPACE_IN_USE'):
            with module._worker_lock(root):
                pass
    finally:
        release.set(); closing.set(); process.join(5)
    assert not process.is_alive() and not errors
    with module._worker_lock(root):
        pass


def test_start_prompts_once_then_reopens_without_password_reset(local, monkeypatch, capsys):
    import uvicorn
    module, root = local
    monkeypatch.setattr(module.sys.stdin, 'isatty', lambda: True)
    monkeypatch.setattr('builtins.input', lambda prompt: 'local-lawyer')
    answers = iter([PASSWORD, PASSWORD])
    monkeypatch.setattr(module.getpass, 'getpass', lambda prompt: next(answers))
    calls = []

    def serve(app, **kwargs):
        calls.append(kwargs)
        with TestClient(app) as client:
            login(client)

    monkeypatch.setattr(uvicorn, 'run', serve)
    assert module.main(['start', '--directory', str(root)]) == 0
    assert module.main(['start', '--directory', str(root)]) == 0
    assert len(calls) == 2
    assert all(c['host'] == '127.0.0.1' and c['workers'] == 1 and not c['access_log'] for c in calls)
    output = capsys.readouterr()
    assert PASSWORD not in output.out + output.err
