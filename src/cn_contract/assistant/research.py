"""Explicit, single local-library searches sharing the conversation run lifecycle."""
from uuid import UUID, uuid4

from sqlalchemy import bindparam, text
from sqlalchemy.exc import SQLAlchemyError

from .. import domain as d
from ..config import canonical_json
from ..ops.storage import require_active
from ..security import ServiceError
from . import library_handlers as handlers, service
from .attachment_records import items
from .research_records import initial_call


_ACTIVE = {'queued', 'retrieving'}
_ERRORS = {'AUTHORIZATION_REQUIRED', 'CROSS_MATTER_DENIED', 'VERSION_CONFLICT', 'BLOCKED_LIVE',
    'STATE_CONFLICT', 'RESTORED_READ_ONLY', 'LIBRARY_RECORD_INVALID', 'LIBRARY_QUERY_INVALID',
    'LIBRARY_NOT_CONFIGURED', 'LIBRARY_GENERATION_STALE', 'LIBRARY_SOURCE_UNAVAILABLE',
    'LIBRARY_CITATION_INVALID', 'LIBRARY_CITATION_MISMATCH'}


def _append(run_id, event_type, payload, db):
    sequence = db.scalar(text('SELECT COALESCE(MAX(seq),0)+1 FROM assistant_run_events WHERE run_id=:id'),
        {'id':str(run_id)})
    db.execute(text('''INSERT INTO assistant_run_events(run_id,seq,event_type,audience,payload_json,created_at)
        VALUES(:id,:seq,:type,'internal',:payload,:at)'''), {'id':str(run_id), 'seq':sequence,
        'type':event_type, 'payload':canonical_json(payload), 'at':service._at()})


def _initial(row, db, *, required=True):
    """A skill label or old queued message alone is never dispatch authority."""
    events = db.execute(text('''SELECT * FROM assistant_run_events WHERE run_id=:run
        ORDER BY seq'''),
        {'run':row['id']}).mappings().all()
    content = db.scalar(text('SELECT content FROM assistant_messages WHERE id=:id'),
        {'id':row['message_id']})
    try:
        call = initial_call(row, content, events)
        if call is None and required:
            raise ServiceError('STATE_CONFLICT', 409)
        return call
    except (ValueError, TypeError):
        raise ServiceError('LIBRARY_RECORD_INVALID', 409) from None


def read_research(actor, run_id, db):
    row, scope = handlers._history_run(actor, run_id, db)
    call = _initial(row, db)
    receipt = handlers._receipt(call, db)
    if receipt is not None and receipt.scope != scope:
        raise ServiceError('LIBRARY_RECORD_INVALID', 409)
    if row['state'] == 'completed' and receipt is None:
        raise ServiceError('LIBRARY_RECORD_INVALID', 409)
    return d.AssistantResearchView(run=service._run_summary(row, db),
        receipts=(receipt,) if receipt is not None else ())


def find_research(actor, conversation_id, request_id, db):
    service._owned(actor, conversation_id, db)
    identifier = db.scalar(text('''SELECT id FROM assistant_runs
        WHERE conversation_id=:cid AND request_id=:request'''),
        {'cid':str(conversation_id), 'request':str(request_id)})
    return read_research(actor, UUID(identifier), db) if identifier else None


def enqueue_research(actor, conversation_id, request, db):
    request = d.AssistantMessageInput.model_validate(request.model_dump(mode='python'))
    conversation = service._owned(actor, conversation_id, db)
    require_active(db)
    if request.requested_skill != 'legal_research' or request.attachment_ids:
        raise ServiceError('NOT_SUPPORTED', 422)
    try:
        query = d.AssistantLibraryQuery(text=request.content, limit=5)
        if len(request.content) > 200:
            raise ValueError('keyword length')
    except (ValueError, TypeError):
        raise ServiceError('LIBRARY_TOOL_INPUT_INVALID', 422) from None
    previous = find_research(actor, conversation_id, request.request_id, db)
    if previous is not None:
        service.save_message(actor, conversation_id, request, db)
        return previous
    if items(conversation, db):
        raise ServiceError('NOT_SUPPORTED', 422)
    try:
        with db.begin_nested():
            run = service.save_message(actor, conversation_id, request, db)
            accepted = d.AssistantResearchAccepted(call_id=uuid4(), request_sha256=run.request_sha256)
            _append(run.id, 'research.accepted', accepted.model_dump(mode='json'), db)
            handlers.begin_library_call_in_session(actor, run.id, accepted.call_id,
                d.LibraryHandlerRequest(tool='legal_library.search', query=query), db)
            return read_research(actor, run.id, db)
    except SQLAlchemyError:
        raise ServiceError('LIBRARY_RECORD_INVALID', 409) from None


