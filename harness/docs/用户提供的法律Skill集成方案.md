# 群兴工作台法律 Skill 库分析与集成取舍方案

**审查对象：** `claude-for-legal-main.zip`、`claude-for-legal-ZH.zip`  
**项目：** 群兴法律工作台  
**日期：** 2026-11-01  
**用途：** 供宋萌律师确定技能取舍，并作为 Codex 后续接入依据  
**审查边界：** 本次读取 ZIP 目录、README、适配层、领域配置和部分关键 Skill 正文；未安装技能、未运行安装脚本、未连接 MCP、未调用真实模型。

---

## 一、结论先行

**不建议把所有 Skill 全部安装进群兴工作台。建议精选方法论、复用专项工作流、把质量控制规则融入现有四项核心能力。**

这两份压缩包的价值，不是给工作台增加一百多个按钮，而是提供了一套相对成熟的法律工作方法：先识别任务、再选择工作流；区分事实与法律判断；要求证据来源；检查反方论点；设置审批门槛；将复杂任务拆分为可复核步骤。

群兴工作台的一级产品仍然只保留四项能力：

1. 客户接待；
2. 案件整理；
3. 合同审查；
4. 模拟法庭。

其他 Skill 作为后台专项能力，按案件类型和任务阶段组合调用。律师不需要知道后台调用了几个 Skill，也不应该在首页面对几十个法律技能按钮。

推荐原则：

- **复用工作方法，不盲目复制整套插件系统。**
- **优先吸收质量门禁和证据纪律，而不是增加大量新入口。**
- **先接入与群兴现有业务高度重合的技能，再按真实案源扩展。**
- **不允许不同 Skill 各自维护重复客户档案、案件档案、材料库和法律法规库。**
- **所有 Skill 输出都进入统一任务、材料版本、权限、费用和审计体系。**

## 二、压缩包盘点：中文包是主参考，英文包作为上游对照

### 2.1 文件与结构

| 项目 | 英文包 | 中文包 |
|---|---:|---:|
| 压缩文件大小 | 约1.35 MB | 约28.49 MB |
| ZIP 条目数 | 563 | 749 |
| 领域目录 | 12个 | 13个 |
| 领域内 `SKILL.md` | 以实际目录为准，约140个 | 157个 |
| Codex 适配入口 | 无 | 18个 |
| DeepSeek Harness 适配入口 | 无 | 18个 |
| WorkBuddy 适配入口 | 无 | 18个 |
| README 声明版本 | 以包内 README 为准 | v1.1.0 |
| LICENSE | Apache-2.0 | Apache-2.0 |

**关键说明：**

1. 中文包 README 明确说明，它是在 Anthropic `claude-for-legal` 基础上做中国法本地化的版本。
2. 英文包主要用于理解上游设计、工作流来源和方法论，不应直接作为中国法律业务的生产技能。其内容含美国法律、美国诉讼程序和美国监管规则。
3. 中文包新增刑事辩护领域，并提供 Codex、DeepSeek Harness、WorkBuddy 三套适配目录。
4. 中文包的 `.agents/skills`、`.dsh/skills`、`.workbuddy/skills` 各有18个同名路由适配器。这是三种宿主的适配文件，不是54项独立法律能力。
5. 中文包 README 列出13个法律业务领域和5个 Managed Agent Cookbook。实际目录内领域 Skill 文件数量为157；不要把适配器数量、领域 Skill 数量和业务能力数量混为一谈。
6. ZIP 没有 `.git` 历史，无法仅凭压缩包确认实际 Git commit。README 标示 v1.1.0，不等于已核验远端 tag、提交和文件完整性。正式接入前应从原始仓库固定版本并核验 SHA-256。

### 2.2 中文包的13个领域

| 领域 | Skill 数量 | 与群兴的关系 |
|---|---:|---|
| 刑事辩护与合规 | 7 | 高度相关 |
| 诉讼仲裁 | 19 | 高度相关 |
| 商事合同 | 12 | 高度相关 |
| 知识产权 | 12 | 高度相关 |
| 劳动用工 | 20 | 高度相关 |
| 公司与并购 | 13 | 中期扩展 |
| 数据合规与隐私 | 9 | 中期扩展 |
| 监管合规 | 9 | 中期扩展 |
| AI治理 | 10 | 与群兴法律科技产品高度相关 |
| 产品与营销合规 | 7 | 中期扩展 |
| 法律诊所 | 16 | 部分接待方法可借鉴 |
| 法学学习与法考 | 13 | 不进入当前工作台主产品 |
| 法律技能运营 | 10 | 供研发团队研究，不作为律师业务入口 |

另外5个 Managed Agent Cookbook：

- `diligence-grid`：尽调资料批量读取、表格化抽取、逐格来源引用；
- `docket-watcher`：案件动态及期限监控；
- `launch-radar`：产品上线法律风险雷达；
- `reg-monitor`：监管动态监控；
- `renewal-watcher`：合同续约监控。

这些 Cookbook 不是单纯 Markdown 提示词。README 说明其依赖 Managed Agents API、MCP 连接器、外部存储或多角色 Agent。不能复制目录后就宣称可以在群兴系统中运行。

## 三、真正值得引入的不是“技能数量”，而是五类工作质量机制

抽样阅读中文包中的 `chronology`、`brief-section-drafter`、`matter-intake`、刑事 `case-analysis`、`defense-strategy`、IP `infringement-triage`、`cease-desist`、商事合同 `review`、`nda-review`、`vendor-agreement-review`、劳动 `termination-review` 和 `diligence-grid` 后，建议把价值归纳为五类。

