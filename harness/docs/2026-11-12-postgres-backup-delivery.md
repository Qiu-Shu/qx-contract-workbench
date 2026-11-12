# 增强记忆 PostgreSQL 冷备与隔离恢复

2026-11-12，接续 `58a4350ea87d2b1295d1d89f7af8f436dbe13487`，完成[本轮计划](2026-11-12-postgres-backup-plan.md)的源码接入。此前[本地业务快照](2026-11-12-local-backup-delivery.md)对 PostgreSQL 数据一律拒绝；现在可在提供已核验组件、正常停库且通过离线检查时纳入加密备份。未构建安装包、更新安装版、读取真实业务数据库或调用真实模型。

## 已实现

- 继续使用宿主维护锁、Windows 文件冻结、当前用户受限暂存和独立 restic 仓库；将完整 `database` 与 `instance.json` 一并加密保存。数据库目录全部按原始字节复制，不根据其中的文件扩展名转换 SQLite。数据库身份与口令文件不进入公开完成回执。
- 新清单保存全部目录，包括空目录；恢复时要求目录集合一致。旧的不含目录清单的非 PG 快照仍可读取，PG 快照必须有目录清单及数据库身份元数据。
- 固定摘要的 `pg_controldata` 确认 PostgreSQL 18、控制/目录版本及正常停库，`pg_checksums` 检查启用的页校验和。额外核对控制文件所指 WAL 段的长度、集群身份和块大小，并以固定 `pg_waldump` 检查 shutdown checkpoint 的位置、类型、REDO、时间线及记录校验和。
- 残留进程标记、恢复标记、外部表空间、缺失身份、不支持版本、缺少工具或数据损坏均拒绝。完成回执新增 `postgresIncluded`；恢复再执行同样的离线校验后才交付新目录。未提供 PG 工具时，PG 恢复在写入明文暂存之前拒绝。
- 产品备份/恢复过程只使用离线读取工具，不启动数据库、不执行恢复目录的配置、不自动修复文件。正常成功和本轮覆盖的失败路径均清理暂存。

## 实际验证及问题闭环

固定 PostgreSQL 18.1 / pgvector 0.8.5 建立独立虚构数据库：两个合成分组各 20 条记录、中文文本、一次回滚事务及 HNSW 向量索引。经实际 restic 加密备份和新目录恢复后，只在测试夹具中启动恢复数据库，核对 40 条记录、回滚数据不存在、集群身份和身份文件字节一致；检查索引存在、有效且就绪，并由执行计划及实际最近邻查询确认索引被使用。两个分组是合成表数据，不代表 Hindsight bank API 验收。源 PG 文件在备份前后摘要一致。

目标 PG 集成测试 7 项通过；快照 Python 8 项通过。最终完整 `npm test` 退出 0：Node 449 通过/2 跳过，Python 472 通过/1 跳过及 36 子测试。实际命令、退出码、源码和日志摘要见[验证记录](checks/postgres-backup-20261112.json)。原生 PG 集成测试要求 Windows 及显式提供 Python、restic、PG 工具；未配置会跳过，本机本轮已实际运行。

独立 Standards 初审发现 P1：页校验和不能识别缺失的启动必需 WAL。公共入口失败测试复现后增加上述 WAL 检查，覆盖缺失、全零、外来集群身份及 checkpoint 内容损坏；原独立探针复验已拒绝，未解决 0。Spec 初审发现 P2：仅看向量查询结果不足以证明索引恢复。增加索引元数据及执行计划检查，独立删除索引探针实际失败，未解决 0。另有本轮自查发现的 PG 目录内 `.db` 普通文件误判，保留失败日志并修复。

辅助错误与业务失败分开记录：最初 pg0 合成启动出现 UTF-8 错误；测试 pg_ctl 子进程继承输出管道导致等待超时；独审临时口令 ACL 与损坏库启动后的短暂日志占用。这些不计为生产功能缺陷，不用修复后的结果覆盖原始失败。

## 工具来源与使用

复用项目已锁定的 `pg0-embedded==0.15.2`，本轮从锁定来源下载 wheel，核对 SHA-256 `1b47c938991243d938e28c7e1998c1298637fdb15c54ada6d853e02769d50d3e` 后提取；没有升级依赖。PG0 可执行文件摘要及 3 个只读工具、29 个 DLL 的逐文件摘要保存于[固定清单](../config/postgres-backup-runtime.json)。产品入口不下载组件，不把本轮验证视为组件签名或产品分发验收。

源码接口延续原参数，增加 `pgTools`：

```javascript
await createLocalBackup({ data, bundle, python, restic, password, pgTools });
await restoreLocalBackup({ bundle, destination, python, restic, password, pgTools });
```

`pgTools` 是包含 `bin` 的固定 PG 安装根目录；所有路径为本机绝对路径。没有 PG 数据时仍可省略。口令继续通过调用接口或标准输入传递，不能放进命令参数或持久日志；其他路径/口令约束沿用上一阶段。

核对固定上游源码发现 pg0 0.15.2 不识别现有应用设置的 `PG0_HOME`，程序缓存实际落在用户目录 `.pg0/installation/18.1.0`。本轮仅提取并使用该程序缓存，合成数据库保持独立；未读取或迁移用户的全局实例注册，也未修改当前运行产品的启动逻辑。该问题是后续启用流程的前置事项。

## 完成边界与下一步

恢复仍固定 `applicationComplete: false`、`activation: manual-review-required`。本轮证明受限版本的引擎级冷备及合成恢复；没有证明 Hindsight 数据迁移/API/模型语义、跨机启动或所有可能损坏均可识别，也不支持运行中热备、外部表空间或未启用页校验和的集群。文件上限仍为 20,000、单文件 512 MiB、合计 2 GiB；目录最多 20,000。不保留完整文件系统 ACL/全部元数据，断电、真实磁盘写满、大数据压力仍待验。

下一步接续设置及凭据迁移设计与实现，处理 pg0 实例注册/启动路径，再做人工确认的启用流程及桌面入口。恢复不会自动启动模型、微信或重放待办；安装包继续暂缓。

实现依据：[PostgreSQL 文件备份](https://www.postgresql.org/docs/18/backup-file.html)、[pg_controldata](https://www.postgresql.org/docs/18/app-pgcontroldata.html)、[pg_waldump](https://www.postgresql.org/docs/18/pgwaldump.html)、[固定 18.1 WAL 头布局](https://github.com/postgres/postgres/blob/REL_18_1/src/include/access/xlog_internal.h)、[pg0 v0.15.2](https://github.com/vectorize-io/pg0/tree/v0.15.2)。源码核验和本轮实测是不同证据，完成范围以上文及验证记录为准。
