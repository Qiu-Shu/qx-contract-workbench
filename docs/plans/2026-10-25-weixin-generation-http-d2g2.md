# D2g2 代际追加的本机 HTTP 入口

基线 aa20028；沿现有 D2g1 原子服务实施本片。用户已批准无人值守增量实施与正常 GitHub 同步。账号收件仍暂停，不改 schema17、历史解释或运行时分发。

## 接口与边界

原始根会话路径 `/api/assistant/conversations/{cid}/weixin-authorization` 下新增 POST `/generations` 和精确 GET `/generations/by-request/{request_id}`。不允许 body 选择 root/account/actor；新目标由既有八字段 `WeixinPeerGenerationInput` 指定，expected_scope 的 CID 是新目标。新目标路径不反向搜索旧 root。

复用当前身份、同源、CSRF、有界严格 JSON；POST 在解析前后均重新检查根会话权限、恢复 fence、归档及账号/root 撤权。独立 generation 写上下文允许已有 generation，保留 refresh 原有暂停限制。最终由 D2g1 服务在 BEGIN IMMEDIATE 内重新核当前 root、前代、新目标权限和完整 CAS；不复制事务逻辑。

集中 `WeixinGenerationReceiptView` 仅返回 mode=synthetic、state=history_only、generation、request_id、scope、scope_sha256、previous_generation_sha256、previous_scope_sha256、checkpoint_revision、created_at、generation_sha256。不返 root/account/peer/actor/自由 reason/消息/下载信息。scope 摘要与首代前驱关系须自洽；generation_sha256 是完整底层记录的固定凭据，不声称可从删减投影重新计算。

GET 复用固定查询；恢复、逻辑撤权、会话归档或 scope 增长不使历史消失，但当前根和固定目标对象权限仍核。命中返回投影，未知请求或未绑定会话返回 null；成功查询不写业务表/审计，拒绝可沿现有机制记审计。恢复白名单只增加精确 GET 路径，所有写方法仍 409。

## 执行与验收

- [x] 先新增 DTO、实际 HTTP 连续两代/幂等/旧 CAS/严格输入/当前权限/隐私失败测试，根50/独立14 RED均0 setup errors；独立测试恢复、解析期间撤权和丢 ACK。
- [x] 最小实现集中投影、CID wrapper、两路由及精确只读白名单；不增加 head/UI 或隐式收件切换。
- [x] 根代理运行新增与关联服务/恢复/旧授权10模块241不同Python、192 Node和四开发门，独立Standards/Spec审阅实际diff；[实测](../testing/weixin-generation-http/20261025/README.md)记录命令、退出码、数量及源码摘要。
- [x] 更新 README/TODO/TASK_STATUS 和实际证据，仅暂存本片40文件；fetch 后正常提交推送00f17bb，远端 SHA/tree及5,152条目一致；保留用户 AGENTS.md 改动，[同步回执](../testing/weixin-generation-http/20261025/github-sync.md)。

每轮最终答复前另按AGENTS实际检查 HumanLayer 回读与 Obsidian 保存成功回执；TencentDB 使用 Stop 自动入队，不把全局队列冒充本轮成功。记忆成功与否以当轮实际工具回执为准。

全仓、安装版、真实微信/模型/合同/付费/签发/外发均 NOT_RUN；原生崩溃与 WIN-PATH-02 保持 OPEN。最新 CAS head/明确桌面操作、按代际接收分发、可信绑定和 E 有限期许可另片实施。
