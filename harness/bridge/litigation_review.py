"""Finite claim/procedure workpapers with evidence coverage, not legal findings."""
CIVIL_CODE='https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/bgt/art/2023/art_60fb3863b7364b759123a42d1df568ca.html'
CIVIL_PROCEDURE='https://ipc.court.gov.cn/zh-cn/news/view-6231.html'
LABOR_PROCEDURE='https://www.beijing.gov.cn/zhengce/zhengcefagui/qtwj/201912/t20191219_1307906.html'
BASES={
 'service_fee':('服务报酬待核路径','民法典第467、509、577、579条；具体合同类型另核',{
  'agreement':'核合同主体、服务内容、计价及合同性质；服务名称不能替代委托、承揽、技术服务等具体规则。',
  'performance':'核已提供服务的范围、阶段成果、验收或确认及相反材料；部分履行不自动等于全部完成。',
  'due':'核付款条件、期限、验收与催告约定；发票、交付或签约日期不自动作为到期日。',
  'balance':'分列约定报酬、阶段结算、已付、抵扣与争议部分；账面差额不是已认定到期债权。',
  'defenses':'核未履行、质量、履行顺序、抵销及其他抗辩，不把缺材料写成不存在抗辩。'}),
 'sale_price':('买卖价款待核路径','民法典第509、579、595、626、628条',{
  'agreement':'买卖合意、主体、标的及价款约定。',
  'performance':'交付、验收、质量及对待履行义务，不能只凭单方送货表认定完成。',
  'due':'付款条件、期限及催告；不得直接把合同签订日当到期日。',
  'balance':'价款、已付、抵扣与争议扣款分别核；账面差额不等于到期债权。',
  'defenses':'质量、履行顺序、抵销等抗辩及相反材料须回应，不自动接受或排除。'}),
 'private_loan':('借款返还待核路径','民法典第667、675、679、680条',{
  'agreement':'借贷合意和主体；转账本身不能证明借贷关系。',
  'delivery':'实际交付与资金去向；自然人借款成立条件须核。',
  'due':'约定返还期、补充约定及催告条件；未知不直接当到期。',
  'balance':'实际本金、已还、预扣利息与其他款项分别核。',
  'interest':'利息约定及合法范围、适用时点另核，不从本金自动生成利率。'}),
 'unjust_enrichment':('不当得利返还待核路径','民法典第985至988条',{
  'benefit':'得利主体及实际取得利益。',
  'loss':'受损主体、损失及与得利的关联。',
  'no_basis':'有无法律根据；合同争议不自动等于不当得利。',
  'exceptions':'法定例外、知情状态等条件分别核，不默认缺记录即例外不存在。',
  'scope':'现存利益、善恶意及第三人情形影响返还范围，不直接照转账金额判返还。'})}
COMMON={
 'standing':'核主体资格、利害关系、对方身份及请求具体性。',
 'jurisdiction':'核地域、级别、专属或约定管辖及连接点，不凭一处地址指定受理机关。',
 'arbitration':'核仲裁协议原文、争议范围、效力及提出异议的程序，不把有条款直接当排除法院。',
 'limitation':'区分一般与特殊时效，核权利受损知悉、义务人、到期、中断和中止；不得从签约日直接加三年。民法典第188、192至195条。',
 'prior_proceedings':'核已受理、裁判、仲裁及重复起诉；劳动事项还核仲裁前置与法定例外，不因资料未给认定未经历。',
 'service':'核实际送达对象、方式、到达日及相关程序期间，不用发出日自动代替收到日。',
 'authority':'核代理权限、签署及当事人确认；缺选入授权材料不等于现实未授权。'}
LABOR={
 'scope':'核劳动争议受案范围、劳动关系与当事人；不能仅凭工资字样认定劳动关系。',
 'jurisdiction':'核履行地、用人单位所在地及并行申请，按劳动争议仲裁管辖规则另核。',
 'limitation':'一般仲裁时效一年，核知悉起点、中断中止；存续期间欠薪及关系终止后的规则分别核，不从签约日直接推逾期。',
 'prior_proceedings':'核协商调解、仲裁受理/裁决、是否终局及后续救济；不同主体及裁决类型的路径和期限不能混用。',
 'service':COMMON['service'],'authority':COMMON['authority']}
APPEAL={
 'decision':'核一审文书类型、可上诉性与审级；小额诉讼、特别程序、再审及涉外规则不能直接套普通一审上诉。',
 'standing':'核上诉人资格、对其不利部分和诉讼角色；未参加诉讼的主体不自动取得上诉权。',
 'service':COMMON['service']+' 民诉法第85、86条：核起算日排除、法定休假日、在途及顺延，不把日期相加等同法律届满日。',
 'scope':'核上诉请求、事实理由和一审审理范围；新请求、反诉与新证据应分别审查。',
 'filing':'核提交原审法院或二审法院的路径、副本和费用；民诉法第171至174条。',
 'prior_proceedings':'核他方上诉、裁判是否生效及并行救济，不因没有记录认定没有程序。',
 'authority':COMMON['authority']}
AWARD={
 'decision':'核裁决书全文及终局/非终局性质、是否混合事项；不能仅凭金额或标签认定终局。',
 'standing':'区分劳动者与用人单位：终局裁决下劳动者起诉和单位申请撤销不是同一路径。',
 'service':APPEAL['service'],
 'grounds':'用人单位撤销终局裁决须核劳动争议调解仲裁法第49条法定事由和证据，不是重新全面审理实体。',
 'filing':'核第48至50条不同受理法院与期限：终局裁决单位撤销指向仲裁委员会所在地中级法院。',
 'prior_proceedings':'核对方起诉、单位撤销、执行及裁决被撤销后的程序衔接，不能将并行路径视为互不影响。',
 'authority':COMMON['authority']}
