"""Short, caller-owned transactions for local conversation records.

No provider or file I/O occurs here. A queued run is durable intent, not a model
result. The future runner must recheck authorization before any external action.
"""
from datetime import datetime, timezone
import hashlib
import json
from uuid import UUID, uuid4

from sqlalchemy import inspect, text

from .. import domain as d
from ..config import canonical_json
from ..ops.storage import require_active
from ..persistence import SessionRow
from ..security import ServiceError, _principal, authorize


def _current(actor, db):
    db.flush()
    principal = _principal(db.get(SessionRow, str(actor.session_id), populate_existing=True),
                           db, user_id=actor.user_id)
    if principal is None:
        raise ServiceError('AUTHORIZATION_REQUIRED', 401)
    # CH-01 exposes lawyer drafting only; ownership does not grant intake rights.
    if not principal.roles & {d.Role.HANDLING_LAWYER, d.Role.REVIEWING_LAWYER}:
        raise ServiceError('CROSS_MATTER_DENIED', 403)
    return principal


def _workspace_id(db):
    if not inspect(db.connection()).has_table('local_workspace_identity'):
        raise ServiceError('STATE_CONFLICT', 409)
    rows = db.execute(text('SELECT id FROM local_workspace_identity')).all()
    if len(rows) != 1:
        raise ServiceError('STATE_CONFLICT', 409)
    try:
        return UUID(rows[0][0])
    except (ValueError, TypeError):
        raise ServiceError('STATE_CONFLICT', 409) from None


def _intake_access(actor, intake_id, db):
    row = db.execute(text('SELECT owner_id,matter_id FROM intake_cases WHERE id=:id'),
                     {'id':str(intake_id)}).mappings().first()
    if row is None or row['owner_id'] != str(actor.user_id):
        raise ServiceError('CROSS_MATTER_DENIED', 403)
    # Conversion can happen after conversation creation without rebinding it.
    if row['matter_id'] is not None:
        authorize(actor, UUID(row['matter_id']), 'read', db)


def _scope_access(actor, scope_kind, scope_ref, db):
    if scope_kind == 'matter':
        authorize(actor, UUID(str(scope_ref)), 'read', db)
    elif scope_kind == 'intake':
        _intake_access(actor, scope_ref, db)


def _owned(actor, identifier, db):
    current = _current(actor, db)
    row = db.execute(text('SELECT * FROM assistant_conversations WHERE id=:id AND owner_id=:owner'),
        {'id':str(identifier), 'owner':str(current.user_id)}).mappings().first()
    if row is None or row['workspace_id'] != str(_workspace_id(db)):
        raise ServiceError('CROSS_MATTER_DENIED', 403)
    _scope_access(current, row['scope_kind'], row['scope_ref'], db)
    if row['projection_intake_id'] is not None:
        _intake_access(current, row['projection_intake_id'], db)
    return row


def _snapshot(row):
    return d.ScopeSnapshot(workspace_id=row['workspace_id'], conversation_id=row['id'],
        scope_kind=row['scope_kind'], scope_ref=row['scope_ref'],
        binding_revision=row['binding_revision'], input_revision=row['input_revision'],
        materials_revision=row['materials_revision'])


def _expected(row, request):
    if (row['archived_at'] is not None or request.expected_scope != _snapshot(row)
            or request.expected_composer_revision != row['composer_revision']):
        raise ServiceError('VERSION_CONFLICT', 409)


def _digest(value):
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


def _at():
    return datetime.now(timezone.utc).isoformat()


