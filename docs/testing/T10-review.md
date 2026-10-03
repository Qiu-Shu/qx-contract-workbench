# T10 独立 API / jobs /业务审阅

截至 `2026-10-03T08:26:37.706101+00:00`，当前冻结输入上，独立80项、6个正式目标文件41项、12个关联文件195项均实际退出0；0失败、0错误、0跳过，共316个case。全部最终运行前后输入清单相同，封证时逐项再次比较同字节。本轮实证发现的撤销批准后幂等重放P2已修复，并以相同独立探针复验。当前受审工程范围未留已实证未修复P1/P2。此结论仅限本报告实际范围，生产完成及真实法律验收仍阻断。

基线提交 `2d7def7f2ab579f99ce9b493301448760de3c411`；封证时HEAD `2d7def7f2ab579f99ce9b493301448760de3c411`。作者冻结190文件SHA `3789b6ff3a4bb14358ae1022cc0d08bc99a2d168e4c5d651f2aadc4632ac5ddc`；本审阅106输入与作者共有97项，实际逐项比较0差异，包括受审执行源码、固定数据与执行目标。额外作者测试属于作者范围，不借用其PASS。审阅仅写 `.audit-local/t10-api-review/` 与本报告，未写业务源码、正式测试、依赖锁、TASK_STATUS或Vault；唯一作者负责业务修复，根节点负责真正浏览器/Word/全量/提交。固定四份虚构合同与provenance共5文件SHA逐项与准备基线相同。

## 实际结果与命令

完整argv、UTC起止、退出码、JUnit数量、日志SHA和运行前后输入SHA在各同名 `.json/.xml/.log` 中。以下数量为passed/failed/errors/skipped；不是规格84验收合计。历史失败文件保留，不用最后GREEN覆盖。

| 实际证据label | 开始UTC | 退出码 | P/F/E/S | 输入同字节 | 说明 |
|---|---|---:|---|---|---|
| `independent-first` | 2026-10-03T08:04:50.269130+00:00 | 1 | 60/4/0/0 | false | 两项真实P2；另两项只是独立oracle漏接合法STATE_CONFLICT。 |
| `query-first` | 2026-10-03T08:07:00.068053+00:00 | 1 | 1/4/0/0 | true | 四项辅助夹具错误：同名工具注册未替换原SDK工具；非业务RED。 |
| `query-adapted` | 2026-10-03T08:07:46.281537+00:00 | 0 | 5/0/0/0 | false | 改用SDK公开remove_tool后5实际通过，源码同时仍变化。 |
| `query-limits` | 2026-10-03T08:09:17.938261+00:00 | 0 | 7/0/0/0 | true | 另含15积分未知占额、跨计划六次硬限。 |
| `independent-replay-and-high` | 2026-10-03T08:11:00.875208+00:00 | 1 | 14/1/0/0 | false | 14通过；1失败为固定四合同不含high的夹具假设。 |
| `high-adapted` | 2026-10-03T08:12:43.449297+00:00 | 0 | 1/0/0/0 | false | 明确服务器技术high夹具，非律师法律分类或gold。 |
| `independent-expanded` | 2026-10-03T08:14:02.170533+00:00 | 0 | 77/0/0/0 | true | 77实际通过，运行前后当时输入清单相同。 |
| `formal-targets-current` | 2026-10-03T08:14:29.883163+00:00 | 0 | 38/0/0/0 | true | 38实际通过；UI journey是API驱动。 |
| `affected-current` | 2026-10-03T08:15:41.193183+00:00 | 0 | 195/0/0/0 | true | 195实际通过；最后jobs/app变化后又跑affected-final。 |
| `independent-outcomes-current` | 2026-10-03T08:21:06.453526+00:00 | 1 | 2/1/0/0 | true | 2通过；1辅助oracle误用error_code；HTTP409已经正确。 |
| `independent-outcomes-adapted` | 2026-10-03T08:21:20.902161+00:00 | 0 | 6/0/0/0 | true | 3独立+3正式实际通过，固定HTTP字段code。 |
| `independent-final` | 2026-10-03T08:22:31.687067+00:00 | 0 | 80/0/0/0 | true | 最终独立80，0失败/错误/跳过。 |
| `formal-final` | 2026-10-03T08:22:31.710627+00:00 | 0 | 41/0/0/0 | true | 最终6正式文件41，0失败/错误/跳过。 |
| `affected-final` | 2026-10-03T08:23:04.828178+00:00 | 0 | 195/0/0/0 | true | 最终12关联文件195，0失败/错误/跳过。 |

