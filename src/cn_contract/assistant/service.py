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


def create_conversation(actor, request: d.AssistantConversationCreateInput, db, *, page_size=None):
    if page_size is not None:
        d.AssistantMessagePageQuery(limit=page_size)
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
        identifier = UUID(previous['id'])
        return (read_conversation(current, identifier, db) if page_size is None else
                read_conversation_page(current, identifier, db, limit=page_size))
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
    return (read_conversation(current, identifier, db) if page_size is None else
            read_conversation_page(current, identifier, db, limit=page_size))


def read_conversation(actor, identifier, db):
    row = _owned(actor, identifier, db)
    messages = db.execute(text('''SELECT id,role,content,source_revision,created_at
        FROM assistant_messages WHERE conversation_id=:id ORDER BY rowid'''),
        {'id':str(identifier)}).mappings().all()
    return d.AssistantConversationView(scope=_snapshot(row), display_title=row['display_title'],
        composer_revision=row['composer_revision'], draft_input=row['draft_input'],
        projection_intake_id=row['projection_intake_id'], created_at=row['created_at'],
        archived_at=row['archived_at'], messages=tuple(d.AssistantMessageView(**message) for message in messages))


def _run_summary(row, db):
    last_event_seq = db.scalar(text('SELECT COALESCE(MAX(seq),0) FROM assistant_run_events WHERE run_id=:id'),
                               {'id':row['id']})
    return d.AssistantRunSummary(id=row['id'], message_id=row['message_id'], request_id=row['request_id'],
        request_sha256=row['request_sha256'], scope=d.ScopeSnapshot.model_validate_json(row['scope_snapshot']),
        state=row['state'], requested_skill=row['requested_skill'], cancel_requested=bool(row['cancel_requested']),
        created_at=row['created_at'], last_event_seq=last_event_seq)


def read_conversation_page(actor, identifier, db, *, before=None, limit=50):
    query = d.AssistantMessagePageQuery(before=before, limit=limit)
    row = _owned(actor, identifier, db)
    parameters = {'id':str(identifier), 'limit':query.limit + 1}
    boundary = ''
    if query.before is not None:
        anchor = db.scalar(text('SELECT rowid FROM assistant_messages WHERE id=:message AND conversation_id=:id'),
                           {**parameters, 'message':str(query.before)})
        if anchor is None:
            raise ServiceError('CROSS_MATTER_DENIED', 403)
        boundary = ' AND rowid<:before'
        parameters['before'] = anchor
    messages = db.execute(text('''SELECT id,role,content,source_revision,created_at
        FROM assistant_messages WHERE conversation_id=:id''' + boundary +
        ' ORDER BY rowid DESC LIMIT :limit'), parameters).mappings().all()
    latest = db.execute(text('''SELECT * FROM assistant_runs WHERE conversation_id=:id
        ORDER BY rowid DESC LIMIT 1'''), {'id':str(identifier)}).mappings().first()
    return d.AssistantConversationPageView(scope=_snapshot(row), display_title=row['display_title'],
        composer_revision=row['composer_revision'], draft_input=row['draft_input'],
        projection_intake_id=row['projection_intake_id'], created_at=row['created_at'], archived_at=row['archived_at'],
        messages=tuple(d.AssistantMessageView(**message) for message in reversed(messages[:query.limit])),
        next_before=messages[query.limit-1]['id'] if len(messages) > query.limit else None,
        latest_run=_run_summary(latest, db) if latest else None)


def find_run(actor, conversation_id, request_id, db):
    _owned(actor, conversation_id, db)
    row = db.execute(text('''SELECT * FROM assistant_runs
        WHERE conversation_id=:conversation AND request_id=:request'''),
        {'conversation':str(conversation_id), 'request':str(request_id)}).mappings().first()
    return _run_summary(row, db) if row else None


