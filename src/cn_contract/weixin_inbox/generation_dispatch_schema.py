"""One immutable delivery acknowledgement per synthetic target cursor slot."""
import sqlite3

from . import dispatch_schema


STATEMENTS = (
    'CREATE UNIQUE INDEX weixin_dispatch_binding_cursor ON weixin_dispatch_receipts(task_binding_id,expected_task_cursor)',
)


def expected_objects():
    with sqlite3.connect(':memory:') as connection:
        for statement in (*dispatch_schema.STATEMENTS, *STATEMENTS):
            connection.execute(statement)
        return connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_master "
            "WHERE name='weixin_dispatch_binding_cursor' ORDER BY type,name").fetchall()


def expected_dispatch_objects():
    return sorted(dispatch_schema.expected_objects()+expected_objects(), key=lambda row:(row[0],row[1]))


def initialize_storage(database):
    with database.engine.begin() as connection:
        found = [tuple(row) for row in connection.exec_driver_sql(
            "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE tbl_name='weixin_dispatch_receipts' ORDER BY type,name")]
        if found == expected_dispatch_objects():
            return
        if found != dispatch_schema.expected_objects():
            raise ValueError('DATABASE_SCHEMA_MISMATCH')
        for statement in STATEMENTS:
            connection.exec_driver_sql(statement)
