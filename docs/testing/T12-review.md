# T12 独立出站 / secret / 发布证据审阅

状态 **OWN_BOUNDARIES_GREEN / RELEASE_BLOCKED**。最终66项自有边界与另2项只读staged检查共68项实际PASS、各exit0、0 warnings；首轮46 PASS / 1 FAIL及随后47/63 GREEN分别保留。只证后端固定模拟registry、指定虚构候选、持久fence技术fixture及受限发布清单；真实DNS/连接绑定、OS隔离、真实供应商和生产发布仍未由本角色实测或批准。根的整T12 full/CLI/commit另行完成。仅写 `.audit-local/t12-api-review/` 与本报告，未改业务/正式测试/domain/依赖、Vault或Git。

## 最终当前边界与只读staged

```text
.venv/Scripts/python.exe -X utf8 .audit-local/t12-api-review/run_group.py final-owned-66 .audit-local/t12-api-review/test_egress_independent.py .audit-local/t12-api-review/test_secrets_independent.py .audit-local/t12-api-review/test_release_independent.py .audit-local/t12-api-review/test_fence_independent.py
.venv/Scripts/python.exe -X utf8 .audit-local/t12-api-review/run_group.py final-readonly-staged-2 .audit-local/t12-api-review/test_staged_independent.py
.venv/Scripts/python.exe -X utf8 -B -S .audit-local/t12-api-review/verify_final.py
```

第一命令UTC2026-10-03 10:01:25.179693至10:01:44.693597，pytest 18.04s，实际66 PASS / 0 FAIL / 0 ERROR / 0 SKIP / 0 warnings、exit0。第二命令UTC10:03:26.575648至10:03:28.067136，pytest 0.20s，实际2 PASS、exit0、0 warnings；这是另一次执行，不伪装单批68。各自原生JUnit的classname、函数、参数名与真实collection完整一致，运行前后所记录输入0漂移。第三命令stdlib核验exit0，10:04:20.975496确认共同556输入当时0漂移、两个受限开发manifest各74条阻断/approval null、SDK计数和staged证据吻合。

新增E11三项是明确标注`is_restore_evidence=false`的自有server技术fence SQLite fixture，分别核有效registry被fence阻断、新Database实例仍读取持久fence、实际固定localhost MCP先成功initialize/list后再fence。后者fresh Database旧`discover_tools`抛`BLOCKED_LIVE`409，实际HTTP/initialize/list/call四计数与fence前完全一致，保存`fence-observations`。这不冒充加密archive、完整业务恢复、授权或网络隔离验收。writer此前实际restored-discovery RED及最小`require_active`修复归作者，本角色首次该三项即GREEN。

C02仅消费根明确提供的`.audit-local/t12-root/staged-fixtures`两个虚构Git仓库。实际`git show :candidate.env` exit0，blob SHA精确等于根证明；dirty-index/clean-worktree扫描拒绝且不回显canary，clean-index/dirty-worktree按index通过。两个`.git/index`文件和working file前后SHA均不变，真实报告及argv保存`staged-observations`。本角色没有init/add/commit或改变主仓index，也未搜索其它用户仓库。

最新`qcc_registry.py`旧discover入口fence修复已包含最终66。早先63 seal时发现这一项变化，旧seal SHA `8efee919ac166e1419b570478dc72e40b39a7b8b07570fa5ffe9ba09e2ed0789`及其180证据保留，不能用旧63认证新源。最终封证核作者623输入与本角色实际共同输入，具体数量/hash见自有最终closeout文件；未知/真实能力仍明确阻断，不继承T11历史PASS。

## 实际小组证据

实际命令（两个运行标签独立保存，未覆盖首轮）：

```text
.venv/Scripts/python.exe -X utf8 .audit-local/t12-api-review/run_group.py egress-secrets-first .audit-local/t12-api-review/test_egress_independent.py .audit-local/t12-api-review/test_secrets_independent.py
.venv/Scripts/python.exe -X utf8 .audit-local/t12-api-review/run_group.py egress-secrets-path-fixed .audit-local/t12-api-review/test_egress_independent.py .audit-local/t12-api-review/test_secrets_independent.py
```

