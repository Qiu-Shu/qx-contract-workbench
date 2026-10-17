"""Additive synthetic attachment schema without a case or intake placeholder."""
from contextlib import closing
import hashlib
import json
import sqlite3

import pytest

from cn_contract.assistant_schema_baseline import ASSISTANT_V1_ROWS
from cn_contract.schema_migrations import upgrade_database
from cn_contract.storage_schema import CURRENT_VERSION, identify_schema, schema_rows
from tests.integration.test_storage_schema_versions import old_database, rows


def assistant_database(path):
    connection = old_database(path)
    for kind in ('table', 'index', 'trigger'):
        for row in ASSISTANT_V1_ROWS:
            if row[0] == kind and row[3] is not None:
                connection.execute(row[3])
    connection.commit()
    return connection


def test_old_assistant_schema_is_frozen_and_upgrades_additively(tmp_path):
    # Measured from exact assistant-v1 sqlite_master rows at 00b106c.
    assert hashlib.sha256(json.dumps(ASSISTANT_V1_ROWS, ensure_ascii=False,
        separators=(',', ':')).encode()).hexdigest() == '1a02490d4fee36cd1337eb673a999433b6d5dd7f85cdffa852358cf5b9b39369'
    with closing(assistant_database(tmp_path/'old.db')) as connection:
        before = rows(connection)
        assert identify_schema(before) == 'assistant-v1'
        assert set(before) < set(schema_rows('assistant-attachments-v1'))
        assert upgrade_database(connection) == CURRENT_VERSION
        assert rows(connection) == schema_rows(CURRENT_VERSION)
        assert set(before).issubset(rows(connection))
        assert connection.execute('SELECT username FROM users').fetchone() == ('old-user',)
        assert not connection.execute('SELECT id FROM matters').fetchall()
        assert not connection.execute('SELECT id FROM intake_cases').fetchall()


def test_attachment_upgrade_failure_rolls_back_entire_isolated_chain(tmp_path, monkeypatch):
    from cn_contract import schema_migrations
    with closing(old_database(tmp_path/'old.db', 'pre-intake')) as connection:
        before = rows(connection)
        original = schema_migrations.statements_for
        monkeypatch.setattr(schema_migrations, 'statements_for', lambda target:
            (*original(target), 'INVALID SQL') if target == 'assistant-attachments-v1' else original(target))
        with pytest.raises(sqlite3.Error): upgrade_database(connection)
        assert rows(connection) == before
        assert not connection.in_transaction


@pytest.fixture
def attachment_database(tmp_path):
    with closing(assistant_database(tmp_path/'current.db')) as connection:
        upgrade_database(connection)
        for conversation_id in ('conversation-a', 'conversation-b'):
            connection.execute('''INSERT INTO assistant_conversations
                (id, workspace_id, owner_id, request_id, request_sha256, scope_kind, scope_ref,
                 binding_revision, input_revision, materials_revision, composer_revision,
                 projection_intake_id, display_title, draft_input, created_at, archived_at)
                VALUES (?, 'workspace', 'synthetic-user', ?, ?, 'conversation', NULL,
                        1, 0, 0, 0, NULL, '合成附件会话', '', '2026-10-17T00:00:00Z', NULL)''',
                (conversation_id, 'create-'+conversation_id, '0'*64))
        connection.execute('''INSERT INTO assistant_attachments VALUES
            ('attachment-a', 'conversation-a', 'workspace', 'synthetic-user', 'receive-a', ?,
             '合成.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
             1, ?, 'assistant/conversation-a/attachment-a/original.bin', '{}',
             'synthetic-user', '2026-10-17T00:00:00Z')''', ('0'*64, '1'*64))
        connection.execute('''INSERT INTO assistant_attachment_parses VALUES
            ('conversation-a', 'attachment-a', 1, 'parse-a', ?, 'synthetic-parser', NULL,
             'failed', NULL, NULL, 'SYNTHETIC_ERROR', 'synthetic-user', '2026-10-17T00:00:00Z')''', ('2'*64,))
        connection.execute('''INSERT INTO assistant_material_snapshots VALUES
            ('conversation-a', 1, 'upload', 'selection-a', ?, '[]',
             'synthetic-user', '2026-10-17T00:00:00Z')''', ('3'*64,))
        connection.commit()
        yield connection


@pytest.mark.parametrize('table', ['assistant_attachments', 'assistant_attachment_parses',
                                  'assistant_material_snapshots'])
@pytest.mark.parametrize('operation', ['UPDATE', 'DELETE'])
def test_historical_original_parse_and_material_selection_are_immutable(attachment_database, table, operation):
    connection = attachment_database
    before = connection.execute('SELECT * FROM '+table).fetchall()
    sql = ('UPDATE '+table+" SET created_at='changed'" if operation == 'UPDATE' else 'DELETE FROM '+table)
    with pytest.raises(sqlite3.IntegrityError, match='IMMUTABLE_RECORD'):
        connection.execute(sql)
    connection.rollback()
    assert connection.execute('SELECT * FROM '+table).fetchall() == before


def test_parse_cannot_point_to_another_conversations_attachment(attachment_database):
    connection = attachment_database
    with pytest.raises(sqlite3.IntegrityError, match='FOREIGN KEY'):
        connection.execute('''INSERT INTO assistant_attachment_parses VALUES
            ('conversation-b', 'attachment-a', 2, 'parse-b', ?, 'synthetic-parser', NULL,
             'failed', NULL, NULL, 'SYNTHETIC_ERROR', 'synthetic-user', '2026-10-17T00:00:00Z')''', ('4'*64,))
    connection.rollback()
    assert connection.execute('SELECT COUNT(*) FROM assistant_attachment_parses').fetchone() == (1,)


def test_request_receipts_and_parse_revisions_are_unique(attachment_database):
    connection = attachment_database
    for statement in (
        '''INSERT INTO assistant_attachments SELECT 'attachment-b', conversation_id, workspace_id,
            owner_id, request_id, request_sha256, original_name, mime, byte_size, sha256, storage_ref,
            policy_json, actor_id, created_at FROM assistant_attachments''',
        '''INSERT INTO assistant_attachment_parses SELECT conversation_id, attachment_id, 2,
            request_id, request_sha256, parser_version, baseline_view, reading_status, result_json,
            result_sha256, failure_code, actor_id, created_at FROM assistant_attachment_parses''',
        '''INSERT INTO assistant_material_snapshots SELECT conversation_id, 2, kind,
            request_id, request_sha256, items_json, actor_id, created_at FROM assistant_material_snapshots''',
    ):
        with pytest.raises(sqlite3.IntegrityError, match='UNIQUE'):
            connection.execute(statement)
        connection.rollback()


def test_partial_attachment_schema_is_rejected_without_automatic_repair(tmp_path):
    from cn_contract.assistant.attachment_schema import initialize_storage
    from cn_contract.config import load_settings
    from cn_contract.persistence import Database
    from cn_contract.storage_bootstrap import initialize_storage as initialize_all
    database = Database('sqlite:///'+str(tmp_path/'current.db'), tmp_path/'protected', load_settings())
    try:
        initialize_all(database)
        with database.engine.begin() as connection:
            connection.exec_driver_sql('DROP TRIGGER immutable_assistant_attachments_update')
        with pytest.raises(ValueError, match='DATABASE_SCHEMA_MISMATCH'):
            initialize_storage(database)
        with database.engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE name='immutable_assistant_attachments_update'").first() is None
    finally:
        database.engine.dispose()
