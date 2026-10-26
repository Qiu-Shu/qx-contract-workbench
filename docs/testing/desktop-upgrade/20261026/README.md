# 0.5.0 本机安装升级与后续回归（2026-10-26）

用户要求“先升级桌面安装软件，然后继续”。基线 `8945e38dc441b9aae2888c6adffb697fa56ad6ee`。已在原安装目录将 0.4.1 更新为 0.5.0，注册表版本、应用实际版本均核实，默认资料目录已成功启动到登录页；未替用户输入密码或触发真实模型发送。安装前、安装后启动前，全部 64 个用户资料文件逐文件 SHA256 相同。首次新版启动后，原件、设置和受保护凭据 4 个文件未变，旧数据库 63 张表中的全部旧行保留，数据库 integrity_check=ok。

本次修改仅包含版本号、显式补入入口依赖 model-bridge.cjs、中文路径 npm shim、打包依赖测试、桌面升级验收脚本和两处旧数据库测试夹具。Python 产品源码未改变；真实微信和真实模型联调未验收。用户 AGENTS.md 原修改未纳入提交。

## 安装与保留资料

安装包：`dist/desktop/Qunxing-Workbench-0.5.0-Setup.exe`，146,701,149 字节，SHA256 `a7f83e8517aaa1a6d0f4e02b371dc3a3de50cb9e57654343ecbb3bcf0df34fb3`。未签名。安装包、运行库、真实资料与凭据均不上传 Git。

使用现有 NSIS 当前用户安装的 `/S` 原地升级，退出码 0；appId、资料目录、卸载保留资料选项未改变。已安装目录中的 586 个文件与验收过的 win-unpacked 文件逐一摘要相同。升级前完整资料副本保存在本机 `%LOCALAPPDATA%/QunxingWorkbenchValidation/upgrade-snapshots/before-0.5.0-20261026`，未上传。原安装目录名称仍含 041，不影响当前实际版本 0.5.0。

资料核对算法：安装前递归计算用户资料目录全部普通文件 SHA256，复制至新建备份目录，再比较源、复制目标两份清单；安装后首次启动前再次比较全部 64 项。首次启动后对 protected、model-credentials 和 desktop-settings.json 再核摘要。用 sqlite3 `mode=ro` 打开备份库和当前库，检查当前库完整性；枚举备份库 63 张表，以各表旧列列表投影当前表，逐行确认每条旧行均存在，且无表行数减少。只保存脱敏计数到 [data-retention.json](data-retention.json)，完整清单与数据库留在本机忽略目录。这里不声称检查了真实案件业务内容或完成律师验收。

## 实际验证

| 检查 | 结果 |
|---|---|
| 打包依赖回归 | 实际 RED：main 缺 model-bridge；修复后 2/2 PASS |
| 桌面逻辑 `node --test --test-reporter=tap desktop/tests/*.test.cjs` | 370/370 PASS，退出 0 |
| 固定依赖构建 `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_desktop.ps1` | 最终退出 0 |
| 旧安装版合成案件 `desktop/tests/acceptance.cjs` | 14 项检查 PASS |
| 旧合成工作区 → 新包 `desktop/tests/upgrade.cjs` | 10 项检查 PASS |
| 新包全新合成工作区 `desktop/tests/acceptance.cjs` | 14 项检查 PASS |
| 实际安装核验 | 586 文件一致、0.5.0 原工作区到登录，4 项 PASS |
| 已安装版本合成加密备份/恢复 `desktop/tests/backup.cjs` | 10 项检查 PASS |
| 两份升级 Python 回归 | 最终 67/67 PASS，退出 0，134.04 秒 |
| schema/defaults/sources/runtime 四开发门 | 各退出 0 |

桌面验收的 14/10 是脚本内检查点，不能与 Node/pytest 用例数相加。旧版合成测试保留旧账号、案件、原文锚点及 Word；新包升级检查新底稿的保存/重载、事实/跟进/导出入口、待收件目标列表、重启保留草稿和所属后台退出。浏览器监听未见页面脚本错误或页面外联；该监听不代表全系统网络审计。

Python 命令：`.venv/Scripts/python.exe -m pytest tests/integration/test_workspace_upgrade.py tests/integration/test_workspace_upgrade_semantic_preflight.py -q --tb=short --junitxml=.audit-local/desktop-upgrade-20261026/upgrade-final.xml`。两次结果分别保存 initial/final 的 JUnit 和日志。

四开发门分别执行：`python -m cn_contract.cli schema --check`、`python scripts/verify_defaults.py`、`python scripts/verify_sources.py --mode development`、`python scripts/verify_runtime_dependencies.py --mode development`，均使用项目 .venv。构建实际 Python 3.12.14、Node 24.22.1；桌面 Node 测试使用本机 Node 24.20.0。Electron 44.8.0 / electron-builder 26.15.3 / npm 12.2.0 依原锁定依赖，未升级或改写第三方依赖锁。

首次构建被 Windows PowerShell 执行策略拒绝，改为仅该构建进程 ExecutionPolicy Bypass，未修改系统策略；随后复现中文绝对路径写入 npm.cmd 后乱码导致依赖扫描无 JSON，改为 ASCII shim 用自身 `%~dp0` 定位固定 npm，`npm --version` 返回 12.2.0，最终构建成功。首次 UI 升级脚本误等待“第 1 版”，实际产品显示“已保存档案版本 1”；仅修正测试文本，使用重新由旧安装版建立的全新合成工作区重跑通过，保留首次失败记录。

安装完成后的升级回归首次为 58 setup errors + 9 FAIL：旧版夹具漏删后来新增的 assistant_evidence_revisions、assistant_followup_revisions，恰好多出两表/四索引/四触发器。两处仅补充 DROP TABLE，原精确 schema 相等、identify_schema 和全部语义断言保持。独立 AST 核对 17 个测试函数与基线一致；最终完整 67 项重跑通过。此修正仅影响测试，不要求重建已安装软件。

## 继续处理恢复故障

已安装版本本次完成一次合成加密备份/恢复和原件、历史 Word 核对，但不能用一次成功关闭 WIN-PATH-02。继续尝试 Windows 内置 WPR 的 Kernel-File 事件校准：独立冻结后台副本、独特进程名、单次合成恢复。恢复成功并捕获一次 rename。实测本机 ProcessExeFilter 没有约束该内核提供程序，故停止此采集路线；仅保留目标测试进程的脱敏 rename 摘要，无关原始 ETL 已删除，并核实 WPR 不再运行。没有持续或全机后台采集。

[校准结果](trace-calibration.json)仅说明采集能力与限制，不是故障复现或根因。IRP 地址会复用，不能仅按地址拼接跨时间事件；本轮不声称获取了失败 NTSTATUS。Microsoft 的 [EventProvider 文档](https://learn.microsoft.com/en-us/windows-hardware/test/wpt/eventprovider)说明该过滤属性，但本机实测不满足所需范围，不能以文档替代校准。下一步需先验证能严格限制到合成进程的事件入口，再捕获失败时间窗；不加入产品重试、不改 ACL、不关闭安全软件。

WIN-PATH-02、既有原生 AV 均继续 OPEN；未重跑全仓长进程测试、未验证真实微信/模型、未验证干净第二台 Windows。安装成功、合成演示、法律验收、生产完成分别记录。

独立复核：Spec/Standards 均 0 确认遗留；覆盖实际 asar 显式文件、固定依赖、测试夹具精确性、升级脚本与文档边界。67 项最终成绩由主代理在复核后读取实际退出 0 确认。
