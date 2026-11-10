"""Bounded source-state and clause checks, shared by original draft producers.

Not a general entailment engine: checks the documented negative-state families
and unsupported noncompete comparisons, preserving independent clauses.
"""
import re

TOPICS = {
    '起诉状收取情况': r'起诉状|诉状',
    '协商记录': r'协商记录|协商过程|协商程序',
    '授权文件或授权状态': r'授权(?:文件|材料|委托书|手续)?|发函授权',
    '签章情况': r'签名|签章|盖章|捺印',
    '调整期限或配套安排': r'期限|配套|补贴方案',
    '秘密接触情况': r'商业秘密|技术秘密|秘密信息',
}
NEGATIVE = re.compile(r'不存在|缺失|缺少|没有(?!效力|效果|关系|法律依据|事实依据|必要)'
    r'|(?:尚|暂)?无(?=(?:任何|相关|正式|有效|书面)?(?:'+ '|'.join(TOPICS.values()) +r'))'
    r'|未(?:曾|能|实际)?(?:收到|取得|获得|签署|发生|实施|履行|接触|知悉)')
QUALIFIED = re.compile(r'未提供|未提交|未交来|未载明|未记载|未见|材料中|材料内|是否|未知|待核|不清楚|不明|未能确认|不能|不得|不要|不应|不代表|不等于|不推定|不认定|不意味着|不据')
CONDITIONAL = re.compile(r'^\s*(?:[（(]?\d+[)）、.．]\s*)?(?:如果|假如|若|如(?=未|无|有|缺|经|实际|违约|确)|一旦|假设|即使|即便|倘若|在[^。！？\n]{0,30}情况下(?:直接)?(?:改写|修改|认定|填写|推定|声称))')
COMPARISON = re.compile(r'不相称|失衡|低对价|过高|过低|明显不合理|显失公平|范围过宽|范围过广|明显不相适应|明显不匹配|完全脱节|大幅调减的现实风险')
ONCE = re.compile(r'(?:甲方与乙方|双方|用人单位与劳动者)?(?:在)?(?:同一|本次|本份)劳动(?:关系|合同)(?:存续期间|存续期|存续中|中|内)?(?:只|仅|只能|仅能|仅可)?(?:约定|设置|设定)(?:一|1)次试用期')
ONCE_TEXT = '同一用人单位与同一劳动者只能约定一次试用期'


