"""Authorized local source registration and separate completeness/verification gates."""
from datetime import datetime, timezone
import hashlib
from urllib.parse import urlsplit
from uuid import UUID, uuid4
from sqlalchemy import select
from ..domain import AuthorityInput, Authority, ApprovalEvidence
from ..persistence import read_matter, _editable, _audit_change as audit_change, _material_changed, MembershipRow
from ..security import authorize, authorize_rule_manager, rule_reviewer_valid, ServiceError
from .storage import (AuthoritySnapshotRow,SourceEvidenceRow,SourceAttestationRow,AuthorityVerificationRow,require_storage,digest)


def checked_evidence(evidence,actor,sha256):
    evidence=ApprovalEvidence.model_validate_json(evidence.model_dump_json())
    if (evidence.reviewer_id!=actor.user_id or evidence.reviewed_at>datetime.now(timezone.utc)
        or evidence.text_snapshot_sha256!=sha256):
        raise ServiceError('RULE_UNAPPROVED',409)
    return evidence


def _source_row(authority_id,matter_id,db):
    row=db.get(AuthoritySnapshotRow,str(authority_id),populate_existing=True)
    if row is None or row.matter_id!=str(matter_id):
        raise ServiceError('CROSS_MATTER_DENIED',403)
    source=Authority.model_validate_json(row.payload)
    if digest(source.model_dump(mode='json'))!=row.sha256 or source.id!=UUID(row.id):
        raise ServiceError('VERSION_CONFLICT',409)
    return row


def register_authority(input,actor,*,matter_id,db,supersedes_id=None):
    """Register local text without fetching URLs or accepting a verified claim.

    Each successor receives a new UUID. Scope is the owning case; registration
    invalidates current dependent approvals while historical rows remain intact.
    """
    authorize(actor,matter_id,'confirm_facts',db)
    require_storage(db)
    _editable(matter_id,db)
    input=AuthorityInput.model_validate_json(input.model_dump_json())
    if (input.verification_status!='unverified' or input.verified_by is not None
        or input.verified_at is not None or input.fetched_at and input.fetched_at>datetime.now(timezone.utc)):
        raise ServiceError('RULE_UNAPPROVED',409)
    if supersedes_id is not None:
        _source_row(supersedes_id,matter_id,db)
        if db.scalar(select(AuthoritySnapshotRow.id).where(AuthoritySnapshotRow.supersedes_id==str(supersedes_id))):
            raise ServiceError('VERSION_CONFLICT',409)
    item=Authority(id=uuid4(),**input.model_dump(mode='python'))
    marker=' '.join((item.title,item.issuer,item.url,item.text_snapshot,item.legal_rank)).lower()
    classification='synthetic' if 'synthetic' in marker or '虚构' in marker else 'unreviewed'
    with db.begin_nested():
        db.add(AuthoritySnapshotRow(id=str(item.id),matter_id=str(matter_id),
            supersedes_id=str(supersedes_id) if supersedes_id else None,classification=classification,
            payload=item.model_dump_json(),sha256=digest(item.model_dump(mode='json'))))
        db.flush()
        if supersedes_id is not None:
            from ..rules.storage import RuleSnapshotRow, RuleInvalidationRow, require_storage as require_rules
            require_rules(db)
            for row in db.scalars(select(RuleSnapshotRow).where(RuleSnapshotRow.matter_id==str(matter_id))):
                from ..domain import Rule
                if supersedes_id in Rule.model_validate_json(row.payload).authority_ids:
                    db.add(RuleInvalidationRow(matter_id=row.matter_id,rule_id=row.rule_id,version=row.version,
                        timestamp=datetime.now(timezone.utc),reason='authority_changed_requires_review'))
            _material_changed(matter_id,db,'awaiting_fact_confirmation')
        audit_change(matter_id,actor,'authority_registered','authority',db,entity_id=item.id,after_hash=item.snapshot_sha256)
    return item


def read_authority(authority_id,actor,*,matter_id,db):
    authorize(actor,matter_id,'read',db)
    require_storage(db)
    row=_source_row(authority_id,matter_id,db)
    verified=db.scalar(select(AuthorityVerificationRow).where(AuthorityVerificationRow.authority_id==row.id)
        .order_by(AuthorityVerificationRow.timestamp.desc(),AuthorityVerificationRow.id).limit(1))
    return Authority.model_validate_json(verified.payload if verified else row.payload)


