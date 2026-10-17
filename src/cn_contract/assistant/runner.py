"""One explicit attempt; network awaits never retain a database session."""
import asyncio

from .. import domain as d
from .providers import attempts


async def execute_attempt(actor, identifier, database, runtime):
    with database.session() as db:
        claimed = attempts.claim(actor, identifier, db, runtime)
    if claimed is None:
        with database.session() as db:
            return attempts.read_attempt(actor, identifier, db)
    token, request, config = claimed
    cancelled = False
    try:
        async with asyncio.timeout(config.timeout_seconds):
            reply = await runtime.provider.generate(request, expected_config=config)
            reply = d.MainReply.model_validate(reply.model_dump(mode='python'))
    except asyncio.CancelledError:
        cancelled = True
        reply = d.MainReply(state='sent_unknown', error_code='PROVIDER_ERROR')
    except Exception:
        reply = d.MainReply(state='sent_unknown', error_code='PROVIDER_ERROR')
    with database.session() as db:
        attempts.settle(actor, identifier, token, reply, db, runtime)
    if cancelled:
        raise asyncio.CancelledError()
    with database.session() as db:
        return attempts.read_attempt(actor, identifier, db)
