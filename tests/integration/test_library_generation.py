"""Durability with actual SQLite files and invented sources, including Windows readers."""
import csv
import importlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

import pytest


def fixture(root, count=12):
    from cn_contract.library.csv_source import import_case_file
    source = root.parent / (root.name + '.csv')
    with source.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['案号', '文书内容'])
        writer.writerows([[str(i), '虚构租赁争议。' * 30] for i in range(count)])
    import_case_file(root, source, 'fiction')


def test_failed_build_keeps_current_and_resumes_without_duplicates(tmp_path, monkeypatch):
    from cn_contract.library import index
    root = tmp_path / 'library'
    fixture(root)
    old = index.build_generation(root)
    index.activate_generation(root, old)
    assert hasattr(index, 'check_budget'), 'generation resource checkpoint missing'
    real = index.check_budget
    calls = 0
    def fail(path, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise ValueError('LIBRARY_DISK_BUDGET')
        return real(path, **kwargs)
    monkeypatch.setattr(index, 'check_budget', fail)
    with pytest.raises(ValueError, match='BUDGET'):
        index.build_generation(root, batch_size=2)
    assert index.current_generation(root)['generation_id'] == old
    pending = [p.name for p in (root / 'generations').iterdir() if p.name != old][0]
    monkeypatch.setattr(index, 'check_budget', real)
    resumed = index.build_generation(root, resume=pending, batch_size=2)
    assert resumed == pending
    with sqlite3.connect(root / 'generations' / resumed / 'search.sqlite') as db:
        assert db.execute('select count(*),count(distinct unit_id) from units').fetchone() == (12, 12)
        assert db.execute('select count(*) from search').fetchone() == (12,)
    index.activate_generation(root, resumed)


def test_windows_reader_survives_pointer_swap_and_corruption_rejected(tmp_path):
    from cn_contract.library import index
    root = tmp_path / 'library'
    fixture(root)
    old = index.build_generation(root)
    index.activate_generation(root, old)
    with sqlite3.connect((root / 'generations' / old / 'search.sqlite').as_uri() + '?mode=ro', uri=True) as reader:
        reader.execute('BEGIN')
        assert reader.execute('select count(*) from units').fetchone()[0] == 12
        new = index.build_generation(root)
        index.activate_generation(root, new)
        assert reader.execute('select count(*) from units').fetchone()[0] == 12
        assert index.current_generation(root)['generation_id'] == new
    broken = root / 'generations' / old / 'search.sqlite'
    with broken.open('r+b') as stream:
        stream.seek(200)
        stream.write(b'broken')
    with pytest.raises(ValueError, match='HASH_MISMATCH'):
        index.activate_generation(root, old)
    assert index.current_generation(root)['generation_id'] == new


def test_budget_rejects_low_disk_and_high_memory(tmp_path, monkeypatch):
    import importlib.util
    assert importlib.util.find_spec('cn_contract.library.budget'), 'budget guard missing'
    budget = importlib.import_module('cn_contract.library.budget')
    monkeypatch.setattr(budget.shutil, 'disk_usage', lambda path: type('Usage', (), {'free': 1})())
    with pytest.raises(ValueError, match='DISK_BUDGET'):
        budget.check_budget(tmp_path, force=True)
    monkeypatch.setattr(budget.shutil, 'disk_usage', lambda path: type('Usage', (), {'free': 500 * 1024**3})())
    monkeypatch.setattr(budget, 'process_bytes', lambda: 9 * 1024**3)
    with pytest.raises(ValueError, match='MEMORY_BUDGET'):
        budget.check_budget(tmp_path, force=True)


def test_killed_index_resumes_with_same_rows(tmp_path):
    from cn_contract.library import index
    root = tmp_path / 'library'
    fixture(root, 3000)
    command = [sys.executable, '-X', 'utf8', '-m', 'cn_contract.library', 'build-index', '--library-root', str(root)]
    child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    observed, generation = 0, None
    try:
        deadline = time.monotonic() + 30
        while child.poll() is None and time.monotonic() < deadline:
            files = list((root / 'generations').glob('*/search.sqlite'))
            if files:
                generation = files[0].parent.name
                try:
                    with sqlite3.connect(files[0].as_uri() + '?mode=ro', uri=True, timeout=.1) as db:
                        observed = db.execute('select count(*) from units').fetchone()[0]
                except sqlite3.Error:
                    pass
            if 0 < observed < 3000:
                child.kill()
                break
            time.sleep(.02)
        child.communicate(timeout=30)
        assert 0 < observed < 3000, 'no committed intermediate batch observed'
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate()
    assert index.build_generation(root, resume=generation) == generation
    manifest = index.validate_generation(root, generation)
    assert manifest['coverage']['records'] == 3000
    with sqlite3.connect(root / 'generations' / generation / 'search.sqlite') as db:
        assert db.execute('select count(*),count(distinct unit_id) from units').fetchone() == (3000, 3000)