def _complete_source_candidate(item):
    """Conservative intake gate; a human still must verify substantive completeness."""
    parsed=urlsplit(item.url)
    host=parsed.hostname or ''
    ranks={'law','administrative_regulation','judicial_interpretation','departmental_rule','local_regulation'}
    marker=(item.title+' '+item.text_snapshot).lower()
    return bool(not any(term in marker for term in ('征求意见稿','草案','检索摘要','搜索摘要','正文待取得','draft','search snippet','search result'))
        and parsed.scheme in ('http','https') and host.endswith(('.gov.cn','.court.gov.cn'))
        and not parsed.username and not parsed.password and parsed.port in (None,80,443)
        and item.legal_rank in ranks and item.text_snapshot.strip()!=item.title.strip()
        and len(item.text_snapshot.strip())>=128 and item.promulgated_at is not None
        and item.effective_from is not None and item.fetch_status=='fetched')


def register_source_evidence(authority_id,actor,*,matter_id,db,source_bytes):
    """Responsible human uploads an exact locally acquired UTF-8 source artifact.

    Bytes are supplied, never a client path/URL. This append-only evidence is
    necessary but does not itself attest completeness or legal applicability.
    """
    authorize_rule_manager(actor,matter_id,db)
    require_storage(db)
    _editable(matter_id,db)
    row=_source_row(authority_id,matter_id,db)
    item=Authority.model_validate_json(row.payload)
    if (row.classification=='synthetic' or not _complete_source_candidate(item)
        or type(source_bytes) is not bytes or source_bytes!=item.text_snapshot.encode('utf-8')):
        raise ServiceError('RULE_UNAPPROVED',409)
    identifier=uuid4()
    with db.begin_nested():
        db.add(SourceEvidenceRow(id=str(identifier),authority_id=row.id,acquired_by=str(actor.user_id),
            timestamp=datetime.now(timezone.utc),source_sha256=row.sha256,
            artifact_sha256=hashlib.sha256(source_bytes).hexdigest(),original_bytes=source_bytes))
        audit_change(matter_id,actor,'authority_registered','authority',db,entity_id=item.id,after_hash=row.sha256)
    return 'local-evidence:'+str(identifier)


def attest_authority_source(authority_id,actor,evidence,*,matter_id,db,provenance_ref):
    """Explicit human completeness review, never a route or metadata claim.

    A responsible rule manager must separately record the acquired full official
    text, issuer/rank/jurisdiction and temporal/exception review against its entire
    registration hash. No synthetic registration can receive this attestation.
    The opaque local evidence reference is stored, never fetched or executed.
    """
    authorize_rule_manager(actor,matter_id,db)
    _editable(matter_id,db)
    row=_source_row(authority_id,matter_id,db)
    item=Authority.model_validate_json(row.payload)
    proof=checked_evidence(evidence,actor,row.sha256)
    if (row.classification=='synthetic' or not _complete_source_candidate(item) or not isinstance(provenance_ref,str)
        or not provenance_ref.startswith('local-evidence:')
        or item.fetch_status!='fetched' or not item.text_snapshot.strip() or item.effective_from is None
        or item.promulgated_at is None or item.fetched_at is None or proof.reviewed_at<item.fetched_at):
        raise ServiceError('RULE_UNAPPROVED',409)
    try:
        identifier=UUID(provenance_ref[15:])
        if str(identifier)!=provenance_ref[15:]: raise ValueError('canonical evidence id required')
    except ValueError:
        raise ServiceError('RULE_UNAPPROVED',409) from None
    artifact=db.get(SourceEvidenceRow,str(identifier),populate_existing=True)
    if (artifact is None or artifact.authority_id!=row.id or artifact.source_sha256!=row.sha256
        or artifact.original_bytes!=item.text_snapshot.encode('utf-8')
        or artifact.artifact_sha256!=item.snapshot_sha256 or proof.reviewed_at<artifact.timestamp):
        raise ServiceError('RULE_UNAPPROVED',409)
    with db.begin_nested():
        db.add(SourceAttestationRow(id=str(uuid4()),authority_id=row.id,reviewer_id=str(actor.user_id),
            timestamp=datetime.now(timezone.utc),classification='official_complete',source_sha256=row.sha256,
            provenance_ref=provenance_ref,evidence=proof.model_dump_json()))
        audit_change(matter_id,actor,'authority_verified','authority',db,entity_id=item.id,after_hash=row.sha256)


