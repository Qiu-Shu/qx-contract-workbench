# D2f：跨对话收件目标的代际存储底座

基线 `01d5a1a`。沿当前 `codex/contract-review-v2` 和用户无人值守授权推进，保留 AGENTS.md 用户改动；复用已完成的 A—C、D2a—e，不重做旧阶段。此计划兼作本片设计与验收合同。

**Goal:** 保留精确 peer 根映射和全部历史，增加可校验、可升级、可恢复的跨对话目标代际记录；为后续显式切换服务提供不可变证据。

**Architecture:** 仅追加 schema17 `weixin-generations-v1`，不改变原 mapping、grant、poll、descriptor 和 dispatch 表。当前没有正式对话 rebind 服务，本片的新目标限定为同 owner/workspace 的另一已有 CID 及其 synthetic task binding；不声称律师已能在页面转案。无追加服务、HTTP 写入口或自动生成代际。

**Tech Stack:** 现有 Python、SQLite、SQLAlchemy、Pydantic 与加密 qxbak，无新增依赖。

## 取舍与边界

直接改 mapping 会丢失历史并违反原唯一键/不可变约束；放宽 D2d 的 same-target 则会让旧 accepted 借新 scope 投递。本片采用独立代际表，保留 D2d 的五目标身份与单调版本约束。

裁决：新代际尚无运行解析器，因此存在代际记录的整个账号暂停 poll、dispatch 和 scope refresh（包括其他 peer），旧相关 find 也可被现有 mapping guard 拒绝。完整备份可验证旧文本不等于运行入口可继续读取旧文本。账号/peer 永久撤权仍可执行。此限制只影响非空代际账号；产品尚无入口生成这些记录。下一片实现显式原子切换与按代际授权后再解除这项临时限制，不能先用新 scope 解释旧消息。

真实微信资格/身份、账号登录、网络/下载解密/发送、产品真实模型、付费、真实合同外发、签发、安装包及生产验收均未启用。安装版0.4.1、原生长进程崩溃和 WIN-PATH-02 保持开放。

## 存储合同

`weixin_peer_generations` 14列：id、root_mapping_id、generation、request_id、actor_id、task_binding_id、scope_json、scope_sha256、previous_generation_sha256、previous_scope_sha256、checkpoint_revision、created_at、reason、generation_sha256。整行不可 UPDATE/DELETE；root/generation、root/request、目标 task binding 唯一；FK 指向原根 mapping、users、task binding。除首代 previous_generation_sha256 外字段非空。

集中 DTO `WeixinPeerGeneration` 只在 domain.py 定义，scope_json 对应 scope；严格正整数 generation、非负 checkpoint、UTC、完整 scope/hash，理由复用已有有界校验。generation=1 当且仅当 previous_generation_sha256 为 None；generation_sha256 绑定其余完整规范 JSON 字段。JSON scope 必须规范表示，UUID 必须规范，不能只校验 hash 格式。

历史必须满足：

- root/account/user/目标 binding/目标 conversation 均存在，同 owner、同真实 workspace；synthetic binding 对应精确新CID。
- 目标不是原 root CID、前代 CID，也不得复用任何原 mapping 或其他代际占用的 binding；不同 CID 的 input/material revision 不与旧 CID 比大小。
- 每 root generation 从1连续；首代 previous_scope_sha256 取当时 D2d 有效 scope，后代取前代 scope；后代 previous_generation_sha256 精确连接前代完整摘要。
- created_at 严格晚于 root、目标 binding/对话、前代和该账号所有既存 poll/dispatch/grant 活动；首次代际之后不得有该账号 poll/dispatch/grant，后代和永久撤权可保留。
- checkpoint_revision 精确对应创建时账号 poll 边界；不可在 account/root 已撤权后创建，时间不能靠不同 UTC 字符串排序。
- 用现有历史 scope 验证器核对目标存在、owner/workspace、版本、时间和目标引用；不把当前成员资格冒充过去事实。所有历史回执、原 payload 和摘要均保持原值。

## 实施与验证步骤

- [x] 先新增 DTO、schema、历史损坏及运行阻断失败测试，保留命令、退出码和 RED。
- [x] 最小实现 generation_schema / generation_integrity，追加 schema catalog/bootstrap/迁移，保留32个前驱 native/non-native 固定摘要；三个旧微信 validator 在新版本仍执行。
- [x] ops 完整性 hook 与两类恢复 fence 接续 `weixin_generation_enabled=false`；普通归档拒绝非空代际，完整 native qxbak 可保留但恢复不能执行。
- [x] 当前 account active / mapping guard / 旧CID投影接账号暂停；恢复、撤权、归档状态优先于 target_changed；零代际行为保持。
- [x] 独立合成测试覆盖两代链、D2d前置grant、篡改重算摘要仍拒绝、跨owner/workspace/binding占用、checkpoint/时间/撤权、SQL不可变、迁移三路径、真实两次qxbak恢复、恢复只读及相应样本零run；不把直接SQL样本称运行切换。
- [x] 根代理执行关联回归及四开发门，独立冻结复核代码与证据；814不同Python、192 Node通过。额外浏览器WinError5失败如实保留；全仓/安装版/真实账号未运行标 NOT_RUN。
- [x] 只提交本轮授权源码、文档和独立合成样本，fetch 后正常推送并比对远端 SHA 与递归文件树；产品6e36cb5及5,073条目一致，[回执](../testing/weixin-generations/20261024/github-sync.md)。

HumanLayer回读、Obsidian成功回执与TencentDB Stop按当前AGENTS逐轮收尾，实际成功/待同步状态见本聊天本轮最终答复；不能以GitHub推送代替记忆成功。

## 文件与审查焦点

产品：domain.py、storage_schema.py、schema_migrations.py、storage_bootstrap.py、weixin_inbox/generation_schema.py、generation_integrity.py、accounts.py、conversation.py、integrity.py、dispatch_integrity.py、grant_integrity.py、ops/backup.py、workspace_backup.py，以及旧assistant/task六族版本gate。测试：新 generation DTO/schema/integrity、backup/guard 模块及既有 D2d/D2e/任务/升级/恢复关联模块；4处旧schema/workspace夹具补后继兼容。没有前端布局变动。

审查特别检查：旧版指纹或validator被漏接；新目标 scope 反向授权旧文本；跨两表 binding 占用；时间格式造成顺序误判；零代际旧用户行为被破坏。测试与实现具体命名、命令、实际数量和偏离在阶段证据中记录。
