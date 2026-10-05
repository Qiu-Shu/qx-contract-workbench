# C2a：具体工作稿版本核对

状态：设计准备；待 A2 候选通路稳定后实施。CR-01 已确认的逐案版本核对，不放开正式签发，也不替代真实法源核验或修改后全合同语义重审。

复用既有 `exports.approvals._bundle` 对当前 run、原件、事实、规则/政策、律师决定、补丁及实际制品字节的检查。新增不可变 WorkingDraftConfirmation，独立于正式 Approval；业务 DTO 只放 domain.py，持久化复用 append-only ExportRecordRow。

输入：bundle_id、预期 bundle manifest hash、决定 snapshot hash、受众、对实际待补/转专项 finding IDs 的完整确认、核对理由。身份与时间、原文/事实版本、实际 artifact hash 由后端取得。禁止客户端填写正式批准、来源已核、actor、生产或数据出站状态。

仅在显式 assisted_draft 政策下，经当前案件律师会话核对后保存。所有意见须已有明确处置；未处置或待完成编辑不允许确认工作稿。补查/转专项可以保留，但须完整列入当前未完成范围并明确确认；不能把它们改写成无风险。正文中未核依据仍 pending。

保存前与保存结束再检查实际 bundle/current snapshot/所有 artifact hash；新决定、文件、事实、来源、政策、补丁或权限变化后，旧确认只作为历史，不再是当前有效确认。核对本工作稿不会创建正式 Approval，不改变案件为 approved，不启用任何外发或费用。

目标验证：真实 RED；正确人工候选旅程→明确处置→草案→确认正例；未处置/待编辑/漏列待补范围、改决定后旧确认、不同案件、撤权/停用、伪批准/身份字段、错误实际字节及外层回滚反例；旧 mock 默认及正式 BLOCKED_LIVE 保留。实际 API/DOCX 旅程与浏览器视觉分别登记，不把接口断言写成浏览器验收。
