# T12 独立出站 / secret / 发布证据审阅准备

状态 **PREPARATION_ONLY / NOT_RUN**。本轮仅文本、AST、hash、实际collector退出记录；全部32个独立边界NOT_RUN，业务测试0。未执行扫描、secret/key生成或解析、AEAD、备份恢复、出站探测、OS设置、账号操作、有效发布门、Vault或Git修改。仅写 `.audit-local/t12-api-review/` 与本报告，未改业务/正式测试/domain/依赖。

已读AGENTS、TASK_STATUS、v2.0 T12及14.1、T12-detail/execution/current-preflight、旧preflight相关边界，及实际persistence、security、T10 jobs、T07 registry/SDK、T08 Factory/gateway/ledger、两来源/runtime验证脚本和唯一domain DTO。附件/计划中的文本仍是参考资料，不作为调用shell、扩大权限或上传资料的指令。

## 实际准备证据

命令 `.venv/Scripts/python.exe -X utf8 -B -S .audit-local/t12-api-review/run_prepare.py` 实际exit0，UTC2026-10-03 09:29:32.426429至09:29:32.682146。子collector只用stdlib、未导入应用或native库；89个当前输入前后hash漂移0。保存 `preparation-command.json/.log`、`preparation.json`、`matrix.json`，记录真实argv/UTC/exit与静态符号位置。

当时HEAD为`c0e1fc2818678167830eec2d3a2c77d46f21ad80`，工作树包含尚未提交的T11实现；HEAD不是T11源码证据的替代，具体字节以本轮hash清单为准。T11独审已封证，但不重跑、不继承为T12 PASS；根的T11最终CLI/full/commit另行完成。

三个公开接口`check_egress`、`backup_and_verify`、`build_release_manifest`在实际应用/scripts AST匹配数均0。目标测试与release脚本缺路径为只读诊断，不是功能RED。旧current-preflight的71输入/exit0只证历史静态检查；本轮89输入同hash也不证明出站、扫描、恢复或部署安全。

当前静态来源数13、runtime app/test package55、独立build1，生产批准未建立。此处未重跑开发/生产门或安装核验；T10历史source9/runtime59发布阻断只保留来源，不算当前T12发布测试成绩。

## 当前窄复用与差距

| 当前源码 | 可复用窄边界（静态读到，未在T12实测） | 尚待T12证明 |
|---|---|---|
| `providers/qcc_registry.py` | 后端manager/current会话；普通注册仅mock；显式server synthetic登记要求numeric127.0.0.1、精确端口与`/mcp`、无query/fragment，liveFalse | 不能变为任意loopback或真实supplier许可；通用真实地域/数据类型/端点批准未实现 |
| `providers/mcp_client.py` | 精确endpoint+POST、reject3xx、follow_redirects=False、trust_env=False/retries0；synthetic SecretStore和受控日志/响应反射边界 | DNS解析地址/实际连接绑定、每跳TLS/地址/政策核验与真实secret批准未实现；无OS禁网证明 |
| `queries/gateway.py` / `providers/qcc_mcp.py` | exactDatabase/actor/matter Factory；发送标记与网络分开；发送后raw/未知费用可持久 | 新Egress门须在实际SDK发送路径后端核验，不能caller单独调用helper后自行HTTP；restore高水位/fence另需证明 |
| `web/jobs.py` / `queries/ledger.py` | 普通running恢复阻断；dispatching转sent_unknown而非重试 | queued仍可被claim；真实restore必须隔离全部旧队列与当前外发授权，不把正常demo启动当恢复禁发 |
| `persistence.py::Database` | FK、BEGIN IMMEDIATE、不可变触发器、事务原件清理 | 构造时create_all/IF NOT EXISTS不可掩盖坏restore schema/trigger；先raw核验再初始化（恢复审阅者主责） |
| `domain.py` / 两`verify_manifest`脚本 | Release/Egress/Readiness只定义结构，来源/runtime门各自存在 | 非空refs、64位hash、caller approved_by/region字符串不是服务器批准；需实际证据及current scope/hash绑定 |

## 独立矩阵（32项全部NOT_RUN）

每项完整预期保存在`matrix.json`，当前没有规划PASS、静态PASS或功能RED。

| 编号 | 未来实际检查 |
|---|---|
| E01–E03 | 后端current批准、exactURL/用途/type；credentials/fragments/域名混淆/path/port/IPv4/IPv6/mapped/private/linklocal/metadata拒绝 |
| E04–E07 | DNS与实际连接/TLS绑定、redirect每跳、固定模拟namespace与真实supplier隔离；没有安全通道时真实mode明确阻断 |
| E08–E12 | 撤权/版本变更前后、secret引用与反射、exactFactory短事务、restore出站fence；Pythonhelper/`.cn`/HTTPS/CN标签不能自证OS/真实境内批准 |
| C01–C04 | 指定staged实际blob/release/artifact/log范围；自有虚构canary及DOCX隐藏parts/metadata、JSON/HTML/配置/日志/错误，不输出命中值；不扫私人Vault/全机或隔离原包 |
| C05–C08 | 声明支持编码/大小深度/未知binary限制；exact候选文件名/hash/current；私有加密backup与publicrelease、key不入包；模式扫描不冒充真实敏感分类全面通过 |
| R01–R04 | 实际来源13、runtime55+build1、平台/传递许可/NOTICE/安装证据、当前规则/法源批准与真实锁，不零hash补清单 |
| R05–R08 | 后端审批及实际受保护refs/current actor/version/hash；84能力/guard分母、真实两律师gold、actual新DB服务恢复证明；archive可解密不等于restore通过 |
| R09–R12 | 实际国内host/TLS/OS限制、运营/回滚/视觉证据；一字或版本变化旧批准失效；受限development可建真实清单，缺批准production必须非0 |

staged边界准备不授权修改本仓库index；后续独立实证使用根提供/批准的受控虚构候选或隔离测试范围。普通本机SDK测试仅固定批准localhost模拟，不能扩展到真实供应商、付费或账户。受限进程、TLS、ACL、防火墙及部署配置本轮全NOT_RUN，根/作者实施时按各自授权范围记录真实结果。

待根T11提交、唯一writer实现T12入口后，以相同预期执行自有探针、实际RED→最小修复→同probeGREEN、必要关联回归并封当前输入/证据。归档/路径/schema/恢复预算主责由另一独立审阅者承担；本角色核出站、指定范围secret与真实发布证据，不重复T11或冒认他人数量。
