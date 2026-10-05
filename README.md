# 群兴合同审查工作台

当前已完成 T00–T10 的来源、统一类型、权限、解析、事实、规则批准门、四类虚构合同闭环、本机 MCP、持久预算、草案修订及中文页面；Scrapling 已安装。T11 的固定评测与40份工程材料已实际运行，能力缺口和法律 gold 保留阻断。T12 受控备份恢复与发布门已实测。T13 守卫和受限内部交付已完成已执行的工程范围；新增 DeepSeek 首批纯离线契约、受控本机两工具 MCP、Codex适配发现及调用元数据修复，当前完整回归1030项/零警告。适配源包0.1.2已准备，独立宿主仍使用0.1.1缓存；本聊天已加载根未验证，实际调用、真实联调、网页ChatGPT连接及生产仍未完成或阻断。**仅限虚构工程演示；不能上传真实材料、签发正式意见或作为生产软件使用。**

现有目录最初为空 Git 仓库；用户确认无其他代码。本次为增量初始化，没有整仓替换、删除用户文件或复制A包运行文本。

实测产物：

- [现状差距与阻断](docs/BASELINE_GAPS.md)
- [任务实测与下一任务](docs/TASK_STATUS.md)
- [来源锁](sources/upstream.lock.json) 与 [复用记录](docs/reuse/)
- [T00测试证据](docs/testing/T00.md)
- [T01模型与审阅](docs/testing/T01-domain.md) 与 [独立审阅](docs/testing/T01-review.md)
- [T02权限和事务](docs/testing/T02.md) 与 [独立安全审阅](docs/testing/T02-review.md)
- [T03解析和锚点](docs/testing/T03.md) 与 [独立攻击审阅](docs/testing/T03-review.md)
- [T04事实与计算](docs/testing/T04.md) 与 [独立信任根审阅](docs/testing/T04-review.md)
- [T05规则与政策](docs/testing/T05.md) 与 [独立攻击审阅](docs/testing/T05-review.md)
- [T06实际四案演示](docs/testing/T06-demo.md)、[父节点验收](docs/testing/T06-parent-checks.md)与[独立攻击审阅](docs/testing/T06-review.md)
- [T07本机SDK实测](docs/testing/T07.md)、[父节点验收](docs/testing/T07-parent-checks.md)与[独立攻击审阅](docs/testing/T07-review.md)
- [T08预算网关实测](docs/testing/T08.md)、[父节点验收](docs/testing/T08-parent-checks.md)与[独立账本审阅](docs/testing/T08-review.md)
- [T09导出实测](docs/testing/T09.md)、[独立审阅](docs/testing/T09-review.md)、[实际Word十页验收](docs/testing/T09-word-visual.md)与[父节点验收](docs/testing/T09-parent-checks.md)
- [T10作者接口与任务实测](docs/testing/T10.md)、[模板依赖实际采用](docs/reuse/T10-dependencies.md)与[HTTP/任务接入决策](docs/adr/0005-http-jobs-and-synthetic-ui.md)
- [T11固定评测与实际范围](docs/testing/T11.md)、[T12安全恢复实测](docs/testing/T12.md)、[安全说明](docs/SECURITY_RUNBOOK.md)与[运维说明](docs/OPERATIONS_RUNBOOK.md)
- [Scrapling安装与使用](docs/tools/SCRAPLING.md)
- [DeepSeek离线适配](docs/testing/DEEPSEEK-offline.md)、[根回归与实际范围](docs/testing/DEEPSEEK-parent-checks.md)、[协议独审](docs/testing/DEEPSEEK-offline-review.md)与[边界独审](docs/testing/DEEPSEEK-boundary-review.md)

