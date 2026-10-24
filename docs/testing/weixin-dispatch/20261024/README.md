# D2c 合成收件至共享任务分发实测（2026-10-24）

已按[实施合同](../../../plans/2026-10-24-weixin-dispatch-d2c.md)实现本机合成分发。真实微信尚未接通；不增加 transport、HTTP/IPC/UI、依赖或模型调用。

## 源码与当前行为

追加第15版 `weixin-dispatch-v1`：一张13字段、不可变的 `weixin_dispatch_receipts` 表，唯一关联 accepted 原始 descriptor 与 TaskInbox event；`domain.py` 仅追加 `WeixinDispatchReceipt`。回执固定来源、payload hash、actor、binding、整数游标及UTC时间，不固定可变化的 task_id/草稿状态，也不代表意见已生成。

`weixin_inbox/dispatch.py` 的 `dispatch_synthetic_descriptor` 从持久 descriptor 重建内容和目标，在当前数据库 principal、账号owner/workspace、映射scope/ACL/撤权/归档及restore fence核验后，复用同一Session调用现有 `receive_batch`，再保存固定回执；BEGIN IMMEDIATE 持有至 commit，成功后才返回。按每mapping的 poll revision/ordinal 顺序分发 accepted 前缀；blocked/duplicate不能分发，其他peer不相互阻塞。已有同source TaskInbox事件而无分发回执时拒绝，不能收养桌面事件为微信分发。

`find_dispatch_receipt` 可查询已提交结果；重放回读固定回执，不再调用 `receive_batch` 或推进游标，仍需当前权限。恢复副本仅允许当前权限下查询，写入口包括同请求重放也拒绝。旧拒绝路径可能单独提交授权拒绝审计，不宣称绝对零数据库写入；业务事件、草稿、游标、分发回执不得半提交。

实际复用共享 TaskDraft：指令/附件任一顺序先收集；pending DOCX/PDF不具原件/解析能力，不能冻结；未知引用和多草稿歧义保留待分配事件；已冻结来源的合法回复进入补充草稿并继承原指令；明确律师文字暂停/取消/继续沿用既有规则，不启动模型。现有桌面任务读取服务可读取同一TaskDraft，本轮未跑浏览器或更新安装版。

`dispatch_integrity.py` 在full qxbak重核固定回执、原poll/accepted descriptor、精确账号/peer/mapping/owner/TaskInbox来源、canonical JSON/SHA、accepted前缀、历史撤权和游标区间。允许桌面批次造成游标间隙、后续scope变化及动态分配；历史合法不等于当前授权。旧14版native/non-native的28组原始及规范化指纹不改，旧inbox DDL SHA仍为 `e194dc41c69c1b1e0103f8c17557715dbdc46ef95a4771427e07d1c10fcacdf0`。bootstrap/迁移/native升级/备份及旧六类与base微信完整性gate均接续，两处fence均增加 `weixin_dispatch_enabled=false`。

## 本轮实际验证

本机原始证据在 `.local/weixin-dispatch-20261024/`，汇总为 `verification-summary.json`。按classname/name去重，**19个模块、679个不同Python用例最终均有通过证据**；不是单次全仓全绿。`final-runtime-clock` 与 `related-final` 各出现1个同一有意伪造model_copy输入的序列化warning，未隐瞒或计作失败。

