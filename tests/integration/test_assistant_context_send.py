"""Source-bound answers: fixed server format, one nested registration, no Jev."""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.assistant.context_preview import assemble_context
from cn_contract.assistant.providers import attempts
from cn_contract.assistant.providers.context_codec import build_basis, prepare as prepare_context
from cn_contract.assistant.providers.policy import MainModelRuntime, encoded, sha
from cn_contract.assistant.runner import execute_attempt
from cn_contract.assistant.task_manager import GenerationTasks
from cn_contract.assistant.providers.judge_policy import JudgeRuntime
from cn_contract.assistant.tools.library import LegalLibraryAdapter
from cn_contract.config import load_settings
from cn_contract.ops import backup
from cn_contract.persistence import Database
from cn_contract.security import ServiceError, authenticate, login
from cn_contract.web.local_server import initialize_workspace
from tests.integration.test_assistant_research_service import request
from tests.integration.test_assistant_library_adapter import library


class SyntheticContextProvider:
    def __init__(self, config):
        self.config = config
        self.calls = []
        self.context_calls = []

    async def generate(self, request, *, expected_config=None):
        self.calls.append(request)
        return d.MainReply(state='received', provider_request_id='fictional-plain',
            usage=d.MainUsage(prompt_tokens=20, completion_tokens=10, total_tokens=30),
            output=d.MainCandidate(text='独立虚构普通候选，请律师核对。', citations=(
                d.MainCitation(message_id=request.message_id, quote_sha256=request.source_sha256),)))

    async def generate_context(self, request, *, expected_config=None, preflight=None):
        self.context_calls.append(request)
        source = request.manifest.sources[0]
        return d.MainContextReply(state='received', provider_request_id='fictional-context',
            usage=d.MainUsage(prompt_tokens=40, completion_tokens=20, total_tokens=60),
            output=d.MainContextCandidate(text='独立虚构资料候选，请律师核对。', citations=(
                d.MainContextCitation(saved_citation_id=source.saved_citation_id,
                                      quote_sha256=source.quote_sha256),)))