在当前 Windows 项目目录运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_sources.py -q
.\.venv\Scripts\python.exe scripts/verify_defaults.py --file config/defaults.json
.\.venv\Scripts\python.exe -m cn_contract.cli config-validate
.\.venv\Scripts\python.exe -m cn_contract.cli schema --check
.\.venv\Scripts\cn-contract.exe --help
.\.venv\Scripts\python.exe scripts/verify_sources.py --mode development
.\.venv\Scripts\python.exe scripts/verify_sources.py --mode release
.\.venv\Scripts\python.exe scripts/verify_runtime_dependencies.py --mode development
.\.venv\Scripts\python.exe scripts/verify_runtime_dependencies.py --mode release
.\.venv\Scripts\python.exe scripts/scrapling_smoke.py
```

development模式核对实际文件和许可隔离，保留13项生产批准警告。release目前必须返回非零：实际采用的G04修订方法、G06 PDF解析、G08 DOCX组件、G10开发工具和G13 MCP SDK的使用范围、依赖或生产审批存在9个实际阻断，不能靠安装成功解除门禁。

Scrapling安装在本项目 `.venv`，Chromium在 `.local/scrapling/browsers`，后续公开网页任务可复用。四项本地虚构HTML验证通过；另实际读取六页公开Microsoft Word API文档，保留TLS校验与原CA字节，详见工具记录。未接入QCC或处理真实合同。

T01 实测全套158项通过；覆盖领域/配置/CLI/来源门，尚不代表业务闭环。事实采用七类`{kind,value}`结构保持JSON往返类型；Decimal事实必须有单位。角色按规格四种命名，后续服务从数据库核对权限。

重建开发环境需Python3.12与Windows AMD64（其他平台另行生成锁）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock -r requirements-build.lock
.\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e .
```

当前验证editable安装；应用/测试锁已扩展为55包，build1包单独锁，55 wheel/97主许可/79依赖边见[T10模板依赖实际采用](docs/reuse/T10-dependencies.md)。仅新增Jinja2和MarkupSafe，原53完整记录及T09安装历史保持；环境71含开发工具。纯读取runtime开发门通过，发布门实际59阻断。生产批准仍为空，独立wheel分发和部署未验收。Scrapling可按其专用锁另外安装，不要求审材料流程加载浏览器。

T02实际全套200项通过，包含42个新权限/事务用例；独立攻击审阅已关闭事务清理与缓存状态缺陷。HTTP测试保留1条上游TestClient/httpx弃用警告。基础服务用法见T02报告；正式签发仍阻断。

T03 最终实测全套269项通过；独立69目标及14攻击探针通过。DOCX未读对象和PDF扫描/注释/隐藏文字有明确缺口；文字层提取不代表视觉等价，OCR及PDF进程解码沙箱未部署。来源发布门仍阻断。

T04 全套345项通过；独立76目标/31攻击探针通过。事实确认/主体决定按版本追加并原子回滚；从只读原件重算解析，阻断伪造已存原文/完整性标记；计算不猜付款基数，不编造企业外查结果。

T05 全套431项通过；独立86目标/45攻击探针通过。法源证据精确绑定服务端取得bytes、正文及元信息hash；适用日期、例外、负责人权限和政策版本由后端核验。14卡仍全draft、9条法源索引pending，现实法律规则批准仍BLOCKED_RULE_APPROVAL。

T06全套511项通过；独立80目标/77攻击探针通过。四份独立虚构DOCX的实际CLI各输出18维、9个JSON文件和受保护SQLite证据；审查12次、确认前候选抽取4次mock调用均保留usage/raw hash，QCC为0。未批准法律规则的维度如实不足，mock不得正式签发；没有Word/PDF制品。

```powershell
.\.venv\Scripts\python.exe -X utf8 -m cn_contract.cli demo --fixture tests/fixtures/synthetic/sales_basic.docx --provider mock --qcc off
```

其余三个实际fixture为service_basic.docx、lease_basic.docx和nda_basic.docx。输出目录为本次实际生成的`.local/review-demo`子目录，不允许通过该演示入口处理其他材料。

