"""Exercise the real DuckDB adapter in an explicitly supplied isolated runtime."""
import csv
import hashlib
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess

import pytest

PILOT_PYTHON = os.environ.get('QX_PILOT_PYTHON')
pytestmark = pytest.mark.skipif(not PILOT_PYTHON, reason='explicit isolated DuckDB test runtime required')


@pytest.mark.parametrize('mismatch', [False, True])
def test_pilot_readonly_mapping_or_explicit_mismatch(tmp_path, mismatch):
    assert importlib.util.find_spec('cn_contract.library.pilot'), 'pilot import adapter missing'
    module = importlib.import_module('cn_contract.library.pilot')
    incoming = tmp_path / 'input'
    incoming.mkdir()
    original = incoming / '虚构.csv'
    header = '案号,文书内容\r\n'.encode('utf-8')
    raw = '虚构号,完全虚构None正文\r\n'.encode('utf-8')
    original.write_bytes(header + raw)
    pilot = tmp_path / 'pilot'
    (pilot / 'data').mkdir(parents=True)
    database = pilot / 'data' / 'judgments.duckdb'
    values = ['a' * 64, str(original), 1, len(header), len(header) + len(raw),
              'b' * 64 if mismatch else hashlib.sha256(raw).hexdigest(),
              hashlib.sha256('完全虚构None正文'.encode('utf-8')).hexdigest()]
    script = '''import duckdb,sys,json
c=duckdb.connect(sys.argv[1])
c.execute("create table records(record_id varchar,source_file varchar,ordinal bigint,byte_start bigint,byte_end bigint,raw_sha256 varchar,body_sha256 varchar)")
c.execute("insert into records values (?,?,?,?,?,?,?)",json.loads(sys.argv[2]))
c.close()
'''
    made = subprocess.run([PILOT_PYTHON, '-X', 'utf8', '-c', script, str(database), json.dumps(values)], capture_output=True, timeout=30)
    assert made.returncode == 0, made.stderr.decode('utf-8')
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    root = tmp_path / 'library'
    result = module.import_pilot(root, pilot, incoming, python_executable=Path(PILOT_PYTHON))
    assert result['mapped'] == (0 if mismatch else 1)
    assert result['mismatched'] == (1 if mismatch else 0)
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    catalog = importlib.import_module('cn_contract.library.catalog')
    if not mismatch:
        record = catalog.get_record(root, 'a' * 64)
        assert record.fields['case_no'] == '虚构号'
        assert record.body_sha256 == values[-1]
        assert module.import_pilot(root, pilot, incoming, python_executable=Path(PILOT_PYTHON))['mapped'] == 1
        assert len(list(catalog.iter_records(root))) == 1
    else:
        assert len(list(catalog.iter_records(root))) == 0
        assert result['issues'][0]['reason'] == 'PILOT_BYTES_MISMATCH'
