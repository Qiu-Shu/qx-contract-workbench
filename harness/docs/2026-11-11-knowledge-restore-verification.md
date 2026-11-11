# 2.16 审核 R01 / R02 修复验证

基线：`b802e214d66c694e91350e59d57917c611ae1581`（相对 v0.2.16 只改发布记录）。本轮全部用独立合成数据、内存/临时 SQLite；未打开用户业务库或调用真实模型。

## 最终行为

- 新导入的来源记录持久标记“尚未在本机见到”；刷新、读取前检查、材料同步、导出均保留正文、引用及历史。界面和模型索引说明原文暂不可追溯。恢复条目默认待核对；人工确认后可分片读保存正文，原文追溯仍须真实来源存在。
- 本机观察到来源后恢复正常来源生命周期；明确删除及已有删除标记继续阻止旧备份复活。只对迁入但未见来源作区别，不取消来源清理。
- 恢复按目标库当前会话绑定归位，修正同来源已存在的错配条目；不覆盖正确归属条目的人工更正。归属冲突写 audit，并在恢复结果计数；修订历史使用当前条目归属。
- 兼容旧 v1 中无 bindings 行的 inbox 条目；来源绑定缺失但声称其他项目的异常备份仍拒绝。历史页补全其当前条目与绑定的传递依赖，可逆序导入。
- 两份旧知识测试显式区分 local/model，使用当前自动工作归属、404语义和有效来源列表；未改产品默认模式以迎合旧测试。

## 实际执行

命令从仓库根目录运行，Node `v24.20.0`。下列日志在本地忽略目录 `harness/.local/audit-0216/knowledge/`，不包含真实材料。

| 检查 | 实际结果 | 日志 |
|---|---|---|
| `node --test harness/desktop/integration/knowledge-restore.test.mjs` 修复前 | 11项：2通过、9失败，退出1；正文清空和归属错误实际复现 | red.log |
| 首轮修复后同命令 | 11/11通过，退出0 | green.log |
| 旧 API/runtime 两文件原样 | 19项：9通过、10失败，退出1 | legacy-red.log |
| 修正过时测试并增加默认 local 测试 | 20/20通过，退出0 | legacy-green.log |
| 独审发现旧 inbox 不兼容、本机见到后删除；自查历史分页依赖 | 15项：12通过、3失败，退出1；修复后15/15、退出0 | observed-red.log / review-green.log |
| 人工确认迁入规则可读及原文未迁入标注 | 新增测试先失败，修复后16/16通过，退出0 | restored-read-red.log / restored-read-green.log |
| 知识、材料、统一知识、可移植案件提供方、并发归属回归 | 77/77通过，0跳过，退出0 | final-regression.log |
| 客户端语法 `node --check harness/desktop/integration/knowledge-client.js` | 退出0 | 本轮命令输出 |

77项命令：`node --test harness/desktop/integration/knowledge*.test.mjs harness/tests/knowledge-flow.test.mjs harness/tests/knowledge-materials.test.mjs harness/tests/unified-knowledge.test.mjs harness/tests/unified-portability.test.mjs harness/tests/audit-standards-scope.test.mjs`（PowerShell 先将通配符展开为文件参数）。`NODE_PATH` 使用现有本机发行依赖和构建依赖；`QX_TEST_APP` 指现有合成验证 payload，提供 Python 运行时。未安装依赖。

初次扩大回归时缺 DSH 依赖导致1文件加载失败；补现有依赖路径后可移植测试又因未设 QX_TEST_APP 找不到 Python 失败。分别记录于 regression.log、regression-with-deps.log；补齐前置环境后的77项结果为最终关联验证。专项结果有重叠，不累加为平台总通过数。

## 独立审阅与限制

独立审阅复现旧 inbox 兼容和 seen-then-deleted 两项问题，均补失败测试后修复；恢复规则确认后的模型读取问题也纳入本次修复。测试覆盖真实路由处理器和模型工具入口，但使用合成源及内存数据库；不是原生 Electron GUI、真实模型法律质量或已安装用户数据迁移验收。旧备份不能告诉新设备备份之后在另一台设备发生的删除；该固有限制保留。
