"""Repair only the 33 assigned workbench adapters; preserve the source library."""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / 'docs/checks/skills-repair'
SKILLS = ROOT / 'workspace/.dsh/skills'
ITEMS = json.loads((CHECKS / 'group-c.json').read_text(encoding='utf-8-sig'))

COMMON = '''## 材料与执行

仅用当前请求授权的案件和材料。事实按“来源/陈述者—原话或准确转述—能支持的内容—未知项”整理；本次未提供证据、程序中未提交证据、事实未发生是三种状态，不能互换。未知就在相关结论处保留，不靠末尾免责声明修补确定断言。

现行法和案例以实际核验的来源、版本、位置为准；给定假设规则时只在该假设内分析。案件归档、版本和文书导出复用 `qx-case-work`，用户限制不写入时只交付正文。按实际工具结果报告检索、保存、送达状态；未执行就是未执行。外发、法院提交、跨案读取须有本次相应授权。
'''

SPECS = {}

def spec(name, action, trigger, reason, body, checks, replacement=None):
    assert name not in SPECS
    SPECS[name] = dict(action=action, trigger=trigger, reason=reason,
                       body=body.strip(), checks=checks, replacement=replacement)

def disabled(name, reason, alternative):
    spec(name, 'disable', 'an administrator inspects this retired adapter; unavailable for legal workbench invocation.',
         reason, f'''此入口已停用，仅保留原名和来源供迁移核对。

停用原因：{reason}

当前工作台替代：{alternative}

这里不执行原教学/管理流程，不把未知人员、安装来源、时间或学习进度补成事实。原始资料仍只读保留；恢复需另行评估与明确配置。''',
         ['disable-model-invocation: true', 'user-invocable: false', '当前工作台替代'])

disabled('chinese-legal-law-student', '法考、课堂教学总入口不属于当前律所实务工作台，原入口会继续分派已停用教学技能。',
         '实务案件摘要使用 qx-case-work；法考或课堂辅导没有已验证的工作台替代，不自动转成实务任务。')
disabled('legal-zh-builder-hub-customize', '旧 Claude 插件中心的画像与版本管理混合，风格调整可能误改固定 SHA 或安装元数据。',
         '单次文风直接在当前任务说明；工作台配置修改按明确文件和字段单独处理，不从本技能写全局配置。')
disabled('legal-zh-builder-hub-uninstall', '旧 Claude 卸载机制和安装来源尚未认证适用于本工作台，不能推定由本中心安装。',
         '通过当前工作台实际技能清单核对来源和依赖，再按明确管理请求生成具体变更；本入口没有卸载执行能力。')
disabled('legal-zh-clinic-semester-handoff', '学生离届、学期和导师分配是教学诊所制度，当前律所工作台没有该制度或名册。',
         '律师案件交接使用 qx-case-work 的本案记录与待办，只列有来源的已完成事项；不模拟学期离届人数。')
for suffix, label in [
    ('bar-prep-questions', '法考试题生成'), ('exam-forecast', '历年考题与考点预测'),
    ('flashcards', '法条记忆卡片'), ('outline-builder', '法学课程大纲'),
    ('session', '专项教学练习'), ('study-plan', '法考学习计划')]:
    disabled('legal-zh-law-student-' + suffix, f'{label}属于教学备考功能，当前律所实务工作台不支持其课程、训练与学习状态管理。',
             '不提供同等教学替代；实际案件中的规则、证据及文书问题使用 qx-case-work。不得把假设题变成现行法结论或把学习计划改名冒充办案能力。')

spec('legal-zh-clinic-client-comms-log', 'repair', 'the user records, reads or summarizes communications for an authorized matter.',
     '将真实沟通与计划联系分区，去掉默认现在/内部节点作沟通日期和旧全局日志路径。', '''
保留按案追加、阅读、摘要和跟进模式。先识别输入是在描述已发生沟通，还是拟发送的文字/未来待办。

## 输出顺序

1. **已发生沟通**：每条列实际发生日期时间（未知即待补）、方向、媒介、参与者及已知身份、原始来源、2–4句内容摘要。没有发生记录时写“本次未提供已发生沟通”，不创建空壳历史条目。
2. **后续待办**：拟联系对象、目的、负责人、计划日或内部补件节点、完成状态。T1 等补件日只在这里出现，不替代通话/邮件发生日。
3. **跟进摘要**：仅在实际日志范围内计算次数、最近联系、未回复事项。没有日志就不推断无人回复或长期失联。

需要保存时通过 qx-case-work 追加本案记录；更正引用原条目并保留历史，不覆盖。起草或导出信函不构成已发送记录；只有用户确认发送事实或工具回执才可记为发出。内部策略留在内部工作稿。''',
     ['已发生沟通', '后续待办', '不替代通话/邮件发生日', '起草或导出信函不构成已发送记录'])