### 3.1 任务分流机制

商事合同 `review` 会先读取合同标题、主协议和附件结构，再决定调用 NDA、供应商协议、SaaS/MSA 或 DPA 对应流程；多个专项可以组合，最后整合成一份备忘录。

群兴可以吸收这一机制：用户只说“帮我审合同”，系统先识别合同类型、我方身份、主协议与附件，再路由到相应子流程。不要把所有合同都用同一份泛化提示词审查。

### 3.2 证据与来源纪律

`chronology` 要求每个事件能回到材料来源；`brief-section-drafter` 要求逐字引用必须精确、事实要有案卷引用、法律命题要有法条来源；`case-analysis` 要求对不同供述和客观证据交叉比对。

群兴应将这些变成统一输出协议：

- 事实陈述标注材料名称、页码/段落/消息时间和材料版本；
- 直接引语必须逐字核对；
- 推断、当事人陈述、客观证据、法律评价分别标识；
- 无法定位的事实标为“来源待补”，不得编造页码或证据编号；
- 法律条文、案例和时效规则标明来源及核验状态；
- 每个关键结论都列出支持材料、反向材料和缺口。

### 3.3 对抗性与反方检查

刑事 `defense-strategy` 不只分析辩方主张，也拆解控方可能的构成要件逻辑；诉讼工作流区分主张方和抗辩方的时间线重要性；IP `infringement-triage` 要求同时列出权利方和被控方有利、不利及不确定因素。

群兴模拟法庭应吸收这套方法：先形成己方理论，再由对方律师攻击，最后由法官视角检查证据、程序、请求和法律适用缺口。不能只让三个角色分别写三段话，必须保存独立回合、攻击点、回应和结论变化。

### 3.4 质量门禁和人工决策点

- `matter-intake` 将利益冲突检查、案件身份、证据保全、关键日期作为案件登记的一部分。
- `cease-desist` 要求起草警告函前先展示对方主体尽调及诉讼风险，用户确认后才继续。
- `nda-review` 不允许在缺少经律师确认的审查标准时给出“绿色、可直接签署”。
- `vendor-agreement-review` 先检查 deal-breaker，再做逐条偏离分析。
- `termination-review` 发现特殊保护群体、证据薄弱或其他高风险标记时要求升级审批。

这些门禁适合群兴，尤其是案件正式建档、合同签署建议、侵权警告函、劳动解除方案和对外发送文书。

### 3.5 结构化工作区和连续记录

不少 Skill 使用 matter workspace、matter.md、history.md、日志文件和版本差异。这种思路值得吸收，但群兴不能照搬它的文件系统当作第二套案件数据库。

正确做法是：Skill 只通过统一案件服务读取当前案件上下文、写入任务成果和追加事件；客户/案件主档、材料版本、权限、审计和成果归档仍由群兴主系统负责。

---

## 四、技能取舍清单：第一批、第二批、暂缓

### 4.1 第一批：优先接入（与现有四大能力直接相关）

| 顺序 | 原领域 / Skill | 对群兴的价值 | 接入位置 | 处理方式 |
|---|---|---|---|---|
| P0 | `litigation-legal/chronology` | 从多份材料抽取、去重、排序事件，按原告/被告立场标记重要性 | 案件整理 | 复用流程与输出结构 |
| P0 | `litigation-legal/brief-section-drafter` | 文书事实逐项引用、法律依据定位、弱论点提示 | 案件整理/文书生成 | 吸收为文书质量门禁 |
| P0 | `litigation-legal/matter-intake` | 案件登记、当事人地位、利益冲突状态、证据保全、关键日期 | 客户接待→案件建档 | 复用字段；冲突检查状态不得由模型自行认定通过 |
| P0 | `criminal-legal/case-analysis` | 刑事笔录对照、供述矛盾、客观证据冲突、证据链缺口 | 案件整理 | 独立刑事子流程 |
| P0 | `criminal-legal/defense-strategy` | 犯罪构成要件、罪与非罪、此罪与彼罪、实体/程序辩护切入点 | 案件整理/模拟法庭 | 独立刑事子流程 |
| P0 | `criminal-legal/bail-application` | 取保候审、羁押必要性审查材料和理由组织 | 案件整理 | 复用框架，现行法核验 |
| P0 | `ip-legal/infringement-triage` | 商标、著作权、专利、商业秘密分别筛查，列双方因素，不直接作侵权认定 | 案件整理 | 独立 IP 子流程 |
| P0 | `ip-legal/cease-desist` | 警告函发送/接收双向分流、主体尽调、发送前确认 | 案件整理/文书生成 | 复用审批门禁，不自动发送 |
| P0 | `commercial-legal/review` | 按合同类型识别并调用专项审查 | 合同审查 | 优先吸收其路由设计 |
| P0 | `commercial-legal/nda-review` | NDA 绿/黄/红分流，识别隐藏的排他、许可、竞业、知识产权义务 | 合同审查 | 复用分类框架，但无经律师确认标准时不得给绿色 |
| P0 | `commercial-legal/vendor-agreement-review` | 逐条对比审查指引，提供可直接替换的修订语言、审批升级 | 合同审查 | 复用审查方法与输出模板 |
| P0 | `employment-legal/termination-review` | 解除风险标记、特殊保护群体、证据、地域差异 | 案件整理/专项咨询 | 复用检查清单，地方规则实时核验 |

说明：这里的 P0 是建议优先级，不代表这些 Skill 已经通过群兴业务验收。每个 Skill 都应先经样本测试，再决定挂载。