@pytest.fixture
def context_world(tmp_path, library):
    """Native full-schema workspace with real saved citations and a saved draft."""
    from cn_contract.assistant import research as research_service
    root = tmp_path/'合成上下文工作区'
    initialize_workspace(root, 'lawyer', 'fixture123', data_parent=tmp_path)
    database = Database('sqlite:///'+str(root/'workbench.db'), root/'protected',
                        load_settings(), initialize_schema=False)
    with database.session() as db:
        token, _ = login('lawyer', 'fixture123', db)
        actor = authenticate(token, db)
        conversation = service.create_conversation(
            actor, d.AssistantConversationCreateInput(request_id=uuid4()), db)
        queued = research_service.enqueue_research(actor, conversation.scope.conversation_id,
            request(conversation), db)
    result = research_service.execute_research(actor, queued.run.id, database,
                                               LegalLibraryAdapter(library[0]))
    ids = result.receipts[0].result.citation_ids
    assert ids
    with database.session() as db:
        view = service.read_conversation(actor, conversation.scope.conversation_id, db)
        view = service.save_draft(actor, view.scope.conversation_id, d.AssistantDraftInput(
            expected_scope=view.scope, expected_composer_revision=view.composer_revision,
            content=' 请按所选历史片段列出需要核对的问题。\n保留不同结论。 '), db)
        row = service._owned(actor, view.scope.conversation_id, db)
        config = d.MainModelConfig(enabled=True, model='deepseek-flash', input_usd_per_million='0.3',
            output_usd_per_million='1.2', price_reference='synthetic-ceiling')
        submission = d.MainContextSubmission(request_id=uuid4(), expected_scope=view.scope,
            expected_composer_revision=view.composer_revision, content=view.draft_input,
            citation_ids=ids)
        scope, manifest, records = assemble_context(actor, row, submission.citation_ids, db,
                                                    question=submission.content)
        basis = build_basis(submission.request_id, manifest, scope,
                            submission.expected_composer_revision, config, records)
    policy = d.MainModelPolicy(policy_id=uuid4(), workspace_id=view.scope.workspace_id,
        actor_id=actor.user_id, config_sha256=sha(encoded(config)),
        allowed_content_sha256s=(basis.manifest_sha256,), max_total_usd='1', max_calls=5,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    runtime = MainModelRuntime(SyntheticContextProvider(config), policy)
    yield database, actor, view, submission, basis, runtime
    database.engine.dispose()


def enqueue(world):
    database, actor, view, submission, _, runtime = world
    with database.session() as db:
        return attempts.enqueue_context(actor, view.scope.conversation_id, submission, db, runtime)


def test_context_answer_roundtrip_preserves_format_sources_and_bytes(context_world):
    database, actor, view, submission, basis, runtime = context_world
    first = enqueue(context_world)
    assert type(first) is d.MainContextAttemptView and first.input_format == 'library-context-v1'
    assert first.state == 'reserved' and first.receipt is None and first.output is None
    cid = str(view.scope.conversation_id)
    with database.session() as db:
        row = db.execute(text('SELECT * FROM assistant_model_attempts WHERE id=:id'),
                         {'id': str(first.id)}).mappings().one()
        assert row['input_format'] == 'library-context-v1'
        relations = db.execute(text('''SELECT ordinal,saved_citation_id FROM assistant_model_input_citations
            WHERE attempt_id=:id ORDER BY ordinal'''), {'id': str(first.id)}).all()
        assert [item[1] for item in relations] == [str(value) for value in submission.citation_ids]
        assert [item[0] for item in relations] == list(range(len(relations)))
        message = db.execute(text('''SELECT m.* FROM assistant_messages m
            JOIN assistant_runs r ON r.message_id=m.id WHERE r.id=:run'''),
            {'run': str(first.run_id)}).mappings().one()
        assert message['content'] == submission.content
    completed = asyncio.run(execute_attempt(actor, first.id, database, runtime))
    assert completed.state == 'received' and completed.receipt.cost_status == 'estimated'
    assert completed.receipt.estimated_cost_usd == Decimal('0.000036')
    assert completed.output.review_status == 'unverified' and completed.output.audience == 'internal'
    assert (completed.output.candidate.citations[0].saved_citation_id
            == basis.source_bindings[0].saved_citation_id)
    assert len(runtime.provider.context_calls) == 1 and runtime.provider.calls == []
    with database.session() as db:
        assert attempts.read_attempt(actor, first.id, db) == completed
        assert backup._file_references(db) == []
        events = service.read_events(actor, first.run_id, db)
        assert [event.event_type for event in events.events] == [
            'message.accepted', 'model.reserved', 'model.started', 'model.finished']


def test_context_replay_is_idempotent_and_conflicts_on_change(context_world):
    database, actor, view, submission, basis, runtime = context_world
    first = asyncio.run(execute_attempt(actor, enqueue(context_world).id, database, runtime))
    with database.session() as db:
        assert attempts.enqueue_context(actor, view.scope.conversation_id, submission, db, runtime) == first
    assert len(runtime.provider.context_calls) == 1
    for changes in ({'content': '换一个问题'}, {'citation_ids': (uuid4(),)},
                    {'expected_composer_revision': submission.expected_composer_revision + 9}):
        changed = submission.model_copy(update=changes)
        with database.session() as db, pytest.raises(ServiceError) as failure:
            attempts.enqueue_context(actor, view.scope.conversation_id, changed, db, runtime)
        assert failure.value.code in ('VERSION_CONFLICT', 'STATE_CONFLICT')
    assert len(runtime.provider.context_calls) == 1


@pytest.mark.parametrize('change', ['missing', 'disabled', 'expired', 'manifest', 'config'])
def test_unapproved_context_registration_sends_nothing(context_world, change):
    database, actor, view, submission, basis, runtime = context_world
    if change == 'missing':
        runtime.policy = None
    elif change == 'disabled':
        runtime.provider.config = runtime.provider.config.model_copy(update={'enabled': False})
    elif change == 'expired':
        runtime.policy = runtime.policy.model_copy(update={
            'expires_at': datetime.now(timezone.utc) - timedelta(seconds=1)})
    elif change == 'manifest':
        runtime.policy = runtime.policy.model_copy(update={'allowed_content_sha256s': ('0'*64,)})
    else:
        runtime.policy = runtime.policy.model_copy(update={'config_sha256': '0'*64})
    with pytest.raises(ServiceError) as failure:
        enqueue(context_world)
    assert failure.value.code == 'BLOCKED_LIVE'
    with database.session() as db:
        current = service.read_conversation(actor, view.scope.conversation_id, db)
        # Only the earlier research message remains; the draft is untouched.
        assert len(current.messages) == 1 and current.draft_input == submission.content
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_input_citations')) == 0
    assert runtime.provider.context_calls == []


def test_registration_rolls_back_message_attempt_and_relations_together(context_world, monkeypatch):
    database, actor, view, submission, _, runtime = context_world
    with database.session() as db:
        before = {table: db.scalar(text('SELECT COUNT(*) FROM ' + table)) for table in
                  ('assistant_messages', 'assistant_runs', 'assistant_model_attempts',
                   'assistant_model_input_citations', 'assistant_run_events')}
    monkeypatch.setattr(attempts.context_codec, 'prepare',
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError('synthetic mid-transaction failure')))
    with pytest.raises(ValueError, match='synthetic'):
        enqueue(context_world)
    with database.session() as db:
        current = service.read_conversation(actor, view.scope.conversation_id, db)
        assert len(current.messages) == 1 and current.draft_input == submission.content
        after = {table: db.scalar(text('SELECT COUNT(*) FROM ' + table)) for table in before}
        assert after == before
        # The saved citations themselves are untouched historical records.
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_library_citations')) >= len(submission.citation_ids)


