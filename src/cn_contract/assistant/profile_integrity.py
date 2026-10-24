"""Replay immutable profile history without live access checks or external I/O."""
import hashlib
import json
from uuid import UUID, NAMESPACE_URL, uuid5

from pydantic import TypeAdapter
from sqlalchemy import text

from .. import domain as d
from ..record_codec import encode, sha
from ..security import ServiceError
from ..storage_schema import identify_schema
from . import attachment_records as records
from .profiles import merge_profile


def _fail():
    raise ValueError('ASSISTANT_PROFILE_INTEGRITY')


def _uuid(value):
    if type(value) is not str or str(UUID(value)) != value:
        _fail()
    return value


def _at(value):
    if type(value) is not str:
        _fail()
    return TypeAdapter(d.UTCDatetime).validate_python(value)


def _model(kind, raw, digest=None):
    if type(raw) is not str or len(raw) > 2097152:
        _fail()
    value = kind.model_validate(json.loads(raw))
    if encode(value.model_dump(mode='json')) != raw:
        _fail()
    if digest is not None and hashlib.sha256(raw.encode('utf-8')).hexdigest() != digest:
        _fail()
    return value


def _intake(db, identifier, revision, owner, at):
    case = db.execute(text('SELECT * FROM intake_cases WHERE id=:id'),
                      {'id': str(identifier)}).mappings().first()
    row = db.execute(text('SELECT * FROM intake_revisions WHERE intake_id=:id AND revision=:rev'),
                     {'id': str(identifier), 'rev': revision}).mappings().first()
    if (case is None or row is None or case['owner_id'] != owner
            or case['current_revision'] < revision or _at(row['saved_at']) > at):
        _fail()
    payload = json.loads(row['payload'])
    value = d.IntakeDraft(client_reply=row['client_reply'], internal_notes=row['internal_notes'], **payload)
    if encode(value.model_dump(mode='json', exclude={'client_reply', 'internal_notes'})) != row['payload']:
        _fail()
    return value, case


def _sources(db, patch, conversation, at):
    scope = patch.scope
    refs = tuple(ref for change in patch.changes for ref in change.source_refs)
    message_ids = {ref.message_id for ref in refs if ref.kind == 'message'}
    document_ids = {ref.attachment_id for ref in refs if ref.kind == 'document'}
    if len(message_ids) > 200 or len(document_ids) > 20:
        _fail()
    if any(ref.conversation_id != scope.conversation_id for ref in refs):
        _fail()
    messages, documents = [], []
    if scope.input_revision:
        boundary = db.scalar(text('''SELECT created_at FROM assistant_messages
            WHERE conversation_id=:cid AND source_revision=:rev AND role='user' '''),
            {'cid': conversation['id'], 'rev': scope.input_revision})
        if boundary is None or _at(boundary) > at:
            _fail()
    selected = {}
    if scope.materials_revision:
        selection = db.execute(text('''SELECT * FROM assistant_material_snapshots
            WHERE conversation_id=:cid AND revision=:rev'''),
            {'cid': conversation['id'], 'rev': scope.materials_revision}).mappings().first()
        if selection is None or selection['actor_id'] != conversation['owner_id'] or _at(selection['created_at']) > at:
            _fail()
        items = tuple(d.AssistantMaterialRef.model_validate(x) for x in json.loads(selection['items_json']))
        selected = {item.attachment_id: item.parse_revision for item in items}
        if len(selected) != len(items):
            _fail()
    for identifier in message_ids:
        row = db.execute(text('''SELECT id,role,content,created_at,source_revision FROM assistant_messages
            WHERE id=:id AND conversation_id=:cid'''),
            {'id': str(identifier), 'cid': conversation['id']}).mappings().first()
        if (row is None or row['role'] != 'user' or row['source_revision'] > scope.input_revision
                or _at(row['created_at']) > at):
            _fail()
        messages.append(d.AssistantMessageView(**row))
    for ref in refs:
        if ref.kind == 'document' and selected.get(ref.attachment_id) != ref.parse_revision:
            _fail()
    for identifier in document_ids:
        row = db.execute(text('SELECT * FROM assistant_attachments WHERE id=:id'),
                         {'id': str(identifier)}).mappings().first()
        if (row is None or row['conversation_id'] != conversation['id']
                or row['workspace_id'] != conversation['workspace_id'] or row['owner_id'] != conversation['owner_id']
                or _at(row['created_at']) > at):
            _fail()
        parsed_row = records.parse_row(scope.conversation_id, identifier, selected[identifier], db)
        if parsed_row['actor_id'] != conversation['owner_id'] or _at(parsed_row['created_at']) > at:
            _fail()
        parsed = records.parse_view(parsed_row)
        if parsed.result is None:
            _fail()
        documents.append(d.ProfileDocumentSource(conversation_id=scope.conversation_id,
            attachment_id=identifier, original_name=row['original_name'], original_sha256=row['sha256'],
            parse_revision=parsed.revision, result_sha256=parsed.result_sha256, result=parsed.result))
    return d.ProfileSourceSnapshot(scope=scope, messages=messages, documents=documents)


