"""Audience-specific projections of immutable saved sources, with no new writes."""
import hashlib
from datetime import datetime
from uuid import UUID, NAMESPACE_URL, uuid5

from sqlalchemy import text

from .. import domain as d
from ..config import canonical_json
from ..ops.storage import require_active
from ..security import ServiceError
from . import service, profile_store
from .providers.attempts import read_attempt

_BINDING = ('workspace_id','conversation_id','scope_kind','scope_ref','binding_revision')
_LABELS = {'title':'事项标题','contact':'联系方式','consultation':'咨询经过','questions':'待追问事项',
           'materials':'材料清单','follow_up_at':'跟进时间','follow_up_note':'跟进备注',
           'client_reply':'客户回复','internal_notes':'律师内部意见','principal_amount':'本金',
           'interest_amount':'利息','payment_amount':'已付款项'}
_NOTE = '工作草稿 · 事实与依据待核。未经律师审核，不是正式法律意见。'


def _current(actor, cid, db):
    row = service._owned(actor, cid, db)
    require_active(db)
    return service._snapshot(row)


def _binding(saved, current):
    if (any(getattr(saved,k) != getattr(current,k) for k in _BINDING)
            or saved.input_revision > current.input_revision
            or saved.materials_revision > current.materials_revision):
        raise ServiceError('VERSION_CONFLICT',409)


def _value(field):
    if field.protected_value is not None:
        return field.protected_value
    values = {canonical_json(c.value.model_dump(mode='json')):c.value for c in field.candidates
              if c.value.kind != 'null'}
    if len(values) > 1:
        raise ServiceError('VERSION_CONFLICT',409)
    return next(iter(values.values()),None)


def _format(value):
    if value is None or value.kind == 'null':
        return ''
    if value.kind == 'text':
        return value.value
    if value.kind == 'list':
        return '\n'.join('• '+x for x in value.value)
    if value.kind == 'materials':
        states = {'needed':'待补充','received':'已收到 · 待核对','checked':'律师标记已核对'}
        return '\n'.join('• '+x.name+' — '+states[x.state] for x in value.value)
    if value.kind == 'money':
        return format(value.value,'f')+' '+value.unit
    return value.value.isoformat()


def _profile(actor, cid, revision, db, current):
    saved = profile_store._profile(cid,db,revision)
    if saved is not None:
        _binding(saved.scope,current)
    return saved


def _client_text(saved):
    field = next((f for f in saved.fields if f.field == 'client_reply'),None)
    value = _format(_value(field)) if field is not None else ''
    if not value.strip():
        raise ServiceError('VERSION_CONFLICT',409)
    return value


def list_outputs(actor, cid, db, *, before=None):
    current = _current(actor,cid,db)
    options = []
    # Walk immutable profile versions first, then model answers. One typed cursor
    # identifies a real owned source, with at most 20 options in every response.
    if before is None or before.kind == 'profile':
        if before is not None:
            profile_store._profile(cid,db,before.profile_revision)
        revisions = db.scalars(text('''SELECT revision FROM assistant_profile_revisions
            WHERE conversation_id=:cid AND (:before IS NULL OR revision<:before)
            ORDER BY revision DESC LIMIT 21'''),
            {'cid':str(cid),'before':before.profile_revision if before else None}).all()
        for revision in revisions[:20]:
            profile = profile_store._profile(cid,db,revision)
            if any(getattr(profile.scope,k) != getattr(current,k) for k in _BINDING):
                continue
            _binding(profile.scope,current)
            audiences = ['internal']
            try:
                _client_text(profile)
                audiences.insert(0,'client')
            except ServiceError:
                pass
            options.append(d.AssistantOutputOption(source=d.AssistantOutputSource(kind='profile',profile_revision=revision),
                label=f'档案草稿 · 版本 {revision}',audiences=tuple(audiences)))
        if len(revisions)>20:
            return d.AssistantOutputList(conversation_id=cid,items=tuple(options),
                next_before=d.AssistantOutputSource(kind='profile',profile_revision=revisions[19]))
    parameters = {'cid':str(cid)}
    boundary = ''
    if before is not None and before.kind == 'model':
        anchor = db.scalar(text('SELECT rowid FROM assistant_model_outputs WHERE id=:id AND conversation_id=:cid'),
                           {**parameters,'id':str(before.output_id)})
        if anchor is None:
            raise ServiceError('CROSS_MATTER_DENIED',403)
        boundary = ' AND o.rowid<:before'
        parameters['before'] = anchor
    room = 20-len(options)
    parameters['limit'] = room+1
    rows = db.execute(text('''SELECT o.id,o.scope_json,o.created_at FROM assistant_model_outputs o
        JOIN assistant_runs r ON r.id=o.run_id AND r.conversation_id=o.conversation_id
        JOIN assistant_model_attempts a ON a.id=o.attempt_id AND a.run_id=r.id
        WHERE o.conversation_id=:cid AND r.state='completed' AND a.state='received' '''+boundary+
        ' ORDER BY o.rowid DESC LIMIT :limit'),parameters).mappings().all()
    for row in rows[:room]:
        try:
            saved = d.ScopeSnapshot.model_validate_json(row['scope_json'])
        except ValueError:
            raise ServiceError('VERSION_CONFLICT',409) from None
        # Old bindings stay in their archive; do not offer them in a new case.
        if any(getattr(saved,k) != getattr(current,k) for k in _BINDING):
            continue
        options.append(d.AssistantOutputOption(source=d.AssistantOutputSource(kind='model',output_id=row['id']),
            label='已保存回答 · '+row['created_at'],audiences=('internal',)))
    cursor = (d.AssistantOutputSource(kind='model',output_id=rows[room-1]['id']) if room else options[-1].source) if len(rows)>room else None
    return d.AssistantOutputList(conversation_id=cid,items=tuple(options),next_before=cursor)


