"""Replay follow-up history and fixed fact/material links without granting authority."""
from uuid import UUID

from sqlalchemy import text

from .. import domain as d
from . import evidence_records, attachment_records as materials
from .profile_integrity import _at, _model, _scope


def _latest_before(rows, at):
    return next((r['revision'] for r in rows if _at(r['created_at'])<=at),0)


def context(db,cid,scope,profile_revision,evidence_revision,at,*,versions=None):
    if versions is None:versions={s.revision:s for _,_,s in evidence_records.history(db,cid)}
    available={rev:s for rev,s in versions.items() if s.created_at<=at}
    if max(available,default=0)!=evidence_revision:raise ValueError('FOLLOWUP_EVIDENCE_VERSION')
    profile_rows=db.execute(text('SELECT revision,created_at FROM assistant_profile_revisions WHERE conversation_id=:cid ORDER BY revision DESC'),{'cid':str(cid)}).mappings().all()
    if _latest_before(profile_rows,at)!=profile_revision:raise ValueError('FOLLOWUP_PROFILE_VERSION')
    material_rows=db.execute(text('SELECT revision,created_at FROM assistant_material_snapshots WHERE conversation_id=:cid ORDER BY revision DESC'),{'cid':str(cid)}).mappings().all()
    if _latest_before(material_rows,at)!=scope.materials_revision:raise ValueError('FOLLOWUP_MATERIAL_VERSION')
    input_revision=db.execute(text("SELECT source_revision AS revision,created_at FROM assistant_messages WHERE conversation_id=:cid AND role='user' ORDER BY source_revision DESC"),{'cid':str(cid)}).mappings().all()
    if _latest_before(input_revision,at)!=scope.input_revision:raise ValueError('FOLLOWUP_INPUT_VERSION')
    current=available.get(evidence_revision)
    statement=evidence_records.statement(cid,db,profile_revision)[1] if profile_revision else None
    return {'versions':available,'facts':{f.id:f for f in current.rows} if current else {},
        'evidence_revision':evidence_revision,'selection':evidence_records.selected(scope,db),'statement':statement}


def fact(ref,ctx):
    saved=ctx['versions'].get(ref.evidence_revision)
    row=next((f for f in saved.rows if f.id==ref.fact_id),None) if saved else None
    if row is None:raise ValueError('FOLLOWUP_FACT_LINK')
    return row


def attention(item,ctx):
    reasons=[]
    for ref in item.facts:
        old=fact(ref,ctx);current=ctx['facts'].get(ref.fact_id)
        if current is None:reasons.append('关联事实已移出当前底稿')
        elif current!=old:reasons.append('关联事实已更正，请重新核对')
        else:
            source=current.source
            if source.kind=='statement':
                if ctx['statement'] is None or ctx['statement'][source.start:source.end]!=source.quote:reasons.append('关联事实的原始陈述已变化')
            elif source.attachment_id not in ctx['selection'] or source.kind=='document' and ctx['selection'][source.attachment_id]!=source.parse_revision:
                reasons.append('关联事实的材料已移出或重读')
    for ref in item.materials:
        if ref.attachment_id not in ctx['selection']:reasons.append('关联材料已移出当前范围')
        elif ctx['selection'][ref.attachment_id]!=ref.parse_revision:reasons.append('关联材料的读取版本已变化')
    return tuple(dict.fromkeys(reasons))