def _origin(profile):
    field = next((f for f in profile.fields if f.field == 'consultation'), None)
    return ('profile_summary' if field is not None and field.protected_value is None
            and field.verification == 'unverified' and any(c.value.kind != 'null' for c in field.candidates) else 'user')


def _historical_origin(db, origins, target, revision, owner, at):
    candidates = [(rev, proof) for (identifier, rev), proof in origins.items()
                  if identifier == target and rev <= revision] if target is not None else []
    if not candidates:
        return 'user'
    start, (origin, created_at) = max(candidates, key=lambda item: item[0])
    if created_at > at:
        _fail()
    if origin != 'profile_summary':
        return origin
    original = _intake(db, target, start, owner, at)[0].consultation
    for current in range(start + 1, revision + 1):
        if _intake(db, target, current, owner, at)[0].consultation != original:
            return 'user'
    return origin


def _scope(db, scope, conversation, workspace, at):
    if (str(scope.workspace_id) != workspace or str(scope.conversation_id) != conversation['id']
            or scope.binding_revision > conversation['binding_revision']
            or scope.binding_revision == conversation['binding_revision'] and (
                scope.scope_kind != conversation['scope_kind']
                or (str(scope.scope_ref) if scope.scope_ref else None) != conversation['scope_ref'])
            or scope.input_revision > conversation['input_revision']
            or scope.materials_revision > conversation['materials_revision']
            or _at(conversation['created_at']) > at):
        _fail()
    if scope.scope_kind != 'conversation':
        table = 'matters' if scope.scope_kind == 'matter' else 'intake_cases'
        target = db.execute(text(f'SELECT * FROM {table} WHERE id=:id'),
                            {'id': str(scope.scope_ref)}).mappings().first()
        if target is None or scope.scope_kind == 'intake' and target['owner_id'] != conversation['owner_id']:
            _fail()


