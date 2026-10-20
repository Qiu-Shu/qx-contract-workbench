"""Independent synthetic SQLite check of WorkBuddy's conditional review claims."""
import json
import sqlite3
from pathlib import Path
from cn_contract.assistant.library_schema import STATEMENTS, TABLES, expected_objects
from cn_contract.persistence import Database
from cn_contract.config import load_settings
from cn_contract.storage_schema import schema_rows

def objects(db):
    return [row for row in db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name') if row[2] in TABLES]

observed = []
for foreign_keys in (0, 1):
    with sqlite3.connect(':memory:') as db:
        db.execute(f'PRAGMA foreign_keys={foreign_keys}')
        # Build the actual frozen predecessor, then the new statements.
        for kind, name, table, sql in schema_rows('assistant-judge-v1'):
            if kind == 'table':
                db.execute(sql)
        for kind, name, table, sql in schema_rows('assistant-judge-v1'):
            if kind in ('index', 'trigger') and sql:
                db.execute(sql)
        for statement in STATEMENTS:
            db.execute(statement)
        observed.append(objects(db))
        assert objects(db) == expected_objects()
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        assert db.execute("PRAGMA table_info('assistant_run_events')").fetchall()[0][5] == 1
        assert db.execute("PRAGMA table_info('assistant_run_events')").fetchall()[1][5] == 2

database = Database('sqlite:///:memory:', Path('.local/library-ledger-20261020/workbuddy-synthetic-files'),
                    load_settings(), initialize_schema=False)
with database.engine.connect() as db:
    enabled = db.exec_driver_sql('PRAGMA foreign_keys').scalar_one()
assert enabled == 1
database.engine.dispose()
report = {'foreign_keys_modes': [0, 1], 'library_object_rows': len(observed[0]),
          'rows_equal_between_modes': observed[0] == observed[1],
          'rows_equal_expected_objects': True, 'foreign_key_check_empty_both_modes': True,
          'parent_composite_primary_key': ['run_id', 'seq'], 'application_foreign_keys': enabled,
          'scope': 'In-memory synthetic schema only; no source corpus or user workspace.'}
Path('.local/library-ledger-20261020/workbuddy-independent-check.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
print(json.dumps(report))
