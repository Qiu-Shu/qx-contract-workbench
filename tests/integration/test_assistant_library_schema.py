"""Fixed library receipts extend, but never relabel, historical databases."""
from contextlib import closing
import hashlib
import importlib
import json
import sqlite3
from uuid import uuid4

import pytest

from cn_contract import domain as d
from cn_contract import schema_migrations, storage_schema
from cn_contract.assistant import service
from cn_contract.config import load_settings
from cn_contract.persistence import Database
from cn_contract.storage_bootstrap import initialize_storage
from tests.integration.test_assistant_judge_schema import old_db
from tests.integration.test_assistant_storage import workspace, conversation

PREVIOUS = ('pre-intake', 'intake-v1', 'assistant-v1', 'assistant-attachments-v1',
            'assistant-model-v1', 'assistant-judge-v1')
HISTORICAL = {False: '6f32a34c5d9f9c5c25815dde728504bc90a7b6512b5ea54818bae294e767a688',
              True: '900c3e39df4c11686d70b89e7c7c50a13da051e7e00bed8a08ea8f734a47cfc4'}


def test_library_chain_upgrades_judge_to_current_with_exact_delta(tmp_path):
    with closing(old_db(tmp_path/'old.db', 'assistant-judge-v1', False)) as db:
        before = schema_migrations.database_rows(db)
        assert schema_migrations.upgrade_database(db) == storage_schema.CURRENT_VERSION
        after = schema_migrations.database_rows(db)
        # Library tables are additive; the context step replaces the model
        # family's attempts table and immutable-input trigger in place.
        assert {row[2] for row in set(after) - set(before)} == {
            'assistant_handler_receipts', 'assistant_library_citations',
            'assistant_model_input_citations', 'assistant_model_attempts',
            'assistant_profile_revisions', 'assistant_profile_receipts', 'assistant_profile_handlers',
            'task_channel_bindings', 'task_inbox_events', 'task_drafts',
            'task_draft_events', 'task_executions', 'task_media_resolutions',
            'weixin_accounts', 'weixin_peer_bindings', 'weixin_poll_receipts', 'weixin_inbox_descriptors',
            'weixin_dispatch_receipts', 'weixin_peer_scope_grants', 'weixin_peer_generations',
            'weixin_descriptor_generations', 'assistant_evidence_revisions', 'assistant_followup_revisions'}
        assert {row[1] for row in set(before) - set(after)} == {
            'assistant_model_attempts', 'immutable_assistant_model_input'}
        assert storage_schema.identify_schema(after) == storage_schema.CURRENT_VERSION
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []


