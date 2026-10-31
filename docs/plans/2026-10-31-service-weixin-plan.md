# 服务台级微信 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将已连通的本人微信接入整个服务台，自动归集、建会话及调用能力，统一 Jev 辅助和不限费用的 DeepSeek 设置。

**Architecture:** 复用现有会话、TaskDraft、收件来源、执行和模型传输；连接与目标会话解耦。共享辅助判断返回建议，后端进行最终归属、权限和版本核验。

**Tech Stack:** 现有 Python/FastAPI/SQLite 与 Electron/原生 JavaScript，不新增平台依赖。

**Spec:** docs/plans/2026-10-31-service-weixin-design.md

## Global Constraints

- 沿当前分支，保留已有未提交文件；不读取或上传密钥/真实合同，不运行真实模型作为普通测试。
- DeepSeek 不限费用使用明确空上限，不使用巨额数字冒充；旧有限额记录摘要及回执保持兼容。
- 连接限定本人工作区/律师/微信，任务授权逐项校验；Jev 结果不能扩权。
- 不自动重发未知请求，不覆盖原件、消息或执行版本；不得重建第二任务数据库。
- 保留同伴前端；微信入口位于业务能力上方；不添加逐次确认弹窗。

## Review Focus

- 重启恢复显式关闭设置，不因默认开启而再次打开。
- 并行到达/重复/乱序/晚到消息不能形成重复执行或污染原材料版本。
- 切换、归档一个聊天不应断开服务台连接，退出登录必须停止外发。
- Jev 低置信、超时或过期结果不能错误跨案件归属；上下文引用必须可追溯。
- 新增持久记录及空预算必须能升级、回读、备份恢复，不改变旧数据摘要。

### Task 1: 模型显示、不限费用与自动默认

Files: desktop/model-session.cjs、setup-model.js、setup.html、main.cjs、model-control.cjs，src/cn_contract/domain.py、assistant/native_model_control.py、providers/{policy,attempts,profile_attempts}.py、material_attempts.py 及关联调用者/测试。

Interface: 主模型授权 max_total_usd=null 表示不设费用上限；正 Decimal 继续代表旧有限政策。Jev 的独立旧授权不在本任务改为无限。automaticAnalysisPolicy 使用 null，保留用户明确 false；服务台后续消费该政策。

- [ ] 先写并运行 RED：null 后端普通/材料路径可执行；旧有限额仍阻断；未知记录不补发；默认开启且 false 重启保留。
- [ ] 最小实现所有实际调用点、持久配置兼容和 DeepSeek V4.1 Flash 文案。
- [ ] 定向 Python/Node 回归，记录命令/数量/退出码；独立审阅后提交。

### Task 2: 服务台后台、消息批次与共享 Jev 判断

Files: weixin_inbox/personal_runtime.py、personal.py、runtime_records.py、ingress/dispatch/accounts 和必要增量存储；assistant/providers/jev_codec.py、judge*、domain.py、desktop_entry.py、关联测试及资源登记。

Interface: 服务台 start 接受 {session_token,workspace_id,automatic_policy}；旧 conversation start 保持兼容。新增 GET /api/assistant/personal-weixin/status 与 /qr.svg，服务台状态不依赖当前聊天。后端为每个已归属批次保存 conversation/task/source/version；明确规则及共享 Jev 判断统一返回等待/开始/澄清、原事项/新事项、四能力和材料类型，不直接执行外部副作用。

- [ ] 先写 RED：跨聊天连接、两事项分流、续问、5 秒归集、明确等待、重复消息、执行中补件、退出撤权。
- [ ] 实现服务台连接、持久归集和来源关联，复用现有任务与附件登记。必要 schema 增量保留历史对象并补升级/恢复校验。
- [ ] 接入共享 Jev（使用已配置独立凭据、最小输入、单次去重、过期结果丢弃、超时回退）；复用四业务能力与版本冻结。
- [ ] 定向集成/升级/恢复/模型隔离测试，独立审阅后提交；向 Task 3 交付实际接口说明。

### Task 3: 全局微信 UI 与桌面接线

Files: desktop/{personal-weixin,model-control,main,preload}.cjs，assistant.html、assistant-weixin-personal.mjs/css、assistant.mjs 及相关前端/桌面测试。

Interface: 使用 Task 2 服务台接口；桥接校验当前工作区和身份而非页面会话。全局面板显示真实状态及活动事项链接，不改变当前正在编辑的草稿。

- [ ] RED：面板在业务能力上方、无聊天可连接、切换会话不 disable、连点只一次、登出停用。
- [ ] 实现入口、状态及新会话列表刷新；显示辅助模型可用状态，不以文字代替实际配置。
- [ ] Node/页面测试及真实浏览器虚构流程，独立审阅后提交。

### Task 4: 最终验收、打包与原位升级

- [ ] 运行影响范围集成和开发门；合成全链路验证批次、路由、模型、微信回复及恢复。
- [ ] 全变更独立审阅，修复确认问题后冻结源码，构建下一验证版并核对包内源一致。
- [ ] 先备份现有用户资料，确认无活动执行后原位更新，核对原件/旧记录保留；不主动重发真实历史材料。
- [ ] 更新 TASK_STATUS/证据，正常提交推送；记录真实手机业务验收仍需用户侧的部分。
