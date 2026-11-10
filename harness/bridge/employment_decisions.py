"""Save source-bound employment checklists without inferring facts or selecting a route."""
import json
import re
from source_bound_litigation import _reference, _contextual_quote
from employment_review import calculate_employment_amount


LAW_URL = 'https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/bgt/art/2023/art_0abfdd261c03417b949df19d869add8d.html'
REGULATION_URL = 'https://www.beijing.gov.cn/zhengce/gwywj/201105/t20110506_780976.html'
INTERPRETATION_ONE = 'https://www.hncourt.gov.cn/public/detail.php?id=183584'
INTERPRETATION_TWO = 'https://www.court.gov.cn/fabu/xiangqing/472691.html'

_TERMS = {
    'payroll': ('工资记录对账', [
        '按同一原文行的姓名、工资期间、应发工资、代扣合计及实发工资核对；缺项不补零，不跨人、月份、版本或文件拼金额。',
        '只作来源条件算术：应发减代扣再减实发。代扣的合法性、应发口径和支付事实另核；账面差额不等于已认定欠薪，负差额也不自动认定应退。',
        '各行独立保存，不累计为全案应付款；其他收入、加班、补偿与税费依据未核，不自动换算。局部待核不影响其余完整记录。',
    ], []),
    'hiring': ('录用与合同条款', [
        '核实际用工、合同起止、签署及主体；offer、拟签稿和实际用工分别保存。核书面合同及法定必备事项，不以摘录缺项认定原合同缺项。（劳动合同法第7、10、17条）',
        '按合同期限核试用期上限：三个月以上不满一年为一个月，一年以上不满三年为二个月，三年以上固定期限及无固定期限为六个月；不满三个月或以完成任务为期限不得约定。同一用人单位与同一劳动者只能约定一次；试用期包含在合同期限内。（第19条）',
        '试用期工资须核相同岗位最低档工资或合同约定工资的法定80%标准，并同时核适用最低工资；基数、地区和用工状态未查清前不算实际欠薪。（第20条、实施条例第14、15条）',
        '担保或扣证、培训服务期及违约金逐项核；不要把合同拟写条件当已实际执行，违法约定与已发生损失分别审查。（第9、22、25条）',
    ], [LAW_URL, REGULATION_URL]),
    'change': ('合同变更', [
        '分别对照原条款、拟变更内容、劳动者意见、实际履行及书面记录；单方通知不等于协商一致，也不以材料未交推出没有协商。（劳动合同法第35条）',
        '未签书面变更不直接判无效：还须核协商一致、口头变更实际履行超过一个月、内容合法且不违背公序良俗等条件；单纯经过一个月不替代这些条件。（劳动争议解释一第43条）',
        '工资、地点、岗位、时间及主体变化分别核对；合理性、履行事实、地方规则和特殊保护条件另审。本次不自动据变更认定解除、降薪合法性或赔偿金额。',
    ], [LAW_URL, INTERPRETATION_ONE]),
    'noncompete': ('竞业限制', [
        '先区分在职与离职后限制，核人员范围、实际知悉或接触的秘密及保密事项；仅签字、职务名称或缺保密材料不能替代核查，也不能把接触状态未知认定为未接触。（劳动合同法第23、24条；劳动争议解释二第13、14条）',
        '离职后限制核范围、地域与秘密的对应、期限上限二年及按月补偿；在职限制的补偿问题另核，不能直接照搬离职后规则。范围超过合理比例的部分与条款全部效力须区分。（第23、24条；解释二第13、14条）',
        '核是否启动、实际履行、补偿支付、有效约定和违约事实，再讨论停止履行、返还补偿或违约金；签字不自动证明违约成立。规则时间适用、地方标准及损失证据另审。（解释二第15条及相关解释）',
    ], [LAW_URL, INTERPRETATION_TWO]),
}