### 4.2 第二批：有实际案源再接入

| 原领域 / Skill | 适用业务 | 为什么不是第一批 |
|---|---|---|
| `corporate-legal/diligence-issue-extraction` | 公司并购、股权投资、企业尽调 | 需要尽调数据室和批量文档场景 |
| `corporate-legal/tabular-review` | 多合同、多文件逐项尽调表 | 需要统一表格 Schema、引用定位和批量任务队列 |
| `corporate-legal/board-minutes`、`written-consent` | 董事会/股东会决议、书面决议 | 属于公司专项服务产品 |
| `corporate-legal/closing-checklist` | 并购交割 | 需要交易项目管理和条件清单 |
| `privacy-legal/dpa-review`、`pia-generation`、`dsar-response` | 数据处理协议、个人信息保护影响评估、个人信息权利响应 | 需要数据处理活动信息、系统清单和监管依据 |
| `ai-governance-legal/use-case-triage`、`aia-generation`、`vendor-ai-review` | AI项目合规、算法/模型供应商审查 | 与群兴法律科技咨询业务相关，但需独立产品定义 |
| `regulatory-legal/policy-diff`、`reg-gap-analysis` | 政策差异和合规差距 | 依赖稳定法规来源和更新机制 |
| `product-legal/feature-risk-assessment`、`launch-review` | 产品上线、广告营销和功能合规 | 需要客户产品需求、业务流程和证据输入 |
| `employment-legal/internal-investigation` | 企业内部调查 | 需要证据保全、调查权限和敏感材料隔离 |
| `ip-legal/clearance`、`fto-triage`、`ip-clause-review` | 商标检索、专利自由实施初筛、IP合同条款 | 需要专业数据库和技术材料支持 |

### 4.3 暂缓或不进入群兴律师工作台主入口

| Skill/领域 | 处理意见 | 原因 |
|---|---|---|
| `law-student/*` | 暂缓 | 法考学习与律师办案不是同一产品场景 |
| `legal-clinic/*` | 不整体接入 | 面向法律诊所、学生案件和导师审阅；仅提取接待、通俗沟通和交接方法 |
| `legal-builder-hub/*` | 不给律师展示 | 是技能发现、安装、管理和质量检查工具，属于研发运营工具 |
| `docket-watcher` | 暂缓真实自动监控 | 需法院数据源、身份认证、可靠期限计算和提醒机制 |
| `renewal-watcher` | 暂缓 | 需要合同台账、日期字段、提醒和持续调度能力 |
| `reg-monitor` | 暂缓 | 需要监管信息源、去重、重大性判断和定时任务 |
| `launch-radar` | 暂缓 | 需要客户产品/功能台账及上线计划 |
| `diligence-grid` Managed Agent | 暂不直接部署 | 依赖 Managed Agents API 与多角色基础设施，先复用其逐格引用方法 |

## 五、哪些内容应当直接提升群兴现有四项能力

### 5.1 客户接待：从“销售接待”升级为“案件入口分诊”

建议吸收：

- `litigation-legal/matter-intake` 的统一登记字段；
- `legal-clinic/client-intake` 的结构化提问、客户沟通和交接思路；
- `commercial-legal/cold-start-interview` 中先识别客户/团队业务画像的配置方法，但改为群兴所级配置，不要求每个律师反复做一遍；
- `ip-legal/infringement-triage`、`criminal-legal/case-analysis` 等专项领域的初步分流问题。

群兴接待输出建议统一为：

1. 客户基本信息及信息来源；
2. 客户真实诉求；
3. 我方身份/对方身份/争议类型；
4. 程序阶段和紧急期限；
5. 关键事实与待核实事实；
6. 已有材料及材料缺口；
7. 潜在利益冲突状态（未检索/待人工核验/已按律所流程确认，不由模型直接判定通过）；
8. 推荐业务能力及下一步；
9. 内部接待底稿；
10. 客户可见回复草稿。

**不要照搬“客户销售评级、成交概率、付款能力画像”等销售型字段。** 群兴接待首先是专业服务分诊和冲突审查，不应把客户商业价值判断混入法律事实记录。

### 5.2 案件整理：优先吸收证据和时间线工作流

建议把以下能力组合为一个案件整理流水线：

```text
上传材料
  -> 文件识别/OCR/解析
  -> 材料清单与版本登记
  -> 事实抽取（逐条保留来源）
  -> chronology 时间线
  -> 证据三性/证明目的/证明力初步分析
  -> 请求权/犯罪构成/抗辩要件映射
  -> 争点清单
  -> 反方观点与证据缺口
  -> 律师确认
  -> 文书或庭审准备
```

优先复用：

- `litigation-legal/chronology`：事件提取、去重、按攻防立场标记重要性；
- `litigation-legal/claim-chart`：将构成要件或请求权要件与证据逐项映射；
- `litigation-legal/brief-section-drafter`：文书章节起草与来源纪律；
- `criminal-legal/case-analysis`：刑事笔录矛盾、口供与客观证据比对；
- `criminal-legal/defense-strategy`：控辩双方的构成要件和辩护切入点；
- `litigation-legal/deposition-prep`：如未来确有询问/证人准备业务，可再引入。

群兴应将现有材料解析、卷宗证据 MVP、时间线构建器等既有能力与这些流程对照，**不要再造一套文件解析、OCR、时间线数据库或证据库**。Skill 负责告诉系统“如何分析”，主工作台负责“材料在哪、版本是什么、来源如何回溯、权限是什么”。

