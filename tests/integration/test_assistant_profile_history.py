"""Read-only save outcomes for synthetic profile generation history; no network."""
import json
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant.providers import attempts, history
from cn_contract.assistant import profile_store, service
from cn_contract.assistant.providers.policy import sha
from cn_contract.security import ServiceError, authenticate, login, provision_user
from tests.integration.test_assistant_attachment_backup import corrupt
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_profile_execution import profile_world
from tests.integration.test_assistant_profile_model_integrity import profile_history
from tests.integration.test_assistant_profile_sources import state


def test_saved_profile_history_returns_verified_commit_without_original_request_id(profile_world):
    database, actor, conversation, _ = profile_world
    result, prepared, _ = profile_history(profile_world)
    before = state(database)
    with database.session() as db:
        current = service._owned(actor, conversation.scope.conversation_id, db)
        restored = history.read_history(actor, current, d.MainGenerationHistoryQuery(
            message_ids=(prepared.request.message_id,)), db).items[0].attempt
    assert restored == result
    saved = restored.model_dump(mode='json')['profile_save']
    assert set(saved) == {'outcome', 'reason_code', 'receipt'}
    assert saved['outcome'] == 'applied' and saved['reason_code'] is None
    assert saved['receipt']['event_type'] == 'profile.saved'
    assert saved['receipt']['profile_revision'] == 1
    assert saved['receipt']['profile_changed'] is True
    assert saved['receipt']['projection_changed'] is True
    assert saved['receipt']['audience'] == 'internal'
    assert state(database) == before


def read(database, actor, identifier):
    with database.session() as db:
        return attempts.read_attempt(actor, identifier, db)


@pytest.mark.parametrize('event', ['response.ready', 'profile.saved'])
def test_profile_history_rejects_handler_event_payload_disagreement(profile_world, event):
    database, actor, *_ = profile_world
    view, _, _ = profile_history(profile_world)
    corrupt(database, 'assistant_run_events',
            'UPDATE assistant_run_events SET payload_json=? WHERE event_type=?', ('{}', event))
    with pytest.raises(ServiceError) as failure:
        read(database, actor, view.id)
    assert failure.value.code == 'VERSION_CONFLICT'


@pytest.mark.parametrize('outcome', ['unchanged', 'save_failed', 'version_conflict'])
def test_profile_history_separates_successful_reply_from_save_result(profile_world, monkeypatch, outcome):
    database, actor, *_ = profile_world
    if outcome != 'unchanged':
        def fail_save(*args):
            if outcome == 'version_conflict':
                raise ServiceError('VERSION_CONFLICT', 409)
            raise ValueError('synthetic save failure')
        monkeypatch.setattr(profile_store, '_commit', fail_save)
    view, _, _ = profile_history(profile_world, project_intake=False, empty=outcome == 'unchanged')
    assert view.state == 'received' and view.output is not None
    saved = read(database, actor, view.id).profile_save
    if outcome == 'unchanged':
        assert saved.outcome == 'unchanged' and saved.reason_code is None
        assert saved.receipt.event_type == 'profile.unchanged'
        assert saved.receipt.profile_revision == 0 and saved.receipt.intake_id is None
    else:
        assert saved.outcome == 'blocked' and saved.reason_code == outcome and saved.receipt is None


@pytest.mark.parametrize('status', ['reserved', 'sending', 'sent_unknown', 'failed_before_send'])
def test_profile_history_without_output_never_invents_a_save(profile_world, status):
    database, actor, *_ = profile_world
    view, _, _ = profile_history(profile_world, state=status)
    assert view.output is None and read(database, actor, view.id).profile_save is None


@pytest.mark.parametrize('tamper', ['missing_handler', 'handler_run', 'handler_output', 'handler_conversation',
    'handler_basis', 'handler_sequence', 'missing_receipt', 'receipt_actor', 'receipt_session',
    'receipt_request', 'receipt_revision', 'output_run', 'output_scope', 'output_quote', 'message_content'])
