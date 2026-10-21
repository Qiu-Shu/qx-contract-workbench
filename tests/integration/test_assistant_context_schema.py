"""assistant-context-v1: additive in-place model migration with frozen history."""
from contextlib import closing
import hashlib
import json
import sqlite3
import subprocess
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import schema_migrations, storage_schema
from cn_contract.config import load_settings
from cn_contract.persistence import Database
from cn_contract.storage_bootstrap import initialize_storage
from tests.integration.test_assistant_judge_schema import old_db

PREVIOUS = ('pre-intake', 'intake-v1', 'assistant-v1', 'assistant-attachments-v1',
            'assistant-model-v1', 'assistant-judge-v1', 'assistant-library-v1')
# Frozen exact rows of every older version; the context slice must not move them.
HISTORICAL = {
    ('assistant-library-v1', False): 'd201f0f277b7f534aa9fb3e65212b7149fafc1047ccefbfabcbc15ca2156b22f',
    ('assistant-library-v1', True): '54549ca27bbcf6dd109a6b0419765c1a6091726d0edb63cf12e7b6bc8d3b615f',
}


def digest(rows):
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def test_context_is_current_and_keeps_every_older_version():
    assert storage_schema.CURRENT_VERSION == 'assistant-context-v1'
    assert storage_schema.VERSIONS == PREVIOUS + ('assistant-context-v1',)
    for version in PREVIOUS:
        for native in (False, True):
            rows = storage_schema.schema_rows(version, native=native)
            assert storage_schema.identify_schema(rows, native=native) == version


@pytest.mark.parametrize('native', [False, True])
def test_library_structure_is_frozen_against_future_initializer_changes(native):
    rows = storage_schema.schema_rows('assistant-library-v1', native=native)
    assert digest(rows) == HISTORICAL[('assistant-library-v1', native)]


def test_context_is_an_in_place_model_upgrade_from_library():
    previous = set(storage_schema.schema_rows('assistant-library-v1'))
    current = set(storage_schema.schema_rows('assistant-context-v1'))
    changed = {row[2] for row in current - previous} | {row[2] for row in previous - current}
    assert changed == {'assistant_model_attempts', 'assistant_model_input_citations'}
    added = {row[1] for row in current - previous}
    removed = {row[1] for row in previous - current}
    # The attempts table row itself is replaced by its migrated SQL.
    assert removed == {'immutable_assistant_model_input', 'assistant_model_attempts'}
    assert {'immutable_assistant_model_input', 'assistant_model_attempts',
            'assistant_model_input_citations'} <= added
    attempts = next(row for row in current if row[0] == 'table' and row[1] == 'assistant_model_attempts')
    assert 'input_format' in attempts[3] and 'library-context-v1' in attempts[3]
    for native in (False, True):
        rows = storage_schema.schema_rows('assistant-context-v1', native=native)
        assert storage_schema.identify_schema(rows, native=native) == 'assistant-context-v1'


@pytest.mark.parametrize('version', PREVIOUS)
@pytest.mark.parametrize('native', [False, True])
def test_all_historical_versions_upgrade_without_replacing_objects_or_rows(tmp_path, version, native):
    with closing(old_db(tmp_path/'old.db', version, native)) as db:
        db.execute("INSERT INTO users VALUES ('synthetic-user', 'old-user', 'not-a-real-password', '[]', 0)")
        db.commit()
        before = schema_migrations.database_rows(db)
        assert schema_migrations.upgrade_database(db) == 'assistant-context-v1'
        after = schema_migrations.database_rows(db)
        assert storage_schema.identify_schema(after, native=native) == 'assistant-context-v1'
        assert db.execute('SELECT username FROM users').fetchall() == [('old-user',)]
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        if version in ('assistant-model-v1', 'assistant-judge-v1', 'assistant-library-v1'):
            formats = db.execute('SELECT input_format FROM assistant_model_attempts').fetchall()
            assert all(value == ('plain-text-v1',) for value in formats)
        # Shared old objects keep their original SQL; only the model family changes.
        old_objects = {row[1]: row for row in before}
        for row in after:
            if row[1] in old_objects and row[2] not in ('assistant_model_attempts',):
                assert row == old_objects[row[1]]
        assert schema_migrations.upgrade_database(db) == 'assistant-context-v1'
        assert schema_migrations.database_rows(db) == after


@pytest.mark.parametrize('native', [False, True])
def test_context_step_failure_preserves_library_schema_and_records(tmp_path, monkeypatch, native):
    with closing(old_db(tmp_path/'old.db', 'assistant-library-v1', native)) as db:
        before = schema_migrations.database_rows(db)
        actual = schema_migrations.statements_for
        monkeypatch.setattr(schema_migrations, 'statements_for', lambda target:
            (*actual(target), 'INVALID SQL') if target == 'assistant-context-v1' else actual(target))
        with pytest.raises(sqlite3.Error):
            schema_migrations.upgrade_database(db)
        assert schema_migrations.database_rows(db) == before
        assert not db.in_transaction


