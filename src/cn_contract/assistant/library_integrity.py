"""Validate local-library history without reading external sources or live grants."""
from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy import text

from .. import domain as d
from ..config import canonical_json
from ..storage_schema import identify_schema
from .library_records import encoded, model, receipt_view, result_citations, sha
from .research_records import initial_call


def _fail():
    raise ValueError('ASSISTANT_LIBRARY_INTEGRITY')


def _uuid(value):
    if type(value) is not str or str(UUID(value)) != value:
        _fail()
    return value


def _at(value):
    if type(value) is not str:
        _fail()
    return TypeAdapter(d.UTCDatetime).validate_python(value)


def _run_history(db, run_id, workspace):
    run = db.execute(text('SELECT * FROM assistant_runs WHERE id=:id'), {'id':run_id}).mappings().first()
    if run is None:
        _fail()
    for field in ('id', 'conversation_id', 'message_id', 'actor_id', 'session_id', 'request_id'):
        _uuid(run[field])
    conversation = db.execute(text('SELECT * FROM assistant_conversations WHERE id=:id'),
                              {'id':run['conversation_id']}).mappings().first()
    message = db.execute(text('SELECT * FROM assistant_messages WHERE id=:id'),
                         {'id':run['message_id']}).mappings().first()
    session_user = db.scalar(text('SELECT user_id FROM sessions WHERE id=:id'), {'id':run['session_id']})
    user = db.scalar(text('SELECT id FROM users WHERE id=:id'), {'id':run['actor_id']})
    scope = model(d.ScopeSnapshot, run['scope_snapshot'])
    if (conversation is None or message is None or user != run['actor_id'] or session_user != user
            or conversation['owner_id'] != user or conversation['workspace_id'] != workspace
            or str(scope.workspace_id) != workspace or str(scope.conversation_id) != run['conversation_id']
            or message['conversation_id'] != run['conversation_id'] or message['role'] != 'user'
            or message['source_revision'] != scope.input_revision
            or scope.binding_revision > conversation['binding_revision']
            or scope.binding_revision == conversation['binding_revision'] and (
                scope.scope_kind != conversation['scope_kind']
                or (str(scope.scope_ref) if scope.scope_ref else None) != conversation['scope_ref'])
            or scope.input_revision > conversation['input_revision']
            or scope.materials_revision > conversation['materials_revision']
            or not _at(conversation['created_at']) <= _at(message['created_at']) == _at(run['created_at'])):
        _fail()
    if scope.scope_kind != 'conversation':
        table = 'matters' if scope.scope_kind == 'matter' else 'intake_cases'
        target = db.execute(text(f'SELECT * FROM {table} WHERE id=:id'),
                            {'id':str(scope.scope_ref)}).mappings().first()
        if target is None or scope.scope_kind == 'intake' and target['owner_id'] != user:
            _fail()
    events = db.execute(text('SELECT * FROM assistant_run_events WHERE run_id=:id ORDER BY seq'),
                        {'id':run_id}).mappings().all()
    accepted = canonical_json({'message_id':run['message_id'], 'input_revision':scope.input_revision, 'state':'queued'})
    if (not events or events[0]['event_type'] != 'message.accepted' or events[0]['audience'] != 'internal'
            or events[0]['payload_json'] != accepted or events[0]['created_at'] != run['created_at']):
        _fail()
    previous = _at(run['created_at'])
    for seq, event in enumerate(events, 1):
        timestamp = _at(event['created_at'])
        if event['seq'] != seq or timestamp < previous:
            _fail()
        previous = timestamp
    return scope, conversation, events, run, message['content']