T07全套557项通过、零警告；独立46目标/66攻击探针/17授权回归通过。固定mcp/mcp-types2.2.0及httpx2/httpcore2 2.13.1实际向独立本机127.0.0.1模拟服务器握手、发现、调用；调用前检查完整schema/价格/服务器批准，拒绝任意端点和外部schema引用，保留安全原始证据与未知状态。没有真实QCC请求或付费。

T08全套609项通过、零警告；独立52目标/58探针/78关联回归通过。预留、发送标记与收据采用显式Database短事务；网络等待期间无持写Session。超时或未知扣费保持预算预留与次数，不自动重试；对账追加新收据，不伪造成功送达。三组独立缺陷均已复验关闭。

T09全套646项通过、零警告；独立37目标/61探针/136关联回归通过。内部、客户、合同对方三类新报告及内部精确正文原生修订，实际Word六轮/十页检查通过；接受、拒绝各五段全文精确核对，同句未误改，原件不变。复杂对象及对外原件包修订保留人工项；mock正式签发仍BLOCKED_LIVE。

T10已接入六类中文页面、第11节14接口、原文定位、完整事实确认、18维mock审查、五类处置、精确草案批准、三类受众预览下载和持久任务。Jinja2/MarkupSafe实际离线固定hash安装完成。父全套709项/零警告；四类普通浏览器各18维、16份实际下载及四次mock拒签完成，见[T10浏览器记录](docs/testing/T10-browser.md)和[父检查](docs/testing/T10-parent-checks.md)。完整浏览器网络捕获NOT_RUN，声明资源/应用console/后端QCC账本分别核验；法律与生产继续阻断。

启动本机虚构演示：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m cn_contract.cli demo-server --port 8765
```

浏览器访问 `http://127.0.0.1:8765/login`。虚构用户名 `lawyer`、`reviewer`、`assistant`、`admin`，统一模拟密码 `synthetic-only-12345`，只供本机示范。每次启动新建项目`.local/http-demo`独立目录，不覆盖旧案。真实身份与部署认证尚待后续任务。

以lawyer建案，可明确填写复核用户名reviewer。上传仅接受`tests/fixtures/synthetic/`的sales_basic.docx、service_basic.docx、lease_basic.docx、nda_basic.docx四个服务器登记虚构hash；选择基线，逐项核对事实，再开始mock审查。人工处置与整段修改批准是两个操作；明确选定内部/客户/对方范围后生成草案，下载由后端核验当前版本和hash。mock请求正式签发始终显示BLOCKED_LIVE。Q0只登记并选择待人工明确名称的虚构原文候选，不发送请求或收费。

QCC收据报告消费者、补丁后完整法律/数值语义重审、真实法律规则、律师金标准、账号/数据政策/上线批准仍分别未实现或阻断。

T11新增固定84项工程评测登记、40份独立短虚构材料、家族完整开发24/预留盲测16和真实mock工程sampler。能力状态、部分断言和guard分别记录；40材料运行不代表84项全部实现或独立律师盲测。法律金标准两名reviewer及法律指标仍null/pending；实际费用与人工复核时间未测。运行协议与当前实际验证见[评测协议](docs/EVALUATION_PROTOCOL.md)和[T11作者记录](docs/testing/T11.md)。

```powershell
.\.venv\Scripts\python.exe -X utf8 -m cn_contract.cli evaluate --suite tests/acceptance/cases.json --offline --output .local/evaluation-new.json
```

每次使用新的项目内JSON路径以保留旧证据。当前完整能力与真实法律批准未满足，生成实际报告后退出码为1且readiness为BLOCKED；不据此宣称生产完成。离线只使用本机独立模拟服务，实际模型和QCC请求为0，web/demo材料范围保持原四个登记hash。

T12 的恢复只到新目录，旧会话撤销、queued/running 隔离、unknown 积分与调用次数保留；历史制品按原记录/hash从新 root 读取，当前修订和所有发送保持隔离。备份 key resolver 仅接受显式公开虚构测试材料，生产密钥管理未批准。应用出站门、pattern secret 扫描与真实 Git index 扫描不等同操作系统沙箱或全面敏感分类。

