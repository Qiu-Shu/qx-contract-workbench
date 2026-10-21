"""Database-only additive upgrades for fully verified, isolated restore copies."""
from .storage_schema import CURRENT_VERSION, VERSIONS, identify_schema, schema_rows


def database_rows(connection):
    return connection.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()


def statements_for(version):
    if version == 'intake-v1':
        from .intake.schema import STATEMENTS
    elif version == 'assistant-v1':
        from .assistant.schema import STATEMENTS
    elif version == 'assistant-attachments-v1':
        from .assistant.attachment_schema import STATEMENTS
    elif version == 'assistant-model-v1':
        from .assistant.model_schema import STATEMENTS
    elif version == 'assistant-judge-v1':
        from .assistant.judge_schema import STATEMENTS
    elif version == 'assistant-library-v1':
        from .assistant.library_schema import STATEMENTS
    elif version == 'assistant-context-v1':
        from .assistant.context_schema import STATEMENTS
    elif version == 'assistant-rounds-v1':
        from .assistant.rounds_schema import STATEMENTS
    else:
        raise ValueError('DATABASE_SCHEMA_MISMATCH')
    return STATEMENTS


def _module(version):
    if version == 'assistant-rounds-v1':
        from .assistant import rounds_schema
        return rounds_schema
    return None


def requires_foreign_keys_off(version):
    """Table-rebuild migrations DROP a referenced parent and need an FK OFF window."""
    module = _module(version)
    return bool(getattr(module, 'REQUIRES_FOREIGN_KEYS_OFF', False)) if module else False


def upgrade_database(connection):
    """Caller has already verified archive bytes/rows/references in staging.

    No caller transaction may be committed here. The entire missing chain is
    atomic, and no workspace marker, file, HTTP service or worker is accessed.
    """
    if connection.in_transaction:
        raise ValueError('MIGRATION_TRANSACTION_ACTIVE')
    before = database_rows(connection)
    native = any(row[1] == 'local_workspace_identity' for row in before)
    version = identify_schema(before, native=native)
    connection.execute('PRAGMA foreign_keys=ON')
    connection.execute('PRAGMA trusted_schema=OFF')
    if (connection.execute('PRAGMA quick_check').fetchall() != [('ok',)]
            or connection.execute('PRAGMA foreign_key_check').fetchall()):
        raise ValueError('DATABASE_INTEGRITY')
    if version == CURRENT_VERSION:
        return version
    targets = VERSIONS[VERSIONS.index(version) + 1:]
    # A table-rebuild migration DROPs a referenced parent table, which FK
    # enforcement rejects; open an explicit FK OFF window before BEGIN and
    # still run foreign_key_check before committing.
    fk_off = any(requires_foreign_keys_off(target) for target in targets)
    if fk_off:
        connection.execute('PRAGMA foreign_keys=OFF')
    try:
        connection.execute('BEGIN IMMEDIATE')
        try:
            if database_rows(connection) != before:
                raise ValueError('DATABASE_SCHEMA_MISMATCH')
            for target in targets:
                for statement in statements_for(target):
                    connection.execute(statement)
                if database_rows(connection) != schema_rows(target, native=native):
                    raise ValueError('DATABASE_SCHEMA_MISMATCH')
            if connection.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('DATABASE_INTEGRITY')
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    finally:
        if fk_off:
            connection.execute('PRAGMA foreign_keys=ON')
    return CURRENT_VERSION
