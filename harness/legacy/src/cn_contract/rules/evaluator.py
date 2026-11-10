"""Fail-closed server selection. Human strings never become executable triggers."""
from datetime import date,datetime,timezone
from uuid import UUID
from sqlalchemy import select
from ..domain import ReviewContext,RuleSnapshot,RuleSelection,RuleExclusion,ParseResult
from ..persistence import (read_matter,get_fact_snapshot,fact_snapshot_sha256,read_version,get_parse_result,DocumentRow)
from ..security import authorize,ServiceError
from ..facts.storage import trusted_parse
from ..authorities.registry import read_authority
from ..authorities.applicability import effective_on
from .loader import (read_rule_snapshot,read_policy,policy_is_approved,_rule_row,rule_is_approved)
import json


def confirmed_field(facts,field):
    """Only one current explicit confirmed value; unknown conflicts stay unknown."""
    values=[f for f in facts if f.field==field and f.confirmation_status!='rejected']
    if len(values)!=1: return None
    value=values[0]
    if value.confirmation_status not in ('confirmed','corrected') or value.confirmed_at>datetime.now(timezone.utc): return None
    return value


def _trusted_facts(context,actor,db):
    documents={v.id:v for v in context.document_versions}
    if len(documents)!=len(context.document_versions): raise ServiceError('VERSION_CONFLICT',409)
    for version in context.document_versions:
        if version!=read_version(context.matter.id,version.id,actor,db): raise ServiceError('VERSION_CONFLICT',409)
    required=set(a for f in context.fact_snapshot.facts if f.confirmation_status in ('confirmed','corrected') for a in f.anchor_ids)
    anchors=set()
    for version in context.document_versions:
        parsed=get_parse_result(context.matter.id,version.id,actor,db)
        if parsed is None: continue
        if required & {a.id for a in parsed.anchors}:
            trusted_parse(context.matter.id,version.id,actor,db,parsed)
            if db.scalar(select(DocumentRow.id).where(DocumentRow.supersedes_id==str(version.id))):
                raise ServiceError('VERSION_CONFLICT',409)
            anchors.update(a.id for a in parsed.anchors)
    for fact in context.fact_snapshot.facts:
        if fact.matter_id!=context.matter.id: raise ServiceError('CROSS_MATTER_DENIED',403)
        if fact.confirmation_status not in ('confirmed','corrected'): continue
        if fact.provenance_type=='external' or fact.receipt_ids: raise ServiceError('NOT_SUPPORTED',409)
        if (len(set(fact.anchor_ids))!=len(fact.anchor_ids) or not set(fact.anchor_ids).issubset(anchors)
            or fact.provenance_type=='document' and not fact.anchor_ids): raise ServiceError('VERSION_CONFLICT',409)


