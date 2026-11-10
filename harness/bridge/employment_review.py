"""Record employment review drafts and calculate explicit monetary scenarios only."""
from decimal import Decimal, localcontext, ROUND_HALF_UP
import json
import re


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label}须提供文字，未知事项请明确写待核及所缺材料。')
    if len(value) > 20000:
        raise ValueError(f'{label}超过20000字上限，请分批保存，不会截断正文。')
    return value


def save_employment_review(cases, case_id, stage, findings, request_id='', supersedes=''):
    """追加待核劳动审查笔记；每项fact/basis/source/risk/action，可选topic/pending/citations。

    stage为hiring/change/termination/dispute；更正仅在用户明确要求时传supersedes。
    citations沿用案件原文校验（path、quote，可选sha256、chunk），不把材料陈述认定为事实。
    """
    if stage not in ('hiring', 'change', 'termination', 'dispute'):
        raise ValueError('stage须为hiring/change/termination/dispute。')
    if not isinstance(findings, list) or not 1 <= len(findings) <= 100:
        raise ValueError('findings须为1至100项审查记录。')
    try:
        size = len(json.dumps(findings, ensure_ascii=False))
    except (TypeError, ValueError, OverflowError, RecursionError):
        raise ValueError('findings须为可保存的文字和引用对象。') from None
    if size > 200000:
        raise ValueError('单次审查含引用超过200000字上限，请分批保存，不会截断正文。')
    lines = [f'劳动用工审查｜阶段：{stage}｜内部工作稿，事实及法律适用均待核']
    citations = []
    rule_reviews=[]
    from draft_review import DraftReview,save_review_audit
    review=DraftReview(cases,case_id)
    labels = {'fact':'事实/陈述', 'basis':'依据及适用边界', 'source':'来源', 'risk':'风险', 'action':'行动'}
    for i, item in enumerate(findings, 1):
        if not isinstance(item, dict) or set(item) - (set(labels) | {'topic', 'pending', 'citations','rule','parameters'}):
            raise ValueError('审查项含不支持字段，请使用fact/basis/source/risk/action/topic/pending/citations。')
        rule=item.get('rule')
        if rule is not None and rule not in ('probation_pay','noncompete_comparison'):raise ValueError('不支持的程序审查规则。')
        pay_topic=isinstance(item.get('topic'),str) and re.search(r'试用.{0,4}工资|工资.{0,4}试用',item['topic'])
        program_owned=rule in ('probation_pay','noncompete_comparison') or (stage=='hiring' and pay_topic)
        if rule=='noncompete_comparison':
            from employment_rule_review import prepare_noncompete_comparison
            item,rule_review=prepare_noncompete_comparison(cases,case_id,item,i-1);rule_reviews.append(rule_review)
        elif rule=='probation_pay' or (stage=='hiring' and pay_topic):
            if stage!='hiring':raise ValueError('试用工资规则用于hiring阶段。')
            from employment_rule_review import prepare_probation_pay
            item,rule_review=prepare_probation_pay(cases,case_id,item,i-1);rule_reviews.append(rule_review)
        elif 'parameters' in item:raise ValueError('parameters须与支持的rule共同使用。')
        # Correct only affected prose before persistence/export; source quotes and
        # caller inputs remain separately inspectable in the internal audit.
        item=dict(item)
        refs=item.get('citations',[])
        if not program_owned and refs==[] and any(re.search('竞业|补偿|对价',str(item.get(k,''))) for k in ('topic','fact','basis','risk','action')):
            from noncompete_conditions import single_source_citation
            recovered=single_source_citation(cases,case_id)
            if recovered:
                refs=recovered;item['citations']=recovered
        nc=any('竞业' in str(item.get(k,'')) for k in ('topic','fact','basis','risk','action'))
        if (not nc and isinstance(item.get('topic'),str) and '离职后经济补偿' in item['topic']
                and re.search(r'第(?:36|三十六)条',str(item.get('basis','')))):
            nc=any(re.search(r'竞业[^。！？\n]{0,30}补偿',text) for text in review.sources(refs if isinstance(refs,list) else []))
        if not nc and not program_owned and isinstance(refs,list):
            nc=any('竞业' in text for text in review.sources(refs))
        release_issue=False
        if nc and not program_owned:
            from noncompete_conditions import release_requested
            release_issue=release_requested(item)
            from employment_rule_review import review_compensation_conditions
            item=review_compensation_conditions(item,review,i)
        for field in ('topic','fact','basis','risk','action','pending','source'):
            if field in item and not program_owned:
                item[field]=review.text(item[field],f'第{i}项{field}',refs if isinstance(refs,list) else [],
                    noncompete=nc and field in ('topic','fact','risk','action'),proposal=field=='action')
        if nc and not program_owned:
            from noncompete_conditions import finalize_noncompete_conditions
            item=finalize_noncompete_conditions(item,review,i,release_issue=release_issue)
        if rule_reviews and rule_reviews[-1]['finding_index']==i-1:
            rule_reviews[-1]['prepared_finding']=dict(item)
        lines.append(f'\n{i}. '+_text(item.get('topic', '审查事项'), 'topic'))
        lines.extend(f'{label}：{_text(item.get(key), key)}' for key, label in labels.items())
        lines.append('待核事项：'+_text(item.get('pending', '事实、来源及法律适用尚需核验'), 'pending'))
        refs = item.get('citations', [])
        if not isinstance(refs, list) or any(not isinstance(ref, dict) for ref in refs):
            raise ValueError('citations须为案件材料引文对象列表。')
        if len(refs) > 20 or len(citations) + len(refs) > 200:
            raise ValueError('每项至多20条引用，单次至多200条；请分批保存。')
        for ref in refs:
            citation = dict(ref)
            lines.append('原始引用输入（非事实认定）：'+json.dumps(ref, ensure_ascii=False, sort_keys=True))
            if citation.get('status') in ('unmatched', 'ambiguous', 'unverified'):
                # An offset match cannot resolve a previously failed or ambiguous alignment.
                citation['provided_status'] = citation['status']
                citation['start'] = citation['end'] = None
                lines.append('引用待核：保留原失败/歧义状态，不能据位置匹配升级为已核。')
            path = citation.get('path', '')
            source_path = (cases.store.safe(path, must_exist=False).relative_to(cases.root).as_posix()
                           if isinstance(path, str) and path.strip() else '')
            if (source_path.lower().startswith('drafts/') or
                    citation.get('source_kind') in ('model_draft', 'inference', 'draft')):
                # Keep the path so CaseStore still enforces this case's material membership.
                citation['start'] = citation['end'] = None
                lines.append('引用待核：草稿/模型输出不能作为原始证据；正文及原引用已保留，请补原始材料。')
            citations.append(citation)
    result=cases.add_note(case_id, 'employment_review', '\n'.join(lines),
                          source='劳动用工审查；来源见各项；未作事实或法律认定',
                          supersedes=supersedes, citations=citations, request_id=request_id)
    if result.get('recorded') is False:return result
    # Read the stored revision, including idempotent retries, not a second model summary.
    with cases.db() as db:
        body=db.execute('SELECT content FROM legal_notes WHERE case_id=? AND id=?',
                        (case_id,result['id'])).fetchone()['content']
    summary='已保存劳动审查意见草稿；事实、规则适用及建议尚待律师复核，未对外发送。'
    if review.changes:summary+=f'已修订{len(review.changes)}处事实状态或候选表述，原稿和修订理由见本次内部核对稿。'
    summary+=('\n\n同一保存记录：\n'+body if len(body)<=150000 else
              '\n记录超过聊天展示上限，请回读本次笔记或导出Word查看完整内容；未截断保存。')
    return {**result,'user_summary':summary,'rule_reviews':rule_reviews,'review_changes':review.changes,
            **save_review_audit(cases,case_id,review.changes)}


