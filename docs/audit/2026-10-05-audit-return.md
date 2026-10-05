# 独立审计回件核验：证据与 F01–F16 映射

本报告保留本轮最初只读核验时点，正文“CR-01未确认”“未修改产品”等描述均指该时点。随后用户明确接受律师辅助工作稿路线，当前决定见 [ADR 0006](../adr/0006-assisted-review-scope.md)，实施状态见 [ASSISTED_SCOPE](../ASSISTED_SCOPE.md)。本页不将后续实现或新测试倒写为初始核验结果。

核验日期：2026-10-05。只读产品审计；核验时 HEAD 为 `4d0f65abd825f7335c41f72e2209282241be6867`，本机解释器 Python 3.12.14。产品、批准记录、宿主配置和供应商状态没有修改。CR-01 仍为外部报告的建议，不能据此调整首发范围或开放真实材料、模型、QCC、签发。

## 附件与安全盘点

报告：`D:/Downloads/群兴合同审查工作台_独立审计与优先落地报告_v1.0.md`，47,635 bytes。

证据包：`D:/Downloads/群兴合同审查工作台_独立审计证据包_v1.0.zip`，119,705 bytes，SHA-256 `95bc978b93daf7e921a17d30af7179505eed2496fd7d3156a01fbea85a8e9a21`。

实际枚举 27 个普通文件成员，展开总大小 352,038 bytes；逐成员尺寸、压缩尺寸、CRC32、SHA-256 在 `zip-inventory.json`。没有绝对路径、父级逃逸路径、反斜杠或盘符路径、加密成员或符号链接，读取全部成员时 CRC 校验成功。只复制白名单中的 8 个证据文件到本审计目录，没有解压覆盖仓库。`probes/independent_probes.py` 只作数据读取，未执行；`collect_evidence.py` 未执行。

原审计材料声称核验 617 个清单文件（609 工程、8 交接摘要）并在前后保持字节一致。该证据包只有其核验记录，并不重新提供原 617 个材料或 Git 对象；该断言不能由本证据包独立重算全部 617 项。此次另核 `source_excerpts.md` 的 52 段摘录、36 个唯一当前文件，文件哈希和逐行物理行号全部匹配；探针 JSON 引用的 8 个源码 hash 全部匹配；当前插件绑定 90 个仓库文件 hash 全部匹配。

## 计数与环境边界

- `findings.json` 是 F01–F16 共 16 项，无缺号或重复号。
- `independent_probe_results.json` 是 20 个观察、15 符合预期、5 不符。五项为 `META_string_progress`、`DOCX_ordinary_parts`、`PDF_white_hidden`、`SOURCE_plugin_scope`、`EXPORT_rejected_finding`。probe 脚本 exit0 表示完成记录，不能叫 20 项全部通过。
- `commands.json` 记录 6 条普通独立命令：defaults exit0，其余 5 条 exit1。原审计的解释器是 Linux Python3.13.5，超出 `pyproject.toml` 的 `>=3.12,<3.13`；pwdlib/mcp/mcp-types/httpx2 缺失，其他固定依赖版本也不同。其模块导入或锁证据缺失，不证明当前 Windows Python3.12 产品失败。
- 当前历史 JUnit 重新解析得 1030 testcase、0 failure/error/skipped，属于读取历史 XML，没有重跑1030。
- 当前静态84能力登记为5 RUNNABLE、36 NOT_RUN、16 NOT_IMPLEMENTED、7 NOT_SUPPORTED、20 BLOCKED。RUNNABLE不是本次PASS，58守卫不能补足业务能力分母。40合成样本和Word/浏览器成绩属于历史；本轮没有重新运行。
- 当前实际读取9条pending法源，实际 `load_default_cards()` 得14张draft卡。没有新增或批准法源。

## 每项判断

分类允许并存：“可验证问题”指具体可复现行为缺口；“有意受限profile”指源码/ADR明确限定的模式；“未实现”指目标消费者或正例尚不存在；“证据不足”指当前运行/产品效果不能由本轮推出；“需要范围选择”指会改变已获准首发或模型/数据/宿主路线。

