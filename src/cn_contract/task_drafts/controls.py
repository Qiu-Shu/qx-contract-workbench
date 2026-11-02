"""Hash-only receipts for an owner's explicit desktop resume; no wire authority."""
from datetime import datetime, timezone
import json
from uuid import uuid4
from sqlalchemy import text
from .. import domain as d
from ..audit import append_event
from ..assistant import business


def _fingerprint(actor, draft, db):
    from . import service
    controls = []
    for row in service._events(draft.id, db):
        value = service._payload(row)
        if service._control(value) or business.negative_only(value.text):
            controls.append((row['id'], row['payload_sha256']))
    return service._digest({'draft_id':str(draft.id), 'conversation_id':str(draft.conversation_id),
        'actor_id':str(actor.user_id), 'controls':controls})


def record_resume(actor, draft, db):
    # audit_events targets are identifiers, not foreign keys to real matters.
    # The explicit entity_type keeps a conversation target distinct from a case.
    append_event(d.AuditEvent(id=uuid4(), matter_id=draft.conversation_id,
        actor_id=actor.user_id, action='task_draft_resumed', entity_type='task_draft',
        entity_id=draft.id, before_hash=None, after_hash=_fingerprint(actor, draft, db),
        timestamp=datetime.now(timezone.utc), reason='explicit_desktop_resume', correlation_id=uuid4()), db)


def confirmed_resume(actor, draft, db):
    expected = _fingerprint(actor, draft, db)
    rows = db.scalars(text('''SELECT payload FROM audit_events WHERE action='task_draft_resumed'
        AND matter_id=:cid AND actor_id=:actor'''),
        {'cid':str(draft.conversation_id), 'actor':str(actor.user_id)})
    for raw in rows:
        value = json.loads(raw)
        if (value.get('entity_type') == 'task_draft' and value.get('entity_id') == str(draft.id)
                and value.get('after_hash') == expected):
            return True
    return False
