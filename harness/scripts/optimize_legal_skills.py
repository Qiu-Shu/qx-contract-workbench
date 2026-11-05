"""Repair the active legal adapters, preserving source archives and all names.

Default is a read-only plan. --apply writes per-file backups and a SHA manifest.
Only the 175 catalogued adapter SKILL.md files and one shared workbench reference
are eligible. Re-running is idempotent; original zh/en files are never written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "workspace/.dsh/skills"
OUT = ROOT / "docs/checks/skills-quality"
SHARED = ROOT / "workspace/legal-library/workbench/practice-context.md"
MARKER = "<!-- legal-quality-v1 -->"

BOUNDARY = """## 工作台执行边界

<!-- legal-quality-v1 -->
- 以当前请求、用户提供的材料和明确授权的当前事项为上下文；原库模板和占位符不是机构事实或授权。没有画像也先完成可做的分析，只补问关键缺口。
- 正文保留的 `~/.claude/...`、插件安装日志、MCP和slash command是原系统标识，不是本工作台可执行路径或已连接工具。不得据此读取全局画像、创建配置或运行原库脚本。实际读取和输出必须使用本次明确指定且已核实的路径；未指定保存位置时在对话中交付草稿。
- 仅当前任务明确要求持久化时写入该任务的授权位置。跨事项开关或原库设置不能替代跨案授权；不读取其他案件或复用其正文。
- 先核实当前运行时真实可用的工具，再执行检索、文件或外部服务操作。没有工具时交付可审查的方案/待核清单，不声称已查询、已发送、已安装或已完成。
- 只给假设规则或禁止联网时，结论限于这些规则和材料；其他法律义务列“待核”，不补造现行法结论。模型记忆不是已核验依据，`[法条原文]`仅在实际读到并校对来源和版本时使用。
- 明确区分材料事实、当事人陈述、假设、缺失事项和建议。无证据不把模板默认日期、主体属性、合规状态或程序保护填成事实。

"""

FIELDS = {
    "ai-governance": "系统用途与使用对象；部署方式与数据类别；对外提供情况；供应商和负责人；已有评估/备案证据（未知留空）",
    "commercial": "采购/销售方向；合同类型与交易目标；用户已确认的审查立场；审批授权；需保留或修改的条款",
    "corporate": "主体与交易结构；章程和授权文件版本；决策机关；交割条件；尽调范围与资料来源",
    "criminal": "脱敏事项代号；诉讼阶段与强制措施；已知罪名或待核点；材料范围；申请目标与紧急节点",
    "employment": "用工地与主体；员工/承包关系；岗位和时间线；制度证据；当前争议及处理目标",
    "ip": "权利类型与地域；权属链条；产品/技术及公开时间；已有检索材料；许可或争议目标",
    "law-student": "课程与学习目标；教学大纲和材料来源；考试形式与日期；可用时间；需要练习的知识点",
    "builder-hub": "当前运行时；需要管理的技能名称与实际路径；来源/许可证/固定SHA；允许的管理动作；回滚要求",
    "clinic": "脱敏事项；实践领域与管辖待核项；来访者目标；导师审阅范围；已获材料与内部节点",
    "litigation": "当前事项代号；争点与程序阶段；证据编号及定位；已确认期限来源；本次文书或庭审目标",
    "privacy": "处理活动、数据类型及主体；法域事实；系统清单；角色与供应商；已有权利请求/评估证据",
    "product": "功能与用户群；数据流；上线范围和日期；营销主张的证明材料；产品负责人及未决设计",
    "regulatory": "业务范围与法域事实；待比对法规的明确版本；内部制度版本；差距/负责人；既有监测来源",
}

SHARED_TEXT = """# 法律工作台：按需建立和修改实践上下文

<!-- legal-quality-v1 -->
此文件合并13个领域的入门和定制流程。它是工作流参考，不是用户画像；不得据此推断事实或启动全库读取。原库 `zh/`、`en/` 与Apache-2.0许可证保持原样。

## 触发与输入

只有用户明确要建立、重新设置或修改某领域配置时使用。本次业务分析不以完成画像为前提。先复用当前请求已提供的信息；仅用户指定现有配置且授权读取时才读取该文件。领域最小字段由调用本流程的同名适配入口提供。

## 建立上下文