最终实际执行命令如下；执行器内部pytest精确argv与JUnit路径以JSON为准。没有运行全套。

```powershell
.venv/Scripts/python.exe -X utf8 .audit-local/t10-api-review/run_review.py independent-final .audit-local/t10-api-review/test_independent_api.py .audit-local/t10-api-review/test_independent_jobs.py .audit-local/t10-api-review/test_independent_query_http.py .audit-local/t10-api-review/test_independent_outcomes.py
```

```powershell
.venv/Scripts/python.exe -X utf8 .audit-local/t10-api-review/run_review.py formal-final tests/integration/test_api.py tests/acceptance/test_ui_journey.py tests/integration/test_api_controls.py tests/integration/test_api_query_jobs.py tests/integration/test_api_replay_current.py tests/integration/test_api_job_outcomes.py
```

```powershell
.venv/Scripts/python.exe -X utf8 .audit-local/t10-api-review/run_review.py affected-final tests/security/test_auth.py tests/security/test_matter_access.py tests/security/test_approval.py tests/unit/test_model_schema.py tests/unit/test_versions.py tests/unit/test_state.py tests/integration/test_exports.py tests/unit/test_patch_preconditions.py tests/integration/test_budget_concurrency.py tests/integration/test_query_recovery.py tests/integration/test_review_flow.py tests/security/test_prompt_injection.py
```

## 复用与实际业务边界

14个规格端点全部以实际TestClient请求检查真实cookie认证、CSRF、case成员和统一安全错误；辅助登录/登出、案件列表、事实/基线、立场、patch同样连实际后端。四种固定虚构合同实际走建案→保护原件→候选事实→确认→mock审查→五种人工决定/精确草案→三受众预览下载。`test_ui_journey.py`的四旅程是API驱动，不是浏览器。

T02实际会话/案件授权、T03保护原件/版本、T04事实、T05规则快照、T06mock工作流和原始attempt、T08实际Factory/账本、T09精确patch/批准/导出被直接调用。业务DTO仍来自唯一domain。assistant保留T02允许的案件上传/候选解析/读取，不能确认事实、启动审查或管理批准；admin无当然案件阅读权。不存在的对象与他案统一拒绝，列表不泄露其他案名。

实际拒绝未登记字节且准确`*/*/original.bin`保护原件数量0、DocumentRow数量0；客户端synthetic/provider/approved/role/member/can_sign声称不生效。同key同输入仅一次、变输入409、撤成员拒绝重放，原件不删除。五种决定保留server身份/时间，ReviewRun原始findings的human_decision不被覆盖。

JobInput公共适配、保护输入字段不可覆盖、双worker仅claim一次、caller捕获异常后继续commit无半job/event、恢复running变blocked不重试均实际验证。3个服务提交与最终状态短事务间实际立场/原件并发变化正确blocked无result。执行前session/member/role/disabled四种实际撤权都不调用mock。真正sealed MockProvider的两次无效输出留failed ReviewRun及两条原始attempt，job为failed/MODEL_OUTPUT_INVALID并保留result_ref；HTTP/public同key重放无新模型attempt。

