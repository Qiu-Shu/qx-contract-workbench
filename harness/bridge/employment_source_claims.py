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

# shortcut: this is a bounded attribution grammar, not general entailment;
# unsupported sentence structures require new counterexamples before extension.
ATTRIBUTION=re.compile(
    r'(?:员工|劳动者|用人单位|公司|单位|主管|HR|人事|人力资源部|甲方|乙方|双方|证人)'
    r'(?:[甲乙丙丁A-Z]|[“「][^”」]{1,12}[”」])?(?:本人)?'
    r'(?:(?:已经|已|曾|明确|书面|口头)|向[^，,；;。！？\n]{1,12}){0,2}'
    r'(?P<verb>自述|自称|陈述|声称|表示|承认|否认|告知|确认|说明|反映|证实|称)')
ATTRIBUTION_REQUEST=re.compile(
    r'^\s*(?:并|同时|再)?(?:请|应|建议|需|待|拟|要求|核对|核实|询问|调取|收集|补充)')
ATTRIBUTION_QUALIFIER=re.compile(
    r'不能|不得|不应|不要|不认定|不据|不等于|不代表|不足以|避免|是否|与否|未能确认|无法确认|尚无材料证明|不写入|不代')
ATTRIBUTION_NOUN=re.compile(
    r'^(?:(?:的)?(?:证明力|真实性|可信度)|的(?:内容|说法|范围|含义)(?:仍|尚)?(?:需|应|须|待|是否|与否)'
    r'|不足以|不能|应|需|并列|冲突|[、）)])')
INDEPENDENT_ANALYSIS=re.compile(
    r'^\s*(?:也|仍|尚|还|且|并|再)?(?:不能|不得|不应|不要|不足以|应|须|需|请|建议|是否|若|如|待核|核对|核实|收集|补充)'
    r'|不足以|不代表|不等于|不意味着|难以(?:证明|认定|判断|确认)'
    r'|(?:效力|证明力|真实性|适格|事实基础|适用条件)[^，,；;。！？\n]{0,12}(?:需|不足|取决|待核|无法|不能|是否)')


def bind_source_attribution(item, contexts, review, index):
    """Normalize identified attribution restatements; keep independent analysis."""
    sourced={s.strip('。！？\n ') for c in contexts
             for s in re.findall(r'[^。！？\n]+[。！？\n]?',c)}
    replacement=('本项来源陈述以所引原文为准' if contexts
                 else '该陈述的来源归属尚无已匹配原文支持')
    item=dict(item)
    for field in ('topic','basis','risk','action','pending'):
        value=item.get(field)
        if not isinstance(value,str):continue
        output=[]
        for sentence in re.findall(r'[^。！？\n]+[。！？\n]?|[。！？\n]',value):
            # Only a complete sourced sentence may retain its speaker and scope.
            # An unrelated attribution or a substring after a negation is not proof.
            if sentence.strip('。！？\n ') in sourced or CONDITIONAL.search(sentence):
                output.append(sentence);continue
            pieces=re.split(r'([，,；;]|但是|但|然而|因此|所以|却|而且)',sentence)
            reported_scope=False
            for n in range(0,len(pieces),2):
                part=pieces[n]
                # Preserve independent reasoning; a multi-clause reported payload
                # must not survive as bare facts after its unsupported speaker is removed.
                if reported_scope:
                    if INDEPENDENT_ANALYSIS.search(part):
                        reported_scope=False
                    else:
                        punctuation=re.search(r'[。！？\n]+$',part)
                        pieces[n-1]=''
                        pieces[n]=punctuation.group() if punctuation else ''
                        continue
                match=ATTRIBUTION.search(part)
                if not match:continue
                prefix=part[:match.start()]
                tail=part[match.end():]
                if (CONDITIONAL.search(part) or ATTRIBUTION_REQUEST.match(prefix)
                        or ATTRIBUTION_QUALIFIER.search(prefix)
                        or re.match(r'^[:：]?(?:是否|与否)',tail)
                        or (match.group('verb') in ('自述','陈述','说明') and ATTRIBUTION_NOUN.match(tail))):
                    continue
                # A bare noun (e.g. a requested list of statements) has no asserted
                # payload. "据某方陈述" explicitly introduces reported content.
                if not tail.strip('。！？\n ') and not re.search(r'据|按照|依照',prefix):continue
                punctuation=re.search(r'[。！？\n]+$',part)
                pieces[n]=replacement+(punctuation.group() if punctuation else '')
                reported_scope=True
            output.append(''.join(pieces))
        updated=''.join(output)
        if updated!=value:
            review.changes.append(dict(label=f'第{index}项{field}',original=value,replacement=updated,
                reason='该处来源归属复述未按完整原句绑定，改为指回本项来源；保留独立分析，原稿供内部核对。',
                citations=item.get('citations',[])))
            item[field]=updated
    return item


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
            parts=re.split(r'([，,；;]|但是|但|然而|因此|所以|却|而且)',sentence)
            reported_scope=False
            for n in range(0,len(parts),2):
                part=parts[n]
                if reported_scope:
                    if INDEPENDENT_ANALYSIS.search(part):
                        reported_scope=False
                    else:
                        punctuation=re.search(r'[。！？\n]+$',part)
                        parts[n-1]=''
                        parts[n]=punctuation.group() if punctuation else ''
                        continue
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
                subject=('陈述媒介及内容' if match.group().startswith(('口头','口述')) else
                         '考勤具体内容及违纪判断')
                punctuation=re.search(r'[。！？\n]+$',part)
                parts[n]='本项'+subject+('以所引原文为准' if contexts else '尚无已匹配原文支持')+(punctuation.group() if punctuation else '')
                reported_scope=True
            sentences[i]=''.join(parts)
        replace(field,''.join(sentences),'所引完整原句不支持该媒介、考勤内容或违纪认定；保留来源陈述供核对。')
    return item,observation
