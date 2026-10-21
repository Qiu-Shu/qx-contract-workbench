"""Synthetic model archives preserve provenance and never resume outbound work."""
import asyncio
from contextlib import closing
from decimal import Context, Inexact, localcontext
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import attachments, service
from cn_contract.assistant.providers import attempts
from cn_contract.assistant.providers.policy import encoded, sha
from cn_contract.assistant.runner import execute_attempt
from cn_contract.config import canonical_json
from cn_contract.ops import backup, workspace_backup
from cn_contract.persistence import Database
from cn_contract.security import authenticate, login, ServiceError
from cn_contract.web import local_server
from tests.helpers.legacy_assistant_backup import PASSPHRASE, write_old_cnbak
from tests.helpers.synthetic_operations import keys
from tests.integration.test_assistant_attachment_backup import corrupt
from tests.integration.test_assistant_generation import world


def reserved(world):
    database, actor, conversation, request, runtime = world
    with database.session() as db:
        return attempts.enqueue_generation(actor, conversation.scope.conversation_id, request, db, runtime)


def test_native_references_reject_changed_model_wire_digest(world):
    database, *_ = world
    reserved(world)
    corrupt(database, 'assistant_model_attempts', "UPDATE assistant_model_attempts SET request_sha256=?", ('0'*64,))
    with database.session() as db, pytest.raises(ValueError, match='ASSISTANT_MODEL'):
        backup._file_references(db)


@pytest.mark.parametrize('event_kind', ['model_events', 'message_event'])
def test_model_archive_rejects_noncontiguous_run_events(world, tmp_path, monkeypatch, event_kind):
    database, actor, _, _, runtime = world
    first = reserved(world)
    asyncio.run(execute_attempt(actor, first.id, database, runtime))
    selector = "event_type LIKE 'model.%'" if event_kind == 'model_events' else "event_type='message.accepted'"
    corrupt(database, 'assistant_run_events', f'UPDATE assistant_run_events SET seq=seq+100 WHERE {selector}')
    with database.session() as db, pytest.raises(ValueError, match='ASSISTANT_MODEL'):
        backup._file_references(db)
    root = Path(database.engine.url.database).parent
    rejected = tmp_path/'rejected-sequence.qxbak'
    with pytest.raises(ValueError, match='ASSISTANT_MODEL'):
        workspace_backup.create_workspace_backup(root, rejected, PASSPHRASE, data_parent=tmp_path)
    assert not rejected.exists()
    # Independently exercise restoration with authenticated hostile fixture data.
    hostile = tmp_path/'authenticated-invalid-sequence.qxbak'
    with monkeypatch.context() as patch:
        patch.setattr(workspace_backup, '_file_references', lambda db: [])
        workspace_backup.create_workspace_backup(root, hostile, PASSPHRASE, data_parent=tmp_path)
    before = (root/'workbench.db').read_bytes()
    destination = tmp_path/'must-not-restore-events'
    with pytest.raises(ValueError, match='ASSISTANT_MODEL'):
        workspace_backup.restore_workspace_backup(hostile, destination, PASSPHRASE)
    assert not destination.exists() or not list(destination.iterdir())
    assert (root/'workbench.db').read_bytes() == before
    assert len(runtime.provider.calls) == 1


