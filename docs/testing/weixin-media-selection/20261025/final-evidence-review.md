# D2g5f 最终证据独立核算

范围：只读复核 `docs/testing/weixin-media-selection/20261025/README.md`、`verification-summary.json`、根四组 XML/log/metadata、Node/独立探针/开发门/浏览器记录及发布字节。没有重跑测试、修改已发布文件或审查本人 HTTP 测试的业务语义；这次是证据算术、来源和声明范围复核。最终 GitHub 提交/推送回执尚未生成，**明确不在此快照内**。

## 结论

**0 项未解决的证据算术、漏报失败或验收范围问题。** 曾发现 README 把同一 app 内持久 fence HTTP 拒绝写为“app 重建隔离”，root 已修正，当前文案明确不是 app 重建或新执行 qxbak。该修订与被独审 HTTP 模块的已述覆盖范围一致；本核算不对本人测试再作独立语义审查。

| 根组 | XML 实际不同 ID | PASS | FAIL | error/skip | metadata exit |
|---|---:|---:|---:|---:|---:|
| final-http | 47 | 47 | 0 | 0/0 | 0 |
| final-core | 67 | 67 | 0 | 0/0 | 0 |
| final-recovery | 76 | 75 | 1 | 0/0 | 1 |
| final-weixin | 47 | 47 | 0 | 0/0 | 0 |
| 合计 | **237** | **236** | **1** | **0/0** | 非全绿 |

逐条重建 XML `classname::name`，与机器总表每组 `test_ids` 顺序一致，组间无重复，11 个不同模块；新增 HTTP 模块恰 22 个不同 ID，已包含在 237 中，没有把作者首次 22 PASS 或 root 重复执行另加一次。四组 argv/exit 与各自 metadata 一致，日志尾部计数相符。

唯一失败 ID 为 `tests.integration.test_task_drafts_migration::test_restore_blocks_each_pending_execution_and_all_task_writes[awaiting_facts]`；trace 保留 `workspace_backup.py:380` 的 staging 目录发布 rename WinError 5。README/总表没有将它写为 PASS、SKIP 或生产完成，WIN-PATH-02 与原生 AV 仍 OPEN。旧 Python 恢复代码与迁移测试均未改，直接失败路径不执行本片 JS；这不等于根因已诊断或恢复可靠性已通过。

## Node、探针及失败历史

`final-node.log` 重新读取 293 个 Subtest、293 个 `ok`、293 个不同标题，TAP tests/pass=293，fail/cancelled/skipped/todo 均 0；argv 为 16 个 assistant Node 脚本。新增脚本在输出中的完整连续区间恰 60 项，包含于 293。

独立正式探针 GREEN 的 2 项均 PASS、exit 0，保持原正式 RED 探针字节不变；机器总表标记不计入主 Node/Python 数，口径正确。原始 RED 及初始误触 guard 的试写记录分开保留。

复算作者历史日志：初始 54 FAIL；首次实现 75 PASS（54 新+21 旧）；材料变化回归 55 PASS/1 FAIL；77 PASS（56 新+21 旧）；scope 回退回归 57 PASS/3 FAIL；81 PASS（60 新+21 旧）。历史重复未累计入最终 293。browser-01 的凭据校验失败没有被冒充运行成功，NOT_CAPTURED 已明确；browser-02 政策拒绝、browser-03 尚未直接观测 GET 的局限与最终 browser-04 补强也如实分列。

## 输入快照及发布字节

- 机器总表列出 **626** 项当前输入，逐项 SHA 与当前文件一致。
- 根四 Python、final-node、四开发门、browser-04 共 10 组，每组自己的 626 项 before=after。
- 较早 final-http/core/recovery/node 和四门相对最终仅有 `scripts/validate_task_media_selection_browser.py` 一个历史差异：`dee43897…`→`582ae180…`。总表逐组例外与重算结果完全一致。它是后来补强独立浏览器验收的脚本，早期这些组不导入/执行它；产品、测试、fixture 输入均一致。final-weixin、browser-04 已使用最终脚本，无差异。
- 总表 `published_copies_sha256` 的 **63 份**文件全部与公开目录实际 SHA 一致，且与 `.local` 原始文件**逐字节相同**，没有仅做“可读内容相同”的宽松核对。`browser-report.json`、两张 `browser-selection-*.png` 分别映射 `browser-04/report.json` 和该目录两张 screenshot；其余为同名原始文件。核算时公开目录 65 份文件为 63 份拷贝+README+总表。

四开发门 metadata 均 exit 0；实际来源日志仍有 13 个 NOT_PRODUCTION_APPROVED，依赖日志 `native_build_verified=false`、network_calls=0。最终 browser-04 的脚本 SHA 与当前一致、实际 exit 0，精确 DOCX PATCH / PDF PATCH→GET、前后原件 HTTP 200+bytes、原事件保持、四模型/执行表 0、外网请求和页面错误 0，均与已独审报告一致。这里是回读 root 记录，未冒充本核算者独立启动 Chromium 或再目视截图。

## Git 字节策略及独审身份

`.gitattributes` 本轮仅新增两条范围受限的字节保留规则：

```text
docs/testing/weixin-media-selection/20261025/** -text -whitespace
scripts/test_assistant_task_media_selection.mjs -text whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol
```

`git check-attr` 确认新证据日志与新 Node 脚本 text 为 unset、working-tree-encoding 未指定；防止 Git 对测量日志/JSON及有意 CRLF fixture 做换行改写。该变更属于 Git 证据字节策略，不是产品运行配置、模型/数据政策、依赖或数据库改动；不将它写成已执行的运行门。规则和其 SHA 另存本核算 JSON，626 个运行输入的历史口径不因此被改写。

README 准确区分：前端/Node 独审由未写它们的同一审查者按 Spec/Standards 两轴进行，排除其自编 HTTP22；HTTP 测试由另一位前端作者交叉审阅，不自审其 JS；浏览器脚本为独立静态核对与 root 实际记录回读。不是两个完全独立团队全产品审查，也不是本核算者独立重跑所有测试。

真实微信/合同/模型/付费、签发/外发、安装版 0.4.1、全仓长单进程及本轮 WorkBuddy 均没有被从 NOT_RUN 扩大成通过。GitHub、HumanLayer、Obsidian/TencentDB 最终回执由 root 后续实际执行核验，不属于本证据快照。
