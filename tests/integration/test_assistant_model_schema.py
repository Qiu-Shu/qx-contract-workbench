"""Synthetic model ledger upgrades retain historical sources and durable claims."""
from contextlib import closing
import hashlib
import importlib
import json
import sqlite3
from uuid import uuid4

import pytest

from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.schema_migrations import upgrade_database
from cn_contract.storage_schema import CURRENT_VERSION, identify_schema, schema_rows
from tests.integration.test_assistant_attachment_schema import assistant_database
from tests.integration.test_assistant_storage import workspace, conversation
from tests.integration.test_storage_schema_versions import rows


def test_model_schema_is_an_additive_version():
    assert CURRENT_VERSION == 'assistant-rounds-v1'
    old = set(schema_rows('assistant-attachments-v1'))
    assert old < set(schema_rows(CURRENT_VERSION))
    assert identify_schema(schema_rows(CURRENT_VERSION)) == CURRENT_VERSION


def attachment_database(path):
    from cn_contract.assistant_attachment_schema_baseline import ASSISTANT_ATTACHMENTS_V1_ROWS
    connection = assistant_database(path)
    for kind in ('table', 'index', 'trigger'):
        for row in ASSISTANT_ATTACHMENTS_V1_ROWS:
            if row[0] == kind and row[3] is not None:
                connection.execute(row[3])
    connection.commit()
    return connection


def test_frozen_attachments_baseline_ignores_future_initializer(tmp_path, monkeypatch):
    from cn_contract.assistant import attachment_schema
    from cn_contract.assistant_attachment_schema_baseline import ASSISTANT_ATTACHMENTS_V1_ROWS
    from cn_contract import storage_schema
    assert hashlib.sha256(json.dumps(ASSISTANT_ATTACHMENTS_V1_ROWS, ensure_ascii=False,
        separators=(',', ':')).encode()).hexdigest() == '846038e24febb7d58d1a3041b783e56ecc2d566193b541d7188b0fc111f7da69'
    with closing(attachment_database(tmp_path/'old.db')) as connection:
        original = rows(connection)
        assert identify_schema(original) == 'assistant-attachments-v1'
        before = connection.execute('SELECT * FROM users').fetchall()
        assert upgrade_database(connection) == CURRENT_VERSION
        assert set(original) < set(rows(connection))
        assert connection.execute('SELECT * FROM users').fetchall() == before
    try:
        monkeypatch.setattr(attachment_schema, 'expected_objects', lambda: [('table','not-historical','not-historical','bad')])
        importlib.reload(storage_schema)
        assert storage_schema.schema_rows('assistant-attachments-v1') == original
    finally:
        monkeypatch.undo()
        importlib.reload(storage_schema)


def test_model_step_failure_preserves_old_attachment_schema(tmp_path, monkeypatch):
    from cn_contract import schema_migrations
    with closing(attachment_database(tmp_path/'old.db')) as connection:
        original = rows(connection)
        actual = schema_migrations.statements_for
        monkeypatch.setattr(schema_migrations, 'statements_for', lambda target:
            (*actual(target), 'INVALID SQL') if target == 'assistant-model-v1' else actual(target))
        with pytest.raises(sqlite3.Error):
            upgrade_database(connection)
        assert rows(connection) == original
        assert not connection.in_transaction


@pytest.fixture
def ledger(workspace):
    from cn_contract.assistant.context_schema import initialize_storage as context
    from cn_contract.assistant.model_schema import initialize_storage
    from cn_contract.assistant.rounds_schema import initialize_storage as rounds
    database, actors, _, _ = workspace
    initialize_storage(database)
    context(database)
    rounds(database)
    value = conversation(workspace)
    with database.session() as db:
        run = service.save_message(actors['lawyer'], value.scope.conversation_id,
            d.AssistantMessageInput(request_id=uuid4(), expected_scope=value.scope,
                expected_composer_revision=0, content='独立合成模型账本测试'), db)
    with closing(sqlite3.connect(database.engine.url.database)) as connection:
        connection.execute('PRAGMA foreign_keys=ON')
        identifier = str(uuid4())
        connection.execute('''INSERT INTO assistant_model_attempts
            (id,run_id,conversation_id,policy_id,config_sha256,policy_sha256,request_sha256,
             input_json,config_json,policy_json,reserved_usd,created_at,state,claim_sha256,updated_at)
            VALUES (?,?,?,'synthetic-policy',?,?,?,'{}','{}','{}','0.000001',?, 'reserved',NULL,?)''',
            (identifier,str(run.id),str(value.scope.conversation_id),'1'*64,'2'*64,'3'*64,
             '2026-10-17T00:00:00Z','2026-10-17T00:00:00Z'))
        connection.execute('INSERT INTO assistant_model_receipts VALUES (?, ?, ?)',
            (identifier,'{"status":"unknown","cost_usd":null}','2026-10-17T00:00:00Z'))
        connection.execute('INSERT INTO assistant_model_outputs VALUES (?, ?, ?, ?, ?, ?, ?)',
            (str(uuid4()),identifier,str(value.scope.conversation_id),str(run.id),'{}',
             '{"synthetic":true}','2026-10-17T00:00:00Z'))
        connection.commit()
        yield connection


