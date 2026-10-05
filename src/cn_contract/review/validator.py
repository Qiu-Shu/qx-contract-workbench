"""Persisted run identity, current original evidence and controlled conclusions."""
import json
from ..domain import ReviewRun,EvidenceBundle,ReviewContext,ValidationResult
from ..security import ServiceError,authorize
from .storage import _row,read_run,read_attempts
from .workflow import current_manifest,controlled_findings


def validate_findings(run,evidence,*,actor,db):
    authorize(actor,run.matter_id,'read',db)
    errors=[]
    try:
        run=ReviewRun.model_validate_json(run.model_dump_json())
        evidence=EvidenceBundle.model_validate_json(evidence.model_dump_json())
        row=_row(run.matter_id,run.id,actor,db)
        saved=read_run(run.matter_id,run.id,actor,db=db,current=True)
        if run!=saved: errors.append('IMMUTABLE_RUN_MISMATCH')
        context=ReviewContext.model_validate_json(row.context_json)
        manifest,anchors,parses,selection,actual=current_manifest(context,actor,db,json.loads(row.config_json),allow_finished=True)
        if run.manifest!=manifest: errors.append('MANIFEST_MISMATCH')
        if evidence.authorities or evidence.receipts: errors.append('UNSUPPORTED_EVIDENCE_REFERENCE')
        referenced={aid for c in run.coverage for aid in c.examined_anchor_ids}
        referenced.update(aid for f in run.findings for aid in (*f.anchor_ids,*f.cross_anchor_ids))
        if not referenced.issubset(anchors): errors.append('ANCHOR_OUTSIDE_CURRENT_ORIGINAL')
        if any(aid not in anchors or value!=anchors[aid] for aid,value in evidence.anchors.items()): errors.append('ANCHOR_EVIDENCE_MISMATCH')
        if not referenced.issubset(evidence.anchors): errors.append('ANCHOR_EVIDENCE_MISSING')
        if run.manifest.model_provider=='assisted_manual':
            from .proposals import validate_saved_run
            validate_saved_run(run,row,actor,db,state=(manifest,anchors,parses,selection,actual))
            return ValidationResult(ok=not errors,errors=tuple(dict.fromkeys(errors)),
                warnings=('离线人工候选工程校验；真实推理未运行，不构成法律核验、批准或正式签发。',),
                checked=('18维及双向finding结构','受保护不可变proposal/run','当前原件/事实/立场/规则/政策/辅助政策',
                    '明确检查的锚点和待核依据，未覆盖维度保留不足'))
        attempts=read_attempts(run.matter_id,run.id,actor,db=db)
        processed=set(json.loads(row.processed_json))
        actual_processed={aid for a in attempts if a['operation']=='review_chunk' and a['valid'] for aid in a['anchor_ids']}
        if processed!=actual_processed: errors.append('PROCESSED_ANCHOR_MISMATCH')
        if any(f.authority_ids or f.rule_ids or f.human_decision is not None or f.replacement_text is not None for f in run.findings):
            errors.append('UNSUPPORTED_CONCLUSION_OR_HUMAN_APPROVAL')
        # Equality with stored run is essential: no arbitrary claim is certified
        # merely because it quotes an actual approved source or exact anchor.
        for c in run.coverage:
            if len(set(c.examined_anchor_ids))!=len(c.examined_anchor_ids) or {str(a) for a in c.examined_anchor_ids}!=processed:
                errors.append('COVERAGE_PROCESSING_MISMATCH')
        if run.status=='completed' and (processed!={str(a) for a in anchors} or not any(a['operation']=='review_cross_clauses' and a['valid'] for a in attempts)):
            errors.append('INCOMPLETE_STRUCTURAL_PROCESSING')
    except (ValueError,ServiceError) as exc:
        errors.append(exc.code if isinstance(exc,ServiceError) else 'MODEL_OUTPUT_INVALID')
    return ValidationResult(ok=not errors,errors=tuple(dict.fromkeys(errors)),warnings=('mock工程校验，不构成律师批准或正式签发。',),
        checked=('18维及双向finding结构','受保护不可变run','当前原件/事实/规则/政策/manifest','实际逐块与跨条款attempt'))
