"""Bounded completed text turns, rebuilt from the same immutable conversation."""
from datetime import datetime
from uuid import UUID

from sqlalchemy import text

from .. import domain as d
from ..security import ServiceError
from .providers.deepseek_protocol import json_bytes

FIXED_SCOPE = ('workspace_id', 'conversation_id', 'scope_kind', 'scope_ref', 'binding_revision')
MAX_TURNS = 8
MAX_BYTES = 32768


def select_history(db, scope, *, budget=MAX_BYTES, before_at=None):
    """Caller authorizes scope; history replay supplies its old revision/time cut."""
    if scope.input_revision == 0 or budget <= 0:
        return ()
    rows = db.execute(text('''SELECT m.id,m.content,m.source_revision,r.scope_snapshot,r.id AS run_id,
        o.run_id AS output_run_id,o.id AS output_id,o.output_json,o.created_at,a.input_format
        FROM assistant_messages m JOIN assistant_runs r ON r.message_id=m.id
        JOIN assistant_model_attempts a ON a.run_id=r.id
        JOIN assistant_model_outputs o ON o.attempt_id=a.id
        WHERE m.conversation_id=:cid AND r.conversation_id=:cid AND o.conversation_id=:cid
        AND m.role='user' AND m.source_revision<=:rev AND r.state='completed'
        AND a.conversation_id=:cid AND o.run_id=r.id AND r.requested_skill IS NULL AND a.state='received' AND a.round_no=1
        AND a.input_format IN ('plain-text-v1','profile-text-v1')
        ORDER BY m.source_revision DESC LIMIT 9'''),
        {'cid':str(scope.conversation_id), 'rev':scope.input_revision}).mappings().all()
    turns = []
    try:
        for row in rows:
            saved = d.ScopeSnapshot.model_validate_json(row['scope_snapshot'])
            if any(getattr(saved, key) != getattr(scope, key) for key in FIXED_SCOPE):
                continue
            if before_at is not None and datetime.fromisoformat(row['created_at']) > before_at:
                continue
            model = d.MainProfileOutputView if row['input_format'] == 'profile-text-v1' else d.MainOutputView
            output = model.model_validate_json(row['output_json'])
            if (output.scope != saved or str(output.id) != row['output_id']
                    or str(output.run_id) != row['run_id'] or row['output_run_id'] != row['run_id']
                    or output.created_at != datetime.fromisoformat(row['created_at'])
                    or saved.input_revision != row['source_revision']):
                raise ValueError('history source mismatch')
            pair = (d.ConversationHistoryMessage(message_id=UUID(row['id']), role='user',
                        source_revision=row['source_revision'], content=row['content']),
                    d.ConversationHistoryMessage(message_id=output.id, role='assistant',
                        source_revision=row['source_revision'], content=output.candidate.text))
            candidate = (*pair, *turns)
            if len(turns) == MAX_TURNS * 2 or len(json_bytes([m.model_dump(mode='json') for m in candidate])) > min(MAX_BYTES, budget):
                break
            turns = list(candidate)
    except (ValueError, TypeError):
        raise ServiceError('VERSION_CONFLICT', 409) from None
    return tuple(turns)


def for_message(db, scope, content, config, *, before_at=None):
    from .providers import profile_codec
    # Leave room for the extra system instruction and message framing. No partial
    # turns or text truncation: the actual included messages are shown at consent.
    budget = config.max_input_bytes - len(json_bytes(profile_codec._text_request(content, config))) - 1024
    return select_history(db, scope, budget=max(0, budget), before_at=before_at)