spec('legal-zh-clinic-deadlines', 'repair', 'the user records or reviews matter deadlines and internal follow-up dates.',
     '将日期登记与期间计算分开，以明确基准日和可计数条目生成预警，不臆测导师日期或完整台账。', '''
## 登记与报告

每条列：案件、事项、日期/时间/时区、日期性质（法定/法院指定/约定/内部计划/待核）、来源、负责人、状态。来源缺失的法律期限保持待核；内部材料提交日保留为内部计划。未知日期或导师审阅时间独立列出，不纳入到期计数。

报告先给**评估基准日**及其来源、所用台账范围。系统时间或用户指定时点可作为基准；均未获得时仅列日期，逾期数及未来7天数写“无法计算”，不猜当前日期。日期已知时计算日历天差并说明口径：逾期为截止日早于基准日且未有完成/关闭记录；今天为0；未来7天为1–7天；8–14天另列。缺少完成信息的条目标“状态待核，日期已过/将到”，与确定逾期分开。

例：基准日2026-11-04、内部节点2026-11-10，相差6天，列入未来7天内部安排；这不是法定期限核验。未知日期不等于零条。

新增先查当前授权台账内重复项；更新保留原日期及变更来源；完成需要实际提交/送达或完成记录；关闭保留原因。报告不自动改状态，也不创建推送。法律期限需先核触发事件、送达日期、期间规则和适用法，不能拿内部安排替代。''',
     ['评估基准日', '未来7天为1–7天', '未知日期不等于零条', '报告不自动改状态'])

spec('legal-zh-clinic-draft', 'merge', 'a legacy clinic drafting request concerns a real matter document.',
     '实务起草复用qx-case-work，移除默认教学guide模式及未经提供的导师签字制度。', '''
本入口保留旧名，实务起草统一使用 **qx-case-work**。不再执行教学诊所的 guide/teach 分叉；这不代表替代课程教学。

按请求交付连贯、可编辑正文：当事人和请求、材料支持的事实与来源、理由、结尾。必要的未知字段就地占位，内部待核清单单列。文书类型已明确就直接写，不强制补全机构画像。

如用户明确给出导师/律师审阅要求，准确保留原要求；“审阅”不扩成必须签字或已批准。文件是待审草稿，生成或保存不等于提交/发送。文书出具日期与内部交稿节点分开。

管辖机构与法律依据栏只填实际提供或核验的内容；仅给假设事实且禁止检索时填写“管辖及适用规则待核”，不按记忆写管辖规则。''',
     ['qx-case-work', '不再执行教学', '“审阅”不扩成必须签字'], 'qx-case-work')

spec('legal-zh-clinic-plain-language-letters', 'merge', 'a legacy request asks for a plain-language client letter about matter progress.',
     '重复的通俗信函入口合并到状态沟通，去除可发送与待审矛盾。', '''
兼容入口：使用 **legal-zh-clinic-status** 的当事人模式，正文写清已有进展、待核事项、下一步与对方需提供的材料；归档或导出使用 qx-case-work。

交付明确为“供审阅的沟通草稿（尚未发送）”，审阅和发送状态按真实记录说明；上层“可发送回复”只是正文分区标签，不表示已经审阅或实际发送。不据该标签新增已批准、已核实、已通知的事实。

期限段使用两句结构：“[日期]是内部补件安排。相关法律期限及对权利的影响尚待核实。”此处只能确认日期性质，不判断有无权利影响；“不影响任何权利”或“无需其他行动”均不是内部安排可推出的结论。''',
     ['legal-zh-clinic-status', '供审阅的沟通草稿', '权利的影响尚待核实'], 'legal-zh-clinic-status')

spec('legal-zh-clinic-research-start', 'repair', 'the user needs a legal research starting point or a gap review of supplied research.',
     '保留检索路线图，按未提供/未读取/实际检索未命中区分状态，去掉默认读取诊所种子文件。', '''
交付检索路线图，不冒充检索结果。先从已给材料明确法域、争点和希望解决的问题；不足时列必要缺口并继续给有用关键词。

## 路线图结构

1. **现有材料状态**：用户未给文件＝“本次未提供”；有路径但未读取＝“尚未读取”；只有实际查过明确范围才能写“在某范围、关键词与时间下未检索到匹配”。没有查文件不能写文件不存在或无匹配。
2. **已知内容**：用户材料的原话、位置与适用范围；内部备忘录是线索，不自动视为已核现行法。
3. **待查问题与来源**：按争点列待查法律问题、一手来源类别、检索词、法域/时间条件和需核版本；没有实际原文不编具体条号、裁判号和引文。
4. **下一步验证**：对每个缺口写查什么、为何影响结论、如何核对。只有工具真实返回的结果才列在“已检索”，其余列“计划检索”。

用户限制只按假设材料时，基于该材料完成问题拆解，其他规则明确不在本轮结论范围。''',
     ['本次未提供', '尚未读取', '实际查过明确范围', '计划检索'])

