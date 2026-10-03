# 群兴合同审查工作台实施计划

> For agentic workers: use superpowers:executing-plans or subagent-driven-development task by task; user has explicitly authorized starting T00 in this repository. Independent read-only source audits may run concurrently.

**Goal:** 从空仓库建立可追溯的内部合同审查工具，先虚构数据闭环，再受控外查和修订；真实试点始终需要独立批准。

**Architecture:** 沿用 v2.0 任务接口和默认目录，单一 Python 工作流；来源锁与运行数据分离。案件权限、版本、预算和审批由服务端程序执行，生产门禁无法由 mock 绕过。

**Tech Stack:** Python 3.12、Pydantic 2、FastAPI、SQLAlchemy 2、SQLite、Jinja2、pytest；依赖从实际解析结果锁定。

**Spec:** `C:/Users/Administrator/Desktop/群兴律所_合同审查工作台_Codex实施规格与任务书_v2.0.md`；本计划不扩大用户授权。

## 全局约束

- QCC 关闭、mock 默认；20积分、6次、每工具1页、付费自动重试0次。
- 文件50MiB、20文件、每案200MiB、每文件200页；zip合同上传和docm关闭。
- CN-mainland，sales/service/lease/nda；科技专项未批准关闭；所有18维均必须明确状态。
- 原包A、真实客户合同和密钥不进入Git；不自动购买、对外发送或上传真实资料。
- source_commit_lock_required=true；任何 missing/unknown 保留真实阻断状态。

## Review Focus

- 改名、拼接后限制来源进入运行目录也须阻断（T00）。
- 同哈希跨案先授权，不因缓存共享绕过权限（T02）。
- 未读部件与扫描页显式unsupported，禁止完整读取声明（T03）。
- mock、schema失败、未批准法源不能签发正式意见（T05/T06/T09）。
- 请求发送后超时保持未知扣费预留，不重试；补丁必须匹配批准版本（T08/T09）。

## 任务与验证

每项以规格第13节的输入、接口和验收断言为准，顺序为失败测试 → 确认失败 → 最小实现 → 目标测试及受影响回归 → TASK_STATUS实测记录。

- [x] T00：`scripts/verify_sources.py` 的 `verify_manifest(path, mode)`；13项锁、许可证据、复用记录、ADR；28项测试通过；实际发布保持依赖/批准阻断，记录于TASK_STATUS。
- [x] T01：domain/config/schema/CLI；四类、18项、extra禁止、默认配置哈希；158项实际通过，独立审阅修正四个问题并通过；生产批准仍阻断。
- [x] T02：SQLAlchemy案件/权限/版本/审计；42目标/200全套实际通过；独立事务及状态缓存缺陷已修正复验；正式签发仍阻断。
- [x] T03：安全上传、DOCX部件与PDF逐页、锚点；69目标/269全套及独立14攻击探针实际通过。OCR/全面视觉等价/解码沙箱未部署；生产门禁仍阻断。
- [x] T04：事实候选与人工确认、Decimal计算、客户立场与主体消歧；76目标/345全套及31独立攻击探针实际通过，存储解析污染P2关闭；真实模型/外部收据/签发仍阻断。
- [x] T05：来源原文、法域时点、draft/approved规则和客户偏好隔离；431全套/86目标/45独立探针通过，生产规则仍待律师批准。
- [x] T06：四份独立虚构DOCX实际CLI通过；18维、缺件、证据、注入、JSON单次修复；511全套/80目标/77独立探针；QCC调用0，法律规则仍待批准。
- [x] T07：固定SDK本机MCP模拟发现/批准绑定/调用，46目标/557全套/66独立探针通过；真实QCC、价格、许可与生产仍BLOCKED_LIVE。
- [ ] T08：原子预算和幂等，未知扣费恢复；缺许可或账户为BLOCKED_LIVE。
- [ ] T09：三类报告、原生正文修订候选、精确位置/版本/签发；复杂对象manual_required。
- [ ] T10：可操作内部页面、API、任务状态和导出。
- [ ] T11：84项分别映射实际用例和金标准，未支持不得用安全阻断PASS冒充能力PASS。
- [ ] T12：部署限制、出站、秘密检查、真实备份恢复和manifest；批准环境待定。
- [ ] T13：真实联调guards和GO/NO-GO；无实际许可、账单、律师金标准只能BLOCKED_LIVE。

本计划按已明确授权执行，不另设重复审批。每阶段实际产物及待办记入 `docs/TASK_STATUS.md`；不把任务清单当成实现。
