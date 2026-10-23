# CH-07C2d 桌面用途确认：独立计划复核

2026-10-23；基线 d3c3b173af0fe3f3f0d878df6793a601e181d081。只读核对 `docs/plans/2026-10-23-profile-desktop.md` 与现有 domain、profile preview/native control、profile 合并/保存、Electron control/session/approval/window 接口。使用 CodeGraph 定位并读取实际源码；记忆检索未提供更近的接口事实。未修改产品、未跑测试，不是运行通过证明。

受审计划 SHA256：`7117ad8866d6155ecb51aeae4230c682c988d6700922c74afbd799617aadcd47`（计划可能由统筹后续修订，本报告针对该版本）。

## 结论

缩小范围成立：可信 desktopAssistant.authorizeProfile → 主进程重读计划 → 原生窗口 → 私有管道 ACK，是有独立行为和拒绝条件的完整授权入口切片。无需为本片增加永久并列按钮、renderer 提交状态机、SSE 或档案侧栏；这些是后续统一页面工作。不得将本片完成描述为“聊天自动建档已经接通”。

接口数目正确：MainProfileSendBasis 为 17 字段；ScopeSnapshot 为 7 字段；私有 authorize_profile 为 5 字段；页面选择为 5 字段；profile modal details 为 6 字段。format/template/purpose/handler/version 与现存 Python 合同一致。scope_kind=intake 时目标 id 必须等于 scope_ref；target id/revision 同空或同非空。project_intake=false 时仍可能有已有 target 基线，不能以有 target 推导会写接待。

## 一处必要的合同精确化

第 4 条的“主进程确认前后核对……无附件/技能”中，“重读当前页面无技能选择”没有对应数据接口：

- `domain.AssistantDraftInput` 只有 scope/composer/content；`AssistantConversationView` 不存页面当前技能选择。
- `web/static/assistant-state.mjs:createDraftController` 中 `state.skill` 是 renderer 状态。
- `web/assistant_profile_generation.py:preview` 构造 AssistantMessageInput 时 requested_skill 缺省为 None；`profile_preparation_service.build_profile_basis` 确实拒绝传入 message 带技能，但此 preview 并未读取页面 state.skill。

建议将该条明确为：主进程重读草稿与已选附件；该档案入口固定文字协议，不接受技能字段，服务端仍拒绝带技能的 profile-generations 提交；后续统一页面负责技能选择与此用途的交互互斥。不增加虚构的 draft.requested_skill 字段，也不依靠 renderer 自报技能作为权限证明。这是文档表述修正，不要求扩大本片接口。

## 保存说明与验证应保持的界线

1. 六字段 modal 可准确表达意图。`project_intake=false` 显示本次不投影接待；true 且已有目标显示目标版本；true 且无目标只能说“有可投影字段时形成接待草稿”，不能保证一定创建。`profiles.merge_profile`、`profile_store._commit` 对无变化有明确分支。
2. 预算沿既有原生文字：本机预留，不保证供应商实际费用。保护律师更正是既有合并规则，不应扩大成“自动确认事实”或绝对不会产生冲突。
3. authorized/existing 应在 lease 方法、withAuthorization 和 IPC 三处保留真实 ACK 区分；existing 不新 grant、不撤销未由本次新增的许可。后续页面 GET-only 找回要求继续保留，本片没有页面提交按钮不能据此声称已测页面恢复。
4. 新鲜授权/取消实机路径应保持模型 POST、message、attempt、output、handler 和 profile/接待版本新增均为零。若独立 existing 夹具有事先登记数据，核对计数不变，不与新鲜路径零数混用。原生授权本身不是模型执行或保存成功。
5. 验收复用现有 actual-main observer、中文合成目录、modal、私有管道，增加 profile 模式即可；原 plain/context/Jev Node 兼容回归仍覆盖共享抽取。窗口归属、恢复目录、iframe/HTTP 页面拒绝、前后 token/草稿/profile/intake/config 漂移及 awaiting_input 等活动状态需要明确目标断言。
6. 新增模块纳入 package.json 白名单；不要求本片重复此前 4,393 项 Python 全套或安装替换 0.4.1。Windows 原生实测、Node 假窗口、已有 Python 合成链的结果必须分别表述。

除上述第 4 条的精确化外，未发现本片必须扩范围才能解决的设计阻断。待源码冻结后另作 Spec 实施复核。