spec('legal-zh-clinic-status', 'repair', 'the user asks for a client, internal or court-facing status summary of an authorized matter.',
     '按事实状态生成面向受众的正文，删除默认正在核对/目前无需操作和教学身份签名。', '''
选择用户指定的 client/internal/court 受众；未指定时先给内部简报，不自行外发。

先整理“已完成（来源/日期）｜正在进行（实际执行记录）｜拟办（负责人/计划日）｜未知/待核”。“已完成”只填用户报告或工具记录的完成动作；仅提供案情，不算已经接待、登记或入库。程序阶段与立案/提交状态另设来源字段，没有记录就填“未知”，不由尚未联系客户推断“咨询阶段、未立案、未提交”。只有拟联系、待核的材料不能写成“已联系”“正在核对”；没有进展记录就如实说明本次材料未显示进展。

- **当事人正文**：用普通语言写已知情况、需要补充什么、下一步拟做什么；明确内部安排与尚未确认的法律期限。联系方法、签署人、律师/学生身份只有用户给出才使用。不能因暂无记录就承诺“目前无需任何操作”。
- **内部简报**：程序状态、已完成与待办、关键日期性质、需要决策的问题和资料缺口。负责人、审阅状态未知就保留未知。
- **法院报告草稿**：依已提供的法院要求组织，只写有依据的程序进展，格式和期限未核则注明待核。

输出可编辑沟通草稿，内部来源说明另列。上层“可发送回复”标签不表示已完成审阅或发送，也不新增审批要求；实际状态仍据记录填写。草稿、审批、排队、发送分别记录；建议动作不是完成事实，未获结果不记为已办。''',
     ['正在进行（实际执行记录）', '拟办', '不能因暂无记录就承诺', '建议动作不是完成事实'])

spec('legal-zh-clinic-supervisor-review-queue', 'repair', 'the user explicitly supplies a review queue or asks to prepare review entries.',
     '保留可用的审阅条目整理，不把缺配置判断成休眠，也不模拟批准或通知。', '''
先给队列状态：有当前配置或系统查询结果才判已启用/未启用；无配置写“启用状态未确认”。状态未知时仍可根据所给文稿生成待审条目，不新增制度要求。

每项列：案件、文稿ID/版本、提交者、拟审阅者（未知即待补）、提交时间、要求审阅原因、相关日期及性质、内容位置、状态及证据。未实际入队的列“待审条目草稿”，不报队列总量或等待时长。只有读取完整授权队列并有基准时点，才汇总数量和等待时间。

对批准、编辑后批准、退回：记录明确决定者、决定内容、时间和对应文稿版本；没有真实决定记录则保持待审，助手不代替人批准。修改保留旧版；起草审阅条目不表示发送通知。没有执行工具时交付清单并说明尚未入队。''',
     ['启用状态未确认', '待审条目草稿', '助手不代替人批准'])

spec('legal-zh-criminal-bail-application', 'repair', 'the user requests a bail application or custody-necessity review draft.',
     '按阶段与措施类型分支处理，不把未知措施日起算羁押，不默认退赔、保证金或随传随到承诺。', '''
## 先确定程序，再拟正文

列“程序阶段｜现强制措施类型｜决定机关｜采取日期及来源｜实际羁押起点及凭据｜申请人身份/权限”。未知字段就地待核。只知采取强制措施日期不能认定刑拘、逮捕或已被羁押，不能据此计算羁押天数/期限届满。

阶段、措施或是否羁押任一未知时，申请事项栏只写“请求依法审查变更强制措施的适当路径，具体类型及受理机关待核”。不展开取保/羁押必要性审查条件分支，更不能把“未羁押”接到羁押必要性审查。只有措施与适用规则已核实才选择程序；申请人身份未知就留空，不把信息提供的母亲自动填为申请人，也不把已知母子关系写成关系未知。

按实际核验的适用规则，将法定条件、社会危险性、健康/家庭情况、认罪情况、退赔/谅解逐项与来源对应；“家属称已退赔”保持归属，缺转账凭证只表示付款情况未核实。无证明的初犯、身体情况、罪轻、不具危险性不得填成肯定理由。

交付：申请事项（类型/机关待核）、已有材料支持的事实与理由正文、附件清单、必要补件。担保方式、保证人资格、支付保证金意愿、到案承诺分别为“待申请人确认”，用户没有表达时不代写其已承诺。申请日期不得借用内部补件日。

例：材料仅写“11月1日采取措施”，对应记录为“措施类型及是否羁押待核”，不写“自11月1日起羁押”。''',
     ['实际羁押起点及凭据', '不能据此计算羁押天数', '待申请人确认', '付款情况未核实'])