@pytest.mark.parametrize('failure', ['alter', 'trigger', 'relation'])
def test_context_step_partial_failure_leaves_no_half_migration(tmp_path, monkeypatch, failure):
    from cn_contract.assistant import context_schema
    with closing(old_db(tmp_path/'old.db', 'assistant-library-v1', False)) as db:
        before = schema_migrations.database_rows(db)
        index = {'alter': 0, 'trigger': 2, 'relation': 3}[failure]
        actual = schema_migrations.statements_for
        def faulty(target):
            statements = actual(target)
            if target != 'assistant-context-v1':
                return statements
            return statements[:index] + ('INVALID SQL',) + statements[index + 1:]
        monkeypatch.setattr(schema_migrations, 'statements_for', faulty)
        with pytest.raises(sqlite3.Error):
            schema_migrations.upgrade_database(db)
        assert schema_migrations.database_rows(db) == before
        assert not db.in_transaction


@pytest.mark.parametrize('damage', ['trigger', 'table', 'extra_index', 'old_trigger', 'missing_trigger'])
def test_partial_or_modified_context_schema_is_not_repaired(tmp_path, damage):
    from cn_contract.assistant import context_schema, model_schema
    database = Database('sqlite:///'+str(tmp_path/'partial.db'), tmp_path/'protected', load_settings())
    try:
        initialize_storage(database)
        with database.engine.begin() as db:
            db.exec_driver_sql({
                'trigger': 'DROP TRIGGER immutable_assistant_model_input_citations_update',
                'table': 'DROP TABLE assistant_model_input_citations',
                'extra_index': 'CREATE INDEX unexpected_context_index ON assistant_model_input_citations(attempt_id)',
                'old_trigger': "DROP TRIGGER immutable_assistant_model_input",
                'missing_trigger': "DROP TRIGGER immutable_assistant_model_input",
            }[damage])
            if damage == 'old_trigger':
                db.exec_driver_sql('''CREATE TRIGGER immutable_assistant_model_input BEFORE UPDATE OF
                    id,run_id,conversation_id,policy_id,config_sha256,policy_sha256,request_sha256,
                    input_json,config_json,policy_json,reserved_usd,created_at
                    ON assistant_model_attempts BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END''')
            before = list(db.exec_driver_sql('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))
        # The context initializer owns the migrated family and rejects every damage.
        with pytest.raises(ValueError, match='DATABASE_SCHEMA_MISMATCH'):
            context_schema.initialize_storage(database)
        # The legacy model initializer only inspects its own three tables: pure
        # citation-table damage is invisible to it; any drift inside the migrated
        # model family (old or missing immutable-input trigger) is rejected.
        if damage in ('missing_trigger', 'old_trigger'):
            with pytest.raises(ValueError, match='DATABASE_SCHEMA_MISMATCH'):
                model_schema.initialize_storage(database)
        else:
            model_schema.initialize_storage(database)
        with database.engine.connect() as db:
            assert list(db.exec_driver_sql('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')) == before
    finally:
        database.engine.dispose()


def test_model_initializer_accepts_both_exact_known_structures(tmp_path):
    from cn_contract.assistant import model_schema
    database = Database('sqlite:///'+str(tmp_path/'fresh.db'), tmp_path/'protected', load_settings())
    try:
        initialize_storage(database)
        model_schema.initialize_storage(database)
        with closing(sqlite3.connect(database.engine.url.database)) as raw:
            rows = raw.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
        assert storage_schema.identify_schema(rows) == 'assistant-context-v1'
    finally:
        database.engine.dispose()
    # A positively identified legacy V1 model family is still accepted as-is.
    legacy = Database('sqlite:///'+str(tmp_path/'legacy.db'), tmp_path/'protected2', load_settings())
    try:
        with legacy.engine.begin() as db:
            from cn_contract.assistant.model_schema import STATEMENTS
            for statement in STATEMENTS:
                db.exec_driver_sql(statement)
        model_schema.initialize_storage(legacy)
    finally:
        legacy.engine.dispose()


@pytest.mark.parametrize('native', [False, True])
def test_fresh_bootstrap_matches_stepwise_upgrade(tmp_path, native):
    from cn_contract.assistant import context_schema
    fresh = Database('sqlite:///'+str(tmp_path/'fresh.db'), tmp_path/'fresh-files', load_settings())
    try:
        initialize_storage(fresh)
        with closing(sqlite3.connect(fresh.engine.url.database)) as raw:
            built = raw.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
    finally:
        fresh.engine.dispose()
    with closing(old_db(tmp_path/'old.db', 'assistant-library-v1', False)) as db:
        schema_migrations.upgrade_database(db)
        migrated = schema_migrations.database_rows(db)
    assert [tuple(row) for row in built] == [tuple(row) for row in migrated]
    assert [tuple(row) for row in migrated] == storage_schema.schema_rows('assistant-context-v1')


def _old_source(path):
    result = subprocess.run(['git', 'show', '0d53fdf:src/cn_contract/' + path],
        capture_output=True, text=True, encoding='utf-8')
    if result.returncode != 0:
        pytest.skip('baseline source unavailable')
    return result.stdout


@pytest.mark.parametrize('native', [False, True])
def test_frozen_baseline_code_rejects_context_structure(tmp_path, native):
    """The actual pre-context release must refuse the new structure, not relabel it."""
    database = Database('sqlite:///'+str(tmp_path/'fresh.db'), tmp_path/'protected', load_settings())
    try:
        initialize_storage(database)
        with closing(sqlite3.connect(database.engine.url.database)) as raw:
            rows = [tuple(row) for row in raw.execute(
                'SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')]
        before = (tmp_path/'fresh.db').read_bytes()
    finally:
        database.engine.dispose()
    module = type(storage_schema)('old_storage_schema')
    module.__dict__['__package__'] = 'cn_contract'
    exec(compile(_old_source('storage_schema.py'), 'old_storage_schema.py', 'exec'), module.__dict__)
    assert module.CURRENT_VERSION == 'assistant-library-v1'
    with pytest.raises(ValueError, match='DATABASE_SCHEMA_MISMATCH'):
        module.identify_schema(rows, native=native)
    old_model = type(storage_schema)('old_model_schema')
    old_model.__dict__['__package__'] = 'cn_contract.assistant'
    exec(compile(_old_source('assistant/model_schema.py'), 'old_model_schema.py', 'exec'), old_model.__dict__)
    reopened = Database('sqlite:///'+str(tmp_path/'fresh.db'), tmp_path/'protected', load_settings())
    try:
        with pytest.raises(ValueError, match='DATABASE_SCHEMA_MISMATCH'):
            old_model.initialize_storage(reopened)
    finally:
        reopened.engine.dispose()
    assert (tmp_path/'fresh.db').read_bytes() == before


@pytest.fixture
def context_workspace(tmp_path):
    from cn_contract.assistant import service
    from cn_contract.assistant.providers.policy import encoded, sha
    from cn_contract.config import canonical_json
    from cn_contract.security import authenticate, login, provision_user
    from cn_contract import domain as d
    database = Database('sqlite:///'+str(tmp_path/'synthetic.sqlite'), tmp_path/'protected', load_settings())
    initialize_storage(database)
    workspace_id = uuid4()
    with database.session() as db:
        db.execute(text('CREATE TABLE local_workspace_identity (id TEXT PRIMARY KEY NOT NULL)'))
        db.execute(text('INSERT INTO local_workspace_identity VALUES (:id)'), {'id': str(workspace_id)})
        provision_user('lawyer', 'only-fictional-password', {d.Role.HANDLING_LAWYER}, db)
        token, _ = login('lawyer', 'only-fictional-password', db)
        actor = authenticate(token, db)
        conversation = service.create_conversation(actor, d.AssistantConversationCreateInput(request_id=uuid4()), db)
        run = service.save_message(actor, conversation.scope.conversation_id, d.AssistantMessageInput(
            request_id=uuid4(), expected_scope=conversation.scope, expected_composer_revision=0,
            content='独立合成问题'), db)
        config = d.MainModelConfig(enabled=True, model='deepseek-flash', input_usd_per_million='0.3',
            output_usd_per_million='1.2', price_reference='synthetic-ceiling')
        policy = d.MainModelPolicy(policy_id=uuid4(), workspace_id=workspace_id, actor_id=actor.user_id,
            config_sha256=sha(encoded(config)), allowed_content_sha256s=(sha('独立合成问题'),),
            max_total_usd='1', max_calls=5, expires_at='2999-01-01T00:00:00Z')
        from cn_contract.assistant.providers.policy import prepare
        prepared = prepare(d.MainRequest(run_id=run.id, scope=run.scope, message_id=run.message_id,
            content='独立合成问题', source_sha256=sha('独立合成问题')), config)
        attempt = str(uuid4())
        at = service._at()
        db.execute(text('''INSERT INTO assistant_model_attempts
            (id,run_id,conversation_id,policy_id,config_sha256,policy_sha256,request_sha256,
             input_json,config_json,policy_json,reserved_usd,created_at,state,updated_at,input_format)
            VALUES(:id,:run,:cid,:policy,:config_sha,:policy_sha,:request_sha,:input,:config,:policy_json,
                   '0.00009',:at,'reserved',:at,'plain-text-v1')'''),
            {'id': attempt, 'run': str(run.id), 'cid': str(conversation.scope.conversation_id),
             'policy': str(policy.policy_id), 'config_sha': sha(encoded(config)),
             'policy_sha': sha(encoded(policy)), 'request_sha': sha(prepared.wire_payload_json),
             'input': encoded(prepared), 'config': encoded(config), 'policy_json': encoded(policy), 'at': at})
        citation = str(uuid4())
        receipt = str(uuid4())
        seq = db.scalar(text(
            'SELECT COALESCE(MAX(seq),0)+1 FROM assistant_run_events WHERE run_id=:id'), {'id': str(run.id)})
        db.execute(text(
            'INSERT INTO assistant_run_events VALUES (:run,:seq,:type,:aud,:payload,:at)'),
            {'run': str(run.id), 'seq': seq, 'type': 'tool.before', 'aud': 'internal',
             'payload': '{}', 'at': at})
        db.execute(text('''INSERT INTO assistant_handler_receipts
            (id,run_id,event_seq,handler_id,handler_version,payload_sha256,request_json,result_json,
             result_sha256,scope_json,created_at)
            VALUES(:id,:run,:seq,'legal_library.search','1',:psha,'{}','{}',:rsha,'{}',:at)'''),
            {'id': receipt, 'run': str(run.id), 'seq': seq, 'psha': '1'*64, 'rsha': '2'*64, 'at': at})
        db.execute(text('''INSERT INTO assistant_library_citations
            (id,receipt_id,ordinal,citation_json,citation_sha256,created_at)
            VALUES(:id,:receipt,0,'{}',:csha,:at)'''),
            {'id': citation, 'receipt': receipt, 'csha': '3'*64, 'at': at})
    yield database, attempt, citation
    database.engine.dispose()


def test_migrated_default_format_and_empty_relations(context_workspace):
    database, attempt, _ = context_workspace
    with database.session() as db:
        row = db.execute(text(
            'SELECT input_format FROM assistant_model_attempts WHERE id=:id'), {'id': attempt}).one()
        assert row == ('plain-text-v1',)
        assert db.scalar(text(
            'SELECT COUNT(*) FROM assistant_model_input_citations')) == 0


def test_input_format_is_immutable_and_constrained(context_workspace):
    database, attempt, _ = context_workspace
    with database.engine.connect() as raw:
        with pytest.raises(Exception, match='IMMUTABLE_RECORD'):
            raw.execute(text(
                "UPDATE assistant_model_attempts SET input_format='library-context-v1' WHERE id=:id"),
                {'id': attempt})
        raw.rollback()
        with pytest.raises(Exception, match='CHECK'):
            raw.execute(text('''INSERT INTO assistant_model_attempts
                (id,run_id,conversation_id,policy_id,config_sha256,policy_sha256,request_sha256,
                 input_json,config_json,policy_json,reserved_usd,created_at,state,updated_at,input_format)
                SELECT id||'-x',run_id,conversation_id,policy_id,config_sha256,policy_sha256,request_sha256,
                 input_json,config_json,policy_json,reserved_usd,created_at,state,updated_at,'unknown-format'
                 FROM assistant_model_attempts WHERE id=:id'''), {'id': attempt})
        raw.rollback()


def test_relation_constraints(context_workspace):
    database, attempt, citation = context_workspace
    with database.engine.connect() as raw:
        raw.execute(text('PRAGMA foreign_keys=ON'))
        def add(**changes):
            record = {'attempt': attempt, 'ordinal': 0, 'citation': citation, **changes}
            raw.execute(text('''INSERT INTO assistant_model_input_citations
                (attempt_id,ordinal,saved_citation_id) VALUES(:attempt,:ordinal,:citation)'''), record)
        add()
        raw.commit()
        for changes, match in [
            ({'ordinal': 0}, 'UNIQUE'), ({'ordinal': 1}, 'UNIQUE'),
            ({'ordinal': 1, 'citation': str(uuid4())}, 'FOREIGN KEY'),
            ({'ordinal': 1, 'attempt': str(uuid4())}, 'FOREIGN KEY'),
            ({'ordinal': -1}, 'CHECK'), ({'ordinal': 8}, 'CHECK')]:
            with pytest.raises(Exception, match=match):
                add(**changes)
            raw.rollback()
        with pytest.raises(Exception, match='IMMUTABLE_RECORD'):
            raw.execute(text('UPDATE assistant_model_input_citations SET ordinal=1'))
        raw.rollback()
        with pytest.raises(Exception, match='IMMUTABLE_RECORD'):
            raw.execute(text('DELETE FROM assistant_model_input_citations'))
        raw.rollback()
        assert raw.execute(text('SELECT COUNT(*) FROM assistant_model_input_citations')).one() == (1,)
