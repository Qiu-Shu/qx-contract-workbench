# 本地备份的数据范围与停写入口

2026-11-12，接续[备份准备计划](2026-11-12-backup-preparation-plan.md)，基线 `e334db351cd71f6f6b9e93c8e11e01842d56d2b9`。本轮新增开发侧准备入口；**未生成备份或恢复目录，未接入 restic 产品功能，未构建或安装新版。** 原有 [restic 实验及准入结论](research/2026-11-12-candidate-restic-admission.md)继续有效。

## 已确认的数据范围

下列路径都相对于明确选定的安装数据根，默认是 `%APPDATA%/QunxingHarness`。本轮从源码和合成数据核对，没有扫描用户正在使用的数据根。范围检查只读取文件系统元数据及有限的宿主状态 JSON，不读取业务正文、凭据或数据库记录。

| 范围 | 准备入口的分类 | 后续备份/恢复要求 |
| --- | --- | --- |
| `workspace/` | protect | 保留原件、收件、草稿、自定义方法、材料/案件/知识/媒体数据库及全部相对引用；目录内新增文件也进入清单 |
| `.qx-private/` | protect | 保留脱敏原件、映射和预览；必须进入加密备份及受限暂存区 |
| `.local/dsh-home/sessions/` | protect | 宿主 JSONL / 压缩会话日志及版本信息；不是仅靠 SQLite 保存聊天 |
| `.local/dsh-home/storages/` | protect | 宿主 JSON KV 持久状态，包括工作区关系等；恢复后不能据此自动重发任务 |
| `.local/layered-knowledge.sqlite` 及侧文件 | protect | 分层知识数据库；兼顾历史 `.local/dsh-home/.local/` 位置，不能漏掉 WAL |
| `.local/dsh-home/qx-wechat/qx-route.json`、`qx-seen.json`、`qx-pending.json` | protect | 路由、去重及待处理消息不能当凭据一起丢弃；未来恢复待处理消息必须隔离待确认，不能自动发送 |
| `.local/case-memory-runtime/database/` 与 `instance.json` | cold-postgres，必须待审 | PG 冷备及其数据库身份；身份文件含数据库口令，不能省略或输出。尚未验证可恢复性，不自动重建、不自动调用模型 |
| `.local/dsh-home/profiles/` | settings-review | 自定义配置可能包含外部路径和秘密；后续逐项迁移，不能直接复制启用 |
| `.local/desktop-data/`、`.local/dsh-home/.credentials.yaml` | reauthorize | DPAPI/模型凭据和桌面配置不当作可移植业务文件；换机须重新授权 |
| 其他 `qx-wechat/` 项目 | reauthorize-review | 登录态、联系人及偏好需分别处理；本步不读取内容，也不擅自丢弃或恢复启用 |
| 已知组件、模型、虚拟环境、运行日志与令牌 | rebuild / runtime | 不列入本步业务文件集合；恢复时重新准备不等于已获联网、下载或付费许可 |
| 未识别的目录或文件 | unclassified | 明确待审，不静默跳过；不对自定义外部存储作完整性保证 |

路径策略见 [backup-preparation.cjs](../desktop/backup-preparation.cjs)。SQLite 主文件及 `-wal`、`-shm` 都列入范围；`storage: sqlite-set` 只是处理提示，不是数据库校验结果，更不是允许逐文件热拷。文档、文件名里人为保存的秘密也不会被本步自动识别。

宿主默认会话和 KV 位置由现有固定依赖 `@deepseek-ai/dsh-base/cordis.patch.yml` 的 `dshHomePath('sessions')` / `dshHomePath('storages')` 核对；附件位置来自 [portable.json](../packaging/payload-config/portable.json)。其他来源包括 [安装运行入口](../desktop/installed-runtime.cjs)、[增强记忆运行入口](../desktop/case-memory-runtime.cjs)、[分层知识 API](../desktop/integration/knowledge-api.mjs)、[微信插件](../plugins/wechat/qx-plugin.js)、[材料库](../bridge/store.py)和[脱敏](../bridge/privacy.py)。

## 离线维护窗口的行为

`withBackupPause(data, consumer)` 先核对安装布局及路径，再取得和 [installed-host.cjs](../desktop/installed-host.cjs)完全相同的 `claimLauncher` OS 独占锁。后台在运行或另一轮维护已取得锁时拒绝。取得锁后，还要求宿主状态与运行记录属于同一 launcher、状态为 stopped、host PID 均为空；缺记录、记录损坏、仍在停止或停止身份不匹配都拒绝。

增强记忆仍有 owner / PostgreSQL PID 文件或状态仍在运行时也拒绝，包括无法证明已停止的残留文件。不会自动删除它们，不会杀进程。正常返回或抛错都会释放锁；维护进程崩溃由 OS 释放。持锁期间再次启动真实安装宿主会在初始化前失败，业务文件不变。

这不是在线排队暂停协议：使用前须等任务完成并完整退出后台，单纯关闭窗口可能仍保留微信后台。它只隔离受管安装宿主，不能锁住外部编辑器、直接启动的 Python/上游 CLI 或外部工作区。后续一致快照仍需校验源文件是否变化，以及各数据库与文件引用是否完整。

被保护范围中的 junction、符号链接、硬链接及特殊文件会拒绝；已知排除范围的根如果是链接，会标记 `linked: true` 和待审，不跟随目标。未知目录不递归扫描，只报告分类。范围检查有深度及数量上限，不能把超限称为完整。

## 开发入口

在源码 `harness/` 下运行 `node scripts/backup-preflight.cjs --data <绝对安装数据目录>`。它在维护锁内执行一次范围检查，随后释放锁；只打印文件数、字节数、分类数及待审状态，不打印文件名、业务正文、令牌或凭据。失败输出稳定错误码并退出 1。

退出 0 只表示本次准备检查执行完成。输出始终带 `backupComplete: false`；`scopeReviewRequired: false` 也不表示已有可恢复备份。脚本结束之后没有后台锁、定时器或持续备份。未来快照步骤须在 `withBackupPause` 的受控回调内完成，不能使用已释放的检查结果冒充停写状态。

## 实际验证

证据目录：`D:/CodexChecks/AI-Shixiong-backup-preparation-20261112`。仅用自动生成的合成数据；没有触及运行中的用户工作台或调用模型。

- 新入口的首轮测试分别因缺少模块/导出而失败，记录为能力尚未实现，不冒充旧产品的业务缺陷复现。
- 9 项目标测试通过，exit 0：活动锁拒绝、真实宿主启动被阻止、两轮维护互斥、回调异常释放、维护子进程实际被终止后的锁释放、停止记录及 PG 拒绝、数据范围与凭据分类、链接防越界、命令输出脱敏。
- Standards 初审无硬性违规或可操作 smell；Spec 发现排除的缓存 junction 未被标为待审。新增用例实际 RED（`false !== true`）后修复，独立原探针复跑通过，两轴最终未解决项均为 0。原失败证据保留。
- 完整离线回归与最终 Node 回归的实际数量、命令、退出码及源码/日志摘要见[结构化验证记录](checks/backup-preparation-20261112.json)。链接修复后只重跑受影响的完整 Node 集，Python 本轮未变动。

下一步是受限暂存区及各 SQLite 一致副本，再接 restic 完整快照登记与新目录恢复。PG 冷备/恢复、跨库引用、外部文件改动、空间/权限故障及换机凭据仍需各自验证。本轮不把“准备步骤完成”扩大为“全量备份已保护”。