def assess_employment_terms(cases, case_id, review_stage, citations, request_id='', supersedes='', scenario_citations=None, extract_parameters=False):
    """Save source clauses and stage-specific review conditions, never an individual legal verdict."""
    if not isinstance(review_stage, str) or review_stage not in _TERMS:
        raise ValueError('review_stage须为hiring/change/noncompete/payroll。解除使用原解除工具。')
    if type(extract_parameters) is not bool:raise ValueError('extract_parameters须为布尔值。')
    if not isinstance(citations, list) or not 1 <= len(citations) <= 30:
        raise ValueError('citations须为1至30项本案原文。')
    scenario_citations = [] if scenario_citations is None else scenario_citations
    if not isinstance(scenario_citations,list) or len(scenario_citations)>10:
        raise ValueError('scenario_citations至多10项完整假设行。')
    if len(json.dumps([citations,scenario_citations], ensure_ascii=False)) > 100000:
        raise ValueError('引用总长超过上限，请拆分，不截断原文。')
    sources = {s['path']:s for s in cases.materials(case_id)}
    contexts, refs, rows = {}, [], []
    for raw in citations:
        ref, source = _reference(cases, case_id, raw, sources, contexts)
        quote, span = _contextual_quote(source, ref['start'], ref['end'])
        refs.append(ref); rows.append({'citation':ref,'quote':quote,'span':span})
    from employment_term_scenarios import compare_term_scenario
    scenarios=[]
    for raw in scenario_citations:
        ref, source = _reference(cases,case_id,raw,sources,contexts)
        scenario=compare_term_scenario(review_stage,ref['quote'],source,ref['start'],ref['end'])
        scenarios.append({**scenario,'citation':ref,'assumption':ref['quote']})
        refs.append(ref)
    if sum(len(c['text']) for c in contexts.values()) > 120000:
        raise ValueError('来源上下文超过上限，请分批保存。')
    extraction,extraction_text=None,''
    if extract_parameters:
        if review_stage=='payroll':
            from employment_payroll import extract_payroll
            extraction,extraction_text=extract_payroll(list(contexts.values()))
        else:
            from employment_parameter_extraction import extract_term_parameters
            extraction,extraction_text=extract_term_parameters(review_stage,list(contexts.values()))
    title, checks, urls = _TERMS[review_stage]
    lines = [f'劳动用工｜{title}｜内部待核稿',
             '一、材料原文（按句界保留，真实性及上下文另核；本稿不作条款效力认定）']
    for index,row in enumerate(rows,1):
        ref=row['citation']
        lines.extend([f'{index}. {row["quote"]}',f'出处：{ref["path"]}；片段{ref["chunk"]}；SHA-256 {ref["sha256"]}'])
    lines.extend(['二、逐项核验条件（全国一般规则；未自动认定本案满足或不满足）',*checks,
                  '三、法源与边界','法源于2026-11-05编制时核对，不表示本次运行已联网检索；仍须核适用时点及地方规定。',*urls,
                  '四、完整来源片段（供核对否定、条件及陈述主体）'])
    for context in contexts.values(): lines.extend([context['path'],context['text']])
    scenario_text='\n'.join(s['assumption']+'\n'+s['text'] for s in scenarios)
    if scenarios:
        lines.extend(['五、来源明确假设的程序核算（不是案件事实认定）',scenario_text])
    if extraction_text:lines.extend(['自动提取与条件核算',extraction_text])
    from material_scan import location_label
    provenance=[]
    notices=[]
    for context in contexts.values():
        label=location_label(context)
        if label:provenance.append(f'{context["path"]}；片段{context["chunk"]}；{label}')
        notices.extend(f'{context["path"]}：{warning}' for warning in context.get('parse_warnings',[]))
        if context.get('failed_pages'):
            notices.append(f'{context["path"]}：尚未读完整的页 {context["failed_pages"]}；已读内容仍可使用。')
    delivery_sections=[]
    if provenance:delivery_sections.append('来源位置\n'+'\n'.join(dict.fromkeys(provenance)))
    if notices:delivery_sections.append('材料读取提示（仅影响所述部分）\n'+'\n'.join(dict.fromkeys(notices)))
    delivery_text='\n\n'.join(delivery_sections)
    if delivery_text:lines.append(delivery_text)
    with cases.db() as db:
        db.execute('BEGIN IMMEDIATE')
        note=cases._add_note(db,case_id,'employment_review','\n'.join(lines),
                             source='来源绑定的'+title+'核验清单，未作法律认定',
                             citations=refs,request_id=request_id,supersedes=supersedes)
        if note.get('warnings'):
            raise ValueError('保存时来源变化或失配，本次未保存，请回读材料。')
    recorded=note.get('recorded',True)
    result={'recorded':recorded,'note':note,'review_stage':review_stage,'legal_verified':False,
            'clauses':rows,'checks':checks,'source_contexts':list(contexts.values()),'scenarios':scenarios,'parameter_extraction':extraction,
            'user_summary':f'已保存{title}原文及核验清单，共{len(rows)}项引文。未作个案效力认定、实际应付金额计算或对外提交；具体条件和来源见同一保存记录。' if recorded else '本次更正未保存，请回读当前记录后处理。'}
    if recorded:
        result.update(id=note['id'],kind=note['kind'])
        if scenario_text: result['user_summary']+='\n\n同一记录中的假设核算：\n'+scenario_text
        if extraction_text:result['user_summary']+='\n\n同一记录中的参数候选：\n'+extraction_text
        if delivery_text:result['user_summary']+='\n\n'+delivery_text
    return result