def test_settle_rejects_forged_output_citations_but_keeps_real_usage(context_world):
    database, actor, view, submission, basis, runtime = context_world
    first = enqueue(context_world)
    with database.session() as db:
        token, request, _ = attempts.claim(actor, first.id, db, runtime)
        assert type(request) is d.MainContextRequest
        forged = d.MainContextReply(state='received', provider_request_id='fictional-forged',
            usage=d.MainUsage(prompt_tokens=40, completion_tokens=20, total_tokens=60),
            output=d.MainContextCandidate(text='合成伪造引用候选', citations=(
                d.MainContextCitation(saved_citation_id=uuid4(), quote_sha256='0'*64),)))
        attempts.settle(actor, first.id, token, forged, db, runtime)
        result = attempts.read_attempt(actor, first.id, db)
        assert result.state == 'received' and result.output is None
        assert result.receipt.cost_status == 'estimated'
        assert result.receipt.estimated_cost_usd == Decimal('0.000036')
        assert result.receipt.error_code == 'MODEL_OUTPUT_INVALID'
        assert backup._file_references(db) == []
    assert runtime.provider.context_calls == []


def test_cancel_before_claim_releases_context_reservation(context_world):
    database, actor, view, submission, _, runtime = context_world
    first = enqueue(context_world)
    with database.session() as db:
        service.cancel_run(actor, first.run_id, d.AssistantCancelInput(request_id=uuid4()), db)
    result = asyncio.run(execute_attempt(actor, first.id, database, runtime))
    assert result.state == 'failed_before_send' and result.receipt.cost_status == 'not_sent'
    with database.session() as db:
        assert service.get_run(actor, first.run_id, db).state == 'cancelled'
        assert backup._file_references(db) == []
    assert runtime.provider.context_calls == []


def test_recovery_marks_context_states_without_redispatch(context_world):
    database, actor, view, submission, _, runtime = context_world
    first = enqueue(context_world)
    with database.session() as db:
        assert attempts.recover_attempts(db) == 1
        recovered = attempts.read_attempt(actor, first.id, db)
        assert recovered.state == 'failed_before_send' and recovered.receipt.cost_status == 'not_sent'
        assert recovered.input_format == 'library-context-v1'
        assert backup._file_references(db) == []
        assert attempts.recover_attempts(db) == 0
    result = asyncio.run(execute_attempt(actor, first.id, database, runtime))
    assert result.state == 'failed_before_send'
    assert runtime.provider.context_calls == []