spec('legal-zh-criminal-case-analysis', 'repair', 'the user asks to compare criminal evidence, statements, contradictions or missing links.',
     '保留供述与客观证据比较，将否定事实、缺件及量刑因素分栏，消除缺付款凭证推断未退赔。', '''
用当前授权材料编制“证据/位置｜陈述者｜原话或转述｜支持的事实范围｜有利/不利意义｜待核”。必要个人标识使用代称，不因可分离标识要求整案重交。

输出依次为证据概况、按事件合并的时间线、具体矛盾、证据缺口、补证/询问建议。矛盾必须是同一事项存在不能同时成立的说法；记不清、未提及、未提供凭证不是相反证据。供述变化只是需核线索，不能直接认定刑讯或虚假。

退赔单列“谁称已退赔、金额/时间说法、现有凭证、核实状态”。无付款凭证写“本次材料缺凭证，退赔情况未核实”；不改成“退赔尚未发生/未实际退赔”。材料明确否认付款时保留该否认及来源，也不能擦成完全未知。谅解书、退赔、认罪认罚分别核实，不能互相代替。

区分定罪证据、量刑材料与程序问题；仅有部分卷宗时，结论范围限于这部分，不能认定整个案件只有孤证或已排除合理怀疑。涉及排非或定罪标准先核适用规则。''',
     ['不能同时成立的说法', '退赔情况未核实', '定罪证据、量刑材料与程序问题'])

spec('legal-zh-criminal-compliance-non-prosecution', 'repair', 'the user reviews an enterprise compliance plan in a criminal matter or asks about non-prosecution options.',
     '保留整改差距分析，把程序适用性独立待核，不从侦查阶段直接排除合规机制。', '''
先列涉嫌事项与来源、企业/个人各自角色、程序阶段、已知整改内容和本轮目标。涉嫌罪名、单位犯罪、个人责任不能从企业名称或整改计划推定。

退赔/配合情况用四列：“陈述者及原话｜意愿或行为说法｜本次凭证｜核实状态”。“愿退赔”只能记为意愿；缺凭证的状态为“退赔情况未核实”，不是“退赔未发生”。正式启动、整改落实也只填已知记录，没有启动/运行记录时写“本次未提供”，不写“尚未启动/无任何执行”。

分别交付两部分：

1. **整改计划差距表**：问题/风险—现有措施与证据—缺口—建议—验证材料。围绕与涉嫌事项相关的组织职责、业务控制、培训、举报与保护、监督整改、第三方风险及运行记录审查。建议不是已经落实，缺少材料不是证明制度不存在；组织独立性、整改有效性需具体核查。
2. **程序适用待核表**：程序阶段与机关、所请求机制、法域/现行规则、申请资格与材料、待核结论。处于侦查阶段只是已知状态，不能单凭阶段断言不具启动条件；正式启动、主动整改、争取从宽和不起诉结果分别说明。规则未核时不承诺或排除不起诉，不将企业整改写成个人责任自动切割。

输出一组与当前风险相连的可执行改进建议和补件，保留法律适用核验状态，不照抄旧参考中的条号作为现行依据。''',
     ['整改计划差距表', '程序适用待核表', '不能单凭阶段断言', '不将企业整改写成个人责任自动切割'])

for domain in ['criminal', 'litigation']:
    spec(f'legal-zh-{domain}-matter-workspace', 'merge', 'the user invokes a legacy matter-workspace request.',
         '与当前案件工作流重复，移除活跃事项全局切换和旧插件目录管理，统一显式案件ID。', '''
兼容入口：调用 **qx-case-work** 处理本次明确案件的创建、读取和记录。按其真实工具能力执行；不再维护旧插件的活跃事项、全局 switch 或归档目录。

已有案件用明确 case_id；同名多案不猜，不因家属提供信息就把其列为委托人。家属身份、委托关系、律师授权分别记录。关联案件未知写“未知/本次不检索”，不能写“无”；跨案授权另行判断。

输出字段固定区分“用户拟定代号｜实际case_id｜建档状态”。例如demo-a只能填拟定代号；实际case_id未由已知记录或工具返回时填写“待创建后返回”，不以代号冒充。未执行建案时不填写建档日期或进行中状态。委托资料未提供写“签署状态未知/本次未提供”，不能填“未签”。仅收当前操作必需的最小字段，身份信息按需要用代称。下一步明确交给qx-case-work，不另造平行目录管理。

用户请求的列表、归档或切换只有实际工具支持且范围明确才执行；否则交付未执行的具体方案，不伪造已切换或已归档结果。''',
         ['qx-case-work', '明确 case_id', '未知/本次不检索', '家属身份、委托关系、律师授权分别记录'], 'qx-case-work')

