# C1 / F03：律师决定进入报告与版本链

2026-10-05。最高优先缺陷的有限工程修复；全部案件、账户和原件是独立虚构数据。原 ReviewRun/意见、每次处置和原件不覆盖。

复用现有处置表，形成稳定的不可变 ReviewDecisionSnapshot：明确编辑实际替换分析/建议/精确文字；reason-only 编辑保持待完成。客户稿隐藏驳回建议，补查/转专项/未完成编辑显示待办；内部保留原意见、备选与全部历史。处置变化使旧草案、批准及相关补丁失效；无关 finding 的独立补丁可继续使用。成果绑定决定快照、原文/事实/规则/政策、run、patch、受众及实际文件 hash。

|实际执行阶段|exit|结果|
|---|---:|---|
|作者最初目标 RED|1|19 failed，0 errors|
|作者权限/旧记录/精确改文字段补强 RED|1|真正产品断言与辅助脚本错误分别保留，不把 fixture 错误计功能 RED|
|作者初版最终目标|0|50 passed|
|作者目标 + domain/model_schema|0|177 passed，0 warnings；之前另有 272 关联回归（不同执行范围）|
|独立初版正式目标|0|50 passed|
|独立服务/事务/API 探针|0|46/46；17 个实际 DOCX；包含两真实 SQLite connection 的串行竞争与原文逐句检查|
|独立多条撤权恢复反例|1|3 情形中 1 通过/2 未满足；role/disabled 各两条旧处置，授权接手全部回滚|
|恢复修复正式 RED|1|GET 两参数 2 failed；部分保存两参数 2 failed|
|恢复后目标/API/四类旧旅程关联|0|69 passed=54 C1+11 APIcontrols+4旅程，0 warnings|
|恢复独立原探针|0|3/3；原两条恢复与单条控制|
|恢复独立 HTTP 探针|0|58/58；role/disabled 各29项，6实际新DOCX|
|恢复独立相关正式测试|0|11 passed / 43 deselected；前端语法检查 exit0|

恢复修复将当前资格状态 ReviewDecisionAuthorityStatus 作为独立实时视图，保持不可变快照/hash 不变。授权律师能读取原记录、逐条接手；部分修正可持久化，但其余有效处置的作者撤权时仍禁止导出、下载和补丁。全部重核后可生成新稿；旧稿继续失效。客户端不能通过 require_authority 字段关闭核验（422）；助手既有读取权保留但写入403，停用身份读写401，跨案403。

原始 RED/目标/关联在 `.audit-local/audit-f03-implementation-20261005` 和 `audit-f03-review-repair-20261005/repair-summary.json`；初次独审在 `audit-c1-docx-review-20261005/REVIEW.md`，恢复独审在同目录 `RECOVERY_RECHECK.md` 与 `recovery-recheck/closure-evidence.json`。辅助脚本初次重用已批准 patch UUID 被正确拒绝，后用新 UUID；恢复 API 探针曾读取公开接口正确过滤的 storage_ref 而报错，改从内部行读取后另存复跑。两次均非产品缺陷。所有证据分母按各次实际运行记录，不相加，也不以旧旅程替代新12份材料。

原始接口和五种处置现已通过本切片独立复验。新增候选通路、工作稿最终确认、修改后完整语义重审、现实法律核对和实际宿主仍单独实施/登记。mock 正式签发持续 BLOCKED_LIVE；本记录不称真实业务、法律模型或生产验收完成。根完整回归另记。
