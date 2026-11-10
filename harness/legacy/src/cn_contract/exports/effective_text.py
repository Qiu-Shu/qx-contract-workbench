"""Bound accepted-text projection and explicit lawyer re-review, never inference."""
import re
from uuid import UUID, uuid4

from .. import domain as d
from ..documents.ingest import _parse
from ..persistence import read_original, read_version, configured_database
from ..security import ServiceError
from . import storage as s
from .redline_adapter import verify_plain_changes

SNAPSHOT_KIND = 'effective_text'
REVIEW_KIND = 'effective_text_review'
DIMENSIONS = ('legal', 'amounts', 'deadlines', 'attachments', 'definitions_references')
# Inventory only: no implicit currency conversion, arithmetic or completeness claim.
NUMBER = re.compile(r'(?<![A-Za-z_\d.＋+−-])[＋+−-]?\d+(?:\.\d+)?\s*(?:万元|元|％|%|天|日|个月|月|年)')
DEADLINE = re.compile(r'\d{4}年\d{1,2}月\d{1,2}日|[＋+−-]?\d+\s*(?:个工作日|工作日|天|日|个月|月|年)')
REFERENCE = re.compile(r'第[一二三四五六七八九十百零\d]+[条款]|附件[一二三四五六七八九十\d]*|[“「][^”」\n]{1,80}[”」]')


def _signals(documents):
    signals = []
    for document in documents:
        for paragraph in document.paragraphs:
            for kind, pattern in (('number', NUMBER), ('deadline', DEADLINE), ('reference', REFERENCE)):
                for match in pattern.finditer(paragraph.text):
                    signals.append(d.EffectiveTextSignal(kind=kind, document_version_id=document.version_id,
                        anchor_id=paragraph.anchor_id, quote=match.group()))
    # A changed amount/term surviving elsewhere is a lead, not proof of conflict.
    removed = set()
    for document in documents:
        for paragraph in document.paragraphs:
            if paragraph.patch_id:
                for pattern in (NUMBER, REFERENCE):
                    removed.update(set(pattern.findall(paragraph.original_text)) - set(pattern.findall(paragraph.text)))
    for signal in tuple(signals):
        if signal.quote in removed:
            signals.append(signal.model_copy(update={'kind': 'old_value_remaining'}))
    return tuple(signals)


