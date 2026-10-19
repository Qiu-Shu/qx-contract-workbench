"""Bounded message-to-attempt lookup under the conversation's current binding."""
from uuid import UUID

from sqlalchemy import bindparam, text

from ... import domain as d
from ...security import ServiceError
from .. import service
from .attempts import read_attempt


def read_history(actor, conversation, query, db):
    scope = service._snapshot(conversation)
    rows = db.execute(text('''SELECT m.id,a.id AS attempt_id FROM assistant_messages m
        LEFT JOIN assistant_runs r ON r.message_id=m.id AND r.conversation_id=m.conversation_id
        LEFT JOIN assistant_model_attempts a ON a.run_id=r.id AND a.conversation_id=m.conversation_id
        WHERE m.conversation_id=:cid AND m.id IN :messages''').bindparams(bindparam('messages', expanding=True)),
        {'cid':conversation['id'], 'messages':[str(value) for value in query.message_ids]}).mappings().all()
    if len(rows) != len(query.message_ids):
        raise ServiceError('CROSS_MATTER_DENIED', 403)
    found = {row['id']:row['attempt_id'] for row in rows}
    results = []
    for message_id in query.message_ids:
        attempt_id = found[str(message_id)]
        if attempt_id is None:
            continue
        attempt = read_attempt(actor, UUID(attempt_id), db)
        # Input/material revisions advance with conversation history; case binding must not.
        binding = ('workspace_id', 'conversation_id', 'scope_kind', 'scope_ref', 'binding_revision')
        if any(getattr(attempt.scope, key) != getattr(scope, key) for key in binding):
            raise ServiceError('CROSS_MATTER_DENIED', 403)
        results.append(d.MainGenerationHistoryItem(message_id=message_id, attempt=attempt))
    return d.MainGenerationHistoryView(scope=scope, items=tuple(results))
