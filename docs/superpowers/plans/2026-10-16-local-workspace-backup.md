# 本机工作区备份实施计划

> 执行：复用 implement 与现有 inline 工作方式，按下面步骤逐项完成；用户已批准范围与无人值守，不再重复访谈。

**Goal:** Windows 中创建可验证的完整加密案件备份，并打开独立只读恢复副本。

**Architecture:** 新增本机维护模块，复用 worker.lock、SQLite backup、严格路径检查和恢复隔离表。独立归档格式；原有 fictional backup 不改宽。桌面只在自有设置页接受口令，通过 stdin 调用冻结 Python 维护模式。

**Tech Stack:** 现有 Python/cryptography/SQLite、Electron/Jinja；不加依赖。

**Spec:** docs/superpowers/specs/2026-10-16-local-workspace-backup.md

## 全局约束

- DTO 仍集中在 domain.py；只在新建目录写入，不覆盖原件或源数据库。
- 固定 scrypt N=32768、r=8、p=1，随机 16 字节盐、12 字节 nonce，AES-256-GCM 16 字节 tag；归档不保存口令。
- 归档/未压缩总量 2 GiB，单文件 512 MiB，文件数 20,000；ZIP_STORED，拒绝压缩、链接、路径跳转和额外条目。
- 新建恢复副本会话全撤销、任务阻断、批准隔离；HTTP 写入只允许重新登录/退出。
- 备份不含独立法库、浏览器缓存、日志、锁、旧升级快照；材料不上传。

## 审查重点

- 并发工作区/写入与读取截面不一致：维护锁和文件二次核验。
- 损坏/伪造归档与 Windows 路径：认证后解包，严格名单、资源上限和结构核对。
- 原件或导出缺失、恢复到新路径：引用逐项核对、历史记录不改。
- 历史会话/批准/任务复活：持久恢复隔离与服务端只读，重启后仍在。
- 原生维护页或设置失效：页面来源验证、管道协议、原工作区不覆盖、密码不落盘。

## Task 1 — 维护引擎

Files: 新增 src/cn_contract/ops/workspace_backup.py；必要 DTO 在 domain.py；tests/integration/test_workspace_backup.py。

- [x] 写完整本机 DOCX/接待/导出恢复以及锁、错误密码、损坏、缺文件、不可覆盖测试，运行真实 RED。
- [x] 实现 create_workspace_backup(root, destination, passphrase, data_parent)、restore_workspace_backup(archive, parent, passphrase)；返回确切报告，不将“已创建”混同“已恢复”。
- [x] 目标 GREEN、补资源/链接/中断边界，保留原 synthetic-only 测试。

## Task 2 — 只读恢复与 Windows 操作

Files: local_server.py、desktop_entry.py、web/workspace recovery routes/banner、desktop main/preload/setup/maintenance、tests。

- [x] 服务端只读恢复模式，旧会话失效、新登录可核对原件/接待/历史导出；写入明确拒绝。
- [x] 维护进程协议及主进程菜单/设置页口令/原生选择器；恢复副本与原工作区切换。
- [x] 开发版实机运行；测试密码错误、文件损坏、取消、返回原工作区。

## Task 3 — 独立审阅与交付

- [x] code-review 双轴审查，以 42ffddc 为基线，复验并关闭实证问题。
- [x] 相关 Python/Node、绑定/依赖/来源门，冻结与安装验证；必要范围全套按仓库要求执行。
- [x] 更新测试记录、TASK_STATUS、Obsidian；仅本地提交，不推送。

验收分母、分段补验与安装限制以 docs/testing/WORKSPACE-BACKUP-20261016.md 和同目录数值汇总为准。