def read_history(actor, conversation, query, db):
    query = d.MainGenerationHistoryQuery.model_validate(query.model_dump(mode='python'))
    conversation = service._owned(actor, UUID(conversation['id']), db)
    rows = db.execute(text('''SELECT m.id,r.id AS run_id FROM assistant_messages m
        LEFT JOIN assistant_runs r ON r.message_id=m.id AND r.conversation_id=m.conversation_id
        WHERE m.conversation_id=:cid AND m.id IN :messages''').bindparams(bindparam('messages', expanding=True)),
        {'cid':conversation['id'], 'messages':[str(value) for value in query.message_ids]}).mappings().all()
    if len(rows) != len(query.message_ids):
        raise ServiceError('CROSS_MATTER_DENIED', 403)
    found = {row['id']:row['run_id'] for row in rows}
    results = []
    for message_id in query.message_ids:
        run_id = found[str(message_id)]
        if run_id is None:
            continue
        row = db.execute(text('SELECT * FROM assistant_runs WHERE id=:run'),
            {'run':run_id}).mappings().one()
        if _initial(row, db, required=False) is not None:
            results.append(d.AssistantResearchHistoryItem(message_id=message_id,
                research=read_research(actor, UUID(run_id), db)))
    return d.AssistantResearchHistoryView(scope=service._snapshot(conversation), items=tuple(results))


def _seal(run_id, db, *, interrupted=False, code='LOCAL_RESEARCH_FAILED'):
    try:
        require_active(db)
    except ServiceError as error:
        if error.code == 'BLOCKED_LIVE':
            return
        raise
    row = db.execute(text('SELECT * FROM assistant_runs WHERE id=:id'),
        {'id':str(run_id)}).mappings().first()
    if row is None or row['state'] not in _ACTIVE:
        return
    _initial(row, db)
    state = 'cancelled' if row['cancel_requested'] else 'interrupted' if interrupted else 'failed'
    db.execute(text('UPDATE assistant_runs SET state=:state WHERE id=:id'),
        {'id':str(run_id), 'state':state})
    _append(run_id, 'research.' + state, {'state':state,
        'error_code':code if code in _ERRORS else 'LOCAL_RESEARCH_FAILED'}, db)


def interrupt_research(run_id, db):
    """Trusted lifecycle cleanup only; no stale user credentials can authorize I/O."""
    _seal(run_id, db, interrupted=True)


def execute_research(actor, run_id, database, adapter):
    try:
        with database.session() as db:
            row, _ = handlers._history_run(actor, run_id, db)
            call = _initial(row, db)
            if row['state'] not in _ACTIVE:
                return read_research(actor, run_id, db)
            if row['state'] != 'queued':
                raise ServiceError('ASSISTANT_BUSY', 409)
            handlers._execution(actor, run_id, db, call.payload)
            db.execute(text("UPDATE assistant_runs SET state='retrieving' WHERE id=:id"), {'id':str(run_id)})
            _append(run_id, 'research.started', {'state':'retrieving'}, db)
    except ServiceError as error:
        if error.code != 'ASSISTANT_BUSY':
            with database.session() as db:
                owned = db.scalar(text('''SELECT COUNT(*) FROM assistant_runs
                    WHERE id=:id AND actor_id=:actor AND session_id=:session'''),
                    {'id':str(run_id), 'actor':str(actor.user_id), 'session':str(actor.session_id)})
                if owned:
                    _seal(run_id, db, code=error.code)
        raise
    try:
        handlers.execute_library_handler(actor, run_id, call.event_seq, database, adapter)
        with database.session() as db:
            handlers._execution(actor, run_id, db, call.payload)
            db.execute(text("UPDATE assistant_runs SET state='completed' WHERE id=:id"), {'id':str(run_id)})
            _append(run_id, 'research.completed', {'state':'completed'}, db)
            return read_research(actor, run_id, db)
    except Exception as error:
        code = error.code if isinstance(error, ServiceError) and error.code in _ERRORS else 'LOCAL_RESEARCH_FAILED'
        with database.session() as db:
            _seal(run_id, db, code=code)
        raise ServiceError(code, error.status_code if isinstance(error, ServiceError) else 409) from None