| 实际命令目标（统一 `-m pytest -q`） | 回执 | 实际结果 |
| --- | --- | --- |
| 新dispatch DTO、dispatch服务、dispatch原子验收、既有Weixin accounts/ingress/ingress_atomic（6文件） | `final-runtime-clock.xml/.txt/.exit.json` | `.venv/Scripts/python.exe -B -X utf8`；exit0，120 passed，1 warning，89.21s |
| 既有 `test_task_drafts.py test_task_draft_routes.py test_weixin_accounts.py test_weixin_inbox_ingress.py test_weixin_ingress_atomic.py`、`tests/unit/test_domain.py` | `related-final.xml/.txt/.exit.json` | 同上前缀；exit0，236 passed，1 warning，109.95s；其中accounts/ingress/atomic的81项由时钟修复后的120项再次验证，其余155项源码未变 |
| `tests/integration/test_weixin_dispatch_integrity.py` | `integrity-clock-final.xml` | `.venv/Scripts/python.exe`；exit0，73 passed，29.78s |
| `tests/integration/test_weixin_dispatch_schema.py --basetemp=.local/weixin-dispatch-20261024/storage-tmp` | `storage-schema-green.xml/.log/.exit` | 同上前缀；exit0，84 passed，51.87s |
| 旧微信完整性/备份、model wire、profile ledger与8类旧任务来源损坏，详见下段 | `storage-gates-green.xml/.log/.exit` | 同上前缀；exit0，88 passed，74.43s |
| `tests/integration/test_weixin_inbox_schema.py --basetemp=.local/weixin-dispatch-20261024/storage-inbox-final-tmp` | `storage-inbox-final.xml/.log/.exit` | 同上前缀；exit0，91 passed，43.78s |
| 旧inbox schema/native workspace/catalog三文件中，仅选择原生升级58与catalog10的通过身份 | `storage-successor-green.xml/.log/.exit` | **整个命令exit1：154 passed/5 failed**，157.26s；选中两模块68项全过，5处旧inbox断言另由上行整文件91复验替代，不将159称全绿 |

运行时首行完整目标为 `tests/unit/test_weixin_dispatch_dto.py tests/integration/test_weixin_dispatch.py tests/integration/test_weixin_dispatch_atomic.py tests/integration/test_weixin_accounts.py tests/integration/test_weixin_inbox_ingress.py tests/integration/test_weixin_ingress_atomic.py`；根代理命令另带 `--tb=short --junitxml=.local/weixin-dispatch-20261024/<回执>.xml`。其余storage精确目标保存在本机 `storage-notes.md`：`test_weixin_inbox_integrity.py`、`test_weixin_inbox_backup.py`、`test_assistant_model_backup.py::test_native_references_reject_changed_model_wire_digest`、`test_assistant_profile_model_integrity.py::{test_profile_events_without_a_model_ledger_are_never_empty,test_empty_successor_runs_all_archive_validators}`、`test_task_drafts_migration.py::test_task_source_corruption_rejects_backup_and_authenticated_restore`，均在 `tests/integration/`。跨行重复用例只计一次，7份XML哈希与源码摘要已回读。

运行验收实际使用public D2b账号/映射/poll和dispatcher；覆盖两个顺序、当前权限/撤权/归档/scope、顺序/来源碰撞、两种显式控制后恢复、歧义/未知引用、受控本地DOCX解析与人工材料关联后冻结、合法回复补充。真实SQL插入/commit前故障全部业务回滚；commit后丢失ACK可find；双Session只收件一次；新Python进程能读取固定回执。两代真实qxbak逐行保留TaskInbox/草稿/关联/binding及dispatch回执的5表快照，恢复拒绝重发；该备份样例中task executions/assistant runs/review runs均0。两类加密认证有效但内部来源损坏的归档拒绝发布，源全部文件字节保持。

四开发门在最终时钟修复后均以 `.venv/Scripts/python.exe -B -X utf8` 运行且exit0：`-m cn_contract.cli schema --check`、`scripts/verify_defaults.py`、`scripts/verify_sources.py --mode development`、`scripts/verify_runtime_dependencies.py --mode development`。保留13项NOT_PRODUCTION_APPROVED，依赖55 runtime＋1 build、native_build_verified=false、network_calls=0。

## 失败、时钟修复和独立复核

