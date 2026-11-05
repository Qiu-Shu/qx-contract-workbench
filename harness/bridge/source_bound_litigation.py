"""Source-only editable drafts; arithmetic is not a legal or factual finding."""
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
import re

from docx_delivery import _filename, _publish
from litigation_documents import TYPES, _bytes, _document


SECTIONS = ('parties', 'requests', 'facts', 'sections')
MONEY = re.compile(
    r'(?<![A-Za-z0-9.,+\-−负正万亿零〇一二三四五六七八九十百千])'
    r'(?P<number>(?:[1-9][0-9]{0,2}(?:,[0-9]{3})+|0|[1-9][0-9]*)(?:\.[0-9]+)?)'
    r'(?P<unit>亿元|万元|元)(?![0-9.万亿])'
)
LIMITS = ('这是依据所选原文和有限字段形成的可编辑待审文稿；没有自动完成事实认定、'
          '诉讼角色归属、请求权基础或法律适用审查。按句界恢复原文仍须核对完整语境。律师须结合完整材料完善请求和论证。')


def _shape(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= set(value) or set(value) - set(required) - set(optional):
        raise ValueError('字段不符合来源草稿结构；不接受自由改写正文或额外事实字段。')


def _list(value, name, maximum, minimum=0):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ValueError(f'{name}须为{minimum}至{maximum}项的列表。')
    return value


def _reference(cases, case_id, ref, sources, contexts=None):
    _shape(ref, ('path', 'quote', 'sha256', 'chunk'), ('start', 'end'))
    if (not isinstance(ref['path'], str) or not isinstance(ref['quote'], str)
            or not ref['quote'].strip() or len(ref['quote']) > 20000
            or not isinstance(ref['sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', ref['sha256'])
            or type(ref['chunk']) is not int or ref['chunk'] < 0):
        raise ValueError('引用须含真实路径、非空逐字原文、sha256和整数片段号。')
    result = cases.validate_citations(case_id, [ref])
    citation = result['citations'][0]
    path = citation['path']
    if path.lower().startswith('drafts/'):
        raise ValueError('工作草稿不能作为原始来源。')
    current = sources.get(path)
    if (result['warnings'] or citation['status'] != 'matched' or current is None
            or current['changed'] or current['missing'] or current['sha256'] != ref['sha256']
            or current['link_id'] != citation['link_id']):
        raise ValueError('引文不匹配、失效或不是本案当前关联版本，未生成草稿。')
    # read_material.start is a row offset; chunk is an ordinal and may be sparse.
    with cases.db() as db:
        offset = db.execute('SELECT COUNT(*) FROM chunks WHERE path=? AND ordinal<?',
                            (path, ref['chunk'])).fetchone()[0]
    read = cases.read_material(case_id, path, start=offset, limit=1)
    chunks = read.get('chunks', [])
    if (read.get('sha256') != ref['sha256'] or len(chunks) != 1
            or chunks[0]['ordinal'] != ref['chunk']):
        raise ValueError('不能回读相同来源片段，未生成草稿。')
    source_text = chunks[0]['text']
    matches = [m.start() for m in re.finditer('(?=' + re.escape(ref['quote']) + ')', source_text)]
    if 'start' in ref or 'end' in ref:
        start, end = ref.get('start'), ref.get('end')
        if type(start) is not int or type(end) is not int or start not in matches or end != start + len(ref['quote']):
            raise ValueError('引用位置不匹配。')
    else:
        if len(matches) != 1:
            raise ValueError('原句位置有歧义，请提供匹配的start/end或扩大上下文。')
        start = matches[0]
        end = start + len(ref['quote'])
    if contexts is not None:
        contexts[(path, ref['sha256'], ref['chunk'])] = {
            'path': path, 'sha256': ref['sha256'], 'chunk': ref['chunk'], 'text': source_text}
    return {**citation, 'start': start, 'end': end}, source_text


def _money(cases, case_id, operand, sources, contexts=None):
    _shape(operand, ('citation', 'amount'))
    amount = operand['amount']
    if not isinstance(amount, str) or len(amount) > 40 or MONEY.fullmatch(amount) is None:
        raise ValueError('amount须为原文完整金额，使用阿拉伯数字及元/万元/亿元。')
    ref, context = _reference(cases, case_id, operand['citation'], sources, contexts)
    matches = [m for m in MONEY.finditer(context)
               if ref['start'] <= m.start() and m.end() <= ref['end'] and m.group() == amount
               and not re.search(r'(?:负|正|[+\-−]|[0-9][eE])\s*$', context[:m.start()])]
    if len(matches) != 1:
        raise ValueError('金额不是原文完整数值或出现多次；请缩小到有明确上下文的唯一金额。')
    match = matches[0]
    with localcontext() as ctx:
        ctx.prec = 60
        value = Decimal(match['number'].replace(',', '')) * {'元': 1, '万元': 10000, '亿元': 100000000}[match['unit']]
        if value != value.quantize(Decimal('0.01')) or value > Decimal('1e20'):
            raise ValueError('金额精度超过分或数值过大，请人工核对。')
    return value, {'amount': amount, 'value_yuan': _number(value), 'citation': ref,
                   'amount_start': match.start(), 'amount_end': match.end()}


def _number(value):
    return format(value, 'f').rstrip('0').rstrip('.') if '.' in format(value, 'f') else format(value, 'f')


def _contextual_quote(source, start, end):
    """Restore sentence boundaries for display only; not semantic certification."""
    boundaries = '。！？\r\n'
    left = max(source.rfind(mark, 0, start) for mark in boundaries) + 1
    right = end
    if source[end - 1] not in boundaries:
        stop = re.search('[。！？\r\n]', source[end:])
        right = len(source) if stop is None else end + stop.start() + (stop.group() not in '\r\n')
    return source[left:right], {'start': left, 'end': right}


def _role_labels(kind):
    return ({'client': '拟委托人', 'issuer': '拟发函人', 'recipient': '拟收函人'} if kind == 'lawyer_letter'
            else {'applicant': '拟申请人', 'respondent': '拟被申请人'} if kind == 'labor_arbitration'
            else {'plaintiff': '拟原告', 'defendant': '拟被告'})


def _prepare_brief(cases, case_id, kind, brief, arithmetic, sources, used, contexts):
    if brief is None or brief == {}:
        return None
    _shape(brief, (), ('parties', 'claim_kind', 'claim_amount', 'calculation_index'))
    claim = brief.get('claim_kind', 'undetermined')
    if claim not in ('payment', 'return', 'undetermined'):
        raise ValueError('claim_kind只支持payment/return/undetermined，不推断借款等关系。')
    roles = _role_labels(kind)
    parties, seen = [], set()
    for party in _list(brief.get('parties', []), 'parties', len(roles)):
        _shape(party, ('role', 'name', 'citation'))
        role, name = party['role'], party['name']
        if not isinstance(role, str) or role not in roles or role in seen:
            raise ValueError('角色不适用于该文书或重复。')
        if (not isinstance(name, str) or not 1 <= len(name) <= 200 or name != name.strip()
                or re.search(r'[\x00-\x1f\r\n]', name)):
            raise ValueError('主体名称须为原文连续名称，不接受另行扩写。')
        ref, _ = _reference(cases, case_id, party['citation'], sources, contexts)
        if name not in ref['quote']:
            raise ValueError('主体名称不在匹配原文中，不能补写公司类型或姓名。')
        used[ref['path']] = sources[ref['path']]
        parties.append({'role': role, 'label': roles[role], 'name': name, 'citation': ref})
        seen.add(role)
    if 'claim_amount' in brief and 'calculation_index' in brief:
        raise ValueError('claim_amount与calculation_index只选一个。')
    amount, binding = None, None
    if 'claim_amount' in brief:
        try:
            _shape(brief['claim_amount'], ('citation', 'amount'))
        except ValueError as error:
            raise ValueError('brief.claim_amount仅接受citation和原文amount；'
                             '引用程序差额请删除claim_amount，改用brief.calculation_index指向本次算式，'
                             '不能嵌入claim_amount或传计算结果。') from error
        value, binding = _money(cases, case_id, brief['claim_amount'], sources, contexts)
        amount = _number(value)
        used[binding['citation']['path']] = sources[binding['citation']['path']]
    elif 'calculation_index' in brief:
        index = brief['calculation_index']
        if type(index) is not int or not 0 <= index < len(arithmetic):
            raise ValueError('calculation_index必须指向本次程序算式。')
        amount, binding = arithmetic[index]['result_yuan'], {'calculation_index': index}
    if amount is not None and Decimal(amount) <= 0:
        raise ValueError('请求暂列金额须大于零；零或负差额只保留算术核对。')
    request = None
    if kind in ('civil_complaint', 'labor_arbitration') and amount is not None:
        actor, recipient, adjudicate = ('被申请人', '申请人', '裁决') if kind == 'labor_arbitration' else ('被告', '原告', '判令')
        verb = {'payment': '支付', 'return': '返还', 'undetermined': '支付或返还'}[claim]
        request = (f'如经核实{actor}负有相应{verb}义务且履行条件已经成就，拟请求{adjudicate}{actor}向{recipient}{verb}{amount}元。'
                   '本金额仅作待审请求暂列，须核对已付、已返还及依法可抵扣款项并相应调整；'
                   '款项性质、请求方向、义务依据及到期情况均按完整材料核实，不由该数额认定。')
    elif kind == 'civil_defense':
        request = ('拟请求：在核对原告诉讼请求及其依据后，请依法审查并对缺乏事实或法律依据的部分不予支持。'
                   '具体答辩范围待结合诉状及材料确定；本稿不据收款数额承认债务，'
                   '也不以收款与对方主张的差额直接确定应驳回范围。')
    elif kind == 'lawyer_letter':
        request = ('拟请收函方核对下列材料所述事项，并就金额构成、依据及差异提出反馈。'
                   '如核对确认存在应履行事项，请就拟处理安排反馈；回复期限、核对方式和时间待当事人确认。'
                   '这是待审发函方案，不表明委托人已同意核账、已安排人员或承诺提交资料；委托及发函权限待核。')
    elif kind == 'representation':
        request = ('拟主张：请结合下列原文及核实后的事实审查争议。材料中的标准、比例或责任方案，'
                   '仅在对应约定或法律依据成立且适用于本案时，作为拟请求采用的依据；'
                   '成立条件未明的部分保留待核，不将原文记载直接提升为已确认事实。'
                   '具体责任及范围依完整材料另行确定，代理权限另核。')
    if request and amount is not None and kind not in ('civil_complaint', 'labor_arbitration'):
        request += f'选定原文金额或程序差额为{amount}元，仅供争议事项核对，不表示任何一方已认欠或已确认责任。'
    return {'parties': parties, 'role_labels': roles, 'claim_kind': claim,
            'amount_yuan': amount, 'amount_binding': binding, 'request_text': request,
            'role_assignment_verified': False}


def build_source_bound_litigation(cases, case_id, document_type, filename, excerpts, calculations=None, brief=None):
    """Build source-only Word and audit; no caller-authored facts or legal conclusions.

    excerpts: [{section: parties|requests|facts|sections, citation:{path,quote,sha256,chunk[,start,end]}}].
    calculations: [{minuend:{citation,amount}, subtrahends:[{citation,amount}]}].
    amount is an exact monetary token including 元/万元/亿元, not a computed result.
    brief optionally selects source-bound party names and a finite conditional request.
    """
    _filename(filename)
    if document_type not in TYPES:
        raise ValueError('不支持的文书类型。')
    _list(excerpts, 'excerpts', 100, 1)
    calculations = [] if calculations is None else _list(calculations, 'calculations', 20)
    try:
        if len(json.dumps([excerpts, calculations, brief], ensure_ascii=False)) > 250000:
            raise ValueError('资料超过250000字，请拆分。')
    except (TypeError, OverflowError) as error:
        raise ValueError('资料须使用JSON基础类型。') from error
    snapshot = cases.export_snapshot(case_id)
    sources = {x['path']: x for x in snapshot['materials']}
    rows, arithmetic, used, contexts = [], [], {}, {}
    for item in excerpts:
        _shape(item, ('section', 'citation'))
        if item['section'] not in SECTIONS:
            raise ValueError('section须为parties/requests/facts/sections。')
        ref, source_text = _reference(cases, case_id, item['citation'], sources, contexts)
        used[ref['path']] = sources[ref['path']]
        contextual_quote, contextual_span = _contextual_quote(source_text, ref['start'], ref['end'])
        rows.append({'section': item['section'], 'citation': ref,
                     'contextual_quote': contextual_quote, 'contextual_span': contextual_span})
    for item in calculations:
        _shape(item, ('minuend', 'subtrahends'))
        _list(item['subtrahends'], 'subtrahends', 20, 1)
        total, first = _money(cases, case_id, item['minuend'], sources, contexts)
        terms, deducted = [], set()
        with localcontext() as ctx:
            ctx.prec = 60
            for operand in item['subtrahends']:
                value, term = _money(cases, case_id, operand, sources, contexts)
                binding = (term['citation']['path'], term['citation']['sha256'],
                           term['citation']['chunk'], term['amount_start'], term['amount_end'])
                if binding in deducted:
                    raise ValueError('同一来源金额不能在一项算式中重复扣减。')
                deducted.add(binding)
                total -= value
                terms.append(term)
        for term in [first, *terms]:
            path = term['citation']['path']; used[path] = sources[path]
        arithmetic.append({'minuend': first, 'subtrahends': terms, 'result_yuan': _number(total)})

    prepared_brief = _prepare_brief(cases, case_id, document_type, brief, arithmetic, sources, used, contexts)
    conditional = bool(prepared_brief and prepared_brief['request_text'])
    selected_sections = {key: sum(r['section'] == key for r in rows) for key in SECTIONS}
    if document_type == 'representation':
        missing = ([] if conditional else ['brief（形成待审条件主张）'])
        missing += [key for key in ('requests', 'facts') if not selected_sections[key]]
        if missing:
            raise ValueError('代理意见缺少：' + '、'.join(missing) +
                             '。请将待保留主张原句放入requests，依据或相反材料原句放入facts，'
                             '并传入有限字段brief；未生成文稿。')

    title, requests_label, facts_label = TYPES[document_type]
    draft = _document(title + ('（条件草稿）' if conditional else '（来源草稿）'))
    audit = _document(title + ' — 内部来源核对稿（勿对外发送）')
    draft.add_paragraph(LIMITS)
    audit.add_paragraph(f'案件ID：{case_id}')
    if prepared_brief:
        audit.add_paragraph(json.dumps(prepared_brief, ensure_ascii=False, indent=2))
    labels = {'parties': '当事人及角色', 'requests': requests_label,
              'facts': facts_label, 'sections': '其他材料所载事项'}
    for key, label in labels.items():
        draft.add_heading(label, 1)
        if key == 'parties' and prepared_brief:
            by_role = {p['role']: p for p in prepared_brief['parties']}
            for role, role_label in prepared_brief['role_labels'].items():
                name = by_role[role]['name'] if role in by_role else '【名称未填】'
                draft.add_paragraph(f'{role_label}（身份与角色对应待核）：{name}')
        selected = [r for r in rows if r['section'] == key]
        if not selected:
            draft.add_paragraph('【待补：未选入相关来源；不推断现实中有无该事项。】')
        for row in selected:
            ref = row['citation']
            draft.add_paragraph(f'材料《{ref["path"]}》记载如下（按句界恢复的原文，陈述人及真实性依原材料另核）：')
            draft.add_paragraph(row['contextual_quote'])
            audit.add_paragraph(json.dumps(row, ensure_ascii=False, indent=2))
        if key == 'requests':
            draft.add_paragraph(prepared_brief['request_text'] if conditional else
                                '拟请求事项：【待承办人根据材料确定具体请求、对象和成立条件；引述材料不等于采用其中主张。】')
    if arithmetic:
        draft.add_heading('金额核对（仅算术）', 1)
        for row in arithmetic:
            expression = ' − '.join([row['minuend']['value_yuan'] + '元',
                                     *(x['value_yuan'] + '元' for x in row['subtrahends'])])
            draft.add_paragraph(expression + ' = ' + row['result_yuan'] + '元。')
        draft.add_paragraph('上述差额仅按选定原文数值计算；对应关系、是否应扣、是否到期及能否作为请求金额均待核实。')
        audit.add_paragraph(json.dumps(arithmetic, ensure_ascii=False, indent=2))
    draft.add_heading('独立风险提示（待审）', 1)
    draft.add_paragraph('引用和计算不证明请求成立；来源完整性、责任条件、程序期限及实际可实现范围须复核。'
                        '本提示不表示客户已接受风险说明或已经认可任何方案。')
    metadata = ['委托授权及客户态度', '署名', '拟署日期']
    if document_type != 'lawyer_letter':
        metadata = ['受理机关', '案号', *metadata]
    for label in metadata:
        draft.add_paragraph(label + '：【本稿未填，依明确来源核实后填写。】')
    draft.add_paragraph('本次仅生成待核草稿；不执行签署、发函或提交。案件现实程序状态以原始资料为准。')
    audit.add_paragraph(json.dumps(list(used.values()), ensure_ascii=False, indent=2))
    audit.add_heading('引用所在完整片段（内部上下文，不等于正文采用）', 1)
    for context in contexts.values():
        audit.add_paragraph(f'来源：{context["path"]}；sha256：{context["sha256"]}；片段：{context["chunk"]}')
        audit.add_paragraph(context['text'])
    audit.add_paragraph(LIMITS)

    missing_sections = [key for key in SECTIONS if not selected_sections[key]
                        and not (key == 'requests' and conditional)
                        and not (key == 'parties' and prepared_brief and prepared_brief['parties'])]
    role_labels = _role_labels(document_type)
    filled_roles = {p['role'] for p in prepared_brief['parties']} if prepared_brief else set()
    missing_roles = [role for role in role_labels if role not in filled_roles]
    selections = '；'.join(f'{labels[key]}{count}处' for key, count in selected_sections.items() if count)
    user_summary = ('已保存待审条件文稿。' if conditional else '已保存部分完成的来源整理稿。')
    user_summary += '正文选入原文：' + selections + '。'
    user_summary += '已形成待审条件请求。' if conditional else '未形成条件请求。'
    user_summary += f'程序金额核对{len(arithmetic)}项。'
    if missing_sections:
        user_summary += '本稿待补章节：' + '、'.join(labels[key] for key in missing_sections) + '。'
    if missing_roles:
        user_summary += ('本稿未填写角色：' + '、'.join(role_labels[role] for role in missing_roles) +
                         '；不表示原材料没有该信息或授权不存在，请核对已给拟角色后补入。')
    user_summary += (f'内部稿保留{len(contexts)}个引用所在完整片段，仅供核对上下文；'
                     '未选入的观点不代表已写入正文。事实、角色、请求及法律适用仍须律师审核，文稿不可直接提交或发出。')

    def check_sources():
        now = {x['path']: x for x in cases.materials(case_id)}
        for path, original in used.items():
            current = now.get(path)
            if (not current or current['changed'] or current['missing']
                    or current['link_id'] != original['link_id'] or current['sha256'] != original['sha256']):
                raise ValueError('生成期间来源变动，未保留对外草稿；请回读后重试。')

    body_bytes, audit_bytes = _bytes(draft), _bytes(audit)
    check_sources()
    internal = _publish(cases.store, Path(filename).stem + '-内部核对.docx', audit_bytes)
    check_sources()
    output = _publish(cases.store, filename, body_bytes)
    try:
        check_sources()
    except Exception:
        # Only remove our just-created outward file, never a pre-existing draft.
        target = cases.store.safe(output['path'])
        if hashlib.sha256(target.read_bytes()).hexdigest() == output['sha256']:
            target.unlink()
        raise
    return {**output, 'internal_path': internal['path'], 'internal_sha256': internal['sha256'],
            'body_text': '\n'.join(p.text for p in draft.paragraphs),
            'internal_text': '\n'.join(p.text for p in audit.paragraphs),
            'case_id': case_id, 'document_type': document_type,
            'status': 'conditional_draft' if conditional else 'source_bound_draft',
            'completion_status': 'conditional_draft' if conditional else 'partial',
            'brief': prepared_brief,
            'user_summary': user_summary, 'selected_sections': selected_sections,
            'missing_sections': missing_sections, 'missing_roles': missing_roles,
            'source_contexts': list(contexts.values()),
            'pending_work': ['承办人核实角色、选定请求及其适用条件。',
                             '依据完整材料补全事实论证、法律依据与程序要求。'],
            'excerpts': rows, 'calculations': arithmetic, 'sources': list(used.values()),
            'ready_to_submit': False, 'legal_verified': False, 'limits': LIMITS}