```powershell
.\.venv\Scripts\python.exe -X utf8 -m cn_contract.cli release-manifest --mode development --output .local/release-new.json
```

该开发清单绑定当前实际源/config与明确引用的证据 bytes，批准字段为空；`--mode production` 当前实际非零。T11历史评测的时间/hash/源范围保留，新增T12不能把旧84结果冒称当前全面通过。生产许可、律师 gold、真实账户/数据政策、国内host、TLS、OS隔离和最新外部发送高水位仍分别阻断。

T13只添加真实查询前的拒绝门和上线判断，不启用真实请求。`qcc-smoke --approval-id <内部UUID> --plan-id <内部UUID>` 当前缺现实后端认证/批准信任根时非零退出，0供应商请求；没有force、密钥或mock升级选项。任意文件GO/PASS和六类refs非空均不能授权上线；当前现实批准解析缺失，维持BLOCKED。实际费用硬事件由后端账本给NO_GO，其他现实验收未建立。

受限交付和解除条件见[真实联调准备](docs/LIVE_READINESS.md)、[影子记录与测量方法](docs/SHADOW_RUN_REPORT.md)、[上线决定](docs/GO_NO_GO.md)及[T13实际记录](docs/testing/T13.md)。T13阶段实际84项评测为5能力PASS/36 NOT_RUN/16 NOT_IMPLEMENTED/7 NOT_SUPPORTED/20 BLOCKED，58 guard另列；40个新工程run实际39 PASS/1 NOT_SUPPORTED。DeepSeek本批未重跑该材料CLI，不把历史报告当新增完整能力通过。真实live和影子均未执行，法律gold/指标、真实成本与律师分钟未知，不将工程mock/guard通过写成现实上线。

## DeepSeek 首批纯离线契约