def save_effective_text(bundle, run, snapshot, patches, applied, manual, actor, db):
    """Only internal bundles carry a full-text view; outside reports stay filtered."""
    if bundle.audience != 'internal':
        return
    documents = []
    settings = configured_database(db).settings
    for version_id in run.manifest.document_hashes:
        version = read_version(run.matter_id, version_id, actor, db)
        parsed = _parse(read_original(run.matter_id, version_id, actor, db), version, settings)
        artifact, applied_ids = applied.get(version_id, (None, set()))
        updates = {p.anchor_id: p for p in patches if p.id in applied_ids}
        effective = parsed
        limitations = (*parsed.unsupported_parts, *parsed.quality_issues)
        if artifact:
            raw = s.checked_bytes(artifact.storage_ref, artifact.content_sha256, db)
            verify_plain_changes(raw, [(updates[a.id], a) for a in parsed.anchors if a.id in updates], settings)
            derived = version.model_copy(update={'sha256': artifact.content_sha256, 'baseline_view': d.BaselineView.ACCEPTED_VIEW})
            effective = _parse(raw, derived, settings)
            # The fixed writer only adds the two watermark relationships; patch
            # strings cannot alter the package graph. Original relationship limits
            # remain in `limitations`, even if their path is in this generated set.
            generated = {'word/t09DraftHeader.xml', 'word/t09DraftFooter.xml',
                'word/_rels/document.xml.rels', 'word/document.xml:revisions:manual_required'}
            limitations = tuple(dict.fromkeys((*limitations,
                *(p for p in effective.unsupported_parts if p not in generated), *effective.quality_issues)))
        original_by_location = {(a.part_name, a.element_id): a for a in parsed.anchors}
        paragraphs = []
        for a in effective.anchors:
            original = original_by_location.get((a.part_name, a.element_id))
            patch = updates.get(original.id) if original else None
            paragraphs.append(d.EffectiveParagraph(anchor_id=original.id if original else a.id,
                location=a.part_name + ':' + a.element_id, kind=a.kind,
                original_text=original.quote if original else '', text=a.quote, patch_id=patch.id if patch else None))
        paragraphs = tuple(paragraphs)
        if not paragraphs:
            limitations += ('没有可读文字；不得声明全文已核对。',)
        if version.original_name.lower().endswith('.pdf'):
            limitations += ('PDF仅展示结构提取文字，原页及图像文字需另行人工核对。',)
        documents.append(d.EffectiveDocument(version_id=version_id, original_sha256=version.sha256,
            original_name=version.original_name, baseline_view=version.baseline_view, artifact_id=artifact.id if artifact else None,
            paragraphs=paragraphs, limitations=limitations))
    limitations = tuple('存在未落实的人工修改：' + item['reason'] for item in manual)
    value = d.EffectiveTextSnapshot(bundle_id=bundle.id, matter_id=run.matter_id, run_id=run.id,
        bundle_manifest_sha256=bundle.manifest_sha256, decision_snapshot_sha256=snapshot.sha256,
        artifact_hashes={a.id: a.content_sha256 for a in bundle.artifacts}, documents=tuple(documents),
        signals=_signals(documents), limitations=limitations, sha256='0' * 64)
    value = value.model_copy(update={'sha256': s.sha(value.model_dump(mode='json', exclude={'sha256'}))})
    s.append(SNAPSHOT_KIND, bundle.id, value.model_dump(mode='json'), actor, run.matter_id, db)


def read_effective_text(matter_id, bundle_id, actor, *, db):
    from .approvals import _bundle, require_current_artifact
    s.authorize(actor, matter_id, db)
    bundle, run = _bundle(bundle_id, actor, db)
    if bundle.matter_id != matter_id:
        raise ServiceError('CROSS_MATTER_DENIED', 403)
    if bundle.audience != 'internal':
        raise ServiceError('NOT_SUPPORTED', 409)
    for artifact in bundle.artifacts:
        require_current_artifact(artifact, db)
    row = s.latest(SNAPSHOT_KIND, bundle_id, db)
    if not row or row.matter_id != str(matter_id):
        raise ServiceError('APPROVAL_STALE', 409)
    try:
        value = d.EffectiveTextSnapshot.model_validate_json(row.payload)
        if (value.bundle_id != bundle.id or value.matter_id != matter_id or value.run_id != run.id or
                value.bundle_manifest_sha256 != bundle.manifest_sha256 or
                value.sha256 != s.sha(value.model_dump(mode='json', exclude={'sha256'})) or
                dict(value.artifact_hashes) != {a.id: a.content_sha256 for a in bundle.artifacts} or
                {v.version_id: v.original_sha256 for v in value.documents} != dict(run.manifest.document_hashes)):
            raise ValueError('effective text binding differs')
    except ValueError:
        raise ServiceError('VERSION_CONFLICT', 409) from None
    return value


def _review_context(matter_id, bundle_id, actor, db):
    from ..review.proposals import require_assisted_policy
    from ..review.decisions import read_snapshot, disposition
    require_assisted_policy(db)
    value = read_effective_text(matter_id, bundle_id, actor, db=db)
    snapshot = read_snapshot(matter_id, value.run_id, actor, db=db)
    if snapshot.sha256 != value.decision_snapshot_sha256:
        raise ServiceError('APPROVAL_STALE', 409)
    if any(disposition(f) in {'unreviewed', 'pending_edit'} for f in snapshot.resolved_findings):
        raise ServiceError('STATE_CONFLICT', 409)
    return value, snapshot


