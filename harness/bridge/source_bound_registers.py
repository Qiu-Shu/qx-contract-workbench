"""Deterministic, case-scoped quotation registers, not legal fact classifiers."""
import copy
import re
from hashlib import sha256
from io import BytesIO
from contextlib import contextmanager
from datetime import date

from docx_delivery import _filename, _publish


FIELDS = {
    'corporate': dict(agenda='议题', entity='主体', participants='人员', notice='通知',
                      meeting='会议', votes='票数', decision='决定', signature='签署',
                      mandate='授权', debt='债务事项', follow_up='后续安排'),
    'compliance': dict(obligation='要求', responsible_party='责任主体', scope='适用范围',
                       deadline='截止日期', feedback_deadline='反馈日期', report_deadline='报送日期',
                       decision='业务决定', submission='提交情况', implementation='实施情况',
                       acceptance='验收情况', evidence_status='记录情况'),
    'ip': dict(asset_type='资产及权利类型', jurisdiction='材料所示法域', intended_use='拟使用地',
               application_place='拟申请地', applicant='申请人', inventor='创作者或发明人',
               agent='代理机构', registered_holder='登记权利人', licensor='许可人',
               licensee='被许可人', license_scope='许可范围', status='权利阶段',
               filing_date='申请日期', certificate_term='证载期限',
               internal_estimate='内部预计期限', date_context='日期与事件原文线索', fees='费用'),
}
KINDS = {'corporate': 'corporate_record_draft', 'compliance': 'compliance_work', 'ip': 'ip_register'}
TITLES = {'corporate': '公司事项原文台账', 'compliance': '合规事项原文台账', 'ip': '知识产权原文台账'}
ACTUAL_STATUS = '以本项来源原文明确记载为限；未明确部分待核。'
NOTICE = ('本表逐字保留材料记载（包括明确决定、0票、未申请等），不将已给内容改为未知。'
          '来源匹配只证明文字出处，不认证事实真实性或法律效力；材料缺少记录不等于实际未发生。'
          '字段名称仅为摘录分类，不证明原文支持该分类；须结合完整片段复核主体、事项和语境。')
REVIEW_ACTIONS = {
    'corporate': '请按议题核对既有会议、表决及签署材料；已给票数与决定保留，未给结果不等于事项未发生。',
    'compliance': ('先查已有业务决定及反馈、报送记录。分别跟踪义务主体、适用范围、反馈截止日和报告截止日；'
                   '只有参考日与年份明确时才比较日历先后。临近反馈期时先复核现有决定和理由，再决定是否追加动作；'
                   '反馈期仍开放不等于合规履行期，日期已过也不证明未履行。'),
    'ip': ('分别核对每项资产的申请人、代理人、许可双方与权利类型；内部提交、官方申请和授权须分开。'
           '证载期与内部预计照录并核对依据；先确认法域、申请日与适用过渡规则，再判断期限。'
           '历史法版本不由授权日直接决定，证载期限也不证明当前权利有效；请核对官方登记与后续变更。'),
}
IP_RULE_CARD = {
    'id': 'cn-design-pre-20210601', 'jurisdiction': '中国', 'right_type': '外观设计专利',
    'transition_basis': 'application_date', 'applies_before': '2021-06-01',
    'pre_transition_years': 10, 'applied_to_asset': False,
    'official_source': 'https://www.cnipa.gov.cn/art/2021/5/27/art_2073_159683.html',
    'checked_at': '2026-11-05',
    'text': ('仅在确认属于中国外观设计且申请日早于2021-06-01时，按官方过渡说明核对十年保护期限；'
             '历史法基准是申请日及过渡条件，不以授权日直接选择版本。'
             '本卡未应用于任何资产，未计算届满日，不能据期限认定今日有效。'
             '法域、类型或申请日等基础未确认时，须先核实适用条件。'
             '商标证载期限与内部预计独立保留，均不替代当前登记状态。'),
}


@contextmanager
def _publication_guard(cases):
    published = {}
    try:
        yield published
    except Exception:
        if published:
            path = cases.safe(published['path'])
            if path.is_file() and sha256(path.read_bytes()).hexdigest() == published['sha256']:
                path.unlink()
        raise


