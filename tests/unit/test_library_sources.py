"""Original-byte preservation and source identity, using invented files only."""
import hashlib
import importlib
import importlib.util
import os
import sqlite3
from datetime import datetime, timezone

import pytest


def api():
    assert importlib.util.find_spec('cn_contract.library'), 'local library implementation missing'
    return importlib.import_module('cn_contract.library.assets')


def source(tmp_path, name='法规.md', text='# 虚构测试规定\r\n第一条 测试。'):
    path = tmp_path / name
    path.write_bytes(text.encode('utf-8'))
    return path


def test_source_copy_hash_and_alias(tmp_path):
    assets = api()
    original = source(tmp_path)
    raw = original.read_bytes()
    root = tmp_path / '资料 库'
    first = assets.register_source(root, original, 'fiction', 'law_markdown')
    moved = tmp_path / '另一个目录'
    moved.mkdir()
    alias = moved / original.name
    alias.write_bytes(raw)
    second = assets.register_source(root, alias, 'fiction', 'law_markdown')
    assert first.source_id == second.source_id
    assert first.sha256 == hashlib.sha256(raw).hexdigest()
    assert assets.read_asset(root, first.source_id, 0, len(raw)) == raw
    assert original.read_bytes() == raw
    assert len(second.aliases) == 2
    original.write_text('原路径被后来修改', encoding='utf-8')
    assert assets.read_asset(root, first.source_id, 0, len(raw)) == raw


def test_changed_content_retains_both_versions(tmp_path):
    assets = api()
    original = source(tmp_path)
    root = tmp_path / 'library'
    first = assets.register_source(root, original, 'fiction', 'law_markdown')
    old = original.read_bytes()
    original.write_text('另一个版本', encoding='utf-8')
    second = assets.register_source(root, original, 'fiction', 'law_markdown')
    assert first.source_id != second.source_id
    assert assets.read_asset(root, first.source_id, 0, len(old)) == old


def test_snapshot_change_abort(tmp_path, monkeypatch):
    assets = api()
    original = source(tmp_path)
    root = tmp_path / 'library'
    copy = assets._copy_snapshot

    def copy_then_change(src, dst):
        result = copy(src, dst)
        src.write_bytes(b'changed during read')
        return result

    monkeypatch.setattr(assets, '_copy_snapshot', copy_then_change)
    with pytest.raises(ValueError, match='SOURCE_CHANGED'):
        assets.register_source(root, original, 'fiction', 'law_markdown')
    with sqlite3.connect(root / 'catalog.sqlite') as db:
        assert db.execute('select count(*) from sources').fetchone()[0] == 0


def test_reject_overlapping_and_nonempty_root(tmp_path):
    assets = api()
    original = source(tmp_path)
    with pytest.raises(ValueError, match='OVERLAP|NOT_INITIALIZED'):
        assets.register_source(tmp_path, original, 'fiction', 'law_markdown')
    assert original.read_bytes()


def test_reject_redirected_root(tmp_path):
    assets = api()
    original = source(tmp_path)
    target = tmp_path / 'real'
    target.mkdir()
    link = tmp_path / 'link'
    if os.name == 'nt':
        import subprocess
        subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)], check=True, capture_output=True)
    else:
        link.symlink_to(target, target_is_directory=True)
    try:
        with pytest.raises(ValueError, match='REDIRECTED'):
            assets.register_source(link / 'nested', original, 'fiction', 'law_markdown')
        assert list(target.iterdir()) == []
    finally:
        # rmdir removes this test junction itself, never its target tree.
        link.rmdir() if os.name == 'nt' else link.unlink()


def test_asset_corruption_and_invalid_ranges_are_rejected(tmp_path):
    assets = api()
    original = source(tmp_path)
    root = tmp_path / 'library'
    item = assets.register_source(root, original, 'fiction', 'law_markdown')
    for start, end in [(-1, 2), (5, 2), (0, item.size + 1)]:
        with pytest.raises(ValueError):
            assets.read_asset(root, item.source_id, start, end)
    with pytest.raises(ValueError):
        assets.read_asset(root, '../outside', 0, 1)
    (root / 'assets' / item.asset_key).write_bytes(b'x' * item.size)
    with pytest.raises(ValueError, match='HASH_MISMATCH'):
        assets.read_asset(root, item.source_id, 0, item.size)


def test_audit_append_only(tmp_path):
    assets = api()
    root = tmp_path / 'library'
    item = assets.register_source(root, source(tmp_path), 'fiction', 'law_markdown')
    catalog = importlib.import_module('cn_contract.library.catalog')
    domain = importlib.import_module('cn_contract.domain')
    event = domain.LibraryReviewEvent(subject_id=item.source_id, version_id=item.sha256,
        operator='虚构审核者', recorded_at=datetime.now(timezone.utc),
        field='text_integrity', value='needs_review', reason='虚构核对记录')
    first = catalog.append_review(root, event)
    second = catalog.append_review(root, event.model_copy(update={'reason': '第二次虚构核对'}))
    assert first != second
    with sqlite3.connect(root / 'catalog.sqlite') as db:
        rows = db.execute('select event_hash,previous_hash from reviews order by seq').fetchall()
        assert rows == [(first, None), (second, first)]
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("update reviews set event_json='{}'")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute('delete from reviews')