@pytest.mark.parametrize('state', ['reserved', 'sending', 'received', 'sent_unknown', 'failed_before_send'])
def test_native_model_roundtrip_preserves_history_without_network(world, tmp_path, state):
    database, actor, conversation, request, runtime = world
    first = reserved(world)
    if state == 'received':
        first = asyncio.run(execute_attempt(actor, first.id, database, runtime))
    elif state != 'reserved':
        with database.session() as db:
            token, _, _ = attempts.claim(actor, first.id, db, runtime)
        if state != 'sending':
            with database.session() as db:
                attempts.settle(actor, first.id, token, d.MainReply(state=state, error_code='PROVIDER_ERROR'), db, runtime)
    with database.session() as db:
        before = dict(db.execute(text('SELECT * FROM assistant_model_attempts')).mappings().one())
    root = Path(database.engine.url.database).parent
    with local_server._worker_lock(root):
        pass
    original = (root/'workbench.db').read_bytes()
    archive = tmp_path/'synthetic-model.qxbak'
    workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
    result = workspace_backup.restore_workspace_backup(archive, tmp_path/'restored', PASSPHRASE)
    target = Path(result['restored_root'])
    restored = Database('sqlite:///'+str(target/'workbench.db'), target/'protected', database.settings, initialize_schema=False)
    backup._mark_storage_flags(restored)
    try:
        with restored.session() as db:
            token, _ = login('lawyer', 'fixture123', db)
            current = authenticate(token, db)
            view = attempts.read_attempt(current, first.id, db)
            expected = {'reserved':'failed_before_send', 'sending':'sent_unknown'}.get(state, state)
            assert view.state == expected and view.reserved_usd == first.reserved_usd
            assert view.receipt.cost_status == ('not_sent' if expected == 'failed_before_send' else
                                               'estimated' if expected == 'received' else 'unknown')
            after = dict(db.execute(text('SELECT * FROM assistant_model_attempts')).mappings().one())
            for key in before.keys()-{'state','updated_at'}:
                assert before[key] == after[key]
            if state in {'reserved','sending'}:
                assert service.get_run(current, first.run_id, db).state == 'interrupted'
                assert attempts.recover_attempts(db) == 0
            if state == 'received':
                assert view.output == first.output
                assert view.output.review_status == 'unverified' and view.output.audience == 'internal'
            else:
                assert view.output is None
            assert backup._file_references(db) == []
            events = service.read_events(current, first.run_id, db, after_seq=1)
            assert [event.seq for event in events.events] == list(range(2, len(events.events)+2))
        calls = len(runtime.provider.calls)
        with pytest.raises(ServiceError) as blocked:
            asyncio.run(execute_attempt(current, first.id, restored, runtime))
        assert blocked.value.code == 'BLOCKED_LIVE'
        assert len(runtime.provider.calls) == calls
        again = tmp_path/'model-again.qxbak'
        workspace_backup.create_workspace_backup(target, again, PASSPHRASE, data_parent=tmp_path)
        workspace_backup.restore_workspace_backup(again, tmp_path/'again', PASSPHRASE)
    finally:
        restored.engine.dispose()
    assert (root/'workbench.db').read_bytes() == original


def test_cnbak_explicitly_refuses_model_records(world):
    database, *_ = world
    reserved(world)
    with database.session() as db, pytest.raises(ValueError, match='ASSISTANT_MODELS_REQUIRE_QXBAK'):
        backup._file_references(db, allow_assistant=False)


def test_model_history_survives_current_session_revocation(world):
    database, actor, *_ = world
    first = reserved(world)
    runtime = world[-1]
    asyncio.run(execute_attempt(actor, first.id, database, runtime))
    with database.session() as db:
        db.execute(text('UPDATE sessions SET revoked=1'))
        db.execute(text('UPDATE users SET disabled=1'))
        assert backup._file_references(db) == []


def test_archive_cost_check_ignores_callers_decimal_context(world):
    database, actor, _, _, runtime = world
    first = reserved(world)
    asyncio.run(execute_attempt(actor, first.id, database, runtime))
    with localcontext(Context(prec=1, traps=[Inexact])), database.session() as db:
        assert backup._file_references(db) == []


@pytest.mark.parametrize('reason', ['cancelled', 'scope_changed'])
def test_unsent_terminal_history_is_valid_without_a_claim(world, reason):
    database, actor, conversation, _, runtime = world
    first = reserved(world)
    if reason == 'cancelled':
        with database.session() as db:
            service.cancel_run(actor, first.run_id, d.AssistantCancelInput(request_id=uuid4()), db)
    else:
        current = attachments.read_materials(actor, conversation.scope.conversation_id, database=database)
        attachments.select_materials(actor, conversation.scope.conversation_id,
            d.AssistantMaterialSelectionInput(request_id=uuid4(), expected_scope=current.scope, items=()), database=database)
        asyncio.run(execute_attempt(actor, first.id, database, runtime))
    with database.session() as db:
        view = attempts.read_attempt(actor, first.id, db)
        assert view.state == 'failed_before_send' and view.receipt.cost_status == 'not_sent'
        assert db.scalar(text('SELECT claim_sha256 FROM assistant_model_attempts')) is None
        assert backup._file_references(db) == []
    assert runtime.provider.calls == []


