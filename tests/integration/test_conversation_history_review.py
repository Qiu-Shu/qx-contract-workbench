"""Independent adversarial checks using only synthetic local ledger records."""
from datetime import timedelta
import asyncio
import json
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import conversation_history, service
from cn_contract.assistant.model_integrity import validate_model_records
from cn_contract.assistant.providers import attempts, profile_codec
from cn_contract.assistant.providers.deepseek_protocol import json_bytes
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.config import canonical_json
from cn_contract.ops import backup, workspace_backup
from cn_contract.persistence import Database
from cn_contract.security import ServiceError, authenticate, login
from tests.helpers.legacy_assistant_backup import PASSPHRASE
from tests.integration.test_assistant_attachment_backup import corrupt
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_main_provider import config, KEY
from tests.integration.test_assistant_profile_execution import profile_world, authorize, enqueue
from tests.unit.test_assistant_profile_codec import response


def next_turn(state, content):
    database, actor, conversation, _ = state
    with database.session() as db:
        current = service.read_conversation(actor, conversation.scope.conversation_id, db)
        current = service.save_draft(actor, current.scope.conversation_id, d.AssistantDraftInput(
            expected_scope=current.scope, expected_composer_revision=current.composer_revision, content=content), db)
    request = d.AssistantMessageInput(request_id=uuid4(), expected_scope=current.scope,
        expected_composer_revision=current.composer_revision, content=content)
    return database, actor, current, request


def completed(state, answer='独立虚构回答，仍待律师核对。'):
    """Exercise real authorize/enqueue/claim/settle; never open a network socket."""
    database, actor, _, _ = state
    provider = DeepSeekProvider.for_synthetic_loopback(config(), lambda: KEY,
        'http://127.0.0.1:1/chat/completions')
    async def scenario():
        _, runtime, basis, _ = authorize(state, provider)
        attempt = enqueue(state, runtime)
        with database.session() as db:
            token, prepared, _ = attempts.claim(actor, attempt.id, db, runtime)
            reply = profile_codec.decode_response(response(prepared.request,
                {'text':answer, 'citations':[], 'profile_changes':[]}), prepared.request, provider.config, KEY)
            attempts.settle(actor, attempt.id, token, reply, db, runtime)
            result = attempts.read_attempt(actor, attempt.id, db)
        assert result.output is not None
        return result, basis, runtime
    return asyncio.run(scenario())


def test_selection_enforces_binding_revision_time_and_conversation(profile_world):
    first, _, _ = completed(profile_world)
    database, actor, conversation, _ = profile_world
    with database.session() as db:
        scope = service.read_conversation(actor, conversation.scope.conversation_id, db).scope
        history = conversation_history.select_history(db, scope)
        assert len(history) == 2
        assert conversation_history.select_history(db, scope.model_copy(update={'input_revision':0})) == ()
        assert conversation_history.select_history(db, scope.model_copy(update={'binding_revision':2})) == ()
        assert conversation_history.select_history(db, scope.model_copy(update={'conversation_id':uuid4()})) == ()
        assert conversation_history.select_history(db, scope, before_at=first.output.created_at-timedelta(microseconds=1)) == ()
        assert conversation_history.select_history(db, scope, before_at=first.output.created_at) == history
    completed(next_turn(profile_world, '第二轮独立虚构问题。'))
    with database.session() as db:
        assert conversation_history.select_history(db, scope) == history


def test_history_budget_keeps_complete_pairs_and_drops_oldest(profile_world):
    completed(profile_world, '第一轮独立回答。')
    state = next_turn(profile_world, '第二轮独立问题。')
    completed(state, '第二轮独立回答。')
    database, actor, conversation, _ = state
    with database.session() as db:
        scope = service.read_conversation(actor, conversation.scope.conversation_id, db).scope
        history = conversation_history.select_history(db, scope)
        size = len(json_bytes([m.model_dump(mode='json') for m in history]))
        assert len(history) == 4
        assert conversation_history.select_history(db, scope, budget=size) == history
        assert conversation_history.select_history(db, scope, budget=size-1) == history[-2:]
        assert conversation_history.select_history(db, scope, budget=0) == ()


