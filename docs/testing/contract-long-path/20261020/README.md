# WIN-PATH-01：Windows 深中文目录合同原件

2026-10-20，基线 `7446a9ce47d9452568f7d2ea1cf53c92167d53f4`。本片修复旧合同创建、读取及回滚清理的长路径失败，复用现有 `ops/file_paths.py`；唯一产品改动是 `persistence.py` 的 I/O 边界。没有新增依赖、schema、服务或新的路径封装。

## 修复后的行为

应用根和数据库 URL 保持普通路径；逻辑 `matter_uuid/version_uuid/original.bin` 引用不变。仅文件创建、读取、只读权限和失败清理使用 Windows 扩展路径。授权、大小/SHA 校验、独占写入、事务所有权、嵌套提交及回滚机制沿用现有实现。

目录独占创建仍在取得原件清理所有权之前。目录创建失败或 UUID 碰撞时，不能把其他事务的文件当作本次原件删除。不会递归清除共享案件目录；可能留下的空父目录不是成功原件或业务记录。读取路径检查或读取本身出现 OSError 时，沿用固定 `VERSION_CONFLICT`，不返回本机路径。

## 本轮实测

| 验证 | 实际结果 |
| --- | --- |
| 最终关联回归 | **424 passed，0 failures/errors/skipped，exit0**；pytest 522.01秒，外层进程524.953秒。含本片20单元及3集成测试，不重复相加。[完整结果](target-verification.json)、[JUnit](target.xml)、[日志](target.log)、[范围](target-nodeids.txt)。 |
| 四开发检查 | schema、defaults、sources development、runtime dependencies development 均exit0。原有生产来源许可及原生发布待办保持，不等同生产批准。见 [1](gate-1.log)、[2](gate-2.log)、[3](gate-3.log)、[4](gate-4.log)。 |
| 新增故障覆盖 | 实际原件根自身超过285字符；普通/已扩展输入；write/flush/fsync/chmod/审计/commit失败、root/nested回滚、close、UUID碰撞、创建目录失败、缺失/篡改及越界清理拒绝。已提交原件、版本数、配额和审计保持一致。[首批20项](unit-green-expanded.xml)。 |
| 同份合同恢复链 | 合成DOCX经HTTP上传及解析、原件读取、qxbak、长路径只读恢复下载、二次备份恢复；旧会话撤销和写入阻断，SHA及相对引用保持。[3项集成](backup-green.xml)。 |
| Windows实际TCP | **16次HTTP请求、3台源码服务，exit0**；原件父目录279→282→282字符，数据库路径208/211字符；两个恢复副本的下载和禁写均验证。模型/Jev调用0，输入摘要稳定，3台服务及端口均已关闭。[摘要](backup-summary.json)、[回执](backup-tcp-report.json)、[探针](backup-tcp.py)。备份恢复由同进程维护API执行，不称桌面按钮实测。 |
| 原诊断样本对照 | 同一 `sales-dev-1` 在短/深路径均完成解析、3项事实确认和18维mock；新深路径原件完整路径271字符。[结果](path-verification.json)。这是新独立目录复验，不是覆盖此前失败目录；没有真实模型调用。 |
| 独立需求复核 | 4项独立探针通过，0待修发现；授权先行、既有UUID marker不被误清理、nested释放后outer commit失败的清理边界。[审查](spec-review.md)、[探针及摘要](spec-path-probes.json)。 |
| 独立规范复核 | 4项定向检查通过，0待修发现；实际原件父目录280、恢复281、DB209字符。1个JUnit属性格式警告已留存。[审查](standards-review.md)、[实测](standards-evidence.json)。 |
| WorkBuddy | 本轮实际连通，`wb-b9aff7ba1c57` completed/end_turn；只读成功读取修复前3文件。静态意见逐项核对，未作为运行验收替代。[回执](workbuddy-review.json)、[处置](workbuddy-resolution.md)。 |

最终关联批次覆盖原件/鉴权、存储初始化、合同解析/重解析/事实、工作台、既有备份与升级恢复、40份合成样本验收。不是项目全套，也不把各阶段重复用例累计成总数。输入稳定性和精确命令见 `target-verification.json`。

## 保留的失败与限制

- 有效RED：3个新单元失败（普通路径mkdir失败，以及扩展前缀进入应用根），另有真实DOCX上传进入 `create_version` 后出现 WinError3；见 [单元](unit-red.log)、[集成](backup-red.log)。此前 WinError206 保留在[前片诊断](../../context-preview/20261020/path-diagnosis.md)，不改写历史证据。
- 实际TCP首轮在第二恢复副本的禁写POST遇到 WinError10054连接复位，[原回执](backup-tcp-reset-report.json)保留。相同副本用urllib/httpx各10次均返回预期409，原完整探针逻辑未改后重跑通过。**复位原因尚未确定**，不把这次失败删除或说成已修复的产品缺陷。[定向结果](backup-tcp-readonly-report.json)。
- Standards首轮命令参数拼接错误在收集前exit4，随后修正调用才4项通过；[原失败](standards-invocation-error.log)。没有因此改产品。
- qxbak合同原件链已实测；旧cnbak正常路径回归通过，不宣称旧格式在任意长目标目录可用。实际UNC网络共享、超过260字符的SQLite数据库文件路径、单个目录分量超长、Electron/冻结后端/新安装器未验。
- 安装版仍为0.4.1。真实合同、F盘原始资料和索引、网盘未下载年份、真实模型账户及阿里云部署未动。本片未测总体包体/RSS/冷启动，不宣称资源目标完成。

## 复现与接续

从仓库根使用独立合成环境和全新、足够短且有40GiB以上可用空间的D盘临时根，按 [目标清单](target-nodeids.txt)运行pytest；本片长目录由测试自己创建。复制 [verify.py](verify.py)/[target_runner.py](target_runner.py) 时改用新的输出目录，避免覆盖本次证据；不将已有资料目录作为basetemp。证据只复制显式选定的日志、XML、摘要与诊断脚本，[manifest](manifest.json)记录其字节摘要，不含临时数据库、原件、密钥或安装产物。

下一片回到 [CH-06B2b2](../../../plans/2026-10-20-context-send-storage.md)：同时闭合资料辅助回答的新许可、不可变输入格式、来源关联、原生确认和升级恢复，不绕过当前外发边界。
