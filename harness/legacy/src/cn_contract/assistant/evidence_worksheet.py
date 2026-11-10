"""Manual, source-bound matter preparation. No model or external service calls."""
from sqlalchemy import text

from .. import domain as d
from ..ops.storage import require_active
from ..record_codec import encode, sha, now
from ..security import ServiceError
from . import service, attachment_records as materials, attachment_files, evidence_records as records
from .reception_worksheet import view as reception_view


def _history(db,cid):
    try:return records.history(db,cid)
    except (ValueError,TypeError):raise ServiceError('VERSION_CONFLICT',409) from None


def read(actor,cid,db):
    conversation=service._owned(actor,cid,db);reception=reception_view(actor,cid,db)
    history=_history(db,cid);snapshot=history[-1][2] if history else None
    revision,statement=records.statement(cid,db);selected=materials.items(conversation,db)
    selection={x.attachment_id:x.parse_revision for x in selected};directory=[]
    for row in db.execute(text('SELECT * FROM assistant_attachments WHERE conversation_id=:cid ORDER BY rowid'),{'cid':str(cid)}).mappings():
        attachment=materials.attachment_view(row);parse=selection.get(attachment.id)
        parsed=materials.parse_view(materials.parse_row(cid,attachment.id,parse,db)) if parse else None
        directory.append(d.EvidenceMaterial(attachment=attachment,selected=attachment.id in selection,
            parse_revision=parse,reading_status=parsed.reading_status if parsed else None))
    historical=[]
    for fact in snapshot.rows if snapshot else ():
        ref=fact.source
        current=(statement is not None and statement[ref.start:ref.end]==ref.quote) if ref.kind=='statement' else (
            ref.attachment_id in selection and (ref.kind!='document' or selection[ref.attachment_id]==ref.parse_revision))
        if not current:historical.append(fact.id)
    return d.EvidenceWorksheetView(scope=service._snapshot(conversation),profile_revision=revision,
        revision=snapshot.revision if snapshot else 0,rows=snapshot.rows if snapshot else (),
        saved_scope=snapshot.scope if snapshot else None,statement=statement,writable=reception.writable,
        materials=tuple(directory),historical_ids=tuple(historical))


def historical(actor,cid,revision,db):
    service._owned(actor,cid,db)
    found=next((item[2] for item in _history(db,cid) if item[2].revision==revision),None)
    if found is None:raise ServiceError('VERSION_CONFLICT',409)
    return found


def find(actor,cid,key,db):
    service._owned(actor,cid,db)
    return next((records.receipt(row) for row,request,_ in _history(db,cid) if request.request_id==key),None)


def _check(actor,cid,value,db):
    require_active(db);view=read(actor,cid,db)
    if not view.writable or str(value.expected_scope.conversation_id)!=str(cid):raise ServiceError('VERSION_CONFLICT',409)
    history=_history(db,cid)
    for row,request,_ in history:
        if request.request_id==value.request_id:
            if request!=value:raise ServiceError('VERSION_CONFLICT',409)
            return view,records.receipt(row)
    if (value.expected_scope!=view.scope or value.expected_profile_revision!=view.profile_revision
            or value.base_revision!=view.revision):raise ServiceError('VERSION_CONFLICT',409)
    if view.revision>=200:raise ServiceError('FILE_LIMIT',413)
    previous={r.id:r for r in view.rows}
    try:
        for fact in value.rows:
            records.source(fact.source,value.expected_scope,value.expected_profile_revision,now(),db,
                inherited=fact.id in previous and fact.source==previous[fact.id].source)
    except (ValueError,TypeError):raise ServiceError('VERSION_CONFLICT',409) from None
    return view,None


def commit(actor,cid,value,*,database):
    value=d.EvidenceCommitInput.model_validate(value.model_dump(mode='python'))
    raw=encode(value.model_dump(mode='json'))
    if len(raw.encode('utf-8'))>2097152:raise ServiceError('FILE_LIMIT',413)
    with database.session() as db:
        _,receipt=_check(actor,cid,value,db)
        if receipt:return receipt
        originals={r.source.attachment_id for r in value.rows if r.source.kind!='statement'}
        originals=[dict(materials.owned_attachment(actor,cid,i,db)) for i in originals]
    # Filesystem I/O outside the transaction; current ACL, scope and rows rechecked below.
    for original in originals:attachment_files.read_checked(original,database)
    with database.session() as db:
        _,receipt=_check(actor,cid,value,db)
        if receipt:return receipt
        at=now();snapshot=d.EvidenceSnapshot(scope=value.expected_scope,profile_revision=value.expected_profile_revision,
            revision=value.base_revision+1,rows=value.rows,created_at=at)
        payload=encode(snapshot.model_dump(mode='json'))
        if len(payload.encode('utf-8'))>2097152:raise ServiceError('FILE_LIMIT',413)
        db.execute(text('''INSERT INTO assistant_evidence_revisions
            (conversation_id,revision,request_id,request_json,request_sha256,snapshot_json,snapshot_sha256,actor_id,session_id,created_at)
            VALUES (:cid,:rev,:rid,:request,:request_sha,:snapshot,:snapshot_sha,:actor,:session,:at)'''),
            {'cid':str(cid),'rev':snapshot.revision,'rid':str(value.request_id),'request':raw,'request_sha':sha(value.model_dump(mode='json')),
             'snapshot':payload,'snapshot_sha':sha(snapshot.model_dump(mode='json')),'actor':str(actor.user_id),'session':str(actor.session_id),'at':at.isoformat()})
        return d.EvidenceReceipt(conversation_id=cid,request_id=value.request_id,revision=snapshot.revision,
            snapshot_sha256=sha(snapshot.model_dump(mode='json')),created_at=at)