def test_profile_history_rejects_corrupt_output_handler_and_receipt_links(profile_world, tamper):
    database, actor, *_ = profile_world
    view, _, _ = profile_history(profile_world)
    if tamper == 'missing_handler':
        corrupt(database, 'assistant_profile_handlers', 'DELETE FROM assistant_profile_handlers')
    elif tamper.startswith('handler_'):
        column = {'handler_run':'run_id', 'handler_output':'output_id', 'handler_conversation':'conversation_id',
                  'handler_basis':'basis_sha256', 'handler_sequence':'profile_receipt_sequence'}[tamper]
        value = '0' * 64 if column == 'basis_sha256' else 99 if tamper == 'handler_sequence' else str(uuid4())
        corrupt(database, 'assistant_profile_handlers', f'UPDATE assistant_profile_handlers SET {column}=?', (value,))
    elif tamper == 'missing_receipt':
        corrupt(database, 'assistant_profile_receipts', 'DELETE FROM assistant_profile_receipts')
    elif tamper.startswith('receipt_'):
        column = {'receipt_actor':'actor_id', 'receipt_session':'session_id', 'receipt_request':'request_id',
                  'receipt_revision':'profile_revision'}[tamper]
        corrupt(database, 'assistant_profile_receipts', f'UPDATE assistant_profile_receipts SET {column}=?',
                (99 if tamper == 'receipt_revision' else str(uuid4()),))
    elif tamper == 'message_content':
        corrupt(database, 'assistant_messages', "UPDATE assistant_messages SET content='不同的合成原话'")
    else:
        value = view.output.model_dump(mode='json')
        if tamper == 'output_run':
            value['run_id'] = str(uuid4())
        elif tamper == 'output_scope':
            value['scope']['conversation_id'] = str(uuid4())
        else:
            ref = value['candidate']['profile_patch']['changes'][0]['source_refs'][0]
            ref['quote'] = '乙称借款99000元'
            ref['quote_sha256'] = sha(ref['quote'])
        corrupt(database, 'assistant_model_outputs', 'UPDATE assistant_model_outputs SET output_json=?',
                (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')),))
    with pytest.raises(ServiceError) as failure:
        read(database, actor, view.id)
    assert failure.value.code == 'VERSION_CONFLICT'


def test_profile_history_keeps_ownership_boundary(profile_world):
    database, actor, *_ = profile_world
    view, _, _ = profile_history(profile_world)
    with database.session() as db:
        provision_user('history-other', 'fixture123', {d.Role.HANDLING_LAWYER}, db, local_workbench_password=True)
        token, _ = login('history-other', 'fixture123', db)
        other = authenticate(token, db)
    with pytest.raises(ServiceError) as failure:
        read(database, other, view.id)
    assert failure.value.code == 'CROSS_MATTER_DENIED'


def test_ordinary_attempt_contract_does_not_gain_profile_fields(world):
    database, actor, conversation, request, runtime = world
    with database.session() as db:
        view = attempts.enqueue_generation(actor, conversation.scope.conversation_id, request, db, runtime)
    assert type(view) is d.MainAttemptView and 'profile_save' not in view.model_dump(mode='json')


@pytest.mark.parametrize('later', ['draft', 'message', 'profile', 'session'])
def test_saved_receipt_stays_historical_after_later_local_work(profile_world, later):
    database, actor, conversation, _ = profile_world
    original, _, _ = profile_history(profile_world)
    with database.session() as db:
        current = service.read_conversation(actor, conversation.scope.conversation_id, db)
        if later == 'draft':
            service.save_draft(actor, current.scope.conversation_id, d.AssistantDraftInput(
                expected_scope=current.scope, expected_composer_revision=current.composer_revision,
                content='后续草稿不改变历史保存结果。'), db)
        elif later == 'message':
            service.save_message(actor, current.scope.conversation_id, d.AssistantMessageInput(
                request_id=uuid4(), expected_scope=current.scope,
                expected_composer_revision=current.composer_revision, content='后续发送的独立消息。'), db)
        elif later == 'profile':
            receipt = original.profile_save.receipt
            profile_store._commit(actor, d.ProfileCommitInput(request_id=uuid4(),
                patch=d.ProfilePatch(scope=current.scope, base_profile_revision=1),
                expected_intake_id=receipt.intake_id, expected_intake_revision=receipt.intake_revision,
                manual_edits=(d.ProfileEdit(field='title', value={'kind':'text','value':'后续律师更正的标题'}),)),
                d.ProfileSourceSnapshot(scope=current.scope), db)
        else:
            token, _ = login('lawyer', 'fixture123', db)
            actor = authenticate(token, db)
    before = state(database)
    restored = read(database, actor, original.id)
    assert restored.profile_save == original.profile_save
    assert restored.profile_save.receipt.profile_revision == 1
    assert state(database) == before


def test_rebound_conversation_does_not_show_old_save_as_current(profile_world):
    database, actor, *_ = profile_world
    view, _, _ = profile_history(profile_world)
    with database.session() as db:
        db.execute(text('UPDATE assistant_conversations SET binding_revision=binding_revision+1'))
    with pytest.raises(ServiceError) as failure:
        read(database, actor, view.id)
    assert failure.value.code == 'VERSION_CONFLICT'


@pytest.mark.parametrize('change', [dict(outcome='unchanged'), dict(receipt=None), dict(reason_code='save_failed'),
    dict(outcome='blocked', reason_code='save_failed'), dict(extra='authority')])
def test_save_view_rejects_false_success_or_unrecognized_fields(profile_world, change):
    result, _, _ = profile_history(profile_world)
    with pytest.raises(ValueError):
        d.MainProfileSaveView.model_validate(result.profile_save.model_dump(mode='python') | change)


def test_lost_output_does_not_leave_a_successful_save_in_history(profile_world):
    database, actor, *_ = profile_world
    view, _, _ = profile_history(profile_world)
    corrupt(database, 'assistant_model_outputs', 'DELETE FROM assistant_model_outputs')
    with pytest.raises(ServiceError) as failure:
        read(database, actor, view.id)
    assert failure.value.code == 'VERSION_CONFLICT'
