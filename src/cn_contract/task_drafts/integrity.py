"""Verify archived task provenance without granting access or replaying work."""
import hashlib
from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy import text

from .. import domain as d
from ..assistant.attachment_integrity import _json
from ..assistant.attachment_records import parse_row, parse_view
from ..assistant.profile_integrity import _scope
from ..config import canonical_json
from ..security import ServiceError
from ..storage_schema import identify_schema


def _fail():
    raise ValueError('TASK_DRAFT_INTEGRITY')


def _uuid(value):
    if type(value) is not str or str(UUID(value)) != value:
        _fail()
    return value


def _at(value):
    if type(value) is not str:
        _fail()
    return TypeAdapter(d.UTCDatetime).validate_python(value)


def _model(kind, raw, digest=None):
    if type(raw) is not str:
        _fail()
    value = kind.model_validate(_json(raw))
    if canonical_json(value.model_dump(mode='json')) != raw:
        _fail()
    if digest is not None and hashlib.sha256(raw.encode('utf-8')).hexdigest() != digest:
        _fail()
    return value


def _media(db, media, conversation, at):
    parsed = None
    if media.attachment_id is not None:
        row = db.execute(text('SELECT * FROM assistant_attachments WHERE id=:id'),
                         {'id':str(media.attachment_id)}).mappings().first()
        if (row is None or row['conversation_id'] != conversation['id']
                or row['workspace_id'] != conversation['workspace_id']
                or row['owner_id'] != conversation['owner_id'] or _at(row['created_at']) > at
                or row['original_name'] != media.name or row['mime'] != media.mime
                or media.sha256 is not None and media.sha256 != row['sha256']):
            _fail()
        if media.parse_revision is not None:
            saved = parse_row(conversation['id'], media.attachment_id, media.parse_revision, db)
            if saved['actor_id'] != conversation['owner_id'] or _at(saved['created_at']) > at:
                _fail()
            parsed = parse_view(saved)
    return d.TaskManifestMedia(**media.model_dump(),
        result_sha256=parsed.result_sha256 if parsed else None,
        reading_status=parsed.reading_status if parsed else None)


def _execution(db, row, draft, conversation, events, resolutions, workspace):
    manifest = _model(d.TaskDraftManifest, row['manifest_json'], row['manifest_sha256'])
    value = d.TaskExecutionView(**{key:row[key] for key in (
        'id','draft_id','revision','manifest_sha256','state','matter_id','job_id',
        'review_run_id','prepare_request_id','review_request_id','review_input_sha256',
        'error','created_at','updated_at')}, manifest=manifest,
        document_versions=_json(row['document_versions_json']), source_versions=_json(row['source_versions_json']))
    at = _at(row['created_at'])
    if (draft['state'] != 'frozen' or manifest.draft_id != value.draft_id
            or str(value.draft_id) != draft['id'] or manifest.revision != draft['revision']
            or value.revision != draft['revision'] or str(manifest.conversation_id) != conversation['id']
            or manifest.instruction != draft['instruction']
            or at < _at(draft['created_at']) or value.updated_at < at):
        _fail()
    _scope(db, manifest.scope, conversation, workspace, at)
    expected = []
    for saved, payload in events:
        media = []
        for original in payload.media:
            resolution = resolutions.get((saved['id'], original.media_id))
            source = resolution.replacement if resolution and resolution.action == 'resolve' else original
            if resolution and resolution.action == 'exclude':
                item = d.TaskManifestMedia(**original.model_dump(), excluded=True, exclusion_reason=resolution.reason)
            else:
                item = _media(db, source, conversation, at)
            media.append(item)
        expected.append(d.TaskManifestEvent(id=saved['id'], event_id=payload.event_id,
            payload_sha256=saved['payload_sha256'], text=payload.text, media=tuple(media)))
    personal = any(db.scalar(text("SELECT channel FROM task_channel_bindings WHERE id=:id"),
        {'id':saved['binding_id']}) == 'weixin_personal' for saved, _ in events)
    if manifest.events != tuple(expected) or manifest.synthetic == personal:
        _fail()
    included = {item.attachment_id:item for event in manifest.events for item in event.media if not item.excluded}
    main = UUID(draft['main_attachment_id']) if draft['main_attachment_id'] else next(iter(included)) if len(included) == 1 else None
    if (not included or manifest.main_attachment_id not in included
            or manifest.main_attachment_id != main
            or any(item.status != 'ready' or item.reading_status != 'readable' for item in included.values())):
        _fail()
    if value.matter_id is None:
        if value.document_versions or value.source_versions or value.prepare_request_id or value.review_run_id:
            _fail()
    else:
        if (value.prepare_request_id is None or set(value.source_versions) != set(included)
                or set(value.source_versions.values()) != set(value.document_versions)):
            _fail()
        for source, version in value.source_versions.items():
            stored = db.execute(text('SELECT * FROM document_versions WHERE id=:id'),
                                {'id':str(version)}).mappings().first()
            if (stored is None or stored['matter_id'] != str(value.matter_id)
                    or stored['sha256'] != included[source].sha256
                    or stored['sha256'] != value.document_versions[version]
                    or stored['uploaded_by'] != conversation['owner_id']):
                _fail()
    if value.review_run_id is not None:
        saved = db.execute(text('SELECT * FROM review_runs WHERE id=:id'),
                           {'id':str(value.review_run_id)}).mappings().first()
        if (saved is None or saved['matter_id'] != str(value.matter_id)
                or saved['actor_id'] != conversation['owner_id']
                or value.review_request_id is None or value.review_input_sha256 is None):
            _fail()
        run = d.ReviewRun.model_validate(_json(saved['payload']))
        context = d.ReviewContext.model_validate(_json(saved['context_json']))
        request = d.ReviewStartInput(fact_version=context.fact_snapshot.version,
            document_hashes={version.id:version.sha256 for version in context.document_versions})
        request_digest = hashlib.sha256(canonical_json(request.model_dump(mode='json')).encode('utf-8')).hexdigest()
        if (run.id != value.review_run_id or run.matter_id != value.matter_id
                or dict(run.manifest.document_hashes) != dict(value.document_versions)
                or run.manifest.model_provider != 'mock'
                or value.state in ('completed', 'failed') and value.state != run.status
                or context.matter.id != value.matter_id or request_digest != value.review_input_sha256):
            _fail()
    elif value.review_request_id is not None or value.review_input_sha256 is not None or value.state == 'completed':
        _fail()