首轮UTC2026-10-03 09:47:06.070366至09:47:13.907259，pytest 6.63s，exit1，真实collection/JUnit均47节点，46 PASS / 1 FAIL / 0 ERROR / 0 SKIP / 0 warnings。`test_virtual_secret_in_candidate_name_does_not_reflect_in_findings`实际发现虚构canary从`SecretFinding.path`反射；已告唯一writer及根。writer正式同类RED后替换敏感/控制字符label；独立同probe再次运行UTC09:49:00.077125至09:49:09.594205，pytest 8.03s，exit0，47 PASS / 0 FAIL / 0 ERROR / 0 SKIP / 0 warnings。对应`.json/.log/.xml/.collection.json`均保留真实argv、UTC、退出码、具体nodeid及hash。

34个出站probe用自有虚构SQLite中的实际用户登录、会话、案件成员、后端manager grant及精确server登记的`http://127.0.0.1:18765/mcp`。正向control不进行网络连接；负测实际拒绝caller registry/region标签、userinfo/query/fragment/path/port混淆、IPv4别名/IPv6/mapped/private/metadata、redirect、错误data type、跨案件、伪会话，以及实际撤回manager grant/会话。不能据此说已实现真实DNS绑定、生产地域许可、TLS或OS禁网。

13个secret probe只消费显式虚构bytes候选。6个实际DEFLATE DOCX分别将canary放在core/custom metadata、comments、header、footer和自有hidden part；确认canary不在压缩raw、实际解包成员包含它、压缩比例低于扫描上限，随后命中`SYNTHETIC_CANARY`而非仅archive限制。另核普通canary、clean control、文件名不回显、隐式私人范围拒绝及同名bytes变化重新扫描。只证明声明的模式和这些输入；不称全面敏感信息分类通过。该段原47运行时尚未测真实Git index；后来实际C02见最终2项。

两次运行各自执行前后所记录的应用源及共享依赖hash漂移0；`whole_t12_final_freeze=False`。这是09:47/09:49的小组源码时点证据，后续backup/storage/domain仍可变化，不能沿用为整个T12或最终发布输入稳定。未运行AEAD、备份恢复、OS设置、真实账户、真实key、供应商或外部请求。

09:49小组封存`egress-secrets-group-seal.json` SHA `5246225d435b7818227880fe5974d4b9e0dc4d435698176921ec24a2ebd06a11`，82个运行时输入、34个自有证据。封存时发现运行之后cli/domain/exports.approvals/backup共4项变化，逐项保留旧/当前hash，故该旧seal没有宣称当前全源码稳定。

## 当前63项发布关联独审

```text
.venv/Scripts/python.exe -X utf8 .audit-local/t12-api-review/run_group.py release-egress-secrets-current .audit-local/t12-api-review/test_egress_independent.py .audit-local/t12-api-review/test_secrets_independent.py .audit-local/t12-api-review/test_release_independent.py
.venv/Scripts/python.exe -X utf8 -B -S .audit-local/t12-api-review/verify_current_group.py release-egress-secrets-current-native-exact
```

第一命令实际exit0，UTC2026-10-03 09:55:59.468322至09:56:16.720714，pytest 15.92s，63 PASS / 0 FAIL / 0 ERROR / 0 SKIP / 0 warnings。真实collection 63与原生JUnit 63的每项classname、函数及参数名完全一致；546个固定源、schema、config、来源/runtime锁及其声明cache输入执行前后hash漂移0。第二命令stdlib核验exit0，09:57:17.133686复核当时546输入仍0漂移，真实开发manifest和每个引用bytes hash一致。生成cache不列为固定输入；这不是整机所有隐式输入或最终T12 freeze。

