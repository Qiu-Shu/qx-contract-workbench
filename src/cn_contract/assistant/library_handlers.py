"""Fixed local-library calls with immutable receipts, without an autonomous runner."""
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .. import domain as d
from ..ops.storage import require_active
from ..security import ServiceError
from . import service
from .library_records import encoded, model, receipt_view, result_citations, sha
from .tools.service import execute_tool


_ACTIVE = {'queued', 'preparing', 'routing', 'retrieving', 'generating', 'persisting'}


def _identifier(value):
    try:
        return value if isinstance(value, UUID) else UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise ServiceError('LIBRARY_TOOL_INPUT_INVALID', 422) from None


def _request(value):
    try:
        value = d.LibraryHandlerRequest.model_validate(value.model_dump(mode='python', warnings=False)
            if isinstance(value, d.LibraryHandlerRequest) else value)
        _bounded(value, 8192)
        return value
    except (ValueError, TypeError):
        raise ServiceError('LIBRARY_TOOL_INPUT_INVALID', 422) from None


def _bounded(value, limit):
    raw = encoded(value)
    if len(raw) > limit:
        raise ValueError('LIBRARY_RECORD_INVALID')
    return raw


def _history_run(actor, run_id, db):
    row = service._owned_run(actor, run_id, db)
    try:
        scope = model(d.ScopeSnapshot, row['scope_snapshot'])
        if str(scope.conversation_id) != row['conversation_id'] or str(scope.workspace_id) != str(service._workspace_id(db)):
            raise ValueError('scope identity')
        if row['actor_id'] != str(actor.user_id):
            raise ValueError('run owner')
        message = db.execute(text('SELECT * FROM assistant_messages WHERE id=:id'),
            {'id':row['message_id']}).mappings().first()
        if (message is None or message['conversation_id'] != row['conversation_id']
                or message['role'] != 'user' or message['source_revision'] != scope.input_revision):
            raise ValueError('run message')
    except (ValueError, TypeError):
        raise ServiceError('LIBRARY_RECORD_INVALID', 409) from None
    service._scope_access(actor, scope.scope_kind, scope.scope_ref, db)
    return row, scope


def _execution(actor, run_id, db, payload=None):
    row, scope = _history_run(actor, run_id, db)
    require_active(db)
    if row['session_id'] != str(actor.session_id):
        raise ServiceError('AUTHORIZATION_REQUIRED', 401)
    if row['state'] not in _ACTIVE or row['cancel_requested']:
        raise ServiceError('STATE_CONFLICT', 409)
    conversation = service._owned(actor, scope.conversation_id, db)
    if conversation['archived_at'] is not None or service._snapshot(conversation) != scope:
        raise ServiceError('VERSION_CONFLICT', 409)
    if payload is not None and (payload.scope != scope or
            payload.expected_composer_revision != conversation['composer_revision']):
        raise ServiceError('VERSION_CONFLICT', 409)
    return row, scope, conversation


def _event(row, run_id):
    try:
        if row is None or row['event_type'] != 'tool.before' or row['audience'] != 'internal':
            raise ValueError('event identity')
        return d.LibraryHandlerCall(run_id=run_id, event_seq=row['seq'],
            payload=model(d.LibraryHandlerEvent, row['payload_json']))
    except (ValueError, TypeError):
        raise ServiceError('LIBRARY_RECORD_INVALID', 409) from None


def _load_call(actor, run_id, event_seq, db):
    _execution(actor, run_id, db)
    row = db.execute(text('SELECT * FROM assistant_run_events WHERE run_id=:run AND seq=:seq'),
        {'run':str(run_id), 'seq':event_seq}).mappings().first()
    call = _event(row, run_id)
    _execution(actor, run_id, db, call.payload)
    return call


def _receipt(call, db):
    row = db.execute(text('''SELECT * FROM assistant_handler_receipts
        WHERE run_id=:run AND event_seq=:seq AND handler_id=:handler AND handler_version=:version'''),
        {'run':str(call.run_id), 'seq':call.event_seq, 'handler':call.payload.handler_id,
         'version':call.payload.handler_version}).mappings().first()
    if row is None:
        return None
    try:
        view = receipt_view(row)
        if (row['payload_sha256'] != sha(encoded(call.payload)) or view.request != call.payload.request
                or view.scope != call.payload.scope):
            raise ValueError('receipt identity')
        citations = db.execute(text('SELECT * FROM assistant_library_citations WHERE receipt_id=:id ORDER BY ordinal'),
            {'id':row['id']}).mappings().all()
        expected = result_citations(view.result.result)
        if len(citations) != len(expected):
            raise ValueError('citation count')
        for ordinal, (stored, citation, identifier) in enumerate(zip(citations, expected, view.result.citation_ids)):
            if (stored['id'] != str(identifier) or stored['ordinal'] != ordinal
                    or stored['citation_json'] != encoded(citation)
                    or stored['citation_sha256'] != sha(stored['citation_json'])
                    or stored['created_at'] != row['created_at']):
                raise ValueError('citation identity')
        return view
    except (ValueError, TypeError):
        raise ServiceError('LIBRARY_RECORD_INVALID', 409) from None