def preview(actor, cid, selected, db):
    selected = d.AssistantOutputSelection.model_validate(selected.model_dump(mode='python'))
    current = _current(actor,cid,db)
    citations = []
    if selected.source.kind == 'profile':
        saved = _profile(actor,cid,selected.source.profile_revision,db,current)
        source_label = f'已保存档案 · 版本 {saved.revision}'
        if selected.audience == 'client':
            body = _client_text(saved)
            source_label += ' · 客户回复'
        else:
            sections = []
            for field in saved.fields:
                try:
                    content = _format(_value(field))
                except ServiceError:
                    content = '存在多个候选，请在档案中核对；本次未导出候选正文。'
                if content.strip():
                    sections.append(_LABELS[field.field]+'\n'+content)
            body = '\n\n'.join(sections)
    else:
        if selected.audience != 'internal':
            raise ServiceError('NOT_SUPPORTED',422)
        row = db.execute(text('SELECT * FROM assistant_model_outputs WHERE id=:id AND conversation_id=:cid'),
            {'id':str(selected.source.output_id),'cid':str(cid)}).mappings().first()
        if row is None:
            raise ServiceError('CROSS_MATTER_DENIED',403)
        try:
            attempt = read_attempt(actor,UUID(row['attempt_id']),db)
            saved = attempt.output
            run = db.execute(text('SELECT state,conversation_id FROM assistant_runs WHERE id=:id'),
                             {'id':row['run_id']}).mappings().one()
            if (attempt.state != 'received' or saved is None or saved.id != selected.source.output_id
                    or saved.run_id != attempt.run_id or str(saved.run_id) != row['run_id']
                    or saved.scope != attempt.scope or saved.scope != d.ScopeSnapshot.model_validate_json(row['scope_json'])
                    or saved.created_at != datetime.fromisoformat(row['created_at'])):
                raise ValueError('output identity')
            if run['state'] != 'completed' or run['conversation_id'] != str(cid):
                raise ValueError('incomplete run')
            _binding(saved.scope,current)
        except ValueError:
            raise ServiceError('VERSION_CONFLICT',409) from None
        body = saved.candidate.text
        source_label = '已保存模型回答 · '+saved.created_at.isoformat()
        for citation in saved.candidate.citations:
            if hasattr(citation,'saved_citation_id'):
                citations.append('已保存资料片段：'+str(citation.saved_citation_id))
            else:
                citations.append('本次输入原文：'+str(citation.message_id)+'；SHA256 '+citation.quote_sha256)
    if not body.strip():
        raise ServiceError('VERSION_CONFLICT',409)
    values = dict(conversation_id=str(cid),selection=selected.model_dump(mode='json'),
        title='客户回复草稿' if selected.audience == 'client' else '律师内部工作稿',
        source_label=source_label,text=body,notes=(_NOTE,),citations=tuple(citations),review_status='unverified')
    digest = hashlib.sha256(canonical_json(values).encode()).hexdigest()
    return d.AssistantOutputPreview(id=uuid5(NAMESPACE_URL,'qx-assistant-output:'+digest),
                                    content_sha256=digest,**values)


def checked_export(actor, cid, value, db):
    result = preview(actor,cid,d.AssistantOutputSelection(source=value.source,audience=value.audience),db)
    if result.content_sha256 != value.expected_content_sha256:
        raise ServiceError('VERSION_CONFLICT',409)
    return result
