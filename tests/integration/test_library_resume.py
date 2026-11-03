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
    from tests.helpers.library_cli import child_command, child_env
    original = tmp_path / '虚构.csv'
    count = 20000
    with original.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['案号', '文书内容'])
        writer.writerows([[str(i), '完全虚构的恢复测试正文' * 30] for i in range(count)])
    root = tmp_path / '资料 库'
    command = child_command('import-cases', '--library-root', str(root), '--input', str(original),
                            '--batch-id', 'fiction', '--batch-size', '100')
    # The child does not inherit the pytest fixture: the launcher declares the
    # capacity this child measures, so durability does not depend on host free space.
    env = child_env()
    child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    observed = 0
    interrupted = False
    child_err = b''
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
                interrupted = True
                break
            time.sleep(.02)
        _, child_err = child.communicate(timeout=30)
        detail = 'child_rc=%s child_stderr=%r observed=%d' % (
            child.returncode, child_err.decode()[-400:], observed)
        assert interrupted, 'the import was never interrupted, so resume was not proven: ' + detail
        assert 0 < observed < count, 'did not observe an intermediate durable batch: ' + detail
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate()
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8',
                            timeout=180, env=env)
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