### 5.3 合同审查：不要替换现有引擎，重点引入类型路由和审查质量门禁

建议结构：

```text
合同/附件进入
  -> 识别主合同、附件、订单、补充协议
  -> 判断合同类型及我方身份
  -> 检查审查指引是否存在
  -> 先检查 Deal-breaker
  -> 按合同类型调用专项审查
  -> 逐条风险与替代条款
  -> 法律风险与商业摩擦分轴
  -> 审批升级提示
  -> 生成审查备忘录/修订稿
  -> 材料版本与成果归档
```

优先吸收：

- `commercial-legal/review`：主协议/附件识别和多 Skill 路由；
- `commercial-legal/vendor-agreement-review`：合同立场、审查指引偏离、具体替代语言；
- `commercial-legal/nda-review`：NDA 快速分类及隐藏的非保密义务；
- `commercial-legal/saas-msa-review`：仅在实际有 SaaS/订阅合同场景时启用；
- `commercial-legal/amendment-history`：多轮修订版本差异；
- `commercial-legal/escalation-flagger`：超出审查权限的事项上报。

群兴现有合同审查项目应作为唯一审查执行引擎。引入 Skill 作为审查规则、检查顺序、输出格式和审批门禁，不要让两个合同引擎同时分析并输出两份互相矛盾的结论。

**特别限制：** `nda-review` 的绿色分类依赖经律师批准的团队审查标准。群兴没有完成审查指引配置时，只能给出“待律师审查/黄灯”，不能自动判定“可直接签署”。`vendor-agreement-review` 中采购方/供应方预设和金额阈值也必须转为可配置，不能硬编码照搬。

### 5.4 模拟法庭：吸收诉讼技能的攻防纪律

建议工作流：

1. 从案件整理模块读取已确认事实、证据来源、争点和己方理论；
2. 由对方律师视角提出最强攻击，不刻意弱化对方；
3. 对方每个攻击必须关联事实、证据、程序或法律依据；
4. 己方律师逐项回应，指出需要补强的证据；
5. 法官视角审查请求、要件、举证责任、证据合法性、程序风险和逻辑漏洞；
6. 汇总争点、风险、待补证据、庭审提纲和发问提纲；
7. 保存每轮输入、输出、模型/Skill 版本和引用来源。

应复用持衡项目已有的模拟法庭引擎和共享法库。`brief-section-drafter`、`chronology`、`claim-chart` 等是模拟法庭的上游输入和输出质量约束，不要把它们全部包装成新的 Agent。

### 5.5 法律科技与企业顾问业务：作为未来独立产品线

群兴的长期业务还涉及企业数字化、AI、数据合规。中文包中的以下 Skill 值得保留为第二阶段产品储备：

- `ai-governance-legal/use-case-triage`：AI 使用场景分级；
- `ai-governance-legal/aia-generation`：AI 影响评估；
- `ai-governance-legal/vendor-ai-review`：AI 供应商条款审查；
- `privacy-legal/pia-generation`：个人信息保护影响评估；
- `privacy-legal/dpa-review`：数据处理协议审查；
- `product-legal/feature-risk-assessment`：产品功能风险识别；
- `regulatory-legal/policy-diff`：监管政策差异分析。

这些能力可以成为群兴未来企业数字化法律顾问产品的模块，但不应在本轮挤占四项核心工作台能力的交付资源。

---

## 六、不能直接照搬的内容与风险

### 6.1 适配器不是业务引擎

中文包的 `AGENTS.md` 和 `INSTALL_CODEX.md` 明确说明：Codex adapter 的作用是把自然语言任务路由到原领域 `CLAUDE.md`、`skills/*/SKILL.md` 和 Managed Agent Cookbook。也就是说，18个 `chinese-legal-*` 适配入口主要是路由层，不是18套完整独立引擎。

对群兴而言，不应简单复制 `.agents/skills` 后就说主工作台完成接入。必须把原领域 Skill 的输入输出转成群兴主系统可调用的结构化接口，并由统一任务路由实际触发。

### 6.2 领域配置不能原样沿用

多个领域 `CLAUDE.md` 将其自身定位为模板，并要求先完成 `cold-start-interview`，将用户画像写入 `~/.claude/plugins/config/...`；存在 `[PLACEHOLDER]` 时要求停止实质工作。

群兴不能让每位律师在每个 Skill 里重复填写一套配置。建议将配置分成：

- **律所级配置：** 律所名称、业务范围、统一文书风格、风险偏好、输出格式、保密规则；
- **业务领域配置：** 刑事、民商事、劳动、合同、IP等专业规则；
- **案件级配置：** 当事人身份、管辖、案情、争点、策略和案件专属约束；
- **律师个人配置：** 承办律师的写作偏好和授权范围。

配置由群兴自己的 Profile 服务管理，Skill 只读取，不直接写入系统用户目录。冷启动访谈可借鉴，但要做成一次性所级配置和按需补充，而不是复制原插件的路径机制。

### 6.3 原始文件路径与写入方式不适合直接嵌入

上游大量 Skill 假定文件路径为 `~/.claude/plugins/config/...`，并直接要求写入 `matter.md`、`history.md`、`_log.yaml`。群兴已经有自己的客户/案件/材料管理体系，不能允许 Skill 绕过统一服务任意写磁盘或读取其他案件。

改造规则：

- 所有案件读写通过群兴案件服务；
- 所有文件访问由当前任务授权；
- 不允许跨案件读取，除非有明确权限和审计；
- 生成成果先进入草稿区，不自动覆盖原文件；
- 更新成果保留版本和 diff；
- Skill 不直接操作生产数据库。

