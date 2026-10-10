"""Case-bound human legal support and negotiation records, not legal inference."""
from ..domain import FindingBasisReview, FindingBasisReviewInput, ReviewContext
from ..security import ServiceError
from ..authorities.registry import read_authority, authority_dependency, authority_is_verified
from ..authorities.applicability import effective_on
from ..authorities.storage import digest
from .storage import ReviewRunRow


def check_basis(value, run, actor, db):
    value=FindingBasisReviewInput.model_validate(value.model_dump(mode='python',include=set(FindingBasisReviewInput.model_fields)))
    if value.policy_sha256 != run.manifest.policy_sha256:
        raise ServiceError('APPROVAL_STALE',409)
    row=db.get(ReviewRunRow,str(run.id),populate_existing=True)
    context=ReviewContext.model_validate_json(row.context_json)
    status='not_legal_basis'; dependency=None
    if value.kind == 'law':
        authority=read_authority(value.authority_id,actor,matter_id=run.matter_id,db=db)
        if authority.snapshot_sha256 != value.source_sha256 or value.quote not in authority.text_snapshot:
            raise ServiceError('VERSION_CONFLICT',409)
        provenance=authority_dependency(value.authority_id,run.matter_id,db)
        if provenance['successors']:
            raise ServiceError('APPROVAL_STALE',409)
        if value.applicability=='applies' and not effective_on(authority,value.event_date):
            raise ServiceError('RULE_UNAPPROVED',409)
        status='verified' if authority_is_verified(value.authority_id,run.matter_id,db) else 'unverified'
        dependency=digest(provenance)
    return FindingBasisReview(**value.model_dump(mode='python'),source_status=status,
        source_dependency_sha256=dependency,position=context.position)


def ensure_current(value,run,actor,db):
    if check_basis(value,run,actor,db) != value:
        raise ServiceError('APPROVAL_STALE',409)


def current_source(value,matter_id,db):
    if value.kind=='business_preference':return True
    dependency=authority_dependency(value.authority_id,matter_id,db)
    status='verified' if authority_is_verified(value.authority_id,matter_id,db) else 'unverified'
    return (not dependency['successors'] and digest(dependency)==value.source_dependency_sha256
            and status==value.source_status)


def describe(value, *, internal=False):
    if value.kind=='business_preference':
        text='商业偏好（非法律命令）；仅适用于本次案件、立场和政策版本。'
    else:
        source={'verified':'法源真实性已有受控核验记录','unverified':'法源真实性未核验'}[value.source_status]
        support={'pending':'命题支持待核','supported':'律师记录支持该命题','not_supported':'不支持该命题'}[value.support]
        applies={'pending':'案件适用性待核','applies':'律师记录适用于所填时点','not_applies':'不适用于本案'}[value.applicability]
        text=source+'；'+support+'；'+applies+'。仅为本条法源记录，不代表全部引用或法律审查完成。'
    if internal:
        text+='\n命题：'+value.proposition+'\n支持理由：'+value.support_reason+'\n适用理由：'+value.applicability_reason
        text+='\n立场：'+value.position.value+'；政策摘要：'+value.policy_sha256
        if value.kind=='law':
            text+='\n法源ID：'+str(value.authority_id)+'；快照摘要：'+value.source_sha256+'\n原文摘录：'+value.quote
            text+='\n适用时点：'+value.event_date.isoformat()
        for label,name in [('标准立场','standard_position'),('退让方案','fallback_position'),('升级条件','escalation_conditions')]:
            if getattr(value,name):text+='\n'+label+'：'+getattr(value,name)
    return text
