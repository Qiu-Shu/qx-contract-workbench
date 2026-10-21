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
    token, prepared, config = claimed
    request = prepared.request
    reply_type = d.MainContextReply if type(request) is d.MainContextRequest else d.MainReply
    cancelled = False
    try:
        async with asyncio.timeout(config.timeout_seconds):
            if type(prepared) is d.MainContextRoundsPreparedInput:
                generate_rounds = getattr(runtime.provider, 'generate_rounds', None)
                if not callable(generate_rounds):
                    raise ValueError('rounds provider required')
                reply = await generate_rounds(prepared, expected_config=config)
            elif type(request) is d.MainContextRequest:
                generate_context = getattr(runtime.provider, 'generate_context', None)
                if callable(generate_context):
                    reply = await generate_context(request, expected_config=config)
                else:
                    # Registry leases dispatch context sends inside generate().
                    reply = await runtime.provider.generate(request, expected_config=config)
            else:
                reply = await runtime.provider.generate(request, expected_config=config)
            reply = reply_type.model_validate(reply.model_dump(mode='python'))
    except asyncio.CancelledError:
        cancelled = True
        reply = reply_type(state='sent_unknown', error_code='PROVIDER_ERROR')
    except Exception:
        reply = reply_type(state='sent_unknown', error_code='PROVIDER_ERROR')
    with database.session() as db:
        attempts.settle(actor, identifier, token, reply, db, runtime)
    if cancelled:
        raise asyncio.CancelledError()
    with database.session() as db:
        return attempts.read_attempt(actor, identifier, db)
