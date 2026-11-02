"""Synthetic delayed control messages must not release a newer personal hold."""
import asyncio
import pytest
from sqlalchemy import text
from cn_contract import domain as d
from cn_contract.task_drafts import service as drafts
from tests.integration.test_assistant_generation import world
from tests.integration.test_weixin_personal_runtime import (
    setup_runtime, close, packet, command, sequenced_command, file_message)


@pytest.mark.parametrize('order', ['newer', 'older', 'unknown', 'contradictory'])
def test_personal_resume_requires_proven_source_order_and_preserves_events(world, order):
    async def scenario():
        runtime, wire, manager, provider, actor = await setup_runtime(world)
        database = world[0]; cid = world[2].scope.conversation_id
        try:
            await runtime.ingest(runtime._epoch, packet(file_message(wire, 9),
                sequenced_command(1), sequenced_command(3, '暂停'), cursor='held'))
            await runtime.advance(runtime._epoch)
            assert not provider.calls
            with database.session() as db:
                draft = drafts.list_drafts(actor, cid, db).items[0]
                assert draft.state == 'paused'
                original = list(db.execute(text('SELECT id,payload_json,payload_sha256 FROM task_inbox_events ORDER BY rowid')))
            resume = command(2, '继续')
            if order != 'unknown':
                resume.update(seq=2 if order == 'older' else 4,
                    create_time_ms=4000 if order == 'newer' else 2000)
            incoming = packet(resume, cursor='resume')
            await runtime.ingest(runtime._epoch, incoming)
            await runtime.advance(runtime._epoch)
            await runtime.ingest(runtime._epoch, incoming)
            await runtime.advance(runtime._epoch)
            assert len(provider.calls) == (1 if order == 'newer' else 0)
            with database.session() as db:
                now = list(db.execute(text('SELECT id,payload_json,payload_sha256 FROM task_inbox_events ORDER BY rowid')))
                assert now[:len(original)] == original and len(now) == len(original) + 1
                assert len(drafts.list_drafts(actor, cid, db).items) == 1
        finally:
            await close(runtime, manager)
    asyncio.run(scenario())


def test_personal_same_original_batch_can_resume_without_source_metadata(world):
    async def scenario():
        runtime, wire, manager, provider, _ = await setup_runtime(world)
        try:
            await runtime.ingest(runtime._epoch, packet(file_message(wire, 9),
                command(1), command(2, '暂停'), command(3, '继续')))
            await runtime.advance(runtime._epoch)
            assert len(provider.calls) == 1
            assert provider.calls[0].basis.manifest.question == '请审查合同'
        finally:
            await close(runtime, manager)
    asyncio.run(scenario())


@pytest.mark.parametrize('new_stop', [False, True])
def test_desktop_resume_is_explicit_and_does_not_cover_later_stop(world, new_stop):
    async def scenario():
        runtime, wire, manager, provider, actor = await setup_runtime(world)
        database = world[0]; cid = world[2].scope.conversation_id
        try:
            await runtime.ingest(runtime._epoch, packet(file_message(wire, 9),
                sequenced_command(1), sequenced_command(3, '暂停'), cursor='held'))
            await runtime.advance(runtime._epoch)
            assert not provider.calls

            def resume():
                with database.session() as db:
                    draft = drafts.list_drafts(actor, cid, db).items[0]
                    drafts.update_draft(actor, draft.id, d.TaskDraftUpdateInput(
                        expected_revision=draft.revision, action='resume'), db)

            resume()
            if new_stop:
                # The existing desktop receipt must not approve an unseen stop,
                # even when another unsequenced "continue" arrives afterwards.
                await runtime.ingest(runtime._epoch, packet(sequenced_command(5, '暂停'), cursor='later-stop'))
                await runtime.ingest(runtime._epoch, packet(command(6, '继续'), cursor='uncertain-resume'))
                await runtime.advance(runtime._epoch)
                assert not provider.calls
                resume()
            await runtime.advance(runtime._epoch)
            assert len(provider.calls) == 1
            assert provider.calls[0].basis.manifest.question == '请审查合同'
            with database.session() as db:
                assert db.scalar(text("SELECT COUNT(*) FROM audit_events WHERE action='task_draft_resumed'")) == (2 if new_stop else 1)
                from cn_contract.task_drafts.integrity import validate_task_records
                from cn_contract.assistant.model_integrity import validate_model_records
                validate_task_records(db)
                validate_model_records(db)
            await runtime.advance(runtime._epoch)
            assert len(provider.calls) == 1
        finally:
            await close(runtime, manager)
    asyncio.run(scenario())