def links(item,previous,ctx,scope,owner,at,db):
    for ref in item.facts:
        fact(ref,ctx)
        inherited=previous is not None and ref in previous.facts
        if not inherited and (ref.evidence_revision!=ctx['evidence_revision'] or ref.fact_id not in ctx['facts']):raise ValueError('FOLLOWUP_OLD_FACT')
    for ref in item.materials:
        row=db.execute(text('SELECT * FROM assistant_attachments WHERE conversation_id=:cid AND id=:id'),
            {'cid':str(scope.conversation_id),'id':str(ref.attachment_id)}).mappings().first()
        if (row is None or row['owner_id']!=owner or row['workspace_id']!=str(scope.workspace_id)
                or row['sha256']!=ref.original_sha256 or _at(row['created_at'])>at):raise ValueError('FOLLOWUP_MATERIAL_LINK')
        if ref.parse_revision is not None:
            parsed=materials.parse_view(materials.parse_row(scope.conversation_id,ref.attachment_id,ref.parse_revision,db))
            if parsed.created_at>at:raise ValueError('FOLLOWUP_FUTURE_PARSE')
        inherited=previous is not None and ref in previous.materials
        if not inherited and (ref.attachment_id not in ctx['selection'] or ctx['selection'][ref.attachment_id]!=ref.parse_revision):raise ValueError('FOLLOWUP_OLD_MATERIAL')
    newly_completed=item.status=='completed' and (previous is None or previous.status!='completed' or previous.result!=item.result)
    if newly_completed and attention(item,ctx):raise ValueError('FOLLOWUP_RECHECK_REQUIRED')


def history(db,cid):
    conversation=db.execute(text('SELECT * FROM assistant_conversations WHERE id=:cid'),{'cid':str(cid)}).mappings().first()
    rows=db.execute(text('SELECT * FROM assistant_followup_revisions WHERE conversation_id=:cid ORDER BY revision'),{'cid':str(cid)}).mappings().all()
    if len(rows)>200:raise ValueError('FOLLOWUP_LIMIT')
    versions={s.revision:s for _,_,s in evidence_records.history(db,cid)} if rows else {}
    previous={};last_at=None;last_scope=None;output=[]
    for index,row in enumerate(rows,1):
        request=_model(d.FollowupCommitInput,row['request_json'],row['request_sha256'])
        snapshot=_model(d.FollowupSnapshot,row['snapshot_json'],row['snapshot_sha256']);at=_at(row['created_at'])
        if (conversation is None or row['revision']!=index or snapshot.revision!=index or request.base_revision!=index-1
                or str(request.request_id)!=row['request_id'] or request.expected_scope!=snapshot.scope
                or request.expected_profile_revision!=snapshot.profile_revision or request.expected_evidence_revision!=snapshot.evidence_revision
                or request.items!=snapshot.items or snapshot.created_at!=at or row['actor_id']!=conversation['owner_id']
                or db.scalar(text('SELECT user_id FROM sessions WHERE id=:id'),{'id':row['session_id']})!=conversation['owner_id']
                or last_at is not None and at<last_at):raise ValueError('FOLLOWUP_RECORD')
        scope=snapshot.scope;_scope(db,scope,conversation,conversation['workspace_id'],at)
        if last_scope and any(getattr(scope,k)<getattr(last_scope,k) for k in ('binding_revision','input_revision','materials_revision')):raise ValueError('FOLLOWUP_SCOPE')
        ctx=context(db,cid,scope,snapshot.profile_revision,snapshot.evidence_revision,at,versions=versions)
        for item in snapshot.items:links(item,previous.get(item.id),ctx,scope,conversation['owner_id'],at,db)
        previous={i.id:i for i in snapshot.items};last_at=at;last_scope=scope;output.append((row,request,snapshot))
    return output


def validate_followup_records(db,*,allowed=True):
    from ..storage_schema import identify_schema
    schema=[tuple(r) for r in db.execute(text('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))]
    native=any(r[1]=='local_workspace_identity' for r in schema)
    if identify_schema(schema,native=native) not in ('assistant-followups-v1', 'assistant-material-model-v1', 'weixin-personal-v1'):return
    ids=db.execute(text('SELECT DISTINCT conversation_id FROM assistant_followup_revisions')).scalars().all()
    if ids and not allowed:raise ValueError('FOLLOWUP_NOT_ALLOWED')
    for cid in ids:history(db,UUID(cid))


def receipt(row):
    return d.FollowupReceipt(conversation_id=row['conversation_id'],request_id=row['request_id'],revision=row['revision'],
        snapshot_sha256=row['snapshot_sha256'],created_at=_at(row['created_at']))