### 6.4 法律规则参考文件不能视为现行法律数据库

中文包 README 说明若干领域内置了核心法律规则参考文件，例如合同法、民事程序、证据规则、公司法、知识产权、个人信息保护和行政法等。这些文件有很高的参考价值，但它们是静态文件。

群兴必须通过持衡共享法库或经批准的法律检索来源核对：

- 法律是否现行有效；
- 修订版本及施行日期；
- 司法解释是否有效；
- 地方规定和裁判口径是否适用；
- 案例是否真实、来源是否可靠；
- 是否存在新法过渡条款。

Skill 的静态参考文件只能用于提示分析方向，不能作为法律效力核验的最终依据。

### 6.5 刑事材料脱敏规则需认真处理

中文包刑事领域的 `CLAUDE.md` 和 `case-analysis` 设置了非常严格的脱敏红线，要求刑事案卷在分析前去除真实姓名、单位、案号等信息，并拒绝未经 OCR 和人工脱敏的卷宗图片/PDF。

这是该仓库明确的安全设计。群兴不能擅自删除这条保护要求。应由律所结合模型部署位置、数据是否出域、客户授权、保密义务和本地化处理能力，另行制定数据分级策略。在没有完成安全评估前，刑事材料默认按该严格规则执行；不能仅因为使用本地模型就自动取消脱敏。

### 6.6 法域、业务立场和阈值必须本地化

即使是中文包，也不能假设其中所有规则、条款阈值、风险评级、审批角色、期限计算都适合吉林省和群兴客户。所有地方性规则、法院实践、行政监管口径和金额阈值必须配置或实时核验。

### 6.7 Managed Agent Cookbook 不能直接当作本地 Skill 执行

例如 `diligence-grid` README 明确说明它面向 Managed Agents API，使用多个角色处理数据室文件，并要求对不可信文档实行只读隔离；每个表格单元格只是线索，不是尽调结论。

群兴第一阶段只吸收：

- 一份文件一行、一个信息点一列的表格抽取思路；
- 每个单元格附逐字来源引用；
- `unclear`、`needs_review` 等状态；
- 不可信文档只读处理；
- CSV 公式注入防护。

不部署其 Managed Agent 运行环境，也不复制多 Agent 编排。

## 七、群兴工作台应该如何接入：不是安装目录，而是建立 Skill Registry

### 7.1 建议的接入架构

```text
律师统一聊天入口
      |
      v
群兴任务识别与路由（主系统）
      |
      +---- 客户接待
      |       +-- matter-intake 方法
      |       +-- client-intake 方法
      |
      +---- 案件整理
      |       +-- chronology
      |       +-- claim-chart
      |       +-- criminal case-analysis（条件触发）
      |       +-- defense-strategy（条件触发）
      |
      +---- 合同审查
      |       +-- commercial review
      |       +-- NDA / vendor / SaaS 子流程
      |       +-- escalation 门禁
      |
      +---- 模拟法庭
              +-- chronology / claim-chart 输入
              +-- 持衡模拟法庭引擎
              +-- brief-section-drafter 输出纪律

统一 Skill Registry
      |
      +-- Skill 元数据、版本、来源、许可
      +-- 输入/输出 Schema
      +-- 权限和适用业务
      +-- 依赖与数据源声明
      +-- 启用/禁用/版本回滚
      +-- 调用记录与质量评分
```

Skill 是可组合的工作流模块。主系统负责任务、数据和权限；Skill 负责专业步骤、检查清单、输出约束。模型负责在授权上下文中完成推理，不负责决定系统权限。

### 7.2 Skill Registry 的最小元数据

每个 Skill 先转成统一登记记录。建议字段：

| 字段 | 含义 |
|---|---|
| `skill_id` | 稳定唯一标识，如 `litigation.chronology` |
| `display_name` | 中文显示名称 |
| `domain` | criminal / litigation / commercial / ip / employment 等 |
| `source_repo` | 原始仓库及路径 |
| `source_version` | 固定 commit/tag 和文件 SHA-256 |
| `license` | Apache-2.0 等 |
| `entrypoint` | 原 Skill 正文或群兴适配后的入口 |
| `triggers` | 适用任务类型和触发条件 |
| `inputs_schema` | 必需输入、可选输入、附件类型 |
| `outputs_schema` | 输出结构、引用、风险、待核事项 |
| `permissions` | 只读材料、可写草稿、禁止操作 |
| `dependencies` | 法库、MCP、文件解析器或其他 Skill |
| `risk_level` | 低/中/高及原因 |
| `human_gate` | 必须人工确认的步骤 |
| `enabled` | 是否启用 |
| `evaluation_status` | 未测/合成测试通过/律师抽检通过 |

**禁止仅以 Skill description 作为安全授权。** Description 只用于发现和路由，真正的权限必须由主系统执行。

### 7.3 Skill 执行契约

每次调用至少提供：

- 当前 `task_id`、`case_id`、`conversation_id`；
- 当前用户、权限范围及授权状态；
- 当前批次的材料 ID 和确切版本；
- 已确认事实、待核事实、禁止假设；
- 适用的业务画像和案件画像；
- 可用法律检索接口及其状态；
- 允许的输出类型和写入范围；
- 是否允许联网、是否允许模型调用及费用上限。

每次调用必须返回结构化结果：