spec('legal-zh-law-student-case-brief', 'replace', 'a legacy case-brief request seeks a source-backed practical case summary.',
     '原技能默认学生自行作答，与办案摘要冲突；明确改为qx-case-work实务摘要替代，原教学能力不再执行。', '''
此旧名兼容入口已由 **qx-case-work 的实务案例摘要**替代。原技能是课堂引导，并非完整代写；本工作台不再宣称或执行其训练模式。

用户提供裁判全文/片段时，直接交付“来源与覆盖范围、基本案情及陈述归属、审理经过、争点、该文本实际载明的裁判结果/理由、适用限制”。只有案例名称时，先获取真实文本；无法获取则给已知信息与缺口，不从记忆补案号、结果或裁判理由。

假设案例可按给定规则完成分析，但标题注明假设，不写成真实法院裁判。规则未说明交易可分割或可部分追认时，不推定超额交易当然切成授权内与授权外两部分；写明该问题尚待规则或条件补足。此分支的分析单位是“一笔交易”，只写“订购数量超过授权；整笔交易如何适用追认规则、能否拆分待补规则”，数量差只是算术，不写“授权内部分已约束本人/超出部分效力待定”。摘要各段包括争点和结论保持同一范围。摘要请求直接交付已有材料能支持的内容，不要求用户先自己写答案。''',
     ['原技能是课堂引导', '假设案例', '不推定超额交易当然切成', '直接交付'], 'qx-case-work')

spec('legal-zh-litigation-brief-section-drafter', 'repair', 'the user asks to draft a substantive section of a litigation document or oral argument.',
     '保留实质段落、精确引用及反论点，区分签收与履行、内部节点与成文日。', '''
按用户指定章节和书面/口头用途起草；用途未知时默认书面草稿。先核我方地位、所求结论与材料来源，未知用中性称谓，不从原告/被告模板补角色。

交付连贯实质段落，按“主张及其归属—证据能证明的范围—推理前提—对方主张及回应”展开。原句确切才加引号，引用位置必须支持完整命题；不利材料及论点限制在相关论点处说明。

合同约定交货日和物流签收日是两类记录；可描述相差日历天数，认定迟延仍取决于交付方式、履行节点与变更约定。签收是否等同实际交付一律按已知条款判断；条款未知时用“尚不能判断是否等同”，既不写“就是交付日”，也不写“并非交付完成时间”。不能把没有延期材料写成未达成延期或对方未向法院举证。

文末仅列关键待核事实、规则及内部来源说明。成文日期用明确出具日，无则待补；内部提交节点另列，不自动填在标题或落款。口头提纲则保留最有依据的要点和可能回应，不替用户补事实。''',
     ['物流签收日是两类记录', '对方主张及回应', '成文日期用明确出具日'])

spec('legal-zh-litigation-claim-chart', 'repair', 'the user requests a civil elements chart or a patent claim-to-evidence comparison.',
     '把映射状态落到单个命题，避免局部条款证成合同整体或日期不明否定证言整体。', '''
按请求区分民事要件与专利权利要求，不用默认立场。民事先列诉请/抗辩及规则核验状态；专利先列专利号、具体权利要求、目标及侵权/无效/审查模式，原文未给则标缺口。

## 交付

先列影响最大的缺口，再按表输出：

| 单一要件/命题及依据 | 支持材料与精确位置 | 具体相反材料/主张及归属 | 当前可支持范围 | 缺口与补证 |
|---|---|---|---|---|

每个映射仅覆盖该条内容。合同局部条款载明日期，只能支持该日期约定的文字，合同成立、效力、完整内容分别待核。证人记不清日期只影响该日期线索，不能据此评价全部证言无证明力。“本次材料未见相反证据”不是“对方没有证据”，也不证明程序中尚未举证。主张、表达媒介分开：材料只说“对方称”就保留该表述，口头/书面/聊天方式未知，不补成口头主张。日期没年份就保留原形式，待核年份，不按评估日推年份。

专利逐要件映射，争议术语列待解释；从属权利要求展开所引用的全部要件。侵权与无效分表；无效分析保留文献公开时间、单篇公开与组合论证区别，不把多篇拼接直接写成单篇已披露。结论限于证据覆盖和待核事项，不直接裁定侵权/责任。

按用户需要导出Markdown/CSV/表格，保留引文来源。写入CSV或表格前，将来自材料且以等号、加号、减号、@、制表符或回车开头的值按文本转义，避免公式执行；未实际导出不报路径。''',
     ['单一要件/命题', '合同成立、效力、完整内容分别待核', '从属权利要求展开', '按文本转义'])

