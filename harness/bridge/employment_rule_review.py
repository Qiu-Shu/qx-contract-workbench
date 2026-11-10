"""Program-owned probation-pay opinion from labeled, case-bound operands."""
import re
from decimal import Decimal
from source_bound_litigation import _money
from employment_parameter_extraction import PATTERNS
from employment_term_scenarios import compare_term_scenario
from material_scan import source_warnings

FIELDS=('contract_pay','grade_pay','minimum_pay','probation_pay')
BASIS=('劳动合同法第20条、劳动合同法实施条例第15条：分别核同岗最低档工资80%与合同约定工资80%，'
       '并核适用最低工资；不把同岗最低档工资全额误写成唯一法定下限。'
       ' https://www.mohrss.gov.cn/xxgk2020/fdzdgknr/zcfg/fg/202011/t20201103_394939_wap.html')


def prepare_probation_pay(cases,case_id,item,index):
    params=item.get('parameters',{});contexts={};refs=[];values={};comparison=None;error=''
    try:
        if not isinstance(params,dict) or set(params)!=set(FIELDS):
            raise ValueError('需分别绑定合同工资、同岗最低档工资、适用最低工资和试用工资四项原文金额；缺值不补零。')
        sources={s['path']:s for s in cases.materials(case_id)}
        for key in FIELDS:
            value,binding=_money(cases,case_id,params[key],sources,contexts)
            ref=binding['citation'];source=contexts[(ref['path'],ref['sha256'],ref['chunk'])]
            matches=list(PATTERNS[key].finditer(source['text']))
            if len(matches)!=1 or not (ref['start']<=matches[0].start()<=binding['amount_start']<binding['amount_end']<=matches[0].end()<=ref['end']):
                raise ValueError('金额未绑定唯一且完整的对应工资标签，或存在多个值；请回读，不由模型改写来源。')
            match=matches[0]
            prefix=re.split('[，,、；;。\n]',source['text'][:match.start()])[-1]
            suffix=re.split('[，,、；;。\n]',source['text'][match.end():])[0]
            if re.search('不|未|非|否认|未知|待核|或',prefix+suffix) or source_warnings(source):
                raise ValueError('对应工资字段有否定、未定或来源识别疑点，仅本项待核。')
            values[key]=format(value,'f');refs.append(params[key]['citation'])
        if len(contexts)!=1:raise ValueError('四个工资口径须来自同一完整来源片段；本分支不跨人或文件拼接。')
        formula=f'试用工资假设：合同工资{values["contract_pay"]}元，同岗最低档工资{values["grade_pay"]}元，适用最低工资{values["minimum_pay"]}元，拟试用工资{values["probation_pay"]}元。'
        comparison=compare_term_scenario('hiring',formula,formula,0,len(formula))
    except (ValueError,TypeError,KeyError) as exc:
        error=str(exc);refs=[]
    if comparison:
        candidate=max(Decimal(comparison['contract_floor']),Decimal(comparison['grade_floor']))
        risk=comparison['text']
        action=(f'候选修改：试用期月工资拟约定为{candidate:.2f}元，具体构成和支付周期另核。'
                '取两种比较口径中较高值是拟议方案，不是全国统一强制选择；不擅自改变合同期限。'
                '实际履行月数及合法试用期限未核，不计算整段欠薪。')
        fact='来源原文（主体、工资口径及适用关系待核）：\n'+next(iter(contexts.values()))['text']
    else:
        fact='本项参数未完成来源绑定，不采用模型自填的工资事实或算式。'
        risk='本项待核：'+error
        action='回读四项带标签的原文金额后核算；其他已经明确的审查事项继续保存。'
    # Caller prose remains in the tool-call audit; it cannot override this rule's saved opinion.
    prepared=dict(topic='试用工资｜程序规则核验',fact=fact,basis=BASIS,source='本案来源绑定参数；适用关系尚待核实',
                  risk=risk,action=action,pending='工资构成、适用地区和时期、实际履行月数另核；不据拟定标准认定应付款。',
                  citations=list({str(r):r for r in refs}.values()))
    return prepared,{'finding_index':index,'rule':'probation_pay','comparison':comparison,'pending_reason':error,'prepared_finding':prepared}