_USER_SUMMARY = ('已保存劳动解除条件清单。程序未判断任何路径成立或不成立，'
                 '未确定实际应付款、补偿月份或最晚通知日；材料陈述见文档保存的原句及完整片段上下文。'
                 '已给事实不会因程序未判断变为未知。用户明确给定参数的情景算术可另行核算，不等于实际应付认定。')

# These are alternative rules to check, never findings that the selected quotations satisfy them.
_PATHS = (
    ('mutual_employer', '用人单位提出的协商解除',
     '核用人单位提出、双方真实协商一致及协议内容；不能把仅有谈判或拟议协议当已达成。',
     '符合第46条第2项时依法核经济补偿N；协议另定款项按真实约定及效力另审，不能认定所有协商解除都必付N。',
     '劳动合同法第36、46条第2项、47条'),
    ('mutual_worker', '劳动者提出的协商解除',
     '核劳动者提出和双方真实协商一致；提出方未知时不能自动归入任何一方。',
     '不能仅因协商一致认定法定N；约定补偿及其他法定支付依据分别核验，不等于全部款项为零。',
     '劳动合同法第36、46条第2项'),
    ('worker_resignation', '劳动者普通辞职',
     '核劳动者真实辞职意思、适用第37条的通知要求及是否另有第38条事由。',
     '不能仅凭普通辞职认定第46条经济补偿；工资等已发生债权另核，不以辞职一概归零。',
     '劳动合同法第37、38、46条'),
    ('worker_article38', '劳动者依法单方解除',
     '核第38条具体法定事由、实际解除意思表示及对应事实；不能把资料未交当成用人单位违法已成立。',
     '符合第38条、第46条第1项时核经济补偿N，不自动转为违法解除赔偿2N。',
     '劳动合同法第38、46条第1项、47条'),
    ('employer_article39', '用人单位过失性解除',
     '核第39条具体事由、制度及事实证据、实际采用理由和适用程序；匿名投诉未访谈不推定其他调查证据存在或不存在。',
     '合法适用第39条时，不仅因该解除发生第46条经济补偿或第40条代通知金；工资、约定及其他责任另核。',
     '劳动合同法第39、43、46条'),
    ('article40_notice', '第40条：提前通知分支',
     '第40条法定实体条件成立，并符合第42条限制、第43条等适用程序；选择提前三十日以书面形式通知劳动者本人，核实际到达与期限。',
     '符合第46条第3项时核经济补偿N；已依法选择提前通知分支，不因第40条本身再加一个月代通知金。工资等款项分别核。',
     '劳动合同法第40、42、43、46条第3项、47条'),
    ('article40_pay', '第40条：代通知金分支',
     '第40条法定实体条件成立，并符合第42条限制、第43条等适用程序；选择额外支付一个月工资替代提前三十日书面通知。付款不能替代实体条件或其他程序。',
     '符合条件时为经济补偿N与代通知金并列；代通知金按上一个月工资标准核定，与补偿平均基数不同。不能把全部第40条解除简写为无条件N+1。',
     '劳动合同法第40、42、43、46条第3项、47条；实施条例第20条'),
    ('article41', '经济性裁员',
     '核第41条具体法定事由、人数门槛、提前说明与听取意见、方案报告、优先留用以及第42条限制；不能只凭经营困难字样判定成立。',
     '依法适用第41条且符合第46条第4项时核经济补偿N；不自动套第40条一个月代通知金。',
     '劳动合同法第41、42、46条第4项、47条'),
    ('fixed_term_expiry', '固定期限合同届满',
     '核合同确实届满、是否应续延或订立无固定期限合同、续订条件与劳动者态度；未知不等于拒绝续订。',
     '依第46条第5项核经济补偿及其例外；用人单位维持或提高条件续订而劳动者不同意的例外须查明，不能将所有届满直接映射为N。',
     '劳动合同法第14、44、45、46条第5项、47条'),
    ('unlawful', '违法解除或终止的救济',
     '核实际解除或终止是否发生、是否属于违法解除或终止；劳动者要求且能够继续履行时适用继续履行，不要求或者劳动合同不能继续履行时再核赔偿。',
     '符合第48、87条赔偿条件时核法定标准二倍的赔偿金，不再另加同一解除的经济补偿；赔偿年限依实施条例第25条自用工日起核，不能把第97条历史分段经济补偿直接翻倍。',
     '劳动合同法第48、87条；实施条例第25条'),
)