def test_request_byte_budget_selects_only_history_that_fits(profile_world):
    completed(profile_world)
    database, actor, conversation, _ = profile_world
    content = '后续独立虚构问题。'
    with database.session() as db:
        scope = service.read_conversation(actor, conversation.scope.conversation_id, db).scope
        history = conversation_history.select_history(db, scope)
        history_bytes = len(json_bytes([m.model_dump(mode='json') for m in history]))
        current_bytes = len(json_bytes(profile_codec._text_request(content, config())))
        exact = config(max_input_bytes=current_bytes+1024+history_bytes)
        clipped = config(max_input_bytes=current_bytes+1024+history_bytes-1)
        assert conversation_history.for_message(db, scope, content, exact) == history
        assert conversation_history.for_message(db, scope, content, clipped) == ()
        assert conversation_history.for_message(db, scope, content, config(max_input_bytes=current_bytes)) == ()


def test_one_shot_grant_binds_entire_history_and_rejects_substitution(profile_world):
    completed(profile_world)
    state = next_turn(profile_world, '后续独立虚构问题。')
    _, actor, _, request = state
    async def scenario():
        provider = DeepSeekProvider.for_synthetic_loopback(config(), lambda: KEY,
            'http://127.0.0.1:1/chat/completions')
        _, runtime, basis, policy = authorize(state, provider)
        assert policy.max_calls == 1
        changed = basis.model_dump(mode='json')
        changed['conversation_history'][1]['content'] = '未经此次同意的替代回答。'
        substituted = d.MainProfileSendBasis.model_validate(changed)
        with pytest.raises(ServiceError) as rejected:
            runtime.check_profile_submission(actor, request, substituted)
        assert rejected.value.code == 'BLOCKED_LIVE'
        runtime.check_profile_submission(actor, request, basis)
    asyncio.run(scenario())


def test_oversize_latest_answer_never_sends_a_partial_turn_or_older_gap(profile_world):
    completed(profile_world, '较早的虚构回答。')
    state = next_turn(profile_world, '第二轮独立虚构问题。')
    completed(state, '虚'*12000)
    database, actor, conversation, _ = state
    with database.session() as db:
        scope = service.read_conversation(actor, conversation.scope.conversation_id, db).scope
        assert conversation_history.select_history(db, scope) == ()


def test_selection_is_latest_eight_complete_turns(profile_world):
    state = profile_world
    for ordinal in range(10):
        completed(state, f'虚构回答 {ordinal}。')
        if ordinal != 9:
            state = next_turn(state, f'虚构问题 {ordinal+1}。')
    database, actor, conversation, _ = state
    with database.session() as db:
        scope = service.read_conversation(actor, conversation.scope.conversation_id, db).scope
        history = conversation_history.select_history(db, scope)
        assert len(history) == 16
        assert [m.source_revision for m in history[::2]] == list(range(3, 11))
        assert all(m.role == ('user' if i % 2 == 0 else 'assistant') for i, m in enumerate(history))
        validate_model_records(db)


def test_historical_v1_and_v2_replay_survives_newer_turn(profile_world):
    first, first_basis, _ = completed(profile_world)
    state = next_turn(profile_world, '继续第一轮，独立虚构。')
    second, second_basis, _ = completed(state)
    assert not first_basis.conversation_history and len(second_basis.conversation_history) == 2
    completed(next_turn(state, '第三轮，不能进入旧记录的上下文。'))
    database, actor, _, _ = state
    with database.session() as db:
        assert attempts.read_attempt(actor, first.id, db) == first
        assert attempts.read_attempt(actor, second.id, db) == second
        validate_model_records(db)


