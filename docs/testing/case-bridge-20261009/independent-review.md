# 本机选案桥独立审阅（2026-10-09）

基线 HEAD b50d64c；审阅对象为父任务指定的本机选案桥未提交增量。只改此忽略目录内的独立探针及报告，未改产品、Git索引、分支或源绑定。使用 CodeGraph 与当前源码核对，按 requesting-code-review / Ponytail 流程审阅。

## 优点与覆盖

- 读取复用现有后端身份、案件成员、审查上下文、原件字节与来源校验；没有另建客户端身份权威。
- MCP 无选案、身份、地址或路径参数；固定 loopback 地址且禁代理、禁跳转、有限响应大小。
- 公开 DTO 与审计不包含本机凭据，界面明确同意内容进入聊天。
- 独立探针已通过 ORM 账户禁用/角色/会话/成员撤销后恢复及回滚共8项；授权审计commit后撤权恢复的发布窗口1项；真实合成PDF上传解析后危险文字排除、质量疑点与范围保留1项。

## 已复现的重要问题（均已修复并复验）

1. P2，`src/cn_contract/web/case_bridge.py` 的 `before_flush` 监听仅扫描 ORM new/dirty/deleted，漏掉 `Session.execute` 批量权限写入。成员 delete/insert、用户角色 handling→assistant→handling、会话 revoked true→false 三条实际数据库写路径均使旧token继续返回200。违反撤权恢复必须重新同意；需要覆盖实际批量写入口，包含事务回滚的保守失效。
2. P2，`read()` 异常清理先比较 `self.active is active` 再调用 `close()`，检查与清理不原子。确定性插入时序：旧凭据过期→旧read准备close→新select成功201→旧close清掉新grant与凭据→新token读取401。需要在同一锁内按预期active比较并清理，避免旧请求影响新授权。

## 执行证据

运行目录均为 `D:/Documents/ChatGPT/律所项目`，仅独立虚构材料；不访问真实模型、QCC、真实材料或外部服务。

1. `.venv/Scripts/python.exe -m pytest tests/integration/test_case_bridge.py tests/unit/test_case_bridge_client.py -k 'not actual_loopback' -q`
   - 29 passed / 1 failed / 1 deselected，43.38秒，退出码1。失败为父新增测试读取不存在的 `DocumentRow.storage_key`，不是产品失败。父同步修复后单项复验：
   - `.venv/Scripts/python.exe -m pytest tests/integration/test_case_bridge.py::test_original_tampering_invalidates_read -q --junitxml=.audit-local/case-bridge-review-20261009/tamper-recheck.xml`
   - 1 passed，2.99秒，退出码0。
2. `.venv/Scripts/python.exe -m pytest .audit-local/case-bridge-review-20261009/test_review_probes.py -q --junitxml=.audit-local/case-bridge-review-20261009/probes.xml`
   - 当时9项：8 passed / 1 failed，18.75秒，退出码1。第9项是本审阅探针未在启动前登记合成PDF（策略409）；修正后因缺上传幂等键另失败1项（422）。均为探针构造问题，未归因产品。
3. `.venv/Scripts/python.exe -m pytest .audit-local/case-bridge-review-20261009/test_review_probes.py::test_pdf_uncertainty_remains_excluded_from_bridge -q --junitxml=.audit-local/case-bridge-review-20261009/pdf-recheck.xml`
   - 1 passed，4.75秒，退出码0；策略与解析、读取均走真实本机服务。
4. `.venv/Scripts/python.exe -m pytest .audit-local/case-bridge-review-20261009/test_review_probes.py::test_authority_interleaved_after_grant_commit_cannot_publish -q --junitxml=.audit-local/case-bridge-review-20261009/interleave.xml`
   - 1 passed，3.18秒，退出码0。
5. `.venv/Scripts/python.exe -m pytest .audit-local/case-bridge-review-20261009/test_review_probes.py -k 'bulk_authority or old_read_cleanup' -q --junitxml=.audit-local/case-bridge-review-20261009/bulk-race-red.xml`
   - 4 failed / 10 deselected，11.59秒，退出码1；对应上述两个真实问题，保留RED证据。

## 不作判断的范围与原因

- OS管理员任意改库、进程内存或可执行文件：不属于本次批准的本机普通使用边界，不将理论性管理员攻击作为缺陷。
- 真实模型、QCC、真实合同、正式签发、生产部署：明确关闭或阻断，未执行亦未评价法律质量。
- 浏览器实际点击、无障碍实机行为：仅静态审阅本次前端控件与事件路径，没有作浏览器通过声明。
- 实际8767 TCP及STDIO验收、源绑定重建：父任务正在独立执行，本审阅避免占用端口或使用旧绑定，不重复其结论。
- 无关既存 `.gitignore`、CodeGraph与工具文档：父明确排除。

## 最终复验

父修复后核对当前源码：engine `before_execute` 捕获权限表 Core/bulk DML，维护 TextClause 保守失效；`close(expected=active)` 在同一锁内比较并清理。独立探针仅修改close拦截器以转发新增关键字参数，保留原时序和断言，没有降低条件。

`.venv/Scripts/python.exe -m pytest .audit-local/case-bridge-review-20261009/test_review_probes.py -q --junitxml=.audit-local/case-bridge-review-20261009/final-probes.xml`

结果：14 passed，33.53秒，退出码0。原始四项真实RED全部闭合，8项ORM恢复/回滚、PDF完整性与授权发布窗口关联探针均通过。

最终结论：本次指定工程增量可继续交付流程；0未解决 Critical/Important。实际STDIO/TCP、最终源绑定及父关联回归以父任务独立结果为准，本审阅不代替生产或法律验收。新增账户跨进程维护锁由父另补；任意外部DBAPI/OS管理员改库不纳入服务进程内事件保证。
