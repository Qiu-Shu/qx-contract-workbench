# D2b 合成账号和原子收件实测（2026-10-24）

已按[实施合同](../../../plans/2026-10-24-weixin-inbox-d2b.md)实现本机 synthetic-only 服务。真实微信未接通；无新 HTTP/IPC/UI、依赖或 schema，沿用 D2a 四表和 D1 逐条解码。

## 源码已实现

`domain.py` 追加 4 个输入 DTO，不接受调用方 owner/workspace/next revision 或执行能力；服务重新校验 DTO，不能靠 model_copy 绕过。`weixin_inbox/accounts.py` 提供创建/读取账号、绑定/读取精确 peer、撤销账号/peer 六个 API；身份取数据库真实 principal，角色、会话有效期、owner/workspace、任务绑定及 scope 均由后端核验。bot/peer 字符串只表示合成命名空间，不代表微信身份认证。

映射重放只接受同账号/peer/task binding/完整 scope；不得隐式重绑或撤销后复活。首次撤权时间、actor、reason 保留，相同原因幂等、不同原因冲突。当前分类检查会话归档、完整 scope 修订、案件 membership、接待 owner/转案和 projection；案件自身归档也阻断新增收件，未改变既有只读授权。历史映射只读 API 可向同一账号 owner 返回固定 scope ID 元数据，包含案件 ID，不含案件标题、客户、文字或附件。accepted 回执内容则始终重新检查当前映射权限；失效后拒绝读取与重放。

`weixin_inbox/ingress.py:record_synthetic_poll` 独立持有 Session，经 Database 既有 begin listener 在身份读取前取得 BEGIN IMMEDIATE。先构造完整有序 receipt/descriptors，再插入所有行，最后以 expected revision/opaque cursor 做 CAS；同一事务 commit 成功后才返回。分类 guard 只读，不调用会 rollback/commit 的 security.deny。`find_poll_receipt` 以账号/request_id 找回固定回执，不推进游标；同请求且请求摘要/原始响应 SHA 相同可重放，内容变化冲突；current auth/fence 不被幂等短路绕过。

单账号 poll 可含多个精确 peer。坏 envelope 整批拒绝；坏消息保留 blocked 摘要，不丢弃有效邻居。未知 peer、错误 recipient、过期/撤销/无权映射有固定原因；同来源同 hash 指向原始结果，已接纳为 duplicate、已阻断仍 previously_blocked，内容变化为 event_conflict；同 poll 更早记录也适用。空 poll 留回执并增加本地 revision，opaque cursor 可不变。仅保存安全文字和 pending DOCX/PDF，不保存完整 wire、AES/CDN/context/session 能力数据，不调用任务分发、文件下载、模型或对外发送。

运行 SQLite 未加密；请求/响应/source 原文丢弃，其 SHA 不能证明远端真实性。此 API 是合成持久收件，尚无真实可信绑定、轮询或 transport。恢复副本允许当前身份下找回可读历史，但 record 即使只是同请求重放也被 fence 拒绝。

## 本轮实际验证

原始日志、XML、退出码和摘要位于本机 `.local/weixin-ingress-20261024/`。最终 **9 个文件、444 个不同 Python 用例通过**，0 failures/errors/skips；有 1 个有意伪造 model_copy 输入引起的 Pydantic serialization warning。不是全仓或生产验收。

| 实际命令 | 原始回执 | 结果 |
| --- | --- | --- |
| `.venv/Scripts/python.exe -B -X utf8 -m pytest tests/unit/test_weixin_ingress_inputs.py tests/unit/test_domain.py tests/integration/test_weixin_accounts.py tests/integration/test_weixin_inbox_ingress.py tests/integration/test_weixin_ingress_atomic.py -q --tb=short --junitxml=.local/weixin-ingress-20261024/final-service.xml` | `final-service.xml`、`.txt`、`.exit.json` | exit 0；212 passed（20 输入＋111 既有领域＋32 账号＋41 收件＋8 原子验收），1 warning，65.72s |
| `.venv/Scripts/python.exe -m pytest tests/unit/test_weixin_offline_protocol.py tests/unit/test_weixin_inbox_dto.py tests/integration/test_weixin_offline.py tests/integration/test_weixin_inbox_integrity.py -q --junitxml=.local/weixin-ingress-20261024/related.xml` | `related.xml`、`.log`、`.exit` | exit 0；232 passed，30.07s |