def read_saved_citation(actor, saved_citation_id, db):
    identifier = _identifier(saved_citation_id)
    service._current(actor, db)
    row = db.execute(text('''SELECT c.*,r.run_id,r.event_seq FROM assistant_library_citations c
        JOIN assistant_handler_receipts r ON r.id=c.receipt_id WHERE c.id=:id'''),
        {'id':str(identifier)}).mappings().first()
    if row is None:
        raise ServiceError('CROSS_MATTER_DENIED', 403)
    _, scope = _history_run(actor, UUID(row['run_id']), db)
    event = db.execute(text('SELECT * FROM assistant_run_events WHERE run_id=:run AND seq=:seq'),
        {'run':row['run_id'], 'seq':row['event_seq']}).mappings().first()
    call = _event(event, UUID(row['run_id']))
    receipt = _receipt(call, db)
    if receipt is None or receipt.scope != scope or identifier not in receipt.result.citation_ids:
        raise ServiceError('LIBRARY_RECORD_INVALID', 409)
    ordinal = receipt.result.citation_ids.index(identifier)
    return d.SavedLibraryCitation(id=identifier, receipt_id=receipt.id, run_id=receipt.run_id,
        scope=receipt.scope, citation=result_citations(receipt.result.result)[ordinal], created_at=receipt.created_at)


def _source(actor, run_id, request, db, *, before_seq=None):
    if request.saved_citation_id is None:
        return None
    saved = read_saved_citation(actor, request.saved_citation_id, db)
    seq = db.scalar(text('SELECT event_seq FROM assistant_handler_receipts WHERE id=:id'),
        {'id':str(saved.receipt_id)})
    if saved.run_id != run_id or (before_seq is not None and seq >= before_seq):
        raise ServiceError('CROSS_MATTER_DENIED', 403)
    return saved.citation


def begin_library_call(actor, run_id, call_id, request, database):
    run_id, call_id, request = _identifier(run_id), _identifier(call_id), _request(request)
    try:
        with database.session() as db:
            db.connection()  # Database's begin hook acquires BEGIN IMMEDIATE before any read.
            _, scope, conversation = _execution(actor, run_id, db)
            rows = db.execute(text('''SELECT * FROM assistant_run_events
                WHERE run_id=:run AND event_type='tool.before' ORDER BY seq'''),
                {'run':str(run_id)}).mappings().all()
            calls = tuple(_event(row, run_id) for row in rows)
            if len(calls) > 8 or len({item.payload.call_id for item in calls}) != len(calls):
                raise ServiceError('LIBRARY_RECORD_INVALID', 409)
            for item in calls:
                if item.payload.call_id == call_id:
                    _execution(actor, run_id, db, item.payload)
                    if item.payload.request != request:
                        raise ServiceError('VERSION_CONFLICT', 409)
                    return item
            if len(calls) == 8:
                raise ServiceError('LIBRARY_TOOL_LIMIT', 409)
            citation = _source(actor, run_id, request, db)
            payload = d.LibraryHandlerEvent(call_id=call_id, handler_id=request.tool, request=request,
                scope=scope, expected_composer_revision=conversation['composer_revision'],
                citation_sha256=sha(encoded(citation)) if citation else None)
            seq, total = db.execute(text('SELECT COALESCE(MAX(seq),0),COUNT(*) FROM assistant_run_events WHERE run_id=:run'),
                {'run':str(run_id)}).one()
            if seq != total:
                raise ServiceError('LIBRARY_RECORD_INVALID', 409)
            db.execute(text('''INSERT INTO assistant_run_events
                (run_id,seq,event_type,audience,payload_json,created_at)
                VALUES (:run,:seq,'tool.before','internal',:payload,:at)'''),
                {'run':str(run_id), 'seq':seq + 1, 'payload':encoded(payload), 'at':service._at()})
            return d.LibraryHandlerCall(run_id=run_id, event_seq=seq + 1, payload=payload)
    except SQLAlchemyError:
        raise ServiceError('LIBRARY_RECORD_INVALID', 409) from None