def create_conversation(actor, request: d.AssistantConversationCreateInput, db):
    request = d.AssistantConversationCreateInput.model_validate(request.model_dump(mode='python'))
    current = _current(actor, db)
    require_active(db)
    workspace_id = _workspace_id(db)
    _scope_access(current, request.scope_kind, request.scope_ref, db)
    digest = _digest({'owner_id':str(current.user_id), 'workspace_id':str(workspace_id),
                      'request':request.model_dump(mode='json')})
    previous = db.execute(text('''SELECT id,request_sha256 FROM assistant_conversations
        WHERE owner_id=:owner AND request_id=:request'''),
        {'owner':str(current.user_id), 'request':str(request.request_id)}).mappings().first()
    if previous:
        if previous['request_sha256'] != digest:
            raise ServiceError('VERSION_CONFLICT', 409)
        return read_conversation(current, UUID(previous['id']), db)
    identifier = uuid4()
    db.execute(text('''INSERT INTO assistant_conversations
        (id,workspace_id,owner_id,request_id,request_sha256,scope_kind,scope_ref,
         binding_revision,input_revision,materials_revision,composer_revision,
         display_title,draft_input,created_at)
        VALUES (:id,:workspace,:owner,:request,:digest,:kind,:ref,1,0,0,0,:title,'',:at)'''),
        {'id':str(identifier), 'workspace':str(workspace_id), 'owner':str(current.user_id),
         'request':str(request.request_id), 'digest':digest, 'kind':request.scope_kind,
         'ref':str(request.scope_ref) if request.scope_ref else None,
         'title':request.display_title, 'at':_at()})
    return read_conversation(current, identifier, db)


def read_conversation(actor, identifier, db):
    row = _owned(actor, identifier, db)
    messages = db.execute(text('''SELECT id,role,content,source_revision,created_at
        FROM assistant_messages WHERE conversation_id=:id ORDER BY rowid'''),
        {'id':str(identifier)}).mappings().all()
    return d.AssistantConversationView(scope=_snapshot(row), display_title=row['display_title'],
        composer_revision=row['composer_revision'], draft_input=row['draft_input'],
        projection_intake_id=row['projection_intake_id'], created_at=row['created_at'],
        archived_at=row['archived_at'], messages=tuple(d.AssistantMessageView(**message) for message in messages))


def save_draft(actor, identifier, request: d.AssistantDraftInput, db):
    request = d.AssistantDraftInput.model_validate(request.model_dump(mode='python'))
    row = _owned(actor, identifier, db)
    require_active(db)
    _expected(row, request)
    db.execute(text('''UPDATE assistant_conversations SET draft_input=:content,
        composer_revision=composer_revision+1 WHERE id=:id'''),
        {'id':str(identifier), 'content':request.content})
    return read_conversation(actor, identifier, db)