def verify_authority(authority_id,actor,evidence,*,matter_id,db):
    authorize_rule_manager(actor,matter_id,db)
    require_storage(db)
    _editable(matter_id,db)
    row=_source_row(authority_id,matter_id,db)
    item=Authority.model_validate_json(row.payload)
    proof=checked_evidence(evidence,actor,item.snapshot_sha256)
    attestation=db.scalar(select(SourceAttestationRow).where(SourceAttestationRow.authority_id==row.id)
        .order_by(SourceAttestationRow.timestamp.desc()).limit(1))
    if (row.classification=='synthetic' or attestation is None or attestation.classification!='official_complete'
        or attestation.source_sha256!=row.sha256 or not rule_reviewer_valid(UUID(attestation.reviewer_id),db)
        or not db.get(MembershipRow,(str(matter_id),attestation.reviewer_id),populate_existing=True)
        or not _complete_source_candidate(item) or item.fetch_status!='fetched' or item.effective_from is None
        or item.promulgated_at is None or item.fetched_at is None or proof.reviewed_at<item.fetched_at
        or db.scalar(select(AuthoritySnapshotRow.id).where(AuthoritySnapshotRow.supersedes_id==row.id))):
        raise ServiceError('RULE_UNAPPROVED',409)
    payload=item.model_dump(mode='python')
    now=datetime.now(timezone.utc)
    payload.update(verification_status='verified',verified_by=actor.user_id,verified_at=now)
    verified=Authority.model_validate(payload)
    with db.begin_nested():
        db.add(AuthorityVerificationRow(id=str(uuid4()),authority_id=row.id,attestation_id=attestation.id,
            reviewer_id=str(actor.user_id),timestamp=now,payload=verified.model_dump_json(),evidence=proof.model_dump_json()))
        audit_change(matter_id,actor,'authority_verified','authority',db,entity_id=item.id,after_hash=item.snapshot_sha256)
    return verified


def authority_dependency(authority_id,matter_id,db):
    """Protected deterministic material and approval provenance for rule hashes."""
    row=_source_row(authority_id,matter_id,db)
    verifications=db.scalars(select(AuthorityVerificationRow).where(AuthorityVerificationRow.authority_id==row.id)
        .order_by(AuthorityVerificationRow.timestamp,AuthorityVerificationRow.id)).all()
    attestations=db.scalars(select(SourceAttestationRow).where(SourceAttestationRow.authority_id==row.id)
        .order_by(SourceAttestationRow.timestamp,SourceAttestationRow.id)).all()
    successors=db.scalars(select(AuthoritySnapshotRow.id).where(AuthoritySnapshotRow.supersedes_id==row.id).order_by(AuthoritySnapshotRow.id)).all()
    return {'source_sha256':row.sha256,'classification':row.classification,'predecessor':row.supersedes_id,
        'verifications':[{'id':v.id,'reviewer':v.reviewer_id,'at':v.timestamp.isoformat(),'payload':v.payload,'evidence':v.evidence,'attestation':v.attestation_id} for v in verifications],
        'attestations':[{'id':a.id,'reviewer':a.reviewer_id,'at':a.timestamp.isoformat(),'classification':a.classification,'sha256':a.source_sha256,'provenance_ref':a.provenance_ref,'evidence':a.evidence} for a in attestations],
        'successors':list(successors)}


def authority_is_verified(authority_id,matter_id,db):
    dependency=authority_dependency(authority_id,matter_id,db)
    if dependency['classification']=='synthetic' or dependency['successors'] or not dependency['verifications']:
        return False
    latest=dependency['verifications'][-1]
    item=Authority.model_validate_json(latest['payload'])
    attestation=next((a for a in dependency['attestations'] if a['id']==latest['attestation']),None)
    return bool(attestation and attestation['classification']=='official_complete'
        and attestation['sha256']==dependency['source_sha256'] and item.verification_status=='verified'
        and item.verified_by==UUID(latest['reviewer']) and item.verified_at==datetime.fromisoformat(latest['at'])
        and rule_reviewer_valid(item.verified_by,db) and rule_reviewer_valid(UUID(attestation['reviewer']),db)
        and db.get(MembershipRow,(str(matter_id),latest['reviewer']),populate_existing=True)
        and db.get(MembershipRow,(str(matter_id),attestation['reviewer']),populate_existing=True))