JURISDICTION={
 'jurisdiction':COMMON['jurisdiction'],
 'response':'核是否已答辩或反诉以及提出异议的时点；应诉管辖仍有级别管辖、专属管辖例外。民诉法第130条。',
 'service':'核起诉状副本收到日、答辩期间及涉外等特别规则；不把开庭日直接当异议截止日。',
 'arbitration':COMMON['arbitration'],
 'standing':COMMON['standing'],'authority':COMMON['authority']}
ROUTES={'civil_first_instance':(COMMON,CIVIL_PROCEDURE),'labor_arbitration':(LABOR,LABOR_PROCEDURE),
 'civil_appeal':(APPEAL,CIVIL_PROCEDURE),'labor_award_remedy':(AWARD,LABOR_PROCEDURE),
 'jurisdiction_objection':(JURISDICTION,CIVIL_PROCEDURE)}


def prepare_legal_review(raw,claims,bind):
    from source_bound_litigation import _shape,_list
    _shape(raw,(),('claims','procedure'))
    results=[];lines=['请求权要件核查（拟选路径，尚未作事实或适用认定）',
      '下列覆盖状态只表示本稿选入材料，不表示举证充分或要件成立；缺项只表示未选入。法源为2026-11-05编制核对，适用时点仍须复核。']
    seen=set()
    def refs(items):return [bind(ref) for ref in _list(items,'材料引用',10)]
    def show(group):
        return [row['quote']+'\n出处：'+row['citation']['path']+'；片段'+str(row['citation']['chunk']) for row in group]
    for item in _list(raw.get('claims',[]),'请求权审查',20):
        _shape(item,('claim_index','basis'),('elements',))
        idx,basis=item['claim_index'],item['basis']
        if type(idx) is not int or not 0<=idx<len(claims) or idx in seen:
            raise ValueError('请求权审查须对应本次claims的有效且不重复索引。')
        if not isinstance(basis,str) or basis not in BASES:
            raise ValueError('basis须为'+ '/'.join(BASES)+'；未确定路径时不伪选。')
        seen.add(idx);title,articles,rules=BASES[basis];provided={}
        for element in _list(item.get('elements',[]),'elements',len(rules)):
            _shape(element,('key',),('supporting','opposing'))
            key=element['key']
            if not isinstance(key,str) or key not in rules or key in provided:raise ValueError('要件key不适用于所选路径或重复。')
            provided[key]=element
        elements=[];lines.extend(['',f'请求{idx+1}｜{title}',claims[idx]['quote'],articles,CIVIL_CODE])
        for key,rule in rules.items():
            entry=provided.get(key,{})
            supporting=refs(entry.get('supporting',[]));opposing=refs(entry.get('opposing',[]))
            state=('both_sides' if supporting and opposing else 'support_only' if supporting else 'opposing_only' if opposing else 'unselected')
            elements.append({'key':key,'condition':rule,'supporting':supporting,'opposing':opposing,'source_status':state,'established':None})
            lines.extend([f'要件核查：{rule}',f'本稿拟支持{len(supporting)}条、相反或限制{len(opposing)}条；尚未判断证明力。'])
            lines.extend('拟支持原文：'+x for x in show(supporting));lines.extend('相反或限制原文：'+x for x in show(opposing))
            if not supporting:lines.append('未选入本要件支持材料，需补选或核对；不能认定事实不存在。')
        results.append({'claim_index':idx,'basis':basis,'elements':elements,'missing_support':[e['key'] for e in elements if not e['supporting']],
                        'selected_basis_verified':False,'official_source':CIVIL_CODE})
    procedure=None
    if raw.get('procedure') is not None:
        p=raw['procedure'];_shape(p,('route',),('items','remedy'));route=p['route']
        if not isinstance(route,str) or route not in ROUTES:raise ValueError('程序路线不属于支持的核查路径。')
        rules,source=ROUTES[route]
        chosen={}
        for item in _list(p.get('items',[]),'程序材料',len(rules)):
            _shape(item,('key',),('citations',));key=item['key']
            if not isinstance(key,str) or key not in rules or key in chosen:raise ValueError('程序key不适用于该路线或重复。')
            chosen[key]=refs(item.get('citations',[]))
        lines.extend(['','程序核查（路线候选，不是受理或期限结论）',
                     '民事程序：民诉法第85、86、122、124、130、157、171至174条及各路径适用规则。' if source==CIVIL_PROCEDURE else '劳动争议程序：劳动争议调解仲裁法第2、5、21、27至29、47至50条。',source])
        if route=='civil_first_instance':lines.append('民事时效法源：'+CIVIL_CODE)
        items=[]
        for key,rule in rules.items():
            group=chosen.get(key,[]);items.append({'key':key,'condition':rule,'citations':group,'satisfied':None})
            lines.extend([rule,*(show(group) if group else ['本项未选入程序材料；须回读核实，不能认定手续未办或程序障碍不存在。'])])
        procedure={'route':route,'items':items,'unselected':[i['key'] for i in items if not i['citations']],'route_verified':False,'official_source':source}
        if p.get('remedy') is not None:
            from procedure_remedies import prepare_remedy
            procedure['remedy']=prepare_remedy(p['remedy'],route,bind)
            lines.extend(['',procedure['remedy']['text']])
            for ref in procedure['remedy']['classification_citations']+[procedure['remedy']['service_citation']]:
                if ref:lines.extend(['救济来源：'+ref['citation']['path'],ref['quote']])
    return {'claims':results,'procedure':procedure,'legal_verified':False},'\n'.join(lines)
