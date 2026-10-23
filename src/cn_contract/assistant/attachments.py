"""Local file receipts and immutable sources, independent of contract cases.

Commands own short transactions. The native host holds its existing workspace
worker lock; maintenance stops that host before taking a complete qxbak snapshot.
"""
from io import BytesIO
from pathlib import Path, PurePath
import zipfile
from uuid import UUID, uuid4

from sqlalchemy import text

from .. import domain as d
from ..config import canonical_json
from ..documents.docx_adapter import read_package, has_revisions, parse_docx
from ..ops.storage import require_active
from ..security import ServiceError
from . import attachment_files as files, attachment_records as records
from .attachment_integrity import MAX_PARSE_JSON_BYTES, MAX_CONVERSATION_PARSE_JSON_BYTES
from .service import _at, _digest, _owned, _snapshot

PARSER_VERSION = 'qx-docx-attachments-v1'
MAX_CONVERSATION_FILES = 20
MAX_CONVERSATION_MIB = 100
MAX_PARSE_REVISIONS = 64


def _assistant_type(data, name, mime):
    """Content sniffing for assistant materials; the matter-side _type stays DOCX/PDF."""
    extension = PurePath(name).suffix.lower()
    if extension not in d.ASSISTANT_MATERIAL_MIME_EXT.get(mime, ()):
        raise ServiceError('FILE_UNSUPPORTED', 400)
    if mime == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
        if data.startswith(b'PK\x03\x04'):
            return 'docx'
    elif mime == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
        if data.startswith(b'PK\x03\x04'):
            try:
                with zipfile.ZipFile(BytesIO(data)) as package:
                    if package.namelist():
                        return 'xlsx'
            except zipfile.BadZipFile:
                pass
    elif mime == 'application/pdf':
        if data.startswith(b'%PDF-'):
            return 'pdf'
    elif mime == 'image/png':
        if data.startswith(b'\x89PNG\r\n\x1a\n'):
            return 'png'
    elif mime == 'image/jpeg':
        if data.startswith(b'\xff\xd8\xff'):
            return 'jpeg'
    elif mime == 'text/csv':
        try:
            if data.decode('utf-8-sig').strip():
                return 'csv'
        except UnicodeDecodeError:
            pass
    raise ServiceError('FILE_UNSUPPORTED', 400)


def _validate(model, value):
    return model.model_validate(value.model_dump(mode='python'))


def _write(actor, cid, db):
    row = _owned(actor,cid,db)
    require_active(db)
    return row


def _same(operation, kind, digest):
    if operation['kind'] != kind or operation['request_sha256'] != digest:
        raise ServiceError('VERSION_CONFLICT',409)


def _policy(request, checksum, database):
    if request.policy.material_mode == 'local':
        if getattr(database,'_local_materials_enabled',False) is not True:
            raise ServiceError('DATA_POLICY_UNAPPROVED',409)
    else:
        registered = getattr(database,'_assistant_synthetic_hashes',None)
        if registered is None:
            from ..ops.backup import _registered_hashes
            registered = _registered_hashes()
        if checksum not in registered:
            raise ServiceError('DATA_POLICY_UNAPPROVED',409)


def _upload_receipt(actor, cid, request_id, db):
    operation = records.operation(cid,request_id,db)
    if operation is None:
        return None
    if operation['kind'] != 'upload':
        raise ServiceError('VERSION_CONFLICT',409)
    identifier = db.scalar(text('SELECT id FROM assistant_attachments WHERE conversation_id=:cid AND request_id=:rid'),
        {'cid':str(cid),'rid':str(request_id)})
    row = records.owned_attachment(actor,cid,identifier,db)
    if row['request_sha256'] != operation['request_sha256']:
        raise ServiceError('VERSION_CONFLICT',409)
    return d.AssistantAttachmentReceipt(attachment=records.attachment_view(row),materials_revision=operation['revision'])


