# T02 独立审阅实际记录

审阅时间：2026-10-02T13:37:37Z。审阅者为未实现T02的独立agent；只读源码和测试，仅写本报告。范围为规格§1、§5、T02及T02-detail中的SQLite权限、原件、追加审计、事务、快照与状态基础。只使用独立虚构输入与系统临时目录；没有真实合同、企查查、外传、付费调用、安装或提交。

## 当前结论

最终定向复验：2026-10-02T13:41:52Z，42项目标测试独立通过，另10组修复攻击探针通过；本报告两个P2类别均已关闭，在本轮范围内没有剩余阻断。工程基础通过不表示真实认证部署、律师样本验收或生产批准；正式批准接口刻意返回NOT_IMPLEMENTED，属于T09待办而非本轮缺陷。本报告没有独立运行全套，因此实现者所报全套数量不列为审阅者的实际PASS。

## 实际运行

|命令或探针|退出码|实际数量/结果|
|---|---:|---|
|`.venv/Scripts/python.exe -m pytest tests/security/test_auth.py tests/security/test_matter_access.py tests/unit/test_versions.py tests/unit/test_state.py -q --tb=short` 首次|1|34 passed / 3 failed；当时实现者正在新增主动RED，三项为错案版本审计、原件缺失错误、确认人冒充；不能视为最终仍存在缺陷|
|同目标命令稳定源码复跑|0|37 passed / 0 failed，7.28s；Starlette TestClient对httpx发一条弃用警告|
|通过PowerShell here-string输入`.venv/Scripts/python.exe -`：Session.close隐式回滚|0|探针执行成功；业务断言失败事件：document_rows=0，original_survives_session_close=true|
|同输入方式：nested commit后outer rollback|0|探针执行成功；业务断言失败事件：document_rows=0，original_exists=true|
|独立七组攻击探针首轮|1|运行到SQL不可变探针时因审阅脚本写成DELETE table而语法报错；这是探针错误，不是实现失败或RED证据；已改为DELETE FROM table重跑|
|独立七组攻击探针修正复跑|0|7 passed / 0 failed：真实DB角色与can_sign、缓存membership撤销、原件hash篡改、parse错案、fact错案、parse/fact直接SQL不可改、新原件使Approval stale及旧Export superseded|
|同输入方式：缓存状态下archived终态攻击|0|探针执行成功；业务断言失败事件：accepted=true，state=awaiting_fact_confirmation|
|目标命令最终定向复验|0|42 passed / 0 failed，9.53s；仍仅一条Starlette/httpx弃用警告|
|修复后10组独立断言探针，PowerShell here-string输入`.venv/Scripts/python.exe -`|0|10 passed / 0 failed；详细范围见下文|

37项目标覆盖包括跨案同hash、admin非成员、伪造Actor.roles、内容读取前授权、cookie/CSRF、过期/撤销/禁用/错用户会话、缓存角色降权、DB版本/审计不可变、日志不含测试正文和密钥、配额并发、错误流与事务回滚、supersedes归属、精确Decimal/单位往返、状态和旧制品失效。独立七组另补member can_sign和parse/fact SQL UPDATE/DELETE四次真实拒绝。以上数量不能合并冒充84项法律验收。

## P2：事务结束时原件清理不覆盖Session.close及保存点

位置：`src/cn_contract/persistence.py`的session_factory及after_commit/after_rollback钩子（初稿行191、207–217）。服务允许直接使用显式session_factory，但未提交的Session关闭仅回滚DB，没有清理新原件。保存点成功会触发after_commit，提前清空父事务的新原件清单，导致随后的父事务回滚遗留文件。异常退出及后续重试可积累不对应任何版本/配额记录的材料和磁盘占用。

可复现代码（`world/meta`仅创建虚构测试用户、案件和临时SQLite）：

```python
with database.session_factory() as db:
    version = persistence.create_version(meta(matter.id), actor, db,
        content=BytesIO(b'SYNTHETIC-CLOSE-ROLLBACK'))
# 新session观察DocumentRow数量0，但storage_root/version.storage_ref仍存在。

db = database.session_factory()
version = persistence.create_version(meta(matter.id), actor, db,
    content=BytesIO(b'SYNTHETIC-NESTED-COMMIT'))
with db.begin_nested():
    pass
db.rollback()
# DocumentRow数量0，但original仍存在。
```

修复已独立验证，状态CLOSED。当前实现按真实SessionTransaction归属记录原件：根事务close/rollback删除未提交文件，保存点commit把文件记录转移到父层，保存点rollback只清自己的文件。独立断言确认普通close后DB/文件/配额均0；保存点内外各创建一份后内commit外rollback均删除；内rollback外commit保留父原件、删除子原件、DB仅1版本且file_count=1，父原件内容可重新授权读取。

## P2：transition_matter使用缓存状态，能够重新开启已归档案件

位置：`src/cn_contract/persistence.py`的transition_matter（初稿行376起）使用未刷新MatterRow的db.get；read_matter也可能返回旧状态。authorize刷新安全记录，但不会刷新案件状态。

可复现顺序：案件先转为parsed；reused=session_factory()获取并持有MatterRow后commit；另一session合法转archived；reused调用transition_matter(..., 'awaiting_fact_confirmation', ...)并commit。实际被接受，归档终态被覆盖为awaiting_fact_confirmation。此路径违反archived无出边的状态图，并且绕过新原件/事实服务已有的归档限制。

修复已独立验证，状态CLOSED。当前state/read/editable及审批/制品读取使用populate_existing取得当前DB值。独立6组缓存归档探针分别确认read_matter返回archived，transition/set_position/save_fact_snapshot/save_parse_result/create_version均拒绝STATE_CONFLICT，归档状态不变且未增加版本、parse或facts。第10组探针持有缓存Matter/Approval/Export后由另一session保存新事实，独立读取确认active_fact_version=1、Approval stale、Export superseded均实时刷新。

## 修复复验断言详情

10组均以每组新建虚构临时SQLite/原件目录运行，服务调用及数据库/磁盘读取由审阅者独立执行。前3组为上述close、内commit外rollback、内rollback父commit；接下来6组为上述缓存归档read及5个可变入口；最后1组为缓存批准/旧导出/当前事实版本刷新。打印实际结果`{"passed":10,"failed":0}`，包含10个明确检查名，命令exit0。42项目标回归是另一次完整运行，未把探针脚本数当作pytest用例数。

## 边界

trusted provision_user/provision_matter/set_membership/revoke_session是服务器初始化或管理原语，未向cookie客户端公开，审阅没有将直接调用这些构造fixture原语当客户端权限绕过。审计目标UUID允许不存在以保存拒绝事件，区别于业务外键。没有测试真实部署、cookie设置端点、文件系统管理员篡改防护、删除案件/共享检索、签发或备份恢复；这些不能在本报告称PASS。