def list_conversations(actor, db, *, cursor=None, limit=20):
    query = d.AssistantConversationQuery(cursor=cursor, limit=limit)
    current = _current(actor, db)
    parameters = {'owner':str(current.user_id), 'workspace':str(_workspace_id(db)), 'limit':query.limit}
    boundary = ''
    if query.cursor is not None:
        anchor = db.execute(text('''SELECT id,created_at FROM assistant_conversations
            WHERE id=:id AND owner_id=:owner AND workspace_id=:workspace'''),
            {**parameters, 'id':str(query.cursor)}).mappings().first()
        if anchor is None:
            raise ServiceError('CROSS_MATTER_DENIED', 403)
        # A formerly accessible row can still advance the owner's scan after revocation.
        boundary = ' AND (created_at<:at OR (created_at=:at AND id<:id))'
        parameters.update(at=anchor['created_at'], id=anchor['id'])
    rows = db.execute(text('''SELECT id FROM assistant_conversations
        WHERE owner_id=:owner AND workspace_id=:workspace AND archived_at IS NULL''' + boundary +
        ' ORDER BY created_at DESC,id DESC LIMIT :limit'), parameters).all()
    items = []
    for identifier, in rows:
        try:
            row = _owned(current, identifier, db)
        except ServiceError as error:
            if error.code != 'CROSS_MATTER_DENIED':
                raise
            continue
        items.append(d.AssistantConversationSummary(scope=_snapshot(row), display_title=row['display_title'],
            composer_revision=row['composer_revision'], created_at=row['created_at'], archived_at=row['archived_at']))
    return d.AssistantConversationPage(items=tuple(items),
        next_cursor=rows[-1][0] if len(rows) == query.limit else None)


def archive_conversation(actor, identifier, request, db, *, require_disconnected=None):
    request = d.AssistantArchiveInput.model_validate(request.model_dump(mode='python'))
    row = _owned(actor, identifier, db)
    require_active(db)
    if (request.expected_scope != _snapshot(row)
            or request.expected_composer_revision != row['composer_revision']):
        raise ServiceError('VERSION_CONFLICT', 409)
    if row['archived_at'] is not None:
        return read_conversation(actor, identifier, db)
    if db.scalar(text('''SELECT 1 FROM assistant_runs WHERE conversation_id=:id
            AND state IN ('queued','preparing','routing','retrieving','generating','persisting')'''),
            {'id':str(identifier)}):
        raise ServiceError('ASSISTANT_BUSY', 409)
    if inspect(db.connection()).has_table('task_executions') and db.scalar(text('''
            SELECT 1 FROM task_executions e JOIN task_drafts t ON t.id=e.draft_id
            WHERE t.conversation_id=:id AND e.state IN ('creating_matter','queued','running')'''),
            {'id':str(identifier)}):
        raise ServiceError('ASSISTANT_BUSY', 409)
    # No await between the target runtime guard and this transaction's archive write.
    if require_disconnected is not None:
        require_disconnected(identifier)
    db.execute(text('UPDATE assistant_conversations SET archived_at=:at WHERE id=:id'),
        {'id':str(identifier), 'at':_at()})
    return read_conversation(actor, identifier, db)


def save_draft(actor, identifier, request: d.AssistantDraftInput, db, *, page_size=None):
    if page_size is not None:
        d.AssistantMessagePageQuery(limit=page_size)
    request = d.AssistantDraftInput.model_validate(request.model_dump(mode='python'))
    row = _owned(actor, identifier, db)
    require_active(db)
    _expected(row, request)
    db.execute(text('''UPDATE assistant_conversations SET draft_input=:content,
        composer_revision=composer_revision+1 WHERE id=:id'''),
        {'id':str(identifier), 'content':request.content})
    return (read_conversation(actor, identifier, db) if page_size is None else
            read_conversation_page(actor, identifier, db, limit=page_size))


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


def _owned_run(actor, identifier, db):
    _current(actor, db)
    row = db.execute(text('SELECT * FROM assistant_runs WHERE id=:id'),
                     {'id':str(identifier)}).mappings().first()
    if row is None:
        raise ServiceError('CROSS_MATTER_DENIED', 403)
    _owned(actor, UUID(row['conversation_id']), db)
    return row


def _event(event):
    return d.AssistantRunEvent(seq=event['seq'], event_type=event['event_type'], audience=event['audience'],
        payload=json.loads(event['payload_json']), created_at=event['created_at'])