def ingest_attachment(actor, cid, request, stream, *, database):
    request = _validate(d.AssistantAttachmentInput,request)
    with database.session() as db:
        _write(actor,cid,db)
    with files.stage(stream,database) as (temporary,size,checksum):
        data = temporary.read_bytes()
        kind = _assistant_type(data,request.original_name,request.mime)
        if kind == 'docx':
            read_package(data,database.settings)
        digest = _digest({'conversation_id':str(cid),'request':request.model_dump(mode='json'),
                          'sha256':checksum,'byte_size':size})
        identifier, created = uuid4(), None
        try:
            with database.session() as db:
                row = _write(actor,cid,db)
                previous = records.operation(cid,request.request_id,db)
                if previous:
                    _same(previous,'upload',digest)
                    return _upload_receipt(actor,cid,request.request_id,db)
                records.expected(row,request.expected_scope)
                _policy(request,checksum,database)
                count,total = db.execute(text('SELECT COUNT(*),COALESCE(SUM(byte_size),0) FROM assistant_attachments WHERE conversation_id=:cid'),
                    {'cid':str(cid)}).one()
                if (count >= min(MAX_CONVERSATION_FILES,database.settings.upload_max_matter_files)
                        or total+size > min(MAX_CONVERSATION_MIB,database.settings.upload_max_matter_mib)*1024**2):
                    raise ServiceError('FILE_LIMIT',413)
                relative = Path('assistant')/str(cid)/str(identifier)/'original.bin'
                created = files.publish(temporary,database.storage_root,relative)
                db.execute(text('''INSERT INTO assistant_attachments
                    (id,conversation_id,workspace_id,owner_id,request_id,request_sha256,original_name,
                     mime,byte_size,sha256,storage_ref,policy_json,actor_id,created_at)
                    VALUES (:id,:cid,:wid,:owner,:rid,:digest,:name,:mime,:size,:sha,:ref,:policy,:actor,:at)'''),
                    {'id':str(identifier),'cid':str(cid),'wid':row['workspace_id'],'owner':row['owner_id'],
                     'rid':str(request.request_id),'digest':digest,'name':request.original_name,'mime':request.mime,
                     'size':size,'sha':checksum,'ref':relative.as_posix(),'policy':request.policy.model_dump_json(),
                     'actor':str(actor.user_id),'at':_at()})
                values = (*records.items(row,db),d.AssistantMaterialRef(attachment_id=identifier,parse_revision=None))
                records.snapshot(row,values,'upload',request.request_id,digest,actor,db)
                result = _upload_receipt(actor,cid,request.request_id,db)
            return result
        except BaseException:
            if created is not None:
                # A failure after COMMIT must not remove a durable original.
                with database.session() as db:
                    exists = db.scalar(text('SELECT id FROM assistant_attachments WHERE id=:id'),{'id':str(identifier)})
                if exists is None:
                    files.remove_uncommitted(created,database.storage_root)
            raise


def find_attachment_request(actor,cid,request_id,*,database):
    with database.session() as db:
        _owned(actor,cid,db)
        return _upload_receipt(actor,cid,request_id,db)


def find_material_request(actor,cid,request_id,*,database):
    with database.session() as db:
        _owned(actor,cid,db)
        row = records.operation(cid,request_id,db)
        return None if row is None else d.AssistantMaterialReceipt(request_id=row['request_id'],
            kind=row['kind'],materials_revision=row['revision'],
            items=records.decode_items(row['items_json']))


def read_materials(actor,cid,*,database):
    with database.session() as db:
        row = _owned(actor,cid,db)
        attachments = db.execute(text('SELECT * FROM assistant_attachments WHERE conversation_id=:cid ORDER BY rowid'),
            {'cid':str(cid)}).mappings().all()
        return d.AssistantMaterialsView(scope=_snapshot(row),items=records.items(row,db),
            attachments=tuple(records.attachment_view(records.owned_attachment(actor,cid,item['id'],db)) for item in attachments))


def read_attachment(actor,cid,identifier,*,database):
    with database.session() as db:
        return records.attachment_view(records.owned_attachment(actor,cid,identifier,db))


def read_original(actor,cid,identifier,*,database):
    with database.session() as db:
        row = dict(records.owned_attachment(actor,cid,identifier,db))
    raw = files.read_checked(row,database)
    with database.session() as db:
        records.owned_attachment(actor,cid,identifier,db)
    return raw


def _parse_receipt(actor,cid,identifier,request_id,db):
    previous = records.operation(cid,request_id,db)
    if previous is None:
        return None
    if previous['kind'] != 'parse':
        raise ServiceError('VERSION_CONFLICT',409)
    records.owned_attachment(actor,cid,identifier,db)
    row = db.execute(text('''SELECT * FROM assistant_attachment_parses
        WHERE conversation_id=:cid AND attachment_id=:id AND request_id=:rid'''),
        {'cid':str(cid),'id':str(identifier),'rid':str(request_id)}).mappings().first()
    if row is None or row['request_sha256'] != previous['request_sha256']:
        raise ServiceError('VERSION_CONFLICT',409)
    return d.AssistantAttachmentParseReceipt(parse=records.parse_view(row),materials_revision=previous['revision'])


