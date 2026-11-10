"""Finite remedy branches and conditional date arithmetic, never a legal deadline."""
import re
from datetime import date,timedelta

BRANCHES={
 ('civil_judgment','party'):('appeal',15,'普通可上诉的一审判决：向上一级人民法院上诉，原则上通过原审法院提出。民诉法第171至173条。'),
 ('civil_order','party'):('appeal',10,'可上诉的一审裁定：核限于法定可上诉类型，再核上一级人民法院及提交路径。民诉法第157、171至173条。'),
 ('labor_final','worker'):('sue',15,'劳动者不服终局裁决：核向人民法院起诉的路径。劳动争议调解仲裁法第48条。'),
 ('labor_final','employer'):('set_aside',30,'用人单位不服终局裁决：核第49条法定撤销事由及仲裁委员会所在地中级人民法院；不是普通起诉或上诉路径。'),
 ('labor_nonfinal','worker'):('sue',15,'劳动者不服非终局裁决：核向人民法院起诉的路径。劳动争议调解仲裁法第50条。'),
 ('labor_nonfinal','employer'):('sue',15,'用人单位不服非终局裁决：核向人民法院起诉的路径。劳动争议调解仲裁法第50条。'),
 ('labor_mixed','worker'):('sue',15,'劳动者不服同一份混合事项裁决：如第20条条件适用，按非终局裁决核起诉路径及劳动争议调解仲裁法第50条期间。'),
 ('labor_mixed','employer'):('sue',15,'用人单位不服同一份混合事项裁决：如第20条条件适用，按非终局裁决核起诉路径及劳动争议调解仲裁法第50条期间。')}
SPECIAL=re.compile(r'小额|一审终审|特别程序|再审|涉外|境外|公告|混合裁决|部分终局|送达.{0,8}争议|未收到|未送达|未签收|不是|并非|不属于|是否|待核|未知|尚未确定')
UNCERTAIN=re.compile(r'假设|可能|预计|预期|暂定|未载明|未确认|无法确认|不明|否认|待确认|拟作|模板|样例|更正|改为|不属实|非按照')
DATE=re.compile(r'(?:^|[\r\n；;。])\s*(?:收到日期|送达日期|签收日期)\s*[:：]\s*(\d{4}-\d{2}-\d{2})(?=\s*(?:$|[\r\n；;。]))')
CIVIL_SOURCE='https://ipc.court.gov.cn/zh-cn/news/view-6231.html'
CIVIL_INTERPRETATION='https://www.court.gov.cn/zixun/xiangqing/353651.html'
LABOR_INTERPRETATION='https://rsj.wuhan.gov.cn/zwgk_17/zc/qtzdgkwj/zcfg/202204/t20220427_1963228.html'
FOREIGN_APPELLANT=re.compile(r'(?<!被)上诉人在中华人民共和国领域内(?:没有|无)住所')
MIXED_AWARD=re.compile(r'同一(?:份)?仲裁裁决[，,\s]*(?:该裁决)?同时(?:包含|涉及)终局裁决事项和非终局裁决事项')
FIRST_RETRIAL=re.compile(r'按照第?一审程序(?:审理并)?作出的再审判决')
ACTOR_STATEMENT=re.compile(r'(?:^|[。；;，,\r\n:：])\s*(劳动者|用人单位)(?:也|亦)?'
    r'(?:对(?:该)?(?:终局|非终局)?裁决不服|不服(?:该)?(?:终局|非终局)?裁决)(?=\s*(?:[。；;，,\r\n]|$))')


def _labels(text,label):
    return re.findall(r'(?:^|[\r\n；;。，,:：])\s*(?:'+label+r')\s*[:：]\s*([^\r\n；;。，,]+)',text)


