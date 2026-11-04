# AI师兄法律助手平台 Skill 逐项核对（2026-11-04）

范围：175 个法律库入口/工作流 + 10 个定制与辅助 Skill，共 185 个。名称来自 config/skill-labels.zh-CN.json；内部 ID 保持不变。

## 可复核结论

- 源工作区、安装包 seed、安装后用户工作区均通过官方 FileSystemSkillProvider 实际 list/get：每处 185/185，允许模型调用 185/185，无解析警告、重名或遗漏。
- 核对 1,544 条明确本地引用、502 条嵌套调用记录；修复后没有必需资源缺失或法律领域嵌套名称未解析。仅检查加载、引用及调用接口，不等于逐个业务情境都由模型完成。
- 材料服务真实暴露 11 个工具，法律服务 17 个；reception、contract、case、hearing 四个方法实际读取成功；四主业务 Skill 中 38 处明确调用均对应已注册工具。
- 19 个辅助脚本入口存在；6 个明确本地 JavaScript import 可解析；15 个 JavaScript 文件仅语法解析通过，未执行原库脚本。
- 20 条非阻断提示已逐条区分：7 个“如存在”的英文对照、4 个首次生成文件/缓存、6 个文档示例、2 个上游 README 自链接、1 个上游 Claude 插件安装调用示例。没有将这些记作失败。

## 本次修复与运行条件

1. impeccable 的 Windows 启动路径改为实际 Skill 根目录下的 scripts/impeccable.cmd，避免固定 .agents 路径在 .dsh 平台中失效。启动器的无下载探测能到达正确入口；包内没有设计引擎二进制，探测返回 127。首次使用依赖引擎下载，当前未声称引擎执行通过；技能已有无法启动时读取现有设计资料的回落方式。
2. windows-desktop 明确 USER_CONTROL 表示用户占用控制权：暂停桌面动作，不轮换 PowerShell/FileSystem 连续重试；独立文件/材料工具可继续，待用户释放后再观察续接。
3. design-taste-frontend 未附带可选 scenes.json/场景示例。现有 draw 脚本已回落为空场景列表；不生成伪造模板。
4. 未验收任何外部业务连接器（0 个）。7 个 Skill 主文明确提及 Gmail、Slack、SharePoint 或 DMS 文档系统；当前项目未注册这些专用连接器，相关流程应交付本地文字/文件或在另行连接后使用。CLM 的 QA 提问、Salesforce 合同示例和 humanizer 的 Future Outlook 文案不计作运行依赖。此数量不代表对原始领域参考模板中所有第三方产品的普查。

## 安装副本（部署后复核）

复核时间：2026-11-04T09:43:03.385Z。

- installed-seed：与源完整一致。
- installed-user：与源完整一致。

主任务已同步安装包 seed，并按修改前哈希安全更新用户 Skill。以上是部署后的实际全量加载与完整文件对比结果；修改前哈希和本机迁移回执保存在 report.json，便于追溯。

## 全部 Skill

