"""Windows SQLite must leave room for journal files without moving the index."""
import hashlib
import json
import os
from pathlib import Path

import pytest

from business_store import CaseStore
import privacy
from reader import parse
from store import MaterialStore


pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows SQLite path regression')


def sized_root(base, suffix, length):
    """Bound each component, regardless of the caller's temporary directory length."""
    remaining = length - len(str(base / suffix))
    assert remaining >= 2, 'Use a shorter pytest --basetemp for this boundary fixture.'
    root = base
    while remaining > 100:
        root /= 'x' * 80
        remaining -= 81
    root /= 'y' * (remaining - 1)
    assert len(str(root / suffix)) == length
    return root


@pytest.mark.parametrize('length,label,extended', [
    (252, 'ascii', False), (258, '中文 空格#%', False), (320, '中文 空格#%', True),
])
def test_material_case_index_commit_reopen_rollback_and_source_identity(tmp_path, length, label, extended):
    workspace = sized_root(tmp_path / label, '.qx-materials/index.sqlite', length)
    if extended:
        workspace = Path('\\\\?\\' + str(workspace))
    workspace.mkdir(parents=True)
    original = workspace / '材料.txt'
    original.write_text('虚构材料：验收后十日内支付35000元。', encoding='utf-8')
    before = (hashlib.sha256(original.read_bytes()).hexdigest(), original.stat().st_mtime_ns)
    store = MaterialStore(workspace)
    registered = store.register('材料.txt')
    assert registered['sha256'] == before[0]
    assert parse(store, '材料.txt')['status'] == 'ready'
    cases = CaseStore(store)
    case = cases.create('虚构长目录案件')
    cases.link_materials(case['id'], ['材料.txt'])
    note = cases.add_note(case['id'], 'todo', '核对验收日期')
    with pytest.raises(RuntimeError, match='rollback'):
        with store.db() as db:
            assert db.execute('PRAGMA journal_mode').fetchone()[0] == 'delete'
            db.execute("UPDATE materials SET status='bad'")
            raise RuntimeError('rollback')
    reopened = CaseStore(workspace)
    assert reopened.read_note(case['id'], note['id'])['content'] == '核对验收日期'
    assert '35000' in reopened.read_material(case['id'], '材料.txt')['chunks'][0]['text']
    assert reopened.store.search('35000')['matches'][0]['path'] == '材料.txt'
    assert reopened.store.list()['materials'][0]['status'] == 'ready'
    assert reopened.store.list()['workspace'] == str(workspace.resolve())
    with pytest.raises(ValueError):
        reopened.store.register('../outside.txt')
    with pytest.raises(ValueError):
        reopened.store.register('.qx-materials/index.sqlite')
    with reopened.db() as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert (hashlib.sha256(original.read_bytes()).hexdigest(), original.stat().st_mtime_ns) == before
    assert store.db_path == workspace.resolve() / '.qx-materials/index.sqlite'


def test_long_index_preserves_live_wal(tmp_path):
    workspace = sized_root(tmp_path / 'wal', '.qx-materials/index.sqlite', 258)
    store = MaterialStore(workspace)
    cases = CaseStore(store)
    with store.db() as db:
        assert db.execute('PRAGMA journal_mode=WAL').fetchone()[0] == 'wal'
        db.execute('PRAGMA wal_autocheckpoint=0')
        db.execute('BEGIN')
        assert db.execute('SELECT COUNT(*) FROM legal_cases').fetchone()[0] == 0
        case = cases.create('合成 WAL 案件')
        # Another connection reads committed WAL while the first connection stays open.
        assert CaseStore(workspace).get(case['id'])['case']['title'] == '合成 WAL 案件'
        wal = Path('\\\\?\\' + str(store.db_path) + '-wal')
        assert wal.is_file() and wal.stat().st_size > 0
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert CaseStore(workspace).get(case['id'])['case']['title'] == '合成 WAL 案件'


def test_long_index_rejects_linked_database(tmp_path):
    workspace = sized_root(tmp_path / 'links', '.qx-materials/index.sqlite', 258)
    store = MaterialStore(workspace)
    original = store.db_path
    saved = original.with_name('saved.sqlite')
    original.rename(saved)
    try:
        original.symlink_to(saved)
    except OSError as error:
        if error.winerror == 1314:
            pytest.skip('Windows symbolic-link privilege is unavailable')
        raise
    with pytest.raises(ValueError, match='链接|联接'):
        MaterialStore(workspace)


@pytest.mark.parametrize('context_id', [None, 'synthetic-case'])
def test_long_private_mapping_prepare_review_and_repeated_upload(tmp_path, context_id):
    identifier = '01234567-89ab-4cde-8012-3456789abcde'
    # Context mappings are deeper; both mapping layouts previously exceed SQLite's journal limit.
    suffix = (f'contexts/{hashlib.sha256(context_id.encode()).hexdigest()}/mapping.sqlite'
              if context_id else f'documents/{identifier}/.qx-materials/index.sqlite')
    vault = sized_root(tmp_path / '私有 空格#%', suffix, 258)
    source = tmp_path / 'original.txt'
    text = '姓名：李明。电话：13800138000。金额35000元。'
    source.write_text(text, encoding='utf-8')
    before = (source.read_bytes(), source.stat().st_mtime_ns)
    result = privacy.prepare_upload(str(source), str(vault), document_id=identifier,
                                    context_id=context_id, review=True)
    assert result['status'] == 'ready', result
    review = json.loads(Path(result['review_path']).read_text(encoding='utf-8'))
    assert review['original_text'] == text
    assert '李明' not in review['safe_text'] and '13800138000' not in review['safe_text']
    assert '35000元' in review['safe_text']
    restored = review['safe_text']
    for replacement in review['replacements']:
        restored = restored.replace(replacement['token'], replacement['original'])
    assert restored == text
    second = privacy.prepare_upload(str(source), str(vault), context_id=context_id, review=True)
    assert second['status'] == 'ready', second
    second_review = json.loads(Path(second['review_path']).read_text(encoding='utf-8'))
    assert (second_review['safe_text'] == review['safe_text']) is bool(context_id)
    final = privacy.finalize_review(str(vault), review['document_id'], review['review_token'],
                                    review['safe_text'], manual_replacements=[])
    assert final['status'] == 'ready', final
    record_path = vault / 'documents' / review['document_id'] / ('reviewed-' + final['revision'] + '.json')
    record = json.loads(Path('\\\\?\\' + str(record_path)).read_text(encoding='utf-8'))
    assert record['sha256'] == hashlib.sha256(Path(final['safe_path']).read_bytes()).hexdigest()
    assert not result['safe_path'].startswith('\\\\?\\')
    assert (source.read_bytes(), source.stat().st_mtime_ns) == before
