# T13 独立 live guard 审阅：当前 27 项及另批 CLI 2 项

状态：`OWN_BOUNDARIES_GREEN / REAL_LIVE_BLOCKED`。这是独立虚构数据工程检查，真实账户、许可、可信批准、真实适配器、数据地域及生产验收均未建立。本报告不替代根代理的全量测试、当前 84 场景验收或最终提交。

工作目录：`D:\Documents\ChatGPT\律所项目`。本审阅仅写入 `.audit-local/t13-live-review/` 和本报告，未修改业务、正式测试、配置、依赖、Vault、Git、账户或 OS 设置。前置准备报告 `docs/testing/T13-live-review.md` 和其 89 输入、26 个 `NOT_RUN` 检查轴的原封证保留。

## 当前实际执行

| 执行记录 | UTC 时间 | 实际结果 | 退出码 | 原生执行证明 |
|---|---|---|---:|---|
| `current-after-handoff-27` | 2026-10-03 10:27:29.479240–10:27:47.867578 | 27 PASS，0 failure/error/skip/warning；pytest 16.86s | 0 | 27 collected nodeids 与原生 JUnit 具名 testcase 集合完全相等 |
| `current-cli-2`，单独批次 | 2026-10-03 10:27:29.479752–10:27:31.676198 | 2 PASS，0 failure/error/skip/warning；pytest 1.18s | 0 | 2 collected nodeids 与原生 JUnit 集合完全相等 |

实际外层命令分别为：

```text
.venv/Scripts/python.exe -X utf8 -B .audit-local/t13-live-review/run_group.py current-after-handoff-27 .audit-local/t13-live-review/test_backend_independent.py .audit-local/t13-live-review/test_synthetic_current.py
.venv/Scripts/python.exe -X utf8 -B .audit-local/t13-live-review/run_group.py current-cli-2 .audit-local/t13-live-review/test_cli_current.py
```

每份同名 `.json` 保留实际内层 `pytest` 的完整 argv、UTC、退出码、完整 nodeid、JUnit/collection/log 的 SHA-256 和执行前后输入 SHA-256；同名 `.log`、`.xml`、`.collection.json` 为实际产物。内层加载服务器固定 `cn_contract.acceptance.pytest_evidence` 插件，以具名原生 JUnit 核对实际收集集合。

两个命令行子进程实际调用 `cn_contract.cli qcc-smoke --approval-id <独立虚构 UUID> --plan-id <独立虚构 UUID>`：缺少配置后端退出 **1**，输出 `BLOCKED_LIVE`；增加 `--force` 后解析器退出 **2**，拒绝未知参数。逐次 argv、UTC、stdout/stderr 和退出码保存在 `cli-observations/*.json`。CLI 的三个 0 计数是程序声明，结合当前缺后端调用路径解释，未冒称 OS 级网络捕获。这里没有设置账户、密钥或外部端点。

## 实际覆盖与边界

25 个后端用例使用独立本地虚构数据库，真实调用新服务入口、现有认证/成员/计划批准/预算/登记接口。有效工程计划批准仍得到真实入口 `BLOCKED_LIVE`；随机 UUID、客户端字符串/布尔值/空值、另一计划的有效批准、缺 Database/案件上下文均不能产生费用台账。

实际撤销会话、删除成员、将实际角色改为 assistant、禁用用户、撤销计划、替换价格为 7、撤销工具绑定、撤销预算，均在缺真实适配器的最终阻断前命中当前后端拒绝。恢复 fence 技术夹具得到 `BLOCKED_LIVE`/409；其占位 hash 和 `is_restore_evidence:false` 明确不代表实际归档恢复。伪会话及不存在的其他案件 UUID 也被后端拒绝；未把此用例称为“两个已存在案件的跨案件全组合验收”。上述拒绝均独立检查实际 ledger 行数为 0。

实际 Q0、两个分别合法批准的能力项、支持 `page` 参数的本机 SDK 两页计划，均得到 `QUERY_SCOPE_UNAPPROVED`。两页用例在实际发现与绑定后记录本机 SDK 计数，调用两个烟测入口后 HTTP/init/list/call 计数保持不变、tool call 为 0、ledger 为 0，证明该前置范围拒绝实际被消费。真实入口不接受 `force`、`transport`、`approved`、`region` 客户端扩权参数，四个独立用例得到 Python 参数拒绝。

新增两个服务器专用模拟正例分别为成功和超时。它们直接走 `run_synthetic_smoke` 与唯一 T08 Factory，没有注入 FakeTransport，也未暴露 CLI/HTTP 模拟开关。每个计划准确一个 item、一页、`max_calls=1`；重复同一计划得到字节语义相同的 receipt、同一持久 key、一个 ledger 和一个 receipt、台账 call 为 1。成功确认扣除 5 个模拟积分；超时 `sent_unknown`、`charged_credits=null`，5 个模拟积分继续占额、余额为批准额减 5。结果明确包含 `SYNTHETIC_ONLY`。完整 receipt、BudgetEntry、预算状态保存在 `synthetic-observations/*.json`。这里检查的是持久重放和模拟台账，不宣称真实价格或真实供应商请求结果。

26 个准备检查轴的最终范围如下；`PARTIAL` 不能计作整轴 PASS，也不能补齐现实批准：

