# WIN-PATH-01 合同原件长路径修复

基线 `7446a9ce47d9452568f7d2ea1cf53c92167d53f4`；Codex 认领。2026-10-20 完成所列原件/qxbak源码范围实测和独立复核，安装版仍为0.4.1。

本片修复前片已实际复现的 Windows 深中文目录旧合同原件创建失败。优先复用 `ops/file_paths.py`，在文件 I/O 使用扩展路径，在逻辑引用、DTO、数据库 URL 和返回值保留普通路径。沿现有 `persistence` 原件生命周期修正创建、读取和事务清理；不改数据库结构、依赖、系统注册表或已安装的 0.4.1。

验收顺序：

1. 新增原件创建/读取与独立 DOCX 上传备份集成测试，保存有效失败证据。
2. 最小修复并覆盖根回滚、嵌套事务、关闭会话、写入/同步/审计/提交失败及已有原件不覆盖；核对逻辑引用不变。
3. 同份合成 DOCX 经长路径导入、qxbak、长路径只读恢复、HTTP 原件下载及再备份恢复，保留 SHA、权限和引用；硬链接/越界仍拒绝。
4. 定向旧流程回归、四开发检查、独立 Spec/Standards 复核；WorkBuddy 本轮单独检查连接并只读复核，失败不自动重派。
5. 更新 README、TODO、TASK_STATUS 及可共享证据；正常推送现分支并核对远端 SHA。真实材料、运行库和缓存不上传。

范围：qxbak 是现有工作区备份交付链。旧 cnbak 的任意长目录读写、实际 UNC 网络共享、超长 SQLite 数据库路径和新的安装包不自动视为已验；根据本轮实际测试记录。CH-06B2b2 资料发送方案仍待接续，本片不改变主模型/Jev 许可或开启资料外发。

依据：[此前实机诊断](../testing/context-preview/20261020/path-diagnosis.md)、[调用链复核](../testing/context-preview/20261020/long-path-readiness.md)、[v2.1](chat-first-architecture-v2.1.md)。

## 执行结果

有效RED后仅修改persistence.py：I/O处复用现成helper，普通路径和相对引用不变。目录独占创建保持在取得清理所有权之前，避免错误删除预存目录；没有为清理空父目录递归删除共享目录。20新增单元覆盖写入/flush/fsync/chmod/审计/commit、root/nested/close、碰撞、篡改和越界；3新增集成覆盖真实合成DOCX、qxbak及只读恢复、再备份和边界。

最终424关联测试全通过、493输入稳定，四开发检查exit0；Spec4与Standards4独立通过，0待修发现。实际Windows源码HTTP16请求通过原件279/282字符父目录的完整链，模型/Jev0、3服务结束。WorkBuddy本轮只读3文件completed；未将静态意见当运行结果。TCP首轮一次10054复位未确定原因，原失败、20次定向409及完整重跑通过全部保留；没有靠修改产品放宽恢复保护。[完整证据](../testing/contract-long-path/20261020/README.md)。

未改变数据结构或安装环境；实际UNC、超过260字符SQLite文件、旧cnbak任意长目标、GUI/冻结/安装器和总体资源目标不在本片验收结论内。接续CH-06B2b2，保持原账户、外发、云与真实资料边界。
