"""Build the exact pre-material model family in synthetic legacy fixtures."""
import sqlite3

from cn_contract.assistant import profile_model_schema, rounds_v2_schema
from .legacy_personal import downgrade_runtime_statements, downgrade_statements

_STATEMENTS = profile_model_schema.STATEMENTS[:7] + rounds_v2_schema.STATEMENTS[7:]


def downgrade_material_model(connection):
    """Revert only the test fixture's empty model family; never use in production."""
    if not isinstance(connection, sqlite3.Connection) or connection.in_transaction:
        raise ValueError('raw committed sqlite connection required')
    connection.execute('PRAGMA foreign_keys=OFF')
    try:
        connection.execute('BEGIN IMMEDIATE')
        try:
            for statement in (
                *downgrade_statements(connection.execute),
                *downgrade_runtime_statements(connection.execute),
                *_STATEMENTS
            ):
                connection.execute(statement)
            if connection.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('invalid synthetic legacy fixture')
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    finally:
        connection.execute('PRAGMA foreign_keys=ON')


def downgrade_material_model_session(session):
    """Same fixture rebuild inside an existing SQLAlchemy session without model rows."""
    from sqlalchemy import text
    session.execute(text('PRAGMA defer_foreign_keys=ON'))
    execute=lambda sql:session.execute(text(sql))
    for statement in (
        *downgrade_statements(execute),
        *downgrade_runtime_statements(execute),
        *_STATEMENTS
    ):
        session.execute(text(statement))
    if session.execute(text('PRAGMA foreign_key_check')).fetchall():
        raise ValueError('invalid synthetic legacy fixture')
