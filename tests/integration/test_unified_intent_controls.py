"""Exercise real journals and generation ledgers using only mock transports."""
import asyncio
import pytest
from sqlalchemy import text
from tests.integration.test_assistant_generation import world
from tests.integration.test_weixin_service_runtime import setup, later
from tests.integration.test_weixin_personal_runtime import close, packet, command, file_message


@pytest.mark.parametrize('message', [
    '新事项：暂时不审查合同，只接收材料',
    '新事项：不再审查合同，只接收材料',
    '新事项：请审查合同，先别分析',
    '新事项：请审查合同，只接收材料',
    '新事项：如果材料齐全，请审查合同',
    '新事项：对方说请审查合同',
])
def test_hold_keeps_original_without_any_model(world, message):
    async def scenario():
        runtime, wire, manager, main, actor = await setup(world)
        class ForbiddenJudge:
            async def assess(self, *args, **kwargs):
                pytest.fail('held instructions must not reach an auxiliary model')
        runtime.judge = ForbiddenJudge()
        try:
            await runtime.ingest(runtime._epoch, packet(command(1, message), file_message(wire, 2)))
            await runtime.advance(runtime._epoch, now=later())
            assert main.calls == []
            with world[0].session() as db:
                assert db.scalar(text('SELECT COUNT(*) FROM weixin_service_media')) == 1
                assert db.scalar(text('SELECT COUNT(*) FROM weixin_service_runs')) == 0
                assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0
        finally:
            await close(runtime, manager)
    asyncio.run(scenario())


def test_supplement_release_reuses_task_material_version_and_duplicate_is_once(world):
    async def scenario():
        runtime, wire, manager, main, actor = await setup(world)
        try:
            await runtime.ingest(runtime._epoch, packet(command(1, '新事项：虚构甲事项，请整理材料'), file_message(wire, 2)))
            await runtime.advance(runtime._epoch, now=later())
            assert len(main.calls) == 1
            followup = packet(command(3, '继续整理材料'), file_message(wire, 4, '虚构补件.docx'),
                command(5, '虚构补充事实：日期待核'), command(6, '可以开始'), cursor='followup')
            await runtime.ingest(runtime._epoch, followup)
            await runtime.advance(runtime._epoch, now=later())
            assert len(main.calls) == 2
            first, second = [call.basis.manifest for call in main.calls]
            assert first.stable_task_id == second.stable_task_id
            assert len(second.materials) == 2
            assert second.materials[0].original_sha256 == first.materials[0].original_sha256
            await runtime.ingest(runtime._epoch, followup)
            await runtime.advance(runtime._epoch, now=later())
            assert len(main.calls) == 2
        finally:
            await close(runtime, manager)
    asyncio.run(scenario())


def test_cancel_then_old_duplicate_and_material_stay_held_until_explicit_restart(world):
    async def scenario():
        runtime, wire, manager, main, actor = await setup(world)
        try:
            old = command(1, '新事项：请整理材料')
            old.update(seq=1, create_time_ms=1000)
            stop = command(3, '停止处理'); stop.update(seq=3, create_time_ms=3000)
            await runtime.ingest(runtime._epoch, packet(old, file_message(wire, 2), stop))
            await runtime.advance(runtime._epoch, now=later())
            assert not main.calls
            await runtime.ingest(runtime._epoch, packet(old, file_message(wire, 4), cursor='late-duplicate'))
            await runtime.advance(runtime._epoch, now=later())
            assert not main.calls
            restart = command(5, '现在重新开始整理材料'); restart.update(seq=5, create_time_ms=5000)
            await runtime.ingest(runtime._epoch, packet(restart, cursor='restart'))
            await runtime.advance(runtime._epoch, now=later())
            assert len(main.calls) == 1
        finally:
            await close(runtime, manager)
    asyncio.run(scenario())


@pytest.mark.parametrize('order', ['older', 'unknown', 'contradictory'])
def test_unseen_old_or_uncertain_restart_never_releases_newer_stop(world, order):
    async def scenario():
        runtime, wire, manager, main, actor = await setup(world)
        try:
            first = command(1, '新事项：请整理材料'); first.update(seq=1, create_time_ms=1000)
            stop = command(3, '停止处理'); stop.update(seq=3, create_time_ms=3000)
            late = command(2, '现在重新开始整理材料')
            if order != 'unknown':
                late.update(seq=2 if order == 'older' else 4, create_time_ms=2000)
            await runtime.ingest(runtime._epoch, packet(first, file_message(wire, 4), stop))
            await runtime.advance(runtime._epoch, now=later())
            assert not main.calls
            await runtime.ingest(runtime._epoch, packet(late, cursor='unseen-older'))
            await runtime.advance(runtime._epoch, now=later())
            assert not main.calls
            with world[0].session() as db:
                assert db.scalar(text('SELECT COUNT(*) FROM weixin_service_events')) == 4
                assert db.scalar(text('SELECT COUNT(*) FROM weixin_service_media')) == 1
        finally:
            await close(runtime, manager)
    asyncio.run(scenario())


@pytest.mark.parametrize('stop_text', ['不再审查合同', '取消审查合同'])
def test_uncertain_restart_cannot_override_workflow_specific_stop(world, stop_text):
    async def scenario():
        runtime, wire, manager, main, actor = await setup(world)
        try:
            await runtime.ingest(runtime._epoch, packet(command(1, '新事项：请审查合同'),
                file_message(wire, 4), command(3, stop_text)))
            await runtime.advance(runtime._epoch, now=later())
            assert not main.calls
            await runtime.ingest(runtime._epoch, packet(command(2, '现在请审查合同'), cursor='late'))
            await runtime.advance(runtime._epoch, now=later())
            assert not main.calls
        finally:
            await close(runtime, manager)
    asyncio.run(scenario())