两份 XML 按 classname/name 去重无重叠。源与 XML SHA 留在 `verification-summary.json`。账号归档补丁后执行的最终 212 项包含全部新 API 和归档路径；232 项验证未改动的 D1/D2a 关联行为。

8 项原子验收使用**实际 public 服务**创建账号和映射，不通过 SQL 夹具冒充运行收件：descriptor 插入、checkpoint 更新、commit 前三个故障均回滚全部结果与游标；实际 commit 后故意丢失回执可查询找回，重放不增行；两个独立 Session 并发相同请求回读同一结果，不同请求同 revision 仅一条成功；新 Python 进程可找回已提交完整回执；服务生成历史经真实 qxbak 往返逐表相等、恢复拒绝 record 重放、源全部文件字节不变。TaskInbox/draft/execution/assistant run 始终 0。

四开发门均以 `.venv/Scripts/python.exe -B -X utf8` 执行且 exit 0：`-m cn_contract.cli schema --check`、`scripts/verify_defaults.py`、`scripts/verify_sources.py --mode development`、`scripts/verify_runtime_dependencies.py --mode development`。来源保留 13 项 NOT_PRODUCTION_APPROVED；依赖 55 runtime＋1 build、native_build_verified=false、network_calls=0。

## RED、修复和独立复核

有效行为 RED：4 输入 DTO 缺失 20 failed/0 errors；accounts 和 ingress 各在测试体确认缺模块、1 failed；peer 先查映射后鉴权问题 1 failed 后修复；直接案件/接待转案/projection 三路径归档 3 failed 后补 guard。收件首轮实现发现 `+00:00` 与 DTO JSON `Z` 的 receipt 摘要不一致，1 failed 后改为规范 UTC 表达。最终回归均覆盖修复。

辅助测试失败如实保留：输入 fixture 初误用 personal/零绑定修订导致 collection error；初次 ingress 长 bytes 参数 ID 造成路径 setup errors；账号首轮 3 个失败为原生 fixture 重开后未装配既有 storage flags，仅修 fixture。根代理原子测试开发期间服务已落盘，文件名 `atomic-red.xml` 实际是 8 passed 的首轮验收，**不作为失败测试证据**。所有中间通过数不累计进 444。

独立 reviewer 在冻结源码上确认无遗留可证实缺陷：3 条归档用例再次独立通过；另用临时合成工作区核对畸形响应/242 项字段变体、回调不执行、权限撤销与收件事务串行、撤权后查询及重放不能读 accepted 文字。这些探针与正式 444 项分开计数，未独立重跑根代理全部原子验收。

WorkBuddy 任务 `wb-bg-543655acb200` 已完成，桥接核实 actual `kimi-k3-2`。它基于计划/旧源码提出 5 类未实测反例，新模块读取时尚未存在，不能称最终实现审查。实际 pure guard、当前 ACL 重放、跨 owner、同 poll 重复/blocked 不复活及 qxbak fence 均以本轮测试核对；不采纳其与契约相反的“恢复 record 可重放”推断，恢复只允许 find。D1 整批适配器不用于 D2b 混合 poll，仅复用逐条解码；exact schema 识别不能把含未知额外表的库误识别为旧版。

| 最终产品 | SHA256 |
| --- | --- |
| `src/cn_contract/domain.py` | `20d56624ea50dc9f52a51113b8d87d57c0f6b427961dcd06735db3c4b1718876` |
| `src/cn_contract/weixin_inbox/accounts.py` | `6aa6f5d18b9091dc6b66c33e5c018955471b09006f09d6081dcfa94419a347b9` |
| `src/cn_contract/weixin_inbox/ingress.py` | `2885d17d429fc5c3e5865c2f29acf320f8b755433ccd7e07724641c07c320009` |

## 尚未实现与 NOT_RUN

D2c：从 accepted_pending_dispatch 安全分发至共享 TaskDraft，持久分发回执/恢复、再次核验当前权限和版本；本片不自动冻结或审查。过期映射的显式刷新/重新绑定仍待设计，当前明确阻断，不能靠重放隐式更新。

NOT_RUN：真实微信认证/transport/轮询、机器人安装、真实合同、媒体下载解密、Outbox/发送、产品真实模型/付费、E 原生有限期许可、新安装包、全仓/Node/浏览器回归。安装版仍 0.4.1。既有原生长进程崩溃和 WIN-PATH-02 保持开放。
