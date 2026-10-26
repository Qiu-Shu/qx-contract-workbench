"""Rebuild evidence snapshots and their exact historical local sources."""
from uuid import UUID

from sqlalchemy import text

from .. import domain as d
from . import attachment_records as materials, profile_store
from .profile_integrity import _at, _model, _scope


def statement(cid, db, revision=None):
    profile=profile_store._profile(cid,db,revision)
    field=next((f for f in profile.fields if f.field=='consultation'),None) if profile else None
    value=field.protected_value if field else None
    return (profile.revision if profile else 0, value.value if value and value.kind=='text' else None)


def selected(scope, db):
    if not scope.materials_revision:return {}
    row=db.execute(text('SELECT * FROM assistant_material_snapshots WHERE conversation_id=:cid AND revision=:rev'),
        {'cid':str(scope.conversation_id),'rev':scope.materials_revision}).mappings().first()
    if row is None:raise ValueError('EVIDENCE_SELECTION')
    return {x.attachment_id:x.parse_revision for x in materials.decode_items(row['items_json'])}


def source(ref, scope, profile_revision, at, db, *, inherited=False):
    cid=str(scope.conversation_id)
    if ref.kind=='statement':
        _,content=statement(cid,db,ref.profile_revision)
        created=db.scalar(text('SELECT created_at FROM assistant_profile_revisions WHERE conversation_id=:cid AND revision=:rev'),{'cid':cid,'rev':ref.profile_revision})
        if (created is None or _at(created)>at or content is None or content[ref.start:ref.end]!=ref.quote
                or not inherited and ref.profile_revision!=profile_revision):raise ValueError('EVIDENCE_STATEMENT')
        return
    row=db.execute(text('SELECT * FROM assistant_attachments WHERE conversation_id=:cid AND id=:id'),
        {'cid':cid,'id':str(ref.attachment_id)}).mappings().first()
    owner=db.scalar(text('SELECT owner_id FROM assistant_conversations WHERE id=:cid'),{'cid':cid})
    if (row is None or row['owner_id']!=owner or row['workspace_id']!=str(scope.workspace_id)
            or row['sha256']!=ref.original_sha256 or _at(row['created_at'])>at):raise ValueError('EVIDENCE_ORIGINAL')
    current=selected(scope,db)
    if not inherited and ref.attachment_id not in current:raise ValueError('EVIDENCE_SELECTION')
    if ref.kind=='document':
        parsed=materials.parse_view(materials.parse_row(cid,ref.attachment_id,ref.parse_revision,db))
        if (str(ref.conversation_id)!=cid or parsed.result is None or parsed.result_sha256!=ref.result_sha256
                or ref.anchor not in parsed.result.anchors or parsed.created_at>at
                or not inherited and current.get(ref.attachment_id)!=ref.parse_revision):raise ValueError('EVIDENCE_ANCHOR')


def history(db, cid):
    conversation=db.execute(text('SELECT * FROM assistant_conversations WHERE id=:cid'),{'cid':str(cid)}).mappings().first()
    rows=db.execute(text('SELECT * FROM assistant_evidence_revisions WHERE conversation_id=:cid ORDER BY revision'),{'cid':str(cid)}).mappings().all()
    previous={};last_scope=None;last_at=None;result=[]
    if len(rows)>200:raise ValueError('EVIDENCE_LIMIT')
    for index,row in enumerate(rows,1):
        request=_model(d.EvidenceCommitInput,row['request_json'],row['request_sha256'])
        snapshot=_model(d.EvidenceSnapshot,row['snapshot_json'],row['snapshot_sha256']);at=_at(row['created_at'])
        if (conversation is None or snapshot.revision!=index or row['revision']!=index or request.base_revision!=index-1
                or str(request.request_id)!=row['request_id'] or request.expected_scope!=snapshot.scope
                or request.expected_profile_revision!=snapshot.profile_revision or request.rows!=snapshot.rows
                or snapshot.created_at!=at or row['actor_id']!=conversation['owner_id']
                or db.scalar(text('SELECT user_id FROM sessions WHERE id=:id'),{'id':row['session_id']})!=conversation['owner_id']
                or last_at is not None and at<last_at):raise ValueError('EVIDENCE_RECORD')
        scope=snapshot.scope;_scope(db,scope,conversation,conversation['workspace_id'],at)
        if last_scope and any(getattr(scope,k)<getattr(last_scope,k) for k in ('binding_revision','input_revision','materials_revision')):raise ValueError('EVIDENCE_SCOPE')
        if scope.input_revision:
            boundary=db.scalar(text("SELECT created_at FROM assistant_messages WHERE conversation_id=:cid AND source_revision=:rev AND role='user'"),{'cid':str(cid),'rev':scope.input_revision})
            if boundary is None or _at(boundary)>at:raise ValueError('EVIDENCE_SCOPE_TIME')
        if scope.materials_revision:
            boundary=db.scalar(text('SELECT created_at FROM assistant_material_snapshots WHERE conversation_id=:cid AND revision=:rev'),{'cid':str(cid),'rev':scope.materials_revision})
            if boundary is None or _at(boundary)>at:raise ValueError('EVIDENCE_SCOPE_TIME')
        if snapshot.profile_revision:
            boundary=db.scalar(text('SELECT created_at FROM assistant_profile_revisions WHERE conversation_id=:cid AND revision=:rev'),{'cid':str(cid),'rev':snapshot.profile_revision})
            if boundary is None or _at(boundary)>at:raise ValueError('EVIDENCE_PROFILE_TIME')
        for fact in snapshot.rows:
            inherited=fact.id in previous and previous[fact.id].source==fact.source
            source(fact.source,scope,snapshot.profile_revision,at,db,inherited=inherited)
        previous={r.id:r for r in snapshot.rows};last_scope=scope;last_at=at
        result.append((row,request,snapshot))
    return result


def validate_evidence_records(db, *, allowed=True):
    from ..storage_schema import identify_schema
    schema=[tuple(r) for r in db.execute(text('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))]
    native=any(r[1]=='local_workspace_identity' for r in schema)
    version=identify_schema(schema,native=native)
    if version!='assistant-evidence-v1':return
    ids=db.execute(text('SELECT DISTINCT conversation_id FROM assistant_evidence_revisions')).scalars().all()
    if ids and not allowed:raise ValueError('EVIDENCE_NOT_ALLOWED')
    for cid in ids:history(db,UUID(cid))


def receipt(row):
    return d.EvidenceReceipt(conversation_id=row['conversation_id'],request_id=row['request_id'],revision=row['revision'],
        snapshot_sha256=row['snapshot_sha256'],created_at=_at(row['created_at']))
