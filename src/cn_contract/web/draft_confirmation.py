"""Thin routes over the existing working-draft/current bundle services."""
from uuid import UUID
from fastapi import Request

from .. import domain as d
from ..exports.draft_confirmation import confirm_working_draft, read_working_draft_confirmation


def register_routes(app, database, authenticate_first, body_input, write):
    from .request_context import actor_in
    from ..exports.effective_text import read_effective_text, record_effective_review, read_effective_review

    @app.get('/api/matters/{matter_id}/bundles/{bundle_id}/effective-text')
    def effective_text_api(matter_id: UUID, bundle_id: UUID, request: Request):
        with database.session() as db:
            actor = actor_in(request, db, matter_id)
            return read_effective_text(matter_id, bundle_id, actor, db=db)

    @app.post('/api/matters/{matter_id}/effective-text-reviews', status_code=201)
    async def effective_review_api(matter_id: UUID, request: Request):
        authenticate_first(request, matter_id, 'confirm_facts')
        value = await body_input(request, d.EffectiveTextReviewInput)
        return write(request, matter_id, 'effective_text_review', value,
            lambda actor, db: record_effective_review(matter_id, value, actor, db=db))

    @app.get('/api/matters/{matter_id}/effective-text-reviews/{identifier}')
    def effective_review_read_api(matter_id: UUID, identifier: UUID, request: Request):
        with database.session() as db:
            actor = actor_in(request, db, matter_id)
            return read_effective_review(matter_id, identifier, actor, db=db)

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