| 中文名 | 内部 ID | 加载/资源/映射 | 条件或说明 |
|---|---|---|---|
| 浏览器操作 | bb-browser | 通过 | 浏览器连接/登录、联网资料；2 条非阻断提示 |
| AI 治理 | chinese-legal-ai-governance | 通过 | 无额外静态标记 |
| 法律技能运营 | chinese-legal-builder-hub | 通过 | 无额外静态标记 |
| 法律诊所 | chinese-legal-clinic | 通过 | 无额外静态标记 |
| 商事合同 | chinese-legal-commercial | 通过 | 无额外静态标记 |
| 公司与并购 | chinese-legal-corporate | 通过 | 无额外静态标记 |
| 刑事辩护与合规 | chinese-legal-criminal | 通过 | 无额外静态标记 |
| 尽调问题表格 | chinese-legal-diligence-grid | 通过 | 定时运行条件 |
| 案件期限监控 | chinese-legal-docket-watcher | 通过 | 定时运行条件 |
| 劳动用工 | chinese-legal-employment | 通过 | 无额外静态标记 |
| 知识产权 | chinese-legal-ip | 通过 | 无额外静态标记 |
| 产品上线风险汇总 | chinese-legal-launch-radar | 通过 | 定时运行条件 |
| 法学学习与法考 | chinese-legal-law-student | 通过 | 无额外静态标记 |
| 诉讼与仲裁 | chinese-legal-litigation | 通过 | 无额外静态标记 |
| 数据合规与隐私 | chinese-legal-privacy | 通过 | 无额外静态标记 |
| 产品与营销合规 | chinese-legal-product | 通过 | 无额外静态标记 |
| 监管动态监控 | chinese-legal-reg-monitor | 通过 | 定时运行条件 |
| 监管合规 | chinese-legal-regulatory | 通过 | 无额外静态标记 |
| 合同续约监控 | chinese-legal-renewal-watcher | 通过 | 定时运行条件 |
| 网页视觉设计 | design-taste-frontend | 通过 | 无额外静态标记；5 条非阻断提示 |
| 文字润色与去除 AI 痕迹 | humanizer | 通过 | 联网资料、外部服务文字提及（非已连接）；1 条非阻断提示 |
| 界面设计与优化 | impeccable | 通过 | 无额外静态标记；1 条非阻断提示 |
| AI 系统清单编制 | legal-zh-ai-governance-ai-inventory | 通过 | 无额外静态标记 |
| AI 系统风险与合规评估 | legal-zh-ai-governance-aia-generation | 通过 | 联网资料 |
| AI 治理初始配置 | legal-zh-ai-governance-cold-start-interview | 通过 | 联网资料 |
| AI 治理设置调整 | legal-zh-ai-governance-customize | 通过 | 无额外静态标记 |
| AI 治理事项管理 | legal-zh-ai-governance-matter-workspace | 通过 | 无额外静态标记 |
| AI 使用政策监测 | legal-zh-ai-governance-policy-monitor | 通过 | 联网资料、定时运行条件 |
| AI 使用政策起草 | legal-zh-ai-governance-policy-starter | 通过 | 联网资料 |
| AI 合规差距分析 | legal-zh-ai-governance-reg-gap-analysis | 通过 | 联网资料 |
| AI 应用风险分级 | legal-zh-ai-governance-use-case-triage | 通过 | 联网资料 |
| AI 供应商合同审查 | legal-zh-ai-governance-vendor-ai-review | 通过 | 联网资料 |
| 法律技能更新 | legal-zh-builder-hub-auto-updater | 通过 | 联网资料 |
| 法律技能初始配置 | legal-zh-builder-hub-cold-start-interview | 通过 | 无额外静态标记 |
| 法律技能设置调整 | legal-zh-builder-hub-customize | 通过 | 无额外静态标记 |
| 法律技能停用与启用 | legal-zh-builder-hub-disable | 通过 | 无额外静态标记 |
| 法律技能搜索 | legal-zh-builder-hub-registry-browser | 通过 | 联网资料；1 条非阻断提示 |
| 相关法律技能推荐 | legal-zh-builder-hub-related-skills-surfacer | 通过 | 无额外静态标记；1 条非阻断提示 |
| 法律技能安装 | legal-zh-builder-hub-skill-installer | 通过 | 联网资料 |
| 法律技能管理 | legal-zh-builder-hub-skill-manager | 通过 | 无额外静态标记 |
| 法律技能质量评估 | legal-zh-builder-hub-skills-qa | 通过 | 联网资料、外部服务文字提及（非已连接） |
| 法律技能卸载 | legal-zh-builder-hub-uninstall | 通过 | 无额外静态标记 |
| 诊所实践指南编写 | legal-zh-clinic-build-guide | 通过 | 无额外静态标记 |
| 诊所当事人沟通记录 | legal-zh-clinic-client-comms-log | 通过 | 无额外静态标记 |
| 诊所当事人接待 | legal-zh-clinic-client-intake | 通过 | 无额外静态标记 |
| 诊所日常信函起草 | legal-zh-clinic-client-letter | 通过 | 无额外静态标记 |
| 法律诊所初始配置 | legal-zh-clinic-cold-start-interview | 通过 | 定时运行条件 |
| 法律诊所设置调整 | legal-zh-clinic-customize | 通过 | 无额外静态标记 |
| 诊所案件期限管理 | legal-zh-clinic-deadlines | 通过 | 无额外静态标记 |
| 诊所法律文书起草 | legal-zh-clinic-draft | 通过 | 无额外静态标记 |
| 诊所表格生成（旧入口） | legal-zh-clinic-form-generation | 通过 | 无额外静态标记 |
| 诊所案件分析提纲 | legal-zh-clinic-memo | 通过 | 无额外静态标记 |
| 诊所通俗信函（旧入口） | legal-zh-clinic-plain-language-letters | 通过 | 无额外静态标记 |
| 法律诊所学期入门 | legal-zh-clinic-ramp | 通过 | 定时运行条件 |
| 法律检索路线规划 | legal-zh-clinic-research-start | 通过 | 无额外静态标记 |
| 诊所学期案件交接 | legal-zh-clinic-semester-handoff | 通过 | 无额外静态标记 |
| 诊所案件进展摘要 | legal-zh-clinic-status | 通过 | 无额外静态标记 |
| 诊所指导老师审阅 | legal-zh-clinic-supervisor-review-queue | 通过 | 无额外静态标记 |
| 合同修订历史追踪 | legal-zh-commercial-amendment-history | 通过 | 无额外静态标记 |
| 商事合同初始配置 | legal-zh-commercial-cold-start-interview | 通过 | 无额外静态标记 |
| 商事合同设置调整 | legal-zh-commercial-customize | 通过 | 无额外静态标记 |
| 合同风险上报 | legal-zh-commercial-escalation-flagger | 通过 | 无额外静态标记 |
| 商事合同事项管理 | legal-zh-commercial-matter-workspace | 通过 | 无额外静态标记 |
| 保密协议审查 | legal-zh-commercial-nda-review | 通过 | 无额外静态标记 |
| 合同续约期限追踪 | legal-zh-commercial-renewal-tracker | 通过 | 无额外静态标记 |
| 商事合同综合审查 | legal-zh-commercial-review | 通过 | 联网资料、定时运行条件 |
| 合同审查指引更新处理 | legal-zh-commercial-review-proposals | 通过 | 无额外静态标记 |
| 软件订阅服务协议审查 | legal-zh-commercial-saas-msa-review | 通过 | 无额外静态标记 |
| 合同审查业务摘要 | legal-zh-commercial-stakeholder-summary | 通过 | 无额外静态标记 |
| 供应商协议审查 | legal-zh-commercial-vendor-agreement-review | 通过 | 无额外静态标记 |
| 尽调 AI 工具协作 | legal-zh-corporate-ai-tool-handoff | 通过 | 无额外静态标记 |
| 董事会会议纪要起草 | legal-zh-corporate-board-minutes | 通过 | 无额外静态标记 |
| 交易交割清单 | legal-zh-corporate-closing-checklist | 通过 | 无额外静态标记 |
| 公司与并购初始配置 | legal-zh-corporate-cold-start-interview | 通过 | 无额外静态标记；1 条非阻断提示 |
| 公司与并购设置调整 | legal-zh-corporate-customize | 通过 | 无额外静态标记 |
| 交易团队尽调简报 | legal-zh-corporate-deal-team-summary | 通过 | 无额外静态标记 |
| 尽调问题提取 | legal-zh-corporate-diligence-issue-extraction | 通过 | 联网资料、定时运行条件 |
| 公司主体合规追踪 | legal-zh-corporate-entity-compliance | 通过 | 无额外静态标记 |
| 并购交割后整合管理 | legal-zh-corporate-integration-management | 通过 | 外部服务文字提及（非已连接） |
| 重大合同披露清单 | legal-zh-corporate-material-contract-schedule | 通过 | 无额外静态标记 |
| 公司与并购事项管理 | legal-zh-corporate-matter-workspace | 通过 | 无额外静态标记 |
| 批量文件表格审查 | legal-zh-corporate-tabular-review | 通过 | 无额外静态标记 |
| 董事会书面决议起草 | legal-zh-corporate-written-consent | 通过 | 无额外静态标记 |
| 取保候审与羁押审查申请 | legal-zh-criminal-bail-application | 通过 | 无额外静态标记；1 条非阻断提示 |
| 刑事案卷与证据链梳理 | legal-zh-criminal-case-analysis | 通过 | 无额外静态标记；1 条非阻断提示 |
| 刑事业务初始配置 | legal-zh-criminal-cold-start-interview | 通过 | 无额外静态标记；1 条非阻断提示 |
| 涉案企业合规不起诉评估 | legal-zh-criminal-compliance-non-prosecution | 通过 | 无额外静态标记；1 条非阻断提示 |
| 刑事业务设置调整 | legal-zh-criminal-customize | 通过 | 无额外静态标记；1 条非阻断提示 |
| 刑事辩护策略分析 | legal-zh-criminal-defense-strategy | 通过 | 无额外静态标记；1 条非阻断提示 |
| 刑事案件事项管理 | legal-zh-criminal-matter-workspace | 通过 | 无额外静态标记；1 条非阻断提示 |
| 劳动用工初始配置 | legal-zh-employment-cold-start-interview | 通过 | 外部服务文字提及（非已连接） |
| 劳动用工设置调整 | legal-zh-employment-customize | 通过 | 无额外静态标记 |
| 跨地域用工规划启动 | legal-zh-employment-expansion-kickoff | 通过 | 无额外静态标记 |
| 跨地域用工进展更新 | legal-zh-employment-expansion-update | 通过 | 无额外静态标记 |
| 员工规章制度修订比对 | legal-zh-employment-handbook-updates | 通过 | 无额外静态标记 |
| 录用通知与入职条款审查 | legal-zh-employment-hiring-review | 通过 | 联网资料、定时运行条件 |
| 内部调查工作框架 | legal-zh-employment-internal-investigation | 通过 | 无额外静态标记 |
| 跨境用工规划框架 | legal-zh-employment-international-expansion | 通过 | 无额外静态标记 |
| 内部调查材料补充 | legal-zh-employment-investigation-add | 通过 | 无额外静态标记 |
| 内部调查备忘录起草 | legal-zh-employment-investigation-memo | 通过 | 无额外静态标记 |
| 内部调查事项启动 | legal-zh-employment-investigation-open | 通过 | 无额外静态标记 |
| 内部调查记录查询 | legal-zh-employment-investigation-query | 通过 | 无额外静态标记 |
| 内部调查结果摘要 | legal-zh-employment-investigation-summary | 通过 | 无额外静态标记 |
| 员工休假期限追踪 | legal-zh-employment-leave-tracker | 通过 | 定时运行条件 |
| 员工休假登记 | legal-zh-employment-log-leave | 通过 | 无额外静态标记 |
| 劳动用工事项管理 | legal-zh-employment-matter-workspace | 通过 | 无额外静态标记 |
| 员工规章制度起草 | legal-zh-employment-policy-drafting | 通过 | 无额外静态标记 |
| 劳动合同解除审查 | legal-zh-employment-termination-review | 通过 | 联网资料、定时运行条件 |
| 工资工时与休假咨询 | legal-zh-employment-wage-hour-qa | 通过 | 联网资料、定时运行条件 |
| 劳动关系认定分析 | legal-zh-employment-worker-classification | 通过 | 联网资料 |
| 侵权警告函起草与应对 | legal-zh-ip-cease-desist | 通过 | 无额外静态标记 |
| 商标冲突初步检索 | legal-zh-ip-clearance | 通过 | 定时运行条件 |
| 知识产权初始配置 | legal-zh-ip-cold-start-interview | 通过 | 外部服务文字提及（非已连接） |
| 知识产权设置调整 | legal-zh-ip-customize | 通过 | 外部服务文字提及（非已连接） |
| 专利自由实施初筛 | legal-zh-ip-fto-triage | 通过 | 无额外静态标记 |
| 知识产权侵权初筛 | legal-zh-ip-infringement-triage | 通过 | 无额外静态标记 |
| 发明披露初步评估 | legal-zh-ip-invention-intake | 通过 | 联网资料 |
| 知识产权条款审查 | legal-zh-ip-ip-clause-review | 通过 | 联网资料 |
| 知识产权事项管理 | legal-zh-ip-matter-workspace | 通过 | 无额外静态标记 |
| 开源许可证合规审查 | legal-zh-ip-oss-review | 通过 | 联网资料 |
| 知识产权资产管理 | legal-zh-ip-portfolio | 通过 | 无额外静态标记 |
| 著作权通知删除与反通知 | legal-zh-ip-takedown | 通过 | 无额外静态标记 |
| 法考备考练习 | legal-zh-law-student-bar-prep-questions | 通过 | 联网资料 |
| 法学案例摘要 | legal-zh-law-student-case-brief | 通过 | 无额外静态标记 |
| 课堂提问准备 | legal-zh-law-student-cold-call-prep | 通过 | 无额外静态标记 |
| 法学学习初始配置 | legal-zh-law-student-cold-start-interview | 通过 | 无额外静态标记 |
| 法学学习设置调整 | legal-zh-law-student-customize | 通过 | 无额外静态标记 |
| 历年考题与考点分析 | legal-zh-law-student-exam-forecast | 通过 | 无额外静态标记 |
| 法条概念记忆卡片 | legal-zh-law-student-flashcards | 通过 | 无额外静态标记 |
| 法律论证练习批改 | legal-zh-law-student-irac-practice | 通过 | 无额外静态标记 |
| 法律写作反馈 | legal-zh-law-student-legal-writing | 通过 | 无额外静态标记 |
| 法学课程大纲整理 | legal-zh-law-student-outline-builder | 通过 | 无额外静态标记 |
| 法学专项练习 | legal-zh-law-student-session | 通过 | 无额外静态标记 |
| 法学追问训练 | legal-zh-law-student-socratic-drill | 通过 | 无额外静态标记 |
| 法学备考计划 | legal-zh-law-student-study-plan | 通过 | 无额外静态标记 |
| 诉讼文书章节起草 | legal-zh-litigation-brief-section-drafter | 通过 | 无额外静态标记 |
| 案件时间线整理 | legal-zh-litigation-chronology | 通过 | 联网资料 |
| 构成要件与证据对照 | legal-zh-litigation-claim-chart | 通过 | 无额外静态标记 |
| 诉讼业务初始配置 | legal-zh-litigation-cold-start-interview | 通过 | 无额外静态标记 |
| 诉讼业务设置调整 | legal-zh-litigation-customize | 通过 | 无额外静态标记 |
| 律师函起草 | legal-zh-litigation-demand-draft | 通过 | 无额外静态标记 |
| 律师函委托登记 | legal-zh-litigation-demand-intake | 通过 | 无额外静态标记 |
| 收到律师函分析应对 | legal-zh-litigation-demand-received | 通过 | 联网资料 |
| 证人庭前准备 | legal-zh-litigation-deposition-prep | 通过 | 无额外静态标记 |
| 证据保全通知管理 | legal-zh-litigation-legal-hold | 通过 | 无额外静态标记 |
| 单案深度简报 | legal-zh-litigation-matter-briefing | 通过 | 无额外静态标记 |
| 诉讼案件结案归档 | legal-zh-litigation-matter-close | 通过 | 无额外静态标记 |
| 诉讼新案登记 | legal-zh-litigation-matter-intake | 通过 | 无额外静态标记 |
| 诉讼案件进展记录 | legal-zh-litigation-matter-update | 通过 | 无额外静态标记 |
| 诉讼案件工作区管理 | legal-zh-litigation-matter-workspace | 通过 | 无额外静态标记 |
| 外聘律师进展询函 | legal-zh-litigation-oc-status | 通过 | 外部服务文字提及（非已连接） |
| 全部诉讼案件状态汇总 | legal-zh-litigation-portfolio-status | 通过 | 无额外静态标记 |
| 证据三性审查 | legal-zh-litigation-privilege-log-review | 通过 | 无额外静态标记 |
| 调查令与协查通知处理 | legal-zh-litigation-subpoena-triage | 通过 | 联网资料 |
| 数据合规初始配置 | legal-zh-privacy-cold-start-interview | 通过 | 定时运行条件 |
| 数据合规设置调整 | legal-zh-privacy-customize | 通过 | 外部服务文字提及（非已连接） |
| 数据处理协议审查 | legal-zh-privacy-dpa-review | 通过 | 联网资料、定时运行条件 |
| 个人信息权利请求回复 | legal-zh-privacy-dsar-response | 通过 | 联网资料、定时运行条件 |
| 数据合规事项管理 | legal-zh-privacy-matter-workspace | 通过 | 无额外静态标记 |
| 个人信息保护影响评估 | legal-zh-privacy-pia-generation | 通过 | 联网资料、定时运行条件 |
| 个人信息处理规则监测 | legal-zh-privacy-policy-monitor | 通过 | 定时运行条件 |
| 个人信息合规差距分析 | legal-zh-privacy-reg-gap-analysis | 通过 | 联网资料、定时运行条件 |
| 个人信息处理活动分流 | legal-zh-privacy-use-case-triage | 通过 | 定时运行条件 |
| 产品法务初始配置 | legal-zh-product-cold-start-interview | 通过 | 外部服务文字提及（非已连接）；1 条非阻断提示 |
| 产品法务设置调整 | legal-zh-product-customize | 通过 | 无额外静态标记 |
| 产品功能法律风险评估 | legal-zh-product-feature-risk-assessment | 通过 | 联网资料 |
| 产品法务快速咨询 | legal-zh-product-is-this-a-problem | 通过 | 无额外静态标记 |
| 产品上线合规审查 | legal-zh-product-launch-review | 通过 | 联网资料、外部服务文字提及（非已连接） |
| 营销宣传文案审查 | legal-zh-product-marketing-claims-review | 通过 | 联网资料 |
| 产品法务事项管理 | legal-zh-product-matter-workspace | 通过 | 无额外静态标记 |
| 监管合规初始配置 | legal-zh-regulatory-cold-start-interview | 通过 | 联网资料 |
| 法规征求意见事项跟踪 | legal-zh-regulatory-comments | 通过 | 无额外静态标记 |
| 监管合规设置调整 | legal-zh-regulatory-customize | 通过 | 无额外静态标记 |
| 合规差距跟踪框架 | legal-zh-regulatory-gap-surfacer | 通过 | 定时运行条件 |
| 合规整改进度跟踪 | legal-zh-regulatory-gaps | 通过 | 无额外静态标记 |
| 监管合规事项管理 | legal-zh-regulatory-matter-workspace | 通过 | 无额外静态标记 |
| 法规与内部制度差异分析 | legal-zh-regulatory-policy-diff | 通过 | 联网资料 |
| 合规制度修订建议 | legal-zh-regulatory-policy-redraft | 通过 | 无额外静态标记 |
| 法规更新筛选 | legal-zh-regulatory-reg-feed-watcher | 通过 | 联网资料、定时运行条件 |
| 办案整理与文书起草 | qx-case-work | 通过 | 本地案件工具、本地材料工具 |
| 客户接待与跟进 | qx-client-reception | 通过 | 本地案件工具、本地材料工具 |
| 合同审查 | qx-contract-review | 通过 | 本地案件工具、本地材料工具 |
| 模拟法庭 | qx-mock-hearing | 通过 | 无额外静态标记 |
| 网页资料采集 | scrapling | 通过 | 浏览器连接/登录、联网资料 |
| Windows 桌面操作 | windows-desktop | 通过 | 浏览器连接/登录、联网资料、本地材料工具 |

## 复查方法与边界

运行 `node scripts/audit_skills.mjs --self-test` 核对引用解析边界；运行 `node scripts/audit_skills.mjs --out .local/skill-audit` 重新检查当前源库。可重复传入 `--compare 标签=工作区路径` 比较安装副本。它是开发诊断工具，没有加入用户运行门禁。

详细逐项结果、辅助脚本清单、非阻断引用和实际本地工具名称见 report.json。本轮未调用付费模型，未读取客户正文，未自动连接或发送外部消息；法律结论质量、真实账号权限及每种输入材料仍需对应业务验收。
