"""Validate archived conversation sources without granting user access or writing."""
import hashlib
import json
import re
from uuid import UUID

from sqlalchemy import text

from .. import domain as d
from ..config import canonical_json
from ..storage_schema import identify_schema

MAX_PARSE_JSON_BYTES = 64 * 1024**2
MAX_CONVERSATION_PARSE_JSON_BYTES = 100 * 1024**2


def _uuid(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError('ASSISTANT_ATTACHMENT_IDENTITY')
    return value


def _request(row):
    _uuid(row['request_id'])
    if not isinstance(row['request_sha256'], str) or not re.fullmatch('[0-9a-f]{64}', row['request_sha256']):
        raise ValueError('ASSISTANT_MATERIAL_RECEIPT')


def _json(raw):
    if not isinstance(raw, str):
        raise ValueError('ASSISTANT_ATTACHMENT_JSON')
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError('ASSISTANT_ATTACHMENT_DUPLICATE_KEY')
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError('ASSISTANT_ATTACHMENT_JSON')))
    except (RecursionError, UnicodeError, json.JSONDecodeError):
        raise ValueError('ASSISTANT_ATTACHMENT_JSON') from None


def parse_result_json(raw):
    if not isinstance(raw, str):
        raise ValueError('ASSISTANT_ATTACHMENT_JSON')
    if len(raw.encode('utf-8')) > MAX_PARSE_JSON_BYTES:
        raise ValueError('ASSISTANT_PARSE_RESULT_LIMIT')
    return d.ParseResult.model_validate(_json(raw))


