"""Independent fictional trademark statements; no real materials or network."""
from uuid import uuid4

from cn_contract import domain as d
from cn_contract.assistant.providers.policy import encoded, sha
from tests.helpers.case_evidence import response as response


KINDS = ('rights_basis', 'sign_similarity', 'goods_services', 'relevant_public',
    'distinctiveness', 'intent', 'actual_confusion', 'market_overlap')


def manifest_for(question='请做商标侵权初筛。', texts=None):
    texts = texts or ('[权利人甲]称在虚构青枝牌杯具上使用文字标识。',
        '[被主张方乙]称其虚构青枝记杯具标识另有设计来源。')
    cid, attachment = uuid4(), uuid4()
    message = d.ProfileMessageRef(kind='message', conversation_id=cid, message_id=uuid4(),
        source_revision=1, start=0, end=len(question), quote=question, quote_sha256=sha(question))
    sources = [d.MainMaterialSource(source_id=sha(encoded(message)), reference=message)]
    for i, text in enumerate(texts):
        anchor = d.Anchor(id=uuid4(), document_version_id=attachment, part_name='word/document.xml',
            element_id=f'p{i}', kind='body_paragraph', quote=text, quote_sha256=sha(text), start=0,
            end=len(text), table=None, row=None, cell=None, page=None, bbox=None)
        ref = d.ProfileDocumentRef(kind='document', conversation_id=cid, attachment_id=attachment,
            original_sha256='a'*64, parse_revision=1, result_sha256='b'*64, anchor=anchor)
        sources.append(d.MainMaterialSource(source_id=sha(encoded(ref)), reference=ref))
    material = d.MainMaterialFile(attachment_id=attachment, name='独立虚构商标材料.docx',
        original_sha256='a'*64, parse_revision=1, result_sha256='b'*64, reading_status='readable',
        pages=(), parts=('word/document.xml',), unread_parts=(), quality_issues=())
    return d.MainMaterialManifest(workflow='case', stable_task_id=uuid4(), parent_business_run_id=uuid4(),
        question=question, materials=(material,), sources=tuple(sources))


def draft_for(manifest):
    sources = [s for s in manifest.sources if s.reference.kind == 'document' and s.reference.anchor.quote][:2]
    assert len(sources) == 2, 'The synthetic fixture needs two document statements.'
    quotes = [dict(id=f'q{i+1}', source_id=s.source_id, start=0, end=len(s.reference.anchor.quote),
        exact_quote=s.reference.anchor.quote) for i, s in enumerate(sources)]
    factors = [dict(kind=kind, holder=[], respondent=[], unresolved=['尚缺完整材料，待律师核验。'])
        for kind in KINDS]
    factors[0]['holder'] = [dict(text='权利人自述使用情况，权属待核。', quote_ids=['q1'])]
    factors[1]['respondent'] = [dict(text='被主张方自述另有设计来源，尚待核验。', quote_ids=['q2'])]
    value = dict(format_version='trademark-triage-v1', quotes=quotes, factors=factors,
        gaps=['仅为独立虚构样本，未核验权利基础和完整使用事实。'])
    if manifest.trademark_triage is not None and manifest.trademark_triage.method_id in ('trademark-triage-v4', 'trademark-triage-v5'):
        value['format_version'] = 'trademark-triage-v2'
        for factor in factors:
            factor['neutral'] = []
    return value