def test_persisted_source_tamper_rejects_dependent_history_and_backup(profile_world, tmp_path):
    first, _, _ = completed(profile_world)
    state = next_turn(profile_world, '后续独立虚构问题。')
    second, _, _ = completed(state)
    database, actor, _, _ = state
    with database.session() as db:
        raw = db.scalar(text('SELECT output_json FROM assistant_model_outputs WHERE id=:id'), {'id':str(first.output.id)})
    value = json.loads(raw)
    value['candidate']['text'] = '被篡改的历史回答。'
    corrupt(database, 'assistant_model_outputs', 'UPDATE assistant_model_outputs SET output_json=? WHERE id=?',
        (canonical_json(value), str(first.output.id)))
    with database.session() as db:
        with pytest.raises((ValueError, ServiceError)):
            attempts.read_attempt(actor, second.id, db)
        with pytest.raises((ValueError, ServiceError)):
            validate_model_records(db)
    target = tmp_path/'must-not-publish.qxbak'
    with pytest.raises((ValueError, ServiceError)):
        workspace_backup.create_workspace_backup(Path(database.engine.url.database).parent, target, PASSPHRASE,
            data_parent=tmp_path)
    assert not target.exists()


@pytest.mark.parametrize('field', ['run_id', 'created_at'])
def test_history_selection_rejects_output_with_mismatched_stored_identity(profile_world, field):
    first, _, _ = completed(profile_world)
    database, actor, conversation, _ = profile_world
    with database.session() as db:
        raw = db.scalar(text('SELECT output_json FROM assistant_model_outputs WHERE id=:id'), {'id':str(first.output.id)})
        scope = service.read_conversation(actor, conversation.scope.conversation_id, db).scope
    value = json.loads(raw)
    value[field] = str(uuid4()) if field == 'run_id' else (first.output.created_at-timedelta(days=1)).isoformat()
    corrupt(database, 'assistant_model_outputs', 'UPDATE assistant_model_outputs SET output_json=? WHERE id=?',
        (canonical_json(value), str(first.output.id)))
    with database.session() as db:
        with pytest.raises(ServiceError) as rejected:
            conversation_history.select_history(db, scope)
        assert rejected.value.code == 'VERSION_CONFLICT'


def test_qxbak_preserves_v1_and_v2_history_and_restored_execution_stays_blocked(profile_world, tmp_path):
    first, _, _ = completed(profile_world)
    state = next_turn(profile_world, '第二轮，备份恢复用独立虚构问题。')
    second, basis, runtime = completed(state)
    database, _, _, _ = state
    with database.session() as db:
        before = dict(db.execute(text('SELECT id,input_json FROM assistant_model_attempts')).all())
        assert 'conversation_history' not in json.loads(before[str(first.id)])['basis']
        assert json.loads(before[str(second.id)])['basis']['conversation_history'] == [m.model_dump(mode='json') for m in basis.conversation_history]
    root = Path(database.engine.url.database).parent
    archive = tmp_path/'独立上下文.qxbak'
    workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
    result = workspace_backup.restore_workspace_backup(archive, tmp_path/'restored', PASSPHRASE)
    restored_root = Path(result['restored_root'])
    restored = Database('sqlite:///'+str(restored_root/'workbench.db'), restored_root/'protected',
        database.settings, initialize_schema=False)
    backup._mark_storage_flags(restored)
    try:
        with restored.session() as db:
            token, _ = login('lawyer', 'fixture123', db)
            actor = authenticate(token, db)
            assert dict(db.execute(text('SELECT id,input_json FROM assistant_model_attempts')).all()) == before
            assert attempts.read_attempt(actor, first.id, db) == first
            assert attempts.read_attempt(actor, second.id, db) == second
            validate_model_records(db)
            with pytest.raises(ServiceError) as denied:
                attempts.claim(actor, second.id, db, runtime)
            assert denied.value.code == 'BLOCKED_LIVE'
        second_archive = tmp_path/'second.qxbak'
        workspace_backup.create_workspace_backup(restored_root, second_archive, PASSPHRASE, data_parent=tmp_path)
        workspace_backup.restore_workspace_backup(second_archive, tmp_path/'restored-again', PASSPHRASE)
    finally:
        restored.engine.dispose()
