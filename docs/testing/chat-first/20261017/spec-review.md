# CH-00A 公共边界抽离：Spec 独立审查

基线：`7b58b92865f0370687427d987fbc8fa42a96c205`。范围：本轮10份已跟踪源码差异、新增storage_bootstrap.py、web/request_context.py及两份对应测试。依据`docs/plans/2026-10-17-shared-boundaries.md`和v2.1第6.4节／CH-00A。

## 结论

发现0项：未见规格缺失、误实现或越界。此结论为静态审查，不是运行通过记录。

- `storage_bootstrap.py:4`保留原12组初始化调用与顺序；其中jobs对应原web.storage，未改DDL、触发器或schema算法。`ops/backup.py:143`只改变初始化函数来源；新导入树无HTTP application依赖。新增schema测试分别固定原有两种结构摘要，未把二者混为同一哈希。
- `web/request_context.py:11–58`与原app中的五个函数逐段一致：认证→同源/CSRF→案件授权次序、256 KiB正文上限、重复键／非有限数／深度30检查及错误映射均保留。未新增绕过鉴权的入口。
- `web/app.py`保留initialize_storage及五个请求辅助函数的直接导入别名。搜索生产调用方与旧测试后，路由/备份/启动/样本运行器均指向适当共享模块；残留旧app导入为兼容测试或实际create_app入口，无遗漏迁移的共享辅助调用方。demo_server把job函数直接改从jobs导入也未改变调用对象。
- 新模块没有反向导入web.app；存储注册函数内部依次导入，未发现新增初始化循环。现有web.storage仍属于持久化注册组成部分，不意味着需要在本切片继续移动整个Web目录。
- 两份新测试采用独立进程观察模块加载、旧别名及schema输出；既有受影响安全/备份目标测试由统筹和另一子代理执行，本审查未重复运行。

未读取真实工作区、未执行迁移、未改产品文件。assistant新schema和迁移尚未实施，按本切片明确范围不计为缺陷；需要后续实现与实测。
