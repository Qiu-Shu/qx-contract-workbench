"""Commit sourced drafts and optional reception projections as one local unit."""
from uuid import UUID, NAMESPACE_URL, uuid5

from sqlalchemy import text

from .. import domain as d
from ..intake import service as intake
from ..ops.storage import require_active
from ..record_codec import encode, sha, now
from ..security import ServiceError
from . import attachment_records as records
from .profile_sources import read_profile_sources
from .profiles import merge_profile
from .service import _owned


def _receipt(row, actor, db):
    try:
        request = d.ProfileCommitInput.model_validate_json(row['request_json'])
        if (sha(request.model_dump(mode='json')) != row['request_sha256']
                or str(request.patch.scope.conversation_id) != row['conversation_id']
                or str(request.request_id) != row['request_id']):
            raise ValueError('receipt request mismatch')
        result = d.ProfileCommitReceipt(**{key: row[key] for key in d.ProfileCommitReceipt.model_fields
            if key not in ('profile_revision', 'profile_changed', 'projection_changed')},
            profile_revision=row['profile_revision'] or 0, profile_changed=bool(row['profile_changed']),
            projection_changed=bool(row['projection_changed']))
        if result.profile_revision:
            _profile(result.conversation_id, db, result.profile_revision)
        if result.intake_id:
            draft = _draft(intake.read(result.intake_id, actor, db, result.intake_revision))
            if sha(draft.model_dump(mode='json')) != result.intake_sha256:
                raise ValueError('receipt projection mismatch')
        return result
    except (ValueError, TypeError):
        raise ServiceError('VERSION_CONFLICT', 409) from None


def _existing(cid, request_id, db):
    return db.execute(text('''SELECT * FROM assistant_profile_receipts
        WHERE conversation_id=:cid AND request_id=:rid'''),
        {'cid': str(cid), 'rid': str(request_id)}).mappings().first()


def _profile(cid, db, revision=None):
    row = db.execute(text('''SELECT p.revision,p.profile_json,p.profile_sha256,c.workspace_id
        FROM assistant_profile_revisions p JOIN assistant_conversations c ON c.id=p.conversation_id
        WHERE p.conversation_id=:cid AND (:rev IS NULL OR p.revision=:rev) ORDER BY p.revision DESC LIMIT 1'''),
        {'cid': str(cid), 'rev': revision}).mappings().first()
    if row is None:
        if revision is not None:
            raise ServiceError('VERSION_CONFLICT', 409)
        return None
    try:
        value = d.ProfileDraftState.model_validate_json(row['profile_json'])
        if (value.scope.conversation_id != UUID(str(cid)) or value.revision != row['revision']
                or str(value.scope.workspace_id) != row['workspace_id']
                or sha(value.model_dump(mode='json')) != row['profile_sha256']):
            raise ValueError('digest')
        return value
    except ValueError:
        raise ServiceError('VERSION_CONFLICT', 409) from None


def read_profile(actor, cid, *, database, revision=None):
    with database.session() as db:
        _owned(actor, cid, db)
        return _profile(cid, db, revision)


def find_receipt(actor, cid, request_id, *, database):
    with database.session() as db:
        _owned(actor, cid, db)
        row = _existing(cid, request_id, db)
        return _receipt(row, actor, db) if row else None


def _writable(actor, cid, db):
    row = _owned(actor, cid, db)
    require_active(db)
    if row['archived_at'] is not None:
        raise ServiceError('VERSION_CONFLICT', 409)
    return row


def _retry(actor, request, db):
    row = _existing(request.patch.scope.conversation_id, request.request_id, db)
    if row is not None:
        if row['request_sha256'] != sha(request.model_dump(mode='json')):
            raise ServiceError('VERSION_CONFLICT', 409)
        return _receipt(row, actor, db)
    return None


def _draft(value):
    return d.IntakeDraft.model_validate(value.model_dump(mode='python', include=set(d.IntakeDraft.model_fields)))


def _consultation_origin(profile):
    field = next((f for f in profile.fields if f.field == 'consultation'), None)
    return 'profile_summary' if (field is not None and field.protected_value is None
        and field.verification == 'unverified' and any(c.value.kind != 'null' for c in field.candidates)) else 'user'


def _bounded(value):
    raw = encode(value.model_dump(mode='json'))
    if len(raw) > 2097152:
        raise ServiceError('FILE_LIMIT', 413)
    return raw


