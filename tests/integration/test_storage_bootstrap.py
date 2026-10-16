"""Backup schema inspection must not compose the HTTP application."""
import subprocess
import sys
from pathlib import Path


def test_schema_reference_without_loading_application():
    root = Path(__file__).resolve().parents[2]
    code = '''
import hashlib, json, sys, sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0, sys.argv[1])
from cn_contract.config import load_settings
from cn_contract.ops.backup import schema_reference
from cn_contract.schema_baseline import INTAKE_V1_ROWS
from cn_contract.storage_schema import CURRENT_VERSION, schema_rows, normalized_schema
schema = schema_reference(load_settings())
assert schema == normalized_schema(CURRENT_VERSION)
old = normalized_schema('intake-v1')
digest = hashlib.sha256(json.dumps(old, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
# Measured from 0.4.1/intake-v1 before moving its initializer (7b58b92).
assert digest == 'cf9282bd4d8b60df107ba98a72c6c116435c3b553294ad135027e1f9e1bf26f4', digest
digest = hashlib.sha256(json.dumps(INTAKE_V1_ROWS, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
assert digest == '2c622bf427fb9ac8c93329862b0fb4acfc45cf7d07349e82800ee51090167ba0', digest
from cn_contract.persistence import Database
from cn_contract.storage_bootstrap import initialize_storage
with TemporaryDirectory() as temp:
    root = Path(temp)
    database = Database('sqlite:///'+str(root/'reference.db'), root/'files', load_settings())
    try:
        initialize_storage(database)
        with closing(sqlite3.connect(root/'reference.db')) as connection:
            rows = connection.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
        assert rows == schema_rows(CURRENT_VERSION)
    finally:
        database.engine.dispose()
assert 'cn_contract.web.app' not in sys.modules
assert 'cn_contract.web.services' not in sys.modules
assert 'pdfplumber' not in sys.modules
'''
    result = subprocess.run([sys.executable, '-I', '-c', code, str(root/'src')],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