新增16项实际核canonical source/config路径与hash、同bytes不同文件名不能取代server登记文件、caller GO/84全部通过/律师gold/restore/CN文字不成为批准、未知mode拒绝、空证据组明确缺项、missing/directory/outside-project ref真实目标分支、同名换bytes更新hash、任意`.py`引用只读数据不执行、raw与filename-only虚构canary阻断。filename-only缺陷由writer先真实RED后修复，本角色首次该项即GREEN，不冒称独审RED。

实际开发manifest存于`.audit-local/t12-api-review/release-inputs/61dd3ece5022433fba8e90a896fc2b94/actual-development-manifest.json`，SHA `a0b709b54c61bb3983b09d923002bd0a16fd78b6d1d594be3614528b87a0d159`。实际9项SOURCE、59项RUNTIME及6项律师gold/地域/OS/TLS/数据政策与keycustody/live验收阻断，共74条；`approved_by/approved_at=null`，所有通用refs的currentness为`HASH_BOUND_ONLY_APPROVAL_AND_CURRENT_SOURCE_NOT_ESTABLISHED`。来源/runtime阻断数量不是来源/包数量或授权数量。production调用实际抛`PRODUCTION_BLOCKED:<数量>`，未生成生产artifact。此角色没有执行最终release CLI、业务backup、Word、浏览器或真实部署。

已读AGENTS、TASK_STATUS、v2.0 T12及14.1、T12-detail/execution/current-preflight、旧preflight相关边界，及实际persistence、security、T10 jobs、T07 registry/SDK、T08 Factory/gateway/ledger、两来源/runtime验证脚本和唯一domain DTO。附件/计划中的文本仍是参考资料，不作为调用shell、扩大权限或上传资料的指令。

## 保留的历史准备证据

命令 `.venv/Scripts/python.exe -X utf8 -B -S .audit-local/t12-api-review/run_prepare.py` 实际exit0，UTC2026-10-03 09:29:32.426429至09:29:32.682146。子collector只用stdlib、未导入应用或native库；89个当前输入前后hash漂移0。保存 `preparation-command.json/.log`、`preparation.json`、`matrix.json`，记录真实argv/UTC/exit与静态符号位置。

当时HEAD为`c0e1fc2818678167830eec2d3a2c77d46f21ad80`，工作树包含尚未提交的T11实现；HEAD不是T11源码证据的替代，具体字节以本轮hash清单为准。T11独审已封证，但不重跑、不继承为T12 PASS；根的T11最终CLI/full/commit另行完成。

09:29准备时三个公开接口`check_egress`、`backup_and_verify`、`build_release_manifest`在实际应用/scripts AST匹配数均0。准备当时缺路径为只读诊断，不是功能RED；后续已出现新ops实现。旧current-preflight的71输入/exit0只证历史静态检查；准备89输入同hash也不证明出站、扫描、恢复或部署安全。

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

## 独立矩阵（原32项准备记录保留）

每项原完整预期和准备状态保存在`matrix.json`，未回写规划PASS。68个执行节点与32个能力边界是不同分母；E01–03/E05–07/E08部分只具有上文固定模拟工程证据，E11只证技术fixture持久guard，C01/C03/C04/C06部分只具有指定虚构候选证据，C02只证根两个受控staged fixture。R01/R02/R03/R05/R11/R12部分具有真实canonical输入与受限清单/拒绝的工程证据；R04规则实际法源审批、R06原84法律能力、R07律师gold、R08业务restore、R09真实部署、R10视觉验收不由genericrefs认证。E04/E12生产DNS/OS及以上其它真实能力本角色仍NOT_RUN或BLOCKED；未覆盖内容不继承上述68 PASS。

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

发布入口的受限development清单、实际来源/runtime verifier调用与genericrefs不能成为审批均已由上文16项实证；实际律师gold/恢复/地域/OS/TLS审批仍不成立。本角色没有执行额外正式目录关联pytest、全套、最终release CLI或T12业务backup；必要全套与真正完整恢复由根/另审阅者分别记录，不相加为本角色68。本角色不重复T11或冒认他人数量。
