# 原生升级前历史语义校验（2026-10-25，D2g5d 前置安全切片）

基线 `3aa504524dd256dc2130605ee06604eb64432204`；实际 Windows 工作目录 D:/Documents/ChatGPT/律所项目。仅修复原生升级的历史校验边界，保留 schema18 和旧分发 guard。所有验收材料独立虚构。

## 源码已实现

[workspace_upgrade.py](../../../../src/cn_contract/web/workspace_upgrade.py) 52行新增私有 `_validate_history`：复用既有 `ops.backup._file_references` 完整 family 校验，使用精确 `mode=ro` URI、显式 BEGIN、SQLAlchemy Session。没有构造 Database、初始化/补表、创建存储目录或重写业务来源；成功、异常均关闭连接并 dispose engine。业务校验错误统一为 `WORKSPACE_DATABASE_MISMATCH`，不将材料内容写入异常；原有 marker 写盘错误、DDL 回滚语义保持。

123行在任何升级备份/回执/marker 变更前按实际旧结构校验；156行在每步 DDL 的 BEGIN IMMEDIATE 写锁内重验，防止初检后业务变化。96–103行 pending 恢复在旧备份的哈希、精确结构、quick_check、外键和 workspace 核验后，再按该备份原版本语义校验；实际 current 库也须通过预验后才能补 marker。已完成当前版本且 marker 一致的 no-op 行为保持；本片不宣称所有当前库每次启动都执行完整健康扫描。

这是记录/逻辑引用层的校验，沿用现有 validator 的覆盖范围，不新增物理原件内容完整性校验或所有历史业务表的通用修复。原件字节未改由实际正反例单独核对。没有 DTO/结构/依赖/HTTP/UI 或账号、模型能力变化。

## 本轮实际验证及已有测试

[机器回执](verification-summary.json)记录完整命令、UTC、退出码、全部不同 case ID、272份源码/选中测试/helper/规格输入摘要以及捕获/发布证据摘要。各组 source_before=source_after，公共输入摘要跨组相同；间接导入的测试模块不在逐组清单时，不冒称被该清单逐一覆盖。最终7短组15模块共 **427个不同Python全部PASS**，含9新增，0FAIL/ERROR/SKIP；不是历史累计或全仓单进程。

| 根最终组 | 不同Python | 结果 |
|---|---:|---|
| legacy | 58 | PASS |
| schema | 173 | PASS |
| backup | 27 | PASS |
| ingress | 52 | PASS |
| integrity | 96 | PASS |
| paths | 12 | PASS |
| new | 9 | PASS |

四开发门 schema/defaults/sources/dependencies 均 exit0；来源仍有13个 NOT_PRODUCTION_APPROVED 提示，依赖门 native_build_verified=false。paths组1条既有 JUnit record_property/xunit2兼容警告保留。Node/前端本片未改，相关测试 NOT_RUN。

[新增9例](../../../../tests/integration/test_workspace_upgrade_semantic_preflight.py)先构造完整服务历史、独立原件及精确v17库。正式RED为3FAIL/1PASS：后代poll、后代dispatch、错误generation摘要均被旧validator拒绝，却被原升级接受；其中 **后代poll** 升到v18后通过新版更宽规则，实际证明升级洗白。dispatch并未被v18放宽，不混淆两者。

最小实现后初始4GREEN；扩展首次8PASS/1FAIL为测试读取已持Windows worker.lock触发PermissionError，只改夹具排除持锁字节并在锁外比较原字节。最终独立9PASS及根最终9PASS是同9例，不重复累计。正式RED前后源码SHA未捕获，标 NOT_CAPTURED；原始失败日志/XML均保留，[初始RED](initial-red.log)、[夹具失败](expansion-fixture-failure.log)、[独立最终9](agent-final-nine.log)。

新增实际覆盖：拒绝前DB/marker/目录候选/原件零变更；合法v17行/身份/原件保留及幂等升级；DDL已提交marker未写时坏current拒绝；旧备份外层SHA重算仍因旧业务非法拒绝；真实receipt写后篡改在DDL前复验拦截（已产生的备份/回执保留，无自动删除）；实际UPDATE得到 SQLITE_READONLY=8；写锁内独立writer得到 SQLITE_BUSY。

[Spec](spec-review.md)和[Standards](standards-review.md)由两名不同代理分别审查，均0确认遗留。Spec代理只写独立测试、未写产品；Standards代理未写产品/该测试，并实际跑[两项独立探针](independent-standards-probe.py)：WAL写者提交后预检仍读同一快照，成功/失败均释放engine且实际DBAPI句柄关闭，失败样本字节不变。[探针回执](independent-standards-probe.json)、[执行命令](independent-standards-run.json)。探针原执行位置为本机.local目录，发布副本未另行执行。

## 尚未实现与 NOT_RUN

本片是代际分发前的安全前置修复；v19索引/按固定代际合成分发设计仍是建议，未升版本或解除旧guard。已完成A—C与代际收件/固定查询不重做。可信微信身份、账户资格/数据政策及E有限期授权仍待。

全仓长单进程、Node/前端、浏览器/Electron、安装版0.4.1、WorkBuddy本轮、真实微信/合同/产品模型/付费调用均 NOT_RUN；没有安装机器人、连接账号、外发或签发。WIN-PATH-02目录rename WinError5和原生长进程AV保持OPEN。

GitHub按后续实际同步回执核对；用户AGENTS保持未暂存。HumanLayer/Obsidian按本轮独立回执收尾，TencentDB沿正常Stop，不预报尚未发生的成功。

[最终独立证据复算](final-evidence-review.md)确认427不同用例、272输入、失败边界与发布字节一致，0发现；后续Git回执不在该审查快照内。
