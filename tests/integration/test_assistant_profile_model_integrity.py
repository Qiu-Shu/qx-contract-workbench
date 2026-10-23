"""Profile model archives bind sources, saving receipts and the shared ledger."""
from contextlib import closing
import asyncio
import json
import sqlite3
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d, storage_schema
from cn_contract.assistant import profile_store, service
from cn_contract.assistant.model_integrity import validate_model_records
from cn_contract.assistant.providers import attempts, profile_codec
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.assistant.providers.policy import sha
from cn_contract.config import canonical_json as encoded, load_settings
from cn_contract.ops import backup, workspace_backup
from cn_contract.persistence import Database
from cn_contract.intake import service as intake
from cn_contract.security import revoke_session
from cn_contract.storage_bootstrap import initialize_storage
from tests.helpers.legacy_assistant_backup import PASSPHRASE
from tests.integration.test_assistant_attachment_backup import corrupt, source
from tests.integration.test_assistant_model_backup import reserved
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_main_provider import config, KEY
from tests.integration.test_assistant_profile_execution import profile_world, authorize, enqueue
from tests.unit.test_assistant_profile_codec import candidate as wire_candidate, response


def validate(database, allowed=True):
    with database.session() as db:
        validate_model_records(db, allowed=allowed)


@pytest.mark.parametrize('kind', ['response.ready', 'profile.saved', 'profile.blocked'])
@pytest.mark.parametrize('allowed', [False, True])
def test_profile_events_without_a_model_ledger_are_never_empty(world, kind, allowed):
    database, actor, conversation, request, _ = world
    with database.session() as db:
        run = service.save_message(actor, conversation.scope.conversation_id, request, db)
        db.execute(text('''INSERT INTO assistant_run_events
            (run_id,seq,event_type,audience,payload_json,created_at)
            VALUES (:run,2,:kind,'internal','{}',:at)'''),
            {'run': str(run.id), 'kind': kind, 'at': run.created_at.isoformat()})
    with pytest.raises(ValueError, match='^ASSISTANT_MODEL_INTEGRITY$'):
        validate(database, allowed=allowed)


