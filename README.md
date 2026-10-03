# 群兴合同审查工作台

当前已完成 T00–T06 的来源、统一类型、权限、解析、事实、规则批准门及四类虚构合同审查闭环，以及 T07 固定 SDK 本机 MCP 模拟、T08 持久预算网关、T09 三类草案与精确原生正文修订，并已安装 Scrapling 开发工具。T10 已接入中文页面、接口和持久任务，正在完成最终普通浏览器、独立审阅和全套验证，实际状态见任务记录。**仅限虚构工程演示；不能上传真实材料、签发正式意见或作为生产软件使用。**

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
- [Scrapling安装与使用](docs/tools/SCRAPLING.md)

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