- `status`：completed / needs_review / blocked / failed；
- `summary`：结论摘要；
- `findings[]`：发现、风险、重要性；
- `citations[]`：材料来源或法律来源；
- `assumptions[]`：假设；
- `missing_information[]`：缺失资料；
- `counterarguments[]`：反向因素；
- `recommended_next_steps[]`：建议后续；
- `human_decisions[]`：必须由律师决定的事项；
- `artifacts[]`：生成成果 ID；
- `skill_version`、`model_version`、`material_versions`。

上游 Skill 是 Markdown 指令，不一定天然满足结构化契约。应通过适配层把输出规范化，不要强迫所有上游 Skill 改写成同一套复杂 Agent。

### 7.4 加载策略：按需加载，不能把157个 Skill 全塞进系统提示词

建议分三级：

- **一级：常驻规则。** 群兴通用法律工作纪律、数据安全、引用纪律、任务权限、客户稿/内部稿隔离。
- **二级：领域路由 Skill。** 商事合同、诉讼、刑事、IP、劳动等领域适配器，仅负责判断该调用哪个专项工作流。
- **三级：专项 Skill。** 只有识别到对应任务时，才加载完整 Skill 正文及其 references。

例如用户上传一份供应商合同，主系统先识别为商事合同，再调用 `commercial.review`；该流程识别出 NDA 附件后，才追加 NDA 检查。没有必要在每个会话里加载刑事辩护、劳动解除、AI治理和法考技能。

---

## 八、具体实施顺序：建议分四轮，不要一口气全量接入

### 第一轮：只读盘点与样本评估

Codex 任务：

1. 解压到独立只读目录，不要解压覆盖群兴主仓库。
2. 生成完整文件清单、SHA-256 清单和领域目录清单。
3. 识别 `CLAUDE.md`、`SKILL.md`、`references/`、`scripts/`、MCP 配置、安装脚本、Cookbook。
4. 对第一批候选逐个读取完整 Skill 正文和依赖引用。
5. 检查是否有硬编码 `~/.claude`、美国法、外部 API、云端数据传输、自动写文件、发送邮件/函件、自动化调度等行为。
6. 输出候选技能与群兴现有功能对照表，标记重复、互补、冲突和缺失。
7. 不安装、不复制、不改写产品代码。

**交付：** `docs/audits/legal-skills/skill-inventory.md`、`skill-source-manifest.json`、`candidate-assessment.md`。

### 第二轮：提取方法论，不接运行时

先把以下规则提取为群兴现有能力的质量门禁：

- 事实逐项引用；
- 时间线去重及攻防重要性；
- 控辩双方构成要件对照；
- 合同类型识别和我方立场确认；
- Deal-breaker 前置检查；
- NDA 隐藏义务识别；
- 高风险事项升级；
- 警告函发送前主体尽调和人工确认；
- 文书逐字引用和弱论点披露；
- 客户稿/内部稿区分。

这些规则先进入当前四项能力的流程设计和测试，不新增 Skill 菜单。

**交付：** `docs/quality-gates/` 下的流程说明、输入输出 Schema 和合成验收样例。

### 第三轮：选择性挂载第一批 Skill

建议优先试点6个，不要第一轮就接入全部12个 P0：

1. `litigation-legal/chronology`
2. `litigation-legal/brief-section-drafter`
3. `criminal-legal/case-analysis`
4. `criminal-legal/defense-strategy`
5. `commercial-legal/review`
6. `ip-legal/infringement-triage`

理由：这6个覆盖案件整理、刑事辩护、文书质量、合同路由和知识产权案件，能用现有虚构材料设计明确验收场景；同时能验证 Skill Registry 和任务适配层是否真的可用。

通过后再追加：

- `matter-intake`；
- `bail-application`；
- `vendor-agreement-review`；
- `nda-review`；
- `cease-desist`；
- `termination-review`。

### 第四轮：根据真实业务量扩展

当群兴出现稳定的并购尽调、公司治理、数据合规、AI治理、监管监控和合同续约业务时，再接入对应领域。没有实际业务、数据源、负责人和验收场景的 Skill 不应提前启用。

---

## 九、建议的文件组织方式

不要把完整上游仓库全部复制到群兴产品主仓库。建议在主项目中维护适配后的最小目录：

```text
src/
  skills/
    registry.py                 # 技能登记与版本管理（按现有语言栈调整）
    router.py                   # 技能路由（复用现有任务路由）
    contracts/
      skill-input.schema.json
      skill-output.schema.json
    adapters/
      claude_for_legal/
        litigation/
        criminal/
        commercial/
        ip/
    policies/
      legal-quality-gates/
        evidence-citation.md
        chronology.md
        adversarial-review.md
        contract-review.md
        external-send-gate.md

docs/
  integrations/
    claude-for-legal/
      source-manifest.json
      license-notice.md
      skill-selection.md
      compatibility.md
  quality-gates/
  testing/
```

此目录是目标示例，Codex 必须先检查主项目实际架构、语言和目录约定，再决定最终位置。不要为符合示例而制造重复架构。

源 Skill 原文应以固定版本作为上游只读来源；群兴的本地改造放在适配层，并记录与上游的差异。不要直接修改上游文件后失去升级对照。

---

## 十、验收方案：每个 Skill 必须证明质量提升，而不是“调用成功”

### 10.1 通用验收项

每个 Skill 至少通过：

