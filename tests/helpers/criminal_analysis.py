"""Independent fictional criminal statements; no real files, accounts or network."""
from uuid import uuid4

from cn_contract import domain as d
from cn_contract.assistant.providers.policy import encoded, sha
from tests.helpers.case_evidence import response


def manifest_for(question='请分析刑事证据并提出辩护策略。\n当前阶段：审查起诉', texts=None):
    texts = texts or ('[证人A]称18时在场。', '[证人B]称19时到场。', '[嫌疑人C]称已退赔，尚待凭证。')
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
    material = d.MainMaterialFile(attachment_id=attachment, name='独立虚构刑事材料.docx',
        original_sha256='a'*64, parse_revision=1, result_sha256='b'*64, reading_status='readable',
        pages=(), parts=('word/document.xml',), unread_parts=(), quality_issues=())
    return d.MainMaterialManifest(workflow='case', stable_task_id=uuid4(), parent_business_run_id=uuid4(),
        question=question, materials=(material,), sources=tuple(sources))


def draft_for(manifest):
    sources = [s for s in manifest.sources if s.reference.kind == 'document' and s.reference.anchor.quote][:3]
    assert len(sources) == 3, 'The synthetic fixture needs three document statements.'
    quotes = [dict(id=f'q{i+1}', source_id=s.source_id, start=0, end=len(s.reference.anchor.quote),
        exact_quote=s.reference.anchor.quote) for i, s in enumerate(sources)]
    strategies = [dict(kind='elements', analysis='核对指控要件与证据联系。', evidence_ids=['e1'],
        unresolved=['法律依据与事实联系待律师核验。']),
        dict(kind='sentencing', analysis='退赔仅作为量刑分析线索。', evidence_ids=['e3'],
            unresolved=['核验退赔凭证及其适用。'])]
    if manifest.criminal_analysis.stage == 'prosecution':
        strategies.append(dict(kind='non_prosecution', analysis='仅作为律师待评估选项，不预测结果。',
            evidence_ids=['e1'], unresolved=['核实程序阶段与完整案卷。']))
    defense = any(source.method_id == 'defense_strategy' for source in manifest.criminal_analysis.method_sources)
    return dict(format_version='criminal-analysis-v1', quotes=quotes,
        evidence=[dict(id='e1', category='conviction', topic='general', claim='材料中的在场说法待核。',
            support=['q1'], opposing=[], unresolved=['核验原始记录。']),
            dict(id='e2', category='authenticity', topic='general', claim='两份材料时间说法需交叉核对。',
                support=['q1'], opposing=['q2'], unresolved=['核查记录形成及上下文，尚未排非。']),
            dict(id='e3', category='sentencing', topic='restitution', claim='退赔说法待核凭证。',
                support=['q3'], opposing=[], unresolved=['核查金额与凭证。'])],
        timeline=[dict(id='t1', event_text='材料记载在场说法。', raw_date='', quote_ids=['q1'],
            conflict_group=None, uncertainty='完整日期待核。')],
        elements=[dict(title='行为与指控的联系', prosecution='控方可能依赖在场说法。',
            defense='在场不当然证明实施行为。', evidence_ids=['e1'], unresolved=['待核其余案卷。'])] if defense else [],
        strategies=strategies if defense else [], gaps=['仅为独立虚构样本，未验证法律推理质量。'])
