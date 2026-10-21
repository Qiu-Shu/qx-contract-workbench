# CH-06B2b2：资料辅助发送闭合切片实测

本机 Windows，基线 `09db5f666305e2e048012b1d3655c742ed110c7b`；2026-10-21 北京时间实施。只用独立合成数据及 127.0.0.1 回环 HTTP，没有真实模型调用或真实资料处理。

## 已完成范围

- **schema `assistant-context-v1`**：`assistant_model_attempts` 增加不可变 `input_format`（CHECK 限定 `plain-text-v1`/`library-context-v1`，旧行迁移为 plain）；新建有序关联表 `assistant_model_input_citations`（attempt_id+ordinal 主键、attempt_id+saved_citation_id 唯一、FK、ordinal 0–7、禁止 UPDATE/DELETE）；替换 immutable input trigger 纳入新列。新建库先建 V1 再跑同一 ALTER，冻结 library-v1 摘要不变，旧 0d53fdf 代码实际拒绝新结构。
- **登记与生命周期**：`enqueue_context` 在同一 begin_nested 完成 message/run/attempt/有序关联/预算/reserved event；同 request_id 幂等重放并逐项比对内容、范围、格式与 citation 顺序，任一变更即冲突；claim/settle/read/history 按持久化格式分派，缺失或未知格式一律视为损坏。上下文分支零 Jev 预留、零 Jev 调用。
- **原生一次许可**：`NativeModelControl.authorize_context` 从持久引用与当前草稿服务端重建 manifest/basis，客户端 basis 仅命名待重建内容，完全相等才授权；策略 `allowed_content_sha256s=(manifest_sha256,)`、max_calls=1；registry 租约显式区分两种 basis，context 许可拒绝普通文字，反之亦然；传输预检在密钥读取前后各核验一次。
- **归档恢复同一 seam**：`context_integrity` 纯校验（清单/关联/持久引用哈希/同 scope/输出引用子集），`model_integrity` 按版本+行格式分派；attachment/judge/library integrity 白名单加新版本；恢复走既有 quarantine/fence/recover，不重建许可、不重发。
- **应用入口**：`POST /api/assistant/conversations/{id}/context-generations`（202）经 `GenerationTasks.submit_context`；请求体无 input_format 字段，格式由可信入口固定。

## 验证结果

| 检查 | 本轮实际结果 | 原始证据 |
| --- | --- | --- |
| 本片目标 Python | **120 passed，1 个预存在环境失败，exit 1**；8 个测试文件，含本片新增 75 项（schema 36、send 14、native 7、backup 16、routes 2）；266 秒 | [日志](target.log)、[XML](target.xml) |
| 唯一失败归属 | `test_preview_stays_blocked_after_backup_restore` 在本机抛 `FILE_LIMIT_OR_LINK`；git stash 到基线 09db5f6 同机同参数复现同一失败，与本片改动无关（见下「预存在环境失败」） | target.log 与基线复验记录 |
| 四项工程门禁 | schema --check、verify_defaults、verify_sources、verify_runtime_dependencies（development）均 exit 0 | [门禁1](gate-1.log)、[2](gate-2.log)、[3](gate-3.log)、[4](gate-4.log) |
| 原生回环字节 | 一次真实资料辅助回答：回环服务器收到的请求体字节与不可变登记的 wire 逐字节相等；候选引用合法、费用 estimated、重放不再发送 | target.log 中 test_native_context_control.py |
| 升级与备份恢复 | 冻结 library-v1 摘要不变、三入口结构相等、中途失败原子回滚；context 五状态 roundtrip、9 项损坏矩阵、恶意归档恢复拒绝、撤权会话后历史仍合法 | target.log 中 context_schema/context_backup |
| 全套回归 | **3450 passed，51 failed，2 skipped，3819 秒**；51 个失败全部位于 qxbak 备份/恢复家族（17 个既有测试文件），全部归因于下述预存在环境问题，与本片改动无关 | [摘要](full-suite-summary.log)（仅尾部 40 行） |

## 失败与修正记录（本片开发过程，全部保留）

- `model_integrity.validate_model_records` 曾未把新版本纳入白名单且未向 `_validate` 传 context_schema 标志，导致所有版本校验被 TypeError 吞成 ASSISTANT_MODEL_INTEGRITY；修复后旧版本行为经回归复验。
- `_replay` 曾只比对消息 digest（不覆盖 citation_ids），改引用重放不被发现；现要求持久化有序关联与重提完全一致。
- `enqueue_context` 曾先 build_basis 后授权，配置禁用时抛 CONTEXT_INPUT_INVALID 而非 BLOCKED_LIVE；授权已前移（codec 新增 manifest_digest），原生 authorize_context 保持先查配置。
- `DeepSeekContextProvider.generate` 更名为 `generate_context` 与生产 provider 及租约分派统一；registry 要求注册 provider 具备普通 generate，故 native e2e 改用生产形态 DeepSeekProvider 回环。
- 测试自身两处反模式已修：`asyncio.run(execute_attempt)` 不得置于打开的 session 内（BEGIN IMMEDIATE 持锁致 database is locked）；任务管理器测试须先 `await finished(tasks)` 再 close，否则任务被取消属预期取消而非完成。
- 单引用 fixture 下反转 citation_ids 是恒等操作，改用随机 UUID 替换来检验冲突。

## 预存在环境失败（基线同等复现，非本片回归）

51 个全套失败与目标切片唯一失败同属一类，机制已定位到本机两个环境事实的叠加：

1. **nlink 假阳性**：本机经 `\\?\` 扩展长度前缀路径 `os.link`+`os.unlink` 后，源文件确已删除（exists=False），但 `stat` 对剩余硬链接仍报 nlink=2（普通路径执行同样操作则正常报 1）。自昨日 WIN-PATH-01（`e387d8c`）把产品路径统一改为 `\\?\` 前缀后，本机发布的每个 qxbak 归档都携带陈旧的 nlink=2，`workspace_backup._reader` 的防链接检查随之拒绝恢复刚发布的归档（FILE_LIMIT_OR_LINK）。git stash 到基线 09db5f6 同机同参数复现 16 个代表项全部同等失败；WIN-PATH-01 当时仅跑 424 关联测试与「下载副本后恢复」（副本 nlink=1），未覆盖「本机发布后立即恢复」路径。
2. **WorkBuddy 安全删除 shim**：`sitecustomize.py` 回收站拦截对超深 `\\?\D:\` 路径抛 Errno 53（找不到网络路径），令两个合同长路径备份测试在 shim 下以 OSError 失败；去掉 shim（`python -S`）后这两项仍因机制 1 失败。

本片新备份测试采用「复制归档后恢复」（字节相同的副本是新目录项、nlink=1），不削弱任何产品检查即在本机跑通完整信任边界。机制 1 疑似 WIN-PATH-01 引入的本机真阳性/假阳性交界问题，建议另立后续片（如 WIN-PATH-02）由产品与系统层面定论；本片不扩大范围。

## 复现与边界

正式测试用项目 `.venv/Scripts/python.exe -X utf8 -m pytest` 加上述 8 个文件运行；选新的短 D 盘 basetemp，`-o junit_family=xunit1`。真实账户、真实供应商、律师选片 GUI、Electron/冻结安装器均不在本片；安装版仍 0.4.1，Jev 真实预算仍未配置、功能仍关闭。旧 V1 编码/字节/权限语义由固定样例对照与历史共存测试证明不变。

[本片执行计划](../../../plans/2026-10-21-context-send.md)；[存储与接线设计](../../../plans/2026-10-20-context-send-storage.md)。GitHub 同步结果以独立回执为准。
