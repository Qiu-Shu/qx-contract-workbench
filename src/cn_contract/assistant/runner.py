"""One explicit attempt; network awaits never retain a database session."""
import asyncio

from .. import domain as d
from .providers import attempts


async def execute_attempt(actor, identifier, database, runtime):
    # Recheck stored originals outside the write transaction immediately before claim.
    with database.session() as db:
        row = attempts._row(identifier, db)
        material = row['input_format'] == 'material-business-v1' and row['state'] == 'reserved'
        if material:
            from . import material_preparation as inputs
            prepared = attempts._input(row)
            _, files = inputs.assemble(actor, inputs.selection_for(prepared.request.basis), db, historical=True)
    if material:
        from .attachment_files import read_checked
        try:
            for file in files:
                read_checked(file, database)
        except Exception:
            with database.session() as db:
                attempts._abandon_unsent(attempts._row(identifier, db), db)
                return attempts.read_attempt(actor, identifier, db)
    with database.session() as db:
        claimed = attempts.claim(actor, identifier, db, runtime)
    if claimed is None:
        with database.session() as db:
            return attempts.read_attempt(actor, identifier, db)
    token, prepared, config = claimed
    request = prepared.request
    source_preflight = None
    if type(prepared) is d.MainMaterialPreparedInput:
        from . import material_attempts, material_preparation as inputs
        from .attachment_files import read_checked
        def source_preflight():
            try:
                with database.session() as db:
                    row = attempts._row(identifier, db)
                    material_attempts.current(actor, row, db, runtime)
                    _, files = inputs.assemble(actor, inputs.selection_for(prepared.request.basis), db, historical=True)
                for file in files:
                    read_checked(file, database)
                return True
            except Exception:
                return False
    reply_type = (d.MainMaterialReply if type(prepared) is d.MainMaterialPreparedInput else d.MainProfileReply if type(prepared) is d.MainProfilePreparedInput
                  else d.MainContextReply if type(request) is d.MainContextRequest else d.MainReply)
    cancelled = False
    try:
        async with asyncio.timeout(config.timeout_seconds):
            if type(prepared) is d.MainMaterialPreparedInput:
                reply = await runtime.provider.generate_material(prepared, expected_config=config,
                    source_preflight=source_preflight)
            elif type(prepared) is d.MainProfilePreparedInput:
                generate_profile = getattr(runtime.provider, 'generate_profile', None)
                if not callable(generate_profile):
                    raise ValueError('profile provider required')
                reply = await generate_profile(prepared, expected_config=config)
            elif type(prepared) is d.MainContextRoundsPreparedInput:
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