Q0经HTTP计划/批准/排队完成，0费用/0调用。Q1测试只在服务端精确允许的本机虚构MCP端点上，经实际安装SDK、实际registry绑定和exact Factory完成；客户端标记不能启用。实际callback用另一SQLite连接写入并commit，证明网络期间无HTTP/worker写事务占锁。发送后session撤销或立场变化拒绝保护结果，同时持久ledger/raw仍保留。unknown经真实新Database/app恢复与同key重放无第二发送。实际15积分未知占额保留、余额5/次数1；实际七个HTTP计划最多发6次。默认服务QCC关闭，非Q0无批准端点即BLOCKED_LIVE、0Job/0ledger/0SDK。没有真实外查、真实积分或供应商付款。

高风险草案的正例使用明确服务器技术状态夹具：实际controlled_findings产生的guarantee_material被设为HIGH后走真实存储/审批；固定四合同原来没有high。实际同案不同reviewer无需can_sign可批草案，作者自己被拒绝；mock即使合成签署成员仍正式BLOCKED_LIVE403。此是身份/状态机测试，不是法律gold、律师批准或模型真实法律分类。RuleInvalidationRow正例同样明确技术夹具：实际追加受保护规则证据且Matter/docs fingerprint不变，HTTP/public旧completed任务重放仍409，未重跑模型。

三audience的实际DOCX/ZIP及manual范围、外部包所有part排除私密来源、精确原件/锚点/旧新文本、tamper和撤销后下载拒绝均当前关联测试执行。HTTP下载输出不泄storage_ref或本地路径，不公开挂载original。下载先current/hash验证再离开Session为只读代码检查，未单独instrument每次下载Session生命周期，不把静态推断标实测PASS。

## 实证缺陷、辅助适配与未运行

独立第一轮真实发现同key缓存绕过批准撤销：actual revoke_patch后HTTP patch approve和preview各仍201返回旧对象，共2失败、1组P2。作者在重放路径补actual current_run/load_patch/read_bundle，独立相同2探针和正式2case复验通过，最终80再次通过。另提示过完成状态仅验actor的并发疑点、弱原件glob、公共start_job缺失、失败run被视为completed等；属于静态提示或作者自己的真实RED，不冒充独立RED。

辅助错误均独立列明：漏接STATE_CONFLICT两项；SDK重复同名工具导致4项；固定四fixture无high导致1项；误取error_code导致1项。全部保留原日志，修的只有自有oracle/夹具，未计业务缺陷。3条最后outcomes独立探针是在作者修复后首次执行，不能称它们独立捕获原业务RED。

初始准备矩阵14端点/22轴/6页全部NOT_RUN与27文件基线保留在`matrix.json`；续接起初该文件缺失，本代理实际执行`prepare_matrix.py`退出0才生成。当前`matrix-final.json`逐项绑定最终真实JUnit case。14端点状态为虚构接口实测/预期阻断；HTML-02运行DOM/URL和HTML-03专门CRLF/log测试、EXPORT-02单独Session生命周期instrument保留PARTIALLY_VERIFIED；6页仅HTTP/HTML通过，真正浏览器全部NOT_RUN_BY_REVIEWER。没有用静态source或HTML快照替代浏览器XSS结论。

中文emoji/script/SVG/引号实际HTML不成为未转义标记、JSON原值仍是数据、六页no-store/无外链；Jinja显式autoescape/StrictUndefined、JS textContent/value和无不可信safe/Markup经过只读检查。真正DOM执行、console/network、截图、普通点击、Word打开和全量结果属于根节点单独证据，本报告不继承它们，也不继承T09历史646为T10 PASS。

## 阻断与封证

真实账户/许可/律师批准/数据政策/实际schema-price未知时继续mock和明确阻断。真实人工法律复核正例、法律gold、QCC收据报告消费者、整份补丁后法律/数值重审、自动表格修改及OCR均未由本轮完成；正确阻断不等于这些能力验收。工程演示、法律样本验收、真实试点批准和生产完成独立。

`review-freeze.json`包含最终输入、3组原始JSON/XML/log SHA、本报告/自有探针/执行器/矩阵SHA，5固定源fixture逐项同准备基线；封证脚本拒绝最终非0、数量不符、运行中输入漂移或封证时输入变化。最终结论不能用于后续改动后的新源码。
