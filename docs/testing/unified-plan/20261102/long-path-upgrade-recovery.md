# 超长目录：升级中断后的恢复验证

2026-11-02。本片已修正超长目录中“数据库升级及回执已提交、workspace标记写入中断”后无法重新打开的问题。仅代表下述隔离源码及合成验证；完整回归与内容采用仍未完成。

## 改动与证据

沿 `trademark-regression-repair/律所项目` 实施，主仓只同步文档。先固定原984份源码和上一片346份证据；本片变更两个已有文件，新增一个测试模块，现985份执行摘要固定。原N983份源码仍供原完整套件使用，不改写其失败。

真实入口 `build_local_app` 先在 `_open_workspace` 检查数据库和标记，再进入升级流程；先前只在 `upgrade` 转换长路径，前置 `pending_matches` 仍用普通路径读取回执和备份。新反例在大于300字符的旧版虚构工作区完成SQL及回执提交，注入标记写入失败，再从真实入口重开，得到 `WORKSPACE_DATABASE_MISMATCH`。原业务行、旧标记和源目录字节的前置断言均已先通过。

产品仅在 `pending_matches` 入口复用 `filesystem_path`。严格schema、工作区身份、回执字段、路径约束、备份hash、只读SQLite、完整性及历史语义检查均保留；未改权限、全局Database或逻辑URL。成功恢复核实登录及原件读取、原身份/业务行、既有回执及before.db字节、不重复已完成升级，随后再次打开无迁移。两个负例分别损坏回执和备份，拒绝打开且故意损坏后的整目录字节保持。

同时真实运行旧中断恢复单项，发现其夹具创建当前结构后漏删9张现有service表，导致精确旧schema等式在测试体前失败（1个setup error，不能说58个测试均实跑失败）。只补显式DROP清单，保留完整精确schema断言和原测试体。该夹具影响的旧模块已整体验证。

## 实际验证

原新用例RED为1失败/2通过，最小修补后3通过；旧夹具原setup error完整保留。最终关联批次如下，重复节点不累加：

| 批次 | 退出码 | 实际结果 |
| --- | --- | --- |
| `upgrade-gap-related` | 0 | 38通过 |
| `upgrade-gap-related-v2` | 0 | 65通过 |

本片共 **103个不同用例最终通过**；新3项、旧中断恢复模块、语义预检哨兵、长路径只读身份及先行入口/旧模型升级关联均在实际XML中定位。首次3项GREEN包含于最终数量。上一片237项、四开发门和更早桌面633项为历史证据，本片不重复计数；本片未改schema定义、默认配置、来源或依赖声明，未重复四开发门。

独立Spec和Standards审阅固定三文件及其before/after摘要，读取命令及退出码分别在报告保存；未发现本片需再修改的问题，不将只读审阅称为额外测试通过。协调者汇总时曾把旧封印外层对象误当文件表，断言退出1且尚未写出新源码摘要；保留原脚本/日志，v2使用files映射核对346原件并成功。命名检查截至汇总快照为13条、退出码分布{'0': 10, '1': 3}；独审读取、直接查找和后续文档/收口核验另记，不能当作全轮命令总数。

## 仍待处理

- 原完整回归session90073仍在运行。截至2026-11-02T06:28:37.262843+00:00，输出2550个结果标记、16个失败；8642为收集数。新增 `test_case_evidence_pipeline::test_oversize_persisted_input_rejects_before_ledger_or_transport_and_rolls_back_message` 尚未归因，须取得实际栈或独立定点复现；不假定与已修缺陷同因。只查原句柄，不并发启动另一全套。
- WIN-PATH-02最终目录rename的间歇WinError5仍OPEN；本片不涉及该故障，也未加自动重试。超长新建initialize=True及junction仍未验收。
- 商标v5/v6内容实验仍未初始化/派发，0/4原答、0/8评分；E已准备的材料、协议及控制器不重做，46份提升/来源文件与旧失败分母保持。工程状态核清后再迁入确认副本、建立正式基线。
- 合同补发待既有确认，不重试或重复询问；伙伴模型接口待办。无提交、推送、合入、安装、真实付费模型、微信、QCC或外发。

## 可复查记录

证据目录：`C:/Users/Administrator/.codex/worktrees/trademark-regression-repair/律所项目/.audit-local/long-path-upgrade-recovery-20261102`。

- `PLAN.md`、`PLAN-addendum-v2.md`、`baseline.json`：边界与旧源保护。
- `upgrade-gap-review-v2.json/.diff`、`review-v2-files/`、`source-snapshot.json`：三个实际变更和985份固定摘要。
- `upgrade-gap-red/green/old-fixture/related/related-v2`的日志、命令、XML和finished记录；`checks-summary.json`：实际数量与去重口径。
- `spec-readonly-diagnosis.json`、`spec-final-review.json`、`standards-final-review.json`：诊断与固定输入独立审阅。
- `original-full-snapshot-02.json`：原完整运行观察；`handoff-verification.json`：最终保护、文档和接续核验。

上一片保持为历史：[长路径恢复修复](trademark-regression-repair.md)。后续内容计划：[商标v5/v6](../../../plans/2026-11-02-trademark-v56-content-comparison.md)。
