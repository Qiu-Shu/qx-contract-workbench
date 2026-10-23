# CH-07C2d：桌面档案用途确认入口

日期：2026-10-23。基线 `d3c3b173af0fe3f3f0d878df6793a601e181d081`。实施中，本文不是完成证明。

## 目标与范围

复用 CH-07C2c 的 Python 档案授权及保存协议，把可信保存计划接入现有 Electron 私有管道、会话与原生确认窗口。普通发送流程本片不变。后续统一对话入口按 v2.1 自动保存待核档案草稿，不增加长期并列的“普通发送/建档发送”业务按钮；先完成可信桌面入口，再接统一页面与真实保存回执。

不修改模型、权限或事实核验边界，不启用真实供应商、不处理真实材料、不改安装版本、不安装替换现有应用。本片无 Python 业务改动、无新队列、无新的 HTTP 授权端点、无 Jev 档案授权。

实机发现的最小修正：初轮真实 Electron 页面在自动保存前停止工作。新增真实 HTTP 模块导入链测试稳定复现 `assistant-context.mjs` 返回 404，根因为现有 `web/app.py` 静态资源白名单遗漏该既有模块。本片只补此文件名，不开放任意静态路径；增加模块导入链回归，原业务权限及模型流程不变。此例外是 Python 静态路由修复，不能再称本片 Python 源码完全未变。

## 接口与安全边界

1. 新 `desktop/profile-basis.cjs` 严格验证 domain.MainProfileSendBasis 的 17 字段及 ScopeSnapshot。固定 format/template/purpose/handler/version，严格 bool、安全整数、UUID、摘要、目标接待配对关系及 scope 绑定；拒绝额外字段。
2. 私有操作 `authorize_profile` 只有 session_token、expected_config_version、basis、max_total_usd、valid_for_seconds 五字段。复用 backend、model-control、model-session 的同一连接、lease、busy、撤销及失效规则。
3. 新 `desktopAssistant.authorizeProfile` 接受严格五字段选择信息：conversation_id、request_id、expected_scope、expected_composer_revision、project_intake。正文与保存计划由主进程使用当前会话从本机服务重读。
4. 主进程确认前后核对完整 scope、草稿、无附件、无活动任务、同一 token、全部 basis。技能选择不持久化在草稿中，因此本协议不接收技能字段，服务端拒绝带技能的档案提交；后续统一页面负责当前技能选择的互斥。profile-preview 直接返回 basis，不沿用 context-preview 的外壳。新档案 snapshot 放专用模块，复用现有 HTTP/cookie 校验和原有审批编排。
5. 原生确认详情严格六字段：kind=profile_draft、content、model、max_total_usd、recipient、basis。沿用隔离窗口、封闭网络、默认取消焦点、关闭/Esc/过期/父窗口失效即取消、textContent 输出。
6. 确认窗显示完整本次文字、接收方、预算及本机保存意图：当前档案基线；是否投影接待；已有接待基线或条件创建说明。档案为待核草稿，保护律师更正；本机保存目标不等于该目标历史正文外发。
7. 新分支返回可信 `{ok:true,status:'authorized'|'existing'}`，状态只能来自核验过的原生 ACK。existing 仅表示已登记，不是新许可；不创建或撤销本调用没有新增的授权。旧 plain/context 返回兼容。
8. 新桌面模块同步 package.json 的显式打包清单，不新增依赖。

## 工作分工与验证

- Native：共享 basis、control/backend/session、专门 Node 测试。
- IPC：档案 snapshot/审批分支/preload、专门 Node 测试；与 Native 确认接口，互不改对方文件。
- 主任务：原生窗口详情与界面、打包清单、独立合成 Windows 验证、汇总与发布。
- 独立复核：按规格及工程标准审查，不由作者自评代替。

先运行有意义的失败测试，再实施并跑目标回归；完成后跑完整桌面 Node 测试及相关门禁。保持上阶段 4,393 项 Python 全套结果的适用范围，不因相同源码重新跑 55 分钟全套。实际 Windows 验证只启动本轮自有进程与合成目录，核对原生模态框、取消/确认、用途计划及私有管道；不能把 Node 假窗口当实机验证。若实际操作无法完成，保留失败和剩余项，不标阶段完成。

## 证据与协作

开发证据保存在 `.local/profile-desktop-20261023`。阶段完结前更新 README、TODO、TASK_STATUS 与执行记录；仅发布检查过的源码和文字合成证据。推送前获取远端更新、检查分叉与协作者认领，正常推送并核对 SHA。现有应用与 WIN-PATH-02 保持原状态。WorkBuddy 本轮状态 native_unavailable，未派发复核，独立复核由子智能体完成。

## 已取得的验证结果（待独立复核收尾与发布）

2026-10-23：最终桌面 Node 366、聊天前端 68 通过；四开发门退出0；621份产品/测试输入前后一致。新增静态路由失败回归精准404后修复，相关Python HTTP/浏览器模块/API控制19通过。上阶段4,393项全套是历史结果，本片没有重跑全套。

实际 Windows Electron 44.8.0 + 源Python后台5组检查通过：完整文字/保存计划、100/150/200%应用缩放、小窗口、键盘取消、确认中草稿变化拒绝、真实私有管道authorized回执后停用。进程退出0，621份输入稳定。未提交模型生成，模型/消息/任务/费用/档案/接待记录均0；不把授权成功说成保存成功，不把应用缩放说成物理DPI验收。安装版保持0.4.1，未生成新安装包。


## CH-07C2d 最终验证

CH-07C2d完成可信桌面档案用途确认入口：复用原生窗口和私有管道，展示完整文字、本机保存目标及接待同步意图；保留authorized/existing区别，不把确认当成已保存。实机发现并修复既有聊天模块静态白名单遗漏。桌面366、前端68、相关Python19通过，四门通过；Windows原生5组、621份输入稳定，模型调用与业务记录均0。统一对话自动归档及档案侧栏仍待CH-07C3，安装版0.4.1和WIN-PATH-02开放状态不变。 [实测](../testing/profile-desktop/20261023/README.md)。
