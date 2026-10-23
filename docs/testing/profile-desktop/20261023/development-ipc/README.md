# CH-07C2d IPC 作者证据

2026-10-23；workspace `D:\Documents\ChatGPT\律所项目`；基线 `d3c3b173`，分支 `codex/contract-review-v2`。仅合成材料，未调用真实模型、未外发、未提交或推送。

## 本分工完成

- 新 `profile-approval.cjs` 严格核验五字段选择，使用共享 HTTP/cookie/guard 重读草稿、材料和直接返回的 profile basis；前后比较完整 canonical basis，包含本机保存基线、目标及用途。
- 新 `desktop:approve-profile` 并入既有选择审批编排，复用 pending/busy/runtime/window，保留 plain/context 返回兼容；档案分支只返回可信 `authorized` 或 `existing`。
- `desktopAssistant.authorizeProfile` 固定转发专用 IPC；不接普通聊天按钮。
- 专用测试覆盖完整 scope、17 字段 basis、预览封套拒绝、取消、状态漂移、终态、cookie 更换、回执、existing 清理、共享锁与 preload。
- 新档案入口仅接受无附件文本，拒绝非空 `materials.items` 和 `materials.attachments`。当前草稿 DTO 无页面技能状态字段；严格 IPC 及 preview body 均不接受技能，历史已完成技能 run 不算本次技能选择。

## 实际命令及数量

|证据|命令|退出码|实际结果|
|---|---|---:|---|
|red.log|`node --test desktop/tests/profile-approval.test.cjs`|1|45 tests，0 pass，45 fail；44项断言档案 IPC 未注册，1项 preload 档案方法不存在|
|green-first.log|`node --test --test-reporter=tap desktop/tests/profile-approval.test.cjs`|1|45 tests，44 pass，1 fail；测试过严地把无效ACK后后端关闭/guard失效的固定 STATE_CONFLICT 写成 BLOCKED_LIVE，已纠正测试并要求停止后端|
|awaiting-input-red.log|`node --test --test-reporter=tap desktop/tests/profile-approval.test.cjs`|1|45 tests，44 pass，1 fail；新增 awaiting_input 活动态断言实际失败，随后从 INACTIVE 删除|
|green-target.log|`node --test --test-reporter=tap desktop/tests/profile-approval.test.cjs desktop/tests/model-approval.test.cjs desktop/tests/context-approval.test.cjs`|0|82 tests，82 pass，0 fail/cancelled/skipped/todo；新档案48，旧plain/context关联34；5361.4294ms|
|本次工具输出|`git diff --check -- desktop/model-approval.cjs desktop/preload.cjs desktop/profile-approval.cjs desktop/tests/profile-approval.test.cjs`|0|无空白错误输出|

`awaiting_input` 为活动状态的依据：`src/cn_contract/assistant/service.py` 的取消及恢复处理、`web/static/assistant-state.mjs` 与 `assistant-context.mjs` 的 ACTIVE 状态。允许的非活动终态仅 completed/cancelled/failed/interrupted/blocked；未知状态拒绝。没有修改旧 plain/context 的状态政策。

4个作者文件冻结清单见 `inputs.json`。测试使用 Native 作者的真实 model-session/profile-basis 实现；HTTP 服务、后端 ACK、窗口是合成夹具。本目录不是实际 Windows 原生窗口或完整桌面回归证明；相关全套验证、实机验证、独立审阅和发布由主任务负责。