1. 记录当前领域、事项范围、已提供事实及其来源；未知项留空。把用户目标与模板建议分开。
2. 按入口的领域字段形成草稿。首轮最多询问3个真正阻碍当前配置目的的问题；不逐项重复询问已知信息。
3. 给出配置草稿、关键假设和仍未回答项。机构审批人、风险容忍度、法域适用和绿色签署标准都必须有用户材料支持，不能从模板生成。
4. 默认仅在对话中交付。用户明确要求保存且给出授权位置时，才核实该位置后写入。无路径则简短确认目的地，期间仍完成可审查草稿。不得使用原系统全局路径作为默认值。

## 修改上下文

1. 用户已提供配置时只改明确指定字段，保留其他内容；展示旧值、新值及影响。
2. 没有旧配置时给出待保存的字段草稿即可，不强制重新进行完整入门问卷。
3. 修改仅作用于当前授权领域/事项；不能借保存偏好授权读取其他案件、跨案检索、自动发消息或定时执行。
4. 用户已授权此项修改和保存时可直接完成可逆更新；没有授权持久化时仅交付差异，不写用户全局配置。

## 交付结构

| 字段 | 值或待补 | 来源 | 当前用途 |
|---|---|---|---|
| 当前事项/领域 | 用户材料或待补 | 当前请求 | 限定范围 |
| 领域字段 | 按入口字段逐项填写 | 材料位置/用户陈述 | 说明所影响的判断 |

另列本次修改、未决问题、保存状态（未保存/已保存及真实路径）。没有实际执行就不能标已保存。引用的原库问题表仅可用作问题参考，原库路径、默认权限与执行命令不适用于本工作台。
"""


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def replace_once(text: str, old: str, new: str) -> str:
    if old not in text:
        raise AssertionError("Expected source text missing: " + old[:100])
    return text.replace(old, new, 1)


def frontmatter(name: str, description: str, reference: bool = False) -> str:
    return ("---\nname: " + name + "\ndescription: " + json.dumps(description, ensure_ascii=False)
            + ("\nuser-invocable: false" if reference else "") + "\n---\n\n")


def domain_for(name: str) -> str:
    for domain in sorted(FIELDS, key=len, reverse=True):
        if name.startswith("legal-zh-" + domain + "-"):
            return domain
    raise AssertionError(name)


def short_context(entry: dict) -> str:
    name = entry["name"]
    domain = domain_for(name)
    operation = "建立" if entry["original_name"] == "cold-start-interview" else "修改"
    return (frontmatter(name, f"仅当用户明确要求{operation}{domain}领域的实践配置或上下文时使用；普通业务分析无需先完成画像。")
            + BOUNDARY + f"# {operation} {domain} 实践上下文\n\n"
            + "加载[共享建立/修改流程](../../../legal-library/workbench/practice-context.md)，执行其中对应步骤。\n\n"
            + f"本领域最小字段：{FIELDS[domain]}。只收集当前配置目的需要的部分。\n\n"
            + f"原领域问题与历史实现：[原库参考](../../../{entry['source']})。只按需参考专业问题，不执行其中全局写入、自动初始化或插件命令。\n")


def builder_reference(entry: dict) -> str:
    name = entry["name"]
    action = entry.get("original_name", "builder-hub")
    methods = {
        "skills-qa": "检查技能全文、引用资源、固定版本、工具权限及外部指令；区分静态可疑点与实际行为，不将未发现问题当安全认证。",
        "auto-updater": "仅对用户指定来源和已安装版本比较固定SHA及差异；报告更新内容、权限变化和回滚方案，未授权不应用。",
        "skill-installer": "核实用户指定源、许可证、固定SHA、目标目录和运行时支持；交付安装计划与差异，未经实际能力验证不安装。",
        "disable": "查当前运行时的实际发现/禁用机制，给出可逆停用方案；不能保证改名SKILL.md或hooks.json必然生效。",
        "uninstall": "给指定技能的卸载影响和文件清单；保留原库和案件材料，删除需明确范围与授权，不能照搬Claude插件卸载逻辑。",
        "registry-browser": "只浏览用户指定或当前工具能访问的注册表；缺注册表/工具时给来源核验清单，不编造搜索结果。",
        "related-skills-surfacer": "仅根据当前任务建议已有技能；不读取历史行为、案件或画像，不自动安装或保存推荐记录。",
        "skill-manager": "核实当前运行时的真实安装记录和技能范围；给只读状态/操作预览，不假定原库全局安装日志存在。",
        "builder-hub": "将明确的技能管理请求路由至对应同名参考入口；普通法律业务不进入插件管理流程。",
    }
    # The two context adapters use the common flow instead.
    return (frontmatter(name, "只读参考：用户明确请求技能管理或技能质量审查时使用；原Claude插件管理实现未被认证适用于本工作台。", True)
            + BOUNDARY + f"# 技能管理参考：{action}\n\n" + methods[action] + "\n\n"
            + "输出：已核实事实、缺失能力、拟操作路径、具体差异、验证和回滚步骤。用户授权且工具/路径验证后才能实际操作；本参考不提供任何已连接工具的保证。\n\n"
            + f"保留原名兼容；[原始方法参考](../../../{entry['source']})仅作只读资料，不执行原库脚本、全局配置写入或hooks。\n")


def add_boundary(text: str) -> str:
    start = text.find("## Harness 工作区路径与使用说明")
    if start >= 0:
        # Preserve source/resources mappings after the obsolete generic adapter block.
        end = text.find("- 原始完整文件：", start)
        if end < 0:
            end = text.find("根据用户任务选择", start)
        assert end > start
        text = text[:start] + BOUNDARY + text[end:]
    else:
        parts = text.split("---", 2)
        assert len(parts) == 3
        text = "---" + parts[1] + "---\n\n" + BOUNDARY + parts[2].lstrip()
    return text.replace(
        "> 适配变更：仅唯一名称、工作区路径与上述适用说明经过调整；下方为提供 ZIP 中的完整技能正文。原始源码和 Apache-2.0 许可证保持不变。",
        "> 适配变更：工作台执行边界与已验证的质量问题在此副本修订；原始全文、来源和Apache-2.0许可证保留在legal-library/zh及en。修改SHA见docs/checks/skills-quality/legal-optimization-manifest.json。")


def targeted(name: str, text: str) -> str:
    # Replace misleading certainty tags wherever the five observed variants occur.
    text = re.sub(r"^.*`\[已确定\]`.*$", "> - `[模型知识 — 未核验]` — 未读取可定位原文的记忆性引用不能标为已确定；须核对来源和版本。", text, flags=re.M)
    text = text.replace("模型知识引用是真实的但应验证", "模型记忆可能错误且尚未核验")
    text = text.replace("模型知识引用是真实的但应被核实", "模型记忆可能错误且尚未核验")
    if name == "legal-zh-ai-governance-ai-inventory":
        a = text.index("#### 第2步：判定角色")
        b = text.index("#### 第3步：分配风险等级", a)
        text = text[:a] + """#### 第2步：记录实际角色，逐法规判断