def _corporate_document(rows, document_type, classifications):
    """Compose source excerpts and fixed drafting conditions; no inferred legal events."""
    from docx import Document
    from docx.shared import Cm, Pt, RGBColor
    from docx.oxml.ns import qn
    doc = Document()
    for name in ('Normal', 'Title', 'Heading 1'):
        style = doc.styles[name]
        style.font.name = 'Microsoft YaHei'
        style.element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
        style.font.color.rgb = RGBColor(0, 0, 0)
    doc.styles['Normal'].font.size = Pt(11)
    doc.styles['Normal'].paragraph_format.line_spacing = 1.15
    doc.styles['Normal'].paragraph_format.space_after = Pt(4)
    doc.styles['Title'].font.size = Pt(18)
    doc.styles['Title'].paragraph_format.space_after = Pt(6)
    doc.styles['Heading 1'].font.size = Pt(12)
    doc.styles['Heading 1'].paragraph_format.space_before = Pt(8)
    doc.styles['Heading 1'].paragraph_format.space_after = Pt(3)
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin = section.bottom_margin = Cm(2)
    section.left_margin = section.right_margin = Cm(2)
    title = '会议纪要 待核稿' if document_type == 'minutes' else '担保事项拟议案'
    doc.add_paragraph(title, 'Title')
    doc.add_paragraph('本轮根据本案材料整理，供核对和修改；未认定既有会议程序、决定或签署的法律效力。')
    if document_type == 'proposal':
        doc.add_heading('拟审议事项', 1)
        doc.add_paragraph('拟提请股东会审议材料所述担保事项，具体要素以已核材料补齐。')
    groups = [('主体与会议信息', {'entity', 'participants', 'notice', 'meeting'}),
              ('议题与材料记载', {'agenda', 'debt', 'mandate'}),
              ('表态与决定记录', {'votes', 'decision'}),
              ('签署与后续安排', {'signature', 'follow_up'})]
    seen, sources = set(), {}
    for heading, fields in groups:
        selected = [r for r, audit in zip(rows, classifications) if audit['requested_field'] in fields]
        if not selected:
            continue
        doc.add_heading(heading, 1)
        for row in selected:
            ref = row['citation']
            key = (ref['path'], ref['chunk'], row['quote'])
            if key in seen:
                continue
            seen.add(key)
            source_key = (ref['path'], ref['version'], ref['chunk'], ref['sha256'])
            source_number = sources.setdefault(source_key, len(sources) + 1)
            doc.add_paragraph(f'材料记载：{row["quote"]} [{source_number}]')
    doc.add_heading('待核事项', 1)
    doc.add_paragraph('材料明确的决定、票数和签署照录；未明确的相关结果本稿待核，不能据材料未记载认定事项未发生。')
    doc.add_paragraph('请逐议题核对既有通知、会议记录、表决和签署材料；公司类型、事项时点、有效章程、权限及适用程序须结合原件复核。')
    doc.add_paragraph('本稿不新增执行授权、负责人、期限或生效条件；补齐待核要素后再决定签署、提交或对外使用。')
    for (path, version, chunk, _), number in sources.items():
        doc.add_paragraph(f'来源 [{number}]：{path}，版本{version}，片段{chunk}。')
    body = '\n'.join(p.text for p in doc.paragraphs)
    data = BytesIO(); doc.save(data)
    return data.getvalue(), body