_COMMON = (
    '材料范围：只保存所选原文摘录，不代表已读取全部材料或确认原文陈述真实；引文匹配不证明法律条件成立。',
    '事实边界：按给定材料或其中明示假设理解。原文中的已知、否定、未知原样保留；本程序不作语义分类，不将任何路径条件自动标为成立或不成立。',
    '调查：未访谈只涉及访谈状态，不推定其他调查证据存在或不存在；缺材料与行为未发生分开。',
    '不能胜任：第40条第2项还需核原岗位不能胜任、培训或者调岗择一及此后仍不能胜任，不能因只做其中一项就判缺项。',
    '保护与程序：逐项核第42条完整条件（包括医疗期、孕产哺乳、职业健康检查、劳动能力、连续工龄及退休条件），以及适用的工会通知、送达等，不把无人核实当不存在。',
    '日期：开业、考核、通知发出、收到、载明拟生效和实际解除分别归属事件；当前仍在工作与未来拟生效并不矛盾，拟生效日后的履行另核。',
    '金额：本工具不输出应付金额、补偿月份或最晚通知日。先核实际解除终点（拟议情景须明确标注）、法定工资口径、连续年限与所选路径；到手数不直接当法定基数。',
    '金额规则：第47条三倍基数与十二年上限须满足相应条件，不适用所有人；经济补偿的2008年前期间按第97条另核。换签依实施条例第10条核非本人原因安排及既往补偿；地区标准依第14条，工资口径依第27条核。',
    '显式算术：用户明确给定情景基数、折算年限和倍数时，可另用calculate_employment_amount；只算假设，不认定实际应付。互斥方案不相加。工资结算仅按材料已给状态另列，未提及不推定存在欠付。',
    '适用边界：下列为常见路径的条件清单，其他终止事由、特殊用工及地方规则另核；不替代承办律师结合全部事实审查。法源为编制时核对的全国规则，非本次联网检索。',
)