def select_rules(context,snapshot,*,actor,db,event_dates=None):
    authorize(actor,context.matter.id,'read',db)
    context=ReviewContext.model_validate_json(context.model_dump_json())
    snapshot=RuleSnapshot.model_validate_json(snapshot.model_dump_json())
    matter=read_matter(context.matter.id,actor,db)
    if matter.status=='archived': raise ServiceError('STATE_CONFLICT',409)
    if context.matter!=matter or context.position!=matter.position or matter.position is None:
        raise ServiceError('VERSION_CONFLICT',409)
    if matter.active_fact_version is None or context.fact_snapshot.version!=matter.active_fact_version:
        raise ServiceError('VERSION_CONFLICT',409)
    facts=get_fact_snapshot(matter.id,matter.active_fact_version,actor,db)
    if facts!=context.fact_snapshot or facts.sha256!=fact_snapshot_sha256(facts.facts): raise ServiceError('VERSION_CONFLICT',409)
    _trusted_facts(context,actor,db)
    if matter.active_policy_version is None or context.policy.version!=matter.active_policy_version:
        raise ServiceError('VERSION_CONFLICT',409)
    policy=read_policy(matter.active_policy_version,actor,matter_id=matter.id,db=db)
    if policy!=context.policy or policy.client_ref!=matter.client_ref: raise ServiceError('VERSION_CONFLICT',409)
    if policy.preferences and not policy_is_approved(policy,matter.id,db): raise ServiceError('RULE_UNAPPROVED',409)
    stored=read_rule_snapshot(actor,matter_id=matter.id,db=db)
    identities=[(r.id,r.version) for r in snapshot.rules]
    if len(set(identities))!=len(identities) or snapshot!=stored or context.rules!=stored.rules:
        raise ServiceError('VERSION_CONFLICT',409)
    required_authorities={a for r in stored.rules for a in r.authority_ids}
    if set(context.authority_ids)!=required_authorities or len(set(context.authority_ids))!=len(context.authority_ids):
        raise ServiceError('VERSION_CONFLICT',409)
    if len(set(context.allowed_scope))!=len(context.allowed_scope): raise ServiceError('VERSION_CONFLICT',409)
    # Explicit dates may corroborate facts, never supply missing facts. Validate
    # every supplied value before draft/unapproved filtering can hide an attack.
    event_dates={} if event_dates is None else event_dates
    if not isinstance(event_dates,dict) or set(event_dates)-{str(r.id) for r in stored.rules}:
        raise ValueError('event_dates uses registered canonical rule UUID strings')
    for key,value in event_dates.items():
        if type(value) is not date: raise ValueError('date required')
        for rule in stored.rules:
            if str(rule.id)!=key: continue
            meta=json.loads(_rule_row(rule.id,rule.version,matter.id,db).metadata_json)
            fact=confirmed_field(facts.facts,meta['event_field']) if meta['event_field'] else None
            if fact is None or fact.typed_value.kind!='date' or fact.unit is not None or fact.typed_value.value!=value:
                raise ServiceError('FACTS_UNCONFIRMED',409)
    applied=[];excluded=[]
    def exclude(rule,reason,rationale):
        excluded.append(RuleExclusion(rule_id=rule.id,version=rule.version,reason=reason,rationale=rationale))
    for rule in stored.rules:
        row=_rule_row(rule.id,rule.version,matter.id,db)
        meta=json.loads(row.metadata_json)
        if matter.contract_type=='unknown' or matter.jurisdiction!=meta['jurisdiction']:
            exclude(rule,'unsupported','当前合同类型或法域须转专项，不声明完整审查覆盖。');continue
        if not meta['enabled'] or meta['specialist']=='technology':
            exclude(rule,'unsupported','科技专项默认关闭，需另行批准。');continue
        if meta['specialist']=='labor':
            relationship=confirmed_field(facts.facts,'labor_relationship')
            if relationship is not None and relationship.typed_value.kind=='bool' and relationship.typed_value.value:
                duration=confirmed_field(facts.facts,'noncompete_duration')
                period='已确认期间及单位；' if duration is not None and duration.unit in ('year','month','day') else '期间及单位不足；'
                exclude(rule,'unsupported','劳动专项转交；'+period+'期限待核实，不能输出确定效力结论。')
            else: exclude(rule,'missing_facts','劳动关系适用前提待确认。')
            continue
        if matter.contract_type not in rule.contract_types or matter.position not in rule.positions or not set(rule.coverage_ids).issubset(set(context.allowed_scope)):
            exclude(rule,'not_applicable','合同类型、客户立场或批准审查范围不匹配。');continue
        if not rule_is_approved(row,db):
            exclude(rule,'unapproved',BLOCKED_RULE_APPROVAL_MESSAGE);continue
        trigger_values=[confirmed_field(facts.facts,field) for field in rule.trigger_facts]
        if any(value is None or value.typed_value.kind=='null' for value in trigger_values):
            exclude(rule,'missing_facts','规则触发事实未唯一确认。');continue
        if any(value.typed_value.kind=='bool' and not value.typed_value.value for value in trigger_values):
            exclude(rule,'not_applicable','已确认触发条件不成立。');continue
        exceptions=[confirmed_field(facts.facts,field) for field in rule.exception_facts]
        if any(value is None or value.typed_value.kind!='bool' for value in exceptions):
            exclude(rule,'missing_facts','例外未明确确认，不能当作不存在。');continue
        if any(value.typed_value.value for value in exceptions):
            exclude(rule,'not_applicable','已确认例外适用。');continue
        if meta['event_field']:
            event=confirmed_field(facts.facts,meta['event_field'])
            if event is None or event.typed_value.kind!='date' or event.unit is not None:
                exclude(rule,'missing_facts','规则适用事件日期尚未唯一确认。');continue
            authorities=[read_authority(a,actor,matter_id=matter.id,db=db) for a in rule.authority_ids]
            if any(a.jurisdiction!=matter.jurisdiction or not effective_on(a,event.typed_value.value) for a in authorities):
                exclude(rule,'not_applicable','已确认事件日期不在核验来源的适用窗口，须重新核查时际关系。');continue
        applied.append(rule)
    # Source/event windows may disambiguate historical rule versions. When they
    # do not, neither order nor the highest version is authority to choose one.
    overlapping={rule.id for rule in applied if sum(other.id==rule.id for other in applied)>1}
    for rule in applied:
        if rule.id in overlapping:
            exclude(rule,'missing_facts','同一规则多个批准版本适用条件重叠；时际关系与版本选择须负责人复核。')
    return RuleSelection(applied=tuple(rule for rule in applied if rule.id not in overlapping),excluded=tuple(excluded))


BLOCKED_RULE_APPROVAL_MESSAGE='BLOCKED_RULE_APPROVAL：规则及精确来源/客户政策尚未获得有效负责人批准。'