def _validate(db, events, receipts, citations, workspace):
    stored, groups, views = {}, {}, {}
    for row in citations:
        identifier = _uuid(row['id'])
        _uuid(row['receipt_id'])
        citation = model(d.CitationRef, row['citation_json'])
        if sha(row['citation_json']) != row['citation_sha256']:
            _fail()
        stored[identifier] = (row, citation)
        groups.setdefault(row['receipt_id'], []).append(row)
    by_event = {}
    for row in receipts:
        _uuid(row['id'])
        _uuid(row['run_id'])
        view = receipt_view(row)
        refs = groups.pop(row['id'], [])
        expected = result_citations(view.result.result)
        if (len(refs) != len(expected) or tuple(r['id'] for r in refs) != tuple(map(str, view.result.citation_ids))):
            _fail()
        for ordinal, (ref, citation) in enumerate(zip(refs, expected)):
            if (ref['ordinal'] != ordinal or ref['citation_json'] != encoded(citation)
                    or _at(ref['created_at']) != view.created_at):
                _fail()
        key = (row['run_id'], row['event_seq'])
        if key in by_event:
            _fail()
        by_event[key] = row, view
        views[row['id']] = view
    if groups:
        _fail()
    for run_id in {row['run_id'] for row in events}:
        scope, conversation, history, run, content = _run_history(db, run_id, workspace)
        research = initial_call(run, content, history)
        if research is not None and run['state'] == 'completed' and (run_id, research.event_seq) not in by_event:
            _fail()
        calls, last_revision = set(), 0
        for event in history:
            if not event['event_type'].lower().startswith('tool.'):
                continue
            if event['event_type'] != 'tool.before' or event['audience'] != 'internal':
                _fail()
            payload = model(d.LibraryHandlerEvent, event['payload_json'])
            if (payload.scope != scope or payload.call_id in calls or len(calls) >= 8
                    or not max(last_revision, scope.input_revision) <= payload.expected_composer_revision <= conversation['composer_revision']):
                _fail()
            calls.add(payload.call_id)
            last_revision = payload.expected_composer_revision
            source = None
            if payload.request.saved_citation_id is not None:
                source = stored.get(str(payload.request.saved_citation_id))
                if source is None:
                    _fail()
                source_row, source_value = source
                origin = views.get(source_row['receipt_id'])
                if (origin is None or str(origin.run_id) != run_id or origin.scope != scope
                        or origin.event_seq >= event['seq'] or origin.created_at > _at(event['created_at'])
                        or payload.citation_sha256 != source_row['citation_sha256']):
                    _fail()
            completed = by_event.pop((run_id, event['seq']), None)
            if completed is not None:
                row, view = completed
                if (row['payload_sha256'] != sha(event['payload_json']) or view.scope != scope
                        or view.request != payload.request or view.handler_id != payload.handler_id
                        or view.handler_version != payload.handler_version
                        or view.created_at < _at(event['created_at'])
                        or source is not None and view.result.result.citation != source_value):
                    _fail()
    if by_event:
        _fail()


def validate_library_records(db, *, allowed=True):
    """Snapshots are historical proof; current sessions and external files may be offline."""
    schema = [tuple(row) for row in db.execute(text('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))]
    native = any(row[0] == 'table' and row[1] == 'local_workspace_identity' for row in schema)
    version = identify_schema(schema, native=native)
    if version in ('pre-intake', 'intake-v1'):
        return
    events = db.execute(text('''SELECT * FROM assistant_run_events WHERE lower(event_type) LIKE 'tool.%'
        OR lower(event_type) LIKE 'research.%' OR payload_json LIKE '%local-research-v1%' ''')).mappings().all()
    if version not in ('assistant-library-v1', 'assistant-context-v1', 'assistant-rounds-v1',
                       'assistant-rounds-v2', 'assistant-profiles-v1', 'assistant-profile-model-v1', 'task-drafts-v1', 'weixin-inbox-v1', 'weixin-dispatch-v1', 'weixin-reauthorization-v1', 'weixin-generations-v1', 'weixin-target-provenance-v1', 'weixin-generation-dispatch-v1', 'assistant-evidence-v1', 'assistant-followups-v1', 'assistant-material-model-v1', 'weixin-personal-v1'):
        if events:
            _fail()
        return
    receipts = db.execute(text('SELECT * FROM assistant_handler_receipts')).mappings().all()
    citations = db.execute(text('SELECT * FROM assistant_library_citations ORDER BY receipt_id,ordinal')).mappings().all()
    if not events and not receipts and not citations:
        return
    if not allowed:
        raise ValueError('ASSISTANT_LIBRARY_REQUIRE_QXBAK')
    identities = db.scalars(text('SELECT id FROM local_workspace_identity')).all() if native else []
    try:
        if len(identities) != 1:
            _fail()
        _validate(db, events, receipts, citations, _uuid(identities[0]))
    except (ValueError, TypeError, KeyError, ArithmeticError, RecursionError):
        raise ValueError('ASSISTANT_LIBRARY_INTEGRITY') from None