def _calendar_date(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
        raise ValueError('日期须为YYYY-MM-DD，不接受自由文字结论。')
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError('日期不是有效日历日期。') from error


def _date_in_quote(value, quote, with_year):
    year = f'{value.year:04d}'
    month = f'0?{value.month}' if value.month < 10 else str(value.month)
    day = f'0?{value.day}' if value.day < 10 else str(value.day)
    if with_year:
        pattern = (rf'(?<![0-9])(?:{year}-{month}-{day}|'
                   rf'{year}年{month}月{day}日)(?![0-9])')
    else:
        # Ambiguous mixed dates need a narrower exact excerpt, never year inference.
        if re.search(r'[0-9]{4}\s*(?:年|[-/])', quote):
            return False
        pattern = rf'(?<![0-9年]){month}月{day}日(?![0-9])'
    return re.search(pattern, quote) is not None


def _compliance_tracking(rows, tracking):
    if not isinstance(tracking, dict) or set(tracking) != {'as_of', 'as_of_entry', 'deadlines'}:
        raise ValueError('tracking仅接受as_of、as_of_entry、deadlines，不接受履行成功或失败状态。')
    reference = _calendar_date(tracking['as_of'])

    def selected(index):
        if type(index) is not int or not 0 <= index < len(rows):
            raise ValueError('跟踪来源索引须为本批entries的0起始编号。')
        return rows[index]['quote']

    reference_quote = selected(tracking['as_of_entry'])
    if not _date_in_quote(reference, reference_quote, True):
        raise ValueError('参考日须在所选本案原文中有完整年月日。')
    deadlines = tracking['deadlines']
    if not isinstance(deadlines, list) or not 1 <= len(deadlines) <= 20:
        raise ValueError('deadlines须为1至20项日期线索。')
    results = []
    lines = ['合规日历跟踪', f'参考日：{reference.isoformat()}；来源原文：{reference_quote}',
             '本节只比较选定来源日期。将日期用作本事项截止日的关系仍待核，不认证法定期限或履行状态。']
    for number, item in enumerate(deadlines, 1):
        if not isinstance(item, dict) or set(item) != {'entry', 'date', 'year_basis'}:
            raise ValueError('每个日期线索只接受entry、date、year_basis。')
        value = _calendar_date(item['date'])
        quote = selected(item['entry'])
        basis = item['year_basis']
        if basis == 'explicit':
            if not _date_in_quote(value, quote, True):
                raise ValueError('所选日期的完整年月日未在该条原文匹配，不能补成年份已知。')
            year_text = '年月日据来源原文'
        elif basis == 'same_as_reference_assumption':
            if value.year != reference.year or not _date_in_quote(value, quote, False):
                raise ValueError('同年假设只适用于来源明确月日且未附年份的日期，不得另造日期。')
            year_text = '年份未给，暂按参考日同年假设；须核原通知年份'
        else:
            raise ValueError('year_basis须为explicit或same_as_reference_assumption。')
        delta = (value - reference).days
        relation = 'before_date' if delta > 0 else 'same_date' if delta == 0 else 'after_date'
        wording = ('所选日期尚未到达' if delta > 0 else '参考日与所选日期同日' if delta == 0
                   else '参考日已在所选日期之后')
        comparison = f'{wording}，相差{abs(delta)}个自然日。'
        lines.extend(['', f'日期线索{number}｜来源摘录{item["entry"] + 1}',
                      f'材料原文：{quote}', f'用于比较的日期：{value.isoformat()}；{year_text}。', comparison,
                      '若该日期是意见反馈截止日，则据此核对反馈窗口；若是整改报告截止日，则分别跟踪报告义务。'])
        results.append({**item, 'source_quote': quote, 'days_from_reference': delta,
                        'date_relation': relation, 'date_semantics_verified': False,
                        'year_assumption': basis != 'explicit', 'comparison': comparison})
    lines.extend(['', '相关材料原文（不由分类推定实际事件）'])
    for index, row in enumerate(rows, 1):
        lines.append(f'来源摘录{index}：{row["quote"]}')
    actions = ('内部建议：按上述日期线索分别核对事项和通知年份；材料已有明确决定时先核对并沿用其范围。'
               '如已有发送记载，先核投递记录和回执，不安排重复首次提交；无回执只需核受理状态。'
               '材料缺记录时先查既有记录，不认定实际未决定、未提交或未受理。'
               '需要改变既有决定或补充报送时另行确认，不能把建议写成批准。')
    lines.extend(['', actions,
                  '计算边界：仅自然日差，不调整工作日、节假日、送达起算、当日截止时点或法律期间，不由日期先后推定履行。'])
    return {'as_of': reference.isoformat(), 'as_of_entry': tracking['as_of_entry'],
            'reference_quote': reference_quote, 'deadlines': results, 'actions': actions}, '\n'.join(lines)


def save_source_bound_register(cases, case_id, domain, entries, request_id='', supersedes='',
                               document_type='', filename='', tracking=None):
    """Save literal case citations, never accept model-written event/effect states.

    entries: [{field: domain enum, citation: {path, sha256, chunk, quote}}].
    An optional matching case_id is accepted inside citation; all other keys reject.
    Output includes top-level id/kind for export_case and fixed legal_verified=False.
    corporate document_type minutes/proposal (guarantee proposal skeleton) plus
    filename creates an editable DOCX. Other domains must omit these options.
    Every returned entry is a source_excerpt. Model fields are retained separately
    in classification_audit, never as confirmed fact fields. Compliance may pass
    tracking={as_of,as_of_entry,deadlines:[{entry,date,year_basis}]} with zero-based
    entry indexes and ISO dates. Dates must match the cited entry. year_basis is
    explicit or same_as_reference_assumption, the latter prominently conditional.
    """
    if not isinstance(domain, str) or domain not in FIELDS:
        raise ValueError('domain须为corporate、compliance或ip。')
    if tracking is not None and domain != 'compliance':
        raise ValueError('tracking目前仅用于compliance的来源日期比较。')
    if not isinstance(document_type, str) or not isinstance(filename, str):
        raise ValueError('文稿类型和文件名须为文字。')
    if document_type:
        if domain != 'corporate' or document_type not in {'minutes', 'proposal'}:
            raise ValueError('仅corporate支持minutes或proposal文稿。')
        _filename(filename)
    elif filename:
        raise ValueError('指定文件名时须同时指定文稿类型。')
    if not isinstance(entries, list) or not 1 <= len(entries) <= 40:
        raise ValueError('entries须为1至40项原文摘录。')
    if not all(isinstance(value, str) and len(value) <= 200 for value in (request_id, supersedes)):
        raise ValueError('请求编号与更正编号须为不超过200字的字符串。')
    prepared = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {'field', 'citation'}:
            raise ValueError('每项只接受field和citation，实际状态及效力由程序固定留出边界。')
        field = entry['field']
        if not isinstance(field, str) or field not in FIELDS[domain]:
            raise ValueError('field须为该领域的中性字段枚举。')
        ref = entry['citation']
        required = {'path', 'sha256', 'chunk', 'quote'}
        if not isinstance(ref, dict) or not required <= set(ref) or set(ref) - required - {'case_id'}:
            raise ValueError('引文须含path、sha256、chunk、quote，不能自填匹配状态或版本。')
        if ref.get('case_id', case_id) != case_id:
            raise ValueError('引文不能引用其他案件编号。')
        if not isinstance(ref['path'], str) or not ref['path'].strip() or len(ref['path']) > 2000:
            raise ValueError('请提供本案材料路径。')
        if not isinstance(ref['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', ref['sha256']):
            raise ValueError('sha256必须来自本案材料读取结果。')
        if type(ref['chunk']) is not int or ref['chunk'] < 0:
            raise ValueError('chunk须为实际读取的非负片段编号。')
        if not isinstance(ref['quote'], str) or not ref['quote'].strip() or len(ref['quote']) > 6000:
            raise ValueError('quote须为1至6000字逐字引文。')
        path = cases.safe(ref['path']).relative_to(cases.root).as_posix()
        if path.split('/')[0].lower() == 'drafts':
            raise ValueError('生成稿不能作为独立原始来源，请引用本案材料。')
        prepared.append((field, {**ref, 'path': path}))

    # Keep case membership, version checks and append in one SQLite transaction.
    with _publication_guard(cases) as published, cases.db() as db:
        db.execute('BEGIN IMMEDIATE')
        cases._case(db, case_id)
        checked, warnings = cases._citations(db, case_id, [ref for _, ref in prepared])
        if warnings or any(ref.get('status') != 'matched' for ref in checked):
            raise ValueError('来源版本变化或逐字引文未匹配，本批未保存；请重新读取本案材料。')
        rows, classifications, total_context = [], [], 0
        for (field, _), ref in zip(prepared, checked):
            chunk = db.execute('SELECT text FROM chunks WHERE path=? AND ordinal=?',
                               (ref['path'], ref['chunk'])).fetchone()
            context = chunk['text'] if chunk else ''
            if not context or len(context) > 16000:
                raise ValueError('来源片段不存在或过长，请拆分后重新读取；本批未保存。')
            total_context += len(context)
            if total_context > 120000:
                raise ValueError('本批上下文过长，请分批整理。')
            classifications.append({'entry': len(rows), 'requested_field': field,
                                    'classification_verified': False, 'is_fact_field': False})
            rows.append({'field': 'source_excerpt', 'label': '来源原文', 'quote': ref['quote'],
                         'classification_verified': False,
                         'context': context, 'citation': ref, 'actual_status': ACTUAL_STATUS,
                         'legal_effect': '待复核；程序不作法律效力判断。'})

        cards = [copy.deepcopy(IP_RULE_CARD)] if domain == 'ip' else []
        lines = [TITLES[domain], '', NOTICE, '', '本轮整理状态：新整理稿，不改变材料所述历史事件。']
        for index, row in enumerate(rows, 1):
            ref = row['citation']
            lines.extend(['', f'事项{index}｜{row["label"]}', '材料逐字记载：', row['quote'],
                          f'实际状态：{ACTUAL_STATUS}', f'效力：{row["legal_effect"]}',
                          f'来源：{ref["path"]}｜版本{ref["version"]}｜片段{ref["chunk"]}｜SHA-256 {ref["sha256"]}',
                          '完整片段上下文（来源文字，不是本程序结论）：', row['context']])
        lines.extend(['', '分类审计（与事实条目分开保存）'])
        for audit in classifications:
            lines.append(f'来源摘录{audit["entry"] + 1}：模型候选分类（未核验；不是事实字段）：{audit["requested_field"]}')
        tracked, tracking_text = _compliance_tracking(rows, tracking) if tracking is not None else (None, '')
        if tracking_text:
            lines.extend(['', tracking_text])
        for card in cards:
            lines.extend(['', '规则核对卡（未应用于本案）', card['text'],
                          f'官方来源：{card["official_source"]}；核验日：{card["checked_at"]}。'])
        lines.extend(['', '风险与下一步核查', REVIEW_ACTIONS[domain]])
        data, body = _corporate_document(rows, document_type, classifications) if document_type else (None, '')
        if body:
            lines.extend(['', '本次可编辑文稿正文', body])
        lines.extend(['', '复核与下一步：先核原件、身份、事项和材料时点；缺记录先查既有记录，'
                      '不能直接写未决定、未提交、未授权。期限比较须单列明确参考日和计算边界，'
                      '不由日期已过推定未履行。需法律评价、会议文稿或拟议案时另行复核，'
                      '不要用新稿状态代替历史状态。本工具没有提交、签署、登记或对外发送。'])
        note = cases._add_note(db, case_id, KINDS[domain], '\n'.join(lines),
                              source='本案逐字来源台账；匹配非真实性或效力认证。',
                              supersedes=supersedes, citations=[ref for _, ref in prepared],
                              request_id=request_id)
        if note.get('warnings'):
            raise ValueError('保存期间来源变化，本批未保存，请重新读取本案材料。')
        saved = note.get('recorded') is not False
        if saved and data:
            current, warnings = cases._citations(db, case_id, [ref for _, ref in prepared])
            if warnings or any(ref.get('status') != 'matched' for ref in current):
                raise ValueError('导出前来源变化，未保存文稿。')
            published.update(_publish(cases.store, filename, data))
            current, warnings = cases._citations(db, case_id, [ref for _, ref in prepared])
            if warnings or any(ref.get('status') != 'matched' for ref in current):
                raise ValueError('导出期间来源变化，本次文稿已撤回。')
        summary = ('已保存本案来源底稿。' if saved else '更正发生冲突，本次未保存。')
        if published:
            summary += f'已生成可编辑文稿：{published["relative_path"]}。正文与本次内部底稿一致。'
        summary += REVIEW_ACTIONS[domain] + '来源匹配不认证事实真实性或法律效力；本工具未提交、签署或对外发送。'
        if saved and tracking_text:
            summary += '\n\n' + tracking_text
        return {**note, 'saved': note.get('recorded') is not False, 'entries': rows,
                'classification_audit': classifications, 'tracking': tracked,
                'tracking_text': tracking_text if saved else '',
                'rule_cards': cards, 'legal_verified': False, 'notice': NOTICE,
                'review_actions': REVIEW_ACTIONS[domain], 'user_summary': summary,
                'document_type': document_type, 'body_text': body if published else '',
                'ready_to_submit': False, **published}
