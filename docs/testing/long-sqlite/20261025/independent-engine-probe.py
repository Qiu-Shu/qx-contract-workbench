"""Synthetic SQLAlchemy URL/DBAPI filename boundary, not product changes."""
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from sqlalchemy import event, text
from sqlalchemy.engine import make_url

from cn_contract.config import load_settings
from cn_contract.ops.file_paths import filesystem_path
from cn_contract.persistence import Database


root = Path(__file__).resolve().parent/'independent-engine-data'
while len(str(root/'workbench.db')) < 310:
    root /= '独立合成engine' * 3
native = filesystem_path(root/'workbench.db')
native.parent.mkdir(parents=True, exist_ok=True)
if not native.exists():
    with closing(sqlite3.connect(native)) as connection:
        connection.execute('CREATE TABLE sentinel (value TEXT)')
        connection.execute("INSERT INTO sentinel VALUES ('synthetic only')")
        connection.commit()
before = sha256(native.read_bytes()).hexdigest()
results = {'raw_extended_url_database': make_url('sqlite:///'+str(native)).database,
           'escaped_extended_url_database': make_url('sqlite:///'+str(native).replace('?', '%3F')).database,
           'path_length': len(str(root/'workbench.db'))}
database = Database('sqlite:///'+str(root/'workbench.db'), root/'protected',
                    load_settings(), initialize_schema=False)


@event.listens_for(database.engine, 'do_connect')
def native_filename(dialect, connection_record, args, kwargs):
    args[0] = str(native)


try:
    with database.session() as session:
        results['rows'] = [tuple(row) for row in session.execute(text('SELECT value FROM sentinel'))]
        results['foreign_keys'] = session.execute(text('PRAGMA foreign_keys')).scalar()
        results['busy_timeout'] = session.execute(text('PRAGMA busy_timeout')).scalar()
    results['hash_stable'] = sha256(native.read_bytes()).hexdigest() == before
    results['portable_storage_root'] = str(database.storage_root)
finally:
    database.engine.dispose()
assert results['rows'] == [('synthetic only',)]
assert results['foreign_keys'] == 1 and results['busy_timeout'] == 15000
assert results['hash_stable'] and not results['portable_storage_root'].startswith('\\\\?\\')
(Path(__file__).resolve().parent/'independent-engine-probe.json').write_text(
    json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(results, ensure_ascii=False))
