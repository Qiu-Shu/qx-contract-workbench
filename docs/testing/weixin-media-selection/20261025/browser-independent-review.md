# D2g5f 浏览器验收脚本独立静态审阅

审阅对象：`scripts/validate_task_media_selection_browser.py`。审阅者未编写该脚本、前端产品或作者 Node 测试；自编 HTTP 测试不纳入独立自审声明。读取代码与所调用的原件/备份检查实现，**本审阅者未执行此浏览器脚本**，浏览器实际运行结果由 root 单独记录。不得把此静态核对称为独立浏览器运行 PASS。

首次读取脚本 SHA256：`dee43897e525236f1a71991faae02b0093a69fa06f5f0819ee7a4db4b4e2f03c`；最终修订及实际记录复核见末节。

## 与切片目标匹配的内容

- 使用 `initialize_workspace` 建立全新 output 下的独立 native 工作区；同一套真实账号/代际/完整收件/固定目标分发服务产生无 attachment_id 的 DOCX/PDF pending，未手写成功 resolution 或假模型回执。
- 后续通过 loopback FastAPI 和真实 Playwright Chromium 页面完成本机文件上传、同 CID 解析、原生 select 键盘选择及按钮 Enter；没有调用微信 transport、下载或解密。
- 源数据已按 root 最新修订使用 `select_fixture('sales')` 的默认登记 DOCX，加现有 `task-pdf-v1/native-sales.pdf`；不再依赖 app 配置前临时设置随后被覆盖的合成 hash。产品数据政策未放宽。
- 页面上传前及关联前断言空选择/按钮禁用，后续只有两个 options、关联 label 与 select 一一对应；主合同 blocker 解除后冻结按钮可用，但不点击冻结，因此仍收集态。
- 对每个关联后的 TaskInbox 原始表按全行及顺序与最初 snapshot 比较，且原 media 的 attachment_id 仍 None；数据库真实 resolution 只一条并与用户实际选中的附件 ID/media ID 一致。
- 终态真实查询 `task_executions`、`assistant_runs`、`assistant_model_attempts`、`review_runs` 均为 0，resolution 恰 2。源 fixture 文件的 SHA 前后相等；这验证 repository 中的合成输入源文件未改变。
- 浏览器网络仅允许本次随机 loopback base，其余请求中止并计入报告；pageerror 与 external_requests 任何非空均失败。1280/360 视口断言无页面横向溢出，记录键盘焦点、字体及两张截图。此项仍需 root 实际查看截图，脚本本身不自动证明视觉质量。

## 历史验收证据缺口（已由 root 补强）

### [P2，已关闭] “回执丢失后只 GET”报告字段未直接观察精确查询

当前 `lose_ack` 只把 PATCH 记入 `writes`；PDF 首次 PATCH 用 `route.fetch()` 证实服务端 HTTP 200，再 abort 浏览器 ACK，这个故障注入有效。之后 `writes==['PATCH']` 能证明没有第二次 PATCH。但 `lost_ack_query_only=lost[0]` 只是“注入过 ACK 丢失”的标记；脚本没有把 GET 记入 trace，也没有断言点击查询发出了 `/api/task-drafts/{draft_id}` 的精确 GET。因此若未来 UI 仅刷新列表而不精确查询，现有浏览器断言仍可能通过。

建议在同一目标 route 记录所有 method，DOCX 断言 `['PATCH']`，PDF 在点击查询后断言 `['PATCH','GET']`；将该实际观察与 patch_count 一并写报告，然后才标 query_only。现有 Node 和独立探针已覆盖该产品逻辑，但不能替代本浏览器报告声称的实际观测。

## 证据口径补充

`backup._file_references(db)`（`src/cn_contract/ops/backup.py:163`）核数据库来源/引用/摘要关系，返回受保护文件清单；它不读取物理文件字节。当前脚本确实核了 repository 样本 SHA 前后相等，不能把这一调用扩写成“关联后保护区 original.bin 再次逐字节核验”。若报告要声称后者，增加关联前后通过原件 HTTP 读回或 `attachment_files.read_checked` 与上传 bytes 比对即可；否则保留当前较窄表述。该增强是范围说明，不是另一个产品漏洞。

当前结论：产品越权/模型调用问题未发现；浏览器报告的精确 GET 证据口径有 1 项待补强。真实微信、真实合同、模型、安装版、原生崩溃及 WIN-PATH-02 均未在本审阅执行。