class DraftReview:
    def __init__(self,cases,case_id):
        self.cases=cases;self.case_id=case_id;self.changes=[];self.cache={}

    def sources(self,refs):
        # Validation includes case membership and the current binary digest. Read
        # full sentence context so a quoted substring cannot cut off a negation.
        from source_bound_litigation import _reference, _contextual_quote
        contexts=[]
        for ref in refs or []:
            if not isinstance(ref,dict) or ref.get('status') in ('unverified','unmatched','ambiguous') or ref.get('source_kind') in ('model_draft','inference','draft'):
                continue
            import json
            key=json.dumps(ref,ensure_ascii=False,sort_keys=True)
            if key not in self.cache:
                self.cache[key]=None
                validated=self.cases.validate_citations(self.case_id,[ref])
                if not validated['warnings'] and validated['citations'][0]['status']=='matched':
                    value=validated['citations'][0]
                    strict={k:value[k] for k in ('path','quote','sha256','chunk','start','end') if k in value}
                    try:
                        bound,text=_reference(self.cases,self.case_id,strict,{s['path']:s for s in self.cases.materials(self.case_id)})
                        context,_=_contextual_quote(text,bound['start'],bound['end'])
                        self.cache[key]=context
                    except (ValueError,KeyError):
                        pass
            if self.cache[key]:contexts.append(self.cache[key])
        return contexts

    def text(self,value,label,refs=(),noncompete=False,proposal=False):
        if not isinstance(value,str):return value  # Producer retains its type/size checks.
        contexts=self.sources(refs)
        topics_to_check=dict(TOPICS)
        negative=NEGATIVE
        if noncompete:
            topics_to_check['竞业补偿约定或履行']=r'补偿'
            negative=re.compile(NEGATIVE.pattern+r'|(?:无|未约定|未支付)(?:任何|经济|竞业)?补偿'
                r'|补偿(?:金额|对价|标准|款项)?(?:尚|并|均|仍|亦)?(?:未约定|未支付|未付)')
            if not proposal:
                negative=re.compile(negative.pattern+r'|补偿(?:金额|对价|标准|安排)?(?:空缺|空白|缺位)')
        def change(original,replacement,reason):
            if replacement.endswith('。') and not original.endswith(('。','！','？','\n')):
                replacement=replacement[:-1]
            self.changes.append(dict(label=label,original=original,replacement=replacement,reason=reason,citations=list(refs)))
            return replacement
        if proposal:
            value=ONCE.sub(lambda m:change(m.group(),ONCE_TEXT,'劳动合同法第19条：一次试用限制以同一双方为范围，不仅限本次劳动关系。'),value)
        output=[]
        for sentence in re.findall(r'[^。！？\n]+[。！？\n]?|[。！？\n]',value):
            if CONDITIONAL.search(sentence):output.append(sentence);continue
            pieces=re.split(r'([，,、；;（）()]|但是|但|然而|因此|所以)',sentence)
            for i in range(0,len(pieces),2):
                part=pieces[i]
                if not part or CONDITIONAL.search(part):continue
                # Exact complete sentences remain source statements. A different
                # party or omitted qualifier cannot borrow another sentence's proof.
                exact=any(part.strip('。！？\n ') in [s.strip('。！？\n ') for s in re.findall(r'[^。！？\n]+[。！？\n]?',c)] for c in contexts)
                if exact:continue
                # A negated list keeps its scope over bare comparison labels;
                # an unrelated unknown qualifier must not hide a new assertion.
                if i and pieces[i-1]=='、' and COMPARISON.fullmatch(part.strip('。！？\n ')):
                    prefix=re.split(r'[，,；;。！？\n]',''.join(pieces[:i]))[-1]
                    if re.search(r'不据|不作|不应|不认定|不能|不得',prefix):continue
                comparison_match=COMPARISON.search(part)
                tentative=bool(comparison_match and re.search(r'可能|易被|有被|需评估',part[:comparison_match.start()]))
                generic_condition=bool(re.search(r'均可能|均有.{0,12}风险',sentence) and not re.search(r'本案|本条款|本协议',sentence))
                comparative_condition=tentative or generic_condition or re.search(r'是否|与否|能否|不能|不得|不应|不认定|不据|不足以|不作|(?:'+COMPARISON.pattern+r')(?:的|时)$',part)
                if noncompete and COMPARISON.search(part) and not comparative_condition:
                    pieces[i]=change(part,'竞业范围或违约金的合理性尚需结合适用条件及比较依据判断，不能仅据条款金额或岗位名称下结论。','缺少可核对的比较依据，保留逐项审查和调整建议，不作确定失衡结论。')
                    continue
                if QUALIFIED.search(part):continue
                topics=[name for name,pattern in topics_to_check.items() if re.search(pattern,part)]
                if topics and negative.search(part.replace('无固定期限','固定期限')):
                    names='、'.join(topics)
                    related=[c for c in contexts if any(re.search(topics_to_check[n],c) for n in topics)]
                    confirmed=[s for c in related for s in re.findall(r'[^。！？\n]+[。！？\n]?',c)
                        if any(re.search(topics_to_check[n],s) for n in topics) and negative.search(s)
                        and re.search(r'(?:明确)?确认|法院认定|判决认定|裁决认定',s)
                        and not re.search(r'不能确认|不予确认|未(?:能)?确认|无法确认|是否|未知|待核|未经',s)]
                    if confirmed:
                        # Preserve the actual source's party and qualifier, not the
                        # model's paraphrase. Do not invent a new factual finding.
                        replacement='所引材料明确记载：'+ ' / '.join('“'+s+'”' for s in dict.fromkeys(confirmed))+'。'
                        pieces[i]=change(part,replacement,'保留已明确陈述的否定及其原文主体，未改成未知。')
                        continue
                    evidence=('所引原文：'+ ' / '.join('“'+c+'”' for c in dict.fromkeys(related))+'；') if related else ''
                    pieces[i]=change(part,f'关于{names}：{evidence}实际状态待核，不能把材料未提供推定为事实不存在。','原文未支持该否定事实；仅修正本句，原稿保留供核对。')
            output.append(''.join(pieces))
        return ''.join(output)


def save_review_audit(cases,case_id,changes):
    if not changes:return {}
    from docx import Document
    from io import BytesIO
    from uuid import uuid4
    from docx_delivery import _publish
    import json
    doc=Document();doc.add_heading('劳动审查内部修订记录（勿对外发送）',0)
    doc.add_paragraph('案件：'+case_id+'。以下原稿用于核对，不是最终采用意见。')
    for row in changes:
        doc.add_heading(row['label'],2)
        doc.add_paragraph('原稿（未采用）：'+row['original'])
        doc.add_paragraph('采用文字：'+row['replacement'])
        doc.add_paragraph('原因：'+row['reason'])
        doc.add_paragraph(json.dumps(row['citations'],ensure_ascii=False))
    data=BytesIO();doc.save(data)
    file=_publish(cases.store,'劳动审查-内部核对-'+uuid4().hex[:12]+'.docx',data.getvalue())
    return dict(internal_path=file['path'],internal_sha256=file['sha256'])
