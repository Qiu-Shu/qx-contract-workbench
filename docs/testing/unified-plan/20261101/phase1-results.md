# 阶段 1：S1/S2 修复与验证

日期：2026-11-01；工作目录 `D:/Documents/ChatGPT/律所项目`。阶段 1 已完成，本轮证据与历史/中途结果分别记录如下。

## 改动

- S1：前后端使用同一组中文合成反例。补齐“暂时不”“不再”、暂停/取消/撤回、只接收材料、条件句和引用转述的保护。桌面在 Jev 辅助判断前检查停止指令，保存期间的新指令也重新核对；存在未知请求时只查询原请求，不重发。
- S2：从批次完整文本保留有效的“继续整理材料”，把材料就绪与事项续接分别判断。原任务继续处理时保持 task_id 与旧材料摘要；多个候选事项继续澄清。
- 微信顺序：保留上游 `seq`、`create_time_ms` 为可选 DTO 字段，写入既有不可覆盖的事件 JSON；不新增数据库表。旧事件缺字段时序列化仍省略字段，保持历史摘要兼容。完整且唯一的源顺序一致才采用；矛盾时保留材料并澄清。缺源时序时，同一首次接收批次按事件顺序处理明确更正；跨接收批次不能仅凭到达顺序解除停止，需在桌面核对后重新发起。不会假定 message_id 可比较。
- 测试夹具：既有历史数据库夹具遗漏 0.6.0 新增的九张微信服务/共享判断表，导致旧结构断言失败。仅在测试 helper 中剔除这些**空表**；有记录即拒绝重建。产品数据库迁移、不可覆盖约束与安全校验没有放宽。
- 旧本人微信流程：与服务批次共用 `instruction_order.py`。在保留全部原事件的前提下，先确认控制消息顺序，再把已解决的暂停/继续控制从业务问题中排除。无法确认跨批恢复时保留材料并提示桌面核对。
- 桌面恢复：后端已有所有权、版本与活动状态检查通过后，在现有不可变 `audit_events` 中追加摘要收据；收据绑定用户、会话、草稿及当时控制事件。后到的停止使摘要失配，旧收据不能解除新停止。没有新增表、覆盖原事件或自动恢复真实账户。

完整产品/测试增量为 `phase1-files.json` 中的 21 个文件，逐文件保存相对于受保护原工作树的前后摘要；可审阅补丁为 `phase1-increment.patch`。包括共享指令保护、旧本人微信兼容及桌面恢复收据，并维护两个历史夹具 helper；未改材料解析器、模型服务或数据库结构。

## 失败先行与审阅

| 证据 | 实际结果 | 结论 |
| --- | --- | --- |
| `audit-red.log/xml` | 3 failed、1 passed，exit 1 | 本机复现原审计 S1/S2，未继承历史结果 |
| `intent-red.log/xml` | 22 failed、7 passed，exit 1 | 否定、条件、引用、桌面/微信边界补充反例 |
| `probes/independent-findings.md` | 独立审阅发现 3 项 P1 及一项条件/转述恢复建议 | 报告为候选早期版本；未改写历史审阅结论 |
| `source-order-red.log` | 3 failed、8 deselected，exit 1 | 迟到、缺顺序与相互矛盾顺序不得解除较新停止 |
| `resumption-red.log` | 2 failed、32 passed，exit 1 | 条件/转述后明确选择另一能力时，不能残留旧能力 |
| `scoped-stop-order-red.log` | 2 failed，exit 1 | 能力级“不再/取消审查合同”也需防迟到恢复 |
| `fixture-and-order-green.log/xml` | 118 passed、240 deselected，exit 0 | 修复后的停止/恢复/原审计及历史升级定向检查 |

独立审阅探针及原审计反例已按字节保存到 `probes/`，原路径与摘要见 `probe-snapshots.json`、`final-review-snapshots.json`。其中相对导入路径保留原样，重放时应恢复到登记的原路径。正式新增回归已进入 `tests/` 与 `scripts/`。原三项 P1 的 8 个独立探针及桌面 5 条轨迹通过；后续旧微信源时序 P1 与桌面恢复 P2 也经独立失败、修复、复验关闭。最后限定复核为 5 passed、22.48 秒、exit 0，见 `probes/final-review-findings.md`；不把作者回归计为独立复核。

