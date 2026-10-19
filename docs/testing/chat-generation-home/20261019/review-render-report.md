# 首页生成展示层独立只读复核

2026-10-19；固定基线 f218f44。本复核者未编写 assistant-render.mjs、assistant.html 或 assistant.css，本次没有修改产品文件。

## Standards

本次范围内未发现新增可复现问题，0 项。

- 模型正文、说明、费用和错误均经 textContent 写入（assistant-render.mjs:48、59、75、161）；没有 innerHTML、模型 URL 或动态脚本。源链接由固定 `#message-` 前缀和已在可见集合中的消息 ID 构成（61–64），原文 article 可聚焦且有 :target 边框。
- 费用保留服务器 Decimal 字符串，不经过浮点换算；unknown 不显示零，estimated 明示估算和待核实际扣费，只有 not_sent 显示已确认未发送与费用 0（71–74）。
- 模板默认禁用发送和隐藏找回；发送以 aria-describedby 关联条件/状态，状态有 role=status 与 aria-live=polite；全局 focus-visible 保留键盘焦点；长文本使用 pre-wrap 与 anywhere。没有新增依赖、远程字体、图片、动画库或真实业务事实。
- 复用主代理已完成的 detector：impeccable-detect.json 为 []，exit 文件为 0。没有重复执行视觉检测。该证据不等于屏幕阅读器或实际触屏验收。

## Spec

本次范围内未发现新增可复现问题，0 项。

- 历史结果按 message_id 插入对应律师输入下，缺失可见消息或不同 conversation_id 的项不展示（97–117）；原文链接只在当前页存在，跨页未加载引用不伪造定位。
- 引用归属的服务器前提也已核对：真实适配器 main.py 与 settle 均要求 citation.message_id 和 quote_sha256 等于本次 prepared request；历史查询额外核验当前案件绑定。没有把展示层集合过滤误称为完整权限控制。
- 只展示 received、internal、unverified 的成果并标记“模型生成·内部草稿·待核对”；取消及失败无候选时展示状态/费用，不生成替代答案（54–75）。历史取消可没有候选，但回执仍可显示估算费用，符合已发生调用保留记账要求。
- 切换对话时先清历史节点；撤权、view与当前conversation不符时可见messages为空，发送禁用并隐藏找回（87–94、123、154–165）。实际状态控制器撤权会重置内容，与该防线共同生效。
- 非授权错误显示固定说明，不把原始异常诊断放入页面；网络未知保持单独的找回操作，不改成“重试发送”。已有 browser-first 的丢失202、取消、切换和撤权检查支持这些路径。

## 已复用的实际证据与边界

- browser-first/browser-report.json：9 组通过，exit 0，真实适配器至本机假供应商 6 次 POST，0 外部浏览器请求、0 CSP、0 JavaScript pageerror；本轮没有重跑九组。
- review-render-sources.json：3 个被审展示文件摘要均与 browser-first 的输入摘要一致。能力缓存修复发生在其他文件，需主代理安排最终浏览器复验。
- git diff --check 对三个展示文件退出 0。源码定位通过 CodeGraph，实际渲染来源以当前文件为准。
- 本复核不声称完整 WCAG、物理中文输入法、系统 DPI、实际触屏或安装版验收；主代理另有六图视觉和四组键盘/长文结果，本报告未把它们重复计为本复核测试。

Standards 0 项；Spec 0 项。

后续按主代理另行授权完成最终真实浏览器复验：browser-final/browser-report.json 为原九组加两个能力缓存反例共 11 组通过，exit 0，6 次回环合成 POST，0 外部请求/CSP/pageerror，12 个产品输入前后摘要一致。改字立即撤销及同任务快速选技能后取消均恢复发送可用，且均未调用供应商。本复验无截图、无产品修改，首轮证据保留。