def assess_employment_termination(cases, case_id: str, citations: list[dict],
                                  request_id: str = '', supersedes: str = '',
                                  scenario_citations: list[dict] | None = None) -> dict:
    """保存原文绑定的解除清单及可选显式情景算术，不认定事实或实际应付款。

    citations为1至30条本案原始材料引文，必须有path/quote/sha256/chunk。
    原文须当前可逐字匹配，不接收模型确认布尔值或自由结论。返回id可用于export_case。
    request_id只供原请求重试，用户明确更正时才传supersedes；更正冲突recorded=false。
    scenario_citations最多10条独立完整行；仅解析材料明列的基数、折算年限、倍数。
    """
    if not isinstance(citations, list) or not 1 <= len(citations) <= 30:
        raise ValueError('citations须为1至30条本案原始材料引文。')
    if scenario_citations is None:
        scenario_citations = []
    if not isinstance(scenario_citations, list) or len(scenario_citations) > 10:
        raise ValueError('scenario_citations至多10条，各方案独立计算，不相加。')
    citations = citations + scenario_citations
    if len(citations) > 40:
        raise ValueError('原文与情景引用合计至多40条。')
    refs = []
    for ref in citations:
        if not isinstance(ref, dict) or set(ref) != {'path', 'quote', 'sha256', 'chunk'}:
            raise ValueError('每条引文须含path、quote、真实sha256、chunk，不接受事实确认值或模型结论。')
        if any(not isinstance(ref.get(key), str) or not ref[key].strip() for key in ('path', 'quote')):
            raise ValueError('path和quote须为非空文字。')
        if len(ref['quote']) > 5000 or len(ref['path']) > 4096:
            raise ValueError('单条引文上限5000字，请按材料片段分条；不截断原文。')
        if type(ref['chunk']) is not int or ref['chunk'] < 0:
            raise ValueError('chunk须为非负整数，不接受布尔值。')
        sha = ref.get('sha256')
        if (not isinstance(sha, str) or len(sha) != 64 or
                any(c not in '0123456789abcdef' for c in sha)):
            raise ValueError('sha256须为读取材料返回的64位小写哈希。')
        path = cases.store.safe(ref['path'], must_exist=False).relative_to(cases.root).as_posix()
        if path.lower().startswith('drafts/'):
            raise ValueError('生成草稿不能作为本工具的原始材料，请引用真实来源。')
        refs.append({**ref, 'path': path})
    if sum(len(ref['quote']) for ref in refs) > 50000:
        raise ValueError('单次引文总长上限50000字，请分批，不截断原文。')
    scenarios=[]
    for ref in scenario_citations:
        # Only an explicit source formula is parsed; dates/net pay never supply hidden operands.
        match=re.fullmatch(r'情景假设[：:]\s*基数([0-9]+(?:\.[0-9]+)?)元[，,]\s*折算年限([0-9]+(?:\.[0-9]+)?)年[，,]\s*倍数([0-9]+(?:\.[0-9]+)?)[。.]?',ref['quote'].strip())
        if not match:
            raise ValueError('情景须为材料中独立完整一行：情景假设：基数10000元，折算年限8.5年，倍数2。请回读明确假设，不从日期或到手收入推算。')
        scenarios.append(calculate_employment_amount(*match.groups(), assumptions=ref['quote']))
    scenario_lines=['各项仅按材料所列假设独立计算，不相加，不认定实际应付款；没有自动选用解除路径、历史分段或封顶规则。']
    for i,scenario in enumerate(scenarios,1):
        scenario_lines.extend([f'情景{i}：'+scenario['assumptions'],
                               scenario['formula']+' = '+scenario['amount']+' 元',scenario['scope']])
    paths = [dict(id=key, title=title, conditions=conditions, payment=payment,
                  legal_basis=basis, assessment='not_assessed')
             for key, title, conditions, payment, basis in _PATHS]
    lines = ['劳动解除条件清单｜内部工作稿，事实及法律适用待承办人复核',
             '一、所选材料原句（不代替事实认定；引用校验状态见笔记citations）']
    for i, ref in enumerate(refs, 1):
        # JSON quoting keeps embedded headings/instructions visibly inside the source quotation.
        lines.append(f'{i}. 来源：{ref["path"]}\n原句：'+json.dumps(ref['quote'], ensure_ascii=False))
    lines.extend(['\n二、共同核对事项', *_COMMON, '\n三、路径条件与款项（逐项对照，不自动选定）'])
    for route in paths:
        lines.extend([f'\n{route["title"]}', '条件：'+route['conditions'],
                      '款项：'+route['payment'], '依据：'+route['legal_basis'],
                      '本案适用状态：程序未作判断，请对照材料核实。'])
    lines.extend(['\n法源索引（编制核对日2026-11-05，适用时点与地方规则仍须核实）',
                  '劳动合同法：'+LAW_URL, '劳动合同法实施条例：'+REGULATION_URL])
    # Validate and append in one DB transaction; a late file change must roll back the insert.
    with cases.db() as db:
        db.execute('BEGIN IMMEDIATE')
        checked, warnings = cases._citations(db, case_id, refs)
        if warnings or any(ref['status'] != 'matched' for ref in checked):
            raise ValueError('原文未匹配、来源版本变化或尚未解析，本批未保存；请重新读取本案材料。')
        contexts, total_context = [], 0
        lines.append('\n四、完整来源片段上下文（材料文字，不是程序判断）')
        for ref in checked:
            chunk = db.execute('SELECT text FROM chunks WHERE path=? AND ordinal=?',
                               (ref['path'], ref['chunk'])).fetchone()
            context = chunk['text'] if chunk else ''
            if not context or len(context) > 16000:
                raise ValueError('来源片段不存在或超过16000字，请拆分后重新读取；本批未保存。')
            total_context += len(context)
            if total_context > 120000:
                raise ValueError('本批来源上下文超过120000字，请分批，不截断原文。')
            contexts.append({'citation': ref, 'context': context})
            lines.extend([f'来源：{ref["path"]}｜版本{ref["version"]}｜片段{ref["chunk"]}｜SHA-256 {ref["sha256"]}',
                          context])
        if scenarios:
            for item in contexts[-len(scenarios):]:
                if item['citation']['quote'].strip() not in [line.strip() for line in item['context'].splitlines()]:
                    raise ValueError('情景引用必须是材料中独立完整一行，不能截掉前置否定或其他限定。')
            lines.extend(['\n五、来源绑定的情景算术（不认定应付）',*scenario_lines])
        note = cases._add_note(db, case_id, 'employment_review', '\n'.join(lines),
                              source='按本案所选逐字来源生成固定条件清单；不作事实或法律认定',
                              citations=refs, request_id=request_id, supersedes=supersedes)
        if note.get('warnings'):
            raise ValueError('保存期间来源变化，本批未保存；请重新读取本案材料。')
    result = {'recorded': note.get('recorded', True), 'note': note, 'paths': paths,
              'source_contexts': contexts,
              'selected_path': None, 'legal_entitlement_verified': False,
              'calculation': {'performed': False, 'amount': None, 'compensation_months': None}}
    if result['recorded']:
        result.update(id=note['id'], kind=note['kind'], user_summary=_USER_SUMMARY)
        if scenarios:
            result['calculation']={'performed':True,'amount':None,'compensation_months':None,'scenarios':scenarios}
            result['user_summary'] += '\n\n已与上述清单保存在同一记录的情景算术：\n'+'\n'.join(scenario_lines)
    else:
        result['user_summary'] = '本次更正未保存，请先回读当前记录再处理；程序未判断任何路径成立或不成立。'
    return result