|编号|分类|核验结论及实际证据|边界/后续意义|
|---|---|---|---|
|F01|有意受限profile；通用有效推理未实现；需要范围选择|`review/model_adapter.py:64`仅接受精确注册MockProvider，`:123`默认空observations；`workflow.py:110`仅接受固定控制输出，`:285`只许mock_credit。`web/services.py:107`显式MockProvider。报告指明并非加密钥就能变真实审查，成立。|受控mock是已授权离线阶段的明确设计；不应当作真实模型运行事故。新assisted或宿主候选模式须另定入口/模型/数据范围。|
|F02|有意受限profile；案件/新文件桥未实现；需要范围选择|`web/app.py:117`默认四个hash，`:277`拒绝未登记上传；MCP `offline_server.py:213`只注册状态与固定示例两个工具。|“仅四份”适用于默认demo，服务端参数可显式登记其他独立虚构hash；没有通用真实资料政策或插件案件桥。发现两工具不证明新合同旅程。|
|F03|可验证问题；决策消费/版本链未实现|`web/services.py:125`追加FindingDecisionRow；`exports/audience_filter.py:20`直接遍历run.findings并无处置过滤；`approvals.py:127`manifest只有run和patch批准。此次正常导入函数的新合成观察仍投影被reject原建议。|完整HTTP“导出→驳回→旧/新下载”本轮未跑。修改意见、最后有效决定、处置变更失效应成为优先修复；不能以存在append-only决定表就认定闭环。|
|F04|可验证兼容问题；有意保守降级|`docx_adapter.py:154`将styles/settings/font/theme/numbering等一般部件列unsupported；`workflow.py:260`任何缺口全局影响18维。新建正常python-docx三段全部正确读到，但11部件unsupported；C06已有supported观察从reviewed_issue降insufficient_material。|这是普通文档兼容与覆盖粒度问题，非三段正文提取失败。styles可能携带继承隐藏、编号信息，不能无条件白名单。Word/WPS/LibreOffice文件与视觉试验未新增。|
|F05|可验证视觉标记缺口；全面视觉验证未实现|`pdf_adapter.py:26`仅按render mode检查。另造白底白字两个矛盾金额PDF，当前真实parser同时提取两金额、page:1:read且quality/unsupported空。源码docstring明确未证明alpha/遮挡/字体视觉等价。|成立的是这个PDF文字层与标记反例；没有确认真实案件被错误计算或输出。原件hash不能证明可见性；该局部反例不等于全PDF失败或P0事故。|
|F06|未实现；有意显式拒绝|`ocr_adapter.py:4`固定OCR_NOT_DEPLOYED；无OCR/校对消费者，`G07-ocr.md`写reference_only与deferred。|拒绝可靠不等于OCR可用。PaddleOCR/PDF.js和48页是外部候选/计划，未获本轮采用批准，未安装、未跑。|
|F07|实质法律规则消费未实现；现实批准不足；有意受限profile|9pending/14draft实际一致；`workflow.py:287`require_legal_rules直接RULE_UNAPPROVED；`:312`说明批准规则仅登记引用依赖。筛选、时际、触发/例外结构已在rules/evaluator实现，但不等于有效法律推理。|不能批准空法源或把律师使用中复核建议当CR-01已落地；最小法源与候选法律观点范围需用户定夺。|
|F08|受限正例未实现；有意生产拒签；需要范围选择|`approvals.py:166`通过当前性/权限/hash核验仍恒BLOCKED_LIVE；规格`:634/636`确有专门人工录入复核fixture的非生产审批状态机正例要求。|缺这个受限正例成立，生产拒签本身正确。工作稿交付确认与生产签发分离是新范围建议，不能因CR-01未确认就直接实现或将旧T10正例记PASS。|
|F09|有意受限profile；补丁后完整语义重审未实现|正文full-anchor整段修订、复杂对象人工降级及已有页眉拒绝在`redline_adapter.py:45/107`和ADR0004明确；`prepare_exports`只生成副本，无完整合同再审链。|不支持页眉是诚实降级，并非已证实错位修改；历史Word打开/接受/拒绝成绩保留，本轮未重跑WPS/Word。不能宣称任意文档无损。|
|F10|有意关闭live；真实账单/费用语义证据不足；模型ledger未实现|queries ledger已有持久原子预留、发送claim、sent_unknown与不自动重发（不是只有DTO）；reconcile显式synthetic_credit。DeepSeek仅pure offline codec，没有真实transport与货币持久ledger。|报告方向成立，但“骨架”需保留既有工程实现与历史模拟测试范围。真实账户/schema/价格/许可/实际扣费仍未验证，不应外呼补证。|
|F11|当前宿主运行证据不足；有意本机适配；需要入口选择|源码0.1.2绑定90/90；`.mcp.json`使用本机绝对路径，manifest声明runtime不打包、hash不自动执行。此次未核当前加载cache/实际入口进程/聊天call。|不能由旧0.1.1记录推出当前cache仍旧，也不能由源0.1.2推出已加载；绝对入口是当前机适配的明确选择，不是portable发布已损坏。|
|F12|有意受限profile；潜在通用协议兼容缺口；宿主影响证据不足|`offline_server.py:133`明确local profile不接string progressToken；本轮string=false/int=true/bool=false/规范UUID=true。已安装锁定SDK `.venv/Lib/site-packages/mcp_types/_types.py:36`是str\|int。|技术差异成立，但不是目标宿主已失败的证明。字符串兼容要有界且不赋予权限；是否扩大离线profile需选择，不能宽放所有metadata。|
|F13|可验证扫描缺口|`scripts/verify_sources.py:12`RUNTIME_DIRS不含plugins；本轮同一独立虚构受限hash放src与plugins，只命中src/probe.txt。`source_excerpts`源hash/物理行完全匹配。|证明扫描范围缺口，不证明当前插件已有AGPL/侵权内容；应按实际交付入口补来源门，不删除隔离证据。|
|F14|业务/法律效果证据不足；当前登记有意诚实阻断；需要范围选择|本轮静态84与历史1030解析均与回件一致；评测协议明确guard与业务PASS分开、gold pending、指标null。|尚未证实当前文件虚报全84通过。开发者看过保留blind不能叫独立盲测；延后双律师gold建议未改变原历史成绩与生产门。|
|F15|筛选交接包可复现性证据不足；非当前产品失败|原审计包没有运行venv/wheel和部分.audit-local，且使用不支持的Python3.13；本机3.12.14能正常导入security/MCP与parser，局部核验实际成功。|128缺失路径是原筛选副本的缺证，不能外推原仓库不存在/伪造。本轮未重建环境，未重新执行全部runtime gate或1030/84。|
|F16|生产隔离/现实身份与数据证据不足；部分未实现；有意阻断live|源码会话重核、角色/成员、CSRF、原件hash/重解析与loopback出站保护存在。解析直接在进程执行、无OS/CPU/内存沙箱证明，readiness保持BLOCKED。|缺独立生产环境证据不等于已证实越权；本轮未重跑权限HTTP/DB旅程或供应商。OCR新worker会增加边界，属于未来上线验收。|

