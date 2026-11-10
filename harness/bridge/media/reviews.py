"""Approval freezes a complete transitive version set, never a project's future."""
from . import domain as d
from .content import references,validate_script
from .shooting import validate_shooting_plan
from .store import digest


def collect_dependencies(store,refs,*,transaction=None):
    found={}; pending=list(refs)
    while pending:
        ref=pending.pop()
        ref=d.MediaRevisionRef.model_validate(ref.model_dump() if isinstance(ref,d.MediaRevisionRef) else ref)
        key=(ref.kind,ref.entity_id)
        if key in found:
            if found[key]!=ref: raise ValueError('CONFLICTING_REFERENCES')
            continue
        row=store._load(transaction,ref,current=True) if transaction is not None else store.load(ref,current=True)
        if ref.kind=='memory' and row['value']['confirmation']!='confirmed': raise ValueError('MEMORY_NOT_PUBLIC')
        found[key]=ref
        pending.extend(references(row['value']))
    return sorted(found.values(),key=lambda r:(r.kind,r.entity_id))


def package_validation(store,project_ref,refs):
    full=collect_dependencies(store,[project_ref,*refs]); kinds={r.kind for r in full}
    if not {'project','profile','brief','script','shooting_plan'}<=kinds: raise ValueError('INCOMPLETE_PACKAGE')
    if sum(r.kind=='script' for r in full)!=1 or sum(r.kind=='shooting_plan' for r in full)!=1:
        raise ValueError('CONFLICTING_PACKAGE')
    errors=[]
    for ref in full:
        value=store.load(ref,current=True)['value']
        if ref.kind in ('brief','script','shooting_plan') and value['project_ref']!=project_ref.model_dump():
            raise ValueError('PROJECT_MISMATCH')
        if ref.kind=='script': errors.extend(validate_script(store,value).blocking_errors)
        if ref.kind=='shooting_plan': errors.extend(validate_shooting_plan(store,value).blocking_errors)
    return full,list(dict.fromkeys(errors))


def approve_package(store,project_ref,refs):
    full,errors=package_validation(store,project_ref,refs)
    if errors: raise ValueError('REVIEW_BLOCKED: '+','.join(errors))
    payload=[r.model_dump(mode='json') for r in full]
    return store.save('review',dict(project_ref=project_ref.model_dump(),approved_refs=payload,
        dependencies_digest=digest(payload),reviewer=store.actor.user_id,approved_at=d.utc_stamp()),expected_revision=0)


def validate_review(store,review_ref,full):
    if store.readonly: raise PermissionError('RESTORED_READ_ONLY')
    review=store.load(review_ref,current=True)['value']
    if review_ref.kind!='review': raise ValueError('REVIEW_REQUIRED')
    payload=[r.model_dump(mode='json') for r in full]
    if review['approved_refs']!=payload or review['dependencies_digest']!=digest(payload): raise ValueError('REVIEW_MISMATCH')