@pytest.mark.parametrize('native', [False, True])
def test_judge_history_is_frozen_against_future_initializer_changes(monkeypatch, native):
    from cn_contract.assistant import judge_schema
    before = storage_schema.schema_rows('assistant-judge-v1', native=native)
    digest = hashlib.sha256(json.dumps(before, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    assert digest == HISTORICAL[native]
    try:
        monkeypatch.setattr(judge_schema, 'expected_objects', lambda: [('table', 'bad', 'bad', 'bad')])
        importlib.reload(storage_schema)
        assert storage_schema.schema_rows('assistant-judge-v1', native=native) == before
    finally:
        monkeypatch.undo()
        importlib.reload(storage_schema)


@pytest.mark.parametrize('version', PREVIOUS)
@pytest.mark.parametrize('native', [False, True])
def test_all_historical_versions_upgrade_without_replacing_objects_or_rows(tmp_path, version, native):
    with closing(old_db(tmp_path/'old.db', version, native)) as db:
        db.execute("INSERT INTO users VALUES ('synthetic-user', 'old-user', 'not-a-real-password', '[]', 0)")
        db.commit()
        before = schema_migrations.database_rows(db)
        assert schema_migrations.upgrade_database(db) == storage_schema.CURRENT_VERSION
        after = schema_migrations.database_rows(db)
        # Only the model family's in-place context migration replaces old objects.
        replaced = {row[1] for row in set(before) - set(after)}
        assert replaced <= {'assistant_model_attempts', 'immutable_assistant_model_input'}
        assert storage_schema.identify_schema(after, native=native) == storage_schema.CURRENT_VERSION
        assert db.execute('SELECT username FROM users').fetchall() == [('old-user',)]
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        assert schema_migrations.upgrade_database(db) == storage_schema.CURRENT_VERSION
        assert schema_migrations.database_rows(db) == after


@pytest.mark.parametrize('native', [False, True])
def test_library_step_failure_preserves_judge_schema_and_records(tmp_path, monkeypatch, native):
    with closing(old_db(tmp_path/'old.db', 'assistant-judge-v1', native)) as db:
        before = schema_migrations.database_rows(db)
        actual = schema_migrations.statements_for
        monkeypatch.setattr(schema_migrations, 'statements_for', lambda target:
            (*actual(target), 'INVALID SQL') if target == 'assistant-library-v1' else actual(target))
        with pytest.raises(sqlite3.Error):
            schema_migrations.upgrade_database(db)
        assert schema_migrations.database_rows(db) == before
        assert not db.in_transaction


@pytest.mark.parametrize('damage', ['trigger', 'table', 'extra_index'])
def test_partial_or_modified_library_schema_is_not_repaired(tmp_path, damage):
    from cn_contract.assistant import library_schema
    database = Database('sqlite:///'+str(tmp_path/'partial.db'), tmp_path/'protected', load_settings())
    try:
        initialize_storage(database)
        with database.engine.begin() as db:
            db.exec_driver_sql({
                'trigger': 'DROP TRIGGER immutable_assistant_handler_receipts_update',
                'table': 'DROP TABLE assistant_library_citations',
                'extra_index': 'CREATE INDEX unexpected_library_index ON assistant_library_citations(created_at)',
            }[damage])
            before = list(db.exec_driver_sql('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))
        with pytest.raises(ValueError, match='DATABASE_SCHEMA_MISMATCH'):
            library_schema.initialize_storage(database)
        with database.engine.connect() as db:
            assert list(db.exec_driver_sql('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')) == before
    finally:
        database.engine.dispose()


@pytest.fixture
def ledger(workspace):
    from cn_contract.assistant.library_schema import initialize_storage
    database, actors, _, _ = workspace
    initialize_storage(database)
    value = conversation(workspace)
    with database.session() as db:
        run = service.save_message(actors['lawyer'], value.scope.conversation_id,
            d.AssistantMessageInput(request_id=uuid4(), expected_scope=value.scope,
                expected_composer_revision=0, content='独立合成引用账本测试'), db)
    with closing(sqlite3.connect(database.engine.url.database)) as db:
        db.execute('PRAGMA foreign_keys=ON')
        seq = db.execute('SELECT MAX(seq) FROM assistant_run_events WHERE run_id=?', (str(run.id),)).fetchone()[0] + 1
        db.execute('INSERT INTO assistant_run_events VALUES (?,?,?,?,?,?)',
                   (str(run.id), seq, 'tool.before', 'internal', '{}', '2026-10-20T00:00:00Z'))
        receipt = dict(id=str(uuid4()), run_id=str(run.id), event_seq=seq,
            handler_id='legal_library.search', handler_version='1', payload_sha256='1'*64,
            request_json='{}', result_json='{}', result_sha256='2'*64, scope_json='{}',
            created_at='2026-10-20T00:00:00Z')
        citation = dict(id=str(uuid4()), receipt_id=receipt['id'], ordinal=0,
            citation_json='{}', citation_sha256='3'*64, created_at='2026-10-20T00:00:00Z')
        insert(db, 'assistant_handler_receipts', receipt)
        insert(db, 'assistant_library_citations', citation)
        db.commit()
        yield db, receipt, citation


def insert(db, table, record):
    db.execute('INSERT INTO '+table+' ('+','.join(record)+') VALUES ('+','.join('?' for _ in record)+')',
               tuple(record.values()))


@pytest.mark.parametrize('table,index', [('assistant_handler_receipts', 1), ('assistant_library_citations', 2)])
def test_history_rejects_update_to_any_field_and_deletion(ledger, table, index):
    db, *_ = ledger
    record = ledger[index]
    before = db.execute('SELECT * FROM '+table).fetchall()
    for field in record:
        with pytest.raises(sqlite3.IntegrityError, match='IMMUTABLE_RECORD'):
            db.execute('UPDATE '+table+' SET '+field+'=?', (record[field],))
        db.rollback()
    with pytest.raises(sqlite3.IntegrityError, match='IMMUTABLE_RECORD'):
        db.execute('DELETE FROM '+table)
    db.rollback()
    assert db.execute('SELECT * FROM '+table).fetchall() == before


@pytest.mark.parametrize('table,index', [('assistant_handler_receipts', 1), ('assistant_library_citations', 2)])
def test_every_ledger_field_is_required(ledger, table, index):
    db, *_ = ledger
    for field in ledger[index]:
        record = {**ledger[index], 'id':str(uuid4()), field:None}
        with pytest.raises(sqlite3.IntegrityError, match='NOT NULL'):
            insert(db, table, record)
        db.rollback()


@pytest.mark.parametrize('field,value', [('handler_id', 'shell.execute'), ('handler_version', '2'),
    ('event_seq', 0), ('event_seq', -1), ('request_json', 'x'*8193),
    ('scope_json', 'x'*4097), ('result_json', 'x'*262145)],
    ids=['unknown-handler', 'unknown-version', 'zero-event', 'negative-event',
         'oversize-request', 'oversize-scope', 'oversize-result'])
def test_receipt_rejects_unbounded_or_unknown_handler_inputs(ledger, field, value):
    db, receipt, _ = ledger
    with pytest.raises(sqlite3.IntegrityError, match='CHECK'):
        insert(db, 'assistant_handler_receipts', {**receipt, 'id':str(uuid4()), field:value})
    db.rollback()


@pytest.mark.parametrize('field,value', [('ordinal', -1), ('ordinal', 8), ('citation_json', 'x'*32769)],
                         ids=['negative-ordinal', 'overflow-ordinal', 'oversize-citation'])
def test_citation_rejects_out_of_bound_snapshot(ledger, field, value):
    db, _, citation = ledger
    with pytest.raises(sqlite3.IntegrityError, match='CHECK'):
        insert(db, 'assistant_library_citations', {**citation, 'id':str(uuid4()), field:value})
    db.rollback()


def test_receipt_event_and_citation_ordinal_are_unique(ledger):
    db, receipt, citation = ledger
    for table, record in (('assistant_handler_receipts', receipt), ('assistant_library_citations', citation)):
        with pytest.raises(sqlite3.IntegrityError, match='UNIQUE'):
            insert(db, table, {**record, 'id':str(uuid4())})
        db.rollback()


@pytest.mark.parametrize('field,value', [('run_id', 'missing-run'), ('event_seq', 999)])
def test_receipt_requires_its_existing_run_event(ledger, field, value):
    db, receipt, _ = ledger
    with pytest.raises(sqlite3.IntegrityError, match='FOREIGN KEY'):
        insert(db, 'assistant_handler_receipts', {**receipt, 'id':str(uuid4()), field:value})
    db.rollback()


def test_citation_requires_existing_receipt(ledger):
    db, _, citation = ledger
    with pytest.raises(sqlite3.IntegrityError, match='FOREIGN KEY'):
        insert(db, 'assistant_library_citations', {**citation, 'id':str(uuid4()), 'receipt_id':'missing-receipt'})
    db.rollback()
