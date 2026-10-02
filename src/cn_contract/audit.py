"""Append-only audit serialization with fixed safe fields and hashed free text."""
import hashlib
import json
from uuid import UUID

from sqlalchemy.orm import Session

from .domain import AuditEvent
from .persistence import AuditRow

ALLOWED_ACTIONS = frozenset({'authorization_denied', 'csrf_denied', 'document_created',
                             'parse_saved', 'facts_changed', 'position_changed', 'state_changed', 'baseline_selected'})
ALLOWED_ENTITIES = frozenset({'matter', 'document', 'facts', 'parse'})


def append_event(event: AuditEvent, db: Session) -> UUID:
    if event.action not in ALLOWED_ACTIONS or event.entity_type not in ALLOWED_ENTITIES:
        raise ValueError('unknown audit action/entity type')
    payload = event.model_dump(mode='json')
    payload['reason_sha256'] = hashlib.sha256(payload.pop('reason').encode('utf-8')).hexdigest()
    db.add(AuditRow(id=str(event.id), matter_id=str(event.matter_id), actor_id=str(event.actor_id),
                    action=event.action, payload=json.dumps(payload, sort_keys=True, separators=(',', ':'))))
    db.flush()
    return event.id