def _validate(db, groups, workspace):
    bindings, inbox, drafts, links, executions, resolution_rows = groups
    conversations = {row['id']:row for row in db.execute(text('SELECT * FROM assistant_conversations')).mappings()}
    channels = {}
    for row in bindings:
        value = d.TaskChannelBindingView(**row)
        conversation = conversations.get(str(value.conversation_id))
        if conversation is None or conversation['workspace_id'] != workspace:
            _fail()
        channels[_uuid(row['id'])] = conversation
    states = {row['id']:row for row in drafts}
    sources = {}
    for row in inbox:
        payload = _model(d.TaskInboxEventInput, row['payload_json'], row['payload_sha256'])
        conversation = channels[_uuid(row['binding_id'])]
        if payload.event_id != row['event_id']:
            _fail()
        if payload.task_id is not None and states[str(payload.task_id)]['conversation_id'] != conversation['id']:
            _fail()
        for media in payload.media:
            _media(db, media, conversation, _at(row['created_at']))
        sources[_uuid(row['id'])] = (row, payload, conversation['id'])
    grouped = {}
    for row in links:
        source, payload, cid = sources[_uuid(row['event_id'])]
        draft = states[_uuid(row['draft_id'])]
        entries = grouped.setdefault(draft['id'], [])
        if (cid != draft['conversation_id'] or type(row['ordinal']) is not int
                or row['ordinal'] != len(entries)+1):
            _fail()
        entries.append((source, payload))
    resolutions = {}
    for row in resolution_rows:
        draft = states[_uuid(row['draft_id'])]
        source = next((payload for saved, payload in grouped.get(draft['id'], ()) if saved['id'] == row['event_id']), None)
        value = d.TaskMediaResolutionView(**{key:row[key] for key in (
            'id','event_id','revision','media_id','action','reason','created_at')},
            replacement=_model(d.TaskMediaInput, row['replacement_json']) if row['replacement_json'] is not None else None)
        if (source is None or value.media_id not in {item.media_id for item in source.media}
                or value.revision > draft['revision'] or value.created_at < _at(draft['created_at'])):
            _fail()
        if value.replacement is not None:
            _media(db, value.replacement, conversations[draft['conversation_id']], value.created_at)
        resolutions.setdefault(draft['id'], {})[(row['event_id'], value.media_id)] = value
    execution_map = {row['draft_id']:row for row in executions}
    for row in drafts:
        identifier = _uuid(row['id'])
        conversation = conversations[_uuid(row['conversation_id'])]
        if (conversation['workspace_id'] != workspace or type(row['revision']) is not int or row['revision'] < 1
                or type(row['instruction']) is not str or len(row['instruction']) > 20000
                or _at(row['updated_at']) < _at(row['created_at'])
                or (row['state'] == 'frozen') != (identifier in execution_map)):
            _fail()
        parent, seen = row['parent_draft_id'], {identifier}
        while parent is not None:
            if parent in seen or states[parent]['conversation_id'] != conversation['id']:
                _fail()
            seen.add(parent)
            parent = states[parent]['parent_draft_id']
        if identifier in execution_map:
            _execution(db, execution_map[identifier], row, conversation, grouped.get(identifier, ()),
                       resolutions.get(identifier, {}), workspace)
    if set(execution_map) - states.keys():
        _fail()


def validate_task_records(db, *, allowed=True):
    """Old schemas stay readable; task history always requires a native archive."""
    schema = [tuple(row) for row in db.execute(text('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))]
    native = any(row[1] == 'local_workspace_identity' for row in schema)
    if identify_schema(schema, native=native) not in ('task-drafts-v1', 'weixin-inbox-v1', 'weixin-dispatch-v1', 'weixin-reauthorization-v1', 'weixin-generations-v1', 'weixin-target-provenance-v1', 'weixin-generation-dispatch-v1', 'assistant-evidence-v1', 'assistant-followups-v1', 'assistant-material-model-v1', 'weixin-personal-v1', 'weixin-personal-runtime-v1', 'weixin-service-v1'):
        return
    tables = ('task_channel_bindings','task_inbox_events','task_drafts','task_draft_events',
              'task_executions','task_media_resolutions')
    groups = [db.execute(text('SELECT * FROM '+table+(' ORDER BY draft_id,ordinal' if table == 'task_draft_events'
        else ' ORDER BY draft_id,revision,id' if table == 'task_media_resolutions' else ''))).mappings().all() for table in tables]
    if not any(groups):
        return
    if not allowed:
        raise ValueError('TASK_DRAFTS_REQUIRE_QXBAK')
    try:
        identities = db.scalars(text('SELECT id FROM local_workspace_identity')).all() if native else []
        if len(identities) != 1:
            _fail()
        _validate(db, groups, _uuid(identities[0]))
    except (ValueError, TypeError, KeyError, ArithmeticError, RecursionError, ServiceError):
        raise ValueError('TASK_DRAFT_INTEGRITY') from None
