"""Real child-process interruption and restart; all data are invented."""
import csv
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time


def test_kill_resume_exact_count(tmp_path):
    assert importlib.util.find_spec('cn_contract.library.__main__'), 'library CLI missing'
    original = tmp_path / '虚构.csv'
    count = 20000
    with original.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['案号', '文书内容'])
        writer.writerows([[str(i), '完全虚构的恢复测试正文' * 30] for i in range(count)])
    root = tmp_path / '资料 库'
    command = [sys.executable, '-X', 'utf8', '-m', 'cn_contract.library', 'import-cases',
               '--library-root', str(root), '--input', str(original), '--batch-id', 'fiction', '--batch-size', '100']
    child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    observed = 0
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and child.poll() is None:
            database = root / 'catalog.sqlite'
            if database.exists():
                try:
                    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
                        observed = db.execute('select count(*) from records').fetchone()[0]
                except sqlite3.Error:
                    pass
            if 0 < observed < count:
                child.kill()
                break
            time.sleep(.02)
        child.communicate(timeout=30)
        assert 0 < observed < count, 'did not observe an intermediate durable batch'
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate()
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=120)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report['stored'] == count and report['complete']
    with sqlite3.connect(root / 'catalog.sqlite') as db:
        assert db.execute('select count(distinct record_id),count(*) from records').fetchone() == (count, count)
        assert db.execute('select next_ordinal,state from import_states').fetchone() == (count + 1, 'complete')
        first = json.loads(db.execute('select record_json from records where ordinal=1').fetchone()[0])
        last = json.loads(db.execute('select record_json from records where ordinal=?', (count,)).fetchone()[0])
        assert first['fields']['case_no'] == '0'
        assert last['fields']['case_no'] == '19999'
