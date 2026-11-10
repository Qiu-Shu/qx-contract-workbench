"""Small persistent legal workflows on the existing local material transport."""
import argparse
from datetime import date, timedelta
from pathlib import Path
import re
import hashlib

from mcp.server.mcpserver import MCPServer
from store import MaterialStore
from business_store import CaseStore
from hearing import HearingStore
from workflows import workflow
import server as material_server
from server import friendly_errors
from source_bound_inputs import MaterialCitation, Citation, Excerpt, Calculation, LitigationBrief, LitigationIssue, LitigationClaim, LegalReview, RegisterEntry, ComplianceTracking, SourceGroup
from pydantic import StrictBool
from verified_delivery import attach_delivery, text_sha256

mcp = MCPServer('qx_legal', instructions=(
    '按需求读取业务方法。持续办理时明确案件ID，把本轮材料关联到该案再读取；'
    '原话、内部分析与客户回复分别追加保存，更正保留原记录。庭审发言是模拟记录，不是证据。'
    '工具保存失败时保留可用正文并说明，不能称保存成功。'), log_level='WARNING')
cases = None
hearings = None


@mcp.tool()
@friendly_errors
def calculate_calendar_date(base_date: str, offset_days: int, rule_source: str) -> dict:
    """按明确基准日和规则作自然日偏移。提前30日传-30，次日起第15日传15。

    必须提供YYYY-MM-DD基准及规则来源说明，不代选起算事件、不查法、不调整节假日或工作日。
    基准/期间规则未知时先核实，结果不能直接当已确认的法定期限；不读写任何案件。
    """
    if not isinstance(base_date, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', base_date):
        raise ValueError('请提供已确认的基准日期，格式为YYYY-MM-DD。')
    if type(offset_days) is not int or not -36600 <= offset_days <= 36600:
        raise ValueError('自然日偏移必须为-36600至36600之间的整数。')
    if not isinstance(rule_source, str) or not rule_source.strip() or len(rule_source) > 2000:
        raise ValueError('请说明本次天数及起算口径的来源，未知规则不能由计算器推定。')
    try:
        result = date.fromisoformat(base_date) + timedelta(days=offset_days)
    except (ValueError, OverflowError):
        raise ValueError('日期不存在或结果超出可表示范围。') from None
    return {'base_date': base_date, 'offset_days': offset_days, 'result_date': result.isoformat(),
            'rule_source': rule_source.strip(), 'rule_verified': False, 'holiday_adjusted': False,
            'scope': '仅核对自然日算术；法律适用、起算事实和节假日顺延须另行核实。'}


@mcp.tool()
@friendly_errors
def get_workflow(name: str) -> dict:
    """按需读取reception/contract/case/hearing/evidence方法与来源；不调用模型。"""
    return workflow(name)


@mcp.tool()
@friendly_errors
def list_cases(query: str = '', offset: int = 0, limit: int = 20) -> dict:
    """按题名查找案件。不要仅按最近时间猜案件归属，同名结果需结合当前会话或询问。"""
    return cases.list(query, offset, limit)


@mcp.tool()
@friendly_errors
def create_case(title: str, our_role: str = '', request_id: str = '') -> dict:
    """用户需要持续办理或保存时建案；our_role只录入已明确立场。request_id用于重复请求找回。"""
    return cases.create(title, our_role, request_id)


@mcp.tool()
@friendly_errors
def get_case(case_id: str, offset: int = 0, limit: int = 30, include_history: bool = False) -> dict:
    """读取指定案件材料、笔记和变更提示；长笔记按返回next_start调用read_case_note。"""
    return cases.get(case_id, offset, limit, include_history)


@mcp.tool()
@friendly_errors
def link_case_materials(case_id: str, paths: list[str]) -> dict:
    """把明确用于本案的材料按当前版本登记；先使用qx_materials导入和解析，不覆盖旧版关联。"""
    return cases.link_materials(case_id, paths)


@mcp.tool()
@friendly_errors
def record_case_note(case_id: str, kind: str, content: str, source: str = '',
                     supersedes: str = '', citations: list[dict] | None = None,
                     request_id: str = '') -> dict:
    """追加consultation/fact/inference/timeline/stance/todo/contract_review/client_reply/internal_note等记录。

    content为自然语言，不限制回答格式或业务篇幅。更正用supersedes指向当前同类别笔记；只有用户明确更正才使用。
    citations每项path、quote，可选sha256、chunk；程序核对原文，不要让模型计算字符偏移。
    未匹配引用保留正文并标待核，材料陈述不等于事实已证实。客户正文与内部分析必须分两条保存。
    """
    return cases.add_note(case_id, kind, content, source, supersedes, citations, request_id)


@mcp.tool()
@friendly_errors
def record_reception(case_id: str, client_reply: str, internal_note: str,
                     source: str = '', request_id: str = '') -> dict:
    """一次事务分别保存客户可转发正文与内部底稿；失败不留下单独半条，重试沿用request_id。"""
    return cases.record_reception(case_id, client_reply, internal_note, source, request_id)


@mcp.tool()
@friendly_errors
def read_case_note(case_id: str, note_id: str, start: int = 0, limit: int = 8000) -> dict:
    """分段读取本案一条完整笔记，按next_start继续；不会把旧笔记改成最新事实。"""
    return cases.read_note(case_id, note_id, start, limit)


@mcp.tool()
@friendly_errors
def read_case_material(case_id: str, path: str, start: int = 0, limit: int = 6,
                       page: int | None = None, version: int | None = None) -> dict:
    """读取本案关联材料；默认核对当前原件，指定version可回读历史解析文字快照。
    当前分页材料返回page_count和next_page；next_start是当前筛选内的片段偏移。读完最后一页不继续试探空白页。
    """
    return cases.read_material(case_id, path, start, limit, page, version)


@mcp.tool()
@friendly_errors
def search_case_materials(case_id: str, query: str, offset: int = 0, limit: int = 10) -> dict:
    """仅搜索本案已关联材料及笔记，kind区分二者。笔记是陈述/分析，不因命中变为原始证据。"""
    return cases.search(case_id, query, offset, limit)


@mcp.tool()
@friendly_errors
def export_case(case_id: str, filename: str = '案件工作稿.docx', audience: str = 'internal',
                note_ids: list[str] | None = None) -> dict:
    """从已保存当前记录生成真实Word。internal含来源；client仅客户回复，默认最新一条，不夹内部底稿。

    note_ids可指定当前笔记；更正后的旧记录可get_case(include_history=True)回查，但不默认导出。
    导出不发送到微信，文件同名另存。工具成功后再提供真实路径。
    """
    if audience not in {'internal', 'client'}:
        raise ValueError('audience只能为internal或client。')
    page = cases.export_snapshot(case_id)
    notes = page['notes']
    if note_ids is not None:
        by_id = {note['id']: note for note in notes}
        if any(identifier not in by_id for identifier in note_ids):
            raise ValueError('所选笔记不在本案当前记录中，请回读后选择。')
        notes = [by_id[identifier] for identifier in dict.fromkeys(note_ids)]
    if audience == 'client':
        if note_ids is not None and any(note['kind'] != 'client_reply' for note in notes):
            raise ValueError('客户版只能导出client_reply，内部底稿不会夹入。')
        if note_ids is None:
            notes = [note for note in notes if note['kind'] == 'client_reply'][-1:]
    if not notes:
        raise ValueError('尚无所选范围的已保存内容，请先保存回复或工作稿。')
    sections = []
    for note in notes:
        if audience == 'internal':
            sections.append(f"## {note['kind']} · {note['id']}")
        sections.append(note['content'])
        if audience == 'internal':
            if note.get('source'):
                sections.append('记录来源：' + note['source'])
            for citation in note.get('citations', []):
                from material_scan import location_label
                display_location=location_label(citation) or citation.get('location','')
                sections.append(f"出处：{citation.get('path', '')}；{display_location}；"
                                f"引用版本：{citation.get('version', '未记录')}；"
                                f"SHA-256 {citation.get('sha256', '未记录')}；片段：{citation.get('chunk', '未记录')}；"
                                f"记录时原文匹配：{citation.get('status', 'unverified')}\n{citation.get('quote', '')}")
            sections.extend('待核：' + str(warning) for warning in note.get('warnings', []))
    if audience == 'internal':
        sections.append('## 当前关联材料版本（引用自身版本见各条出处）')
        for item in page.get('materials', []):
            sections.append(f"{item['path']} · 版本 {item.get('version', '未记录')} · SHA-256 {item['sha256']}")
            if item.get('changed'):
                sections.append('待核：文件内容已变化，当前文件与登记版本不同。')
            if item.get('missing'):
                sections.append('待核：登记的材料文件当前不可读取。')
            sections.extend('待核：' + str(warning) for warning in item.get('warnings', []))
    title = '客户回复' if audience == 'client' else page['case']['title'] + ' · 工作稿'
    result = material_server.write_word_draft(filename, title, '\n\n'.join(sections))
    return {**result, 'case_id': case_id, 'audience': audience,
            'sha256': hashlib.sha256(cases.safe(result['path']).read_bytes()).hexdigest(),
            'note_ids': [note['id'] for note in notes],
            'note_versions': [{'id': note['id'], 'sha256': text_sha256(note['content'])} for note in notes]}


@mcp.tool()
@friendly_errors
def start_hearing(case_id: str, our_role: str, focus: str = '', request_id: str = '', previous_id: str = '') -> dict:
    """开始五阶段民事庭审演练，明确我方plaintiff/defendant。补件重开用previous_id关联，保留旧回合。"""
    return hearings.start(case_id, our_role, focus, request_id, previous_id)


@mcp.tool()
@friendly_errors
def get_hearing(hearing_id: str, offset: int = 0, limit: int = 30) -> dict:
    """回读演练与下一阶段/角色；长发言按next_start调用read_hearing_turn，页末按next_offset续读。"""
    return hearings.get(hearing_id, offset, limit)


@mcp.tool()
@friendly_errors
def list_hearings(case_id: str, offset: int = 0, limit: int = 20) -> dict:
    """按明确案件找回演练ID与已保存进度；多个演练结合当前任务选择，不自动按最近记录续接。"""
    return hearings.list(case_id, offset, limit)


@mcp.tool()
@friendly_errors
def read_hearing_turn(hearing_id: str, turn_id: str, start: int = 0, limit: int = 8000) -> dict:
    """逐段回读本次演练已保存发言，按next_start读取全文；不会改变发言或推进阶段。"""
    return hearings.read_turn(hearing_id, turn_id, start, limit)


@mcp.tool()
@friendly_errors
def record_hearing_turn(hearing_id: str, stage: str, role: str, text: str,
                        citations: list[dict] | None = None, unresolved: str = '', request_id: str = '') -> dict:
    """保存一次真实生成的角色发言；按get_hearing给出的顺序推进。不要预先填充未执行阶段。"""
    return hearings.append_turn(hearing_id, stage, role, text, citations, unresolved, request_id)


@mcp.tool()
@friendly_errors
def get_hearing_role_context(hearing_id: str, role: str) -> dict:
    """生成指定角色的目标、材料版本与已发生发言摘要；供定向追问，不声称同模型角色上下文独立。"""
    return hearings.role_context(hearing_id, role)


@mcp.tool()
@friendly_errors
def ground_case_extractions(case_id: str, path: str, source_sha256: str,
                            chunk: int, extractions: list[dict]) -> dict:
    """用本机LangExtract核对本案摘录出处，不另调模型。先read_case_material获取sha256和ordinal。

    extractions每项仅label、quote逐字原文，最多30项；返回页/片段/字符位置及matched/unmatched/ambiguous。
    不接受无出处事实，不做法律认定，不自动保存；未匹配或重复原句请回读补充上下文。
    """
    from grounded_extraction import ground_case_extractions as ground
    return ground(cases, case_id, path, source_sha256, chunk, extractions)


@mcp.tool()
@friendly_errors
def save_evidence_analysis(case_id: str, issues: list[dict], request_id: str = '', supersedes: str = '') -> dict:
    """保存本案证据分析。每项proposition、finding_kind(material_statement/inference/unknown)、assessment、supporting/opposing列表、unknown/supplement文字列表、admissibility。

    材料项statement/speaker/carrier/citations；admissibility有authenticity/legality/relevance待核问题列表。
    引用必须本案path/quote，可带sha256/chunk/start/end，保留定位失败状态。不将引用匹配认定为法律事实；更正用supersedes。
    """
    from evidence_analysis import save_evidence_analysis as save
    return save(cases, case_id, issues, request_id, supersedes)


@mcp.tool()
@friendly_errors
def generate_litigation_document(case_id: str, document_type: str, filename: str, data: dict) -> dict:
    """生成真实Word正文草稿及独立内部来源稿，不发出/提交。类型civil_complaint/civil_defense/representation/evidence_list/cross_examination/labor_arbitration/lawyer_letter。

    data可含parties[{role,text,citations}]、requests/facts[{heading,text,citations}]、sections[{heading,text,citations}]，title/authority/case_number/signatory/date；律师函mandate{client,issuer,recipient,authorized,citations}。
    事实与理由及其分节放facts，sections仅其他章节；heading可省略。不要留空facts而把事实全放sections。
    未知保留待核；引用必须本案材料，工作草稿不作证据；不冒称授权、签署或已完成审查。只向用户展示正文，内部稿单列。
    返回body_text为实际保存的正文；最终使用同次user_summary及真实文件链接，不在聊天另写一套事实或意见。回执只核对保存版本，不认证正文结论正确。
    """
    from litigation_documents import generate_litigation_document as generate
    return attach_delivery(cases, case_id, generate(cases, case_id, document_type, filename, data))


@mcp.tool()
@friendly_errors
def save_employment_review(case_id: str, stage: str, findings: list[dict], request_id: str = '', supersedes: str = '') -> dict:
    """追加劳动用工审查，stage=hiring/change/termination/dispute。

    findings每项fact/basis/source/risk/action文字，另可topic/pending/citations。未知事实保留待核，不从办公室开业等日期猜实际解除日。
    引用按本案核对；具体法律适用和劳动关系状态由承办人复核。更正仅明确要求时用supersedes。
    保存成功后以id回读并用export_case(note_ids=[id],audience="internal")导出；最终原样交付user_summary和文件。摘要来自同一保存记录，不另行改写事实/建议，来源或记录改变须回读后处理。
    hiring中的试用工资项使用{rule:"probation_pay",parameters:{contract_pay:金额对象,grade_pay:金额对象,minimum_pay:金额对象,probation_pay:金额对象}}。金额对象为{amount:"原文金额含元/万元",citation:{path,quote,sha256,chunk}}，引用须含对应标签且四项同一片段。程序按实施条例15条计算两种80%候选及月差额并生成候选条款，替代本项模型自填的fact/basis/risk/action。缺值/疑点只保留本项待核，其他意见照常保存；查看rule_reviews。标题明确为试用工资而未传参数时，同样不保存模型自拟金额结论。
    竞业金额比较可用{rule:"noncompete_comparison",parameters:{penalty:金额对象,loss:金额对象,monthly_compensation:金额对象,monthly_pay:金额对象}}；参数可缺省，不补零。标签分别为违约金、损失、月补偿、月工资；同源且口径明确才算比值，比值不自动认定过高或失衡。查看rule_reviews的逐项结果。保存前会检查常见的未知变否定、重复试用候选条款、无依据竞业比较；只修关联语句，review_changes及内部核对稿保留原稿和理由，最终交付user_summary与本次note_ids的导出。
    """
    from employment_review import save_employment_review as save
    return attach_delivery(cases, case_id, save(cases, case_id, stage, findings, request_id, supersedes))


@mcp.tool()
@friendly_errors
def calculate_employment_amount(base: str, years: str = '1', multiplier: str = '1', assumptions: str = '') -> dict:
    """精确计算已明确的基数×年限×倍数，参数为非负十进制字符串，assumptions注明情景条件。
    只做算术，不认定N/2N适用，不推算工龄/工资基数/封顶；工资、补偿、赔偿、代通知金分别核定。
    """
    from employment_review import calculate_employment_amount as calculate
    return calculate(base, years, multiplier, assumptions)


@mcp.tool()
@friendly_errors
def build_source_bound_litigation(case_id: str, document_type: str, filename: str,
                                  excerpts: list[Excerpt], calculations: list[Calculation] | None = None,
                                  brief: LitigationBrief | None = None,
                                  issues: list[LitigationIssue] | None = None,
                                  claims: list[LitigationClaim] | None = None,
                                  legal_review: LegalReview | None = None) -> dict:
    """按本案当前原文组装可编辑诉讼来源草稿及内部核对稿；不发送、不认定事实。

    document_type支持civil_complaint/civil_defense/representation/evidence_list/cross_examination/labor_arbitration/lawyer_letter，纯程序核查用procedure_review（必须有legal_review.procedure，不传brief，不生成拟诉求），以及civil_appeal民事上诉来源草稿、labor_award_set_aside撤销劳动仲裁裁决申请来源草稿。
    excerpts每项仅section(parties/requests/facts/sections)、citation{path,quote,sha256,chunk}。先read_case_material取得真实版本与原句。
    不接收模型改写的text、角色全称或已立案/授权/客户知悉声明；未知元数据由程序留空。
    calculations可选，每项{minuend:{citation,amount},subtrahends:[{citation,amount}]}；amount必须为原句中带单位完整金额如96000元或9.6万元。
    brief可选：parties[{role,name,citation}]、claim_kind(payment/return/undetermined)、claim_amount{citation,amount}或calculation_index（两者互斥，指向本次算式）。
    roles为plaintiff/defendant；民事上诉为appellant/appellee；劳动申请和撤销裁决为applicant/respondent；律师函为client/issuer/recipient。name须原文逐字名称，角色对应仍待律师核实。
    brief用于生成固定条件式拟请求；不给任意正文。representation必须有非空brief及requests、facts两类引文，分别保留主张与依据/限制，缺项拒绝生成。
    差额不认定到期应付。引用失败拒绝生成。最终使用user_summary与实际文件；内部完整片段不等于正文已采用所有观点，不能另加事实或承诺。
    issues可选最多20项：claim为主张原文引用，supporting/opposing/legal_basis各为引用列表；全部必须本案来源。逐项保留相反、限制材料及法源摘录，不接收自由结论；缺组只表示未选入，不判定不存在或主张成立。
    多项诉求用claims，最多20项，每项request是诉求原文引用，issue_indices是本次issues的0起始索引列表；未确定关联时留空。程序分别保存请求、争点和缺组，不合并金额，不认证关联正确。
    请求权/程序核查用legal_review：claims[{claim_index,basis,elements:[{key,supporting:[引用],opposing:[引用]}]}]对应本次claims。
    basis=sale_price或service_fee要件key为agreement/performance/due/balance/defenses；service_fee用于服务报酬的合同通则核查，具体合同类型另核；private_loan为agreement/delivery/due/balance/interest；unjust_enrichment为benefit/loss/no_basis/exceptions/scope。这是拟选路径，不能伪称事实成立。
    legal_review.procedure={route,items:[{key,citations:[引用]}]}；route=civil_first_instance的key为standing/jurisdiction/arbitration/limitation/prior_proceedings/service/authority，labor_arbitration为scope/jurisdiction/limitation/prior_proceedings/service/authority。
    复杂程序可选civil_appeal（decision/standing/service/scope/filing/prior_proceedings/authority）、labor_award_remedy（decision/standing/service/grounds/filing/prior_proceedings/authority）、jurisdiction_objection（jurisdiction/response/service/arbitration/standing/authority）。
    前两者可加procedure.remedy={decision_kind,actor,classification_citations:[引用],service_citation:引用}；decision_kind=civil_judgment/civil_order/labor_final/labor_nonfinal/labor_mixed/unknown，actor=party/worker/employer/unknown。分类来源须包含对应一审判决/可上诉裁定或终局/非终局裁决及救济主体；原文明示同一份裁决同时含终局和非终局事项时用labor_mixed，分别多份裁决或否定语境不能套用；不明时用unknown，不伪选。service_citation可省，收到日期只识别完整行或分句“收到日期：YYYY-MM-DD”（亦支持送达日期/签收日期），不从作出日、发出日、预计日期补值；输出仅为未处理法定休假日的条件算术参考点，不是法律截止日。民事上诉、撤销劳动终局裁决的专用来源草稿另见下列模板条件；不能改名冒充完整可提交文书。
    未选入项自动列待补，支持与反证均原文保存；不得填established、satisfied或自由法律结论。不知道的路径不伪选，不据材料齐全宣布可起诉或未过时效。
    专用civil_appeal/labor_award_set_aside必须有匹配的legal_review.procedure.remedy候选及requests/facts两类引文；brief只填角色，不能套用payment/return、claim_amount或calculation_index。原裁判信息、具体诉求和法定事由仍须逐项核实；这两类只是来源草稿，不是自动完成或可提交文书。
    """
    from source_bound_litigation import build_source_bound_litigation as build
    result = build(cases, case_id, document_type, filename,
                 [x.model_dump(exclude_unset=True, exclude_none=True) for x in excerpts],
                 None if calculations is None else [x.model_dump(exclude_unset=True, exclude_none=True) for x in calculations],
                 None if brief is None else brief.model_dump(exclude_unset=True, exclude_none=True),
                 None if issues is None else [x.model_dump(exclude_unset=True, exclude_none=True) for x in issues],
                 None if claims is None else [x.model_dump(exclude_none=True) for x in claims],
                 None if legal_review is None else legal_review.model_dump(exclude_none=True))
    return attach_delivery(cases, case_id, result)


@mcp.tool()
@friendly_errors
def assess_employment_terms(case_id: str, review_stage: str, citations: list[Citation],
                            request_id: str = '', supersedes: str = '',
                            scenario_citations: list[Citation] | None = None,
                            extract_parameters: StrictBool = False) -> dict:
    """保存本案原文条款与阶段核验清单；review_stage为hiring录用、change变更、noncompete竞业、payroll工资对账。

    先read_case_material；citations须1至30条path/quote/sha256/chunk真实引用，原句重复时可带精确start/end位置。保留拟议、否定和未知，拒绝跨案、过期及改写来源。
    程序生成阶段条件与完整出处，不自动认定条款有效/无效、义务成立、实际应付款或行为状态。
    recorded成功后用read_case_note回读，export_case(note_ids=[id],audience="internal")导出同记录。
    request_id仅同参数重试；supersedes仅明确更正。最终使用user_summary和真实文件，不补未归档判断。解除另用assess_employment_termination。
    scenario_citations可选，至多10条来源中独立完整假设行；程序核算后与清单、Word和最终交付保持一致。只接受以下格式（数字据真实原文，不得伪造假设或截掉否定）：
    hiring：“试用期核算假设：固定期限12个月，试用期6个月。”（固定期限12个月也可替换为无固定期限或以完成任务为期限）；
    hiring：“试用工资假设：合同工资10000元，同岗最低档工资9000元，适用最低工资2500元，拟试用工资7000元。”；
    noncompete：“竞业期限假设：离职后竞业36个月。”。change不接受核算。仅情景对照，不认定实际欠薪或约定整体效力。
    payroll配合extract_parameters=true提取工资表物理行或分号分隔键值行，字段为姓名(或劳动者)、工资期间(或月份)、应发工资、代扣合计、实发工资；金额需明确元/万元，表格可继承元单位。期间须明确年月。按行计算应发-代扣-实发的账面差额，不认定欠薪或代扣合法性，不跨人/月/文件拼接或求全案总额。缺值只暂停对应行，其他行继续。读取所有相关片段及表头；不把原件改写成支持格式。此阶段不传scenario_citations。
    自然语言材料可设extract_parameters=true（仅hiring/noncompete）。程序从引用所在完整片段逐行识别带标签和单位的合同期限、试用期、工资或离职后竞业期限候选，保留原文位置。跨行关联要求原文有“劳动者：姓名；合同编号：编号”（也支持相邻两行），其后连续纯参数行才做候选关联；Word连续段落须逐片段引用，缺片段、空行、新身份头隔开。跨文件另须每份原件明示相同姓名、劳动者编号、合同编号（也支持连续三段），回读全部相关段落后查看cross_source_groups；不能模型补造编号或仅凭同名合并。否定、多个主体、版本、冲突值、未知参数或未解析行保留并暂停关联核算。相同参数换算后一致则只核算一次且保留所有来源；副本不增加证据效力。此分支无需伪造scenario_citations或把候选改写成用户已确认假设；最终原样交付包含候选边界的user_summary。
    """
    from employment_decisions import assess_employment_terms as assess
    return attach_delivery(cases, case_id, assess(cases, case_id, review_stage,
                           [x.model_dump(exclude_unset=True, exclude_none=True) for x in citations], request_id, supersedes,
                           None if scenario_citations is None else [x.model_dump(exclude_unset=True,exclude_none=True) for x in scenario_citations],extract_parameters))


@mcp.tool()
@friendly_errors
def assess_employment_termination(case_id: str, citations: list[MaterialCitation],
                                  request_id: str = '', supersedes: str = '',
                                  scenario_citations: list[MaterialCitation] | None = None) -> dict:
    """保存来源约束的劳动解除初审：逐字材料＋固定条件清单，不自动决定适用路径。

    citations每项须path、quote、sha256、chunk；先read_case_material取原句和当前版本。拒绝跨案、失效或不匹配原文。
    不接受模型自定true/false事实；未访谈不推无调查证据。程序列明协商解除、39/40/41条、期满、违法解除各自条件，不能简化为一律N/N+1/2N。
    不自定工资基数、解除日或工龄；显式情景金额另用calculate_employment_amount。返回id可用export_case(note_ids=[id])生成Word，完成说明使用user_summary，不另改写路径或事实。
    同时要求情景算术并归档时，scenario_citations引用原始材料中独立完整一行“情景假设：基数10000元，折算年限8.5年，倍数2。”（示例不能充当本案假设）。
    各项从原句解析后调用同一精确计算程序，与清单存为同一笔记和Word，不相加、不认定实际应付；没有明确原句时拒绝而不猜参数。
    """
    from employment_decisions import assess_employment_termination as assess
    return attach_delivery(cases, case_id,
                           assess(cases, case_id, [x.model_dump() for x in citations], request_id, supersedes,
                                  None if scenario_citations is None else [x.model_dump() for x in scenario_citations]))


@mcp.tool()
@friendly_errors
def save_source_bound_register(case_id: str, domain: str, entries: list[RegisterEntry],
                               request_id: str = '', supersedes: str = '',
                               document_type: str = '', filename: str = '',
                               tracking: ComplianceTracking | None = None,
                               source_groups: list[SourceGroup] | None = None) -> dict:
    """保存公司/合规/IP来源台账；仅登记本案原句和上下文，不把缺记录当未发生。

    domain=corporate/compliance/ip；entries每项仅field与citation{path,quote,sha256,chunk}，先read_case_material。
    corporate字段agenda/entity/participants/notice/meeting/votes/decision/signature/mandate/debt/follow_up；
    compliance字段obligation/responsible_party/scope/deadline/feedback_deadline/report_deadline/decision/submission/implementation/acceptance/evidence_status；
    ip候选分类asset_type/jurisdiction/intended_use/application_place/applicant/inventor/agent/registered_holder/licensor/licensee/license_scope/status/date_context/fees；也接受filing_date/certificate_term/internal_estimate候选。
    所有领域的field都仅是模型未核验分类，单列classification_audit（不是事实字段）；实际保存条目均为source_excerpt原文，不把分类当事实值。
    多议题/多义务/多资产用source_groups，最多20组，每组{subject_entry,entries}都是本次entries的0起始索引，entries必须含subject_entry。组内不重复相同原文，未分组或共享原文显式保留，不能靠分组认定法律关系或权利状态。输出正文及台账均保留该关联。
    corporate需要纪要时填document_type=minutes及filename；proposal仅为任务已明确的股东会担保拟议案骨架，不用于其他议案或替用户选择有权机关。
    正文由程序生成，完整出处保存在笔记；其余返回id可用export_case(note_ids=[id])导出。
    合规跟踪可传tracking{as_of,as_of_entry,deadlines:[{entry,date,year_basis}]}；索引对应本次entries从0起，日期为YYYY-MM-DD。
    参考日须有原文完整日期；截止日期year_basis=explicit须原文完整日期，same_as_reference_assumption须明确月日并显著标同年假设。
    程序计算自然日差并保存条件建议；不判断法律期间或是否已履行。已有决定和发送记载照录，缺回执不改为未发送。
    不接收模型自填实际状态、票数结论或法律有效性。IP附历史法条件，证载期限不等于当前有效。最终完成说明使用user_summary与实际文件。
    """
    from source_bound_registers import save_source_bound_register as save
    result = save(cases, case_id, domain,
                [x.model_dump(exclude_unset=True, exclude_none=True) for x in entries],
                request_id, supersedes, document_type, filename,
                None if tracking is None else tracking.model_dump(exclude_unset=True, exclude_none=True),
                None if source_groups is None else [x.model_dump() for x in source_groups])
    return attach_delivery(cases, case_id, result)


def main():
    global cases, hearings
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', default=str(Path(__file__).resolve().parents[1] / 'workspace'))
    args = parser.parse_args()
    materials = MaterialStore(args.workspace)
    cases = CaseStore(materials)
    hearings = HearingStore(cases)
    # Reuse the existing non-overwriting Word writer in this workspace-bound process.
    material_server.store = materials
    mcp.run(transport='stdio')


if __name__ == '__main__':
    main()
