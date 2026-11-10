"""Exact personal-source CHECK expansion and per-channel conversation identity."""
import sqlite3
from functools import cache

from ..task_drafts import schema as tasks
from . import schema as inbox

REQUIRES_FOREIGN_KEYS_OFF = True
TABLES = ('task_channel_bindings', 'weixin_accounts')


def _rebuild(table, statements):
    original = next(value for value in statements if value.startswith('CREATE TABLE '+table+' ('))
    expanded = original.replace("CHECK(channel='synthetic')", "CHECK(channel IN ('synthetic','weixin_personal'))") \
        .replace("CHECK(mode='synthetic')", "CHECK(mode IN ('synthetic','weixin_personal'))")
    if table == 'task_channel_bindings':
        expanded = expanded.replace('conversation_id TEXT NOT NULL UNIQUE REFERENCES',
            'conversation_id TEXT NOT NULL REFERENCES').replace('created_at TEXT NOT NULL)',
            'created_at TEXT NOT NULL, UNIQUE(conversation_id,channel))')
    with sqlite3.connect(':memory:') as db:
        for statement in statements:
            db.execute(statement)
        triggers = db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name=? ORDER BY name", (table,)).fetchall()
    temporary = table+'_personal'
    return (expanded.replace('CREATE TABLE '+table+' (', 'CREATE TABLE '+temporary+' ('),
        'INSERT INTO '+temporary+' SELECT * FROM '+table,
        *('DROP TRIGGER '+name for name,_ in triggers),
        'DROP TABLE '+table, 'ALTER TABLE '+temporary+' RENAME TO '+table,
        *(sql for _,sql in triggers))


STATEMENTS = _rebuild(TABLES[0], tasks.STATEMENTS) + _rebuild(TABLES[1], inbox.STATEMENTS)


@cache
def expected_tables():
    with sqlite3.connect(':memory:') as db:
        for statement in tasks.STATEMENTS + inbox.STATEMENTS + STATEMENTS:
            db.execute(statement)
        return db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE type='table' AND name IN (?,?) ORDER BY type,name", TABLES).fetchall()


def initialize_storage(database):
    from ..schema_migrations import upgrade_database
    raw = database.engine.raw_connection()
    try:
        upgrade_database(raw)
    finally:
        raw.close()