spec('legal-zh-litigation-demand-draft', 'repair', 'the user requests a demand letter or a draft reply to an opposing party.',
     '保留连贯律师函及内部风险复核，精确保存约定日期，去除可发送保证和未核法条标签。', '''
从已给委托信息直接起草供审阅的函件正文；主体、受函人、授权、请求或金额未知时就地占位。事实、具体要求、所依据的约定、回复方式及落款依序组织；内部核验清单与对外正文分开。

逐字引文须有原文和位置。日期、金额、主体及期限含义忠实保留：“2026-04-01交货”不能改成“4月1日前交货”。签收记录与合同交付认定分别表述，延期主张保留对方归属，未提供材料不写成延期不存在或对方未举证。

请求对方补件时正文直接写“请提供支持该主张的材料”。“本次分析未提供”只属于内部材料范围，不能改成函中“截至发函我方未收到/贵方从未提供”，因为收到范围和未来发函状态均未确认；草稿也不能创造这些过去或未来事实。

正文只使用有依据的主张；尚需核验的事实在该句限定，不靠结尾免责声明。回复期限区分用户指定、建议期限与法定期限；未知起点不算确定截止日。

附简短内部检查：委托/签署权限、保密内容、自认或权利放弃风险、和解措辞、请求与救济依据、发送方式和送达证据。措辞不自动获得保密特权或时效效果，须核适用规则与实际行为。通过真实工具生成文件才报告生成路径；起草不授权外发，也不记录已发送。''',
     ['供审阅的函件正文', '不能改成“4月1日前交货”', '起草不授权外发'])

spec('legal-zh-litigation-demand-intake', 'repair', 'the user registers instructions and facts for a demand letter.',
     '用来源化字段替代固定八问和虚构沟通史，保留策略与外发边界。', '''
用已给信息预填登记，不重复问已知事项：函件类型；发函方/收函方及我方地位；触发事件及来源；合同/法律依据状态；期望请求；回复日期性质；先前沟通；允许公开的信息和签署授权。发函主体与已成立的委托人身份分栏，前者已知不证明后者成立，未知授权不写“委托人已知”。

“先前沟通”只有具体材料支持才填日期、媒介、内容和参与者；没有记录写“本次未提供”。对方称双方同意延期时，只记“对方提出延期主张，现有支持材料待补”，不补成口头约定、已交涉或双方确认。

按必要性另列和解目标、可接受替代方案、不利材料和保密/自认风险；这些是待决策事项，不能填默认客户底线。日期保留原含义，签收日不能直接认作履行日。

交付登记草稿与起草所需的关键缺口。用户已要求拟函时继续产出可用草稿；归档用 qx-case-work，工具未保存不称已入库。''',
     ['本次未提供', '不补成口头约定', '待决策事项'])

spec('legal-zh-litigation-demand-received', 'repair', 'the user supplies a received demand letter or seeks triage of an alleged incoming demand.',
     '来函缺失时先承认输入缺口，主张方向固定分栏，避免把我方主张反转成对方来函指控。', '''
## 先核输入是否是来函

有来函原文时，提取发函人、收函人、收到日期/方式、函件主张、请求、期限和下一步措施及出处。只有纠纷摘要而没有来函时，标题为“纠纷材料预分析（来函未提供）”，这些来函字段待补；不把案情重新编成已经收到的指控。

## 主张分栏后回应

| 提出者及来源 | 提出的主张 | 支持材料及范围 | 我方回应/待核 |
|---|---|---|---|

“拟主张迟延交货”属于用户拟主张；“对方称同意延期”属于对方抗辩，两者不能倒置。甲乙与我方关系未知则保持代号和未知角色。缺延期材料只能写本次未提供，不能据此断言未约定或程序上未举证。物流签收与法律交付区别分析。

给有依据的初步回应要点、证据保留/补件和回复选择的条件；来函和关键期限未给时，不直接推荐暂搁置/不回复或保证无需行动。法律期限、来函自定期限和内部T1分别列出。

仅在明确跨案授权与真实查询结果下关联其他案件；否则写本次未检索。函件回复另交草稿，不发送。''',
     ['纠纷材料预分析（来函未提供）', '提出者及来源', '两者不能倒置', '不直接推荐暂搁置/不回复'])

spec('legal-zh-litigation-deposition-prep', 'repair', 'the user prepares neutral witness questions, testimony review or an examination outline.',
     '先核身份与亲历范围，问题采用开放事实，不填物流职业/中立立场，不以不记得推成不在场。', '''
先整理证人代号、已知身份/关系及来源、是否亲历及信息来源、既有陈述及位置；未知就保留未知。证人A仅说记不清日期时，不能补成物流经办人、乙方员工、中立第三方或未在场；我方/对方证人身份也须来源。

按用户所需问题数交付，不扩大成完整模板。每个问题对应一个待核事实和已知材料，先开放询问：

1. 您与本事项有什么关系，了解哪些环节？
2. 您记得哪些事情，是亲眼看到、亲自参与还是从其他途径了解到的？
3. 对于记不清的日期，有哪些记录或事件可以帮助核对？

以上是问题结构示例，按当前争点调整；不要求证人认同预写答案。只有已有来源支持前提时才用锁定式问题，并列出依据。不得将“您未在场，对吗”或“作为物流经办人”作为无依据前提。

提纲按背景、亲历事实、相关文件、具体不一致、需澄清事项组织；有利/不利仅是对案件主张的关系，不是证人的预设立场。引文逐字可定位。记不清、矛盾、虚假证言分别处理，不教证人填补记忆或统一口径。''',
     ['已知身份/关系及来源', '亲眼看到、亲自参与还是从其他途径', '不要求证人认同预写答案'])