记录自主研发、使用第三方模型、内部部署、向谁提供什么服务等事实。内部开发者/部署者/对外服务方是业务事实标签，不自动等同任何法规的提供者/使用者定义。同一主体在不同法规下可能角色不同；未核验定义时写“法定角色待核”，不能仅凭自研自用判为所有法规下的使用者。

""" + text[b:]
        text = text.replace("#### 第3步：分配风险等级", "#### 第3步：记录内部管理风险（不是法定分类）")
        text = text.replace("| **低风险** | 内部使用，不涉及个人信息，无外部影响 |", "| **低风险候选** | 还须排除安全关键或其他实质影响，内部使用本身不决定低风险 |")
        a = text.index("基于角色和风险等级，确定义务：")
        b = text.index("#### 第5步：输出单系统条目", a)
        text = text[:a] + """每项义务按各自适用范围和触发要件判断，不从内部风险等级直接推导“必须/不适用”。高风险、中风险、低风险均为内部管理标签；不得标“法规分类低风险”。已知安全关键事实优先于内部使用等概括标签。

| 候选义务 | 必须核对的事实与来源 | 未核验时输出 |
|---|---|---|
| 生成式AI相关安全评估 | 是否属于适用的生成服务、是否面向境内公众、是否具有舆论属性或社会动员能力；核对相应规则及版本 | 待核；只给测试规则时仅按该规则分析 |
| 算法备案/透明度 | 服务功能、服务对象、主体角色和具体触发要件分别核对 | 待核，不因内部高风险自动勾选 |
| 科技伦理审查 | 活动性质、适用领域及具体审查范围 | 待核，不因未对外就排除 |
| 个人信息保护影响评估 | 是否处理个人信息，以及敏感信息、自动化决策、对外提供/委托/出境等具体事实和适用依据 | 未提供规则时列待核 |
| 合成内容标识/投诉机制 | 是否形成/传播相关内容、服务模式与适用规则 | 待核，不从总体角色一并排除 |