def file_references(db, *, allowed=True):
    """Return typed protected refs; old schemas are skipped only after recognition."""
    schema = [tuple(row) for row in db.execute(text(
        'SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')).all()]
    native = any(row[0] == 'table' and row[1] == 'local_workspace_identity' for row in schema)
    version = identify_schema(schema, native=native)
    if version in ('pre-intake', 'intake-v1', 'assistant-v1'):
        return []
    if version not in ('assistant-attachments-v1', 'assistant-model-v1', 'assistant-judge-v1', 'assistant-library-v1',
                       'assistant-context-v1', 'assistant-rounds-v1', 'assistant-rounds-v2',
                       'assistant-profiles-v1', 'assistant-profile-model-v1', 'task-drafts-v1', 'weixin-inbox-v1', 'weixin-dispatch-v1', 'weixin-reauthorization-v1', 'weixin-generations-v1', 'weixin-target-provenance-v1', 'weixin-generation-dispatch-v1', 'assistant-evidence-v1', 'assistant-followups-v1', 'assistant-material-model-v1', 'weixin-personal-v1'):
        raise ValueError('DATABASE_SCHEMA_MISMATCH')
    originals = db.execute(text('SELECT * FROM assistant_attachments ORDER BY id')).mappings().all()
    parses = db.execute(text('SELECT * FROM assistant_attachment_parses ORDER BY attachment_id,revision')).mappings().all()
    snapshots = db.execute(text('SELECT * FROM assistant_material_snapshots ORDER BY conversation_id,revision')).mappings().all()
    if not allowed and (originals or parses or snapshots):
        raise ValueError('ASSISTANT_ATTACHMENTS_REQUIRE_QXBAK')
    conversations = {row['id']:row for row in db.execute(text('SELECT * FROM assistant_conversations')).mappings()}
    if not originals and not parses and not snapshots:
        if any(row['materials_revision'] != 0 for row in conversations.values()):
            raise ValueError('ASSISTANT_MATERIAL_REVISION_MISMATCH')
        return []
    identities = db.execute(text('SELECT id FROM local_workspace_identity')).all() if native else []
    if len(identities) != 1:
        raise ValueError('ASSISTANT_ATTACHMENT_WORKSPACE')
    workspace = _uuid(identities[0][0])
    for cid, conversation in conversations.items():
        _uuid(cid)
        _uuid(conversation['owner_id'])
        if conversation['workspace_id'] != workspace:
            raise ValueError('ASSISTANT_ATTACHMENT_WORKSPACE')
    sources, parsed, operations, revisions, refs = {}, {}, {}, {}, []
    for row in originals:
        _request(row)
        identifier, cid = _uuid(row['id']), _uuid(row['conversation_id'])
        owner = conversations.get(cid)
        if (owner is None or row['workspace_id'] != workspace or row['owner_id'] != owner['owner_id']
                or row['actor_id'] != owner['owner_id']):
            raise ValueError('ASSISTANT_ATTACHMENT_OWNER')
        view = d.AssistantAttachmentView(**{key:row[key] for key in (
            'id','conversation_id','request_id','original_name','mime','byte_size','sha256','created_at')},
            policy=d.AssistantMaterialPolicy.model_validate(_json(row['policy_json'])))
        expected = f'assistant/{cid}/{identifier}/original.bin'
        if row['storage_ref'] != expected:
            raise ValueError('ASSISTANT_ATTACHMENT_REFERENCE')
        sources[identifier] = row
        refs.append({'logical_ref':expected, 'physical_ref':expected, 'sha256':view.sha256,
            'size':view.byte_size, 'record_ref':identifier, 'kind':'assistant_original',
            'conversation_id':cid, 'workspace_id':workspace, 'owner_id':row['owner_id']})
    parse_bytes = {}
    for row in parses:
        _request(row)
        identifier, cid = _uuid(row['attachment_id']), _uuid(row['conversation_id'])
        source = sources.get(identifier)
        if source is None or source['conversation_id'] != cid or row['actor_id'] != source['owner_id']:
            raise ValueError('ASSISTANT_PARSE_OWNER')
        result = parse_result_json(row['result_json']) if row['result_json'] is not None else None
        parse_bytes[cid] = parse_bytes.get(cid, 0)+len((row['result_json'] or '').encode('utf-8'))
        if parse_bytes[cid] > MAX_CONVERSATION_PARSE_JSON_BYTES:
            raise ValueError('ASSISTANT_PARSE_RESULT_LIMIT')
        view = d.AssistantAttachmentParseView(**{key:row[key] for key in (
            'attachment_id','conversation_id','revision','request_id','parser_version','baseline_view',
            'reading_status','result_sha256','failure_code','created_at')}, result=result)
        valid = view.reading_status in ('readable','partial')
        if (valid != (result is not None) or valid and (
                result.version_id != UUID(identifier) or view.baseline_view is None or view.failure_code is not None
                or hashlib.sha256(canonical_json(result.model_dump(mode='json')).encode()).hexdigest() != view.result_sha256)
                or not valid and (view.result_sha256 is not None or view.failure_code is None)):
            raise ValueError('ASSISTANT_PARSE_RESULT')
        if view.revision != revisions.get(identifier, 0)+1:
            raise ValueError('ASSISTANT_PARSE_REVISION')
        revisions[identifier] = view.revision
        parsed[(identifier, view.revision)] = row
    latest = {}
    for row in snapshots:
        _request(row)
        cid = _uuid(row['conversation_id'])
        owner = conversations.get(cid)
        if owner is None or row['actor_id'] != owner['owner_id']:
            raise ValueError('ASSISTANT_MATERIAL_OWNER')
        receipt = d.AssistantMaterialReceipt(request_id=row['request_id'], kind=row['kind'],
            materials_revision=row['revision'], items=_json(row['items_json']))
        if receipt.materials_revision != latest.get(cid, 0)+1:
            raise ValueError('ASSISTANT_MATERIAL_REVISION_MISMATCH')
        if len({item.attachment_id for item in receipt.items}) != len(receipt.items):
            raise ValueError('ASSISTANT_MATERIAL_DUPLICATE')
        for item in receipt.items:
            source = sources.get(str(item.attachment_id))
            if (source is None or source['conversation_id'] != cid or item.parse_revision is not None
                    and (str(item.attachment_id), item.parse_revision) not in parsed):
                raise ValueError('ASSISTANT_MATERIAL_REFERENCE')
        latest[cid] = receipt.materials_revision
        operations[(cid, str(receipt.request_id))] = (row, receipt)
    for cid, conversation in conversations.items():
        if conversation['materials_revision'] != latest.get(cid, 0):
            raise ValueError('ASSISTANT_MATERIAL_REVISION_MISMATCH')
    matched = set()
    for kind, values in (('upload', originals), ('parse', parses)):
        for row in values:
            key = (row['conversation_id'], row['request_id'])
            pair = operations.get(key)
            identifier = row['id'] if kind == 'upload' else row['attachment_id']
            revision = None if kind == 'upload' else row['revision']
            if (pair is None or pair[0]['kind'] != kind or pair[0]['request_sha256'] != row['request_sha256']
                    or not any(str(item.attachment_id) == identifier and item.parse_revision == revision
                        for item in pair[1].items)):
                raise ValueError('ASSISTANT_MATERIAL_RECEIPT')
            matched.add(key)
    for key, (row, receipt) in operations.items():
        if row['kind'] != 'selection' and key not in matched:
            raise ValueError('ASSISTANT_MATERIAL_RECEIPT')
        for item in receipt.items:
            source = sources[str(item.attachment_id)]
            referenced = [source]
            if item.parse_revision is not None:
                referenced.append(parsed[(str(item.attachment_id), item.parse_revision)])
            if any(operations[(entry['conversation_id'], entry['request_id'])][0]['revision'] > row['revision']
                    for entry in referenced):
                raise ValueError('ASSISTANT_MATERIAL_REVISION_MISMATCH')
    return refs
