# CH-07C2c：档案用途的应用入口

沿已批准 v2.1 接续，基线 `3d0e1859041572ed9c574e7a917afd044aedc6bf`。Codex 认领；开始工作区干净，获取远端后 0/0、开放 PR 为空，无活动验证进程。WorkBuddy 本轮 `native_unavailable`，未派发。复用现有私有控制管道、任务队列、预览装配与单次账本，不新建服务或依赖。

## 本片交付合同

1. `domain.py` 增加三个严格 DTO：`MainProfileSelection(request_id, expected_scope, expected_composer_revision, project_intake=False)`；`MainProfileSubmission` 在现有 `AssistantMessageInput` 上仅增加严格布尔 `project_intake=False`；`NativeProfileAuthorization` 沿用主模型原生授权五字段，但 `basis` 为 `MainProfileSendBasis`，固定单次，不接受 max_rounds。业务 DTO 不散落各模块。
2. `POST /api/assistant/conversations/{identifier}/profile-preview` 接收 Selection，仅从数据库当前草稿及档案/接待基线重建，返回现有 `MainProfileSendBasis`。无授权、模型调用、消息、账本或业务写入。用当前配置（无配置或 disabled 拒绝）；使用现有 `build_profile_basis`。回复系统文本由固定协议定义，预览 basis 不声称发送许可。空文、附件、技能、错版本/跨会话、归档/恢复副本拒绝。
3. 私有 `authorize_profile` 接收原生 DTO，同一事件循环内验证会话、数据库权限、活动工作区、配置版本；从当前草稿重建完整 basis 后比较，完整保存计划参与授权摘要；max_calls 固定 1。尚未登记的授权重入也先重核当前保存基线，不能借已有 token 绕过目标变更。已登记同请求只核对原始消息、scope、格式、已存 prepared basis 和摘要后返回 existing，不重新 grant 或生成；不将保存成功后自然推进的当前档案版本误当原始基线。普通/资料格式不得升级。撤销、过期或换配置不得复活旧授权 tombstone。新增实现在独立 `native_profile_control.py`，旧主控制类只接入口；复用私有管道严格操作与回执白名单，禁止新增 HTTP 授权接口。
4. `GenerationTasks.submit_profile` 只接受 MainProfileSubmission，把通用消息字段转回精确 AssistantMessageInput，数据库短事务内 resolve 同一 lease、区分新登记与重放、admit、enqueue_profile；提交后才 dispatch，复用 execute_attempt、取消、关闭与失败释放。不得运行 Jev 或资料检索，不替换旧 submit、submit_context 和 /messages 语义。
5. `POST .../profile-generations` 接收 Submission，经读取 body 前后两次当前权限、同源/CSRF、活动状态核验后调用 submit_profile，202。明确新入口，格式由服务端固定；不接收 policy/许可/原始 patch。新路由放独立 web 模块；旧 generation 入口只注册。不增加新 read 通道，复用按 request_id 找回、attempt、history、取消和 SSE；读操作永不 dispatch。单次登记、等待期间编辑、取消及无法确定的结果仍遵守前片规则。

重放区分：重复 POST 沿既有账本校验，需相同且仍有效的原许可；许可撤销、过期或被替换后拒绝重复 POST。客户端此时用既有 GET 找回，不重新授权或提交。原生 existing 只表示已登记，不代表有新发送许可。此界线保留旧生成入口语义，不增加 POST 读取绕过分支。

## 验证与边界

先失败验证，再实现；仅独立合成 SQLite、私有管道和回环供应商。检查本机授权→HTTP登记→任务完成→档案/接待/回执→历史；二次提交仅一个网络请求；缺许可、普通许可、篡改保存计划/格式、CSRF/Origin、跨用户、旧基线、归档/恢复、队列忙、dispatch 失败、在途撤权/取消均有明确结果。关联回归和四开发门、独立 Spec/Standards 复核保留原始命令/退出码/数量与输入摘要。不同阶段计数不相加。

本片没有桌面 IPC/确认窗及前端调用按钮；待下一片在现有原生确认窗接上用途与保存目标，再接档案侧栏。安装版仍 0.4.1；WIN-PATH-02 仍独立开放。真实供应商、真实资料、云及未下载年份均不操作。验证后更新 README/TODO/TASK_STATUS、正常提交推送并核对远端。


## 2026-10-23 最终验证

CH-07C2c已完成档案用途的后端应用入口：预览重建当前草稿及保存计划，私有管道许可固定一次调用，HTTP登记与原任务队列复用；已登记请求只找回，许可失效后用GET读取，不重发。完整Python回归4,393项通过、0失败/错误/跳过，四开发门通过，558份输入稳定；独立Spec9项、Standards10项通过。实际本机子进程/管道/HTTP合成链验证恰好一次回环调用。桌面用途确认与档案侧栏待接，安装版0.4.1及WIN-PATH-02开放状态不变。 [实测](../testing/profile-application/20261023/README.md)。
