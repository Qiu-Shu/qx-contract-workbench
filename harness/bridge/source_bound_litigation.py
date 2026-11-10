"""Source-only editable drafts; arithmetic is not a legal or factual finding."""
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
import re

from docx_delivery import _filename, _publish
from litigation_documents import TYPES as BASE_TYPES, _bytes, _document

TYPES = {**BASE_TYPES,
         'procedure_review': ('程序核查底稿', '材料所载主张（非拟提出请求）', '程序事实及限制材料'),
         'civil_appeal': ('民事上诉状', '上诉请求（原文拟议，范围待核）', '上诉事实与理由'),
         'labor_award_set_aside': ('撤销劳动仲裁裁决申请书', '撤销申请事项（原文拟议，范围待核）', '申请理由及证据')}
REMEDY_DOCUMENTS = {'civil_appeal': ('civil_appeal', 'appeal'),
                    'labor_award_set_aside': ('labor_award_remedy', 'set_aside')}


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
            'path': path, 'sha256': ref['sha256'], 'chunk': ref['chunk'], 'text': source_text,
            'location':chunks[0].get('location',''),
            'parse_warnings':read.get('warnings',[]),
            'failed_pages':read.get('failed_pages',[])}
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
    if kind == 'procedure_review':
        return {}
    return ({'client': '拟委托人', 'issuer': '拟发函人', 'recipient': '拟收函人'} if kind == 'lawyer_letter'
            else {'appellant': '拟上诉人', 'appellee': '拟被上诉人'} if kind == 'civil_appeal'
            else {'applicant': '拟申请人', 'respondent': '拟被申请人'} if kind in ('labor_arbitration', 'labor_award_set_aside')
            else {'plaintiff': '拟原告', 'defendant': '拟被告'})


def _prepare_brief(cases, case_id, kind, brief, arithmetic, sources, used, contexts):
    if brief is None or brief == {}:
        return None
    _shape(brief, (), ('parties', 'claim_kind', 'claim_amount', 'calculation_index'))
    claim = brief.get('claim_kind', 'undetermined')
    if kind in REMEDY_DOCUMENTS and (claim != 'undetermined' or 'claim_amount' in brief or 'calculation_index' in brief):
        raise ValueError('救济文书须使用requests原文列明具体请求，不能套用给付金额请求。')
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


