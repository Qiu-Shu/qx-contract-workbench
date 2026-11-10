"""Case-scoped editable litigation drafts with a separate internal source audit."""
from io import BytesIO
import json
from pathlib import Path
import re

from docx import Document
from docx.shared import Pt
from docx_delivery import _filename, _publish, _string


TYPES = {
    'civil_complaint': ('民事起诉状', '诉讼请求', '事实与理由'),
    'civil_defense': ('民事答辩状', '答辩请求', '答辩事实与理由'),
    'representation': ('代理意见', '代理主张', '争议焦点与论证'),
    'evidence_list': ('证据目录', '证明目的', '证据名称、来源、页码与原件情况'),
    'cross_examination': ('质证意见', '质证主张', '逐项真实性、合法性、关联性及证明力意见'),
    'labor_arbitration': ('劳动仲裁申请书', '仲裁请求', '事实与理由'),
    'lawyer_letter': ('律师函', '拟提出的要求', '事实与理由'),
}
NOTICE = '待核草稿，不可直接提交或发出。引文匹配仅核对文字，不证明事实真实、身份归属、法律适用或金额正确。'
REPRESENTATION_AUTHORITY = re.compile(
    r'(?:本所|本律师|本代理人|诉讼代理人|代理律师|承办律师).{0,20}'
    r'(?:受托|受.{0,20}委托|(?:已获|获得).{0,10}授权)'
    r'|代理人.{0,20}(?:受托|受.{0,20}委托).{0,20}(?:本案|诉讼|出庭)'
    r'|(?:授权委托书|授权材料|授权文件|代理权限|代理手续|诉讼授权).{0,24}已.{0,12}(?:提交|递交|备案)'
    r'|已.{0,12}(?:提交|递交|备案).{0,24}(?:授权委托书|授权材料|授权文件|代理手续|诉讼授权)'
)
LETTER_AUTHORITY = re.compile(REPRESENTATION_AUTHORITY.pattern +
    r'|(?:兹受|现受|受).{1,40}委托.{0,20}(?:发函|函告|致函)'
    r'|(?:已获|获得|经).{0,20}授权.{0,12}(?:发函|函告|致函)')


def _text(value, name):
    if not isinstance(value, str) or len(value) > 50000:
        raise ValueError(f'{name}须为不超过50000字的文字。')
    _string(value, name)
    return value


def _document(title):
    doc = Document()
    doc.styles['Normal'].font.name = 'Microsoft YaHei'
    doc.styles['Normal'].font.size = Pt(11)
    doc.add_heading(title, 0)
    doc.add_paragraph(NOTICE)
    return doc


def _bytes(doc):
    output = BytesIO()
    doc.save(output)
    return output.getvalue()