## 最终回归

最终后端选择见 `regression-green-selection.json`：89 个文件、3,070 项，包含现有全部 `test_weixin*.py`、业务/模型/材料生成、任务草稿、相关升级与原审计/独审探针，分三组在独立合成临时库执行。实际命令、UTC 时间、退出码分别保存在 `regression-green-*-command.json`；测试数量以 XML 和日志为准。源文件摘要见 `regression-green-source-hashes.json`，运行期间一致性另存。

广回归原始结果：3,067 passed、3 failed；第二组另有一条既有 Pydantic 非字符串输入警告。三个失败均为旧本人微信暂停/桌面指定后恢复，之后已经修复。运行期间发现缺陷并修复的五个已有文件列于 `regression-green-source-stability.json`；因此这轮不能称为最终源码的 3,070 项全部通过。

补充验证：`personal-resumption-green` 为 71 passed；`shared-order-green` 为 20 passed、71 deselected；`desktop-resume-receipt-green` 为 57 passed，均 exit 0。它们分别验证兼容过滤、共享源顺序及桌面确认收据，所用源码版本不同，不相加冒充一个通过总数。

最终冻结源码复验：`phase1-final-1` 为 128 passed、314.38 秒；`phase1-final-2` 为 132 passed、106.53 秒，均 exit 0，共 260 项通过。覆盖全部旧本人微信运行测试、新顺序及恢复测试、服务批次路由/执行、S1/S2、草稿及完成记录备份、审计相关版本测试。运行前摘要为 `phase1-final-source-hashes.json`，`phase1-final-source-stability.json` 确认运行期间源码/测试没有变化。

桌面与前端最终命令见 `final-frontend-and-gates-commands.json`：

- `desktop` 的 `npm test`：419 passed，exit 0。
- 22 个现有 `scripts/test_assistant*.mjs`：全部 exit 0；其中业务入口 50 passed。
- schema、默认配置、开发来源、运行依赖四项检查：全部 exit 0。来源检查的 `NOT_PRODUCTION_APPROVED` 等状态保留，不是发布批准。

未运行全仓 Python、安装构建、原生界面完整走查、真实模型、真实微信或律师法律质量验收。测试中的模型调用为合成 provider/本地回放，费用数字为测试账本数据。

## 中途失败与中断

保留全部尝试，不能合并计为最终通过：`intent-green-1` 有测试表名错误；`review-green` 有 DTO 视图传播遗漏及重启边界失败；`review-green-2`、`temp-diagnosis` 暴露新增顺序查询越过 session 生命周期导致数据库锁等待，已将查询移回原 session；`review-final` 的一项引用原话匹配失败已修复。早期名为 green/final 的文件名不代表通过，以退出码为准。

`regression-1` 和 `regression-final-1/2/3` 在审阅或旧夹具失败后主动中断；`regression-schema-diagnosis` 亦未完成。中断退出码及部分输出原样保留，不据进度点计算通过总数。所有测试库均为独立临时合成库，没有打开用户生产数据。

## 阶段推进边界

阶段 0 报告与 213 个原有改动文件备份已完成；原计划在 `docs/plans/群兴工作台_Codex实施计划.md` 原样保存。阶段 1 已达到 S1/S2 与相关安全回归门，按顺序进入阶段 2。最终 260 项并非全仓 Python 验收，不改写广回归及各次中途失败的原始结果。

阶段 2 的能力/来源清单见 `docs/plans/2026-11-01-phase2-capability-inventory.md`。用户已明确确认家事为其自行研发项目并授权本地接入，沿用本机 0.2.0，保留第三方来源与许可声明。客户接待明确使用用户既有“超级销管智能体”（本机登记“超级销冠智能体”）来源；九份资料自动检索尚未接通，不能称四能力已完整融合。

本轮未提交、推送、发布、覆盖安装版或调用真实账户。