spec('legal-zh-litigation-matter-intake', 'repair', 'the user registers a new litigation or dispute matter.',
     '保留登记核心，将身份、利冲、程序、日期事实与法律认定区分，归档复用现工作台。', '''
先用已有材料交付登记草稿：案件名称；主体及我方角色/委托关系；请求和对方说法；来源与争议事实；阶段/机关；关键日期及性质；负责人；风险与需核材料。未知角色不默认原告/被告，家属信息不等于委托关系。

合同约定交货日、物流签收日分别记录；可算两日期的日历差，不能直接作为法律迟延天数。交付条款、变更约定、我方地位待核时，风险写为“是否迟延交付待核”。内部T1不是已核法定期限，登记日期不是立案日期。计划整理日填在“计划事项/日期”栏；仅实际登记工具回执或用户报告的已完成登记可填写“实际登记日期”，未来内部整理日不能标已记或已完成。

利益冲突与关联案件列检查状态和授权范围：未检索写未检索；缺资料写待核，不能填无冲突或无关联案件。仅在授权范围内核对，不自动扫描别案。

下一步列证据保留、紧急期限核实、补件与具体负责人（未知就待定）。实际建案/记录用 qx-case-work，保存成功才报告ID和位置，不写旧插件日志。''',
     ['是否迟延交付待核', '登记日期不是立案日期', '未检索写未检索'])

spec('legal-zh-litigation-portfolio-status', 'repair', 'the user requests an overview of an explicitly authorized matter portfolio.',
     '基于完整程度和明确时点评估组合统计，不从单案或未知基准日断言零逾期。', '''
先列授权案件范围、实际台账来源/覆盖范围、评估基准日及来源。只给单案时产出该案摘要，不称完整组合；没有台账不能把未结数、风险数或逾期数填0。未给时间且无法获得可靠系统时间时只列原始日期，不判已逾期/未到期。

对实际读取的条目，按案件ID去重；明确是否含已结事项。按状态、阶段、已给风险等级及负责人汇总；空白各自记未知，不默认低风险。未知与已核总数分别显示。

节点分法律/法院指定、约定、内部计划、性质待核。以同一基准计算今天、未来1–14/15–30/31–60天及日期已过事项；完成状态未知的单列，不算确定逾期。陈旧案件须有上次更新时间和基准日，不能猜30天未更新。

输出最需关注事项、理由及来源、负责人和下一步；无机构风险阈值时不凭模型定义critical或把缺外聘律师认定违规。每个汇总保留覆盖数量与未知数量；不自动修改案件状态或读取未授权案件。''',
     ['评估基准日及来源', '没有台账不能', '完成状态未知的单列', '覆盖数量与未知数量'])

spec('legal-zh-litigation-privilege-log-review', 'repair', 'the user requests first-pass authenticity, legality and relevance review of evidence.',
     '移除默认可采标签，以三性、证明力、程序状态独立列项，资料缺失时不下可采结论。', '''
这是证据三性初审。原名保留兼容，不表示提供英美法特权认定。先确定待证事实、程序/法域和材料范围；未给的角色、法域、审级保持待核，不从甲乙顺序补乙为交货义务人或默认民事一审。未知时待证事实用中性表述“是否发生迟延交付”。逐项输出：

| 证据及位置 | 真实性（原件/来源/完整性） | 合法性（形成/取得方式及依据） | 与具体待证事实的关联 | 能证明的范围/证明力限制 | 程序提交状态 | 待核与补件 |
|---|---|---|---|---|---|---|

原件、来源、取得方式未核时，填写相应未知项；可写“与日期约定初步相关，可采性待核”，不得同时标“✅可采/无需行动”。资料缺失本身不证明虚假或违法，不据此建议自动剔除。

缺日期可能限制某个时间点的证明，记不清日期可能限制该部分证言；不等于整体无关联或无证明力。是否向法院提交只能按程序记录填写，不能从本轮未提供材料推定未举证。

对具体排除线索注明取得方式、待核依据与来源；规则未核时标需进一步审查，不用旧参考条号冒充法条原文。保留全部原材料及版本，提出审查建议，不代作法院采信决定。''',
     ['程序提交状态', '可采性待核', '不等于整体无关联或无证明力', '不代作法院采信决定'])

