"""Explicit new-protocol synthetic replies; never wraps arbitrary old output."""
import json


def draft_for(manifest):
    quotes, reviews = [], []
    for index, route in enumerate(manifest.contract_review.routes):
        if not route.methods:
            continue
        source = next(s for s in manifest.sources if s.reference.kind == 'document'
            and s.reference.attachment_id == route.attachment_id)
        raw = source.reference.anchor.quote[:2000]
        key = 'q'+str(index)
        quotes.append(dict(id=key,source_id=source.source_id,start=0,end=len(raw),exact_quote=raw))
        for method in route.methods:
            reviews.append(dict(attachment_id=str(route.attachment_id),method_id=method,summary='虚构材料待律师核对',
                findings=[dict(title='合同范围与责任待核',quote_ids=[key],standard_position='待律师确认的候选立场',
                    gap='应结合附件核对权利义务，不代表法律结论',legal_risk='high',commercial_friction='low',
                    replacement='建议：仅对已约定并核验的交付范围承担合同责任。',fallback='由律师确定备选条款')]))
    return dict(format_version='contract-review-v1',stance='unknown',stance_quote_ids=[],quotes=quotes,reviews=reviews,
        gaps=['审查指引与法律适用未核实'])


def response(basis, value=None):
    return json.dumps(dict(id='synthetic-contract-review',object='chat.completion',created=1,model='deepseek-flash',
        choices=[dict(index=0,finish_reason='stop',message=dict(role='assistant',content=json.dumps(
            value if value is not None else draft_for(basis.manifest),ensure_ascii=False)))],
        usage=dict(prompt_tokens=30,completion_tokens=12,total_tokens=42)),ensure_ascii=False).encode()
