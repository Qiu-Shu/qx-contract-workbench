"""Keep cited facts verbatim; bound checks are not a general entailment engine."""
import re
from draft_review import CONDITIONAL

CLAIM=re.compile(r'口头|口述|考勤.{0,12}(?:显示|证明(?!力)|记载|反映)|(?:存在|构成|属于)严重违纪')
CLAIM_QUALIFIER=re.compile(r'不要|不能|不得|不应|不作|不认定|不据|不等于|不代表|不足以|避免|是否|与否|未能确认|无法确认|尚无材料证明')
REQUEST=re.compile(r'^\s*(?:[一二三四五六七八九十\d]+[、.．]\s*)?'
    r'(?:请|应|建议|需|待|进一步|同时|并|再|拟)?(?:向[^，,；;。\n已曾了过]{1,30})?'
    r'(?:核对|核实|收集|补充|提供|查证|询问)(?!了|过|后|完|清楚|并确认|并发现|并查明)')
MEDIUM_QUESTION=re.compile(r'^\s*(?:口头(?:同意|通知|陈述)|口述(?:内容|陈述))(?:是否|能否|与否)')
EXPLICIT_REQUEST=re.compile(r'^\s*(?:请|应|建议|需|待|拟)')
DIRECT_REQUEST=re.compile(r'^\s*(?:请|应|建议|需|待|进一步)?(?:核对|核实|收集|补充|提供)')


def bind_source_facts(item, review, index):
    refs=item.get('citations',[])
    contexts=list(dict.fromkeys(review.sources(refs))) if isinstance(refs,list) else []
    observation=dict(finding_index=index-1,status='source_statement' if contexts else 'unbound',contexts=contexts)
    item=dict(item)

    def replace(field, value, reason):
        old=item.get(field)
        if not isinstance(old,str) or old==value:return
        review.changes.append(dict(label=f'第{index}项{field}',original=old,replacement=value,
                                   reason=reason,citations=refs))
        item[field]=value

    if contexts:
        # Source attribution, persons, periods, units and unknown states travel
        # together. Do not ask the model to supply a second, supposedly verified fact.
        replace('fact','本项来源陈述（保持原文，引用匹配不证明真实）：\n'+'\n'.join(contexts),
                '事实栏使用匹配原句及其上下文，避免改写主体、单位、材料内容或陈述媒介。')
        replace('source','本案已匹配原始材料引文；路径、版本及片段见本项引用；陈述媒介仅以原文为准。',
                '来源由本案引用校验确定，不采用模型自填的口头/书面归类。')
    elif re.search(r'(?:工资|薪酬|年薪|月薪)[^。；\n]{0,24}\d+\s*元',str(item.get('fact',''))):
        replace('fact','本项工资陈述尚无匹配原文，金额、人员和工资周期暂不作为已绑定事实；请补本案原始引用。',
                '未绑定来源的金额不能靠模型自填事实或覆盖说明获得工资周期。')

    # Keep these claims out of the opinion fields too. A broad citation or an
    # unrelated "待核" does not establish attendance content or statement medium.
    source_sentences={s.strip('。！？\n ') for c in contexts for s in re.findall(r'[^。！？\n]+[。！？\n]?',c)}
    for field in ('topic','risk','action','pending','basis') + (() if contexts else ('fact','source')):
        value=item.get(field)
        if not isinstance(value,str):continue
        sentences=re.findall(r'[^。！？\n]+[。！？\n]?|[。！？\n]',value)
        for i,sentence in enumerate(sentences):
            if sentence.strip('。！？\n ') in source_sentences or CONDITIONAL.search(sentence):continue
            parts=re.split(r'[，,；;]|但是|但|然而|因此|所以|却|而且',sentence)
            unsupported=False
            for part in parts:
                match=CLAIM.search(part)
                if not match:continue
                prefix=part[:match.start()]
                if (CLAIM_QUALIFIER.search(prefix) or CONDITIONAL.search(part)
                        or re.fullmatch(r'考勤.{0,8}(?:是否|能否).{0,2}(?:显示|证明|记载|反映)',match.group())
                        or MEDIUM_QUESTION.match(part)
                        or DIRECT_REQUEST.match(prefix)
                        # Newly supported directed questions require an explicit
                        # request/plan, not a bare description of an investigation.
                        or ((EXPLICIT_REQUEST.match(prefix) or EXPLICIT_REQUEST.match(sentence))
                            and REQUEST.match(prefix))):
                    continue
                unsupported=True
            if unsupported:
                sentences[i]='本项陈述媒介、考勤具体内容及违纪判断尚需原文和适用条件支持，当前不作确定认定。'
        replace(field,''.join(sentences),'所引完整原句不支持该媒介、考勤内容或违纪认定；保留来源陈述供核对。')
    return item,observation