## 最终脚本与实际记录只读复核

root 最终脚本 SHA256 为 `582ae180e9f309bf65fb612a3e251c1877a1959ca7f617b42aba392d17101140`。新 `lose_ack` 对精确目标 route 记录所有 method，强制 DOCX 为 `['PATCH']`、PDF 为 `['PATCH','GET']`；`lost_ack_query_only` 依据实际 trace 而非仅故障注入标记。关联前后原件 HTTP GET 均要求 200 且 response body 等于登记源 bytes，补齐物理原件读回依据。

已回读 root 的 `browser-04.json`、`browser-04/report.json` 与最终源码，核对：

- root 实际 argv 运行本最终脚本，UTC `2026-10-25T13:30:28.192598+00:00` 至 `13:30:34.719509+00:00`，exit 0、墙钟 6.532 秒；`source_before == source_after`，本脚本和产品 JS 摘要吻合当前最终快照。
- report 真实记录 DOCX target_methods 为 PATCH，PDF 为 PATCH→GET，两者 patch_count 均 1；PDF lost_ack_query_only 为 true。
- 两类 `original_bytes_preserved`、`original_event_preserved` 均 true；真实表计数代际/分发/人工 resolution 各 2，task execution、assistant run、model attempt、review run 四表为 0；外部请求与 pageerror 为空。
- 1280/360 的 scrollWidth 分别为 1280/360，焦点均在关联按钮。审阅者只回读数值，未重复打开 Chromium 或独立视觉查看截图。

report SHA256：`ff7636564d1e82d131648cfb1cb756e4ff87cfc2d366771d65a6497ca65ce654`。因此历史 `BROWSER-EXACT-GET-OBSERVATION` 关闭；**最终浏览器脚本审阅产品问题 0、验收证据未解决项 0**。此结论是独立静态审阅及 root 实际记录核对，不改称审阅者独立执行浏览器。

## 恢复关联组失败的范围区分

另行只读核对 root `final-recovery.log/json/xml`：实际是 **76 个用例，75 PASS、1 FAIL，0 error、0 skipped，exit 1**，不能记为恢复组全绿。失败用例为 `test_restore_blocks_each_pending_execution_and_all_task_writes[awaiting_facts]`；调用在 `tests/integration/test_task_drafts_migration.py:214`，异常位于 `src/cn_contract/ops/workspace_backup.py:380` 的 staging workspace→新 UUID 目录发布 rename，操作系统返回 WinError 5。保持 WIN-PATH-02 OPEN，并保留失败原始记录是恰当处理。

相对本轮基线 `49e7b55` 的 `git diff --name-only 49e7b55 -- src tests/integration/test_task_drafts_migration.py` 只列 `src/cn_contract/web/static/assistant-tasks.mjs`；Python 恢复实现与迁移测试均未改。迁移模块的 AST imports 均为 Python、SQLAlchemy、pytest 与后端/测试 helpers，失败函数调用备份/恢复/数据库/授权/任务服务，没有 JS 引用、Node、浏览器或此 JS 的执行；它在 restore 返回前的文件 rename 即失败。两份相关 Python 文件的 before/after SHA 在该组中一致，且当前仍吻合。

```text
src/cn_contract/ops/workspace_backup.py 0cebe362b20104388e4ec1c084d5fdae82bbcbd18a42dd23efc0160c82afc1ad
tests/integration/test_task_drafts_migration.py 651ab86a8ada3a68ae5ad4d58dec3a6d322980e43659a27d3b740f900bf2ddf4
final-recovery.log a980172da1aa3b4546f742ea86f501a75481e5f46715184a2393ecef33948b90
final-recovery.xml ebd504ad84f4715d837ebfc77f297c63fd81eb6c1abac0b30b4648488811d336
```

这支持将本片前端行为验收与既有恢复发布 WinError 5 分开报告；**不证明 WinError 5 的具体句柄/系统根因已诊断，也不证明整个恢复能力已可靠**。本审阅者未修改 guard、重跑覆盖失败或关闭该故障。恢复组执行时浏览器脚本尚为前一摘要，组内仍 before=after；最终 browser-04 后续单独运行并冻结，不能把两个不同脚本快照误报为全组同一个全输入快照。