@pytest.mark.parametrize('native', [False, True])
def test_empty_successor_runs_all_archive_validators(tmp_path, native):
    database = Database('sqlite:///'+str(tmp_path/'empty.db'), tmp_path/'protected', load_settings())
    try:
        initialize_storage(database)
        if native:
            with database.session() as db:
                db.execute(text('CREATE TABLE local_workspace_identity (id TEXT PRIMARY KEY NOT NULL)'))
        with database.session() as db:
            rows = [tuple(row) for row in db.execute(text('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))]
            assert storage_schema.identify_schema(rows, native=native) == 'assistant-profile-model-v1'
            assert backup._file_references(db) == []
            assert backup._file_references(db, allow_assistant=False) == []
    finally:
        database.engine.dispose()


@pytest.mark.parametrize('allowed', [False, True])
def test_profile_attempt_is_not_accepted_as_plain_history(world, allowed):
    database, *_ = world
    reserved(world)
    corrupt(database, 'assistant_model_attempts',
            "UPDATE assistant_model_attempts SET input_format='profile-text-v1'")
    with pytest.raises(ValueError, match='^ASSISTANT_MODEL'):
        validate(database, allowed=allowed)


@pytest.mark.parametrize('allowed', [False, True])
def test_handler_alone_cannot_escape_empty_ledger_guard(source, allowed):
    _, database, *_ = source
    # Deliberately hostile archive rows: SQLite files can arrive with FK checks
    # disabled. No attempt/output is present, so the empty-ledger fast path is tested.
    with closing(sqlite3.connect(database.engine.url.database)) as db:
        db.execute('''INSERT INTO assistant_profile_handlers
            (run_id,event_seq,handler_id,handler_version,attempt_id,output_id,
             conversation_id,outcome,reason_code,basis_sha256,created_at)
            VALUES ('missing-run',1,'profile.save','1','missing-attempt','missing-output',
                    'missing-conversation','blocked','save_failed',?,?)''',
            ('0'*64, '2026-01-01T00:00:00+00:00'))
        db.commit()
    with pytest.raises(ValueError, match='^ASSISTANT_MODEL_INTEGRITY$'):
        validate(database, allowed=allowed)


def test_profile_format_rejects_backup_and_authenticated_restore(world, tmp_path, monkeypatch):
    database, *_ = world
    reserved(world)
    corrupt(database, 'assistant_model_attempts',
            "UPDATE assistant_model_attempts SET input_format='profile-text-v1'")
    from pathlib import Path
    root = Path(database.engine.url.database).parent
    rejected = tmp_path/'must-not-publish.qxbak'
    with pytest.raises(ValueError, match='^ASSISTANT_MODEL_INTEGRITY$'):
        workspace_backup.create_workspace_backup(root, rejected, PASSPHRASE, data_parent=tmp_path)
    assert not rejected.exists()
    hostile = tmp_path/'synthetic-inactive-format.qxbak'
    with monkeypatch.context() as patch:
        patch.setattr(workspace_backup, '_file_references', lambda db: [])
        workspace_backup.create_workspace_backup(root, hostile, PASSPHRASE, data_parent=tmp_path)
    before = (root/'workbench.db').read_bytes()
    destination = tmp_path/'must-not-restore'
    with pytest.raises(ValueError, match='^ASSISTANT_MODEL_INTEGRITY$'):
        workspace_backup.restore_workspace_backup(hostile, destination, PASSPHRASE)
    assert not destination.exists() or not list(destination.iterdir())
    assert (root/'workbench.db').read_bytes() == before


def profile_history(profile_world, *, state='received', project_intake=True, empty=False):
    """Use the real ledger/codec/store, with an in-memory synthetic reply, no socket."""
    database, actor, _, _ = profile_world
    provider = DeepSeekProvider.for_synthetic_loopback(config(), lambda: KEY, 'http://127.0.0.1:1/chat/completions')
    async def scenario():
        _, runtime, _, _ = authorize(profile_world, provider, project_intake=project_intake)
        first = enqueue(profile_world, runtime, project_intake=project_intake)
        with database.session() as db:
            prepared = attempts._input(attempts._row(first.id, db))
            if state != 'reserved':
                token, prepared, _ = attempts.claim(actor, first.id, db, runtime)
                if state != 'sending':
                    body = {'text':'待核，没有新增字段。', 'citations':[], 'profile_changes':[]} if empty else wire_candidate()
                    if project_intake and not empty:
                        body['profile_changes'].append({'field':'consultation',
                            'value':{'kind':'text','value':prepared.request.content}, 'origin':'user_statement',
                            'quotes':[{'start':0, 'end':len(prepared.request.content), 'quote':prepared.request.content}]})
                    reply = (profile_codec.decode_response(response(prepared.request, body), prepared.request, provider.config, KEY)
                             if state == 'received' else d.MainProfileReply(state=state, error_code='PROVIDER_ERROR'))
                    attempts.settle(actor, first.id, token, reply, db, runtime)
            view = attempts.read_attempt(actor, first.id, db)
        return view, prepared, runtime
    return asyncio.run(scenario())


@pytest.mark.parametrize('state', ['reserved', 'sending', 'received', 'sent_unknown', 'failed_before_send'])
def test_profile_history_preserves_state_and_shared_cost_validation(profile_world, state):
    database, *_ = profile_world
    view, _, _ = profile_history(profile_world, state=state)
    assert view.state == state
    validate(database)
    with database.session() as db:
        assert backup._file_references(db) == []
    with pytest.raises(ValueError, match='ASSISTANT_MODELS_REQUIRE_QXBAK'):
        validate(database, allowed=False)


@pytest.mark.parametrize('outcome', ['unchanged', 'blocked'])
def test_profile_handler_without_profile_revision_is_still_complete(profile_world, monkeypatch, outcome):
    database, *_ = profile_world
    if outcome == 'blocked':
        def failed_save(*args):
            raise ValueError('synthetic save failure')
        monkeypatch.setattr(profile_store, '_commit', failed_save)
    view, _, _ = profile_history(profile_world, project_intake=False, empty=outcome == 'unchanged')
    assert view.output is not None
    validate(database)
    with database.session() as db:
        assert db.scalar(text('SELECT outcome FROM assistant_profile_handlers')) == outcome
        assert db.scalar(text('SELECT count(*) FROM assistant_profile_revisions')) == 0


@pytest.mark.parametrize('tamper', ['missing_handler', 'extra_event', 'ready_basis', 'result_sequence',
    'result_outcome', 'external_event', 'event_order', 'handler_basis', 'receipt_request',
    'receipt_actor', 'receipt_patch', 'profile_field', 'output_quote', 'output_old_message',
    'output_citation', 'output_document_origin', 'output_received_material', 'output_base'])
def test_profile_archive_rejects_rehashed_source_receipt_and_event_forgery(profile_world, tamper):
    database, *_ = profile_world
    profile_history(profile_world)
    validate(database)
    if tamper == 'missing_handler':
        corrupt(database, 'assistant_profile_handlers', 'DELETE FROM assistant_profile_handlers')
    elif tamper == 'extra_event':
        with database.session() as db:
            row = db.execute(text('SELECT * FROM assistant_run_events ORDER BY seq DESC LIMIT 1')).mappings().one()
            db.execute(text('''INSERT INTO assistant_run_events VALUES(:run,:seq,'profile.saved','internal','{}',:at)'''),
                {'run':row['run_id'], 'seq':row['seq']+1, 'at':row['created_at']})
    elif tamper in {'ready_basis', 'result_sequence', 'result_outcome', 'external_event', 'event_order'}:
        kind = 'response.ready' if tamper == 'ready_basis' else 'profile.saved'
        with database.session() as db:
            row = db.execute(text('SELECT * FROM assistant_run_events WHERE event_type=:kind'), {'kind':kind}).mappings().one()
        payload = json.loads(row['payload_json'])
        if tamper == 'ready_basis':
            payload['basis_sha256'] = '0'*64
        elif tamper == 'result_sequence':
            payload['event_seq'] += 1
        elif tamper == 'result_outcome':
            payload['outcome'] = 'unchanged'
        if tamper == 'external_event':
            corrupt(database, 'assistant_run_events', "UPDATE assistant_run_events SET audience='client' WHERE event_type=?", (kind,))
        elif tamper == 'event_order':
            corrupt(database, 'assistant_run_events', "UPDATE assistant_run_events SET event_type=CASE event_type WHEN 'response.ready' THEN 'profile.saved' WHEN 'profile.saved' THEN 'response.ready' ELSE event_type END")
        else:
            corrupt(database, 'assistant_run_events', 'UPDATE assistant_run_events SET payload_json=? WHERE event_type=?',
                    (encoded(payload), kind))
    elif tamper == 'handler_basis':
        corrupt(database, 'assistant_profile_handlers', 'UPDATE assistant_profile_handlers SET basis_sha256=?', ('0'*64,))
    elif tamper.startswith('receipt_'):
        with database.session() as db:
            row = db.execute(text('SELECT * FROM assistant_profile_receipts')).mappings().one()
        value = json.loads(row['request_json'])
        if tamper == 'receipt_request':
            value['request_id'] = str(uuid4())
        elif tamper == 'receipt_patch':
            value['patch']['changes'][0]['value']['value'] = '99000'
        if tamper == 'receipt_actor':
            corrupt(database, 'assistant_profile_receipts', 'UPDATE assistant_profile_receipts SET actor_id=?', (str(uuid4()),))
        else:
            raw = encoded(value)
            corrupt(database, 'assistant_profile_receipts', 'UPDATE assistant_profile_receipts SET request_id=?,request_json=?,request_sha256=?',
                    (value['request_id'], raw, sha(raw)))
    elif tamper == 'profile_field':
        with database.session() as db:
            value = json.loads(db.scalar(text('SELECT profile_json FROM assistant_profile_revisions')))
        value['fields'][0]['candidates'][0]['value']['value'] = '99000'
        raw = encoded(value)
        corrupt(database, 'assistant_profile_revisions', 'UPDATE assistant_profile_revisions SET profile_json=?,profile_sha256=?', (raw,sha(raw)))
    else:
        with database.session() as db:
            value = json.loads(db.scalar(text('SELECT output_json FROM assistant_model_outputs')))
        candidate = value['candidate']; patch = candidate['profile_patch']; change = patch['changes'][0]
        if tamper == 'output_quote':
            change['source_refs'][0].update(quote='甲称借款99000元',quote_sha256=sha('甲称借款99000元'))
        elif tamper == 'output_old_message':
            change['source_refs'][0]['message_id'] = str(uuid4())
        elif tamper == 'output_citation':
            candidate['citations'] = [{'message_id':change['source_refs'][0]['message_id'],'quote_sha256':change['source_refs'][0]['quote_sha256']}]
        elif tamper == 'output_document_origin':
            change['origin'] = 'document_statement'
        elif tamper == 'output_received_material':
            change.update(field='materials',value={'kind':'materials','value':[{'name':'虚构凭证','state':'received'}]})
        elif tamper == 'output_base':
            patch['base_profile_revision'] = 1
        corrupt(database, 'assistant_model_outputs', 'UPDATE assistant_model_outputs SET output_json=?', (encoded(value),))
    with pytest.raises(ValueError, match='^ASSISTANT_MODEL_INTEGRITY$'):
        validate(database)


def test_profile_receipt_without_adopted_output_cannot_be_a_partial_commit(profile_world):
    database, *_ = profile_world
    view, _, _ = profile_history(profile_world)
    corrupt(database, 'assistant_profile_handlers', 'DELETE FROM assistant_profile_handlers')
    corrupt(database, 'assistant_model_outputs', 'DELETE FROM assistant_model_outputs')
    corrupt(database, 'assistant_run_events', "DELETE FROM assistant_run_events WHERE event_type='response.ready' OR event_type LIKE 'profile.%'")
    with database.session() as db:
        payload = json.loads(db.scalar(text("SELECT payload_json FROM assistant_run_events WHERE event_type='model.finished'")))
        assert db.scalar(text('SELECT count(*) FROM assistant_profile_receipts')) == 1
    payload.update(state='failed', output_id=None)
    corrupt(database, 'assistant_run_events', "UPDATE assistant_run_events SET seq=4,payload_json=? WHERE event_type='model.finished'", (encoded(payload),))
    corrupt(database, 'assistant_runs', "UPDATE assistant_runs SET state='failed' WHERE id=?", (str(view.run_id),))
    with pytest.raises(ValueError, match='^ASSISTANT_MODEL_INTEGRITY$'):
        validate(database)


def test_profile_result_sequence_boolean_cannot_impersonate_receipt_one(profile_world):
    database, *_ = profile_world
    profile_history(profile_world)
    with database.session() as db:
        payload = json.loads(db.scalar(text("SELECT payload_json FROM assistant_run_events WHERE event_type='profile.saved'")))
    assert payload['profile_receipt_sequence'] == 1
    payload['profile_receipt_sequence'] = True
    corrupt(database, 'assistant_run_events', "UPDATE assistant_run_events SET payload_json=? WHERE event_type='profile.saved'", (encoded(payload),))
    with pytest.raises(ValueError, match='^ASSISTANT_MODEL_INTEGRITY$'):
        validate(database)


@pytest.mark.parametrize('later', ['edit_intake', 'convert_intake', 'revoke_session'])
def test_profile_history_remains_valid_after_legitimate_later_actions(profile_world, later):
    database, actor, _, _ = profile_world
    profile_history(profile_world)
    backup._mark_storage_flags(database)
    with database.session() as db:
        identifier = db.scalar(text('SELECT intake_id FROM assistant_profile_receipts'))
        assert identifier is not None
        from uuid import UUID
        record = intake.read(UUID(identifier), actor, db)
        if later == 'edit_intake':
            draft = d.IntakeDraft.model_validate(record.model_dump(include=set(d.IntakeDraft.model_fields)))
            intake.save(record.id, d.IntakeUpdateInput(expected_revision=record.revision,
                draft=draft.model_copy(update={'consultation':'后续律师核对修正的合成原话'})), actor, db)
        elif later == 'convert_intake':
            intake.convert(record.id, d.IntakeConvertInput(expected_revision=record.revision,
                matter=d.MatterCreateInput(title='合成转案',contract_type='unknown',review_mode='pre_sign',
                    position='party_a', objectives=('核对合成借款材料',))), actor, db)
        else:
            revoke_session(actor.session_id, db)
    validate(database)
    with database.session() as db:
        assert backup._file_references(db) == []


@pytest.mark.parametrize('tamper', ['source_hash', 'original_digest', 'basis_composer', 'base_profile',
    'target', 'request_id', 'wire', 'policy_calls', 'policy_extra_basis', 'mixed_format', 'fee'])
def test_profile_archive_checks_whole_basis_original_submission_and_common_ledger(profile_world, tamper):
    database, *_ = profile_world
    profile_history(profile_world)
    with database.session() as db:
        row = db.execute(text('SELECT * FROM assistant_model_attempts')).mappings().one()
    raw = json.loads(row['input_json'])
    if tamper == 'original_digest':
        corrupt(database, 'assistant_runs', 'UPDATE assistant_runs SET request_sha256=?', ('0'*64,))
    elif tamper.startswith('policy_'):
        policy = json.loads(row['policy_json'])
        if tamper == 'policy_calls':
            policy['max_calls'] = 2
        else:
            policy['allowed_content_sha256s'].append('0'*64)
        serialized = encoded(policy)
        corrupt(database, 'assistant_model_attempts', 'UPDATE assistant_model_attempts SET policy_json=?,policy_sha256=?',
                (serialized,sha(serialized)))
    elif tamper == 'mixed_format':
        corrupt(database, 'assistant_model_attempts', "UPDATE assistant_model_attempts SET input_format='plain-text-v1'")
    elif tamper == 'fee':
        with database.session() as db:
            value = json.loads(db.scalar(text('SELECT receipt_json FROM assistant_model_receipts')))
        value['estimated_cost_usd'] = '0'
        corrupt(database, 'assistant_model_receipts', 'UPDATE assistant_model_receipts SET receipt_json=?', (encoded(value),))
    else:
        if tamper == 'source_hash':
            raw['request']['source_sha256'] = raw['basis']['content_sha256'] = '0'*64
        elif tamper == 'basis_composer':
            raw['basis']['expected_composer_revision'] += 1; raw['composer_revision'] += 1
        elif tamper == 'base_profile':
            raw['request']['base_profile_revision'] = raw['basis']['base_profile_revision'] = 1
        elif tamper == 'target':
            raw['basis'].update(expected_intake_id=str(uuid4()), expected_intake_revision=1)
        elif tamper == 'request_id':
            raw['basis']['request_id'] = str(uuid4())
        elif tamper == 'wire':
            raw['wire_payload_json'] += ' '
            raw['basis']['wire_bytes'] = len(raw['wire_payload_json'].encode())
            raw['basis']['wire_sha256'] = sha(raw['wire_payload_json'])
        # Rehash the input and permission to prove relational checks, not a bare checksum.
        policy = json.loads(row['policy_json']); policy['allowed_content_sha256s'] = [sha(encoded(raw['basis']))]
        corrupt(database, 'assistant_model_attempts', '''UPDATE assistant_model_attempts
            SET input_json=?,request_sha256=?,policy_json=?,policy_sha256=?''',
            (encoded(raw),sha(raw['wire_payload_json']),encoded(policy),sha(encoded(policy))))
    with pytest.raises(ValueError, match='^ASSISTANT_MODEL_INTEGRITY$'):
        validate(database)
