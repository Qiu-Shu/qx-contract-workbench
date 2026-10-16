"""Rule registration, explicit approval, and case-scoped customer policy."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from uuid import UUID
from sqlalchemy import select
from ..domain import Rule,RuleSnapshot,PolicySnapshot
from ..config import PROJECT_ROOT
from ..persistence import (read_matter,_editable,_audit_change as audit_change,
    policy_material_changed,_material_changed,MembershipRow)
from ..security import authorize,authorize_rule_manager,rule_reviewer_valid,ServiceError
from ..authorities.registry import (checked_evidence,read_authority,authority_dependency,authority_is_verified)
from ..authorities.storage import digest
from .storage import (RuleSnapshotRow,RuleApprovalRow,RuleInvalidationRow,PolicySnapshotRow,PolicyApprovalRow,
    require_storage,rule_sha256,policy_sha256)

DEFAULT_CARDS=PROJECT_ROOT/'rules'/'default-draft-cards.json'
BLOCKED_RULE_APPROVAL='BLOCKED_RULE_APPROVAL'
_FIELD=re.compile(r'^[A-Za-z][A-Za-z0-9_]*$')
_META_KEYS={'slug','jurisdiction','event_field','enabled','specialist','note'}


def _canonical_identity(rule_id,version):
    if not isinstance(rule_id,str) or not isinstance(version,str) or not re.fullmatch(r'[1-9][0-9]*',version):
        raise ValueError('canonical UUID and positive integer version strings required')
    identifier=UUID(rule_id)
    if str(identifier)!=rule_id: raise ValueError('canonical UUID required')
    if len(version)>9: raise ValueError('version out of range')
    return identifier,int(version)


def _metadata(value):
    result={'slug':None,'jurisdiction':'CN-mainland','event_field':None,'enabled':True,'specialist':None,'note':'Local independently authored rule; legal approval required.'}
    if value is not None:
        if not isinstance(value,dict) or set(value)-_META_KEYS: raise ValueError('unknown rule metadata')
        result.update(value)
    for key in ('slug','event_field','specialist'):
        if result[key] is not None and (not isinstance(result[key],str) or not result[key].strip()): raise ValueError('invalid metadata')
    if result['event_field'] is not None and not _FIELD.fullmatch(result['event_field']): raise ValueError('plain fact field required')
    if result['specialist'] not in (None,'labor','technology'): raise ValueError('unsupported specialist')
    if type(result['enabled']) is not bool or not isinstance(result['jurisdiction'],str) or not result['jurisdiction'].strip(): raise ValueError('invalid metadata')
    if not isinstance(result['note'],str) or not result['note'].strip(): raise ValueError('invalid metadata')
    return result


def load_default_cards():
    """Fixed project-authored data; never load upstream Skills or unknown paths."""
    payload=json.loads(DEFAULT_CARDS.read_text(encoding='utf-8'))
    result=[]
    for item in payload['cards']:
        rule=Rule.model_validate(item['rule'])
        metadata=_metadata(item['metadata'])
        if rule.status!='draft' or rule.authority_ids or rule.approved_by or rule.approved_at:
            raise ValueError('default legal cards must stay draft without invented authorities')
        result.append((metadata['slug'],rule,metadata))
    if len(result)!=14 or len({r.id for _,r,_ in result})!=14: raise ValueError('expected 14 distinct draft cards')
    return tuple(result)


def register_default_cards(actor,*,matter_id,db):
    authorize(actor,matter_id,'confirm_facts',db)
    with db.begin_nested():
        return tuple(register_rule(rule,actor,matter_id=matter_id,db=db,metadata=metadata)
            for _,rule,metadata in load_default_cards())


def register_rule(input,actor,*,matter_id,db,metadata=None):
    authorize(actor,matter_id,'confirm_facts',db)
    require_storage(db)
    _editable(matter_id,db)
    rule=Rule.model_validate_json(input.model_dump_json())
    if (rule.status!='draft' or rule.approved_by is not None or rule.approved_at is not None
        or len(set(rule.authority_ids))!=len(rule.authority_ids)
        or len(set(rule.trigger_facts))!=len(rule.trigger_facts)
        or len(set(rule.exception_facts))!=len(rule.exception_facts)
        or any(not _FIELD.fullmatch(f) for f in rule.trigger_facts+rule.exception_facts)):
        raise ServiceError('RULE_UNAPPROVED',409)
    meta=_metadata(metadata)
    if rule.basis_kind=='law' and meta['event_field'] is None: meta['event_field']='signed_at'
    for authority_id in rule.authority_ids: read_authority(authority_id,actor,matter_id=matter_id,db=db)
    latest=db.scalar(select(RuleSnapshotRow.version).where(RuleSnapshotRow.matter_id==str(matter_id),RuleSnapshotRow.rule_id==str(rule.id))
        .order_by(RuleSnapshotRow.version.desc()).limit(1)) or 0
    if rule.version!=latest+1: raise ServiceError('VERSION_CONFLICT',409)
    policy_binding=None
    if rule.basis_kind=='client_policy':
        matter=read_matter(matter_id,actor,db)
        if matter.active_policy_version is None: raise ServiceError('RULE_UNAPPROVED',409)
        policy=read_policy(matter.active_policy_version,actor,matter_id=matter_id,db=db)
        policy_binding=json.dumps({'client_ref':policy.client_ref,'version':policy.version,'sha256':policy.sha256},sort_keys=True,separators=(',',':'))
    with db.begin_nested():
        db.add(RuleSnapshotRow(matter_id=str(matter_id),rule_id=str(rule.id),version=rule.version,
            payload=rule.model_dump_json(),sha256=rule_sha256(rule),metadata_json=json.dumps(meta,sort_keys=True,ensure_ascii=False,separators=(',',':')),
            policy_binding_json=policy_binding))
        audit_change(matter_id,actor,'rule_registered','rule',db,entity_id=rule.id,after_hash=rule_sha256(rule))
        _material_changed(matter_id,db,'awaiting_fact_confirmation')
    return rule


def _rule_row(identifier,version,matter_id,db):
    row=db.get(RuleSnapshotRow,(str(matter_id),str(identifier),version),populate_existing=True)
    if row is None: raise ServiceError('RULE_UNAPPROVED',409)
    item=Rule.model_validate_json(row.payload)
    if item.id!=identifier or item.version!=version or rule_sha256(item)!=row.sha256: raise ServiceError('VERSION_CONFLICT',409)
    _metadata(json.loads(row.metadata_json))
    return row


def _policy_row(version,matter_id,db):
    if type(version) is not int or version<1: raise ValueError('positive integer version required')
    row=db.get(PolicySnapshotRow,(str(matter_id),version),populate_existing=True)
    if row is None: raise ServiceError('CROSS_MATTER_DENIED',403)
    item=PolicySnapshot.model_validate_json(row.payload)
    if row.sha256!=item.sha256 or row.client_ref!=item.client_ref or item.version!=version or item.sha256!=policy_sha256(item.client_ref,version,item.preferences):
        raise ServiceError('VERSION_CONFLICT',409)
    return row


def _policy_approval(version,matter_id,db):
    return db.scalar(select(PolicyApprovalRow).where(PolicyApprovalRow.matter_id==str(matter_id),PolicyApprovalRow.version==version)
        .order_by(PolicyApprovalRow.sequence.desc()).limit(1))


def policy_is_approved(policy,matter_id,db):
    from ..persistence import MatterRow
    matter_row=db.get(MatterRow,str(matter_id),populate_existing=True)
    if matter_row is None: return False
    current=json.loads(matter_row.payload)
    if policy.client_ref!=current['client_ref'] or policy.version!=current['active_policy_version']:
        return False
    row=_policy_row(policy.version,matter_id,db)
    approval=_policy_approval(policy.version,matter_id,db)
    return bool(approval and approval.sha256==row.sha256 and policy.approved_by==UUID(approval.reviewer_id)
        and policy.approved_at==approval.timestamp and rule_reviewer_valid(policy.approved_by,db)
        and db.get(MembershipRow,(str(matter_id),approval.reviewer_id),populate_existing=True)
        and policy==PolicySnapshot.model_validate_json(approval.payload))


def read_policy(version,actor,*,matter_id,db):
    authorize(actor,matter_id,'read',db)
    require_storage(db)
    matter=read_matter(matter_id,actor,db)
    row=_policy_row(version,matter_id,db)
    if row.client_ref!=matter.client_ref: raise ServiceError('CROSS_MATTER_DENIED',403)
    approval=_policy_approval(version,matter_id,db)
    return PolicySnapshot.model_validate_json(approval.payload if approval else row.payload)


def policy_runtime_sha256(policy,actor,*,matter_id,db):
    """Manifest hash includes ownership and actual approval evidence, no self-claims.

    PolicySnapshot.sha256 is its content hash for approval. This separate runtime
    dependency hash also binds the exact immutable approval record used in a run.
    """
    matter=read_matter(matter_id,actor,db)
    if policy.version!=matter.active_policy_version or policy!=read_policy(policy.version,actor,matter_id=matter_id,db=db):
        raise ServiceError('VERSION_CONFLICT',409)
    if policy.preferences and not policy_is_approved(policy,matter_id,db): raise ServiceError('RULE_UNAPPROVED',409)
    approval=_policy_approval(policy.version,matter_id,db)
    return digest({'matter_id':str(matter_id),'policy':policy.model_dump(mode='json'),'approval':None if approval is None else {
        'sequence':approval.sequence,'reviewer_id':approval.reviewer_id,'timestamp':approval.timestamp.isoformat(),
        'sha256':approval.sha256,'evidence':approval.evidence}})


def save_policy(input,actor,*,matter_id,db):
    authorize(actor,matter_id,'confirm_facts',db)
    require_storage(db)
    _editable(matter_id,db)
    policy=PolicySnapshot.model_validate_json(input.model_dump_json())
    matter=read_matter(matter_id,actor,db)
    if policy.client_ref!=matter.client_ref: raise ServiceError('CROSS_MATTER_DENIED',403)
    if (policy.sha256!=policy_sha256(policy.client_ref,policy.version,policy.preferences)
        or policy.approved_by is not None or policy.approved_at is not None): raise ServiceError('RULE_UNAPPROVED',409)
    latest=db.scalar(select(PolicySnapshotRow.version).where(PolicySnapshotRow.matter_id==str(matter_id))
        .order_by(PolicySnapshotRow.version.desc()).limit(1)) or 0
    if policy.version!=latest+1: raise ServiceError('VERSION_CONFLICT',409)
    with db.begin_nested():
        db.add(PolicySnapshotRow(matter_id=str(matter_id),version=policy.version,client_ref=policy.client_ref,
            sha256=policy.sha256,payload=policy.model_dump_json()))
        policy_material_changed(matter_id,policy.version,actor,db)
        audit_change(matter_id,actor,'policy_changed','policy',db,after_hash=policy.sha256)
    return policy


def approve_policy(version,actor,evidence,*,matter_id,db):
    authorize_rule_manager(actor,matter_id,db)
    require_storage(db)
    _editable(matter_id,db)
    matter=read_matter(matter_id,actor,db)
    if matter.active_policy_version!=version: raise ServiceError('VERSION_CONFLICT',409)
    row=_policy_row(version,matter_id,db)
    if row.client_ref!=matter.client_ref: raise ServiceError('CROSS_MATTER_DENIED',403)
    proof=checked_evidence(evidence,actor,row.sha256)
    now=datetime.now(timezone.utc)
    payload=PolicySnapshot.model_validate_json(row.payload).model_dump(mode='python')
    payload.update(approved_by=actor.user_id,approved_at=now)
    approved=PolicySnapshot.model_validate(payload)
    with db.begin_nested():
        db.add(PolicyApprovalRow(matter_id=str(matter_id),version=version,reviewer_id=str(actor.user_id),
            timestamp=now,sha256=row.sha256,evidence=proof.model_dump_json(),payload=approved.model_dump_json()))
        _material_changed(matter_id,db,'awaiting_fact_confirmation')
        audit_change(matter_id,actor,'policy_approved','policy',db,after_hash=row.sha256)
    return approved


def rule_dependencies(row,db):
    rule=Rule.model_validate_json(row.payload)
    result={'metadata':json.loads(row.metadata_json),'sources':{str(identifier):authority_dependency(identifier,UUID(row.matter_id),db) for identifier in rule.authority_ids},'policy':None}
    if rule.basis_kind=='client_policy':
        from ..persistence import MatterRow
        matter=json.loads(db.get(MatterRow,row.matter_id,populate_existing=True).payload)
        binding=json.loads(row.policy_binding_json) if row.policy_binding_json else None
        version=binding['version'] if binding else None
        if version is not None:
            policy=_policy_row(version,UUID(row.matter_id),db)
            approval=_policy_approval(version,UUID(row.matter_id),db)
            result['policy']={'client_ref':policy.client_ref,'version':version,'sha256':policy.sha256,'binding':binding,
                'active_version':matter['active_policy_version'],'actual_client_ref':matter['client_ref'],
                'approval':None if approval is None else {'reviewer_id':approval.reviewer_id,'timestamp':approval.timestamp.isoformat(),'evidence':approval.evidence,'payload':approval.payload}}
    return result


def _approval(row,db):
    return db.scalar(select(RuleApprovalRow).where(RuleApprovalRow.matter_id==row.matter_id,
        RuleApprovalRow.rule_id==row.rule_id,RuleApprovalRow.version==row.version).order_by(RuleApprovalRow.sequence.desc()).limit(1))


def _invalidations(row,db):
    return db.scalars(select(RuleInvalidationRow).where(RuleInvalidationRow.matter_id==row.matter_id,
        RuleInvalidationRow.rule_id==row.rule_id,RuleInvalidationRow.version==row.version).order_by(RuleInvalidationRow.sequence)).all()


def rule_is_approved(row,db):
    approval=_approval(row,db)
    if (approval is None or approval.rule_sha256!=row.sha256 or approval.dependency_sha256!=digest(rule_dependencies(row,db))
        or not rule_reviewer_valid(UUID(approval.reviewer_id),db)
        or not db.get(MembershipRow,(row.matter_id,approval.reviewer_id),populate_existing=True)
        or any(i.timestamp>=approval.timestamp for i in _invalidations(row,db))): return False
    rule=Rule.model_validate_json(row.payload)
    if rule.authority_ids and not all(authority_is_verified(a,UUID(row.matter_id),db) for a in rule.authority_ids): return False
    if rule.basis_kind=='law': return bool(rule.authority_ids)
    if rule.basis_kind=='client_policy':
        dependency=rule_dependencies(row,db)['policy']
        if dependency is None or dependency['version']!=dependency['active_version'] or dependency['client_ref']!=dependency['actual_client_ref']:
            return False
        version=dependency['version']
        record=_policy_approval(version,UUID(row.matter_id),db)
        if record is None: return False
        policy=PolicySnapshot.model_validate_json(record.payload)
        return policy_is_approved(policy,UUID(row.matter_id),db)
    return True


def approve_rule(rule_id,version,actor,evidence,*,matter_id,db,authority_evidence=None):
    authorize_rule_manager(actor,matter_id,db)
    require_storage(db)
    _editable(matter_id,db)
    identifier,number=_canonical_identity(rule_id,version)
    row=_rule_row(identifier,number,matter_id,db)
    latest=db.scalar(select(RuleSnapshotRow.version).where(RuleSnapshotRow.matter_id==str(matter_id),RuleSnapshotRow.rule_id==str(identifier))
        .order_by(RuleSnapshotRow.version.desc()).limit(1))
    if number!=latest: raise ServiceError('VERSION_CONFLICT',409)
    item=Rule.model_validate_json(row.payload)
    proof=checked_evidence(evidence,actor,row.sha256)
    dependencies=rule_dependencies(row,db)
    if not dependencies['metadata']['enabled'] or dependencies['metadata']['specialist'] is not None:
        raise ServiceError('RULE_UNAPPROVED',409)
    if item.basis_kind=='law' and not item.authority_ids:
        raise ServiceError('RULE_UNAPPROVED',409)
    if item.authority_ids:
        mapping=authority_evidence or {}
        if not isinstance(mapping,dict) or set(mapping)!={str(a) for a in item.authority_ids} or not mapping:
            raise ServiceError('RULE_UNAPPROVED',409)
        for authority_id in item.authority_ids:
            authority=read_authority(authority_id,actor,matter_id=matter_id,db=db)
            checked_evidence(mapping[str(authority_id)],actor,authority.snapshot_sha256)
            if not authority_is_verified(authority_id,matter_id,db) or authority.jurisdiction!=dependencies['metadata']['jurisdiction']:
                raise ServiceError('RULE_UNAPPROVED',409)
    elif authority_evidence: raise ServiceError('RULE_UNAPPROVED',409)
    if item.basis_kind=='client_policy':
        matter=read_matter(matter_id,actor,db)
        policy=read_policy(matter.active_policy_version,actor,matter_id=matter_id,db=db)
        binding=dependencies['policy']
        if (binding is None or binding['version']!=matter.active_policy_version or binding['client_ref']!=matter.client_ref
            or binding['binding']!={'client_ref':policy.client_ref,'version':policy.version,'sha256':policy.sha256}
            or not policy_is_approved(policy,matter_id,db)): raise ServiceError('RULE_UNAPPROVED',409)
    now=datetime.now(timezone.utc)
    payload=item.model_dump(mode='python')
    payload.update(status='approved',approved_by=actor.user_id,approved_at=now)
    approved=Rule.model_validate(payload)
    evidence_payload={'rule':proof.model_dump(mode='json'),'authorities':{key:value.model_dump(mode='json') for key,value in (authority_evidence or {}).items()}}
    with db.begin_nested():
        db.add(RuleApprovalRow(matter_id=str(matter_id),rule_id=rule_id,version=number,
            reviewer_id=str(actor.user_id),timestamp=now,rule_sha256=row.sha256,dependency_sha256=digest(dependencies),
            payload=approved.model_dump_json(),evidence=json.dumps(evidence_payload,ensure_ascii=False,sort_keys=True,separators=(',',':'))))
        _material_changed(matter_id,db,'awaiting_fact_confirmation')
        audit_change(matter_id,actor,'rule_approved','rule',db,entity_id=identifier,after_hash=digest(dependencies))
    return approved


def read_rule_snapshot(actor,*,matter_id,db):
    """All registered versions; no arbitrary newest-rule substitution.

    Hash includes immutable cards, applicability metadata, source text hashes and
    provenance, exact approvals, policies, and recheck events. Current validity is
    rechecked separately so revocation cannot turn a cached approval into proof.
    """
    authorize(actor,matter_id,'read',db)
    require_storage(db)
    rows=db.scalars(select(RuleSnapshotRow).where(RuleSnapshotRow.matter_id==str(matter_id))
        .order_by(RuleSnapshotRow.rule_id,RuleSnapshotRow.version)).all()
    rules=[]; material=[]
    for row in rows:
        _rule_row(UUID(row.rule_id),row.version,matter_id,db)
        approval=_approval(row,db)
        dependencies=rule_dependencies(row,db)
        # Retain the immutable approved representation even when revoked; only
        # select_rules is allowed to decide current applicability/authorization.
        rules.append(Rule.model_validate_json(approval.payload if approval else row.payload))
        material.append({'rule':rules[-1].model_dump(mode='json'),'draft_sha256':row.sha256,
            'dependencies':dependencies,'approval':None if approval is None else {'sequence':approval.sequence,
                'rule_sha256':approval.rule_sha256,'dependency_sha256':approval.dependency_sha256,'evidence':approval.evidence},
            'rechecks':[{'sequence':i.sequence,'at':i.timestamp.isoformat(),'reason':i.reason} for i in _invalidations(row,db)]})
    return RuleSnapshot(rules=tuple(rules),sha256=digest({'matter_id':str(matter_id),'rules':material}))
