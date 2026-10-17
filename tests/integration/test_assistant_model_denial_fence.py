"""A denial's committed audit must not bypass a subsequently committed fence."""
from uuid import uuid4

from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.assistant.providers import attempts
from cn_contract.ops.storage import RestoreFenceRow
from cn_contract.security import ServiceError, remove_membership
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_storage import add_matter


def test_membership_denial_commit_requires_fresh_fence_before_model_settlement(world, monkeypatch):
    database, actor, _, request, runtime = world
    matter_id = add_matter(database, actor)
    with database.session() as db:
        conversation = service.create_conversation(actor, d.AssistantConversationCreateInput(
            request_id=uuid4(), scope_kind='matter', scope_ref=matter_id), db)
        request = request.model_copy(update={'expected_scope':conversation.scope})
        pending = attempts.enqueue_generation(actor, conversation.scope.conversation_id, request, db, runtime)
    with database.session() as db:
        token, _, _ = attempts.claim(actor, pending.id, db, runtime)
        before = dict(db.execute(text('SELECT * FROM assistant_model_attempts WHERE id=:id'),
            {'id':str(pending.id)}).mappings().one())
        before_events = db.scalar(text('SELECT COUNT(*) FROM assistant_run_events WHERE run_id=:id'),
            {'id':str(pending.run_id)})
    with database.session() as db:
        remove_membership(matter_id, actor.user_id, db)

    inserted = False
    failure_code = None
    with database.session() as db:
        original_commit = db.commit

        def commit_then_fence():
            nonlocal inserted
            original_commit()
            if not inserted:
                # Keep deny()'s rollback, audit and commit real. At this exact
                # transaction boundary a separate maintenance connection can
                # acquire the SQLite write lock before settlement resumes.
                with database.session() as maintenance:
                    maintenance.add(RestoreFenceRow(ref=str(uuid4()), archive_sha256='a'*64,
                        manifest_sha256='b'*64, payload='{"synthetic":true}'))
                inserted = True

        with monkeypatch.context() as patch:
            patch.setattr(db, 'commit', commit_then_fence)
            try:
                attempts.settle(actor, pending.id, token, d.MainReply(state='received',
                    usage=d.MainUsage(prompt_tokens=20, completion_tokens=10, total_tokens=30),
                    output=d.MainCandidate(text='独立虚构候选；恢复隔离后不得保存。')), db, runtime)
            except ServiceError as failure:
                failure_code = failure.code

    assert inserted, 'the real membership denial must have released its transaction'
    with database.session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM ops_restore_fences')) == 1
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_receipts')) == 0
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_outputs')) == 0
        after = dict(db.execute(text('SELECT * FROM assistant_model_attempts WHERE id=:id'),
            {'id':str(pending.id)}).mappings().one())
        assert after == before
        assert db.scalar(text('SELECT state FROM assistant_runs WHERE id=:id'),
            {'id':str(pending.run_id)}) == 'generating'
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_run_events WHERE run_id=:id'),
            {'id':str(pending.run_id)}) == before_events
    assert failure_code == 'BLOCKED_LIVE'
    assert runtime.provider.calls == []