def prepare_noncompete_comparison(cases,case_id,item,index):
    """Record each bound operand independently; a ratio is not an excessiveness test."""
    from source_bound_litigation import _number, _reference
    labels={'penalty':r'(?:约定)?违约金','loss':r'(?:(?:已查明|实际|确认)的?)?损失',
            'monthly_compensation':r'(?:每月|月|按月)(?:经济)?补偿(?:金)?',
            'monthly_pay':r'(?:每月|月)(?:工资|薪酬)'}
    params=item.get('parameters',{})
    if not isinstance(params,dict) or set(params)-set(labels):raise ValueError('竞业比较参数仅支持penalty/loss/monthly_compensation/monthly_pay。')
    sources={s['path']:s for s in cases.materials(case_id)}
    values={};bound_refs={};groups={};pending={};positions={};prefixes={};owners={}
    for key,pattern in labels.items():
        if key not in params:pending[key]='未提供，不补零';continue
        try:
            contexts={}
            operand=params[key]
            if not isinstance(operand,dict) or set(operand)!={'amount','citation'} or not isinstance(operand['amount'],str):
                raise ValueError('金额参数须含完整amount及citation')
            original_ref,text=_reference(cases,case_id,operand['citation'],sources,contexts)
            labeled=list(re.finditer(pattern+r'\s*(?:为|：|:)?\s*'+re.escape(operand['amount']),text))
            if len(labeled)!=1 or not (original_ref['start']<=labeled[0].start()<labeled[0].end()<=original_ref['end']):
                raise ValueError('金额未绑定唯一对应标签，不跨字段代用')
            match=labeled[0]
            # Bind the unique labeled occurrence, not another mention of the same
            # numeral in instructions. _money still validates the full numeric token
            # against the original context, including signs and digit boundaries.
            narrowed={k:original_ref[k] for k in ('path','sha256','chunk')}
            narrowed.update(quote=match.group(),start=match.start(),end=match.end())
            value,binding=_money(cases,case_id,dict(amount=operand['amount'],citation=narrowed),sources,contexts)
            ref=binding['citation'];source=next(iter(contexts.values()))
            text=source['text'];matches=list(re.finditer(pattern+r'\s*(?:为|：|:)?\s*'+re.escape(binding['amount']),text))
            if len(matches)!=1 or not(ref['start']<=matches[0].start()<binding['amount_end']==matches[0].end()<=ref['end']):
                raise ValueError('金额未绑定唯一对应标签，不跨字段代用')
            before=re.split('[，,；;。\n]',text[:matches[0].start()])[-1]
            after=re.split('[，,；;。\n]',text[matches[0].end():])[0]
            if re.search('不|未|未知|待核|可能|或',before+after) or source_warnings(source):
                raise ValueError('金额状态或识别有疑点')
            values[key]=value;bound_refs[key]=ref
            record_start=max(text.rfind(mark,0,matches[0].start()) for mark in ('。','；',';','\n'))+1
            groups[key]=(ref['path'],ref['sha256'],ref['chunk'],record_start)
            positions[key]=matches[0].start();prefixes[key]=before.strip(' ：:的')
        except (ValueError,TypeError,KeyError) as exc:pending[key]=str(exc)
    for group in set(groups.values()):
        owner=''
        for key in sorted((k for k in groups if groups[k]==group),key=positions.get):
            if prefixes[key]:owner=prefixes[key]
            owners[key]=owner
    comparison={key+'_yuan':_number(values[key]) if key in values else None for key in labels}
    for key in ('loss','monthly_compensation','monthly_pay'):
        ratio=None
        if 'penalty' in values and key in values:
            if groups['penalty']!=groups[key] or owners['penalty']!=owners[key]:pending[key]='保留各自金额，但记录或主体前缀不同，未确认同一比较对象，不拼接比值'
            elif values[key]>0:ratio=_number((values['penalty']/values[key]).quantize(Decimal('0.0001')))
            else:pending[key]='已知为零，保留该值但不作除数'
        comparison['penalty_to_'+key]=ratio
    names={'penalty':'约定违约金','loss':'损失','monthly_compensation':'月补偿','monthly_pay':'月工资'}
    facts='以下为所选来源各自数值，不因并列认定同一比较对象：'+ '；'.join(names[k]+'：'+(_number(values[k])+'元（仅来源记载）' if k in values else '待核') for k in labels)
    ratios='；'.join('违约金/'+names[k]+'='+str(comparison['penalty_to_'+k]) for k in ('loss','monthly_compensation','monthly_pay') if comparison['penalty_to_'+k] is not None)
    prepared=dict(topic='竞业比较依据与条件',fact=facts,
        basis='劳动合同法第23、24条及劳动争议司法解释（二）第13条：人员、秘密接触、约定范围和期限需结合适用条件分别审查；比例不是法定统一阈值。 https://www.court.gov.cn/fabu/xiangqing/472691.html',
        source='本案逐项来源绑定参数，陈述真实性及适用关系另核',
        risk=(ratios+'。' if ratios else '')+'仅展示可核对的金额和算术，不据比例自动认定过高、失衡、有效或无效；缺失值不阻止其他明确项目。',
        action='候选修改：明确受保护秘密、竞争业务和地域、离职后期限、补偿标准与支付周期；对违约金结合有效义务、违约行为、损失及公平因素评估调整主张，不仅凭违约金绝对金额或岗位名称给结论。',
        pending='；'.join(names[k]+'：'+v for k,v in pending.items()) or '比较对象归属、事实真实性、因果关系及适用规则另核',
        citations=list(bound_refs.values()))
    return prepared,dict(finding_index=index,rule='noncompete_comparison',comparison=comparison,pending_fields=pending,prepared_finding=prepared,
        bindings={k:dict(citation=bound_refs[k],context_prefix=owners[k],record_start=groups[k][-1]) for k in values})


