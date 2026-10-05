"""Thin routes over the existing working-draft/current bundle services."""
from uuid import UUID
from fastapi import Request

from .. import domain as d
from ..exports.draft_confirmation import confirm_working_draft, read_working_draft_confirmation


def register_routes(app, database, authenticate_first, body_input, write):
    from .app import actor_in

    @app.post('/api/matters/{matter_id}/working-draft-confirmations', status_code=201)
    async def confirm_api(matter_id: UUID, request: Request):
        authenticate_first(request, matter_id, 'confirm_facts')
        value = await body_input(request, d.WorkingDraftConfirmationInput)
        return write(request, matter_id, 'working_draft_confirm', value,
            lambda actor, db: confirm_working_draft(matter_id, value, actor, db=db))

    @app.get('/api/matters/{matter_id}/working-draft-confirmations/{identifier}')
    def confirmation_api(matter_id: UUID, identifier: UUID, request: Request):
        with database.session() as db:
            actor = actor_in(request, db, matter_id)
            return read_working_draft_confirmation(matter_id, identifier, actor, db=db)
