"""Save source-bound employment checklists without inferring facts or selecting a route."""
import json
import re
from employment_review import calculate_employment_amount


LAW_URL = 'https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/bgt/art/2023/art_0abfdd261c03417b949df19d869add8d.html'
REGULATION_URL = 'https://www.beijing.gov.cn/zhengce/gwywj/201105/t20110506_780976.html'
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