def test_received_unknown_usage_and_older_scope_remain_valid(world):
    database, actor, conversation, _, runtime = world
    first = reserved(world)
    with database.session() as db:
        token, prepared, _ = attempts.claim(actor, first.id, db, runtime)
        attempts.settle(actor, first.id, token, d.MainReply(state='received', output=d.MainCandidate(
            text='合成待核候选，用量未收到。', citations=(d.MainCitation(message_id=prepared.request.message_id,
                quote_sha256=prepared.request.source_sha256),))), db, runtime)
        current = service.read_conversation(actor, conversation.scope.conversation_id, db)
        service.save_message(actor, conversation.scope.conversation_id,
            d.AssistantMessageInput(request_id=uuid4(), expected_scope=current.scope,
                expected_composer_revision=current.composer_revision, content='第二轮独立合成草稿'), db)
        view = attempts.read_attempt(actor, first.id, db)
        assert view.receipt.cost_status == 'unknown' and view.receipt.estimated_cost_usd is None
        assert view.output.scope.input_revision < service.read_conversation(actor, conversation.scope.conversation_id, db).scope.input_revision
        assert backup._file_references(db) == []


def test_real_over_budget_receipt_is_preserved_without_adopting_output(world, tmp_path):
    database, actor, _, _, runtime = world
    runtime.policy = d.MainModelPolicy.model_validate(
        {**runtime.policy.model_dump(mode='json'), 'max_total_usd':'0.1'})
    first = reserved(world)
    with database.session() as db:
        token, _, _ = attempts.claim(actor, first.id, db, runtime)
        attempts.settle(actor, first.id, token, d.MainReply(state='received',
            usage=d.MainUsage(prompt_tokens=1000000,completion_tokens=0,total_tokens=1000000),
            error_code='MODEL_OUTPUT_INVALID'), db, runtime)
        view = attempts.read_attempt(actor, first.id, db)
        assert view.receipt.estimated_cost_usd > runtime.policy.max_total_usd
        assert view.output is None and backup._file_references(db) == []
    archive = tmp_path/'actual-overage.qxbak'
    workspace_backup.create_workspace_backup(Path(database.engine.url.database).parent, archive, PASSPHRASE, data_parent=tmp_path)
    result = workspace_backup.restore_workspace_backup(archive, tmp_path/'overage-restored', PASSPHRASE)
    root = Path(result['restored_root'])
    restored = Database('sqlite:///'+str(root/'workbench.db'),root/'protected',database.settings,initialize_schema=False)
    backup._mark_storage_flags(restored)
    try:
        with restored.session() as db:
            token, _ = login('lawyer','fixture123',db)
            current = authenticate(token,db)
            assert attempts.read_attempt(current,first.id,db) == view
            assert backup._file_references(db) == []
    finally:
        restored.engine.dispose()


def test_missing_model_ledger_cannot_be_treated_as_empty(world):
    database, *_ = world
    reserved(world)
    corrupt(database, 'assistant_model_attempts', 'DELETE FROM assistant_model_attempts')
    with database.session() as db, pytest.raises(ValueError, match='ASSISTANT_MODEL'):
        backup._file_references(db)


@pytest.mark.parametrize('native', [True, False])
def test_restore_rejects_authenticated_but_inconsistent_model_archive(world, tmp_path, monkeypatch, native):
    database, *_ = world
    reserved(world)
    source = Path(database.engine.url.database)
    before = source.read_bytes()
    archive = tmp_path/('bad-model.qxbak' if native else 'bad-model.cnbak')
    if native:
        corrupt(database, 'assistant_model_attempts', 'UPDATE assistant_model_attempts SET request_sha256=?', ('0'*64,))
        before = source.read_bytes()
        # Construct an authenticated hostile fixture while bypassing validation
        # only during fixture assembly; restoration uses the real trust boundary.
        with monkeypatch.context() as patch:
            patch.setattr(workspace_backup, '_file_references', lambda db: [])
            workspace_backup.create_workspace_backup(source.parent, archive, PASSPHRASE, data_parent=tmp_path)
    else:
        candidate = tmp_path/'nonnative-model.db'
        with closing(sqlite3.connect(source)) as original, closing(sqlite3.connect(candidate)) as copied:
            original.backup(copied)
            copied.execute('DROP TABLE local_workspace_identity')
            copied.commit()
        nonnative = Database('sqlite:///'+str(candidate), tmp_path/'nonnative-files', database.settings, initialize_schema=False)
        try:
            with monkeypatch.context() as patch:
                patch.setattr(backup, '_collect_files', lambda db: ({}, []))
                write_old_cnbak(nonnative, archive)
        finally:
            nonnative.engine.dispose()
    archive_before = archive.read_bytes()
    destination = tmp_path/'must-not-publish'
    with pytest.raises(ValueError, match='ASSISTANT_MODEL'):
        if native:
            workspace_backup.restore_workspace_backup(archive, destination, PASSPHRASE)
        else:
            backup.restore_backup(archive, key_resolver=keys(), restore_parent=destination, settings=database.settings)
    assert not destination.exists() or not list(destination.iterdir())
    assert archive.read_bytes() == archive_before and source.read_bytes() == before


