"""Save an attributed evidence matrix using the existing case note/citation chain."""
import json


NOTICE = ('本记录为待复核办案分析。引文 matched 仅表示原句与本案材料匹配，不证明真实性、'
          '合法性、关联性或证明力；未提交不等于不存在，对方陈述不自动构成诉讼自认。')
ISSUE_KEYS = {'proposition', 'finding_kind', 'assessment', 'supporting', 'opposing',
              'unknown', 'admissibility', 'supplement'}
KINDS = {'material_statement': '材料陈述（非已认定事实）', 'inference': '推断', 'unknown': '未知/待核'}


def _text(value, label, maximum=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f'{label}须为1至{maximum}字文字。')
    return value


def _list(value, label, maximum=30):
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError(f'{label}须为至多{maximum}项列表；未知状态请写明，不能填否定事实。')
    return value


def save_evidence_analysis(cases, case_id, issues, request_id='', supersedes=''):
    """Append a reviewable note; retain raw quotes, let CaseStore verify every citation."""
    if not isinstance(issues, list) or not 1 <= len(issues) <= 30:
        raise ValueError('请提供1至30项待证命题。')
    # Validate before reading case data or writing. Limits also bound stored/exported text.
    try:
        if len(json.dumps(issues, ensure_ascii=False)) > 200000:
            raise ValueError('单次分析过长，请按争点分批保存。')
    except (TypeError, OverflowError):
        raise ValueError('分析内容须为可保存的文字和引用。') from None
    lines, citations = ['证据分析（待复核）', NOTICE], []
    for number, issue in enumerate(issues, 1):
        if not isinstance(issue, dict) or set(issue) != ISSUE_KEYS:
            raise ValueError('每项需包含 proposition/finding_kind/assessment/supporting/opposing/unknown/admissibility/supplement，不能添加评分或其他字段。')
        proposition = _text(issue['proposition'], '待证命题')
        kind = issue['finding_kind']
        if not isinstance(kind, str) or kind not in KINDS:
            raise ValueError('finding_kind 只能为 material_statement、inference 或 unknown。')
        lines.extend(['', f'{number}. 待证命题：{proposition}', f'结论层级：{KINDS[kind]}',
                      '当前分析：' + _text(issue['assessment'], '当前分析')])
        for key, label in (('supporting', '支持材料'), ('opposing', '反对材料')):
            rows = _list(issue[key], label)
            lines.append(label + ('：' if rows else '：本次未列明，不能推定不存在。'))
            for row in rows:
                if not isinstance(row, dict) or set(row) != {'statement', 'speaker', 'carrier', 'citations'}:
                    raise ValueError('材料项需包含 statement、speaker、carrier、citations。')
                lines.append('陈述：' + _text(row['statement'], '材料陈述') + '；陈述主体：' +
                             _text(row['speaker'], '陈述主体', 300) + '；载体：' + _text(row['carrier'], '来源载体', 500))
                refs = _list(row['citations'], '来源引用', 20)
                if not refs:
                    lines.append('出处：未提供可核对引用，仅保留为待核陈述。')
                for ref in refs:
                    if not isinstance(ref, dict):
                        raise ValueError('每项引用须为来源对象；缺少位置可保留但不能称已核验。')
                    citation = dict(ref)
                    pending = []
                    # A failed alignment cannot be upgraded by contradictory caller offsets.
                    if citation.get('status') in ('unmatched', 'ambiguous', 'unverified'):
                        pending.append('原定位结果为' + citation['status'] + '，须补充上下文重新核对。')
                    path = citation.get('path')
                    source_path = (cases.store.safe(path, must_exist=False).relative_to(cases.root).as_posix()
                                   if isinstance(path, str) and path.strip() else '')
                    if (source_path.lower().startswith('drafts/') or
                            citation.get('source_kind') in ('model_draft', 'inference', 'draft')):
                        pending.append('模型或工作稿不能自证为来源证据，须回到原始材料，正文保留待核。')
                    if pending:
                        citation.update(start=None, end=None)
                    citations.append(citation)
                    # Original status is an untrusted input, never a finding in the body.
                    body_ref = {key: value for key, value in citation.items() if key != 'status'}
                    lines.append(f'引文[{len(citations)}]（状态以引用核验栏为准）：' +
                                 json.dumps(body_ref, ensure_ascii=False, sort_keys=True))
                    lines.extend('待核：' + reason for reason in pending)
        for key, label in (('unknown', '未知与缺件'), ('supplement', '补证事项')):
            values = _list(issue[key], label)
            lines.append(label + '：' + ('；'.join(_text(v, label) for v in values) if values else '本次未列明，需承办人复核。'))
        checks = issue['admissibility']
        if not isinstance(checks, dict) or set(checks) != {'authenticity', 'legality', 'relevance'}:
            raise ValueError('admissibility 须包含 authenticity、legality、relevance 三类待核问题。')
        for key, label in (('authenticity', '真实性待核'), ('legality', '合法性待核'), ('relevance', '关联性待核')):
            values = _list(checks[key], label)
            lines.append(label + '：' + ('；'.join(_text(v, label) for v in values) if values else '未列问题，不表示已通过。'))
    note = cases.add_note(case_id, 'evidence_analysis', '\n'.join(lines), source='本案证据分析',
                          citations=citations, request_id=request_id, supersedes=supersedes)
    return {**note, 'saved': bool(note.get('id')), 'legal_verified': False, 'notice': NOTICE}