def prepare_remedy(raw,route,bind):
    from source_bound_litigation import _shape,_list
    _shape(raw,('decision_kind','actor','classification_citations'),('service_citation',))
    kind,actor=raw['decision_kind'],raw['actor']
    kinds={'civil_appeal':('civil_judgment','civil_order','unknown'),
           'labor_award_remedy':('labor_final','labor_nonfinal','labor_mixed','unknown')}
    if route not in kinds:
        raise ValueError('remedy救济核查仅支持civil_appeal或labor_award_remedy路线。'
                         '劳动裁决救济请将legal_review.procedure.route改为labor_award_remedy；'
                         '主体或性质不明可填unknown，保留冲突来源，不要删除remedy绕过核查。')
    if kind not in kinds[route] or actor not in ('party','worker','employer','unknown'):
        raise ValueError('救济分类不适用于所选程序路线。')
    if kind!='unknown' and actor!='unknown' and (kind,actor) not in BRANCHES:raise ValueError('救济主体与文书类型不匹配。')
    refs=[bind(r,True) for r in _list(raw['classification_citations'],'分类来源',10)]
    service=bind(raw['service_citation'],True) if raw.get('service_citation') is not None else None
    texts=list(dict.fromkeys(r['context'] for r in refs));joined='\n'.join(texts)
    warnings=[];action=None;days=None;point=None;guidance=[];sources=[]
    classification=joined
    # shortcut: recognize only explicit source phrases, not arbitrary procedural narratives.
    foreign=bool(FOREIGN_APPELLANT.search(joined)) and not re.search(r'(?:中国境内|中华人民共和国领域内)(?:有|具有)住所',joined)
    mixed=bool(MIXED_AWARD.search(joined)) and not re.search(r'分别|另[一有份]|两份|不同裁决',joined)
    retrial=bool(FIRST_RETRIAL.search(joined)) and not re.search(r'小额|第二审|二审|提审|一审终审',joined)
    parallel=route=='labor_award_remedy' and kind=='labor_final' and actor=='employer' and bool(
        re.search(r'劳动者已(?:经)?[^。；;\n]{0,35}(?:起诉|提起诉讼)',joined))
    if route=='civil_appeal':
        sources.append(CIVIL_SOURCE)
        if re.search(r'涉外|境外|住所|外国',joined):
            guidance.append('涉外上诉须按上诉人本人的住所核查；民诉法第286条的30日规则针对在中华人民共和国领域内没有住所的当事人，不能仅凭外籍、对方住所或案件涉外判断。延期须经法院决定。')
        if '小额' in joined:
            sources.append(CIVIL_INTERPRETATION)
            guidance.append('小额诉讼核查：民诉法第165条规定一审终审；可依民诉法解释第424条向原审人民法院申请再审核查。因法定再审事由作出的再审裁判与因不应按小额诉讼审理而再审作出的裁判，上诉可能性不同。须核申请事由和裁判全文；不能从本次收到日直接计算再审期限。')
        elif '再审' in joined:
            guidance.append('再审裁判核查：民诉法第218条区分按照第一审程序作出的再审裁判与按第二审程序或上级法院提审作出的裁判；前者才进入可上诉性核查。申请再审本身的期间另按第216条核生效日及特定事由知悉日，不能套收到日加15日。')
        if foreign:
            classification=FOREIGN_APPELLANT.sub('',classification).replace('涉外','')
        if retrial and kind=='civil_judgment':classification=FIRST_RETRIAL.sub('一审判决',classification)
    else:
        if parallel:
            sources.append(LABOR_INTERPRETATION)
            guidance.append('并行救济核查：劳动争议司法解释（一）第21条规定，劳动者就终局裁决向基层法院起诉时，中级法院对单位撤销申请不予受理，已受理的驳回申请；劳动者撤诉或被驳回起诉后的撤销申请期间须另核相关裁定及收到日。本次不沿用原裁决收到日计算。')
        if re.search(r'终局裁决.*非终局裁决|混合裁决',joined,re.S):
            sources.append(LABOR_INTERPRETATION)
            guidance.append('劳动争议司法解释（一）第20条：同一仲裁裁决同时含终局与非终局事项时，诉讼按非终局裁决处理；分别作出的多份裁决须逐份核查，不能合并成同一裁决。')
        if mixed and kind in ('labor_nonfinal','labor_mixed'):classification=MIXED_AWARD.sub('非终局裁决',classification)
    labels=list(dict.fromkeys(value.strip() for value in _labels(joined,'救济主体')))
    stated_actors=set(ACTOR_STATEMENT.findall(joined))
    expected={'worker':'劳动者','employer':'用人单位'}.get(actor)
    actor_ok=(not labels or (len(labels)==1 and labels[0] in (
        (expected,) if expected else ('当事人','原告','被告','上诉人'))))
    if expected:
        actor_ok=actor_ok and expected in joined
        if stated_actors:actor_ok=actor_ok and stated_actors=={expected}
        if '劳动者' in joined and '用人单位' in joined:
            actor_ok=actor_ok and (labels==[expected] or stated_actors=={expected})
    if kind=='unknown' or actor=='unknown' or not refs:warnings.append('文书类型、救济主体或分类来源未完整确定，未选择期限分支。')
    elif (SPECIAL.search(classification) or UNCERTAIN.search(joined) or parallel or
          (route=='civil_appeal' and re.search(r'第二审|二审|终审|最高人民法院|已生效|已经生效|被撤销',classification)) or
          re.search(r'没有住所|无住所|外国|域外|国外',classification)):
        warnings.append('分类上下文含未解析的特殊程序、否定或未定信息，不能套用救济期限。')
    else:
        matches={
          'civil_judgment':bool(re.search(r'(?:第一审|一审)判决',classification)),
          'civil_order':bool(re.search(r'(?:第一审|一审)(?:民事)?(?:(?:不予受理|管辖权异议|驳回起诉)裁定|裁定\s*[:：]?\s*(?:不予受理|管辖权异议|驳回起诉))',classification)),
          'labor_final':bool(re.search(r'(?<!非)终局裁决',classification)) and '非终局裁决' not in classification,
          'labor_nonfinal':'非终局裁决' in classification and not bool(re.search(r'(?<!非)终局裁决',classification)),
          'labor_mixed':mixed and '非终局裁决' in classification and not bool(re.search(r'(?<!非)终局裁决',classification))}
        other_civil=(bool(re.search(r'(?:第一审|一审).{0,12}裁定',classification)) if kind=='civil_judgment' else matches['civil_judgment'] if kind=='civil_order' else False)
        if not matches[kind] or other_civil or not actor_ok:warnings.append('原文不能唯一支持所选文书类型或主体，未套用该分支。')
        else:
            action,days,_=BRANCHES[(kind,actor)]
            if foreign and route=='civil_appeal':days=30
    if service is None:warnings.append('缺少收到/送达来源，不能从作出日或发出日推算。')
    elif days is not None:
        context=service['context'];matches=list(DATE.finditer(context))
        all_dates=re.findall(r'\d{4}[-年/]\d{1,2}[-月/]\d{1,2}|(?<!\d)\d{1,2}月\d{1,2}日',context)
        recipients=_labels(context,'受送达人|送达对象|收件人|签收人')
        recipient_labels=re.findall(r'(?:受送达人|送达对象|收件人|签收人)\s*[:：]',context)
        recipient_ok=len(recipient_labels)==len(recipients) and (not recipients or (
            len(recipients)==1 and recipients[0]==(labels[0] if len(labels)==1 else expected)))
        if not recipient_ok:
            warnings.append('送达材料所列主体与救济主体不一致或无法对应，未计算日期参考点。')
        elif SPECIAL.search(context) or UNCERTAIN.search(context) or re.search(r'或|争议|不认可',context) or len(matches)!=1 or len(all_dates)!=1:
            warnings.append('送达片段不是唯一明确收到日期，或含争议/特殊方式，未计算日期参考点。')
        else:
            try:
                start=date.fromisoformat(matches[0][1]);end=start+timedelta(days=days)
                point={'service_date_candidate':start.isoformat(),'days':days,'date':end.isoformat(),
                       'excluded_start_day':True,'holiday_adjusted':False,'legal_deadline':None,
                       'recipient_verified':False,'source':service,'start':matches[0].start(1),'end':matches[0].end(1)}
            except (ValueError,OverflowError):warnings.append('收到日期无效或超范围，未计算日期参考点。')
    lines=['复杂程序救济核查（所选类型和主体仍待律师核实）']
    lines.extend(guidance)
    if days is not None:
        rule=('民诉法第286条：上诉人在中华人民共和国领域内没有住所的条件分支；仍须核本人住所和可上诉性。' if foreign and route=='civil_appeal' else BRANCHES[(kind,actor)][2])
        lines.extend([rule,f'如所选分支确实适用，法定日数候选为{days}日；不等于已确认本案期间。'])
    else:lines.append('尚未确定可适用的救济路径和日数；应分别核文书类型、主体、法定例外及并行救济。')
    if point:
        lines.append(f'条件算术参考：以{point["service_date_candidate"]}为收到日期候选，起算日不计入，加{days}日得到{point["date"]}。这是未处理法定休假日的算术参考点，不是法定届满日；受送达人、送达效力、特殊期间、顺延和在途规则仍须核实。')
    lines.extend('暂停或待补：'+w for w in warnings)
    lines.extend('法源：'+source for source in sources)
    lines.append('程序分支不证明受理条件满足；不自动认定救济获支持或已逾期。')
    return {'decision_kind':kind,'actor':actor,'classification_citations':refs,'service_citation':service,
            'candidate_action':action,'days':days,'calendar_reference':point,'warnings':warnings,
            'official_sources':sources,'legal_deadline':None,'classification_verified':False,'text':'\n'.join(lines)}