@pytest.mark.parametrize('fault', [
    'actor_session', 'source_content', 'source_revision', 'message_conversation',
    'scope_workspace', 'scope_revision', 'scope_materials', 'policy_actor', 'policy_expired',
    'policy_source', 'policy_config', 'config_protocol', 'config_digest', 'policy_digest',
    'wire_template', 'wire_source', 'wire_duplicate_key', 'reserved_budget', 'selected_model',
    'claim_missing', 'receipt_missing', 'receipt_state', 'receipt_cost', 'receipt_unknown_zero',
    'receipt_usage_bool', 'receipt_usage_cap', 'receipt_extra_body', 'receipt_time',
    'output_owner', 'output_scope', 'output_quote', 'output_status', 'output_time',
    'input_duplicate_key', 'event_false_unsent', 'event_client',
])
def test_native_backup_rejects_model_provenance_corruption(world, tmp_path, fault):
    database, actor, conversation, request, runtime = world
    first = reserved(world)
    completed = asyncio.run(execute_attempt(actor, first.id, database, runtime))
    with database.session() as db:
        attempt = dict(db.execute(text('SELECT * FROM assistant_model_attempts')).mappings().one())
        output = dict(db.execute(text('SELECT * FROM assistant_model_outputs')).mappings().one())
        receipt = dict(db.execute(text('SELECT * FROM assistant_model_receipts')).mappings().one())
    table, field = 'assistant_model_attempts', None
    prepared, config, policy = (json.loads(attempt[key]) for key in ('input_json','config_json','policy_json'))
    reply, view = json.loads(receipt['receipt_json']), json.loads(output['output_json'])
    if fault == 'actor_session':
        corrupt(database, 'sessions', 'UPDATE sessions SET user_id=?', (str(uuid4()),))
    elif fault in {'source_content','source_revision','message_conversation'}:
        column, value = {'source_content':('content','OTHER SYNTHETIC MESSAGE'),
            'source_revision':('source_revision',99), 'message_conversation':('conversation_id',str(uuid4()))}[fault]
        corrupt(database, 'assistant_messages', f'UPDATE assistant_messages SET {column}=?', (value,))
    elif fault.startswith('scope_'):
        prepared['request']['scope'][{'scope_workspace':'workspace_id', 'scope_revision':'input_revision',
                                     'scope_materials':'materials_revision'}[fault]] = str(uuid4()) if fault == 'scope_workspace' else 99
        field, value = 'input_json', canonical_json(prepared)
    elif fault.startswith('policy_') and fault != 'policy_digest':
        key, value = {'policy_actor':('actor_id',str(uuid4())), 'policy_expired':('expires_at','2000-01-01T00:00:00Z'),
            'policy_source':('allowed_content_sha256s',['0'*64]), 'policy_config':('config_sha256','0'*64)}[fault]
        policy[key] = value
        value = canonical_json(policy)
        corrupt(database, table, 'UPDATE assistant_model_attempts SET policy_json=?,policy_sha256=?', (value,sha(value)))
    elif fault == 'config_protocol':
        config['protocol_version'] = 'unrecognized-template-v99'
        value = canonical_json(config)
        corrupt(database, table, 'UPDATE assistant_model_attempts SET config_json=?,config_sha256=?', (value,sha(value)))
    elif fault in {'config_digest','policy_digest'}:
        field, value = fault.replace('_digest','_sha256'), '0'*64
    elif fault.startswith('wire_'):
        wire = json.loads(prepared['wire_payload_json'])
        if fault == 'wire_template':
            wire['messages'][0]['content'] = 'Fictional replaced system instructions'
        elif fault == 'wire_source':
            wire['messages'][1]['content'] = '{}'
        prepared['wire_payload_json'] = canonical_json(wire)
        if fault == 'wire_duplicate_key':
            prepared['wire_payload_json'] = '{"model":"untrusted",'+prepared['wire_payload_json'][1:]
        corrupt(database, table, 'UPDATE assistant_model_attempts SET input_json=?,request_sha256=?',
                (canonical_json(prepared),sha(prepared['wire_payload_json'])))
    elif fault == 'reserved_budget':
        field, value = 'reserved_usd', '0'
    elif fault == 'selected_model':
        corrupt(database, 'assistant_runs', "UPDATE assistant_runs SET selected_model='untrusted'")
    elif fault == 'claim_missing':
        field, value = 'claim_sha256', None
    elif fault == 'receipt_missing':
        corrupt(database, 'assistant_model_receipts', 'DELETE FROM assistant_model_receipts')
    elif fault.startswith('receipt_'):
        table, field = 'assistant_model_receipts', 'receipt_json'
        if fault == 'receipt_state': reply['state'] = 'sent_unknown'
        elif fault == 'receipt_cost': reply['estimated_cost_usd'] = '0.000019'
        elif fault == 'receipt_unknown_zero': reply.update(usage=None,cost_status='unknown',estimated_cost_usd='0')
        elif fault == 'receipt_usage_bool': reply['usage']['prompt_tokens'] = True
        elif fault == 'receipt_usage_cap': reply['usage'].update(prompt_tokens=999999,total_tokens=1000009)
        elif fault == 'receipt_extra_body': reply['body'] = 'SYNTHETIC PRIVATE RESPONSE'
        elif fault == 'receipt_time':
            field, value = 'created_at','2000-01-01T00:00:00+00:00'
        if field == 'receipt_json': value = canonical_json(reply)
    elif fault.startswith('output_'):
        table, field = 'assistant_model_outputs', 'output_json'
        if fault == 'output_owner': field, value = 'conversation_id', str(uuid4())
        elif fault == 'output_scope': view['scope']['input_revision'] += 1
        elif fault == 'output_quote': view['candidate']['citations'][0]['quote_sha256'] = '0'*64
        elif fault == 'output_status': view['review_status'] = 'verified'
        elif fault == 'output_time': view['created_at'] = '2000-01-01T00:00:00Z'
        if field == 'output_json': value = canonical_json(view)
    elif fault == 'input_duplicate_key':
        field, value = 'input_json', '{"request":{},'+attempt['input_json'][1:]
    elif fault == 'event_false_unsent':
        # Simultaneously forge a plausible zero-cost terminal receipt and erase
        # the claim, while the durable model.started event still proves a claim.
        corrupt(database, 'assistant_model_outputs', 'DELETE FROM assistant_model_outputs')
        corrupt(database, 'assistant_runs', "UPDATE assistant_runs SET state='failed'")
        corrupt(database, table, "UPDATE assistant_model_attempts SET state='failed_before_send',claim_sha256=NULL")
        reply.update(state='failed_before_send',provider_request_id=None,usage=None,
                     cost_status='not_sent',estimated_cost_usd='0',error_code='PROVIDER_ERROR')
        table, field, value = 'assistant_model_receipts','receipt_json',canonical_json(reply)
    elif fault == 'event_client':
        corrupt(database, 'assistant_run_events', "UPDATE assistant_run_events SET audience='client' WHERE event_type='model.started'")
    if field is not None:
        corrupt(database, table, f'UPDATE {table} SET {field}=?', (value,))
    with database.session() as db, pytest.raises(ValueError, match='ASSISTANT_MODEL'):
        backup._file_references(db)
    # Same trust boundary is reached by the real encrypted archive entry point.
    archive = tmp_path/'invalid.qxbak'
    with pytest.raises(ValueError):
        workspace_backup.create_workspace_backup(Path(database.engine.url.database).parent,
            archive, PASSPHRASE, data_parent=tmp_path)
    assert not archive.exists()
    assert len(runtime.provider.calls) == 1