## 优先级建议（未实施）

1. 可先给 F03、F04、F13 准备明确的失败验收和最小修复范围；F05应在扩大PDF事实消费前纳入质量分流。保留mock、真实外发关闭和所有现有批准边界。
2. F01/F02/F06/F07/F08/F09需要先把CR-01、日常入口、模型与资料边界、扫描需求、工作稿交付方式做范围选择。审计中的12合同、48页、10工作日均为计划，不能升级实测或承诺。
3. F11/F12通过一次经授权的目标宿主实际调用决定实际阻断点。仅源码/SDK/metadata函数通过不足以称聊天入口通过。
4. F10/F14/F15/F16保持真实付费、法律成绩和生产状态阻断；合成工程验证可以独立开展，不需要QCC成为材料内审查前置依赖。

## 本轮实际命令及限制

|动作|退出码/结果|性质|
|---|---|---|
|静态ZIP盘点与每成员读/hash|0；27成员、CRC全部可读取|新只读核验|
|`git rev-parse HEAD`、`.venv/Scripts/python.exe --version`|0；HEAD4d0f65a、Python3.12.14|新只读核验|
|自写local_verify.py第一次运行|1；tests helper import路径未设|核验脚本导入失败，不算产品功能RED|
|加项目根sys.path后运行local_verify.py|0；5组局部行为已记录，8源码hash/90binding相符|新合成局部观察，不是pytest计数|
|局部结果字段修正后`.venv/Scripts/python.exe -X utf8 .../local_verify.py`|0；C06变化、18全局材料不足与其余4组行为明确|最终局部观察结果见JSON|
|摘录hash/物理行crosscheck第一次|Python报错：编码拼写utf8-sig；同shell后续git造成外层0|核验辅助失败，非产品；后续分开执行|
|修正utf-8-sig后的摘录crosscheck|0；52段/36文件hash与物理行0不符|新静态核验|
|规则计数校正，直接load_default_cards|0；14draft|此前通用glob只查顶层status误得0，已修正JSON，不算产品缺卡|
|能力登记与历史JUnit解析|0；84静态、历史1030/0failure/error/skipped|没有执行测试|

没有运行完整pytest、84能力CLI、40材料流水线、真实浏览器、Word/WPS、OCR、SDK子进程或真实宿主聊天call；没有模型/QCC/外网调用、真实资料或密钥访问、全局配置更改、提交、推送或发布。仅本审计目录新增复制证据、自写局部核验与独立虚构DOCX/PDF/扫描标记。

## 后续 CR-01 实施结果（独立于上述初始核验）

用户随后明确采用律师辅助工作稿路线。当前有限工程验收见 [父实际记录](../testing/ASSISTED-parent.md)：完整1346项通过，12新虚构API旅程、实际浏览器/客户DOCX与具体版本确认另证。F03决定与成果、F04普通DOCX、F05已列PDF视觉来源反例、F12有界字符串元数据、F13插件扫描的可复现缺口分别经过RED和独立闭合；不外推任意文档、法律结论或生产。

F01/F02增加了显式人工候选及12份新虚构本机文件通路，真实推理与插件案件桥仍缺；F11源启动增加100文件/57版本绑定及真实SDK/STDIO，仅源验收，未核当前宿主加载。F06仅固定版本/许可/平台预检，OCR与原页viewer未部署、48页未跑。F07法源批准/实质法律消费、F09完整修改重审、F10真实模型费用与供应商、F14法律gold及F16生产批准仍未落实。F08增加具体版本工作稿确认，正式签发继续阻断；未将历史受限签发正例或生产门追记PASS。F15仍未进行全环境重建，本机开发门实际读取通过不能替代可分发环境复原。