只有用户给定R17等假设规则时，结论只写该规则是否触发，其他候选义务列“规则未提供，待核”，不得追加未查法条、无任何监管义务或整体豁免结论。正式核验可从官方原文开始：https://www.cac.gov.cn/2023-07/13/c_1690898327029107.htm 。此链接只是检索入口，不意味着本次已核验现行文本。

""" + text[b:]
    elif name == "legal-zh-employment-internal-investigation":
        a = text.index("## Output header")
        b = text.index("## Purpose", a)
        text = text[:a] + """## 文件属性与法域

先记录实际调查主导者、目的和涉及法域。中国境内HR主导调查的默认标题为“保密 · 内部调查记录”；不能把每份文件标为律师工作文件或为获取法律意见制作。只有确实由律师形成的法律意见才标“律师法律意见”，事实材料单独管理。标题和律师参与本身不产生证据豁免，具体保护范围待适用法律核验。

Upjohn、EEOC、DFEH等仅在明确涉及对应美国制度且已核验适用性时讨论。国内默认流程是投诉登记、合法取证、访谈前必要告知、听取陈述、事实与意见分列、权限和披露审核。记录模板不自动要求美国告知或答辩。

""" + text[b:]
        text = replace_once(text, "> - Is this attorney-directed? (If yes: work product protection applies.\n>   If no: flag privilege risk before proceeding.)", "> - Who leads the investigation and for what purpose? Record facts only; attorney involvement never establishes protection by itself. Applicable legal protection remains to be verified.")
        text = text.replace("Upjohn warning documentation — confirm interviews were preceded\n             by Upjohn warnings and documented", "Interview notice documentation — record the actual notice and its verified legal basis")
        text = text.replace('source: "Upjohn warning documentation"', 'source: "Interview notice documentation applicable to the confirmed jurisdiction"')
        text = text.replace("- Upjohn warning confirmation", "- Interview notice and scope confirmation (jurisdiction-specific; not automatically Upjohn)")
        text = text.replace("All files created by this skill carry the privilege marking above.", "Each file uses its actual nature: internal factual record or separately authored legal opinion; no blanket privilege marking.")
        text = text.replace("EEOC/DFEH/state agency charge response, plaintiff's-counsel demand letter response, regulator response, or any formal complaint reply", "regulator response or formal complaint reply under the confirmed jurisdiction; US agency procedures only when specifically applicable")
    elif name == "legal-zh-privacy-dsar-response":
        text = replace_once(text, "此暂停时效（存在争议）但不要拖延——几天内回复告知需验证，而非拖到第29天。", "身份核验是否影响时限必须依据本次给定规则或已核验的适用制度；未有依据不得主张暂停。先记录收到日、核验日、起算规则和待核项，不默认30天或其他法定时限。")
        text = replace_once(text, "- 如果我们因请求复杂或同时收到您的其他请求而需要更多时间，我们将在初始期限前告知您并解释原因。[如制度允许延期，引用相关条款。]", "[仅当已核验规则明确允许延期且条件已满足时，加入具体延期依据与通知；否则删除本段，不承诺可以延期。]")
        text = replace_once(text, "- 本请求不收费。[或：仅在制度允许且请求明显无依据或过度时收费——引用相关条款。]", "[仅在收费/免费规则已确认时填入；未知时在内部待核表列出，不能把默认不收费写成对外承诺。]")
        text = replace_once(text, "#### 第5a步 — 确认函模板", """#### 第5a步 — 确认函模板

**填充纪律：** 每句话的日期和状态必须有本次材料依据。函件日期不得早于其中声称已完成事件的日期；没有发函日期时保留[拟发函日期]。内部建议目标日必须标“建议，待确认”，不能自动变为对外承诺。删除模板不适用段落；身份核验、系统查询、删除执行、第三方通知等只有实际完成证据才写“已完成”。假设规则仅支持其明示内容，不能添加免费、延期或法定义务。
""")
    elif name in ("legal-zh-commercial-nda-review", "legal-zh-commercial-vendor-agreement-review"):
        text = re.sub(r'如果匹配方向为 `\[未配置\]`，停止并告知用户[^。]+。', "如果匹配方向未配置，先提供一般风险与修改建议，并列机构标准待补；不强制完整入门访谈，也不发机构绿色审批结论。", text)
        if name.endswith("nda-review"):
            text = replace_once(text, "## 范围检查", """## 期限与事实边界

分别提取协议有效期、评估期间、保密义务存续期和成果形成期。某条只写保密五年时，不得把评估期或知识产权转让期间推为五年；未约定的起止点列待确认。商业建议与材料事实分开，不用修改建议填补原合同内容。

