# 本地业务快照、加密保存与隔离恢复

2026-11-12，接续 `444faf80a48181867b937528959919e176acc5db`。实现[本轮计划](2026-11-12-local-backup-plan.md)中的业务文件与 SQLite 闭环，复用既有[范围分类和离线维护锁](2026-11-12-backup-data-scope.md)。这是源码侧操作入口；安装版未更新，未构建安装包，也未备份真实用户材料。

## 已实现的行为

- 备份必须先完整退出受管后台。维护锁覆盖范围检查、快照和加密保存，期间宿主不能重新初始化。不会替用户强杀运行中的工作台。
- 选定业务文件取得 Windows 只读共享句柄；已有写入者导致拒绝。复制前后核对清单，普通文件保留时间戳。SQLite 主文件与 WAL 在冻结时复制到私有暂存，然后从该副本用 SQLite backup API 生成独立数据库，源数据库不做 checkpoint。
- 快照检查文件摘要、数据库 integrity/FK、材料库到原文件的引用、脱敏原件/映射/安全副本，以及已复核副本的引用与摘要。材料恢复后仍能通过现有 `MaterialStore.current()` 检查。没有声称逐项证明所有历史业务语义。
- 每次备份写入全新的目录，里面是独立 restic 仓库。仅在引擎退出 0、完成摘要合法、文件数相符且 `check --read-data` 成功后写入 `completed.json`，登记完整快照 ID、清单摘要及数量。已有目录一律拒绝，失败不会推进旧备份。
- 恢复只取登记的完整 ID。先在内存中解密清单并校验摘要、路径，再创建受限暂存；全部校验通过后以 Windows 无覆盖 rename 交付新目录。源目录与目标、仓库不能重叠，8.3 短路径按实际路径判断，异常盘符和尾随点/空格拒绝。
- 暂存和备份目录在创建时设置当前用户专属、禁止继承的 Windows ACL。正常成功及已测试失败会清除本轮暂存与口令文件；该 ACL 不抵御系统管理员。进程被强杀或断电可能留下受限暂存，不能将删除等同于安全擦除。

## 范围与限制

包括 `workspace`、`.qx-private`、宿主会话/KV、分层知识 SQLite、微信路由/去重/待处理文件。设置、登录态、组件缓存和运行记录的排除分类随加密清单保存。仅有增强记忆 `instance.json` 而没有 `database` 时，身份文件排除；一旦存在 `database` 目录，即使为空，整次备份也明确拒绝，等待 PG 冷备及恢复验证。

恢复结果固定标记 `applicationComplete: false` 和 `activation: manual-review-required`，不生成可启动安装身份，不自动启动模型、微信或重放待处理消息。设置和跨机凭据迁移、PG 恢复、桌面按钮及人工激活流程仍待后续实现。当前不处理外部路径存储，不保留空目录/ACL 等全部文件系统元数据；文件上限 20,000、单文件 512 MiB、合计 2 GiB。空间不足会拒绝，但未做真实磁盘写满、断电或大数据压力验收。

固定引擎为已缓存 restic 0.19.1 Windows amd64，SHA-256 `b0dd1fd21eea5d8fe1325f55f7118213c21f36de8a261e04c0624a5ab9fd7830`。每次调用前核对字节摘要；没有新增下载或依赖。此摘要核对不替代独立签名验证或发行准入；引擎尚未随产品分发。

## 源码接口

`desktop/local-backup.cjs` 导出：

```javascript
await createLocalBackup({ data, bundle, python, restic, password });
await restoreLocalBackup({ bundle, destination, python, restic, password });
```

所有文件路径必须是本机绝对路径；`bundle` 或 `destination` 必须尚不存在，父目录应已存在。Python 使用当前应用已有运行环境。口令须为 12–128 字符，不含换行/NUL，由调用方持有并妥善保存；程序不替用户生成仅封于本机的口令。

该文件也接收标准输入 JSON，`action` 为 `backup` 或 `restore`。不要把口令写入命令参数、源码、持久 JSON 或日志。首次恢复预检只通过子进程环境提供口令，清单仅进入内存；后续使用受限临时口令文件。子进程环境不继承模型密钥或已有 `RESTIC_*` 配置，错误输出只保留稳定代码。

`bridge/backup_snapshot.py` 是内部工作进程，不能绕过桌面协调器直接用于正在运行的安装数据；它自身不持有宿主维护锁。旧 `backup-preflight` 仍只是准备检查，不因新入口存在而变为成功备份证明。

## 验证与审阅

全部材料均为合成数据，真实执行固定 restic。目标覆盖 WAL 已提交/未提交边界、源字节保持、外部写入拒绝、当前用户 ACL、SQLite 与多类文件恢复、材料回读、口令错误、丢失仓库数据块、清单登记摘要不符、目标冲突、路径别名和失败清理。实际命令、分母、退出码与源码/日志摘要见[验证记录](checks/local-backup-20261112.json)。

Standards 初审发现引用基目录、时间戳、短路径绕过；复审发现不存在盘符死循环。Spec 初审发现恢复重叠检查过晚、引用基目录和已复核副本漏检。每项都有独立或正式测试的失败证据，修正后由原审阅者复验。两轴结果分别记录，不把重叠发现重复计为不同缺陷。

最终 Standards 未解决 0（初审 3 项、复审新增 1 项），Spec 未解决 0（初审 3 项，其中引用基目录与 Standards 重叠）。完整离线回归为 Node 441 通过/2 跳过、Python 471 通过/1 跳过及 36 子测试；盘符修复后仅 Node 改变，最终完整 Node 442 通过/2 跳过。两次入口均退出 0，未重复运行未改变的 Python 全套。

原测试辅助错误也保留：Windows ctypes 参数类型声明、测试 SQLite 连接未关闭、PowerShell 模块环境、合成脚本引号、运行环境可执行文件硬链接。它们没有被计为旧产品缺陷，也没有冒充功能 RED。

Windows 行为依据：[CreateDirectoryW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createdirectoryw)、[CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)；数据库副本依据 [Python sqlite3 backup](https://docs.python.org/3.12/library/sqlite3.html)。这些是实现依据，实际验证结果以本轮证据为准。
