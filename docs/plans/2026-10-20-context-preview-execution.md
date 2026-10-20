# CH-06B2b1：选定历史片段的本机完整预览

2026-10-20，基线 `0d53fdfdae806c6fec90c01cab1531a7cb666831`，沿用用户已批准的v2.1和[上下文接续准备](2026-10-20-library-context-readiness.md)。本文件是实施合同；验证结果另记。

本片闭合选片、服务器重建及完整确定性预览这一接口，不修改普通文字许可或执行路径。下一片将新内容许可、不可变输入格式、调用账本、原生确认与备份迁移一起接通；不能仅将资料拼进旧文字请求。

- 业务DTO仅在domain.py新增独立类型。旧MainRequest、MainPreparedInput、MainSendApproval及现有哈希字节不变。
- 页面/原生调用方只传当前完整scope、composer_revision和1—8个有序不重复saved_citation_id。问题从当前已保存草稿读取，引用从既有持久回执重建；拒绝正文、标题、状态、路径等额外输入。
- 当前用户与来源都须获权；同一所有者、工作区、对话、案件和binding_revision。历史input_revision允许较旧，但未来版本拒绝。当前选中附件不在范围内；已取消选中的旧附件不阻断。已恢复副本、归档会话、过期草稿或撤权不得准备新回答。
- `assistant/context_preview.py`复用来源读取与草稿检查；纯`providers/context_preview.py`负责白名单投影、独立模板与规范JSON。不读当前法库、不创建运行/许可/attempt、不预留费用、不调用主模型/Jev。
- 真正投影包含原问题、所选UUID、标题、有界片段、位置、版本与待核状态。内部metadata、原始路径字段、会话/actor/运行身份不进入传输JSON。资料正文中的字面路径或提示不自动删改，不能把字段白名单宣传为任意内容脱敏。
- 无模型配置仍可读取内容清单及完整系统模板；配置存在时返回完整wire、UTF-8字节数、内容/wire/配置摘要。超输入预算返回`input_too_large`，保留完整本机预览，不截断。不读取密钥、不受旧grant有无或过期影响，也不改变旧grant。
- HTTP入口为`POST /api/assistant/conversations/{id}/context-preview`。虽不写业务记录，仍校验登录、CSRF、同源和完整scope，读取body前后复核；不放入恢复副本可执行白名单。
- 预览`ready`只表示本机投影符合当前配置预算，所有状态均`sending_enabled=false`。本片没有面向律师的新选片UI或原生批准窗口，现有页面不出现可发送资料的错误承诺。

验收按公共codec、预览服务、HTTP和配置读取四个接口：有效失败到通过、同源/跨案/陈旧/失效/恢复反例、完整字节边界与旧V1兼容、真实本机服务合成HTTP请求及零模型调用。完成后独立Spec/Standards复核，适当回归及四开发检查；README/TODO/TASK_STATUS与合成证据正常同步GitHub。

WorkBuddy本轮状态连接后，`wb-93002fc64088`完成两份文件只读计划复核，第三个所请求codec路径不存在即跳过。其“prepare缺字节检查”说法须对照实际`main.build_request`纠正；不据未读源码的推断改动已有保护。最终发送的存储方案另有独立只读审查，不把设计当实现。

实现及本轮实测已记录于[证据](../testing/context-preview/20261020/README.md)：644关联Python通过，广泛回归中止而非全套成功；独立复核与实际Windows HTTP已闭合。律师选片界面、原生资料批准及真正发送仍未实现。后续按[存储设计](2026-10-20-context-send-storage.md)接续。