| 检查轴 | 本审阅实际状态 | 尚未由本审阅执行或实现的部分 |
|---|---|---|
| L01 会话、L02 角色/成员、L03 案件边界 | PARTIAL：当前实际会话/成员/assistant/禁用用户、伪会话及无效其他案件 UUID 拒绝 | HTTP body 解析先后；四角色全组合；两个存在案件的全矩阵 NOT_RUN |
| L04 受保护批准、L05 现实缺口、L06 客户端扩权 | PARTIAL：工程计划批准绑定、UUID/类型/缺上下文/四扩权参数拒绝 | 现实账户/许可/地域/材料政策/期限/可信批准适配 NOT_IMPLEMENTED；不逐项伪造真实批准 |
| L07 模拟命名空间 | PARTIAL：真实入口 BLOCKED、两个正例标记 SYNTHETIC_ONLY | 对抗性标签更名、完整 production readiness 独立函数 probe 不在本角色范围 |
| L08 单 item、L09 一页 | 本轮固定前置范围用例 PASS | 校验后并发合法新版扩大范围的 handoff race 属作者 RED→GREEN，不冒称独立复现 |
| L10 绑定/价格、L11 材料/事实/版本 | PARTIAL：实际撤绑定/替换价格拒绝 | 端点/schema/单位/期限各变体及事实/原件/立场变体 NOT_RUN |
| L12 Factory、L13 预算、L14 数量 | PARTIAL：新入口实际调用唯一 Factory；撤预算及两个正例数量/占额检查 | Factory subclass 全攻击组、本轮并发上限、真实币种批准 NOT_RUN |
| L15 unknown/重放 | 固定模拟成功/超时持久重放用例 PASS | 未实施供应商级网络 packet 捕获；不得把台账 call 数冒称该捕获 |
| L16 并发/短事务、L17 发后撤权持久结算 | NOT_RUN（本轮独立动态 probe） | T08 历史结果及当前源码短事务推断不计本轮 PASS |
| L18 敏感输出 | NOT_RUN（本轮新 canary） | T12 历史 secret 扫描不能改记 T13 当前 PASS |
| L19 恢复 fence | PARTIAL：实际技术 fence 拒绝 | 本轮实际 restore NOT_RUN |
| L20 CLI 最小参数 | 两个固定阻断子进程 PASS，独立分母 2 | 没有配置真实后端或账户的正向真实执行 |
| L21 引用、L22 gold/mock GO、L24 hard NO_GO、L25 影子指标、L26 交接验收 | NOT_RUN（本角色独立功能检查） | 由另一审阅角色、根代理或现实人员验收；无真实律师 gold 或 GO |
| L23 当前输入 | 固定执行输入及共同源 hash 检查 PASS | 不宣称整个机器、隐式环境、OS/证书/网络策略或未来代码均稳定 |

## 历史及来源区分

第一次 `backend-first` 实际 **24 PASS/1 FAIL/0 error**，exit 1，11.43s（UTC 10:18:44.532190–10:18:57.067529）。失败来自本审阅夹具误读 `ToolBinding.unit_price`，未进入多项范围目标；这是辅助夹具失败，不能算业务 RED。改为使用现有 API 的价格快照/金额返回值后，同 25 项实际 PASS，exit 0，15.68s（UTC 10:19:47.477196–10:20:04.177114）。原日志未覆盖。

旧名 `final-backend-synthetic-27` 实际 27 PASS/exit 0/11.35s（UTC 10:23:08.430948–10:23:20.857324），其执行期间无漂移，但后来 `live/guards.py`、`queries/gateway.py` 两个执行输入变更，因此只保留为旧时点结果。

作者随后真实复现交接 race：校验单项后，同 ID 合法新版扩大为两页并另 Session 批准，旧路径先产生本机 SDK 两次 tool call 才拒绝；真实供应商调用仍为 0。作者记录的 **1 RED→同 case 加关联 32 GREEN→最终 25/31 GREEN** 均是作者证据，本审阅没有独立复现该 race。当前只读源码确认新入口把先前 plan hash 传给 gateway；gateway 在首个事务加载当前 plan 后、reserve 前比较该可选 hash。此源码确认不额外计作动态 PASS。

## 当前输入封证

作者 v2 `.audit-local/t13-author-final-v2/business.freeze.json`：SHA-256 `7e878014d0f6f66cc68f7a936e3af574da755a1d444d7585e1fc3f868eac3b66`，622 个固定输入。两批独立执行各记录 562 个实际范围输入，前后均 0 差异；与作者共有的 547 个路径 SHA-256 全部相同，当前重新读取作者 622 个输入也为 0 差异。

输入范围包括 src/static/templates、config、schema、sources/原始材料与锁声明的本机固定缓存、prompt/rules、skills、scripts、实际导入 helpers、pyproject/requirements 锁及当时存在的自有 Python probe/runner；排除执行生成的 `__pycache__`/pyc。新建收尾脚本只负责本次封证，不补写进已经结束的 pytest 输入集合。实际闭合命令为 `.venv/Scripts/python.exe -X utf8 -B -S .audit-local/t13-live-review/closeout.py`；实际退出码、UTC、分母、报告 SHA 和共同输入重新读取结果见 `.audit-local/t13-live-review/closeout-validation.json`，最终证据清单见同目录 `review-freeze.json`。旧准备和每轮失败/通过日志同时保留。

根代理的最终 full/current84、另一角色 readiness 审阅、现实批准、律师 gold、生产部署、OS/DNS/TLS/网络 capture、真实账号/密钥/付费/材料上传均不归本次 29 个独立 probe 的 PASS 分母。真实路径维持 BLOCKED；生产未完成。