def _publish_in_session(actor, call, result, db):
    checked = _load_call(actor, call.run_id, call.event_seq, db)
    if checked != call:
        raise ServiceError('LIBRARY_RECORD_INVALID', 409)
    previous = _receipt(call, db)
    if previous is not None:
        return d.LibraryHandlerExecution(receipt=previous, replayed=True)
    try:
        result = d.AssistantLibraryToolResult.model_validate(result.model_dump(mode='python', warnings=False))
        source = _source(actor, call.run_id, call.payload.request, db, before_seq=call.event_seq)
        if source is not None and (result.citation != source or sha(encoded(source)) != call.payload.citation_sha256):
            raise ValueError('original snapshot mismatch')
        identifiers = tuple(uuid4() for _ in result_citations(result))
        saved = d.LibraryHandlerResult(result=result, citation_ids=identifiers)
        receipt = d.LibraryHandlerReceiptView(id=uuid4(), run_id=call.run_id, event_seq=call.event_seq,
            handler_id=call.payload.handler_id, handler_version=call.payload.handler_version,
            request=call.payload.request, scope=call.payload.scope, result=saved, created_at=service._at())
        request_raw = _bounded(receipt.request, 8192)
        scope_raw = _bounded(receipt.scope, 4096)
        result_raw = _bounded(saved, 262144)
        citations = tuple(_bounded(item, 32768) for item in result_citations(result))
        at = receipt.created_at.isoformat()
        with db.begin_nested():
            db.execute(text('''INSERT INTO assistant_handler_receipts
                (id,run_id,event_seq,handler_id,handler_version,payload_sha256,
                 request_json,result_json,result_sha256,scope_json,created_at)
                VALUES (:id,:run,:seq,:handler,:version,:payload,:request,:result,:hash,:scope,:at)'''),
                {'id':str(receipt.id), 'run':str(call.run_id), 'seq':call.event_seq,
                 'handler':receipt.handler_id, 'version':receipt.handler_version,
                 'payload':sha(encoded(call.payload)), 'request':request_raw, 'result':result_raw,
                 'hash':sha(result_raw), 'scope':scope_raw, 'at':at})
            for ordinal, (identifier, raw) in enumerate(zip(identifiers, citations)):
                db.execute(text('''INSERT INTO assistant_library_citations
                    (id,receipt_id,ordinal,citation_json,citation_sha256,created_at)
                    VALUES (:id,:receipt,:ordinal,:raw,:hash,:at)'''),
                    {'id':str(identifier), 'receipt':str(receipt.id), 'ordinal':ordinal,
                     'raw':raw, 'hash':sha(raw), 'at':at})
        return d.LibraryHandlerExecution(receipt=receipt, replayed=False)
    except (ValueError, TypeError, SQLAlchemyError):
        raise ServiceError('LIBRARY_RECORD_INVALID', 409) from None


def execute_library_handler(actor, run_id, event_seq, database, adapter):
    run_id = _identifier(run_id)
    if type(event_seq) is not int or event_seq <= 0:
        raise ServiceError('LIBRARY_TOOL_INPUT_INVALID', 422)
    with database.session() as db:
        call = _load_call(actor, run_id, event_seq, db)
        previous = _receipt(call, db)
        if previous is not None:
            return d.LibraryHandlerExecution(receipt=previous, replayed=True)
        citation = _source(actor, run_id, call.payload.request, db, before_seq=event_seq)
        if citation is not None and sha(encoded(citation)) != call.payload.citation_sha256:
            raise ServiceError('LIBRARY_RECORD_INVALID', 409)
    request = d.AssistantLibraryToolCall(tool=call.payload.handler_id,
        expected_scope=call.payload.scope, expected_composer_revision=call.payload.expected_composer_revision,
        query=call.payload.request.query, citation=citation)
    try:
        result = execute_tool(actor, request, database, adapter)
    except ServiceError:
        with database.session() as db:
            _load_call(actor, run_id, event_seq, db)
        raise
    try:
        with database.session() as db:
            db.connection()
            return _publish_in_session(actor, call, result, db)
    except SQLAlchemyError:
        raise ServiceError('LIBRARY_RECORD_INVALID', 409) from None