@pytest.mark.parametrize('field,value', [('input_json','{"changed":true}'),
    ('reserved_usd','0'), ('policy_id','different-policy'), ('run_id','other-run')])
def test_model_source_and_reserved_cost_are_immutable(ledger, field, value):
    before = ledger.execute('SELECT * FROM assistant_model_attempts').fetchall()
    with pytest.raises(sqlite3.IntegrityError, match='IMMUTABLE_RECORD'):
        ledger.execute('UPDATE assistant_model_attempts SET '+field+'=?', (value,))
    ledger.rollback()
    assert ledger.execute('SELECT * FROM assistant_model_attempts').fetchall() == before


def test_claim_is_once_only_but_state_can_be_recovered(ledger):
    ledger.execute("UPDATE assistant_model_attempts SET state='sending',claim_sha256=?,updated_at=?",
        ('4'*64,'2026-10-17T00:01:00Z'))
    ledger.commit()
    for claim in (None,'5'*64):
        with pytest.raises(sqlite3.IntegrityError, match='IMMUTABLE_RECORD'):
            ledger.execute('UPDATE assistant_model_attempts SET claim_sha256=?', (claim,))
        ledger.rollback()
    ledger.execute("UPDATE assistant_model_attempts SET state='sent_unknown',updated_at='2026-10-17T00:02:00Z'")
    ledger.commit()
    assert ledger.execute('SELECT state,claim_sha256,reserved_usd FROM assistant_model_attempts').fetchone() == (
        'sent_unknown','4'*64,'0.000001')


def test_reserved_without_claim_can_be_proven_unsent(ledger):
    ledger.execute("UPDATE assistant_model_attempts SET state='failed_before_send'")
    ledger.commit()
    assert ledger.execute('SELECT state,claim_sha256 FROM assistant_model_attempts').fetchone() == ('failed_before_send',None)


@pytest.mark.parametrize('table', ['assistant_model_attempts','assistant_model_receipts','assistant_model_outputs'])
def test_model_history_cannot_be_deleted(ledger, table):
    with pytest.raises(sqlite3.IntegrityError, match='IMMUTABLE_RECORD'):
        ledger.execute('DELETE FROM '+table)
    ledger.rollback()


@pytest.mark.parametrize('table', ['assistant_model_receipts','assistant_model_outputs'])
def test_model_receipts_and_outputs_are_append_only(ledger, table):
    with pytest.raises(sqlite3.IntegrityError, match='IMMUTABLE_RECORD'):
        ledger.execute('UPDATE '+table+" SET created_at='changed'")
    ledger.rollback()


def test_one_attempt_per_round_and_output_per_run(ledger):
    # assistant-rounds-v1: one attempt per (run, round_no); copying round 1
    # collides with the occupied round, and one output per run stays unique.
    for sql in (
        '''INSERT INTO assistant_model_attempts SELECT 'another-attempt',run_id,conversation_id,
            policy_id,config_sha256,policy_sha256,request_sha256,input_json,config_json,policy_json,
            reserved_usd,created_at,state,claim_sha256,updated_at,input_format,round_no
            FROM assistant_model_attempts''',
        "INSERT INTO assistant_model_receipts SELECT * FROM assistant_model_receipts",
        '''INSERT INTO assistant_model_outputs SELECT 'another-output',attempt_id,conversation_id,
            run_id,scope_json,output_json,created_at FROM assistant_model_outputs''',
    ):
        with pytest.raises(sqlite3.IntegrityError, match='UNIQUE'):
            ledger.execute(sql)
        ledger.rollback()


def test_partial_model_schema_is_rejected_without_healing(tmp_path):
    from cn_contract.assistant.model_schema import initialize_storage
    from cn_contract.config import load_settings
    from cn_contract.persistence import Database
    from cn_contract.storage_bootstrap import initialize_storage as initialize_all
    database = Database('sqlite:///'+str(tmp_path/'partial.db'), tmp_path/'protected', load_settings())
    try:
        initialize_all(database)
        with database.engine.begin() as connection:
            connection.exec_driver_sql('DROP TRIGGER immutable_assistant_model_receipts_update')
        with pytest.raises(ValueError, match='DATABASE_SCHEMA_MISMATCH'):
            initialize_storage(database)
        with database.engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE name='immutable_assistant_model_receipts_update'").first() is None
    finally:
        database.engine.dispose()
