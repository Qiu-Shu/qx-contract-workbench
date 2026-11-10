"""One exact CHECK expansion; no new tables, credentials or queue."""
import sqlite3
from . import profile_model_schema as previous, model_schema, context_schema, rounds_schema, rounds_v2_schema, profile_schema

REQUIRES_FOREIGN_KEYS_OFF = True
FAMILY_TABLES = previous.FAMILY_TABLES
STATEMENTS = tuple(statement.replace('assistant_model_attempts_profile', 'assistant_model_attempts_material')
    .replace("'profile-text-v1'))", "'profile-text-v1', 'material-business-v1'))")
    for statement in previous.STATEMENTS[:7]) + rounds_v2_schema.STATEMENTS[7:]


def expected_objects():
    with sqlite3.connect(':memory:') as db:
        for statement in (model_schema.STATEMENTS + context_schema.STATEMENTS + rounds_schema.STATEMENTS
                + rounds_v2_schema.STATEMENTS + profile_schema.STATEMENTS + previous.STATEMENTS + STATEMENTS):
            db.execute(statement)
        return previous._found(db)


def expected_model_objects():
    return [row for row in expected_objects() if row[2] in model_schema.TABLES]


def expected_context_objects():
    return [row for row in expected_objects() if row[2] in context_schema.FAMILY_TABLES]


def initialize_storage(database):
    raw = database.engine.raw_connection()
    try:
        found = previous._found(raw)
        expected = expected_objects()
        if found == expected:
            return
        if found != previous.expected_objects():
            raise ValueError('DATABASE_SCHEMA_MISMATCH')
        raw.execute('PRAGMA foreign_keys=OFF')
        try:
            raw.execute('BEGIN IMMEDIATE')
            try:
                if previous._found(raw) != found:
                    raise ValueError('DATABASE_SCHEMA_MISMATCH')
                for statement in STATEMENTS:
                    raw.execute(statement)
                if previous._found(raw) != expected or raw.execute('PRAGMA foreign_key_check').fetchall():
                    raise ValueError('DATABASE_SCHEMA_MISMATCH')
                raw.execute('COMMIT')
            except BaseException:
                raw.execute('ROLLBACK')
                raise
        finally:
            raw.execute('PRAGMA foreign_keys=ON')
    finally:
        raw.close()