def _legal_ready(snapshot, matter_id, actor, db):
    from ..review.decisions import disposition
    from ..review.proposals import read_proposal
    proposal = read_proposal(matter_id, snapshot.run_id, actor, db)
    inputs = dict(zip(proposal.finding_ids, proposal.input.opinions))
    verified_law = False
    for finding in snapshot.resolved_findings:
        if disposition(finding) == 'reject':
            continue
        if disposition(finding) in {'refer', 'request_info'}:
            return False
        basis = finding.human_decision.basis_review
        candidate = inputs[finding.id]
        # QX05 currently binds one legal proposition; multiple references remain pending.
        legal = candidate.basis_kind == 'pending_authority' or bool(candidate.authority_refs)
        if basis and basis.kind == 'law':
            legal = True
        if legal:
            if (not basis or basis.kind != 'law' or len(candidate.authority_refs) > 1 or
                    basis.source_status != 'verified' or basis.support != 'supported' or basis.applicability != 'applies'):
                return False
            verified_law = True
    return verified_law


def record_effective_review(matter_id, value, actor, *, db):
    s.authorize(actor, matter_id, db, write=True)
    value = d.EffectiveTextReviewInput.model_validate_json(value.model_dump_json())
    text, snapshot = _review_context(matter_id, value.bundle_id, actor, db)
    if value.effective_text_sha256 != text.sha256:
        raise ServiceError('VERSION_CONFLICT', 409)
    if value.legal.status == 'reviewed' and not _legal_ready(snapshot, matter_id, actor, db):
        raise ServiceError('RULE_UNAPPROVED', 409)
    limited = bool(text.limitations or any(doc.limitations for doc in text.documents))
    complete = all(getattr(value, name).status == 'reviewed' for name in DIMENSIONS)
    record = d.EffectiveTextReview(**value.model_dump(mode='python'), id=uuid4(), matter_id=matter_id,
        actor_id=actor.user_id, reviewed_at=s.now(),
        status='reviewed_within_read_scope' if complete and not limited else 'pending')
    with db.begin_nested():
        row = s.append(REVIEW_KIND, record.id, record.model_dump(mode='json'), actor, matter_id, db)
        s.append('effective_review_current', value.bundle_id, {'review_id': str(record.id)}, actor, matter_id, db)
        s.audit(actor, matter_id, 'effective_text_reviewed', 'LAWYER_REREVIEW_RECORDED', db,
            entity_id=record.id, after_hash=row.sha256)
        read_effective_review(matter_id, record.id, actor, db=db)
    return record


def read_effective_review(matter_id, identifier, actor, *, db):
    s.authorize(actor, matter_id, db)
    row = s.latest(REVIEW_KIND, identifier, db)
    if not row or row.matter_id != str(matter_id):
        raise ServiceError('CROSS_MATTER_DENIED', 403)
    try:
        record = d.EffectiveTextReview.model_validate_json(row.payload)
        if record.id != identifier or record.matter_id != matter_id or str(record.actor_id) != row.actor_id:
            raise ValueError('review binding differs')
    except ValueError:
        raise ServiceError('VERSION_CONFLICT', 409) from None
    current = s.latest('effective_review_current', record.bundle_id, db)
    import json
    if (not current or current.matter_id != str(matter_id) or json.loads(current.payload)['review_id'] != str(identifier)
            or not s.approver_valid(record.actor_id, matter_id, db)):
        raise ServiceError('APPROVAL_STALE', 409)
    text, snapshot = _review_context(matter_id, record.bundle_id, actor, db)
    if text.sha256 != record.effective_text_sha256:
        raise ServiceError('APPROVAL_STALE', 409)
    if record.legal.status == 'reviewed' and not _legal_ready(snapshot, matter_id, actor, db):
        raise ServiceError('APPROVAL_STALE', 409)
    return record