def get_run(actor, identifier, db):
    row = _owned_run(actor, identifier, db)
    events = db.execute(text('''SELECT seq,event_type,audience,payload_json,created_at
        FROM assistant_run_events WHERE run_id=:id ORDER BY seq'''),
        {'id':str(identifier)}).mappings().all()
    return d.AssistantRunView(id=row['id'], message_id=row['message_id'], request_id=row['request_id'],
        request_sha256=row['request_sha256'], scope=d.ScopeSnapshot.model_validate_json(row['scope_snapshot']),
        state=row['state'], requested_skill=row['requested_skill'], selected_provider=row['selected_provider'],
        selected_model=row['selected_model'], cancel_requested=bool(row['cancel_requested']), created_at=row['created_at'],
        events=tuple(_event(event) for event in events))


def cancel_run(actor, identifier, request: d.AssistantCancelInput, db):
    request = d.AssistantCancelInput.model_validate(request.model_dump(mode='python'))
    row = _owned_run(actor, identifier, db)
    require_active(db)
    active = {'queued', 'preparing', 'routing', 'retrieving', 'generating', 'persisting', 'awaiting_input'}
    if row['state'] not in active or row['cancel_requested']:
        return get_run(actor, identifier, db)
    if _owned(actor, UUID(row['conversation_id']), db)['archived_at'] is not None:
        raise ServiceError('VERSION_CONFLICT', 409)
    state = 'cancelled' if row['state'] in {'queued', 'awaiting_input'} else row['state']
    event_type = 'run.cancelled' if state == 'cancelled' else 'run.cancel_requested'
    with db.begin_nested():
        db.execute(text('UPDATE assistant_runs SET state=:state,cancel_requested=1 WHERE id=:id'),
            {'id':str(identifier), 'state':state})
        sequence = db.scalar(text('SELECT COALESCE(MAX(seq),0)+1 FROM assistant_run_events WHERE run_id=:id'),
                             {'id':str(identifier)})
        db.execute(text('''INSERT INTO assistant_run_events (run_id,seq,event_type,audience,payload_json,created_at)
            VALUES (:id,:seq,:type,'internal',:payload,:at)'''),
            {'id':str(identifier), 'seq':sequence, 'type':event_type, 'at':_at(),
             'payload':canonical_json({'request_id':str(request.request_id),
                 'previous_state':row['state'], 'state':state, 'cancel_requested':True})})
        from .providers.attempts import cancel_reserved_for_run
        from .providers.judge_attempts import cancel_reserved_for_run as cancel_judges
        cancel_judges(identifier, db)
        cancel_reserved_for_run(identifier, db)
    return get_run(actor, identifier, db)


def read_events(actor, identifier, db, *, after_seq=0, limit=100):
    query = d.AssistantEventQuery(after_seq=after_seq, limit=limit)
    row = _owned_run(actor, identifier, db)
    parameters = {'id':str(identifier), 'after':query.after_seq, 'limit':query.limit + 1}
    latest = db.scalar(text('SELECT COALESCE(MAX(seq),0) FROM assistant_run_events WHERE run_id=:id'), parameters)
    if query.after_seq > latest:
        raise ServiceError('STATE_CONFLICT', 409)
    if query.after_seq:
        known = db.scalar(text('''SELECT COUNT(*) FROM assistant_run_events
            WHERE run_id=:id AND seq<=:after'''), parameters)
        if known != query.after_seq:
            raise ServiceError('STATE_CONFLICT', 409)
    rows = db.execute(text('''SELECT seq,event_type,audience,payload_json,created_at FROM assistant_run_events
        WHERE run_id=:id AND seq>:after ORDER BY seq LIMIT :limit'''), parameters).mappings().all()
    if any(event['seq'] != query.after_seq + offset for offset, event in enumerate(rows, start=1)):
        raise ServiceError('STATE_CONFLICT', 409)
    events = tuple(_event(event) for event in rows[:query.limit])
    return d.AssistantEventPage(run_id=identifier, conversation_id=row['conversation_id'], state=row['state'],
        events=events, next_after_seq=events[-1].seq if events else query.after_seq,
        has_more=len(rows) > query.limit)


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