def parse_attachment(actor,cid,identifier,request,*,database):
    request = _validate(d.AssistantAttachmentParseInput,request)
    digest = _digest({'attachment_id':str(identifier),'conversation_id':str(cid),'request':request.model_dump(mode='json')})
    with database.session() as db:
        row = _write(actor,cid,db)
        source = dict(records.owned_attachment(actor,cid,identifier,db))
        if source['mime'] != 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
            raise ServiceError('FILE_UNSUPPORTED',400)
        previous = records.operation(cid,request.request_id,db)
        if previous:
            _same(previous,'parse',digest)
        else:
            records.expected(row,request.expected_scope)
    raw = files.read_checked(source,database)
    if previous:
        with database.session() as db:
            _write(actor,cid,db)
            return _parse_receipt(actor,cid,identifier,request.request_id,db)
    result, failure, result_json = None, None, None
    baseline = request.baseline_view
    try:
        _,parts = read_package(raw,database.settings)
        if has_revisions(parts) and baseline is None:
            status,failure = 'needs_baseline','BASELINE_REQUIRED'
        else:
            baseline = baseline or d.BaselineView.ORIGINAL
            result = parse_docx(raw,d.DocumentParseInput(id=identifier,baseline_view=baseline),database.settings)
            status = 'partial' if result.unsupported_parts or result.quality_issues or not result.anchors else 'readable'
            result_json = canonical_json(result.model_dump(mode='json'))
            if len(result_json.encode('utf-8')) > MAX_PARSE_JSON_BYTES:
                result, result_json, status, failure = None, None, 'failed', 'PARSE_RESULT_LIMIT'
    except Exception:
        # Retain the receipt; parser internals and document text never enter errors.
        result, result_json, status, failure = None, None, 'failed', 'PARSE_FAILED'
    with database.session() as db:
        row = _write(actor,cid,db)
        records.owned_attachment(actor,cid,identifier,db)
        previous = records.operation(cid,request.request_id,db)
        if previous:
            _same(previous,'parse',digest)
            return _parse_receipt(actor,cid,identifier,request.request_id,db)
        records.expected(row,request.expected_scope)
        values = records.items(row,db)
        if not any(item.attachment_id == identifier for item in values):
            raise ServiceError('VERSION_CONFLICT',409)
        revision = 1+db.scalar(text('SELECT COALESCE(MAX(revision),0) FROM assistant_attachment_parses WHERE attachment_id=:id'),{'id':str(identifier)})
        if revision > MAX_PARSE_REVISIONS:
            raise ServiceError('FILE_LIMIT',413)
        used = db.scalar(text('SELECT COALESCE(SUM(length(CAST(result_json AS BLOB))),0) FROM assistant_attachment_parses WHERE conversation_id=:cid'),
                         {'cid':str(cid)})
        if used + len((result_json or '').encode('utf-8')) > MAX_CONVERSATION_PARSE_JSON_BYTES:
            raise ServiceError('FILE_LIMIT',413)
        db.execute(text('''INSERT INTO assistant_attachment_parses
            (conversation_id,attachment_id,revision,request_id,request_sha256,parser_version,baseline_view,
             reading_status,result_json,result_sha256,failure_code,actor_id,created_at)
            VALUES (:cid,:id,:rev,:rid,:digest,:parser,:baseline,:status,:result,:sha,:failure,:actor,:at)'''),
            {'cid':str(cid),'id':str(identifier),'rev':revision,'rid':str(request.request_id),'digest':digest,
             'parser':PARSER_VERSION,'baseline':baseline.value if baseline else None,'status':status,
             'result':result_json,
             'sha':_digest(result.model_dump(mode='json')) if result else None,'failure':failure,'actor':str(actor.user_id),'at':_at()})
        values = tuple(d.AssistantMaterialRef(attachment_id=identifier,parse_revision=revision)
            if item.attachment_id == identifier else item for item in values)
        records.snapshot(row,values,'parse',request.request_id,digest,actor,db)
        return _parse_receipt(actor,cid,identifier,request.request_id,db)


def read_parse(actor,cid,identifier,revision,*,database):
    # Integrity of the protected original is checked before returning its excerpts.
    read_original(actor,cid,identifier,database=database)
    with database.session() as db:
        records.owned_attachment(actor,cid,identifier,db)
        return records.parse_view(records.parse_row(cid,identifier,revision,db))


def find_parse_request(actor,cid,identifier,request_id,*,database):
    read_original(actor,cid,identifier,database=database)
    with database.session() as db:
        records.owned_attachment(actor,cid,identifier,db)
        return _parse_receipt(actor,cid,identifier,request_id,db)


def read_excerpt(actor,cid,identifier,revision,anchor_id,quote_sha256,*,database):
    parsed = read_parse(actor,cid,identifier,revision,database=database)
    matches = [anchor for anchor in parsed.result.anchors if anchor.id == anchor_id] if parsed.result else []
    if len(matches) != 1 or matches[0].quote_sha256 != quote_sha256:
        raise ServiceError('VERSION_CONFLICT',409)
    with database.session() as db:
        row = records.owned_attachment(actor,cid,identifier,db)
        return d.AssistantAttachmentExcerpt(conversation_id=cid,attachment_id=identifier,
            parse_revision=revision,original_sha256=row['sha256'],anchor=matches[0])


def select_materials(actor,cid,request,*,database):
    request = _validate(d.AssistantMaterialSelectionInput,request)
    digest = _digest(request.model_dump(mode='json'))
    with database.session() as db:
        row = _write(actor,cid,db)
        previous = records.operation(cid,request.request_id,db)
        if previous:
            _same(previous,'selection',digest)
            return previous['revision']
        records.expected(row,request.expected_scope)
        for item in request.items:
            records.owned_attachment(actor,cid,item.attachment_id,db)
            if item.parse_revision is not None:
                records.parse_view(records.parse_row(cid,item.attachment_id,item.parse_revision,db))
        return records.snapshot(row,request.items,'selection',request.request_id,digest,actor,db)