1. 路由正确：适用时触发，不适用时不触发；
2. 输入完整：缺少关键事实时明确询问，不自行补造；
3. 材料来源：每个事实可回溯到原材料及版本；
4. 法律来源：法条/案例可核验，未核验时明确标记；
5. 反方分析：至少识别关键不利事实和反向论点；
6. 权限约束：不能读取其他案件或越权写入；
7. 输出结构：符合群兴统一 Schema；
8. 人工门禁：需要律师决定的事项不自动执行；
9. 幂等与版本：重复触发不产生重复成果，更新保留旧版本；
10. 可关闭：技能失败时能回退到原有流程，不阻断主系统。

### 10.2 第一批六项验收矩阵

| Skill | 合成测试材料 | 核心验收 |
|---|---|---|
| chronology | 虚构合同、聊天、转账、证言时间点 | 事件排序正确、重复事件合并、每条有来源、冲突日期不擅自统一 |
| brief-section-drafter | 虚构证据清单、争点和文书要求 | 事实逐项引用、法律命题标注来源、弱论点提示、无虚构引语 |
| criminal case-analysis | 脱敏后的虚构讯问笔录、证言和客观证据 | 供述矛盾、客观证据冲突、证据链缺口、排非线索被标记 |
| defense-strategy | 虚构罪名指控和事实摘要 | 构成要件逐项分析、控方逻辑、辩方反驳、事实不足不作确定结论 |
| commercial review | 虚构供应商合同、NDA及DPA附件 | 正确识别合同类型和我方立场、先检查 Deal-breaker、整合单一备忘录 |
| infringement-triage | 虚构商标权利证明、使用证据和被控标识 | 权利类型分开、双方因素列明、不直接输出侵权定论、不自动发函 |

### 10.3 质量比较方法

每个候选 Skill 做同一组样本的 A/B 比较：

- A组：群兴当前原始工作流；
- B组：群兴工作流 + 候选 Skill 方法论。

由律师按统一评分表比较：

| 维度 | 评分标准 |
|---|---|
| 事实完整性 | 是否遗漏关键事实，是否编造 |
| 证据可追溯性 | 事实是否能定位原文、页码/段落/时间 |
| 法律依据准确性 | 是否有真实来源，是否提示时效核验 |
| 争点覆盖 | 是否覆盖主要争议和构成要件 |
| 反方分析 | 是否识别不利事实、反方论证和失败风险 |
| 可操作性 | 建议是否具体、能否指导下一步 |
| 风险控制 | 是否遵守权限、脱敏、审批和输出隔离 |
| 结果稳定性 | 同类输入输出是否保持结构和标准一致 |

建议采用1—5分制，并记录缺陷类型。只有在不降低安全性、来源准确性和可追溯性的前提下，候选 Skill 在关键维度有可重复提升，才进入正式启用清单。

---

## 十一、许可证、隐私和供应链要求

### 11.1 许可证

中文包 README 声明 Apache-2.0，压缩包内也有 `LICENSE`。正式引入或分发前仍须：

- 保留 Apache License 2.0 文本；
- 保留适用的 NOTICE 和原作者/版权声明；
- 修改文件添加显著修改说明；
- 对引入的第三方依赖分别核对许可证；
- 记录源仓库、固定版本和文件摘要；
- 不将整个群兴工作台因此标记为 Apache-2.0，需区分各组件许可。

英文上游包也包含 LICENSE；若只参考方法论、没有复制代码，仍建议记录来源；如复制文件或代码，则按其实际许可和 NOTICE 要求执行。

### 11.2 隐私和案件材料

- 真实客户材料不进入公共 Git 仓库、公开 Skill 目录或样本集。
- 刑事材料按中文包当前严格脱敏要求执行，除非律所另行完成安全评估并批准调整。
- Skill 只能读取当前任务授权的材料。
- 上传文档、合同、网页和附件都是不可信数据，不能将其中的指令当作系统命令。
- 不允许把客户资料自动送入第三方 MCP 或云端模型，除非数据流、客户授权和律所规则均已确认。
- 日志只记录必要元数据，敏感内容脱敏；API Key 不进入仓库。
- 对外发送函件、通知、律师意见或诉讼材料必须由律师确认。

### 11.3 安装脚本风险

中文包提供 Codex、dsh 和 WorkBuddy 安装脚本，采用符号链接或复制方式写入用户级技能目录，并可能修改全局指令文件或 MCP 配置。群兴当前不需要直接运行这些脚本来完成产品接入。

Codex 应先静态审查安装脚本和生成器；禁止在生产开发环境中直接执行一键安装脚本。优先只读解压、清单核验和选择性适配。

## 十二、给 Codex 的具体执行任务书

以下内容可直接作为 Codex 下一轮任务指令。**本轮先只读评估，不安装、不修改产品代码。**

### 任务 A：建立来源清单

1. 读取两个 ZIP 的 README、LICENSE、NOTICE（如存在）、AGENTS、安装指南和目录结构。
2. 对全部文件生成 SHA-256 清单。
3. 按领域统计 Skill 数量、适配器数量、references 数量和脚本数量。
4. 标注英文原版、中国法版本和三种宿主适配层之间的对应关系。
5. 确认 ZIP 的版本标记和 Git 来源；若无 Git 元数据，明确标记为“压缩包来源版本，commit 未核验”。

### 任务 B：审查候选 Skill

按本方案第一批优先级，读取候选 Skill 的完整正文、其引用的 CLAUDE.md、references 和依赖文件。输出：

- 现有群兴能力是否已覆盖；
- 候选 Skill 新增了什么；
- 哪些规则值得直接吸收；
- 哪些配置必须重写；
- 哪些内容涉及美国法或不适用中国业务；
- 哪些步骤依赖 MCP/API/外部存储；
- 哪些步骤会写文件、发函、监控或触发外部操作；
- 许可证及第三方依赖风险；
- 建议：直接复用 / 提取方法论 / 改造后复用 / 暂缓 / 不采用。