有效RED包括DTO缺失12 failed、运行分发缺失1 failed、新schema缺失1 failed、后继版base微信漏校验29 failed、旧model gate拒新版本1 failed、历史校验缺规则35 failed/33 passed，均区别于setup错误。开发中的5处旧native断言把历史inbox步骤回执与最终dispatch步骤混淆，仅改测试预期后整文件91过；root补充草稿首轮1 failed/12 passed是测试忽略继承旧指令，更正断言后通过；历史校验曾有两个FK/嵌套事务的夹具错误，另记于本机notes。中途通过数不累计。

WorkBuddy任务 `wb-bg-f4887d9fd6eb` 由桥接核实actual `kimi-k3-2`，只读实际新源码、未跑代码。它提出的同一UTC刻度问题经root真实服务+固定时钟复现：先dispatch再revoke的合法历史被严格撤权时间校验拒绝，peer/account两项RED。另两项建议未盲采纳：当前权限下find拒绝旧回执符合契约；poll revision并列被每账号唯一约束排除。

修复在持锁事务中聚合本账号已有UTC时间元数据：撤权必要时取已提交活动之后1µs，绑定、后继poll与dispatch回执遵守已提交时间下界，权限撤销本身立即生效。既有TaskInbox wall时间不改；新历史校验保留receipt不早于poll/mapping/event及严格当时撤权检查，移除计划之外的event必须不早于poll限制，因为跨peer逻辑floor可比旧TaskInbox时钟稍晚。定向2项GREEN及另一peer继续分发、被撤peer新消息blocked均纳入最终120；独立同库多peer探针复现该额外限制后GREEN，来源碰撞仍拒绝。时间用于本机因果元数据，不是远端认证或精确外部时钟证明。最新 `integrity-clock-final` 和源摘要替代早期 `integrity-notes.md` 中的额外时间断言/旧SHA。

独立reviewer先跑四新模块182 passed，再核对跨poll前缀、接收后授权拒绝审计+1而业务全回滚、重放不调用receive_batch三个探针；时钟修复另核对旧schema无dispatch表、UTC Z/offset字面排序、回拨/显式event下界/非法时区、实际多peer接续与碰撞，未改产品文件。独立探针与679正式去重计数分开；首轮探针非法audit action为夹具错误，未冒充产品失败。提交前另将8个已有文件恢复原有LF，除换行外字节及带位置信息的Python AST完全相同；`newline-preservation.json`保存变更前后哈希，`verification-summary.json`已更新最终18源码哈希。该换行还原后未重复业务回归。

| 最终关键产品 | SHA256 |
| --- | --- |
| `domain.py` | `c2d97ed5c5bbcc11a99ac23ba2f0935051828b8622e8b1f8f01dac40b225160a` |
| `weixin_inbox/accounts.py` | `9172aee83d25931a8d3669bfb505fc6a0a980405335abcc186cef24c47286f77` |
| `weixin_inbox/ingress.py` | `0c9a9f44cb46fd4fc1ffc7beb0fbeace4b84201ef2e2c952bbc150786d38bcab` |
| `weixin_inbox/dispatch.py` | `e991919b6d20de81f6bb9fbfbd1cfb171e30f15760b4d80bde144d15978a907f` |
| `weixin_inbox/dispatch_integrity.py` | `31be0d41902ab4b15284849cdf9f6a22993701f63d96b8009332ef2078bbe4e1` |
| `weixin_inbox/dispatch_schema.py` | `998edb572830f2e2b421dc531b42af506edec0def2188fc065bf32ef1980aed1` |

## 待办与NOT_RUN

下一片需设计并实现当前桌面身份下过期映射的显式重新授权/刷新，不能修改历史scope或隐式复活撤销映射；目前scope变化仍明确阻断。随后才接受控transport/可信身份入口及E有限期合同模型许可。

NOT_RUN：真实微信认证/轮询、机器人、真实合同外发、下载解密、Outbox/发送、产品真实模型/付费、E有限期许可、新安装包、全仓/Node/浏览器。运行SQLite未加密，qxbak加密不等于运行库加密。安装版0.4.1、既有原生长进程崩溃和WIN-PATH-02保持开放。
