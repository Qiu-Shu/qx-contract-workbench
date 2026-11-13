"""Parse new materials without discarding the explicit re-import requirement."""
import hashlib
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

import server
from store import MaterialStore, MaterialNotRegistered


@pytest.fixture
def material(tmp_path, monkeypatch):
    store = MaterialStore(tmp_path / 'workspace')
    monkeypatch.setattr(server, 'store', store)
    source = store.root / '合成 材料.txt'
    source.write_text('虚构材料：验收后十日付款35000元。', encoding='utf-8')
    return store, source


def test_parse_new_and_copied_material_preserves_original(material):
    store, source = material
    before = source.read_bytes(), source.stat().st_mtime_ns
    assert server.parse_material(source.name)['status'] == 'ready'
    parsed = server.read_material(source.name)
    assert parsed['sha256'] == hashlib.sha256(before[0]).hexdigest()
    assert server.parse_material(source.name)['status'] == 'ready'
    copied = source.with_name('合成 材料 副本 (1).txt')
    copied.write_bytes(before[0])
    assert server.parse_material(copied.name)['status'] == 'ready'
    assert server.read_material(source.name) == parsed
    assert server.read_material(copied.name)['sha256'] == parsed['sha256']
    assert (source.read_bytes(), source.stat().st_mtime_ns) == before


def test_changed_material_requires_explicit_reimport_and_preserves_old_index(material):
    store, source = material
    server.import_material(source.name)
    server.parse_material(source.name)
    with store.db() as db:
        rows = [tuple(row) for row in db.execute('SELECT * FROM chunks')]
        digest = db.execute('SELECT sha256 FROM materials').fetchone()[0]
    source.write_text('虚构材料新版本，尚未确认导入。', encoding='utf-8')
    with pytest.raises(ToolError, match='原文件已修改'):
        server.parse_material(source.name)
    with store.db() as db:
        assert [tuple(row) for row in db.execute('SELECT * FROM chunks')] == rows
        assert db.execute('SELECT sha256 FROM materials').fetchone()[0] == digest
    server.import_material(source.name)
    assert server.parse_material(source.name)['status'] == 'ready'


@pytest.mark.parametrize('kind', ['outside', 'missing', 'unsupported', 'invalid-mode'])
def test_invalid_parse_does_not_register(material, kind):
    store, source = material
    path, arguments = source.name, {}
    if kind == 'outside':
        outside = store.root.parent / 'outside.txt'
        outside.write_text('synthetic outside material', encoding='utf-8')
        path = str(outside)
    elif kind == 'missing':
        path = 'missing.txt'
    elif kind == 'unsupported':
        path = 'not-an-executable.exe'
        (store.root / path).write_bytes(b'synthetic')
    else:
        arguments['revision_mode'] = 'invalid'
    with pytest.raises(ToolError):
        server.parse_material(path, **arguments)
    with store.db() as db:
        assert db.execute('SELECT COUNT(*) FROM materials').fetchone()[0] == 0


def test_read_still_requires_registration(material):
    _, source = material
    with pytest.raises(ToolError, match='请先调用 import_material'):
        server.read_material(source.name)


def test_competing_registration_cannot_silently_reimport_a_changed_original(material, monkeypatch):
    store, source = material
    current = store.current
    competing = MaterialStore(store.root)
    def race(path, db):
        try:
            return current(path, db)
        except MaterialNotRegistered:
            competing.register(path)
            source.write_text('Concurrent synthetic changed original.', encoding='utf-8')
            raise
    monkeypatch.setattr(store, 'current', race)
    with pytest.raises(ToolError, match='原文件已修改'):
        server.parse_material(source.name)
    with store.db() as db:
        assert db.execute('SELECT sha256 FROM materials').fetchone()[0] != hashlib.sha256(source.read_bytes()).hexdigest()


def test_parser_failure_is_not_retried_or_reported_as_success(material, monkeypatch):
    store, source = material
    broken = source.with_suffix('.pdf')
    broken.write_bytes(b'synthetic invalid PDF')
    calls = []
    original = server.subprocess.run
    def capture(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(server.subprocess, 'run', capture)
    with pytest.raises(ToolError):
        server.parse_material(broken.name)
    assert calls == [1]
    with store.db() as db:
        assert db.execute('SELECT COUNT(*) FROM materials').fetchone()[0] == 1