用户已批准仅完成接入与离线验证、真实调用暂不开始。`review/deepseek_codec.py`提供请求字典构造、人工JSON响应解析和显式合成USD计价三个纯函数；新增业务DTO仅在domain.py。返回固定`OFFLINE_ONLY / protocol_only`，未知费用为None，不生成ModelResponse、真实账单、批准或律师意见。现有页面/CLI仍使用mock且QCC关闭，不能把离线响应传入审查workflow。

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/unit/test_deepseek_codec.py -q
```

本批121正式目标、308关联回归、两独审138与25均实际通过，根全套936项与原生JUnit逐项相等、0警告。四份登记虚构DOCX的12组离线数据示例实际通过，response/token/rates均人工构造；不是供应商返回或12次法律审查。完整输入666项前后零漂移、314原始文件不变，无新SDK或密钥配置，真实供应商请求0。

最终目标是[ChatGPT插件](docs/reuse/CHATGPT-plugin-target-map.md)。已实现下述本机离线两工具原型、历史[连接源包](plugins/qx-contract-offline-local/README.md)及实际安装/发现的[本机 Codex 适配包](plugins/qx-contract-offline-codex/README.md)。宿主聊天调用尚未验收；真实案件的工作台MCP、身份与文件桥、网页ChatGPT连接仍未实施或阻断。真实DeepSeek transport、持久模型费用账本、价格/数据政策/有限调用批准仍缺失或阻断。

## 本机两工具 MCP 离线入口

2026-10-04已实际验证本机STDIO入口，复用固定MCP2.2.0和现有codec，无新增依赖。此入口供MCP客户端通过标准输入/输出调用，启动后等待协议输入；它不会打开网页或自动连接ChatGPT。

```powershell
.\.venv\Scripts\python.exe -X utf8 -m cn_contract.mcp.offline_server
```

|工具|允许参数|实际范围|
|---|---|---|
|workbench_status|空对象|能力和阻断状态；不读取案件|
|deepseek_offline_example|fixture：sales/service/lease/nda；operation：extract_facts/review_chunk/review_cross_clauses；model：deepseek-flash/deepseek-v4-pro|服务器自行读取固定登记虚构文件，返回请求与人工固定响应；协议验证，不是法律审查|

例如工具参数`{"fixture":"sales","operation":"review_chunk","model":"deepseek-flash"}`。拒绝额外原文、路径、URL、密钥、token、价格、身份和批准；返回费用None/unknown/USD，不生成真实账单或法律结论。目录及祖先链接读取前拒绝，协议错误固定脱敏，服务端默认OTel禁用。

离线MCP实现阶段80目标、348关联、独立144与92、父实际24组合+4拒绝及完整1016回归均通过；失败和修复过程见[父验收](docs/testing/MCP-offline-parent.md)、[作者初版](docs/testing/MCP-offline-author.md)及[修复](docs/testing/MCP-offline-author-repair.md)。历史完整1016包含当时新80和原936，不把不同回归分母相加，也不代替T13原84能力或律师验收。

上一阶段验证当前editable仓库的受控本机虚构入口；帧大小及OS CPU/内存硬限制仍未建立。真实模型/QCC、法律gold、影子试点和生产继续关闭。普通依赖初始化读取与工具不读取凭据分别记录，不宣称整个Python进程没有环境继承。

## 本机离线插件连接源包

本机七文件源包在 `plugins/qx-contract-offline-local`，包含通用及同步Codex兼容清单、64px图标、说明与90项运行绑定hash。交付ZIP为 `dist/qx-contract-offline-local-0.1.0.zip`（10,399 bytes）；运行仍依赖当前仓库 `.venv` 和固定虚构样本，包内没有复制runtime、合同或依赖。

源包阶段从解压配置实际启动两种清单，4次状态、48组固定示例及12次拒绝通过，80项既有目标回归通过；独立格式检查18项和边界实际调用通过。该阶段没有新增业务行为或重跑全套1016；历史命令、hash及限制见[源包验收](docs/testing/PLUGIN-local-package.md)。随后实际宿主发现了 portable 绝对路径不兼容，旧结构检查不能作宿主解析通过；原包保留为历史证据，其入口绑定hash因以下兼容修复过时。

## 本机 Codex 安装与工具发现

上阶段独立宿主验收进程0.159.0-alpha.12.1已确认本机适配包0.1.1安装/启用；按项目目录及配置加载其活动缓存，原生发现恰两个虚构离线工具、toolsError为空。本聊天已加载的插件根尚未核验。原portable包关闭，七文件和ZIP保留，全局配置未改；适配仍依赖当前绝对仓库/.venv，不能直接迁移或当独立runtime分发。

上阶段服务增加有界整数progressToken兼容，4项测试先实际失败，84目标及完整1020通过；已安装声明经SDK的24虚构示例、2状态和12拒绝通过，独立边界113检查与格式32检查通过。这些历史结果及范围见[安装与协议验收](docs/testing/PLUGIN-local-host.md)。

本轮进一步按固定宿主源码复现threadId与整数progressToken调用信封：先4失败/6通过，再仅在tools/call允许36位小写规范UUID，标识不作身份或批准、不传业务handler或反射；list/ping及其他字段继续闭合。94目标和完整1030实际通过，独立246边界检查/242请求通过。五文件源包升级0.1.2并更新90绑定；原0.1.1缓存未动，独立宿主read源版本0.1.2与使用旧缓存的服务发现分别记录，新缓存未物化。本聊天已加载的插件根未验证；用户已确认能看到插件和刷新入口，刷新完成及实际调用仍未确认。详见[调用兼容与当前接入状态](docs/testing/PLUGIN-chat-call-compat.md)。

宿主独立验收进程没有已加载聊天，活动宿主proxy连接未建立；没有新建/resume聊天或启动模型推理。聊天中的实际调用、模型主动选择工具与网页ChatGPT连接分别NOT_RUN，身份/文件桥和真实模型/QCC/法律验收/生产仍阻断。
