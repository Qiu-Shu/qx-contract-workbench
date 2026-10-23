"""Conversation material snapshots, with current authorization at every entry."""
from uuid import UUID

from sqlalchemy import text

from .. import domain as d
from ..config import canonical_json
from ..security import ServiceError
from .attachment_integrity import _json, parse_result_json
from .service import _at, _digest, _owned, _snapshot


def owned_attachment(actor, cid, identifier, db):
    conversation = _owned(actor, cid, db)
    row = db.execute(text('SELECT * FROM assistant_attachments WHERE conversation_id=:cid AND id=:id'),
        {'cid':str(cid), 'id':str(identifier)}).mappings().first()
    if (row is None or row['workspace_id'] != conversation['workspace_id']
            or row['owner_id'] != conversation['owner_id']):
        raise ServiceError('CROSS_MATTER_DENIED', 403)
    return row


def attachment_view(row):
    return d.AssistantAttachmentView(**{key:row[key] for key in
        ('id','conversation_id','request_id','original_name','mime','byte_size','sha256','created_at')},
        policy=d.AssistantMaterialPolicy.model_validate_json(row['policy_json']))


def operation(cid, request_id, db):
    return db.execute(text('SELECT * FROM assistant_material_snapshots WHERE conversation_id=:cid AND request_id=:id'),
                      {'cid':str(cid),'id':str(request_id)}).mappings().first()


def expected(conversation, scope):
    if conversation['archived_at'] is not None or scope != _snapshot(conversation):
        raise ServiceError('VERSION_CONFLICT', 409)


def decode_items(raw):
    """Use the same selection bounds for current and historical snapshots."""
    try:
        values = _json(raw)
        if type(values) is not list or len(values) > 20:
            raise ValueError('invalid material selection')
        return d.AssistantMaterialSelectionInput.distinct_attachments(
            tuple(d.AssistantMaterialRef.model_validate(value) for value in values))
    except (ValueError, TypeError):
        raise ServiceError('VERSION_CONFLICT', 409) from None


def items(conversation, db):
    if conversation['materials_revision'] == 0:
        return ()
    raw = db.scalar(text('SELECT items_json FROM assistant_material_snapshots WHERE conversation_id=:cid AND revision=:rev'),
        {'cid':conversation['id'],'rev':conversation['materials_revision']})
    if raw is None:
        raise ServiceError('VERSION_CONFLICT', 409)
    return decode_items(raw)


def snapshot(conversation, values, kind, request_id, digest, actor, db):
    revision = conversation['materials_revision']+1
    db.execute(text('''INSERT INTO assistant_material_snapshots
        (conversation_id,revision,kind,request_id,request_sha256,items_json,actor_id,created_at)
        VALUES (:cid,:rev,:kind,:rid,:digest,:items,:actor,:at)'''),
        {'cid':conversation['id'],'rev':revision,'kind':kind,'rid':str(request_id),'digest':digest,
         'items':canonical_json([value.model_dump(mode='json') for value in values]),
         'actor':str(actor.user_id),'at':_at()})
    db.execute(text('UPDATE assistant_conversations SET materials_revision=:rev WHERE id=:cid'),
               {'rev':revision,'cid':conversation['id']})
    return revision


def parse_row(cid, identifier, revision, db):
    row = db.execute(text('''SELECT * FROM assistant_attachment_parses
        WHERE conversation_id=:cid AND attachment_id=:id AND revision=:rev'''),
        {'cid':str(cid),'id':str(identifier),'rev':revision}).mappings().first()
    if row is None:
        raise ServiceError('VERSION_CONFLICT', 409)
    return row


def parse_view(row):
    try:
        result = parse_result_json(row['result_json']) if row['result_json'] is not None else None
    except ValueError:
        raise ServiceError('VERSION_CONFLICT', 409) from None
    valid = row['reading_status'] in ('readable','partial')
    if (valid != (result is not None) or (result is not None and
            (result.version_id != UUID(row['attachment_id']) or row['baseline_view'] is None
             or row['failure_code'] is not None or _digest(result.model_dump(mode='json')) != row['result_sha256']))
            or result is None and (row['result_sha256'] is not None or row['failure_code'] is None)):
        raise ServiceError('VERSION_CONFLICT', 409)
    return d.AssistantAttachmentParseView(**{key:row[key] for key in
        ('attachment_id','conversation_id','revision','request_id','parser_version','baseline_view',
         'reading_status','result_sha256','failure_code','created_at')}, result=result)
