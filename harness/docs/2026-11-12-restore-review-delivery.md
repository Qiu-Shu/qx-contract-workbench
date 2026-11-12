# 配置保留、恢复审核与启动保护

2026-11-12，接续 `c6d99112188ea110f2f158996b0876384ee7294c`，完成[本轮计划](2026-11-12-restore-review-plan.md)的源码实现。恢复副本现在能保留三类配置原文，给出有限偏好及重新授权清单，并在普通启动入口阻止误用。实际启用流程仍未实现，不能把本轮称为完整换机迁移。未构建安装包、更新安装版、读取真实业务或调用真实模型。

## 配置如何保留

在已有维护锁、源文件冻结、当前用户受限暂存和 restic 加密备份内，选择下列已知配置。恢复时只写入待审核目录，不放回程序自动读取的位置。

| 原数据目录内路径 | 恢复后的待审核路径 |
| --- | --- |
| `.local/desktop-data/locale.json` | `.qx-restore-review/settings/desktop-locale.json` |
| `.local/dsh-home/profiles/web/cordis.patch.yml` | `.qx-restore-review/settings/harness-profile.txt` |
| `.local/dsh-home/qx-wechat/prefs.json` | `.qx-restore-review/settings/wechat-preferences.json` |

注册表位于 `config/backup-settings.json`，备份准备、快照与审核共用。文件不存在时不强行创建；存在时要求普通单链接文件且每份不超过 1 MiB，否则拒绝备份，避免静默遗漏。内容按原始字节保留，包括无法解析的旧配置。模型凭据库、微信登录态及任意插件/自定义代码没有因此纳入复制，其余设置仍按原范围清单分类待审。

配置原文可能包含秘密、命令或旧路径，所以仅保存在加密仓库及当前用户受限的恢复目录，不输出到完成回执或审核结果。恢复目录中的文件是明文，受本机访问控制保护；这不是可公开分享的脱敏包。

## 只读审核和启动保护

新增 `reviewLocalRestore({ destination, python, pgTools })`，也可通过 `desktop/local-backup.cjs` 的标准输入 JSON 使用 `action: "review"`。路径须为本机绝对路径；包含 PG 时须提供上一阶段固定工具。审核已恢复目录不需要备份口令，也不启动 restic 或 PG。

```javascript
const { reviewLocalRestore } = require('./desktop/local-backup.cjs');
const review = await reviewLocalRestore({ destination, python, pgTools });
```

审核冻结目录及文件，重新核对清单、字节摘要、目录、SQLite 和适用的 PG 离线检查，再输出以下内容：

- 配置类别及有限建议值：桌面语言只允许 `zh`、`zh-CN`、`zh-TW`、`en`、`en-US`；微信只识别 `format: plain/raw` 和 `delivery: whole/stream`。所有建议都没有自动应用。
- 模型 API 密钥、微信登录及其他 profile 秘密须重新授权。任意 profile 不执行、不自动迁移路径；自动回复与桌面控制等权限不从旧配置恢复启用。
- 设置审核、重新授权和尚未实现的启用流程保持阻断；存在待处理记录时增加待办审核，有 PG 时增加实例登记及 Hindsight API 验证。

结果始终为 `activation: "blocked"`、`applicationComplete: false`。`verified: true` 仅表示当前副本通过完整性检查，不证明外部来源可信、业务就绪或已批准启用。旧版不含 `settings` 字段的备份仍兼容。

桌面启动、普通安装初始化和独立增强记忆入口共用保护：发现根目录 `backup-manifest.json` 或 `.qx-restore-review` 就在初始化写入前拒绝启动，即使标记内容损坏也不能绕过。该保护防止正常入口误用；不是抵御同一用户主动删除标记或修改代码的安全边界。本轮没有提供删除标记即激活的接口。

## 验证与独立复核

实际 Windows/restic 合成测试覆盖三份配置逐字保留、凭据及登录态排除、秘密/旧路径/命令不进入输出、有限建议值、损坏拒绝、写句柄占用拒绝、超限及硬链接拒绝、初始化和记忆启动阻断。已有 PG 恢复测试增加离线审核与未自动启动检查，随后仍由测试夹具验证 40 条虚构记录及 HNSW 索引恢复。

独立 Spec 复核最终 0 项未解决：另验无效 profile 字节、审核前后文件摘要和修改时间一致、旧清单兼容，以及通过 Electron 替身触达桌面入口的写入前阻断。初次替身缺少 `QX_PAYLOAD_ROOT` 导致探针退出 1，补齐测试环境后退出 0；这项辅助错误没有算作产品失败测试。

独立 Standards 发现 1 项 P2：源码覆盖流程没有带上新增配置 JSON，复制后的 Python worker 无法载入。已补齐两个备份配置文件的覆盖与来源摘要登记，实际执行复制后的 worker 通过；原探针独立复验退出 0，最终未解决 0。这里只验证复制函数及 worker，不代表已执行完整暂存、构建或安装器验收。

新能力首次测试因配置计数缺失而失败；写占用反例也先失败，随后加入整个审核期冻结。失败原日志与修复结果均保留。目标测试先后 23 项、5 项通过；两组覆盖不同代码阶段，不能相加当作独立测试总数。最终完整 `npm test` 退出 0：Node 453 通过/2 跳过，Python 472 通过/1 跳过及 36 子测试。实际命令、退出码与摘要见[验证记录](checks/restore-review-20261112.json)。

## 后续事项

下一步处理 pg0 全局实例登记与启动路径，在隔离数据上验证 Hindsight 业务迁移/API；随后实现设置实际应用、待办处置、重新授权和人工激活，再接桌面入口。断电、磁盘写满、大数据及跨机验证仍待办。安装包继续暂缓，现有安装版未改动。