def save_message(actor, identifier, request: d.AssistantMessageInput, db):
    request = d.AssistantMessageInput.model_validate(request.model_dump(mode='python'))
    row = _owned(actor, identifier, db)
    require_active(db)
    if request.attachment_ids:
        raise ServiceError('NOT_SUPPORTED', 422)
    digest = _digest({'actor_id':str(actor.user_id), 'workspace_id':row['workspace_id'],
        'conversation_id':str(identifier), 'request':request.model_dump(mode='json')})
    previous = db.execute(text('''SELECT id,request_sha256 FROM assistant_runs
        WHERE conversation_id=:conversation AND request_id=:request'''),
        {'conversation':str(identifier), 'request':str(request.request_id)}).mappings().first()
    if previous:
        if previous['request_sha256'] != digest:
            raise ServiceError('VERSION_CONFLICT', 409)
        return get_run(actor, UUID(previous['id']), db)
    active = db.execute(text('''SELECT id FROM assistant_runs WHERE conversation_id=:id
        AND state IN ('queued','preparing','routing','retrieving','generating','persisting')'''),
        {'id':str(identifier)}).first()
    if active:
        raise ServiceError('ASSISTANT_BUSY', 409, retryable=True)
    _expected(row, request)
    message_id, run_id = uuid4(), uuid4()
    timestamp = _at()
    revision = row['input_revision'] + 1
    scope = _snapshot(row).model_copy(update={'input_revision':revision})
    # This savepoint also protects callers that handle an error inside their transaction.
    with db.begin_nested():
        db.execute(text('''INSERT INTO assistant_messages
            (id,conversation_id,role,content,created_at,source_revision)
            VALUES (:id,:conversation,'user',:content,:at,:revision)'''),
            {'id':str(message_id), 'conversation':str(identifier), 'content':request.content,
             'at':timestamp, 'revision':revision})
        db.execute(text('''INSERT INTO assistant_runs
            (id,conversation_id,message_id,actor_id,session_id,request_id,request_sha256,
             scope_snapshot,state,requested_skill,cancel_requested,created_at)
            VALUES (:id,:conversation,:message,:actor,:session,:request,:digest,
                    :scope,'queued',:skill,0,:at)'''),
            {'id':str(run_id), 'conversation':str(identifier), 'message':str(message_id),
             'actor':str(actor.user_id), 'session':str(actor.session_id),
             'request':str(request.request_id), 'digest':digest,
             'scope':canonical_json(scope.model_dump(mode='json')), 'skill':request.requested_skill, 'at':timestamp})
        db.execute(text('''INSERT INTO assistant_run_events
            (run_id,seq,event_type,audience,payload_json,created_at)
            VALUES (:run,1,'message.accepted','internal',:payload,:at)'''),
            {'run':str(run_id), 'at':timestamp,
             'payload':canonical_json({'message_id':str(message_id), 'input_revision':revision, 'state':'queued'})})
        db.execute(text('''UPDATE assistant_conversations SET input_revision=:revision,
            composer_revision=composer_revision+1,draft_input='' WHERE id=:id'''),
            {'id':str(identifier), 'revision':revision})
    return get_run(actor, run_id, db)


def get_run(actor, identifier, db):
    _current(actor, db)
    row = db.execute(text('SELECT * FROM assistant_runs WHERE id=:id'),
                     {'id':str(identifier)}).mappings().first()
    if row is None:
        raise ServiceError('CROSS_MATTER_DENIED', 403)
    _owned(actor, UUID(row['conversation_id']), db)
    events = db.execute(text('''SELECT seq,event_type,audience,payload_json,created_at
        FROM assistant_run_events WHERE run_id=:id ORDER BY seq'''),
        {'id':str(identifier)}).mappings().all()
    return d.AssistantRunView(id=row['id'], message_id=row['message_id'], request_id=row['request_id'],
        request_sha256=row['request_sha256'], scope=d.ScopeSnapshot.model_validate_json(row['scope_snapshot']),
        state=row['state'], requested_skill=row['requested_skill'], selected_provider=row['selected_provider'],
        selected_model=row['selected_model'], cancel_requested=bool(row['cancel_requested']), created_at=row['created_at'],
        events=tuple(d.AssistantRunEvent(seq=event['seq'], event_type=event['event_type'], audience=event['audience'],
            payload=json.loads(event['payload_json']), created_at=event['created_at']) for event in events))


def quarantine_runs(db):
    """Trusted restore maintenance, inside the caller's verified staging transaction."""
    rows = db.execute(text('''SELECT id,state FROM assistant_runs
        WHERE state IN ('queued','preparing','routing','retrieving','generating','persisting','awaiting_input')''')).all()
    for identifier, state in rows:
        sequence = db.scalar(text('SELECT COALESCE(MAX(seq),0)+1 FROM assistant_run_events WHERE run_id=:id'),
                             {'id':identifier})
        db.execute(text("UPDATE assistant_runs SET state='blocked' WHERE id=:id"), {'id':identifier})
        db.execute(text('''INSERT INTO assistant_run_events (run_id,seq,event_type,audience,payload_json,created_at)
            VALUES (:id,:seq,'restore.quarantined','internal',:payload,:at)'''),
            {'id':identifier, 'seq':sequence, 'at':_at(),
             'payload':canonical_json({'previous_state':state, 'reason':'restored_read_only', 'state':'blocked'})})
    return len(rows)