def _decimal(value, label, places):
    if not isinstance(value, str) or not re.fullmatch(r'\d{1,12}(?:\.\d{1,'+str(places)+r'})?', value):
        raise ValueError(f'{label}须为非负十进制字符串，最多12位整数和{places}位小数；不接受浮点数或科学计数法。')
    return Decimal(value)


def calculate_employment_amount(base, years='1', multiplier='1', assumptions=''):
    """仅算显式确认基数×年限×倍数；不认定N/2N、不选工资基数、不推算工龄或封顶。

    金额base最多2位小数，years/multiplier最多4位，返回两位金额和全部算术假设。
    """
    assumptions = _text(assumptions, 'assumptions（明确基数、年限、倍数的情景假设）')
    b = _decimal(base, 'base', 2); y = _decimal(years, 'years', 4); m = _decimal(multiplier, 'multiplier', 4)
    if m <= 0:
        raise ValueError('multiplier必须大于零。')
    with localcontext() as context:
        context.prec = 64
        amount = (b*y*m).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return {'base':base, 'years':years, 'multiplier':multiplier, 'amount':format(amount, '.2f'),
            'formula':f'{base} × {years} × {multiplier}', 'assumptions':assumptions,
            'rounding':'ROUND_HALF_UP to 0.01', 'legal_entitlement_verified':False,
            'scope':'仅情景算术，不认定应付金额。工资、补偿、赔偿、代通知金分别核定；2008年前分段、当地三倍封顶、12年上限及月工资基数均未自动适用。'}