def _replay(db, conversation, receipts, revisions, workspace, origins):
    previous, baseline, last_scope, last_target = None, None, None, None
    last_at = _at(conversation['created_at'])
    for sequence, row in enumerate(receipts, 1):
        at = _at(row['created_at'])
        request = _model(d.ProfileCommitInput, row['request_json'], row['request_sha256'])
        if (row['sequence'] != sequence or row['request_id'] != str(request.request_id)
                or _uuid(row['actor_id']) != conversation['owner_id']
                or db.scalar(text('SELECT user_id FROM sessions WHERE id=:id'),
                             {'id': _uuid(row['session_id'])}) != conversation['owner_id']
                or at < last_at or row['profile_changed'] not in (0, 1) or row['projection_changed'] not in (0, 1)):
            _fail()
        scope = request.patch.scope
        _scope(db, scope, conversation, workspace, at)
        if last_scope is not None and (scope.input_revision < last_scope.input_revision
                or scope.materials_revision < last_scope.materials_revision or scope.binding_revision < last_scope.binding_revision):
            _fail()
        expected_target = str(request.expected_intake_id) if request.expected_intake_id else None
        if (scope.scope_kind == 'intake' and expected_target != str(scope.scope_ref)
                or scope.scope_kind != 'intake' and expected_target is not None
                and expected_target != (last_target or conversation['projection_intake_id'])
                or last_target is not None and expected_target != last_target):
            _fail()
        current = (_intake(db, expected_target, request.expected_intake_revision, conversation['owner_id'], at)[0]
                   if expected_target else None)
        result = merge_profile(previous, request.patch, _sources(db, request.patch, conversation, at),
            intake_baseline=baseline, intake_current=current, manual_edits=request.manual_edits,
            project_intake=request.project_intake)
        if row['profile_changed'] != int(result.changed) or (row['profile_revision'] or 0) != result.profile.revision:
            _fail()
        if result.changed:
            stored = revisions.pop(result.profile.revision, None)
            if (stored is None or _model(d.ProfileDraftState, stored['profile_json'], stored['profile_sha256']) != result.profile
                    or stored['created_at'] != row['created_at']):
                _fail()
            previous = result.profile
        target = row['intake_id']
        changed = result.projection is not None and result.projection != current
        if row['projection_changed'] != int(changed):
            _fail()
        after = None
        if target is None:
            if row['intake_revision'] is not None or row['intake_sha256'] is not None or expected_target or result.projection:
                _fail()
        else:
            _uuid(target)
            if expected_target is not None and target != expected_target:
                _fail()
            if expected_target is None and not changed:
                _fail()
            revision = (request.expected_intake_revision or 0) + int(changed)
            if row['intake_revision'] != revision:
                _fail()
            after, case = _intake(db, target, revision, conversation['owner_id'], at)
            if after != (result.projection if result.projection is not None else current) or sha(after.model_dump(mode='json')) != row['intake_sha256']:
                _fail()
            later = db.scalars(text('SELECT saved_at FROM intake_revisions WHERE intake_id=:id AND revision>:rev'),
                               {'id': target, 'rev': revision})
            if any(_at(saved_at) <= at for saved_at in later):
                _fail()
            if expected_target is None and (case['request_id'] != str(uuid5(NAMESPACE_URL,
                    f'qx-profile:{conversation["id"]}:{request.request_id}'))
                    or case['request_sha256'] != sha(after.model_dump(mode='json'))):
                _fail()
        origin = (_origin(result.profile) if changed else _historical_origin(
            db, origins, target, row['intake_revision'], conversation['owner_id'], at))
        if (row['consultation_origin'] != origin or row['audience'] != 'internal'
                or row['event_type'] != ('profile.saved' if result.changed or changed else 'profile.unchanged')):
            _fail()
        if scope.scope_kind != 'intake' and target is not None and target != conversation['projection_intake_id']:
            _fail()
        if request.project_intake and result.projection is not None:
            baseline = after
        last_scope, last_target, last_at = scope, target, at
    if revisions:
        _fail()


def validate_profile_records(db, *, allowed=True):
    """Archived revisions remain valid after revocation, reparsing and recovery."""
    schema = [tuple(row) for row in db.execute(text('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))]
    native = any(row[0] == 'table' and row[1] == 'local_workspace_identity' for row in schema)
    version = identify_schema(schema, native=native)
    if version not in ('assistant-profiles-v1', 'assistant-profile-model-v1', 'task-drafts-v1', 'weixin-inbox-v1', 'weixin-dispatch-v1', 'weixin-reauthorization-v1', 'weixin-generations-v1'):
        return
    receipts = db.execute(text('SELECT * FROM assistant_profile_receipts ORDER BY conversation_id,sequence')).mappings().all()
    revisions = db.execute(text('SELECT * FROM assistant_profile_revisions ORDER BY conversation_id,revision')).mappings().all()
    if not receipts and not revisions:
        return
    if not allowed:
        raise ValueError('ASSISTANT_PROFILES_REQUIRE_QXBAK')
    try:
        identities = db.scalars(text('SELECT id FROM local_workspace_identity')).all() if native else []
        if len(identities) != 1:
            _fail()
        workspace = _uuid(identities[0])
        histories, states, origins = {}, {}, {}
        for row in receipts:
            histories.setdefault(_uuid(row['conversation_id']), []).append(row)
            _uuid(row['request_id'])
            if row['projection_changed']:
                key = row['intake_id'], row['intake_revision']
                if key in origins:
                    _fail()
                origins[key] = row['consultation_origin'], _at(row['created_at'])
        for row in revisions:
            group = states.setdefault(_uuid(row['conversation_id']), {})
            group[row['revision']] = row
        for cid in histories.keys() | states.keys():
            conversation = db.execute(text('SELECT * FROM assistant_conversations WHERE id=:id'), {'id': cid}).mappings().first()
            if conversation is None or conversation['workspace_id'] != workspace:
                _fail()
            _uuid(conversation['owner_id'])
            _replay(db, conversation, histories.get(cid, []), states.get(cid, {}), workspace, origins)
    except (ValueError, TypeError, KeyError, ArithmeticError, RecursionError, ServiceError):
        raise ValueError('ASSISTANT_PROFILE_INTEGRITY') from None