## 范围检查""")
    elif name == "legal-zh-litigation-privilege-log-review":
        text = text.replace("《民事诉讼法》第65条 `[法条原文]`", "《民事诉讼法》（2023年修正）第68条（版本与适用性仍须按任务核验；官方来源：https://ipc.court.gov.cn/zh-cn/news/view-6231.html）")
    elif name == "legal-zh-criminal-bail-application":
        a = text.index("在开始任何处理之前")
        b = text.index("## 📋 工作流程", a)
        text = text[:a] + "在分析前最小化不必要真实标识。公开机关名称本身不触发全面停止；可直接替换为[侦查机关]后继续。可分离的姓名、证件号等先用占位符，不重复输出。仅当敏感内容无法安全分离且用户未授权处理时暂停相关部分；仍可给材料缺口和通用框架。脱敏不补造罪名、证据或取保条件。\n\n" + text[b:]
    elif name == "legal-zh-employment-leave-tracker":
        text = text.replace("年末未休结转截止（一般不跨年结转）", "核实当年安排及跨1年度安排条件；生产/工作特点必要性、职工同意和实际计划待核，不把年末当作当然失效日")
    elif name == "legal-zh-law-student-exam-forecast":
        text = replace_once(text, "## 置信纪律", """## 置信纪律

- 先按试卷内容、课程和年度去重；同一试卷的多个扫描件只算一个独立样本。样本数只反映覆盖量，不能独立决定预测置信度。
- 不能根据6份文件推定“强置信度”，也不能输出未验证命中率、固定加权倍数或无材料依据的复习比例。复习时间分配若是人为建议，标明依据与可调整范围。
""")
        text = text.replace("[不足（<3） / 中等（3-5） / 强（6+）]", "[独立样本N；同源性、教学大纲和考试形式差异；不能仅以数量分为强置信度]")
        text = text.replace("权重为其在教学大纲中占比的 3-5 倍。", "仅在有实际分值和大纲数据时报告差异；不得默认3-5倍。")
    return text


def refine(name: str, text: str) -> str:
    marker = "<!-- legal-quality-v2-state-evidence -->"
    if marker in text:
        return text
    sections = {
        "legal-zh-privacy-dsar-response": ("#### 第5a步 — 确认函模板", "**执行状态逐句核对：** 每个操作分别标未开始、计划、正在、已完成。材料说尚未查询时，对外草稿只能写‘我们将核查相关系统’，不能写‘正在查询/正在评估’；有开始执行的证据才用‘正在’，有结果证据才用‘已’。不能靠文末免责声明修复正文中虚构的进度。"),
        "legal-zh-litigation-brief-section-drafter": ("# /brief-section-drafter", "**事实缺失时的正文形式：** 未提供损失证据时写‘是否发生损失及其范围待举证’；不能先写‘甲方因迟延受到损失’再附待核标签。未证实交付定义、免责等构成事实时，用‘如……经证实，则可主张……’的条件论证。正文事实句本身必须得到材料支持，文末免责声明或括号待核不能补救无依据断言。"),
        "legal-zh-litigation-deposition-prep": ("## 记录保真——引用和精确定位", "**问题也须有事实边界：** 无证据证明证人不在场、听他人转述或有偏见时，先问‘您是否在场/信息来源是什么’，不能用‘您没有在场，对吗’等包含未证事实的诱导式问题，即使后附待核标签也不行。仅在证据已支持该前提时才用锁定式问题。用户只要三个问题时，交付三问与必要来源说明，不再生成整份模板。"),
        "legal-zh-law-student-exam-forecast": ("## 置信纪律", "- 教师承诺若只来自用户转述，标‘用户转述，未独立核实’，不能提升为已确认命题。‘会考某主题’不等于至少一道独立题、固定分值或具体题型；这些未知项保持未知。复习优先级可依据转述调整，但不生成比转述更具体的考试承诺。"),
    }
    if name not in sections:
        return text
    heading, rule = sections[name]
    assert heading in text, name
    return text.replace(heading, heading + "\n\n" + marker + "\n" + rule, 1)


