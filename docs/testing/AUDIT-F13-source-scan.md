# 审计 F13：插件交付目录来源扫描

日期：2026-10-05；基线 `4d0f65a`；仅修复 `scripts/verify_sources.py` 的运行目录集合，加入 `plugins`。现有递归 hash/指纹扫描及采用冲突校验复用同一集合；未改插件文件、来源锁或批准。隔离 `sources` 仍不是运行目录。

## 实际失败与复验

|执行|退出码|实际结果|
|---|---|---|
|作者新增参数例 RED：`pytest tests/unit/test_sources.py -q --tb=short -k "plugin_delivery or isolated_source or plugin_runtime_target"`|1|14 failed / 2 passed / 28 deselected / 0 errors；plugins六类路径漏扫及reference_only运行目标被漏判|
|作者目标 GREEN：`pytest tests/unit/test_sources.py -q --tb=short`|0|44 passed；相比原28增加16参数例；无警告|
|独审相同44目标，独立JUnit|0|44 passed / 0 failure/error/skipped|
|独审 HEAD 旧实现对新增16例|1|14断言失败 / 2通过 / 0 errors；不修改仓库旧代码|
|独审独立虚构边界探针|0|26/26符合预期；两模式、隐藏/嵌套/改名/无扩展名、BOM/归一化、等价路径、隔离与正常插件|
|作者及独审 `scripts/verify_sources.py --mode development`|0|13来源；0 errors / 13 warnings|
|作者及独审 `scripts/verify_sources.py --mode release`|1|13来源；9 errors / 8 warnings，保留既有发布阻断|

pytest均使用项目 `.venv/Scripts/python.exe -m pytest`；完整 argv/UTC/子命令退出码见忽略目录原始 JSON，包装脚本exit0不替代测试exit。发布9项为 G04 未生产批准，以及 G06/G08/G10/G13 各依赖审核与生产批准未具备；没有新增 LICENSE_BLOCKED 或 ADOPTION_CONFLICT。

独审结论：本 F13 diff 无 findings；仅限已登记 hash/指纹及本次路径边界，不证明未知来源或任意改写均有许可。作者保全13文件、独审保全15文件均未变。其他正在实施的F03/B1不计入此独审。

## 原始证据

- 作者：`.audit-local/audit-f13-source-gate-20261005/REPORT.md`、`command-results.json`、`red.log/red.xml`、`green.log/green.xml`、`source-development.json`、`source-release.json`（以目录实际文件名为准）。
- 独审：`.audit-local/audit-f13-review-20261005/REPORT.md`、`command-results.json`、`target.log/target.xml`、`baseline-red.log/baseline-red.xml`、`probe-results.json`、`development.json`、`release.json`、`input-preservation.json`。

本切片没有全套、真实宿主、供应商或生产验收；完整回归在本轮父阶段记录另行登记，不把44与历史1030相加。没有运行附件脚本、网络抓取、真实材料或付费，也未安装/刷新插件或更改缓存。