def generate_litigation_document(cases, case_id, document_type, filename, data):
    """Generate two new DOCX files; never sends/submits or updates case facts.

    data: optional title, parties[{role,text,citations}], requests/facts[{text,citations}],
    sections[{heading,text,citations}], authority/case_number/signatory/date strings,
    mandate{client,issuer,recipient,authorized,citations} for lawyer letters.
    Missing fields remain visible. All references must belong to this case.
    """
    _filename(filename)
    if document_type not in TYPES:
        raise ValueError('不支持的文书类型。')
    allowed = {'title', 'parties', 'requests', 'facts', 'sections', 'authority',
               'case_number', 'signatory', 'date', 'mandate'}
    if not isinstance(data, dict) or set(data) - allowed:
        raise ValueError('data含不支持的字段；正文请放入facts或sections，不静默丢弃。')
    if 'mandate' in data and document_type != 'lawyer_letter':
        raise ValueError('mandate仅适用于lawyer_letter；其他文书请将委托情况写入带来源的章节。')
    if len(json.dumps(data, ensure_ascii=False)) > 250000:
        raise ValueError('文书数据超过250000字，请拆分。')
    snapshot = cases.export_snapshot(case_id)
    title, requests_label, facts_label = TYPES[document_type]
    pending = ['律师复核事实、当事人角色、主张与金额计算；未知事项保持待核，不转写为否定事实。',
               '受理机关、管辖、时效及期限、要素式表格和电子提交格式须按具体案件另核；签名盖章须本人或有权主体完成。']
    checks, paths, body_paragraphs = [], set(), []
    withheld = []
    from draft_review import DraftReview
    review = DraftReview(cases,case_id)

    def outward_text(value, label, refs=()):
        value=review.text(value,label,refs)
        # Metadata reaches the same outward draft as body text, so has the same boundary.
        if document_type in ('lawyer_letter','representation'):
            # Narrow lexical safeguard, not an authorization audit. Keep ordinary
            # mandate-contract facts, including adjacent sentences, in the draft.
            sentences = re.split(r'(?<=[。！？；\n])', value)
            for index, sentence in enumerate(sentences):
                pattern=LETTER_AUTHORITY if document_type=='lawyer_letter' else REPRESENTATION_AUTHORITY
                if pattern.search(sentence):
                    withheld.append((label, sentence))
                    pending.append(f'{label}涉及委托或代理授权声明；本工具未审核权限，原稿仅供内部核对。')
                    sentences[index] = '【委托或代理授权声明待核；本工具未审核权限，原稿已保留于内部核对稿。】'
            return ''.join(sentences)
        return value

    draft = _document(outward_text(_text(data.get('title', title), 'title'), '标题'))
    audit = _document(title + ' — 内部来源核对稿（勿对外发送）')
    audit.add_paragraph(f'案件ID：{case_id}；案件题名：{snapshot["case"]["title"]}')
    if document_type == 'representation':
        authority_notice = '【本工具未审核代理权；受托、代理权限及授权材料提交情况均待核，不因引文匹配而确认。】'
        draft.add_paragraph(authority_notice)
        audit.add_paragraph(authority_notice)
        pending.append(authority_notice)

    def verify(item, label):
        if not isinstance(item, dict) or set(item) - {'role', 'heading', 'text', 'citations'}:
            raise ValueError(f'{label}须使用text与citations，另可填写role或heading。')
        text = _text(item.get('text', ''), label)
        refs = item.get('citations', [])
        if not isinstance(refs, list) or len(refs) > 100:
            raise ValueError('citations须为不超过100项的列表。')
        prepared = []
        for ref in refs:
            citation = dict(ref) if isinstance(ref, dict) else ref
            if isinstance(citation, dict) and citation.get('status') in ('unmatched', 'ambiguous', 'unverified'):
                citation.update(provided_status=citation['status'], start=None, end=None)
            prepared.append(citation)
        result = cases.validate_citations(case_id, prepared)
        warnings = list(result['warnings'])
        for ref in result['citations']:
            if ref.get('path'):
                paths.add(ref['path'])
            if (str(ref.get('path', '')).replace('\\', '/').lower().startswith('drafts/')
                    or ref.get('source_kind') in ('model_draft', 'inference', 'draft')):
                ref['status'] = 'unverified'
                warnings.append('模型或工作草稿不能作为来源证据；须回到实际原始材料。')
        if not text.strip(): warnings.append('正文缺失。')
        if not refs: warnings.append('未绑定本案原始材料，陈述来源及事实待核。')
        status = 'matched' if result['citations'] and not warnings else 'unverified'
        row = {'label': label, 'text': text, 'status': status, 'citations': result['citations'], 'warnings': warnings}
        checks.append(row)
        pending.extend(f'{label}：{w}' for w in warnings)
        return row

    if document_type == 'lawyer_letter':
        mandate = data.get('mandate', {})
        if not isinstance(mandate, dict) or set(mandate) - {'client', 'issuer', 'recipient', 'authorized', 'citations'}:
            raise ValueError('mandate须分别填写client、issuer、recipient、authorized与citations。')
        if type(mandate.get('authorized', False)) is not bool:
            raise ValueError('authorized须为布尔值。')
        audit.add_heading('收到的委托登记（未经授权审核）', 1)
        audit.add_paragraph(json.dumps(mandate, ensure_ascii=False, indent=2))
        draft.add_heading('委托与发函主体核对', 1)
        for key, label in [('client', '委托人'), ('issuer', '拟发函主体'), ('recipient', '收函主体')]:
            value = _text(mandate.get(key, ''), key)
            draft.add_paragraph(label + '：' + (outward_text(value, label) or '【待核】'))
            if not value: pending.append(label + '待核。')
        if mandate.get('citations'):
            verify({'text': '委托授权材料仅作文字核对，授权范围仍须律师审核。',
                    'citations': mandate['citations']}, '委托授权')
        # Caller flags and matching words are not an authorization review.
        draft.add_paragraph('【委托未核实；本工具未授权发函。不据此宣称律所或律师已受托。】')
        pending.append('委托未核实：核对委托主体、发函主体、收函主体和授权范围；authorized输入不构成授权审核。')

    for key, heading in [('parties', '当事人及诉讼角色'), ('requests', requests_label), ('facts', facts_label), ('sections', '其他章节')]:
        items = data.get(key, [])
        if not isinstance(items, list) or len(items) > 200:
            raise ValueError(f'{key}须为不超过200项的列表。')
        if not items and key == 'sections': continue
        draft.add_heading(heading, 1)
        if not items:
            draft.add_paragraph(f'【待补：{heading}】')
            pending.append(f'{heading}缺失。')
        for index, item in enumerate(items, 1):
            row = verify(item, f'{heading}{index}')
            prefix = outward_text(_text(item.get('role' if key == 'parties' else 'heading', ''), '章节或角色'),
                                  row['label'] + '章节或角色')
            text = outward_text(row['text'], row['label'],item.get('citations',[])) or '【待补正文】'
            paragraph = draft.add_paragraph((prefix + '：' if prefix else '') + text)
            body_paragraphs.append((row, paragraph))
            if row['status'] != 'matched': draft.add_paragraph('【待核：本段来源或引文尚未核对通过。】')

    for key, label in [('authority', '受理机关' if document_type != 'lawyer_letter' else '送达方式'),
                       ('case_number', '案号'), ('signatory', '署名主体'), ('date', '拟署日期')]:
        value = _text(data.get(key, ''), key)
        draft.add_paragraph(label + '：' + (outward_text(value, label) or '【待核，未填写】'))
        if not value: pending.append(label + '待核；不自动编造。')
    draft.add_paragraph('签名／盖章：【未签署，不生成或模拟印章、签名】')
    sources = [row for row in cases.materials(case_id) if row['path'] in paths]
    for source in sources:
        if source['changed'] or source['missing']:
            pending.append('来源版本变化或缺失：' + source['path'])
            for row in checks:
                for citation in row['citations']:
                    if citation.get('path') == source['path']:
                        citation['status'] = 'unverified'
                        if row['status'] == 'matched':
                            for item, paragraph in body_paragraphs:
                                if item is row:
                                    paragraph.insert_paragraph_before('【待核：本段来源或引文尚未核对通过；生成期间来源版本变化。】')
                        row['status'] = 'unverified'
                        reason = '生成期间来源版本变化或缺失，请回读原件后重新生成。'
                        if reason not in row['warnings']: row['warnings'].append(reason)
                        pending.append(row['label'] + '：' + reason)
    for row in checks:
        audit.add_heading(row['label'], 2)
        audit.add_paragraph(row['text'] or '【待补正文】')
        audit.add_paragraph(json.dumps({'status': row['status'], 'citations': row['citations'],
                                       'warnings': row['warnings']}, ensure_ascii=False, indent=2))
    if withheld:
        audit.add_heading('未进入外观正文的委托表述（待核原稿）', 1)
        for label, text in withheld:
            audit.add_paragraph(label + '：' + text)
    if review.changes:
        audit.add_heading('事实状态修订（原稿未采用）',1)
        for change in review.changes:
            audit.add_paragraph(json.dumps(change,ensure_ascii=False))
    pending = list(dict.fromkeys(pending))
    audit.add_heading('待核事项', 1)
    for item in pending: audit.add_paragraph(item)
    audit.add_heading('本次引用来源及版本', 1)
    audit.add_paragraph(json.dumps(sources, ensure_ascii=False, indent=2))
    # Publish the audit first; a later output error leaves only an explicitly internal file.
    internal = _publish(cases.store, Path(filename).stem + '-内部核对.docx', _bytes(audit))
    output = _publish(cases.store, filename, _bytes(draft))
    body_text='\n'.join(p.text for p in draft.paragraphs)
    summary='已生成'+title+'待核正文及独立内部核对稿；未提交或发出，未认证事实或法律意见。'
    if review.changes:summary+=f'已修订{len(review.changes)}处事实状态表述，原稿和理由见内部核对稿。'
    summary+=('\n\n已保存正文：\n'+body_text if len(body_text)<=100000 else
              '\n正文超过聊天展示上限，请打开本次生成的Word查看完整内容；未截断文件。')
    return {**output, 'case_id': case_id, 'document_type': document_type, 'status': 'draft',
            'body_text':body_text,'user_summary':summary,
            'internal_path': internal['path'], 'internal_sha256': internal['sha256'],
            'citation_checks': checks, 'sources': sources, 'pending_checks': pending,
            'review_changes':review.changes,
            'authorization_status': 'unverified' if document_type in ('lawyer_letter', 'representation') else 'not_applicable',
            'ready_to_submit': False, 'legal_verified': False, 'notice': NOTICE}
