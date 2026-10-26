# D2g5h — 待收件列表与明确分发入口

> **For agentic workers:** Use superpowers:executing-plans inline; checkbox steps track implementation and evidence.

**Goal:** 在既有模拟合同任务的微信授权区域，查看明确历史目标的合成待收件，逐条分发并查明未知结果。

**Architecture:** 沿1a84f75/schema21，新增独立assistant-weixin-pending.mjs，接入assistant.mjs生命周期、离开保护和微信/任务写操作互斥；模板/CSS沿既有details、原生select、列表及文字状态。复用已有GET pending、POST dispatches及精确GET回执；后端仅补静态模块白名单，无后端业务、数据库或依赖变更。

**Tech Stack:** 原生ES模块、node:test、FastAPI合成工作区和现有Chromium验证工具。

## 行为与裁决

- 用户已要求继续上一轮明确的UI下一步；沿既有工作台局部扩展，不另启设计访谈或重构。Impeccable Operate与现有视觉、键盘规则优先。计划、业务边界和测试先行内联实施。
- 入口在“微信收件授权 · 离线测试”内，标题“待收件”。目标选择器复用本机对话分页并保留根对话选项，明确“选择收件原先指定的目标；其他对话不能接收这些记录”。候选是已保存对话，并非授权名单；用户明确点读取后由服务核历史归属。显示固定目标标题，不因当前head变化自动替换；未知/无权限目标遵循既有全页撤权清空策略。
- 每次GET明确root和target、limit20；每页替换至多20条，有下一页及刷新首批。只显示UTC时间转本地时间、文本有无、附件数，不注入HTML，不显示通道账号/原文。验证响应五字段item、明确目标、UUID、上限、UTC、next_cursor锚点及重复/循环页。
- 每条明确“分发到所选对话”；仍由后端核固定历史目标、顺序、权限与恢复隔离。请求只提交descriptor_id。无批量分发、自动分发、消息正文预览、模型或执行调用。成功先核9字段回执与descriptor/target关联，再刷新首批，当前目标为根时刷新任务投影，否则提供固定目标链接。
- POST结果不明或回执不匹配：保留固定root/target/descriptor操作，所有写及目标切换/新建/退出被锁；仅精确GET查回执，不自动或手动重发POST。GET null或不匹配继续保留。权限撤销、CID切换、dispose清空并忽略迟到回复。刷新列表失败不把已确认分发降回未知。
- 写需当前稳定已保存状态、非只读、授权未撤销/归档/恢复、无授权/代际/任务未完成操作。恢复模式不读取pending、不POST。确定拒绝清空列表、提示重新读取；权限错误沿controller.revoke。列表在切目标/刷新开始即清空，失败不展示过期项。
- 页面或材料scope变化、跨模块授权更新、迟到列表/回执、重复点击不得恢复旧操作；不在localStorage保存业务数据。未解决操作在刷新/离页前警示，应用内离开阻断。

## 实施与验收

- [x] 先保留有效功能RED（不是导入错误），完成最小列表与明确分发模块、模板、样式及生命周期接线。
- [x] Node专项54项覆盖正常分页/历史目标/空页/严格响应、双击、迟到与切目标/撤权/销毁、scope变化、dirty/read-only/跨模块互斥、丢ACK只GET、匹配失败/null/拒绝与刷新失败。
- [x] 关联Node444项（前端443+几何脚本1）、Python短组85项、四开发门通过；记录实际ID/命令/退出码与644输入SHA，不叠加中间重复测试。
- [x] 独立Spec/Standards均0遗留，原7探针通过；2项P2严格校验实际RED→GREEN。真实本机合成浏览器通过正常分发、丢ACK只查、窄屏和键盘，外部请求/模型/执行均0、22原收件不变。首轮超时保留；Impeccable检测一次无发现，完成一轮桌面/窄屏视觉核验。
- [ ] 更新README/TODO/TASK_STATUS与阶段记录，保留失败证据；fetch后普通提交推送并核SHA/tree，不动用户AGENTS。Obsidian按本轮session/turn记录，TencentDB沿Stop；本聊天不属于HumanLayer指定两聊天。

不更新安装版0.4.1、不启真实微信/下载解密/真实模型；WIN-PATH-02与原生AV保持OPEN，未运行项目不得写PASS。
