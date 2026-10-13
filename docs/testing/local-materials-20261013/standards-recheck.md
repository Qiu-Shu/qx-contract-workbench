# Standards 修复复审

2026-10-13，基于4823d79之后当前未提交差异；未改产品代码。

原两项P2关闭：backup.py:245在实际快照的BEGIN IMMEDIATE维护事务内重验LOCAL案件；workflow.py:341在权限验证后、解析与mock调用前拒绝LOCAL案件。原探针和移植回归合计6 passed，exit0，4.86秒；备份拒绝后cnbak数0。

首次复跑原审计探针得到2 failed/4 passed，原因是探针用异常字符串匹配政策代码，而ServiceError字符串固定脱敏为request blocked。此时实际产品已正确拒绝。只将审计探针改为核对异常code后取得上述6通过；保留recheck-result.xml与recheck-code-result.xml，不覆盖首轮RED。

另复跑当前修改的表单与三受众导出目标：2 passed，exit0，24.94秒，但有1个PytestUnhandledThreadExceptionWarning。synthetic-single-worker于claim_next_job→quarantined→BEGIN IMMEDIATE触发database is locked而退出（demo_server.py:41/persistence.py:181）。未诊断根因，不能将本次记为0警告；建议主回归关注worker锁争用。详见recheck-copy-result.xml。

两份runtime-binding各122个文件hash匹配，均CRLF0；git diff --check exit0，仅测试文件LF转换提示。其余当前差异为本机人工来源文案纠正，未见新增安全边界变更或独立smell问题。

复审只覆盖上述边界及修改目标；未运行完整套件、浏览器/Word，未读真实工作库。原两项整改通过不等于生产或法律质量验收。
