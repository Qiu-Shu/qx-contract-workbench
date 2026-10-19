"""Independent shared-process logging lifetime/isolation probes, no network."""
import asyncio
import logging
import pytest
from cn_contract.assistant.providers import main, jev


def record(name='httpx2.spec'):
    return logging.getLogger(name).makeRecord(name,logging.INFO,__file__,1,
        'SYNTHETIC_PRIVATE_BODY %s',('SYNTHETIC_PRIVATE_KEY',),None)


@pytest.mark.parametrize('modules',[(main,jev),(jev,main)],ids=['main-then-jev','jev-then-main'])
def test_installation_is_idempotent_in_both_provider_orders(modules):
    original=logging.getLogRecordFactory()
    try:
        # Allow both registration orders to propagate earlier wrapper markers.
        for _ in range(2):
            for module in modules:module._protect_logs()
        installed=logging.getLogRecordFactory()
        for _ in range(32):
            for module in modules:module._protect_logs()
        assert logging.getLogRecordFactory() is installed
    finally:logging.setLogRecordFactory(original)


def test_repeated_main_auxiliary_use_cannot_overflow_global_logging_stack():
    original=logging.getLogRecordFactory()
    try:
        for _ in range(602):
            main._protect_logs();jev._protect_logs()
        value=record('independent.safe.logger')
        assert value.getMessage()=='SYNTHETIC_PRIVATE_BODY SYNTHETIC_PRIVATE_KEY'
    finally:logging.setLogRecordFactory(original)


def test_main_jev_and_unrelated_async_contexts_remain_independent():
    original=logging.getLogRecordFactory()
    async def in_context(module):
        token=module._private.set(True)
        try:
            await asyncio.sleep(.01)
            hidden=record()
            assert 'SYNTHETIC' not in hidden.getMessage() and hidden.args==()
            visible=record('independent.safe.logger')
            assert 'SYNTHETIC' in visible.getMessage()
        finally:module._private.reset(token)
    async def without_context():
        await asyncio.sleep(.01)
        assert 'SYNTHETIC' in record().getMessage()
    async def run():await asyncio.gather(in_context(main),in_context(jev),without_context())
    try:
        main._protect_logs();jev._protect_logs()
        asyncio.run(run())
        assert 'SYNTHETIC' in record().getMessage()
    finally:logging.setLogRecordFactory(original)
