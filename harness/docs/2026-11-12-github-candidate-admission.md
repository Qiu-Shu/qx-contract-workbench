# 0.2.16 审核计划：GitHub 候选准入核验

日期：2026-11-12（Asia/Shanghai）。核验原审核列出的 **8 个候选仓库**，另将 Anthropic legal 作为 **1 个参考仓库**对照。结论是：**保留已适配的中国法四项方法、jsdiff 与现有 PDF.js；其余按开发参考、条件实验或暂缓处理，不整仓导入。** 本轮没有构建安装包、安装新依赖、下载模型、升级产品组件或修改生产代码。

实际工作树为 `C:/Users/Administrator/.codex/worktrees/audit-0216-fixes/律所项目`，分支 `codex/audit-0216-fixes`，核验起点 `5e01b065e4a1de9c63aa9d2c51118812e442ec86`。此前已经生成的候选包仅复用其解包资源作只读依赖；本轮没有生成新包，也未更新正式安装。

## 准入结论

“可保留”只指表内已核验的用途和版本，不等于整仓、全部依赖或法律效果已验收。“条件开发”表示可以继续实现缺口，尚不能作为可用产品功能交付。

| 仓库 | 固定范围与许可 | 判断 | 决定依据与剩余条件 |
| --- | --- | --- | --- |
| [CSlawyer1985/claude-for-legal-ZH](https://github.com/CSlawyer1985/claude-for-legal-ZH/tree/59f37f1c8851b8277e24f7a45f4e773bee97bab9/legal-research-cn) | `59f37f1c` 的四项研究方法；Apache-2.0 | **保留已适配四项** | 法源核验、类案对比、争点备忘录、讲座来源包的来源、许可、发现和升级保护复核通过；法律质量仍需律师验收，不导入整个仓库 |
| [kpdecker/jsdiff](https://github.com/kpdecker/jsdiff/tree/ed13aca03aa25735fafc0645d1185e7a1c68fd8c) | 9.0.0；BSD-3-Clause | **保留现有接入** | 已是直接依赖，用于只读文字差异；20 项合同/预览回归通过，不扩展成 Word 版式或法律影响判断 |
| [mozilla/pdf.js](https://github.com/mozilla/pdf.js/tree/1c8020a7d4e43668ac287a3ecf9a8dbea17e4c56) | 现有内嵌 6.3.289；Apache-2.0 | **复用现有组件** | 现有 Harness 预览器已包含它，实际 PDF 第 2 页回看通过；不重复安装。上游 6.5.438 只核对元数据，未验证升级；OCR 坐标叠加待验 |
| [promptfoo/promptfoo](https://github.com/promptfoo/promptfoo/tree/8569e72ed6cf7737082a6042be8d925e40f9739d) | 0.125.1；根许可 MIT | **仅开发，零外发准入未通过** | 已隔离于开发评测目录；禁用遥测后仍有一次 POST 意图。需默认拒绝外连或审计修复后重验；不进入产品运行包 |
| [anthropics/skills：skill-creator](https://github.com/anthropics/skills/tree/2c5958ecac7cee2b583967a2c4981d0f4a75c579/skills/skill-creator) | `2c5958ec` 指定子目录；Apache-2.0 | **可借鉴开发方法** | 可用基线、留出样例和独立比较方法；原脚本调用 Claude CLI，查看器含外部字体/CDN，当前不直接嵌入产品 |
| [restic/restic](https://github.com/restic/restic/releases/tag/v0.19.1) | 0.19.1；BSD-2-Clause | **可以进入受控接入开发** | 本轮 24/24 实验检查通过，4 文件、50 行恢复一致；多库/文件统一停写、PG 数据、私密映射、权限及换机凭据恢复尚未接入 |
| [data-privacy-stack/presidio](https://github.com/data-privacy-stack/presidio/releases/tag/2.2.366) | 2.2.366 + 中文模型 3.8.0；本次代码/模型 MIT | **暂不替换；仅补充识敏试点** | 新样本当前规则覆盖 6/11 处实体，候选 4/11，新增 3、退步 5；直接替换会丢失已有覆盖。组合、误遮和可逆映射仍待实测 |
| [docling-project/docling](https://github.com/docling-project/docling/releases/tag/v2.150.0) | 2.150.0；软件 MIT，模型另审 | **暂不加入默认 DOCX 链** | 新增两份纵向合并/嵌套表样本结构新增 0/2、退步 0/2，连同前次共四份仍无新增结构收益；PDF/OCR 管线未运行，留待单独验证 |
| [anthropics/knowledge-work-plugins/legal](https://github.com/anthropics/knowledge-work-plugins/tree/877a617b435ee2edfb002d9a3703c0a1a03aa1ba/legal)（参考项） | 对照 `877a617b`；既有 G01 仍锁 `8444efcd`；Apache-2.0 | **仅保留方法参考** | 合同审查核心文件与既有 pin 相同；不直接导入带外部连接器与其他法域假设的完整插件 |

以上许可结论针对读到的固定文件。没有把根 LICENSE 推广为整个依赖树、模型权重、训练语料或最终发行物的许可审查；正式分发仍需保留实际使用范围的版权、许可和修改告知。

## 本轮改变判断的证据

**PDF.js 已经存在。** 顶层锁文件没有独立条目，但 `@deepseek-ai/dsh-client-ui-sidebar-documentpreview@0.2.2-alpha.2` 的发行 bundle 实际内联 PDF.js 6.3.289，7,108,803 字节；版本标记、完整 Apache 文本及页面/文字层节点均已核对。需要复用并验证现有组件，不应再新增第二套依赖。[详细来源与实测](research/2026-11-12-candidates-diff-pdf.md)

**Promptfoo 的禁用变量不足以保证零外发。** 固定版本源码与本机分发一致：`record()` 在禁用遥测后仍会调用发送路径。只读探针以合成身份和内存记录器替代网络，两次调用捕获一次 POST 意图，真实网络调用为 0。它证明了控制流缺口，不能证明历史请求实际发送成功。历史 24 案仍是工作流证据，本轮仅复核其摘要、没有重跑完整入口；已更正旧文档把“脚本模型离线”等同于“进程零外连”的表述。[详细复现与条件](research/2026-11-12-candidates-methods-eval.md)

**备份必须覆盖真实存储结构。** 本项目同时有多个 SQLite、附件、原件、可逆脱敏映射、宿主状态与 pg0/PostgreSQL 增强记忆。restic 成功恢复单个合成 SQLite 不能替代全应用一致快照；活动 PG 不能按 SQLite 处理，DPAPI 文件也不能直接代表换机可恢复凭据。[存储边界与接入顺序](research/2026-11-12-candidate-restic-admission.md)

**识敏有增益也有退步，现有规则本身亦有缺口。** Presidio 增加了三个无标签人名的完整识别，但漏掉五处既有覆盖。当前规则还把负例“学校和医院”遮掉了，实际影响五个非实体字符；本轮记录问题，尚未修复。跨度并集可达 9/11 只是现有结果的推算，未实现或验收产品组合。两边的金额、日期和比例控制均保留，小样本不能代表业务总体准确率。[样本、负例及性能证据](research/2026-11-12-candidates-privacy-docling.md)

## 验证范围与实际结果

核验先比较来源/固定版本、许可范围、现有功能重叠、接入与数据边界，再运行适合本机已有环境的合成实验。上游说明是资料，不作为安装或扩大权限的指令。没有用星标数或演示成功替代项目准入。

| 本轮实际执行 | 结果 | 能证明的范围 |
| --- | --- | --- |
| 中国法方法、工作流断言、模拟预算目标测试 | **26 通过，0 跳过，exit 0** | 方法发现/来源/升级保护、断言与模拟预算；未调用真实模型 |
| 合同对比与预览目标测试 | **20 通过，0 跳过，exit 0** | 文字比较、来源与授权、预算、原件保护和并发边界 |
| 现有 Harness 浏览器检查 | **exit 0，页面错误 0** | 文本/DOCX/PDF 第 2 页、旧引用拒绝、草稿保留及三个宽度；现有依赖只读复用 |
| jsdiff / PDF.js 来源探针 | **exit 0** | 实际版本、许可与摘要；不冒充渲染或全面安全审计 |
| Promptfoo 遥测内存探针 | **exit 0，缺口复现** | 2 次 record → 1 次请求意图，0 次真实网络；退出 0 不代表零外发准入通过 |
| restic 隔离备份/恢复 | **24/24，exit 0** | 一个 SQLite、静态文件、错误口令、部分备份与路径/损坏拒绝；非全产品恢复 |
| 现有知识导入导出目标测试 | **15 通过，exit 0** | 原有知识迁移保护；与 restic 实验分别计数 |
| 新增 Presidio / Docling 对照 | **3 个实验进程 exit 0；2 个环境依赖检查 exit 0** | 12 文本/11 实体、2 DOCX；实验顺利完成，候选质量按上文判断 |
| 历史 24 案证据复核 | **14 个执行源码摘要一致** | 旧报告 24/24、scripted、法律质量未评；本轮没有重跑它 |

完整命令、退出码、固定提交和逐项边界见四份专项报告。机器清单在[准入与证据摘要](checks/github-candidate-admission-20261112.json)。新增大文件与原始日志在 `D:/CodexChecks/AI-Shixiong-candidate-admission-20261112`；已提交范围仅为报告、合成样本和验证脚本。没有运行全仓回归，因为生产源码与依赖锁没有变动；上述目标验证按各候选的实际影响执行。

Presidio 本次峰值工作集约 470 MB；Docling DOCX 约 158 MB。它们是单轮实测，不是稳定资源上限。Docling PDF/OCR 所需模型没有下载，不能用 DOCX 成本或结果推断该管线。也未完成真实材料、律师质量、跨机恢复、完整漏洞/依赖许可或最终发行验收。

## 后续工作顺序（尚未实施）

1. 先修复开发评测的外连控制：默认拒绝未授权请求，覆盖遥测、更新、远程生成、分享和子进程；完成独立拦截验收后再重跑 24 案。
2. restic 先做数据清单与统一停写，再做完整快照登记与新目录恢复；分别解决 PostgreSQL、可逆映射、访问权限和换机重新授权。
3. 对当前识敏规则的通用词误遮建立失败用例并修复，再独立评估 Presidio 补充识别，不能先替换后补测。
4. Docling 只对明确存在现有短板的 PDF/跨页/OCR 管线继续试验，先锁模型、许可与资源预算；没有证据前维持当前解析器。

用户要求“先不用构建安装包”继续有效；上列是准入后续条件，不是本轮已完成的实现，也不自动启动构建或发布。
