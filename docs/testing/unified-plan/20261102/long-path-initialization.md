# 超长目录首次创建：真实入口修正

2026-11-02。本片在隔离修复副本完成，最终80个不同后端用例通过，四开发门退出0；两轴独审完成。主仓仅同步文档，完整回归仍在原副本运行。

## 实际问题与最小修正

此前超长目录恢复测试采用已有数据库，未覆盖首次创建。本片从独立虚构空目录调用真实initialize_workspace：原2项测试均失败。普通root.exists看不到已存在的长目录；root.mkdir报WinError3/206，尚未进入数据库创建。原失败日志与目录保留。

单变量构造探针另外确认：Database构造函数内create_all早于本地do_connect路径转换，产生unable to open database file；同一长目录的原生SQLite连接成功。该探针1项通过表示观察符合预期，不计入修复后的80项。

仅改两个实现文件：initialize_workspace的存在检查、建目录、身份数据库连接和标记文件写入复用filesystem_path；将原基础表与四表UPDATE/DELETE的8个不可变触发器原样提为私有_initialize_base_schema。默认Database签名和行为保持；本地创建先构造不初始化的Database、安装原有每engine连接钩子，再在异常释放保护内运行同一基础schema和原扩展初始化。既有打开路径仍先只读精确验证，initialize_schema=False不新增DDL。返回路径、storage_root与engine URL继续使用普通逻辑路径。

## 验证范围

真实成功根目录305字符、数据库318字符、标记320字符，含中文、%23和#。直接在目的地建库，未复制预建数据库或搬到短路径。验证当前精确schema、身份、外键/完整性、未登录401、律师登录、再次打开、逻辑路径，以及完整/部分既有目录拒绝且文件不变。另覆盖5组无效凭据、2种可信父目录拒绝和2种真实symlink根/父节点拒绝。

| 实际批次 | 结果 | 退出码 |
| --- | --- | --- |
| init-target-red | 2失败，原入口证据 | 1 |
| init-constructor-probe | 1项诊断观察通过 | 0 |
| init-target-green | 11通过 | 0 |
| init-related | 69通过 | 0 |

共4条pytest命令，最终11+69=80个不同节点；探针、原失败不计入最终通过数。关联覆盖local_workbench、超长升级中断恢复、附件及工作区备份恢复、存储结构与不可变版本。关联保留2条既有record_property/xunit2兼容警告。四门为schema、defaults、sources13、dependencies56运行包及1构建包；生产来源批准警告和native_build_verified=false仍保留，没有联网安装。

作者及独立审查均核对原DDL抽取和默认构造等价；Spec/Standards没有本片待处置发现。Spec终审5条只读命令全退出0；Standards终审6条为0/0/0/0/1/0，其中一次把合法XML properties误判为异常，随后正确解析，原错误保留，不是产品测试失败。两位审阅者均未运行测试。根协调核对固定源码、XML和保护摘要通过；其命名包装检查快照为13条，退出分布{'0': 12, '1': 1}，不含后续收口、直接探索读取或独审命令。

## 保存与后续

固定990份执行摘要，新增1测试文件及2产品文件变化。U212/S90/Q113/H346封印、旧T12准备文件、主仓716保护文件及暂存保持。T仍是旧的0测试准备，不用本片结果覆盖它。报告和状态同步到主仓及修复副本；未合入、提交、推送、安装或发布。

原N983完整回归90073仍运行：2026-11-02T07:18:49.277986+00:00快照5136个结果标记、28个失败，8642仅是收集数。最新新增4个test_weixin_personal_runtime场景：桌面主材料选择、附件优先、指令优先及重审/迟到材料历史。当前仅有失败节点名，未据此认定根因。保持原源码与原失败，只查原句柄，不另起完整套件。下一片优先取得真实栈并在当前R独立定点核验这些新增失败；没有新可处理失败时再为WIN-PATH-02首次rename错误制定不重试的现场诊断。

本片只证明直接initialize_workspace/build_local_app入口，不覆盖desktop_entry完整协议、安装器、UNC或junction。既有WIN-PATH-02最终目录rename间歇失败仍开放，不能用本片备份测试通过将它关闭。商标正式内容仍0/4原答、0/8评分，既有准备不重做；合同补发待既有确认，伙伴接口待办。本片没有模型原答或法律质量采用结论。

证据：C:/Users/Administrator/.codex/worktrees/trademark-regression-repair/律所项目/.audit-local/long-path-initialization-recheck-20261102。
入口：PLAN.md、scope-decision.json、author-review-input.json、author-review.diff、author-source-snapshot.json（files封装）、author-verification-summary.json、checks-summary.json、两轴final-review.json、handoff-verification.json。原失败/探针、全部命令/XML和旧准备均保留。
