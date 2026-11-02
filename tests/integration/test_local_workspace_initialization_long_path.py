"""Create a brand-new local workspace at its actual long logical destination."""
from contextlib import closing
import json
import os
import sqlite3
from uuid import UUID

from fastapi.testclient import TestClient
import pytest

from cn_contract.ops.file_paths import filesystem_path, sqlite_readonly_uri
from cn_contract.schema_migrations import database_rows
from cn_contract.storage_schema import CURRENT_VERSION, identify_schema
from cn_contract.web import local_server
from tests.integration.test_local_workbench import login, PASSWORD


def long_root(parent):
    root = parent / 'independent-new-workspace'
    while len(str(root)) <= 300:
        root /= '全新-虚构-路径%23#-段落'
    assert len(str(root)) > 300
    assert len(str(root / 'workbench.db')) > 300
    return root


def file_bytes(root):
    native = filesystem_path(root)
    return {path.relative_to(native).as_posix(): path.read_bytes()
        for path in native.rglob('*') if path.is_file()}


def test_initialize_long_workspace_is_created_in_place_and_logs_in(tmp_path):
    root = long_root(tmp_path)
    assert not filesystem_path(root).exists()
    created = local_server.initialize_workspace(root, 'local-lawyer', PASSWORD, data_parent=tmp_path)
    assert created == root
    assert not str(created).startswith('\\\\?\\')
    marker = json.loads(filesystem_path(root / 'workspace.json').read_text(encoding='utf-8'))
    assert str(UUID(marker['workspace_id'])) == marker['workspace_id']
    with closing(sqlite3.connect(sqlite_readonly_uri(root / 'workbench.db'), uri=True)) as db:
        assert identify_schema(database_rows(db), native=True) == CURRENT_VERSION
        assert db.execute('SELECT id FROM local_workspace_identity').fetchall() == [(marker['workspace_id'],)]
        assert local_server._schema_hash(db) == marker['schema_sha256']
        assert db.execute('PRAGMA quick_check').fetchall() == [('ok',)]
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
    app = local_server.build_local_app(root, data_parent=tmp_path)
    assert str(app.state.database.engine.url.database) == str(root / 'workbench.db')
    assert app.state.database.storage_root == root / 'protected'
    with TestClient(app) as client:
        assert client.get('/api/matters').status_code == 401
        login(client)
        assert client.get('/api/session').json()['roles'] == ['handling_lawyer']
        assert client.get('/api/matters').json() == []
    reopened = local_server.build_local_app(root, data_parent=tmp_path)
    assert str(reopened.state.database.engine.url.database) == str(root / 'workbench.db')
    assert reopened.state.database.storage_root == root / 'protected'
    with TestClient(reopened) as client:
        login(client)
        assert client.get('/api/matters').json() == []
    assert json.loads(filesystem_path(root / 'workspace.json').read_text(encoding='utf-8')) == marker
    before = file_bytes(root)
    with pytest.raises(ValueError, match='^WORKSPACE_ALREADY_EXISTS$'):
        local_server.initialize_workspace(root, 'other-lawyer', PASSWORD, data_parent=tmp_path)
    assert file_bytes(root) == before


@pytest.mark.parametrize('username,password', [('', PASSWORD), (' x', PASSWORD),
    ('new\nline', PASSWORD), ('local-lawyer', 'short'), ('local-lawyer', 'x' * 13)])
def test_invalid_credentials_do_not_create_long_workspace(tmp_path, username, password):
    root = long_root(tmp_path)
    with pytest.raises(ValueError, match='^LOCAL_CREDENTIALS_INVALID$'):
        local_server.initialize_workspace(root, username, password, data_parent=tmp_path)
    assert not filesystem_path(root).exists()


@pytest.mark.parametrize('relation', ['outside', 'parent-itself'])
def test_long_workspace_stays_within_trusted_parent(tmp_path, relation):
    root = long_root(tmp_path / 'independent-untrusted')
    parent = tmp_path / 'trusted' if relation == 'outside' else root
    with pytest.raises(ValueError, match='^PROJECT_LOCAL_DIRECTORY_REQUIRED$'):
        local_server.initialize_workspace(root, 'local-lawyer', PASSWORD, data_parent=parent)
    assert not filesystem_path(root).exists()


@pytest.mark.parametrize('redirected_node', ['root', 'parent'])
def test_initialize_long_redirected_workspace_preserves_target(tmp_path, redirected_node):
    target = tmp_path / 'independent-target'
    target.mkdir()
    (target / 'preserved.txt').write_bytes(b'independent synthetic redirect sentinel')
    before = file_bytes(target)
    link = long_root(tmp_path)
    filesystem_path(link.parent).mkdir(parents=True)
    os.symlink(filesystem_path(target), filesystem_path(link), target_is_directory=True)
    assert filesystem_path(link).is_symlink()
    root = link if redirected_node == 'root' else link / 'new-child'
    with pytest.raises(ValueError, match='^REDIRECTED_WORKSPACE$'):
        local_server.initialize_workspace(root, 'local-lawyer', PASSWORD, data_parent=tmp_path)
    assert file_bytes(target) == before


def test_initialize_long_partial_workspace_rejects_without_overwrite(tmp_path):
    root = long_root(tmp_path)
    filesystem_path(root).mkdir(parents=True)
    filesystem_path(root / 'preserved.txt').write_bytes(b'independent synthetic partial workspace')
    before = file_bytes(root)
    with pytest.raises(ValueError, match='^WORKSPACE_ALREADY_EXISTS$'):
        local_server.initialize_workspace(root, 'local-lawyer', PASSWORD, data_parent=tmp_path)
    assert file_bytes(root) == before