def build_source_bound_litigation(cases, case_id, document_type, filename, excerpts, calculations=None, brief=None, issues=None, claims=None, legal_review=None):
    """Build source-only Word and audit; no caller-authored facts or legal conclusions.

    excerpts: [{section: parties|requests|facts|sections, citation:{path,quote,sha256,chunk[,start,end]}}].
    calculations: [{minuend:{citation,amount}, subtrahends:[{citation,amount}]}].
    amount is an exact monetary token including 元/万元/亿元, not a computed result.
    brief optionally selects source-bound party names and a finite conditional request.
    """
    _filename(filename)
    if document_type not in TYPES:
        raise ValueError('不支持的文书类型。')
    if document_type == 'procedure_review' and brief:
        raise ValueError('纯程序核查不接受brief拟请求或角色分配；请保留来源并使用legal_review.procedure。')
    _list(excerpts, 'excerpts', 100, 1)
    calculations = [] if calculations is None else _list(calculations, 'calculations', 20)
    issues = [] if issues is None else _list(issues, 'issues', 20)
    claims = [] if claims is None else _list(claims, 'claims', 20)
    try:
        if len(json.dumps([excerpts, calculations, brief, issues, claims, legal_review], ensure_ascii=False)) > 250000:
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
    prepared_issues = []
    for issue in issues:
        _shape(issue, ('claim',), ('supporting', 'opposing', 'legal_basis'))
        prepared = {}
        for key in ('claim', 'supporting', 'opposing', 'legal_basis'):
            refs = [issue['claim']] if key == 'claim' else _list(issue.get(key, []), key, 10)
            prepared[key] = []
            for raw in refs:
                ref, source_text = _reference(cases, case_id, raw, sources, contexts)
                quote, span = _contextual_quote(source_text, ref['start'], ref['end'])
                prepared[key].append({'citation': ref, 'contextual_quote': quote, 'contextual_span': span})
                used[ref['path']] = sources[ref['path']]
        prepared['missing_groups'] = [k for k in ('supporting','opposing','legal_basis') if not prepared[k]]
        prepared_issues.append(prepared)
    prepared_claims=[]
    for item in claims:
        _shape(item,('request','issue_indices'))
        indices=_list(item['issue_indices'],'issue_indices',20)
        if any(type(i) is not int or not 0<=i<len(prepared_issues) for i in indices) or len(set(indices))!=len(indices):
            raise ValueError('请求须关联本次issues的有效且不重复的0起始索引。')
        ref,source_text=_reference(cases,case_id,item['request'],sources,contexts)
        quote,span=_contextual_quote(source_text,ref['start'],ref['end'])
        used[ref['path']]=sources[ref['path']]
        prepared_claims.append({'request':ref,'quote':quote,'span':span,'issue_indices':indices,
                                'legal_verified':False})
    prepared_review,review_text=None,''
    if legal_review is not None:
        from litigation_review import prepare_legal_review
        def bind_review(raw,include_context=False):
            ref,text=_reference(cases,case_id,raw,sources,contexts)
            quote,span=_contextual_quote(text,ref['start'],ref['end'])
            used[ref['path']]=sources[ref['path']]
            return {'citation':ref,'quote':quote,'span':span,**({'context':text} if include_context else {})}
        prepared_review,review_text=prepare_legal_review(legal_review,prepared_claims,bind_review)
    conditional = bool(prepared_brief and prepared_brief['request_text'])
    selected_sections = {key: sum(r['section'] == key for r in rows) for key in SECTIONS}
    if document_type == 'procedure_review' and not (prepared_review or {}).get('procedure'):
        raise ValueError('程序核查底稿需要legal_review.procedure，不生成空白程序结论。')
    if document_type in REMEDY_DOCUMENTS:
        route, action = REMEDY_DOCUMENTS[document_type]
        procedure = (prepared_review or {}).get('procedure') or {}
        remedy = procedure.get('remedy') or {}
        if procedure.get('route') != route or remedy.get('candidate_action') != action:
            raise ValueError('救济文书缺少匹配的来源绑定程序候选；先核对裁判类型和救济主体，不生成错误类型文书。')
        if not selected_sections['requests'] or not selected_sections['facts']:
            raise ValueError('救济文书须同时选入requests具体请求与facts理由/限制材料；缺项未生成文稿。')
        role_fields = ({'appellant': '上诉人', 'appellee': '被上诉人'} if document_type == 'civil_appeal'
                       else {'applicant': '用人单位', 'respondent': '劳动者'})
        from procedure_remedies import _labels
        # Explicit source labels can disprove a selected role; absence never proves it.
        for party in (prepared_brief or {}).get('parties', []):
            label = role_fields[party['role']]
            names = {name.strip() for context in contexts.values()
                     for name in _labels(context['text'], r'(?:拟)?' + re.escape(label))}
            if names and names != {party['name']}:
                raise ValueError('所填角色与原文明确主体标识冲突或有多个候选；请核对后重试。')
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
    if document_type in REMEDY_DOCUMENTS:
        draft.add_heading('原裁判标识与受理机关核对', 1)
        draft.add_paragraph('原审法院或仲裁委员会、原案号、案由、裁判作出日期及所争议部分：'
                            '【请据原件逐项补全；下列引用不等于已经确认这些项目。】')
        for row in prepared_review['procedure']['remedy']['classification_citations']:
            draft.add_paragraph('程序分类来源：' + row['citation']['path'])
            draft.add_paragraph(row['quote'])
        if document_type == 'labor_award_set_aside':
            draft.add_paragraph('承办人核对：仲裁委员会所在地中级人民法院、法定撤销事由及对应证据；'
                                '对实体结果不满不当然构成撤销事由，不套用一般上诉。')
        else:
            draft.add_paragraph('承办人核对：原审法院、二审受理机关、具体上诉范围、理由及当事人信息；'
                                '本稿未自动认定上诉条件或代为选择撤销、改判或发回的具体请求。')
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
        if key == 'requests' and document_type != 'procedure_review':
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
    if prepared_issues:
        draft.add_heading('逐项争点与论证底稿（分类及适用待核）', 1)
        draft.add_paragraph('下列分组是拟议材料关联，不认定证明力、法律依据适用或主张成立；未选入不代表材料不存在。')
        group_labels = {'claim':'拟讨论主张','supporting':'拟支持材料','opposing':'相反或限制材料','legal_basis':'法律依据'}
        for index, issue in enumerate(prepared_issues, 1):
            draft.add_heading(f'争点{index}', 2)
            for key, label in group_labels.items():
                if not issue[key]:
                    draft.add_paragraph(f'本争点未选入{label}；请回读完整材料后补入或说明适用范围，不据此认定不存在。')
                for row in issue[key]:
                    draft.add_paragraph(label+'（材料原文，分类待核）：'+row['contextual_quote'])
                    draft.add_paragraph('出处：'+row['citation']['path']+'；片段'+str(row['citation']['chunk']))
            draft.add_paragraph('律师待核：请求权构成、各项事实与证据对应、相反材料回应、举证责任、法源效力及程序条件；本程序未自动完成这些判断。')
        audit.add_heading('逐项争点来源与位置', 1)
        audit.add_paragraph(json.dumps(prepared_issues, ensure_ascii=False, indent=2))
    if prepared_claims:
        draft.add_heading('逐项请求与争点对应（待核关联）',1)
        draft.add_paragraph('各请求分别展示，不合并金额或推定彼此兼容；原文中的请求不等于律师已决定采用。')
        linked=set()
        for number,item in enumerate(prepared_claims,1):
            draft.add_heading(f'请求{number}',2)
            draft.add_paragraph('请求原文：'+item['quote'])
            draft.add_paragraph('出处：'+item['request']['path']+'；片段'+str(item['request']['chunk']))
            if not item['issue_indices']:
                draft.add_paragraph('未关联争点：请补请求依据、事实要件和相反材料；不据此认定无请求权。')
            for index in item['issue_indices']:
                linked.add(index)
                issue=prepared_issues[index]
                draft.add_paragraph(f'对应争点{index+1}；拟支持{len(issue["supporting"])}条，相反或限制{len(issue["opposing"])}条，法律依据{len(issue["legal_basis"])}条；来源及全文见该争点。')
                if issue['missing_groups']:
                    draft.add_paragraph('未选入组：'+ '、'.join(group_labels[k] for k in issue['missing_groups'])+'；需要补选或说明，不等于不存在。')
        unlinked=[str(i+1) for i in range(len(prepared_issues)) if i not in linked]
        if unlinked: draft.add_paragraph('尚未关联请求的争点：'+ '、'.join(unlinked)+'；请核对是否遗漏。')
        audit.add_paragraph(json.dumps(prepared_claims,ensure_ascii=False,indent=2))
    if review_text:
        draft.add_heading('请求权与程序工作底稿',1)
        for line in review_text.splitlines():draft.add_paragraph(line)
        audit.add_paragraph(json.dumps(prepared_review,ensure_ascii=False,indent=2))
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
    if document_type in REMEDY_DOCUMENTS:
        user_summary += '文书类型：' + title + '（来源草稿）。已分列原裁判核对、专用角色、请求和理由，尚未完成全文法律论证或提交要件审核。'
    elif document_type == 'procedure_review':
        user_summary += '文书类型：程序核查底稿，仅整理程序候选和来源，不生成答辩主张或拟提出的请求。'
    user_summary += '正文选入原文：' + selections + '。'
    user_summary += '已形成待审条件请求。' if conditional else '未形成条件请求。'
    user_summary += f'程序金额核对{len(arithmetic)}项。'
    if prepared_review:
        user_summary+=f'已保存请求权要件核查{len(prepared_review["claims"])}项及'+('程序核查表；' if prepared_review['procedure'] else '未选程序路线；')+'正反材料与缺选项均在文档，尚未认定要件成立、管辖或期限。'
        if prepared_review['procedure'] and prepared_review['procedure'].get('remedy'):
            user_summary+='\n'+prepared_review['procedure']['remedy']['text']+'\n'
    if prepared_claims:
        user_summary += f'已保存来源绑定请求对应{len(prepared_claims)}项；逐项列明争点关联和未关联缺口，不合并金额或认证请求成立。'
    if prepared_issues:
        user_summary += f'已保存来源绑定争点{len(prepared_issues)}项，分别列出拟支持、相反或限制材料与法律依据；空组仅表示未选入，分类及适用仍待核。'
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
            'body_text': '\n'.join(p.text for p in draft.paragraphs),'claims':prepared_claims,'legal_review':prepared_review,
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
            'excerpts': rows, 'issues': prepared_issues, 'calculations': arithmetic, 'sources': list(used.values()),
            'ready_to_submit': False, 'legal_verified': False, 'limits': LIMITS}