def test_context_branch_never_reserves_or_runs_jev(context_world):
    from tests.integration.test_assistant_task_manager import finished
    database, actor, view, submission, _, runtime = context_world
    tasks = GenerationTasks(database, runtime, judge_runtime=JudgeRuntime())
    async def scenario():
        tasks.start()
        try:
            submitted = tasks.submit_context(actor, view.scope.conversation_id, submission)
            await finished(tasks)
            assert tasks.last_error is None
            return submitted
        finally:
            await tasks.close()
    submitted = asyncio.run(scenario())
    with database.session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_judge_attempts')) == 0
        finished = attempts.read_attempt(actor, submitted.id, db)
        assert finished.state == 'received' and finished.input_format == 'library-context-v1'
    assert len(runtime.provider.context_calls) == 1


def test_plain_and_context_history_coexist_with_distinct_views(context_world):
    database, actor, view, submission, basis, runtime = context_world
    first = asyncio.run(execute_attempt(actor, enqueue(context_world).id, database, runtime))
    with database.session() as db:
        current = service.read_conversation(actor, view.scope.conversation_id, db)
        runtime.policy = d.MainModelPolicy(policy_id=uuid4(), workspace_id=runtime.policy.workspace_id,
            actor_id=runtime.policy.actor_id, config_sha256=runtime.policy.config_sha256,
            allowed_content_sha256s=(basis.manifest_sha256, sha('第二轮独立合成普通文字')),
            max_total_usd=runtime.policy.max_total_usd, max_calls=runtime.policy.max_calls,
            expires_at=runtime.policy.expires_at)
        plain = attempts.enqueue_generation(actor, view.scope.conversation_id,
            d.AssistantMessageInput(request_id=uuid4(), expected_scope=current.scope,
                expected_composer_revision=current.composer_revision,
                content='第二轮独立合成普通文字'), db, runtime)
    # Execution opens its own sessions; never await it inside an open one.
    plain = asyncio.run(execute_attempt(actor, plain.id, database, runtime))
    with database.session() as db:
        from cn_contract.assistant.providers.history import read_history
        conversation_row = service._owned(actor, view.scope.conversation_id, db)
        messages = service.read_conversation(actor, view.scope.conversation_id, db).messages
        history = read_history(actor, conversation_row, d.MainGenerationHistoryQuery(
            message_ids=tuple(item.id for item in messages)), db)
        kinds = {type(item.attempt) for item in history.items}
        assert kinds == {d.MainAttemptView, d.MainContextAttemptView}
        context_item = next(item for item in history.items
                            if type(item.attempt) is d.MainContextAttemptView)
        assert context_item.attempt.output == first.output
        assert backup._file_references(db) == []


def test_v1_history_item_dump_bytes_are_unchanged_by_the_union():
    """The history union must not alter the canonical bytes of plain V1 items."""
    import json as std_json
    from cn_contract.config import canonical_json
    scope = d.ScopeSnapshot(workspace_id=uuid4(), conversation_id=uuid4(), scope_kind='conversation',
        scope_ref=None, binding_revision=1, input_revision=1, materials_revision=0)
    attempt = d.MainAttemptView(id=uuid4(), run_id=uuid4(), scope=scope, state='received',
        reserved_usd=Decimal('0.000018'), receipt=None, output=None)
    item = d.MainGenerationHistoryItem(message_id=uuid4(), attempt=attempt)
    dumped = canonical_json(item.model_dump(mode='json'))
    again = d.MainGenerationHistoryItem.model_validate(std_json.loads(dumped))
    assert canonical_json(again.model_dump(mode='json')) == dumped
    assert set(std_json.loads(dumped)['attempt']) == {
        'id', 'run_id', 'scope', 'state', 'reserved_usd', 'unit', 'receipt', 'output'}