def review_compensation_conditions(item,review,index):
    """Keep compensation facts as bound source statements, separate from legal conditions."""
    item=_condition_compensation_action(item,review,index)
    topic=item.get('topic','')
    if (not isinstance(topic,str) or '补偿' not in topic or re.search(r'违约金|损失|比值|金额比较',topic)
            or any(not isinstance(item.get(k),str) for k in ('fact','basis','source','risk','action'))):
        return item
    item=dict(item)
    def replace(field,text):
        old=item.get(field)
        if not isinstance(old,str) or old==text:return
        review.changes.append(dict(label=f'第{index}项{field}',original=old,replacement=text,
            reason='补偿事实直接保留匹配原文，未记载不等于未约定；程序另列在职、离职后有约定/无约定的适用条件。',citations=item.get('citations',[])))
        item[field]=text
    contexts=list(dict.fromkeys(review.sources(item.get('citations',[]))))
    quoted='\n'.join('“'+text+'”' for text in contexts)
    replace('topic','竞业补偿约定与履行｜来源核对')
    replace('fact',('本案匹配原文（保持原文的陈述主体与状态，不作事实认证）：\n'+quoted if len(quoted)<=16000 else
        '匹配原文较长，完整内容见本项保留的原始引用；仅据原文区分已约定、已履行与未知，不由缺材料推断不存在。') if contexts else
        '本项尚无可匹配的原文，约定及履行状态未核；不根据模型改写认定未约定或未支付。')
    replace('source','本案已匹配引用，路径、版本与片段号见本项原始引用输入；匹配不证明事实真实。' if contexts else '来源状态待核，未使用模型补入事实。')
    replace('basis','劳动争议解释（一）第36条适用于约定竞业限制但未约定离职后经济补偿、且劳动者履行义务的情形：按离职前十二个月平均工资30%按月给付，低于劳动合同履行地最低工资时按该最低工资。已明确约定补偿的，不能直接用此补充规则认定约定金额不足或自动补差，须另核约定效力、地方规则及履行。在职限制另按解释（二）第14条等适用，不自动套离职后补偿规则。 https://www.court.gov.cn/zixun/xiangqing/282121.html https://www.court.gov.cn/fabu/xiangqing/472691.html')
    replace('risk','先核是否已有明确补偿约定及适用规则；未提供约定文本不等于没有约定。已约定金额是否足额、支付是否逾期或不足，应结合有效约定、适用地方规则与实际支付记录核对，不自动按30%补差。')
    return item


def _condition_compensation_action(item,review,index):
    """Condition only compensation instructions, including inside mixed findings."""
    action=item.get('action')
    if not isinstance(action,str):return item
    replacement='标准先按有效约定及适用规则核对；如果未约定补偿且履行义务，则按解释（一）第36条确定'
    revised=re.sub(r'标准不低于法定下限即[^）)；;。\n]+',replacement,action)
    parts=re.split(r'([。！？\n；;]|[①②③④⑤⑥⑦⑧⑨⑩])',revised)
    for i in range(0,len(parts),2):
        part=parts[i]
        if re.search(r'30\s*[%％]|百分之三十|按法定标准补差|按上述下限|按以上(?:标准|下限)',part) and not re.search(r'未约定|建议|拟|候选|不能|不自动',part):
            parts[i]='如果未约定补偿且满足相应履行条件，则按适用规则核算；已约定金额不能自动按30%补差'
    revised=''.join(parts)
    if revised==action:return item
    item=dict(item,action=revised)
    review.changes.append(dict(label=f'第{index}项action',original=action,replacement=revised,
        reason='补偿补充规则须满足适用条件；局部修正补偿指令，保留混合事项中的其他行动。',citations=item.get('citations',[])))
    return item