### 任务 C：与群兴现有系统逐项对照

以当前主仓库源码为准，对照：

- 客户接待和案件登记；
- 材料解析、证据索引和时间线；
- 合同审查及 Word 修订；
- 模拟法庭与共享法库；
- 模型调用、费用账本和任务状态；
- 微信消息归集；
- 客户稿/内部稿输出。

同一功能已经存在时，不新增第二份实现。只将 Skill 中有价值的检查步骤并入现有流程。

### 任务 D：形成最小实施 PR 计划（暂不提交）

给出文件级改造清单、接口 Schema、测试样本、回归命令和风险。未经用户批准，不安装、不改产品代码、不提交推送。

## 十三、建议的最终产品形态

律师看到的始终是：

- 客户接待；
- 案件整理；
- 合同审查；
- 模拟法庭。

律师输入任务后，系统在后台按需调用专项 Skill。比如：

**示例一：刑事案件**

律师上传脱敏材料并输入“帮我分析这个刑事案件”。

后台流程：案件整理 -> 刑事案卷分析 -> 证据矛盾识别 -> 犯罪构成要件分析 -> 辩护策略 -> 模拟法庭。系统将各步骤成果写回同一个案件任务，所有事实都保留材料来源。

**示例二：商标侵权**

律师输入“对方使用了和我方注册商标近似的标识”。

后台流程：案件整理 -> 知识产权类型识别 -> 商标侵权初步筛查 -> 双方有利不利因素 -> 证据缺口 -> 维权路径建议。只有律师确认后，才进入警告函起草；发送仍需单独确认。

**示例三：供应商合同**

律师上传主合同、订单和 NDA，输入“审查一下”。

后台流程：合同类型和我方立场识别 -> 主合同审查 -> NDA 专项审查 -> Deal-breaker 检查 -> 具体替代条款 -> 审批升级 -> 单一审查备忘录。不能把附件漏掉，也不能让 NDA 子流程另起一个案件或另建材料副本。

## 十四、最终建议与决策

### 14.1 建议采用

- 采用中文包作为中国法律方法论主要参考；
- 英文包只用于追溯上游结构和方法来源；
- 第一阶段重点吸收证据引用、时间线、案件登记、刑事证据链、合同类型路由和审批门禁；
- 先把方法论融入群兴四项核心能力，再逐步挂载专项 Skill；
- 使用统一 Skill Registry 和统一任务服务；
- 保留持衡共享法库作为法源底座，避免复制法律数据库；
- 采用按需加载，不将全部 Skill 注入每次模型上下文；
- 所有法律输出保持律师审查草稿定位。

### 14.2 建议暂不采用

- 不安装全部157个领域 Skill；
- 不同时安装三套适配器到群兴生产运行时；
- 不部署 Managed Agent Cookbook 的整套多 Agent 服务；
- 不直接执行上游一键安装脚本；
- 不让每个 Skill 自建客户、案件和材料目录；
- 不将静态法律参考文件视为现行法数据库；
- 不自动发送警告函、律师函、客户回复或法院材料。

### 14.3 当前应先做的六件事

1. 对照群兴主仓库，确认已有功能和真正缺口；
2. 修复0.6.0审计报告中的 S1、S2；
3. 把 `chronology`、`brief-section-drafter` 的证据和文书纪律融入案件整理；
4. 把 `commercial.review` 的合同路由和 `vendor-agreement-review` 的质量门禁融入合同审查；
5. 选择刑事 `case-analysis`、`defense-strategy` 做第一批专项试点；
6. 建立 Skill Registry，先登记版本和调用状态，再逐步接入更多 Skill。

**最终判断：这套法律 Skill 库适合成为群兴工作台的“专业方法库和质量控制层”，不适合成为群兴工作台的第二套产品内核。群兴自己的优势应当是统一任务、统一材料、统一权限、统一模型和统一成果交付；外部 Skill 只负责在正确的节点补足专业工作方法。**

---

## 附：本次审查的来源范围

本次直接读取的主要文件包括：

- `claude-for-legal-ZH-main/README.md`
- `claude-for-legal-ZH-main/AGENTS.md`
- `claude-for-legal-ZH-main/INSTALL_CODEX.md`
- `claude-for-legal-ZH-main/INSTALL_DSH.md`
- `claude-for-legal-ZH-main/INSTALL_WORKBUDDY.md`
- `claude-for-legal-ZH-main/LICENSE`
- `commercial-legal/CLAUDE.md` 及 `review`、`nda-review`、`vendor-agreement-review`
- `litigation-legal/CLAUDE.md` 及 `chronology`、`brief-section-drafter`、`matter-intake`
- `criminal-legal/CLAUDE.md` 及 `case-analysis`、`defense-strategy`
- `ip-legal/CLAUDE.md` 及 `infringement-triage`、`cease-desist`
- `employment-legal/skills/termination-review/SKILL.md`
- `managed-agent-cookbooks/diligence-grid/README.md`

本次没有逐字审阅全部157个 Skill 的全部正文和所有 references，也没有执行安装脚本或运行技能。因此，本文件是基于完整目录盘点、核心说明文件及代表性 Skill 抽样阅读形成的**集成取舍方案**，不是对全部技能逐项作出的安全认证或法律准确性认证。Codex 在正式引入任何候选 Skill 前，仍须完成该技能及其依赖文件的完整审查。
