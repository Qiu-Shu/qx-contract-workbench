"""Explicit local follow-up tracking over immutable evidence and material versions."""
from sqlalchemy import text

from .. import domain as d
from ..ops.storage import require_active
from ..record_codec import encode,sha,now
from ..security import ServiceError
from . import service,evidence_worksheet,evidence_records,followup_records as records
from . import attachment_files,attachment_records as materials


def _history(db,cid):
    try:return records.history(db,cid)
    except (ValueError,TypeError):raise ServiceError('VERSION_CONFLICT',409) from None


def read(actor,cid,db):
    evidence=evidence_worksheet.read(actor,cid,db);saved=_history(db,cid)
    items=saved[-1][2].items if saved else ()
    try:
        ctx=records.context(db,cid,evidence.scope,evidence.profile_revision,evidence.revision,now())
        attention=tuple(d.FollowupAttention(item_id=item.id,reasons=reasons) for item in items if (reasons:=records.attention(item,ctx)))
    except (ValueError,TypeError):raise ServiceError('VERSION_CONFLICT',409) from None
    return d.FollowupWorksheetView(scope=evidence.scope,profile_revision=evidence.profile_revision,evidence_revision=evidence.revision,
        revision=saved[-1][2].revision if saved else 0,items=items,writable=evidence.writable,
        facts=evidence.rows,materials=evidence.materials,attention=attention)


def historical(actor,cid,revision,db):
    service._owned(actor,cid,db)
    snapshot=next((s for _,_,s in _history(db,cid) if s.revision==revision),None)
    if snapshot is None:raise ServiceError('VERSION_CONFLICT',409)
    return snapshot


def find(actor,cid,key,db):
    service._owned(actor,cid,db)
    return next((records.receipt(row) for row,request,_ in _history(db,cid) if request.request_id==key),None)


def _check(actor,cid,value,db):
    require_active(db);view=read(actor,cid,db)
    if not view.writable or str(value.expected_scope.conversation_id)!=str(cid):raise ServiceError('VERSION_CONFLICT',409)
    saved=_history(db,cid)
    for row,request,_ in saved:
        if request.request_id==value.request_id:
            if request!=value:raise ServiceError('VERSION_CONFLICT',409)
            return view,records.receipt(row)
    if (value.expected_scope!=view.scope or value.expected_profile_revision!=view.profile_revision
            or value.expected_evidence_revision!=view.evidence_revision or value.base_revision!=view.revision):raise ServiceError('VERSION_CONFLICT',409)
    if view.revision>=200:raise ServiceError('FILE_LIMIT',413)
    previous={i.id:i for i in view.items}
    try:
        ctx=records.context(db,cid,view.scope,view.profile_revision,view.evidence_revision,now())
        owner=service._owned(actor,cid,db)['owner_id']
        for item in value.items:records.links(item,previous.get(item.id),ctx,view.scope,owner,now(),db)
    except (ValueError,TypeError):raise ServiceError('VERSION_CONFLICT',409) from None
    return view,None


def commit(actor,cid,value,*,database):
    value=d.FollowupCommitInput.model_validate(value.model_dump(mode='python'));raw=encode(value.model_dump(mode='json'))
    if len(raw.encode('utf-8'))>2097152:raise ServiceError('FILE_LIMIT',413)
    with database.session() as db:
        _,receipt=_check(actor,cid,value,db)
        if receipt:return receipt
        # Check both explicit materials and originals behind linked fact versions.
        ids={m.attachment_id for item in value.items for m in item.materials}
        versions={s.revision:s for _,_,s in evidence_records.history(db,cid)}
        for item in value.items:
            for ref in item.facts:
                fact=next(f for f in versions[ref.evidence_revision].rows if f.id==ref.fact_id)
                if fact.source.kind!='statement':ids.add(fact.source.attachment_id)
        originals=[dict(materials.owned_attachment(actor,cid,i,db)) for i in ids]
    for row in originals:attachment_files.read_checked(row,database)
    with database.session() as db:
        _,receipt=_check(actor,cid,value,db)
        if receipt:return receipt
        at=now();snapshot=d.FollowupSnapshot(scope=value.expected_scope,profile_revision=value.expected_profile_revision,
            evidence_revision=value.expected_evidence_revision,revision=value.base_revision+1,items=value.items,created_at=at)
        payload=encode(snapshot.model_dump(mode='json'))
        if len(payload.encode('utf-8'))>2097152:raise ServiceError('FILE_LIMIT',413)
        db.execute(text('''INSERT INTO assistant_followup_revisions
            (conversation_id,revision,request_id,request_json,request_sha256,snapshot_json,snapshot_sha256,actor_id,session_id,created_at)
            VALUES (:cid,:rev,:rid,:request,:request_sha,:snapshot,:snapshot_sha,:actor,:session,:at)'''),
            {'cid':str(cid),'rev':snapshot.revision,'rid':str(value.request_id),'request':raw,'request_sha':sha(value.model_dump(mode='json')),
             'snapshot':payload,'snapshot_sha':sha(snapshot.model_dump(mode='json')),'actor':str(actor.user_id),'session':str(actor.session_id),'at':at.isoformat()})
        return d.FollowupReceipt(conversation_id=cid,request_id=value.request_id,revision=snapshot.revision,
            snapshot_sha256=sha(snapshot.model_dump(mode='json')),created_at=at)