def _commit(actor, request, sources, db):
    """Private transaction boundary; sources must come from read_profile_sources."""
    request = d.ProfileCommitInput.model_validate(request.model_dump(mode='python'))
    cid = request.patch.scope.conversation_id
    conversation = _writable(actor, cid, db)
    retried = _retry(actor, request, db)
    if retried is not None:
        return retried
    records.expected(conversation, request.patch.scope)
    previous = _profile(cid, db)
    target = conversation['scope_ref'] if conversation['scope_kind'] == 'intake' else conversation['projection_intake_id']
    if (str(request.expected_intake_id) if request.expected_intake_id else None) != target:
        raise ServiceError('VERSION_CONFLICT', 409)
    current_record = intake.read(UUID(target), actor, db) if target else None
    if current_record is not None and (current_record.matter_id is not None
            or current_record.revision != request.expected_intake_revision):
        raise ServiceError('VERSION_CONFLICT', 409)
    current = _draft(current_record) if current_record else None
    baseline = None
    for row in db.execute(text('''SELECT request_json,intake_id,intake_revision FROM assistant_profile_receipts
            WHERE conversation_id=:cid AND intake_id IS NOT NULL ORDER BY sequence DESC'''),
            {'cid': str(cid)}).mappings():
        if d.ProfileCommitInput.model_validate_json(row['request_json']).project_intake:
            baseline = _draft(intake.read(UUID(row['intake_id']), actor, db, row['intake_revision']))
            break
    try:
        result = merge_profile(previous, request.patch, sources, intake_baseline=baseline,
            intake_current=current, manual_edits=request.manual_edits, project_intake=request.project_intake)
    except ValueError:
        raise ServiceError('VERSION_CONFLICT', 409) from None
    request_json, profile_json = _bounded(request), _bounded(result.profile)
    projection_changed = result.projection is not None and result.projection != current
    # A caller catching an error and committing its outer transaction must still
    # see none of the draft, reception, link, or receipt writes from this attempt.
    with db.begin_nested():
        if projection_changed:
            if current_record is None:
                creation_id = uuid5(NAMESPACE_URL, f'qx-profile:{cid}:{request.request_id}')
                if db.scalar(text('SELECT 1 FROM intake_cases WHERE owner_id=:owner AND request_id=:rid'),
                        {'owner':str(actor.user_id), 'rid':str(creation_id)}):
                    raise ServiceError('VERSION_CONFLICT', 409)
                current_record = intake.create(d.IntakeCreateInput(request_id=creation_id,
                    draft=result.projection), actor, db)
                db.execute(text('UPDATE assistant_conversations SET projection_intake_id=:iid WHERE id=:cid'),
                    {'iid': str(current_record.id), 'cid': str(cid)})
            else:
                current_record = intake.save(current_record.id, d.IntakeUpdateInput(
                    expected_revision=current_record.revision, draft=result.projection), actor, db)
        at = now()
        if result.changed:
            db.execute(text('''INSERT INTO assistant_profile_revisions
                (conversation_id,revision,profile_json,profile_sha256,created_at) VALUES (:cid,:rev,:raw,:sha,:at)'''),
                {'cid': str(cid), 'rev': result.profile.revision, 'raw': profile_json,
                 'sha': sha(result.profile.model_dump(mode='json')), 'at': at.isoformat()})
        origin = 'user'
        if projection_changed:
            origin = _consultation_origin(result.profile)
        elif current_record:
            origin = current_record.consultation_origin
        receipt = d.ProfileCommitReceipt(conversation_id=cid, sequence=1 + db.scalar(text(
            'SELECT coalesce(max(sequence),0) FROM assistant_profile_receipts WHERE conversation_id=:cid'), {'cid': str(cid)}),
            request_id=request.request_id, profile_revision=result.profile.revision, profile_changed=result.changed,
            intake_id=current_record.id if current_record else None,
            intake_revision=current_record.revision if current_record else None,
            intake_sha256=sha(_draft(current_record).model_dump(mode='json')) if current_record else None,
            projection_changed=projection_changed, consultation_origin=origin,
            event_type='profile.saved' if result.changed or projection_changed else 'profile.unchanged', created_at=at)
        values = receipt.model_dump(mode='json') | {'profile_revision': receipt.profile_revision or None,
            'actor_id': str(actor.user_id), 'session_id': str(actor.session_id),
            'request_json': request_json, 'request_sha256': sha(request.model_dump(mode='json')),
            'created_at': at.isoformat()}
        columns = ','.join(values)
        db.execute(text(f'INSERT INTO assistant_profile_receipts ({columns}) VALUES ({",".join(":"+k for k in values)})'), values)
    return receipt


def save_profile(actor, request: d.ProfileCommitInput, *, database):
    request = d.ProfileCommitInput.model_validate(request.model_dump(mode='python'))
    _bounded(request)
    with database.session() as db:
        _writable(actor, request.patch.scope.conversation_id, db)
        retried = _retry(actor, request, db)
        if retried is not None:
            return retried
    sources = read_profile_sources(actor, request.patch, database=database)
    with database.session() as db:
        return _commit(actor, request, sources, db)