spec('legal-zh-litigation-subpoena-triage', 'repair', 'the user supplies or asks to triage an investigation order, assistance notice or witness summons.',
     '先核通知类型与原文，分开关联性、证明力和程序义务，不从日期不清推出异议理由。', '''
有通知原文时提取发出机关、文号、对象、请求行为/资料范围、签发日、送达事实、明示期限及依据；未提供原文时写“通知未提供”，只给待补字段和范围化准备，不虚构收到或送达。

依实际文本区分法院/律师调查令、行政协查、证人出庭或刑事/监察要求；未知类型不套用固定异议程序。刑事/监察部分列已知字段与需专业复核问题，不自行断言拒绝或不配合。

输出：请求范围与可能保管人（无来源不指定）—资料是否持有/能否取得—负担与保密问题—可考虑的回应或异议及其成立条件—期限待核/行动。跨案关联须明确授权与实际查询；证据保留建议不是已完成保全。

关联性问材料是否指向具体待证事实；证明力问该材料能证明到什么程度。无日期或记不清日期不自动构成无关联异议，也不决定是否必须协助；程序上的异议资格、方式和期间须核通知与适用规则。没有依据时只列核实问题，不代写确定异议结论。

对案情中的对方说法固定记录为“主张及归属｜本次支持材料｜待核问题”。只有主张但无支持材料时结论为“真实性/成立与否待核”，不写“单方陈述，不成立”，也不把此缺口作为通知异议依据。

分清送达日、法定期限、通知要求日与内部安排；起点未知不算确定截止日。拟回复和提交范围先可审查地展示，实际外发/披露需本次授权与工具执行结果。''',
     ['通知未提供', '关联性问材料是否', '不自动构成无关联异议', '起点未知不算确定截止日'])


def source_for(name):
    if name == 'chinese-legal-law-student':
        return 'zh/.dsh/skills/chinese-legal-law-student/SKILL.md'
    for prefix, domain in [('builder-hub', 'legal-builder-hub'), ('clinic', 'legal-clinic'),
                           ('criminal', 'criminal-legal'), ('law-student', 'law-student'),
                           ('litigation', 'litigation-legal')]:
        marker = 'legal-zh-' + prefix + '-'
        if name.startswith(marker):
            return 'zh/' + domain + '/skills/' + name[len(marker):] + '/SKILL.md'
    raise ValueError(name)


def sha(content):
    return hashlib.sha256(content).hexdigest()


def run():
    if (ROOT / 'config/skill-repair-freeze.json').exists():
        raise SystemExit('Reviewed batch is frozen; refusing to overwrite final adapters.')
    assert len(ITEMS) == 33
    assert set(SPECS) == {item['name'] for item in ITEMS}
    prior_path = CHECKS / 'group-c-changes.json'
    prior = {x['name']: x['afterSha256'] for x in json.loads(prior_path.read_text(encoding='utf-8'))} if prior_path.exists() else {}
    changes = []
    for item in ITEMS:
        name = item['name']
        plan = SPECS[name]
        path = SKILLS / name / 'SKILL.md'
        before_path = CHECKS / 'before' / name / 'SKILL.md'
        before = before_path.read_bytes()
        current = path.read_bytes()
        source = source_for(name)
        source_path = ROOT / 'workspace/legal-library' / source
        assert source_path.is_file(), source_path
        front = f'---\nname: {name}\ndescription: "Use when {plan["trigger"]}"\n'
        if plan['action'] == 'disable':
            front += 'disable-model-invocation: true\nuser-invocable: false\n'
        text = front + '---\n\n<!-- workbench-skill-repair-v2 -->\n\n# ' + item['chineseName'] + '\n\n' + plan['body'] + '\n\n'
        if plan['action'] == 'repair':
            text += COMMON + '\n'
        if plan['replacement']:
            replacement_path = SKILLS / plan['replacement'] / 'SKILL.md'
            assert replacement_path.is_file()
            text += f'当前入口：[ {plan["replacement"]} ](../{plan["replacement"]}/SKILL.md)。\n\n'
        text += f'原始方法与许可出处：[原库只读参考](../../../legal-library/{source})。本工作台适配不修改原始库；参考中的旧插件指令不在此执行。\n'
        encoded = text.encode('utf-8')
        # The reproducible repair may only start from the saved baseline or its own output.
        assert current in (before, encoded) or sha(current) == prior.get(name), f'Unexpected concurrent edit: {path}'
        for check in plan['checks']:
            assert check in text, (name, check)
        assert '~/.claude' not in text
        assert len(front) < 1024
        for link in re.findall(r'\]\(([^)]+)\)', text):
            assert (path.parent / link).resolve().is_file(), (name, link)
        path.write_bytes(encoded)
        entry = dict(name=name, action=plan['action'], reason=plan['reason'],
                     beforeSha256=sha(before), afterSha256=sha(encoded), criticalChecks=plan['checks'])
        if plan['replacement']:
            entry['replacement'] = plan['replacement']
        changes.append(entry)
    (CHECKS / 'group-c-changes.json').write_text(json.dumps(changes, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    counts = {a: sum(c['action'] == a for c in changes) for a in ('repair', 'merge', 'disable', 'replace')}
    print(json.dumps(dict(skills=len(changes), actions=counts, localChecks='names, disable flags, links, required contracts, hashes: PASS'), ensure_ascii=False))


if __name__ == '__main__':
    run()