def plan() -> tuple[dict[Path, bytes], dict]:
    catalog = json.loads((ROOT / "workspace/legal-library/skill-catalog.json").read_text(encoding="utf-8"))
    entries = catalog["entries"] + catalog["workflows"]
    assert len(entries) == 175 and len({e["name"] for e in entries}) == 175
    proposed = {}
    for entry in entries:
        name = entry["name"]
        path = ACTIVE / name / "SKILL.md"
        text = path.read_text(encoding="utf-8")
        if '<!-- workbench-skill-repair-v2 -->' in text:
            continue  # Later evidence-based repairs must not be overwritten by this v1 generator.
        if MARKER in text:
            new = refine(name, text)
            if new != text:
                proposed[path] = new.encode("utf-8")
            continue
        if entry.get("original_name") in ("cold-start-interview", "customize"):
            new = short_context(entry)
        elif "builder-hub" in name:
            new = builder_reference(entry)
        elif entry.get("original_name") in ("form-generation", "plain-language-letters"):
            targets = (["legal-zh-clinic-draft"] if entry["original_name"] == "form-generation"
                       else ["legal-zh-clinic-client-letter", "legal-zh-clinic-status"])
            new = frontmatter(name, "兼容旧名称：按请求转入现有诊所文书或当事人沟通工作流。", True) + BOUNDARY
            new += "# 兼容路由\n\n" + "\n".join(f"- 加载 `{n}`： [实际技能](../{n}/SKILL.md)" for n in targets)
            if len(targets) == 2:
                new += "\n\n常规信函选择client-letter；实质性当事人状态更新选择status的client模式。"
            new += f"\n\n[原库参考](../../../{entry['source']})保持不变。\n"
        else:
            new = targeted(name, add_boundary(text))
        new = refine(name, new)
        assert re.search(r"(?m)^name: " + re.escape(name) + r"\s*$", new)
        proposed[path] = new.encode("utf-8")
    if not SHARED.exists() or SHARED.read_text(encoding="utf-8") != SHARED_TEXT:
        proposed[SHARED] = SHARED_TEXT.encode("utf-8")
    for path in proposed:
        assert path == SHARED or (path.parent.parent == ACTIVE and path.name == "SKILL.md")
        assert "legal-library/zh/" not in path.as_posix() and "legal-library/en/" not in path.as_posix()
    return proposed, catalog


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    proposed, catalog = plan()
    records = []
    for path, content in proposed.items():
        before = path.read_bytes() if path.exists() else None
        records.append({"path": path.relative_to(ROOT).as_posix(), "before_sha256": sha(before) if before is not None else None,
                        "after_sha256": sha(content), "before_bytes": len(before) if before is not None else 0, "after_bytes": len(content)})
    if args.apply and proposed:
        manifest_path = OUT / "legal-optimization-manifest.json"
        previous = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        previous_records = {r["path"]: r for r in previous.get("changes", [])}
        # Back up ALL originals before the first active write. Never overwrite a baseline backup.
        for path in proposed:
            if path.exists():
                backup = OUT / "backups/legal-before" / path.relative_to(ROOT)
                backup.parent.mkdir(parents=True, exist_ok=True)
                if backup.exists():
                    prior = previous_records.get(path.relative_to(ROOT).as_posix())
                    assert prior and sha(backup.read_bytes()) == prior["before_sha256"], "Baseline backup differs: " + str(path)
                    stage = OUT / "backups/legal-refinements" / sha(path.read_bytes()) / path.name
                    stage.parent.mkdir(parents=True, exist_ok=True)
                    if not stage.exists():
                        stage.write_bytes(path.read_bytes())
                else:
                    backup.write_bytes(path.read_bytes())
        for record in records:
            prior = previous_records.get(record["path"])
            if prior:
                record["revisions"] = prior.get("revisions", []) + [{"before_sha256": record["before_sha256"], "after_sha256": record["after_sha256"]}]
                record["before_sha256"] = prior["before_sha256"]
                record["before_bytes"] = prior["before_bytes"]
            previous_records[record["path"]] = record
        manifest = {"format": 1, "date": "2026-11-04", "catalog_sha256": sha((ROOT / "workspace/legal-library/skill-catalog.json").read_bytes()),
                    "policy": "Original zh/en library unchanged; all 175 names retained; baseline backups precede writes.", "changes": list(previous_records.values())}
        (OUT / "legal-optimization-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for path, content in proposed.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        # Inspect actual results and relative Markdown links for the new short adapters.
        for path, content in proposed.items():
            assert path.read_bytes() == content
            for link in re.findall(r"\]\((\.{1,2}/[^)]+)\)", content.decode("utf-8")):
                assert (path.parent / link).resolve().exists(), f"Missing link {path}: {link}"
        assert len(catalog["entries"]) + len(catalog["workflows"]) == 175
        assert not plan()[0], "Second run is not idempotent"
    print(json.dumps({"applied": args.apply, "changed_files": len(records), "changes": records}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
