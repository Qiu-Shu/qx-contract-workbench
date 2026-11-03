"""Derive a historical schema from the version contract, not from a hand list.

Several legacy fixtures want one thing: "this database is exactly version X", so
that the migration under test has a truthful starting point. That used to be
spelled as a hand-written `DROP TABLE ...` tuple per fixture, and the tuple
drifts silently. Two ways it drifted:

* `weixin-personal-v1` / `weixin-personal-runtime-v1` added
  `weixin_personal_runs` / `weixin_personal_outbox`, and five fixtures kept
  claiming to be `task-drafts-v1` / `weixin-inbox-v1` /
  `weixin-reauthorization-v1` while leaving twelve later objects in place.
* `assistant-knowledge-v1` rebuilt `assistant_handler_receipts` to admit
  `legal_knowledge.search`; fixtures that merely *kept* that table were left
  holding the newer DDL, which no hand list ever covered.

Either way the exact-equality assertion failed on the fixture, with a stack that
says nothing about the migration the test was written to check.

`rebuild_to_version` reads the target version's own object list out of the
contract and makes the database match it: objects the version never had are
dropped, objects whose DDL changed are rebuilt from the contract, missing ones
are created. Rows in a rebuilt table are carried across by column name, so a
fixture that downgrades a *populated* database keeps its data; if the historical
shape cannot hold the rows, the rebuild refuses instead of quietly emptying the
table.
"""
import contextlib
import sqlite3

from cn_contract import storage_schema
from cn_contract.schema_migrations import database_rows

_CREATE_ORDER = {'table': 0, 'index': 1, 'trigger': 2, 'view': 3}
_BACKUP = '__legacy_shape_backup'


def _columns(connection, table):
    return [row[1] for row in connection.execute('PRAGMA table_info("'+table+'")')]


def rebuild_database(database, version, **options):
    """`rebuild_to_version` for a `persistence.Database` whose session is closed.

    Several fixtures reach for a SQLAlchemy session to issue their DDL; a raw
    connection to the same file is easier to reason about for a whole-schema
    rewrite, and it keeps `schema_rows`' own comparison exact.
    """
    path = database.engine.url.database
    if not path or path == ':memory:':
        raise ValueError('file-backed database required')
    with contextlib.closing(sqlite3.connect(path)) as connection:
        return rebuild_to_version(connection, version, **options)


def rebuild_to_version(connection, version, *, allow_data_loss=False):
    """Make ``connection`` hold exactly the objects ``version`` defines.

    Returns ``{'dropped': [...], 'rebuilt': [...], 'created': [...],
    'rows_carried': {table: count}}`` so the caller can report what the
    downgrade actually did instead of trusting it.
    """
    if not isinstance(connection, sqlite3.Connection):
        raise ValueError('raw sqlite connection required')
    target = storage_schema.schema_rows(version, native=True)
    target_sql = {(row[0], row[1]): row[3] for row in target}
    owner = {row[:2]: row[2] for row in target}
    now_sql = {(row[0], row[1]): row[3] for row in database_rows(connection)}

    missing = [key for key in target_sql if key not in now_sql]
    changed = [key for key in target_sql if key in now_sql and now_sql[key] != target_sql[key]]
    extra = [key for key in now_sql if key not in target_sql]

    rebuilt = [name for kind, name in (*missing, *changed) if kind == 'table']
    # Dropping a table takes its own indexes and triggers with it, so every
    # target object hanging off a rebuilt table must be created again even
    # though its own DDL never changed.
    recreate = [key for key in target_sql
                if key in (*missing, *changed) or owner[key] in rebuilt]

    carried = {}
    for name in rebuilt:
        if not connection.execute('SELECT 1 FROM "'+name+'" LIMIT 1').fetchone():
            continue
        if allow_data_loss:
            continue
        old = tuple(_columns(connection, name))
        backup = _BACKUP+'_'+name
        connection.execute('DROP TABLE IF EXISTS "'+backup+'"')
        connection.execute('CREATE TABLE "'+backup+'" AS SELECT * FROM "'+name+'"')
        carried[name] = (old, connection.execute('SELECT COUNT(*) FROM "'+backup+'"').fetchone()[0])

    # Triggers and indexes first: an index hanging off a *surviving* table (a
    # later version's `weixin_dispatch_binding_cursor`) is not removed by
    # dropping a table, so it has to go explicitly.
    ordered = sorted(changed+extra, key=lambda key: (-_CREATE_ORDER.get(key[0], 9), key[1]))
    for kind, name in ordered:
        if name.startswith('sqlite_'):
            continue
        connection.execute('DROP '+kind.upper()+' IF EXISTS "'+name+'"')

    created = []
    for kind, name in sorted(recreate, key=lambda key: (_CREATE_ORDER.get(key[0], 9), key[1])):
        sql = target_sql[(kind, name)]
        if sql is None:
            continue
        connection.execute(sql)
        created.append((kind, name))

    rows_carried = {}
    for name, (old, count) in carried.items():
        backup = _BACKUP+'_'+name
        keep = [column for column in old if column in _columns(connection, name)]
        connection.execute('INSERT INTO "'+name+'"('+','.join('"'+c+'"' for c in keep)+') '
                           'SELECT '+','.join('"'+c+'"' for c in keep)+' FROM "'+backup+'"')
        moved = connection.execute('SELECT COUNT(*) FROM "'+name+'"').fetchone()[0]
        if moved != count:
            connection.rollback()
            raise ValueError('REBUILD_LOST_ROWS: '+name)
        connection.execute('DROP TABLE "'+backup+'"')
        rows_carried[name] = moved

    connection.commit()
    return {'dropped': ordered, 'rebuilt': rebuilt, 'created': created,
            'rows_carried': rows_carried}
